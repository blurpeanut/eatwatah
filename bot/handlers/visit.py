import html
import logging
import warnings

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db.context import is_private_chat
from db.helpers import (
    ensure_user_and_chat,
    get_entry_by_id,
    get_entry_by_place_and_chat,
    get_wishlist_entries,
    log_error,
    save_visit,
    update_wishlist_status,
)
from services.places_service import search_places

logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
VISIT_PICKING          = 1   # choosing from wishlist or tapping a search button
VISIT_SEARCHING        = 2   # Google Places search — typed query, waiting to pick result
VISIT_RATING           = 3
VISIT_REVIEW           = 4
VISIT_OCCASION         = 5
VISIT_PHOTOS           = 6
VISIT_SEARCHING_LOCAL  = 7   # local wishlist search — typed query, waiting to pick result

# ── Helpers ───────────────────────────────────────────────────────────────────

def _visit_data(context) -> dict:
    """Return the mutable visit-in-progress dict, creating it if absent."""
    if "visit" not in context.user_data:
        context.user_data["visit"] = {
            "google_place_id": None,
            "place_name": None,
            "chat_id": None,
            "wishlist_entry_id": None,  # set if place came from wishlist
            "rating": None,
            "review": None,
            "occasion": None,
            "photos": [],
        }
    return context.user_data["visit"]


def _rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐",       callback_data="vr:1"),
        InlineKeyboardButton("⭐⭐",     callback_data="vr:2"),
        InlineKeyboardButton("⭐⭐⭐",   callback_data="vr:3"),
        InlineKeyboardButton("⭐⭐⭐⭐", callback_data="vr:4"),
        InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="vr:5"),
    ]])


def _occasion_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🍽 Casual",      callback_data="vo:Casual"),
        InlineKeyboardButton("🎉 Special",     callback_data="vo:Special"),
        InlineKeyboardButton("💼 Work",        callback_data="vo:Work"),
        InlineKeyboardButton("⚡ Spontaneous", callback_data="vo:Spontaneous"),
    ]])


# ── Entry: /visit command ─────────────────────────────────────────────────────

async def visit_cmd_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/visit called by user %s in chat %s", user.id, chat.id)

    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )

    context.user_data.pop("visit", None)  # clear any stale state
    vd = _visit_data(context)
    vd["chat_id"] = chat.id

    try:
        entries = await get_wishlist_entries(chat.id)
    except Exception as e:
        logger.error("visit_cmd_entry DB error: %s", e)
        await log_error(user.id, chat.id, "/visit", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"🔖 {e.name[:35]}", callback_data=f"vp:{e.id}")]
        for e in entries[:5]  # show 5 most recent; search covers the rest
    ]
    if entries:
        keyboard.append([InlineKeyboardButton("🔍 Search my list", callback_data="vsl")])
        keyboard.append([InlineKeyboardButton("🌐 Not on my list", callback_data="vs")])
        prompt = "Which place did you visit? 👇"
    else:
        keyboard.append([InlineKeyboardButton("🌐 Search for a place", callback_data="vs")])
        prompt = "Your wishlist is empty — search for any place to log a visit 👇"

    await update.message.reply_text(prompt, reply_markup=InlineKeyboardMarkup(keyboard))
    return VISIT_PICKING


# ── Entry: wl_visit button from /viewwishlist ─────────────────────────────────

async def visit_wl_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point from the ✅ button on a wishlist entry."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    entry_id = int(query.data.split(":")[-1])

    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )

    try:
        entry = await get_entry_by_id(entry_id)
    except Exception as e:
        logger.error("visit_wl_entry lookup error: %s", e)
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    if not entry:
        await query.edit_message_text("Couldn't find that entry 🤔 Try /visit instead.")
        return ConversationHandler.END

    context.user_data.pop("visit", None)
    vd = _visit_data(context)
    vd["chat_id"] = chat.id
    vd["google_place_id"] = entry.google_place_id
    vd["place_name"] = entry.name
    vd["wishlist_entry_id"] = entry.id

    await query.edit_message_text(
        f"Logging a visit for <b>{html.escape(entry.name)}</b> 🍽\n\nHow would you rate it?",
        reply_markup=_rating_keyboard(),
        parse_mode="HTML",
    )
    return VISIT_RATING


# ── State: VISIT_PICKING ──────────────────────────────────────────────────────

