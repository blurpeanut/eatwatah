import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.exc import IntegrityError

from db.connection import AsyncSessionLocal
from db.models import Chat, Error, User, Visit, WishlistEntry

logger = logging.getLogger(__name__)


# ── Error logging ─────────────────────────────────────────────────────────────

async def log_error(
    telegram_id: int | str | None,
    chat_id: int | str | None,
    command: str | None,
    error_type: str | None,
    message: str | None,
) -> None:
    """Write to Errors table. Never raises — errors in error logging are swallowed."""
    try:
        async with AsyncSessionLocal() as session:
            error = Error(
                telegram_id=str(telegram_id) if telegram_id is not None else None,
                chat_id=str(chat_id) if chat_id is not None else None,
                command=command,
                error_type=error_type,
                message=str(message)[:2000] if message else None,
            )
            session.add(error)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("log_error commit failed: %s", e)
    except Exception as e:
        logger.error("log_error session failed: %s", e)


# ── User / chat registration ──────────────────────────────────────────────────

async def ensure_user_and_chat(
    telegram_id: int | str,
    display_name: str,
    chat_id: int | str,
    chat_type: str,
    chat_name: str | None,
) -> bool:
    """Register user and chat if not already in DB.

    Returns True if this is a newly registered user, False otherwise.
    Never raises — exceptions are caught and logged.
    """
    is_new_user = False
    try:
        async with AsyncSessionLocal() as session:
            try:
                user = await session.scalar(
                    select(User).where(User.telegram_id == str(telegram_id))
                )
                if user is None:
                    is_new_user = True
                    session.add(User(
                        telegram_id=str(telegram_id),
                        display_name=display_name or "Friend",
                    ))

                chat = await session.scalar(
                    select(Chat).where(Chat.chat_id == str(chat_id))
                )
                if chat is None:
                    valid_types = {"private", "group", "supergroup"}
                    ct = chat_type if chat_type in valid_types else "private"
                    session.add(Chat(
                        chat_id=str(chat_id),
                        chat_type=ct,
                        chat_name=chat_name,
                    ))

                await session.commit()
            except IntegrityError:
                await session.rollback()
                is_new_user = False
            except Exception as e:
                await session.rollback()
                logger.error("ensure_user_and_chat error: %s", e)
                is_new_user = False
    except Exception as e:
        logger.error("ensure_user_and_chat session error: %s", e)
    return is_new_user


async def get_user_display_names(telegram_ids: list[str]) -> dict[str, str]:
    """Batch-fetch display names for a list of telegram_ids. Returns id → name dict."""
    if not telegram_ids:
        return {}
    try:
        async with AsyncSessionLocal() as session:
            try:
                rows = await session.execute(
                    select(User.telegram_id, User.display_name).where(
                        User.telegram_id.in_(telegram_ids)
                    )
                )
                return {row[0]: row[1] for row in rows}
            except Exception as e:
                logger.error("get_user_display_names error: %s", e)
                return {}
    except Exception as e:
        logger.error("get_user_display_names session error: %s", e)
        return {}


# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_admin_stats() -> dict:
    """Global stats across all users and chats. For admin use only."""
    async with AsyncSessionLocal() as session:
        try:
            total_users    = await session.scalar(select(func.count(User.id)).where(User.is_deleted == False))
            total_chats    = await session.scalar(select(func.count(Chat.id)))
            total_wishlist = await session.scalar(select(func.count(WishlistEntry.id)).where(WishlistEntry.status != "deleted"))
            total_visits   = await session.scalar(select(func.count(Visit.id)))
            recent_errors  = await session.scalar(
                select(func.count(Error.id)).where(Error.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24))
            )
            return {
                "users":      total_users   or 0,
                "chats":      total_chats   or 0,
                "wishlist":   total_wishlist or 0,
                "visits":     total_visits  or 0,
                "errors_24h": recent_errors or 0,
            }
        finally:
            await session.close()


