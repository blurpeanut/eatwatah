import html
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Chat, Update, WebAppInfo
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import (
    ensure_user_and_chat,
    get_user_display_names,
    get_wishlist_entries,
    log_error,
)

logger = logging.getLogger(__name__)

# Singapore region grouping
AREA_TO_REGION: dict[str, str] = {
    # Central
    "Orchard": "Central", "Newton": "Central", "Novena": "Central",
    "Toa Payoh": "Central", "Bishan": "Central", "Braddell": "Central",
    "Chinatown": "Central", "Tanjong Pagar": "Central",
    "Clarke Quay": "Central", "Raffles Place": "Central",
    "Marina Bay": "Central", "Bugis": "Central", "Rochor": "Central",
    "Little India": "Central", "Dhoby Ghaut": "Central",
    "River Valley": "Central", "Robertson Quay": "Central",
    "Boat Quay": "Central", "Outram": "Central", "Tiong Bahru": "Central",
    "Queenstown": "Central", "Redhill": "Central", "Lavender": "Central",
    "Harbourfront": "Central", "Sentosa": "Central",
    "Holland Village": "Central", "Dempsey": "Central", "Buona Vista": "Central",
    # East
    "East Coast": "East", "Bedok": "East", "Tampines": "East",
    "Pasir Ris": "East", "Changi": "East", "Tanah Merah": "East",
    "Paya Lebar": "East", "Marine Parade": "East", "Siglap": "East",
    "Katong": "East", "Tanjong Katong": "East", "Joo Chiat": "East",
    "Geylang": "East", "Kallang": "East",
    # North
    "Woodlands": "North", "Sembawang": "North",
    "Yishun": "North", "Ang Mo Kio": "North",
    # North-East
    "Hougang": "North-East", "Sengkang": "North-East",
    "Punggol": "North-East", "Serangoon": "North-East",
    # West
    "Jurong": "West", "Clementi": "West",
    "Bukit Timah": "West", "Choa Chu Kang": "West",
}
REGION_ORDER = ["Central", "East", "North", "North-East", "West", "Other"]


def _get_region(area: str | None) -> str:
    if not area:
        return "Other"
    return AREA_TO_REGION.get(area, "Other")


def _fmt_date(dt) -> str:
    return f"{dt.day} {dt.strftime('%b')}"


async def show_wishlist(message: Message, chat, user) -> None:
    """Display the wishlist. Called from view_wishlist_handler and start.py quick action."""
    try:
        await ensure_user_and_chat(
            telegram_id=user.id,
            display_name=user.full_name or user.username or "Friend",
            chat_id=chat.id,
            chat_type=chat.type,
            chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
        )

        entries = await get_wishlist_entries(chat.id)

        if not entries:
            await message.reply_text(
                "Your wishlist is empty! Use /add to start building your list 👀"
            )
            return

        webapp_base = os.getenv("WEBAPP_BASE_URL", "").strip().rstrip("/")

        # ── WebApp mode: just open the map ─────────────────────────────────
        if webapp_base:
            count = len(entries)
            webapp_url = f"{webapp_base}/webapp/index.html"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗺 Open map", web_app=WebAppInfo(url=webapp_url))
            ]])
            await message.reply_text(
                f"You've got {count} place{'s' if count != 1 else ''} saved 👇",
                reply_markup=keyboard,
            )
            return

        # ── Fallback: text list (no WebApp configured) ─────────────────────
        added_by_ids = list({e.added_by for e in entries})
        display_names = await get_user_display_names(added_by_ids)

        grouped: dict[str, list] = {r: [] for r in REGION_ORDER}
        for entry in entries:
            grouped[_get_region(entry.area)].append(entry)

        lines = [f"📋 <b>Your Wishlist</b> — {len(entries)} place{'s' if len(entries) != 1 else ''}\n"]

        for region in REGION_ORDER:
            region_entries = grouped[region]
            if not region_entries:
                continue
            lines.append(f"\n📍 <b>{region}</b>")
            for entry in region_entries:
                adder = display_names.get(entry.added_by, "Someone")
                adder_label = "You" if entry.added_by == str(user.id) else html.escape(adder)
                note_line = f"\n   📝 {html.escape(entry.notes)}" if entry.notes else ""
                lines.append(
                    f"\n🔖 <b>{html.escape(entry.name)}</b>\n"
                    f"   {html.escape(entry.address)}\n"
                    f"   Added by {adder_label} · {_fmt_date(entry.date_added)}"
                    + note_line
                )

        await message.reply_html("\n".join(lines))

    except Exception as e:
        logger.error("show_wishlist error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/viewwishlist", type(e).__name__, str(e))
        await message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


async def view_wishlist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/viewwishlist called by user %s in chat %s", user.id, chat.id)
    await show_wishlist(update.message, chat, user)