async def visit_place_picked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped a wishlist entry from the place picker."""
    query = update.callback_query
    await query.answer()

    entry_id = int(query.data.split(":")[-1])

    try:
        entry = await get_entry_by_id(entry_id)
    except Exception as e:
        logger.error("visit_place_picked lookup error: %s", e)
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    if not entry:
        await query.edit_message_text("Couldn't find that entry 🤔 Try /visit instead.")
        return ConversationHandler.END

    vd = _visit_data(context)
    vd["google_place_id"] = entry.google_place_id
    vd["place_name"] = entry.name
    vd["wishlist_entry_id"] = entry.id

    await query.edit_message_text(
        f"<b>{html.escape(entry.name)}</b> — nice! How would you rate it? ⭐",
        reply_markup=_rating_keyboard(),
        parse_mode="HTML",
    )
    return VISIT_RATING


async def visit_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped 'Not on my list' — Google Places search."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Type the place name and I'll look it up on Google Maps 🌐")
    return VISIT_SEARCHING


async def visit_search_local_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped 'Search my list' — local wishlist search."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Type to search your wishlist 🔍")
    return VISIT_SEARCHING_LOCAL


# ── State: VISIT_SEARCHING_LOCAL ──────────────────────────────────────────────

async def visit_search_local_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a search term — filter wishlist locally."""
    chat = update.effective_chat
    query_text = update.message.text.strip()

    vd = _visit_data(context)
    entries = await get_wishlist_entries(vd.get("chat_id") or chat.id)
    matches = [e for e in entries if query_text.lower() in e.name.lower()]

    if not matches:
        await update.message.reply_text(
            "Couldn't find that on your list — try a different name? 🔍"
        )
        return VISIT_SEARCHING_LOCAL

    keyboard = [
        [InlineKeyboardButton(f"🔖 {e.name[:35]}", callback_data=f"vp:{e.id}")]
        for e in matches
    ]
    await update.message.reply_text(
        "Here's what I found — which one? 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return VISIT_SEARCHING_LOCAL


# ── State: VISIT_SEARCHING ────────────────────────────────────────────────────

async def visit_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a search query."""
    user = update.effective_user
    chat = update.effective_chat
    query_text = update.message.text.strip()

    await update.message.reply_text("Searching... please wait 🔍")

    try:
        results = await search_places(query_text)
    except Exception as e:
        logger.error("visit_search_query Places error: %s", e)
        await log_error(user.id, chat.id, "/visit", type(e).__name__, str(e))
        await update.message.reply_text(
            "Map search is having a moment — try again in a bit? 🙏"
        )
        return VISIT_SEARCHING

    if not results:
        await update.message.reply_text(
            "Couldn't find that 😅 Try rephrasing — add the area after the name."
        )
        return VISIT_SEARCHING

    context.user_data["visit_search_results"] = results

    keyboard = [
        [InlineKeyboardButton(f"{i + 1}. {r['name'][:35]}", callback_data=f"vsp:{i}")]
        for i, r in enumerate(results)
    ]
    await update.message.reply_text(
        "Here's what I found — which one? 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return VISIT_SEARCHING


async def visit_search_picked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked from search results."""
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split(":")[-1])
    results = context.user_data.get("visit_search_results", [])

    if not results or idx >= len(results):
        await query.edit_message_text("Search expired 😅 Type the place name again to search.")
        return VISIT_SEARCHING

    place = results[idx]
    vd = _visit_data(context)
    vd["google_place_id"] = place["place_id"]
    vd["place_name"] = place["name"]
    vd["wishlist_entry_id"] = None  # not from wishlist

    await query.edit_message_text(
        f"<b>{html.escape(place['name'])}</b> — nice! How would you rate it? ⭐",
        reply_markup=_rating_keyboard(),
        parse_mode="HTML",
    )
    return VISIT_RATING


# ── State: VISIT_RATING ───────────────────────────────────────────────────────

async def visit_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    rating = int(query.data.split(":")[-1])
    _visit_data(context)["rating"] = rating

    await query.edit_message_text(
        f"{'⭐' * rating} noted!\n\nTell me about it — what did you think? 🍽\n"
        "(Or tap Skip if you'd rather not write a review)",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Skip →", callback_data="vskip_review"),
        ]]),
    )
    return VISIT_REVIEW


# ── State: VISIT_REVIEW ───────────────────────────────────────────────────────

async def visit_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    review_text = update.message.text.strip()
    _visit_data(context)["review"] = review_text
    await update.message.reply_text(
        "Love it 📝 What was the occasion?",
        reply_markup=_occasion_keyboard(),
    )
    return VISIT_OCCASION


async def visit_skip_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _visit_data(context)["review"] = None
    await query.edit_message_text(
        "No worries! What was the occasion?",
        reply_markup=_occasion_keyboard(),
    )
    return VISIT_OCCASION


# ── State: VISIT_OCCASION ─────────────────────────────────────────────────────

async def visit_occasion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    occasion = query.data.split(":")[-1]
    _visit_data(context)["occasion"] = occasion

    await query.edit_message_text(
        "Any photos to add? Send them now, or tap Skip 📸",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Skip →", callback_data="vdone"),
        ]]),
    )
    return VISIT_PHOTOS


# ── State: VISIT_PHOTOS ───────────────────────────────────────────────────────

