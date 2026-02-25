import logging
import os

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import select

from api.auth import validate_init_data
from db.connection import AsyncSessionLocal
from db.models import Visit, WishlistEntry

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


@router.get("/api/wishlist")
async def get_wishlist(
    chat_id: str = Query(..., description="Telegram chat_id to fetch entries for"),
    x_telegram_init_data: str = Header(..., description="Telegram WebApp initData string"),
):
    """Return all active wishlist + visited entries for a chat.

    Auth: Telegram WebApp initData HMAC-SHA256 validation.
    Security: chat_id must match the user.id or chat.id from the validated initData.
    """
    # ── Auth ──────────────────────────────────────────────────────────────────
    bot_token = _get_bot_token()
    valid, data = validate_init_data(x_telegram_init_data, bot_token)
    if not valid:
        raise HTTPException(
            status_code=403,
            detail="Session expired. Close and reopen from Telegram.",
        )

    # ── Security: chat_id must belong to this user ─────────────────────────
    user = data.get("user") or {}
    chat = data.get("chat") or {}
    allowed_ids = {str(user.get("id", "")), str(chat.get("id", ""))} - {""}
    if chat_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="Access denied.")

    # ── DB query ───────────────────────────────────────────────────────────
    try:
        async with AsyncSessionLocal() as session:
            # Both wishlist and visited entries — not deleted
            entries = list(
                (
                    await session.scalars(
                        select(WishlistEntry)
                        .where(
                            WishlistEntry.chat_id == chat_id,
                            WishlistEntry.status.in_(["wishlist", "visited"]),
                        )
                        .order_by(WishlistEntry.date_added.desc())
                    )
                ).all()
            )

            # All visits for this chat, ordered newest first
            visits = list(
                (
                    await session.scalars(
                        select(Visit)
                        .where(Visit.chat_id == chat_id)
                        .order_by(Visit.visited_at.desc())
                    )
                ).all()
            )

        # Build visit lookup: google_place_id → most recent Visit
        visit_map: dict[str, Visit] = {}
        for v in visits:
            if v.google_place_id not in visit_map:
                visit_map[v.google_place_id] = v

        results = []
        for entry in entries:
            visit = visit_map.get(entry.google_place_id)
            results.append({
                "id": entry.id,
                "name": entry.name,
                "address": entry.address,
                "area": entry.area,
                "cuisine_type": entry.cuisine_type,
                "lat": entry.lat,
                "lng": entry.lng,
                "status": entry.status,
                "notes": entry.notes,
                "rating": visit.rating if visit else None,
                "review": visit.review if visit else None,
                "maps_url": f"https://maps.google.com/?place_id={entry.google_place_id}",
            })

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error("GET /api/wishlist error for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=500, detail="Something went wrong — try again in a moment.")
