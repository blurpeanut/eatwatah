"""
FastAPI endpoints for the eatwatah-web Mini App frontend.

All routes live under /api/web/ to avoid colliding with the existing
/api/wishlist endpoint (api/routes/wishlist.py) used by the Telegram WebApp.

Auth: Telegram WebApp initData HMAC-SHA256 validation on every request.
DB:   SQLAlchemy async via AsyncSessionLocal — same pool as the rest of the app.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, select

from api.auth import validate_init_data
from db.connection import AsyncSessionLocal
from db.models import Chat, Visit, WishlistEntry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/web", tags=["wishlist-web"])


def _get_bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


# ── Auth helpers ──────────────────────────────────────────────────────────────

async def _require_auth(x_telegram_init_data: str) -> dict:
    """Validate initData. Returns parsed data or raises HTTP 403."""
    valid, data = validate_init_data(x_telegram_init_data, _get_bot_token())
    if not valid:
        raise HTTPException(
            status_code=403,
            detail="Session expired. Close and reopen from Telegram.",
        )
    return data


async def _require_chat_access(chat_id: str, init_data: dict) -> None:
    """Confirm the authenticated user is allowed to access this chat_id.

    Mirrors the security check in api/routes/wishlist.py:
    - Private chats: chat_id must equal the user's own telegram_id.
    - Group chats (negative IDs): chat_id must exist in the Chats table,
      which is only possible if /viewwishlist was called there via the bot.
    """
    user = init_data.get("user") or {}
    chat = init_data.get("chat") or {}
    allowed_ids = {str(user.get("id", "")), str(chat.get("id", ""))} - {""}

    if chat_id in allowed_ids:
        return

    try:
        chat_id_int = int(chat_id)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied.")
    if chat_id_int >= 0:
        raise HTTPException(status_code=403, detail="Access denied.")

    async with AsyncSessionLocal() as session:
        known_chat = await session.scalar(
            select(Chat).where(Chat.chat_id == chat_id)
        )
    if not known_chat:
        raise HTTPException(status_code=403, detail="Access denied.")


def _authed_user_id(init_data: dict) -> str:
    """Return the authenticated user's telegram_id as a string."""
    user = init_data.get("user") or {}
    return str(user.get("id", ""))


# ── Pydantic models ───────────────────────────────────────────────────────────

class VisitPayload(BaseModel):
    google_place_id: str
    logged_by: str          # telegram_id — must match authenticated user
    rating: Optional[int] = None       # 1–5
    review: Optional[str] = None
    occasion: Optional[str] = None     # Casual / Special / Work / Spontaneous


class DeletePayload(BaseModel):
    google_place_id: str
    deleted_by: str         # telegram_id — must match authenticated user


class AddPayload(BaseModel):
    google_place_id: str
    place_name: str
    address: str = ""       # required in WishlistEntry model; default empty string
    area: Optional[str] = None
    cuisine_type: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    added_by: str           # telegram_id — must match authenticated user
    notes: Optional[str] = None
    any_branch: bool = False


# ── GET /api/web/wishlist/{chat_id} ───────────────────────────────────────────

