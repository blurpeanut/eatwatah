import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import (
    ensure_user_and_chat,
    get_chat_stats,
    is_duplicate_entry,
    is_first_ever_add,
    log_error,
    save_wishlist_entry,
)
from bot.handlers.view_wishlist import show_wishlist
from services.places_service import search_places

logger = logging.getLogger(__name__)

# Curated starter suggestions — slug → display name
CURATED_PLACES: dict[str, str] = {
    "lau_pa_sat":         "Lau Pa Sat",
    "newton_fc":          "Newton Food Centre",
    "old_chang_kee":      "Old Chang Kee",
    "din_tai_fung":       "Din Tai Fung",
    "ps_cafe":            "PS Cafe",
    "jewel_changi":       "Jewel Changi",
    "tiong_bahru_bakery": "Tiong Bahru Bakery",
    "burnt_ends":         "Burnt Ends",
}


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/start called by user %s in chat %s", user.id, chat.id)

    try:
        is_private = is_private_chat(chat.id, user.id)
        is_new = await ensure_user_and_chat(
            telegram_id=user.id,
            display_name=user.full_name or user.username or "Friend",
            chat_id=chat.id,
            chat_type=chat.type,
            chat_name=None if is_private else (chat.title or "Group"),
        )

        if is_new:
            await _send_new_user_welcome(update, user)
        else:
            await _send_returning_user_welcome(update, user, chat)

    except Exception as e:
        logger.error("/start unhandled error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/start", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


async def _send_new_user_welcome(update: Update, user) -> None:
    name = html.escape(user.first_name or "friend")

    keyboard = [
        [
            InlineKeyboardButton(CURATED_PLACES["lau_pa_sat"],         callback_data="curated_add:lau_pa_sat"),
            InlineKeyboardButton(CURATED_PLACES["newton_fc"],           callback_data="curated_add:newton_fc"),
        ],
        [
            InlineKeyboardButton(CURATED_PLACES["old_chang_kee"],       callback_data="curated_add:old_chang_kee"),
            InlineKeyboardButton(CURATED_PLACES["din_tai_fung"],        callback_data="curated_add:din_tai_fung"),
        ],
        [
            InlineKeyboardButton(CURATED_PLACES["ps_cafe"],             callback_data="curated_add:ps_cafe"),
            InlineKeyboardButton(CURATED_PLACES["jewel_changi"],        callback_data="curated_add:jewel_changi"),
        ],
        [
            InlineKeyboardButton(CURATED_PLACES["tiong_bahru_bakery"],  callback_data="curated_add:tiong_bahru_bakery"),
            InlineKeyboardButton(CURATED_PLACES["burnt_ends"],          callback_data="curated_add:burnt_ends"),
        ],
    ]

    await update.message.reply_html(
        f"{name}! 👋 I'm eatwatah — your personal food kaki.\n\n"
        "Tell me spots you want to try, log your visits with ratings, and when you "
        "can't decide where to eat — just /ask me and I'll figure it out 😎\n\n"
        "Hit the menu button or use /help to see everything I can do.\n\n"
        "For now, here are some spots others are saving right now 👇 Tap any to add to your list:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await update.message.reply_text(
        "Or just tell me a place you've been meaning to try 👀 Use /add <place name>"
    )


async def _send_returning_user_welcome(update: Update, user, chat) -> None:
    name = html.escape(user.first_name or "friend")
    is_private = is_private_chat(chat.id, user.id)
    total_saved, visited_count = await get_chat_stats(chat.id)

    list_label = "your list" if is_private else f"{html.escape(chat.title or 'this group')}'s list"

    keyboard = [[
        InlineKeyboardButton("➕ Add Place",      callback_data="quick:add"),
        InlineKeyboardButton("🤖 Get Recs",       callback_data="quick:recs"),
        InlineKeyboardButton("📋 View Wishlist",  callback_data="quick:wishlist"),
    ]]

    await update.message.reply_html(
        f"{name}, welcome back! 👋\n\n"
        f"📋 {total_saved} saved on {list_label} | ✅ {visited_count} visited\n\n"
        "What's the plan today? 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def curated_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle taps on the curated starter suggestion buttons from /start."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    is_private = is_private_chat(chat.id, user.id)

    slug = query.data.replace("curated_add:", "")
    place_name = CURATED_PLACES.get(slug)
    if not place_name:
        await query.edit_message_text("Hmm, something went sideways. Try /add instead 🙏")
        return

    # Auto-register safety net
    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private else (chat.title or "Group"),
    )

    # Search Google Places
    try:
        results = await search_places(place_name)
    except Exception as e:
        logger.error("curated_add Places API error for %s: %s", place_name, e)
        await log_error(user.id, chat.id, "curated_add", type(e).__name__, str(e))
        await query.edit_message_text(
            f"Map search is having a moment 🙏 Try /add {place_name} in a bit!"
        )
        return

    if not results:
        await query.edit_message_text(
            f"Couldn't find {html.escape(place_name)} on Google Maps 😅\n"
            f"Try /add {place_name} to search manually!"
        )
        return

    place = results[0]

    # Duplicate check
    if await is_duplicate_entry(chat.id, place["place_id"]):
        await query.edit_message_text(
            f"⚠️ {html.escape(place['name'])} is already on your list!"
        )
        return

    # Check first-ever add before saving
    first_add = await is_first_ever_add(user.id)

    entry = await save_wishlist_entry(
        chat_id=chat.id,
        added_by=user.id,
        google_place_id=place["place_id"],
        name=place["name"],
        address=place["address"],
        area=place["area"],
        lat=place["lat"],
        lng=place["lng"],
    )

    if not entry:
        await log_error(user.id, chat.id, "curated_add", "SaveFailed", f"Failed to save {place_name}")
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return

    escaped_name = html.escape(place["name"])

    if first_add:
        await query.edit_message_text(
            f"Added <b>{escaped_name}</b> to your wishlist! 🔖\n\n"
            "First one in the bag! 🎉 The more you add and review, the smarter my recs get 👀",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            f"Nice choice! Added <b>{escaped_name}</b> to your wishlist 🔖\n\n"
            "Keep adding and I'll get better at knowing your vibe.",
            parse_mode="HTML",
        )


async def quick_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the quick action buttons on the returning user welcome."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    action = query.data.replace("quick:", "")

    if action == "add":
        await query.message.reply_text(
            "To add a spot, just use:\n/add <place name>\n\nE.g. /add PS Cafe Dempsey 🔍"
        )
    elif action == "recs":
        await query.message.reply_text(
            "Use /ask to get AI-powered recommendations 🤖\n\nTry: /ask something cosy in Bugis"
        )
    elif action == "wishlist":
        await show_wishlist(query.message, chat, user)
    elif action == "visit":
        await query.message.reply_text(
            "Use /visit to log a meal and rate it ⭐"
        )
