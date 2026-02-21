"""
Recommendation engine — three-layer pipeline.

Layer 1: Personal context from DB (taste profile, visit history, wishlist)
Layer 2: External discovery via Google Places + OpenAI query parsing
Layer 3: OpenAI reasoning and synthesis

MUST NOT import anything from /bot/.
Phase 2: external signal pipeline will plug in here without touching bot handlers.
"""
import asyncio
import json
import logging
import os
import re
from collections import Counter
from typing import Any

import openai

from db.helpers import get_visits_for_chat, get_wishlist_entries
from services.places_service import extract_area, search_places

logger = logging.getLogger(__name__)

VIBE_KEYWORDS = [
    "cosy", "chill", "romantic", "aesthetic", "loud", "lively",
    "value", "cheap", "instagrammable", "quiet", "family", "date",
    "work", "casual", "fancy", "atas", "hawker", "vibey", "noisy",
]


def _get_client() -> openai.AsyncOpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return openai.AsyncOpenAI(api_key=key)


# ── Layer 1 — Personal context ────────────────────────────────────────────────

async def _build_taste_profile(chat_id: str | int, user_id: str | int) -> dict:
    """Build taste profile from visit history and wishlist."""
    visits = await get_visits_for_chat(chat_id)
    wishlist = await get_wishlist_entries(chat_id)

    if not visits:
        return {
            "has_history": False,
            "top_areas": [],
            "vibes": [],
            "occasions": [],
            "recent_visits": [],
            "wishlist_highlights": [],
            "visited_place_ids": set(),
        }

    # Area frequency from wishlist entries
    area_counts = Counter(e.area for e in wishlist if e.area)

    # Vibe keywords extracted from review text
    vibe_counts = Counter()
    for v in visits:
        review = (v["visit"].review or "").lower()
        for kw in VIBE_KEYWORDS:
            if kw in review:
                vibe_counts[kw] += 1

    # Occasion frequency
    occasion_counts = Counter(
        v["visit"].occasion for v in visits if v["visit"].occasion
    )

    # Recent 10 visits for AI context
    recent_visits = []
    for v in visits[:10]:
        visit = v["visit"]
        recent_visits.append({
            "place": v["place_name"],
            "rating": visit.rating,
            "review": (visit.review or "")[:100],
            "occasion": visit.occasion,
        })

    # Wishlist highlights (top 10 by date added)
    wishlist_highlights = [
        {"name": e.name, "area": e.area or "Unknown"}
        for e in wishlist[:10]
    ]

    return {
        "has_history": True,
        "top_areas": [a for a, _ in area_counts.most_common(5)],
        "vibes": [kw for kw, _ in vibe_counts.most_common(5)],
        "occasions": [occ for occ, _ in occasion_counts.most_common(3)],
        "recent_visits": recent_visits,
        "wishlist_highlights": wishlist_highlights,
        "visited_place_ids": {v["visit"].google_place_id for v in visits},
    }


# ── Layer 2a — Query parsing ───────────────────────────────────────────────────

async def _parse_query(client: openai.AsyncOpenAI, query: str) -> dict:
    """Use GPT-4o-mini to extract structured search params from the query."""
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=150,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a query parser for a Singapore F&B recommendation app. "
                        "Extract search parameters from the user query. Return JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Parse this query: "{query}"\n\n'
                        "Return JSON with these fields (use null if not mentioned):\n"
                        '{"area": null, "cuisine": null, "vibe": null, '
                        '"occasion": null, "budget": null, "open_now": false}'
                    ),
                },
            ],
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning("Query parse failed: %s — using empty params", e)
        return {}


# ── Layer 2b — Google Places discovery ────────────────────────────────────────

async def _search_candidates(parsed: dict, raw_query: str) -> list[dict]:
    """Search Google Places for up to 10 candidate restaurants."""
    area = parsed.get("area") or ""
    cuisine = parsed.get("cuisine") or ""

    if area or cuisine:
        parts = [p for p in [cuisine, area, "Singapore"] if p]
        search_text = " ".join(parts)
    else:
        search_text = raw_query

    try:
        return await search_places(search_text, max_results=10)
    except Exception as e:
        logger.error("Places candidate search failed: %s", e)
        return []


# ── Layer 3 — OpenAI reasoning ────────────────────────────────────────────────