async def visit_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent a photo — accumulate file_ids."""
    vd = _visit_data(context)
    # Telegram sends the largest available photo as the last item
    file_id = update.message.photo[-1].file_id
    vd["photos"].append(file_id)

    await update.message.reply_text(
        f"Got it! 📸 ({len(vd['photos'])} photo{'s' if len(vd['photos']) != 1 else ''} saved)\n"
        "Send more or tap Done ✅",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Done ✅", callback_data="vdone"),
        ]]),
    )
    return VISIT_PHOTOS


async def visit_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped Done / Skip on photos — save everything."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    vd = _visit_data(context)
    chat_id = vd.get("chat_id") or update.effective_chat.id

    try:
        visit = await save_visit(
            chat_id=chat_id,
            google_place_id=vd["google_place_id"],
            place_name=vd["place_name"],
            logged_by=user.id,
            rating=vd.get("rating"),
            review=vd.get("review"),
            occasion=vd.get("occasion"),
            photos=vd["photos"] or None,
        )
    except Exception as e:
        logger.error("visit_done save_visit error: %s", e)
        visit = None

    if not visit:
        await log_error(user.id, chat_id, "/visit", "SaveFailed", f"place={vd.get('place_name')}")
        await query.edit_message_text(
            "Something went wrong saving your visit — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    # Update wishlist status to 'visited' if place was on the list
    try:
        await update_wishlist_status(chat_id, vd["google_place_id"], "visited")
    except Exception as e:
        logger.warning("visit_done status update failed (non-critical): %s", e)

    context.user_data.pop("visit", None)
    context.user_data.pop("visit_search_results", None)

    await query.edit_message_text(
        "Shiok! Logged 🎉 The more you review, the better I get at finding your next fave spot 🍜"
    )
    return ConversationHandler.END


# ── Fallback / cancel ─────────────────────────────────────────────────────────

async def visit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("visit", None)
    await update.message.reply_text(
        "No worries! Use /visit whenever you're ready to log a meal 😊"
    )
    return ConversationHandler.END


async def visit_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered when conversation_timeout fires (requires job_queue)."""
    chat_id = context.user_data.get("visit", {}).get("chat_id")
    context.user_data.pop("visit", None)
    if chat_id:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Looks like we got cut off. Start again with /visit whenever you're ready 😊",
            )
        except Exception:
            pass
    return ConversationHandler.END


# ── Entry: post_add:visit: button from /add ───────────────────────────────────

async def visit_post_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point from the ✅ Mark Visited button on the /add follow-up."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat

    # callback_data format: post_add:visit:{google_place_id}
    google_place_id = query.data[len("post_add:visit:"):]

    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )

    try:
        entry = await get_entry_by_place_and_chat(chat.id, google_place_id)
    except Exception as e:
        logger.error("visit_post_add_entry lookup error: %s", e)
        await query.answer("Couldn't find that entry — try /visit instead", show_alert=True)
        return ConversationHandler.END

    if not entry:
        await query.answer("Couldn't find that entry — try /visit instead", show_alert=True)
        return ConversationHandler.END

    context.user_data.pop("visit", None)
    vd = _visit_data(context)
    vd["chat_id"] = chat.id
    vd["google_place_id"] = entry.google_place_id
    vd["place_name"] = entry.name
    vd["wishlist_entry_id"] = entry.id

    await query.message.reply_html(
        f"Logging a visit for <b>{html.escape(entry.name)}</b> 🍽\n\nHow would you rate it?",
        reply_markup=_rating_keyboard(),
    )
    return VISIT_RATING


# ── ConversationHandler instance ─────────────────────────────────────────────

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")
    visit_conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler("visit", visit_cmd_entry),
            CallbackQueryHandler(visit_wl_entry,        pattern=r"^wl_visit:"),
            CallbackQueryHandler(visit_post_add_entry,  pattern=r"^post_add:visit:"),
        ],
        states={
            VISIT_PICKING: [
                CallbackQueryHandler(visit_place_picked,        pattern=r"^vp:"),
                CallbackQueryHandler(visit_search_local_prompt, pattern=r"^vsl$"),
                CallbackQueryHandler(visit_search_prompt,       pattern=r"^vs$"),
            ],
            VISIT_SEARCHING_LOCAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, visit_search_local_query),
                CallbackQueryHandler(visit_place_picked, pattern=r"^vp:"),
            ],
            VISIT_SEARCHING: [
                CallbackQueryHandler(visit_search_picked, pattern=r"^vsp:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, visit_search_query),
            ],
            VISIT_RATING: [
                CallbackQueryHandler(visit_rating, pattern=r"^vr:"),
            ],
            VISIT_REVIEW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, visit_review),
                CallbackQueryHandler(visit_skip_review, pattern=r"^vskip_review$"),
            ],
            VISIT_OCCASION: [
                CallbackQueryHandler(visit_occasion, pattern=r"^vo:"),
            ],
            VISIT_PHOTOS: [
                MessageHandler(filters.PHOTO, visit_photo),
                CallbackQueryHandler(visit_done, pattern=r"^vdone$"),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, visit_timeout),
                CallbackQueryHandler(visit_timeout),
            ],
        },
        fallbacks=[CommandHandler("cancel", visit_cancel)],
        allow_reentry=True,
        conversation_timeout=600,
    )