@router.get("/wishlist/{chat_id}")
async def get_wishlist(
    chat_id: str,
    x_telegram_init_data: str = Header(...),
):
    """All active wishlist + visited entries for a chat, newest first.

    Each entry includes the most recent visit data (rating, review, occasion)
    if the place has been visited.
    """
    init_data = await _require_auth(x_telegram_init_data)
    await _require_chat_access(chat_id, init_data)

    try:
        async with AsyncSessionLocal() as session:
            try:
                entries = list(
                    (
                        await session.scalars(
                            select(WishlistEntry)
                            .where(
                                WishlistEntry.chat_id == chat_id,
                                WishlistEntry.status != "deleted",
                            )
                            .order_by(WishlistEntry.date_added.desc())
                        )
                    ).all()
                )

                visits = list(
                    (
                        await session.scalars(
                            select(Visit)
                            .where(Visit.chat_id == chat_id)
                            .order_by(Visit.visited_at.desc())
                        )
                    ).all()
                )
            except Exception as e:
                logger.error("GET /api/web/wishlist/%s DB error: %s", chat_id, e)
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong — try again in a moment.",
                )

        # Build lookup: google_place_id → most recent Visit
        visit_map: dict[str, Visit] = {}
        for v in visits:
            if v.google_place_id not in visit_map:
                visit_map[v.google_place_id] = v

        results = []
        for entry in entries:
            visit = visit_map.get(entry.google_place_id)
            results.append({
                "id": entry.id,
                "google_place_id": entry.google_place_id,
                "name": entry.name,
                "address": entry.address,
                "area": entry.area,
                "cuisine_type": entry.cuisine_type,
                "lat": entry.lat,
                "lng": entry.lng,
                "status": entry.status,
                "any_branch": entry.any_branch,
                "notes": entry.notes,
                "added_by": entry.added_by,
                "date_added": entry.date_added.isoformat() if entry.date_added else None,
                "rating": visit.rating if visit else None,
                "review": visit.review if visit else None,
                "occasion": visit.occasion if visit else None,
                "visited_by": visit.logged_by if visit else None,
                "visited_at": visit.visited_at.isoformat() if visit and visit.visited_at else None,
                "maps_url": f"https://maps.google.com/?place_id={entry.google_place_id}",
            })

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error("GET /api/web/wishlist/%s error: %s", chat_id, e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong — try again in a moment.",
        )


# ── GET /api/web/wishlist/{chat_id}/stats ─────────────────────────────────────

@router.get("/wishlist/{chat_id}/stats")
async def get_wishlist_stats(
    chat_id: str,
    x_telegram_init_data: str = Header(...),
):
    """Per-area counts for map zone colouring.

    Returns a list of {area, total, visited_count, pending_count}.
    Only includes entries where area is not null.
    """
    init_data = await _require_auth(x_telegram_init_data)
    await _require_chat_access(chat_id, init_data)

    try:
        async with AsyncSessionLocal() as session:
            try:
                rows = await session.execute(
                    select(
                        WishlistEntry.area,
                        func.count().label("total"),
                        func.sum(
                            case((WishlistEntry.status == "visited", 1), else_=0)
                        ).label("visited_count"),
                        func.sum(
                            case((WishlistEntry.status == "wishlist", 1), else_=0)
                        ).label("pending_count"),
                    )
                    .where(
                        WishlistEntry.chat_id == chat_id,
                        WishlistEntry.status != "deleted",
                        WishlistEntry.area.isnot(None),
                    )
                    .group_by(WishlistEntry.area)
                )
            except Exception as e:
                logger.error("GET /api/web/wishlist/%s/stats DB error: %s", chat_id, e)
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong — try again in a moment.",
                )

        return [
            {
                "area": row.area,
                "total": row.total,
                "visited_count": int(row.visited_count or 0),
                "pending_count": int(row.pending_count or 0),
            }
            for row in rows
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("GET /api/web/wishlist/%s/stats error: %s", chat_id, e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong — try again in a moment.",
        )


# ── POST /api/web/wishlist/{chat_id}/visit ────────────────────────────────────

@router.post("/wishlist/{chat_id}/visit")
async def mark_visited(
    chat_id: str,
    payload: VisitPayload,
    x_telegram_init_data: str = Header(...),
):
    """Mark a wishlist entry as visited and log the visit.

    Updates wishlist_entries.status → 'visited' and inserts a Visit row.
    Mirrors what the bot does when /visit is called.
    """
    init_data = await _require_auth(x_telegram_init_data)
    await _require_chat_access(chat_id, init_data)

    authed_id = _authed_user_id(init_data)
    if authed_id and payload.logged_by != authed_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = await session.scalar(
                    select(WishlistEntry).where(
                        WishlistEntry.chat_id == chat_id,
                        WishlistEntry.google_place_id == payload.google_place_id,
                        WishlistEntry.status != "deleted",
                    )
                )
                if not entry:
                    raise HTTPException(status_code=404, detail="Entry not found.")

                entry.status = "visited"

                visit = Visit(
                    chat_id=chat_id,
                    google_place_id=payload.google_place_id,
                    place_name=entry.name,
                    logged_by=payload.logged_by,
                    rating=payload.rating,
                    review=payload.review,
                    occasion=payload.occasion,
                    photos=None,
                )
                session.add(visit)
                await session.commit()

            except HTTPException:
                raise
            except Exception as e:
                await session.rollback()
                logger.error("POST /api/web/wishlist/%s/visit DB error: %s", chat_id, e)
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong — try again in a moment.",
                )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("POST /api/web/wishlist/%s/visit error: %s", chat_id, e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong — try again in a moment.",
        )