async def _call_ai_reasoning(
    client: openai.AsyncOpenAI,
    query: str,
    profile: dict,
    candidates: list[dict],
) -> list[dict]:
    """GPT-4o-mini synthesises taste profile + candidates into ranked recs."""

    # Build taste profile section
    if profile.get("has_history"):
        areas_str = ", ".join(profile["top_areas"]) or "no strong preference"
        vibes_str = ", ".join(profile["vibes"]) or "none detected yet"
        occasions_str = ", ".join(profile["occasions"]) or "mixed"

        recent_lines = ""
        for v in profile["recent_visits"]:
            stars = "⭐" * (v["rating"] or 0) if v["rating"] else "unrated"
            snippet = f' — "{v["review"]}"' if v["review"] else ""
            recent_lines += f"\n  - {v['place']} ({stars}){snippet}"

        wishlist_lines = ""
        for w in profile["wishlist_highlights"]:
            wishlist_lines += f"\n  - {w['name']} ({w['area']})"

        profile_section = (
            "This group's taste profile:\n"
            f"- Favourite areas: {areas_str}\n"
            f"- Vibe preferences: {vibes_str}\n"
            f"- Usual occasions: {occasions_str}\n"
            f"- Recent visits:{recent_lines or ' (none yet)'}\n"
            f"- Wishlist:{wishlist_lines or ' (empty)'}"
        )
    else:
        profile_section = (
            "New user with no visit history yet. "
            "Recommend popular, well-loved Singapore F&B spots suited to the query."
        )

    # Build candidates section
    if candidates:
        cand_lines = ""
        for i, c in enumerate(candidates, 1):
            rating_str = f", Google rating: {c['rating']}" if c.get("rating") else ""
            cand_lines += (
                f"\n{i}. {c['name']} — {c['address']}{rating_str}"
                f"\n   Maps: {c.get('maps_url', '')}"
                f"\n   place_id: {c.get('place_id', '')}"
            )
    else:
        cand_lines = "\n(No external candidates found — use your knowledge of Singapore F&B.)"

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1500,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are eatwatah, a casual and friendly Singaporean F&B recommendation assistant. "
                    "Respond in warm, light Singlish tone — natural, never forced. "
                    "Reference the group's actual taste history where possible. "
                    "Never give generic responses. Return valid JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{profile_section}\n\n"
                    f"External candidates from Google Places:{cand_lines}\n\n"
                    f'User query: "{query}"\n\n'
                    "Return 3–5 recommendations ranked by fit as JSON:\n"
                    '{"recommendations": [{"name": "...", "address": "...", '
                    '"source": "from your wishlist|you might like|trending nearby", '
                    '"reason": "1-2 sentences referencing group history", '
                    '"maps_url": "...", "google_place_id": "..."}]}'
                ),
            },
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    recs = data.get("recommendations", [])

    # Enrich recs with area/lat/lng from the Places candidates where available
    candidate_map = {c.get("place_id", ""): c for c in candidates}
    for rec in recs:
        pid = rec.get("google_place_id", "")
        cand = candidate_map.get(pid, {})
        rec.setdefault("area", cand.get("area") or extract_area(rec.get("address", "")))
        rec.setdefault("lat", cand.get("lat"))
        rec.setdefault("lng", cand.get("lng"))

    return recs


# ── Public entry point ────────────────────────────────────────────────────────

async def get_recommendations(
    query: str,
    chat_id: str | int,
    user_id: str | int,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Three-layer recommendation engine.

    Returns (recommendations, source_labels, has_history).

    recommendations: list of dicts — name, address, reason, maps_url,
                     google_place_id, area, lat, lng
    source_labels:   parallel list of source strings per recommendation
    has_history:     False for new users with no visit data

    Raises on unrecoverable error — ask.py catches and shows friendly message.
    """
    client = _get_client()

    # Layer 1 + Layer 2a — run concurrently (DB fetch and query parsing are independent)
    profile, parsed_query = await asyncio.gather(
        _build_taste_profile(chat_id, user_id),
        _parse_query(client, query),
    )

    # Layer 2b — Places search (needs parsed_query from 2a)
    candidates = await _search_candidates(parsed_query, query)

    # Layer 3 — AI reasoning
    recs = await _call_ai_reasoning(client, query, profile, candidates)

    source_labels = [r.get("source", "you might like") for r in recs]
    return recs, source_labels, profile.get("has_history", False)