async def get_chat_stats(chat_id: int | str) -> tuple[int, int]:
    """Return (total_saved, visited_count) for a chat. Returns (0, 0) on error."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                total = await session.scalar(
                    select(func.count(WishlistEntry.id)).where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.status != "deleted",
                    )
                ) or 0
                visited = await session.scalar(
                    select(func.count(WishlistEntry.id)).where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.status == "visited",
                    )
                ) or 0
                return int(total), int(visited)
            except Exception as e:
                logger.error("get_chat_stats error: %s", e)
                return 0, 0
    except Exception as e:
        logger.error("get_chat_stats session error: %s", e)
        return 0, 0


# ── Wishlist reads ────────────────────────────────────────────────────────────

async def get_wishlist_entries(chat_id: int | str) -> list[WishlistEntry]:
    """Fetch active wishlist entries (status='wishlist') for a chat, newest first."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                rows = await session.scalars(
                    select(WishlistEntry)
                    .where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.status == "wishlist",
                    )
                    .order_by(WishlistEntry.date_added.desc())
                )
                return list(rows.all())
            except Exception as e:
                logger.error("get_wishlist_entries error: %s", e)
                return []
    except Exception as e:
        logger.error("get_wishlist_entries session error: %s", e)
        return []


async def get_entry_by_place_and_chat(
    chat_id: int | str,
    google_place_id: str,
) -> WishlistEntry | None:
    """Fetch the active WishlistEntry for a (chat, place_id) pair, or None."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                return await session.scalar(
                    select(WishlistEntry).where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.google_place_id == google_place_id,
                        WishlistEntry.status != "deleted",
                    )
                )
            except Exception as e:
                logger.error("get_entry_by_place_and_chat error: %s", e)
                return None
    except Exception as e:
        logger.error("get_entry_by_place_and_chat session error: %s", e)
        return None


async def get_entry_by_id(entry_id: int) -> WishlistEntry | None:
    """Fetch a single WishlistEntry by primary key."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                return await session.scalar(
                    select(WishlistEntry).where(WishlistEntry.id == entry_id)
                )
            except Exception as e:
                logger.error("get_entry_by_id error: %s", e)
                return None
    except Exception as e:
        logger.error("get_entry_by_id session error: %s", e)
        return None


# ── Wishlist writes ───────────────────────────────────────────────────────────

async def is_duplicate_entry(chat_id: int | str, google_place_id: str) -> bool:
    """Return True if a non-deleted entry with this place_id exists in this chat."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = await session.scalar(
                    select(WishlistEntry).where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.google_place_id == google_place_id,
                        WishlistEntry.status != "deleted",
                    )
                )
                return entry is not None
            except Exception as e:
                logger.error("is_duplicate_entry error: %s", e)
                return False
    except Exception as e:
        logger.error("is_duplicate_entry session error: %s", e)
        return False


async def is_first_ever_add(telegram_id: int | str) -> bool:
    """Return True if this user has never added a wishlist entry across any chat."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                count = await session.scalar(
                    select(func.count(WishlistEntry.id)).where(
                        WishlistEntry.added_by == str(telegram_id),
                        WishlistEntry.status != "deleted",
                    )
                ) or 0
                return int(count) == 0
            except Exception as e:
                logger.error("is_first_ever_add error: %s", e)
                return False
    except Exception as e:
        logger.error("is_first_ever_add session error: %s", e)
        return False