# ── POST /api/web/wishlist/{chat_id}/delete ───────────────────────────────────

@router.post("/wishlist/{chat_id}/delete")
async def delete_entry(
    chat_id: str,
    payload: DeletePayload,
    x_telegram_init_data: str = Header(...),
):
    """Soft-delete a wishlist entry (status → 'deleted').

    Never hard deletes — row is preserved. Matches existing bot behaviour.
    """
    init_data = await _require_auth(x_telegram_init_data)
    await _require_chat_access(chat_id, init_data)

    authed_id = _authed_user_id(init_data)
    if authed_id and payload.deleted_by != authed_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = await session.scalar(
                    select(WishlistEntry).where(
                        WishlistEntry.chat_id == chat_id,
                        WishlistEntry.google_place_id == payload.google_place_id,
                        WishlistEntry.status != "deleted",
                    )
                )
                if not entry:
                    raise HTTPException(status_code=404, detail="Entry not found.")

                entry.status = "deleted"
                await session.commit()

            except HTTPException:
                raise
            except Exception as e:
                await session.rollback()
                logger.error("POST /api/web/wishlist/%s/delete DB error: %s", chat_id, e)
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong — try again in a moment.",
                )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("POST /api/web/wishlist/%s/delete error: %s", chat_id, e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong — try again in a moment.",
        )


# ── POST /api/web/wishlist/{chat_id}/add ──────────────────────────────────────

@router.post("/wishlist/{chat_id}/add")
async def add_entry(
    chat_id: str,
    payload: AddPayload,
    x_telegram_init_data: str = Header(...),
):
    """Add a new place to the wishlist.

    Checks for an existing non-deleted entry before inserting (409 on duplicate).
    """
    init_data = await _require_auth(x_telegram_init_data)
    await _require_chat_access(chat_id, init_data)

    authed_id = _authed_user_id(init_data)
    if authed_id and payload.added_by != authed_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    try:
        async with AsyncSessionLocal() as session:
            try:
                existing = await session.scalar(
                    select(WishlistEntry).where(
                        WishlistEntry.chat_id == chat_id,
                        WishlistEntry.google_place_id == payload.google_place_id,
                        WishlistEntry.status != "deleted",
                    )
                )
                if existing:
                    raise HTTPException(status_code=409, detail="Place already in wishlist.")

                entry = WishlistEntry(
                    chat_id=chat_id,
                    google_place_id=payload.google_place_id,
                    name=payload.place_name,
                    address=payload.address,
                    area=payload.area,
                    cuisine_type=payload.cuisine_type,
                    lat=payload.lat,
                    lng=payload.lng,
                    added_by=payload.added_by,
                    notes=payload.notes,
                    any_branch=payload.any_branch,
                    status="wishlist",
                )
                session.add(entry)
                await session.commit()

            except HTTPException:
                raise
            except Exception as e:
                await session.rollback()
                logger.error("POST /api/web/wishlist/%s/add DB error: %s", chat_id, e)
                raise HTTPException(
                    status_code=500,
                    detail="Something went wrong — try again in a moment.",
                )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("POST /api/web/wishlist/%s/add error: %s", chat_id, e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong — try again in a moment.",
        )
