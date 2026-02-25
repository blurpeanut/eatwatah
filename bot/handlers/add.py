import html
import logging
import re
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
    is_duplicate_entry,
    is_first_ever_add,
    log_error,
    reactivate_if_needed,
    save_note,
    save_wishlist_entry,
)
from services.places_service import classify_cuisine, reverse_geocode_area, search_places

logger = logging.getLogger(__name__)

# Conversation states — /add
CHOOSING_PLACE = 1
MANUAL_INPUT = 2

# Conversation states — add note
NOTE_WAITING = 1


# ── Entry point ──────────────────────────────────────────────────────────────

async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /add command."""
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/add called by user %s in chat %s", user.id, chat.id)

    # Auto-register safety net
    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )
    await reactivate_if_needed(user.id, chat.id, context.bot)

    # Step 0 — validate input
    query_text = " ".join(context.args).strip() if context.args else ""
    if not query_text:
        await update.message.reply_text(
            "Try sending it like this: /add Hai Di Lao Orchard 😄"
        )
        return ConversationHandler.END

    # Store chat_id so callbacks can use the correct chat context
    context.user_data["pending_add_chat_id"] = chat.id

    await update.message.reply_text("Searching for your place... please wait 🔍")

    # Step 1 — call Google Places
    try:
        results = await search_places(query_text)
    except Exception as e:
        logger.error("/add Places API error: %s", e)
        await log_error(user.id, chat.id, "/add", type(e).__name__, str(e))
        await update.message.reply_text(
            "Map search is having a moment — try again in a bit? 🙏"
        )
        return ConversationHandler.END

    if not results:
        await update.message.reply_text(
            "Couldn't find that one. Try rephrasing — add the area after the name.\n\n"
            "Or add it manually 👇",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✏️ Add manually", callback_data="place_select:manual"),
            ]]),
        )
        context.user_data["search_results"] = []
        return CHOOSING_PLACE

    context.user_data["search_results"] = results

    # Build result text (HTML) + selection buttons
    lines = []
    for i, p in enumerate(results):
        rating_str = f" · ⭐ {p['rating']}" if p.get("rating") else ""
        lines.append(
            f"{i + 1}. <b>{html.escape(p['name'])}</b>{rating_str}\n"
            f"   {html.escape(p['address'])}\n"
            f"   <a href='{p['maps_url']}'>📍 View on Maps</a>"
        )

    result_text = "\n\n".join(lines)

    keyboard = [
        [InlineKeyboardButton(
            f"{i + 1}. {p['name']}"[:40],
            callback_data=f"place_select:{i}",
        )]
        for i, p in enumerate(results)
    ]
    keyboard.append([InlineKeyboardButton("🌐 Any branch",                callback_data="place_select:any_branch")])
    keyboard.append([InlineKeyboardButton("✏️ Not here — type manually", callback_data="place_select:manual")])

    await update.message.reply_html(
        f"Here's what I found 👇\n\n{result_text}\n\nWhich one is it?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )
    return CHOOSING_PLACE


# ── State: CHOOSING_PLACE ────────────────────────────────────────────────────

async def place_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle place selection from the search results keyboard."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    chat_id = context.user_data.get("pending_add_chat_id", chat.id)
    results = context.user_data.get("search_results")

    selection = query.data.replace("place_select:", "")

    # ── Manual entry branch ──
    if selection == "manual":
        await query.edit_message_text(
            "No worries! Just type the place name and I'll save it 👌"
        )
        return MANUAL_INPUT

    # Guard: stale results (e.g. after bot restart)
    if not results and selection != "manual":
        await query.edit_message_text(
            "This search has expired 😅 Use /add again to search!"
        )
        return ConversationHandler.END

    # ── Resolve which place was selected ──
    any_branch = selection == "any_branch"
    if any_branch:
        place = results[0]
    else:
        try:
            place = results[int(selection)]
        except (ValueError, IndexError):
            await query.edit_message_text(
                "Something went a bit sideways 😅 Try /add again?"
            )
            return ConversationHandler.END

    # Duplicate check
    try:
        duplicate = await is_duplicate_entry(chat_id, place["place_id"])
    except Exception as e:
        logger.error("place_chosen duplicate check error: %s", e)
        await log_error(user.id, chat_id, "/add", type(e).__name__, str(e))
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    if duplicate:
        await query.edit_message_text(
            f"⚠️ {html.escape(place['name'])} already exists in your wishlist."
        )
        return ConversationHandler.END

    # Derive area via reverse geocoding; classify cuisine from Places types
    lat, lng = place.get("lat"), place.get("lng")
    if lat is not None and lng is not None:
        area = await reverse_geocode_area(lat, lng)
    else:
        area = place.get("area")
    cuisine_type = classify_cuisine(place.get("types", []))

    # Check first-ever add before saving
    first_add = await is_first_ever_add(user.id)

    entry = await save_wishlist_entry(
        chat_id=chat_id,
        added_by=user.id,
        google_place_id=place["place_id"],
        name=place["name"],
        address=place["address"],
        area=area,
        lat=lat,
        lng=lng,
        any_branch=any_branch,
        cuisine_type=cuisine_type,
    )

    if not entry:
        await log_error(user.id, chat_id, "/add", "SaveFailed", f"Failed to save {place['name']}")
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    name_label = html.escape(
        f"{place['name']} (any branch)" if any_branch else place["name"]
    )
    follow_ups = _follow_up_keyboard(entry.id, place["place_id"])

    if first_add:
        await query.edit_message_text(
            f"Added <b>{name_label}</b> to your wishlist! 🔖\n\n"
            "First one in the bag! 🎉 The more you log, the smarter /ask gets 🧠",
            parse_mode="HTML",
            reply_markup=follow_ups,
        )
    else:
        await query.edit_message_text(
            f"Nice choice! Added <b>{name_label}</b> to your wishlist 🔖",
            parse_mode="HTML",
            reply_markup=follow_ups,
        )

    return ConversationHandler.END


# ── State: MANUAL_INPUT ──────────────────────────────────────────────────────

async def manual_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle free-text manual place name entry."""
    user = update.effective_user
    chat = update.effective_chat
    chat_id = context.user_data.get("pending_add_chat_id", chat.id)

    place_name = update.message.text.strip()
    if not place_name:
        await update.message.reply_text(
            "Hmm, didn't catch that. Type the place name and I'll save it 👌"
        )
        return MANUAL_INPUT

    # Derive a stable place_id from the name
    slug = re.sub(r"[^a-z0-9]+", "_", place_name.lower()).strip("_")
    google_place_id = f"manual:{slug}"

    # Duplicate check
    try:
        duplicate = await is_duplicate_entry(chat_id, google_place_id)
    except Exception as e:
        logger.error("manual_input duplicate check error: %s", e)
        await log_error(user.id, chat_id, "/add", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    if duplicate:
        await update.message.reply_text(
            f"⚠️ {html.escape(place_name)} already exists in your wishlist."
        )
        return ConversationHandler.END

    first_add = await is_first_ever_add(user.id)

    entry = await save_wishlist_entry(
        chat_id=chat_id,
        added_by=user.id,
        google_place_id=google_place_id,
        name=place_name,
        address="Manually added",
        area=None,
        lat=None,
        lng=None,
    )

    if not entry:
        await log_error(user.id, chat_id, "/add", "SaveFailed", f"Manual save failed: {place_name}")
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return ConversationHandler.END

    follow_ups = _follow_up_keyboard(entry.id, google_place_id)
    escaped_name = html.escape(place_name)

    if first_add:
        await update.message.reply_html(
            f"Added <b>{escaped_name}</b> to your wishlist! 🔖\n\n"
            "First one in the bag! 🎉 The more you log, the smarter /ask gets 🧠",
            reply_markup=follow_ups,
        )
    else:
        await update.message.reply_html(
            f"Nice choice! Added <b>{escaped_name}</b> to your wishlist 🔖",
            reply_markup=follow_ups,
        )

    return ConversationHandler.END


# ── Post-add follow-up button handler ────────────────────────────────────────

async def post_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for Delete follow-up button. Note and Visit are handled by their own conversations."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "delete":
        entry_id = parts[2] if len(parts) > 2 else None
        if not entry_id:
            await query.message.reply_text("Something went wrong — try /delete instead 🙏")
            return
        try:
            entry = await get_entry_by_id(int(entry_id))
        except Exception:
            entry = None
        if not entry or entry.status == "deleted":
            await query.message.reply_text("This place is no longer on your wishlist.")
            return
        keyboard = [[
            InlineKeyboardButton("Yes, remove it 🗑", callback_data=f"del_confirm:{entry_id}"),
            InlineKeyboardButton("No, keep it 😊",   callback_data="del_cancel"),
        ]]
        await query.message.reply_html(
            f"Sure anot? This will remove <b>{html.escape(entry.name)}</b> from your list 🗑",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ── Note conversation ─────────────────────────────────────────────────────────

async def note_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped 📝 Add Note — prompt for note text."""
    query = update.callback_query
    await query.answer()

    # callback_data: post_add:note:{entry_id}
    entry_id = int(query.data.split(":")[-1])
    context.user_data["pending_note_entry_id"] = entry_id

    try:
        entry = await get_entry_by_id(entry_id)
    except Exception:
        entry = None

    if entry and entry.notes:
        prompt = (
            f"Current note: <i>{html.escape(entry.notes)}</i>\n\n"
            "Send a new note to replace it, or /cancel to keep it 📝"
        )
    else:
        prompt = "What would you like to note about this place? 📝\n(Or /cancel to skip)"

    await query.message.reply_html(prompt)
    return NOTE_WAITING


async def note_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed their note — save it."""
    user = update.effective_user
    chat = update.effective_chat
    note_text = update.message.text.strip()
    entry_id = context.user_data.pop("pending_note_entry_id", None)

    if not entry_id:
        return ConversationHandler.END

    success = await save_note(entry_id, note_text)

    if success:
        await update.message.reply_text("Note saved! 📝")
    else:
        await log_error(user.id, chat.id, "/add", "SaveNoteFailed", f"entry_id={entry_id}")
        await update.message.reply_text(
            "Something went wrong saving your note — not your fault! Try again 🙏"
        )

    return ConversationHandler.END


async def note_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("pending_note_entry_id", None)
    await update.message.reply_text("No worries, skipped the note 😊")
    return ConversationHandler.END


async def note_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("pending_note_entry_id", None)
    return ConversationHandler.END


# ── Fallback / timeout ────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "No worries, cancelled! Use /add <place name> whenever you're ready 👍"
    )
    return ConversationHandler.END


async def add_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered when the /add conversation idles for 10 minutes."""
    context.user_data.pop("pending_add_chat_id", None)
    context.user_data.pop("search_results", None)
    try:
        chat_id = update.effective_chat.id if update and update.effective_chat else None
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Looks like we got cut off 😅 Use /add <place name> again whenever you're ready!",
            )
    except Exception:
        pass
    return ConversationHandler.END


# ── Helpers ───────────────────────────────────────────────────────────────────

def _follow_up_keyboard(entry_id: int, place_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Add Note",      callback_data=f"post_add:note:{entry_id}"),
        InlineKeyboardButton("✅ Mark Visited",  callback_data=f"post_add:visit:{place_id}"),
        InlineKeyboardButton("🗑 Delete",        callback_data=f"post_add:delete:{entry_id}"),
    ]])


# ── Note ConversationHandler instance ────────────────────────────────────────

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")
    note_conversation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(note_entry, pattern=r"^post_add:note:")],
        states={
            NOTE_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, note_received),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, note_timeout),
                CallbackQueryHandler(note_timeout),
            ],
        },
        fallbacks=[CommandHandler("cancel", note_cancel)],
        allow_reentry=True,
        conversation_timeout=300,
    )


# ── Add ConversationHandler instance ─────────────────────────────────────────
# per_message=False is intentional: one conversation per (user, chat) is correct
# for /add. PTBUserWarning about this is suppressed below.

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")
    add_conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_entry)],
        states={
            CHOOSING_PLACE: [
                CallbackQueryHandler(place_chosen, pattern=r"^place_select:"),
            ],
            MANUAL_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_input_received),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, add_timeout),
                CallbackQueryHandler(add_timeout),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
        conversation_timeout=600,
    )