async def save_wishlist_entry(
    chat_id: int | str,
    added_by: int | str,
    google_place_id: str,
    name: str,
    address: str,
    area: str | None,
    lat: float | None,
    lng: float | None,
    any_branch: bool = False,
    notes: str | None = None,
    cuisine_type: str | None = None,
) -> WishlistEntry | None:
    """Persist a wishlist entry. Returns the saved entry or None on failure."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = WishlistEntry(
                    chat_id=str(chat_id),
                    added_by=str(added_by),
                    google_place_id=google_place_id,
                    name=name,
                    address=address,
                    area=area,
                    cuisine_type=cuisine_type,
                    lat=lat,
                    lng=lng,
                    any_branch=any_branch,
                    notes=notes,
                    status="wishlist",
                )
                session.add(entry)
                await session.commit()
                return entry
            except Exception as e:
                await session.rollback()
                logger.error("save_wishlist_entry error: %s", e)
                return None
    except Exception as e:
        logger.error("save_wishlist_entry session error: %s", e)
        return None


async def save_note(entry_id: int, note: str) -> bool:
    """Save or replace the note on a WishlistEntry. Returns True on success."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = await session.scalar(
                    select(WishlistEntry).where(WishlistEntry.id == entry_id)
                )
                if not entry:
                    return False
                entry.notes = note
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error("save_note error: %s", e)
                return False
    except Exception as e:
        logger.error("save_note session error: %s", e)
        return False


async def soft_delete_entry(entry_id: int) -> bool:
    """Set WishlistEntry status to 'deleted'. Returns True on success."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = await session.scalar(
                    select(WishlistEntry).where(WishlistEntry.id == entry_id)
                )
                if not entry:
                    return False
                entry.status = "deleted"
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error("soft_delete_entry error: %s", e)
                return False
    except Exception as e:
        logger.error("soft_delete_entry session error: %s", e)
        return False


async def update_wishlist_status(
    chat_id: int | str,
    google_place_id: str,
    status: str,
) -> None:
    """Update WishlistEntry status if one exists for this (chat, place). No-op if not found."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                entry = await session.scalar(
                    select(WishlistEntry).where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.google_place_id == google_place_id,
                        WishlistEntry.status != "deleted",
                    )
                )
                if entry:
                    entry.status = status
                    await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("update_wishlist_status error: %s", e)
    except Exception as e:
        logger.error("update_wishlist_status session error: %s", e)


# ── Visits ────────────────────────────────────────────────────────────────────

async def save_visit(
    chat_id: int | str,
    google_place_id: str,
    place_name: str,
    logged_by: int | str,
    rating: int | None,
    review: str | None,
    occasion: str | None,
    photos: list[str] | None,
) -> Visit | None:
    """Persist a visit record. Returns the saved Visit or None on failure."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                visit = Visit(
                    chat_id=str(chat_id),
                    google_place_id=google_place_id,
                    place_name=place_name,
                    logged_by=str(logged_by),
                    rating=rating,
                    review=review,
                    occasion=occasion,
                    photos=photos or None,
                )
                session.add(visit)
                await session.commit()
                return visit
            except Exception as e:
                await session.rollback()
                logger.error("save_visit error: %s", e)
                return None
    except Exception as e:
        logger.error("save_visit session error: %s", e)
        return None


async def get_visits_for_chat(chat_id: int | str) -> list[dict]:
    """Fetch all visits for a chat with place names and user display names.

    Returns list of dicts with keys: visit, place_name, user_name.
    Ordered by most recently visited.
    """
    try:
        async with AsyncSessionLocal() as session:
            try:
                visits = list((await session.scalars(
                    select(Visit)
                    .where(Visit.chat_id == str(chat_id))
                    .order_by(Visit.visited_at.desc())
                )).all())

                if not visits:
                    return []

                # Batch-fetch place names from wishlist (fallback to stored place_name)
                place_ids = list({v.google_place_id for v in visits})
                wl_rows = await session.execute(
                    select(WishlistEntry.google_place_id, WishlistEntry.name).where(
                        WishlistEntry.chat_id == str(chat_id),
                        WishlistEntry.google_place_id.in_(place_ids),
                    ).order_by(WishlistEntry.date_added.desc())
                )
                # First name found per place_id wins
                wl_names: dict[str, str] = {}
                for row in wl_rows:
                    if row[0] not in wl_names:
                        wl_names[row[0]] = row[1]

                # Batch-fetch user display names
                user_ids = list({v.logged_by for v in visits})
                user_rows = await session.execute(
                    select(User.telegram_id, User.display_name).where(
                        User.telegram_id.in_(user_ids)
                    )
                )
                user_names = {row[0]: row[1] for row in user_rows}

                result = []
                for v in visits:
                    result.append({
                        "visit": v,
                        "place_name": (
                            wl_names.get(v.google_place_id)
                            or v.place_name
                            or "Unknown Place"
                        ),
                        "user_name": user_names.get(v.logged_by, "Someone"),
                    })
                return result

            except Exception as e:
                logger.error("get_visits_for_chat error: %s", e)
                return []
    except Exception as e:
        logger.error("get_visits_for_chat session error: %s", e)
        return []


# ── Account deactivation ──────────────────────────────────────────────────────

async def reactivate_if_needed(
    telegram_id: int | str,
    chat_id: int | str,
    bot,
) -> bool:
    """Reactivate a deactivated user if needed.

    Returns True if the user was reactivated (is_deactivated was True → set False,
    welcome-back message sent). Returns False in all other cases.
    Never raises.

    Edge cases handled:
    - User does not exist: return False (new user, /start will register them)
    - User is_deleted: return False (permanent deletion, do not touch)
    - User is active: return False (no-op)
    """
    try:
        async with AsyncSessionLocal() as session:
            try:
                user = await session.scalar(
                    select(User).where(User.telegram_id == str(telegram_id))
                )
                if user is None:
                    return False
                if user.is_deleted:
                    return False
                if user.is_deactivated:
                    user.is_deactivated = False
                    await session.commit()
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "👋 Welcome back! Your account has been reactivated "
                            "and your wishlist is still here. Carrying on..."
                        ),
                    )
                    return True
                return False
            except Exception as e:
                await session.rollback()
                logger.error("reactivate_if_needed error: %s", e)
                return False
    except Exception as e:
        logger.error("reactivate_if_needed session error: %s", e)
        return False


# ── Account deletion ──────────────────────────────────────────────────────────

async def anonymise_and_delete_account(telegram_id: int | str) -> bool:
    """PDPA-compliant account deletion.

    - Anonymises the Users record (is_deleted=True, display_name='Deleted User')
    - Soft-deletes all WishlistEntries in the user's private DM chat
    - Clears photos from all their Visits (all contexts)
    - Clears review/rating/occasion from Visits in their private DM chat
    - Group chat entries remain (visible as 'Deleted User') so group lists aren't broken

    Returns True on success, False on failure.
    """
    try:
        async with AsyncSessionLocal() as session:
            try:
                tid = str(telegram_id)

                # 1. Anonymise user record
                user = await session.scalar(select(User).where(User.telegram_id == tid))
                if user:
                    user.is_deleted = True
                    user.display_name = "Deleted User"

                # 2. Soft-delete private DM wishlist entries (chat_id == telegram_id)
                await session.execute(
                    sa_update(WishlistEntry)
                    .where(
                        WishlistEntry.chat_id == tid,
                        WishlistEntry.status != "deleted",
                    )
                    .values(status="deleted")
                )

                # 3. Clear photos from ALL visits by this user (all chats)
                await session.execute(
                    sa_update(Visit)
                    .where(Visit.logged_by == tid)
                    .values(photos=None)
                )

                # 4. Clear PII content from visits in their private DM chat
                await session.execute(
                    sa_update(Visit)
                    .where(Visit.chat_id == tid, Visit.logged_by == tid)
                    .values(review=None, rating=None, occasion=None)
                )

                await session.commit()
                return True

            except Exception as e:
                await session.rollback()
                logger.error("anonymise_and_delete_account error: %s", e)
                return False
    except Exception as e:
        logger.error("anonymise_and_delete_account session error: %s", e)
        return False
