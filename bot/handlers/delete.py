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
    get_wishlist_entries,
    log_error,
    soft_delete_entry,
)

DELETE_SEARCHING = 1

logger = logging.getLogger(__name__)


# ── /delete command ───────────────────────────────────────────────────────────

async def delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show wishlist items as selectable buttons, with optional fuzzy search."""
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/delete called by user %s in chat %s", user.id, chat.id)

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
            await update.message.reply_text(
                "Nothing on your wishlist to remove! Use /add to get started 😊"
            )
            return

        query_text = " ".join(context.args).strip() if context.args else ""

        if query_text:
            matches = [e for e in entries if query_text.lower() in e.name.lower()][:3]
            if not matches:
                await update.message.reply_text(
                    "Couldn't find anything matching that — try /delete without arguments to see your full list."
                )
                return
            keyboard = [
                [InlineKeyboardButton(f"🗑 {e.name[:35]}", callback_data=f"del_pick:{e.id}")]
                for e in matches
            ]
            await update.message.reply_text(
                "Which one do you mean? 👇",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            keyboard = [
                [InlineKeyboardButton(f"🗑 {e.name[:35]}", callback_data=f"del_pick:{e.id}")]
                for e in entries[:5]
            ]
            keyboard.append([InlineKeyboardButton("🔍 Search my list", callback_data="dsl")])
            await update.message.reply_text(
                "Which place do you want to remove? 👇",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    except Exception as e:
        logger.error("/delete error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/delete", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


# ── Search conversation ───────────────────────────────────────────────────────

async def delete_search_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped 'Search my list' — prompt for search text."""
    query = update.callback_query
    await query.answer()
    context.user_data["delete_search_chat_id"] = update.effective_chat.id
    await query.edit_message_text("Type to search your wishlist 🔍")
    return DELETE_SEARCHING


async def delete_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a search term — filter wishlist locally and show matches."""
    chat_id = context.user_data.get("delete_search_chat_id") or update.effective_chat.id
    query_text = update.message.text.strip()

    entries = await get_wishlist_entries(chat_id)
    matches = [e for e in entries if query_text.lower() in e.name.lower()]

    if not matches:
        await update.message.reply_text(
            "Couldn't find that on your list — try a different name? 🔍"
        )
        return DELETE_SEARCHING

    keyboard = [
        [InlineKeyboardButton(f"🗑 {e.name[:35]}", callback_data=f"del_pick:{e.id}")]
        for e in matches
    ]
    await update.message.reply_text(
        "Which one? 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


async def delete_search_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("delete_search_chat_id", None)
    await update.message.reply_text("No worries 😊")
    return ConversationHandler.END


async def delete_search_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("delete_search_chat_id", None)
    return ConversationHandler.END


with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")
    delete_search_conversation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_search_entry, pattern=r"^dsl$")],
        states={
            DELETE_SEARCHING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_search_query),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, delete_search_timeout),
                CallbackQueryHandler(delete_search_timeout),
            ],
        },
        fallbacks=[CommandHandler("cancel", delete_search_cancel)],
        allow_reentry=True,
        conversation_timeout=120,
    )


# ── Show confirmation ─────────────────────────────────────────────────────────

async def delete_show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle del_pick:<id> and wl_delete:<id> — show the confirmation prompt."""
    query = update.callback_query
    await query.answer()

    # Works for both del_pick: and wl_delete: prefixes
    entry_id = int(query.data.split(":")[-1])

    try:
        entry = await get_entry_by_id(entry_id)
    except Exception as e:
        logger.error("delete_show_confirm lookup error: %s", e)
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return

    if not entry or entry.status == "deleted":
        await query.edit_message_text("This entry doesn't seem to exist anymore 🤔")
        return

    keyboard = [[
        InlineKeyboardButton("Yes, remove it 🗑", callback_data=f"del_confirm:{entry_id}"),
        InlineKeyboardButton("No, keep it 😊",   callback_data="del_cancel"),
    ]]
    await query.edit_message_text(
        f"Sure anot? This will remove <b>{html.escape(entry.name)}</b> from your list 🗑",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# ── Confirm deletion ──────────────────────────────────────────────────────────

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Soft-delete the entry and confirm."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    entry_id = int(query.data.split(":")[-1])

    try:
        entry = await get_entry_by_id(entry_id)
        if not entry:
            await query.edit_message_text("Couldn't find that entry 🤔 It may have already been removed.")
            return

        name = entry.name
        success = await soft_delete_entry(entry_id)

        if success:
            await query.edit_message_text(f"Removed <b>{html.escape(name)}</b> from your list 👍", parse_mode="HTML")
        else:
            await log_error(user.id, chat.id, "/delete", "SoftDeleteFailed", f"entry_id={entry_id}")
            await query.edit_message_text(
                "Something went wrong on our end — not your fault! Try again in a bit 🙏"
            )

    except Exception as e:
        logger.error("delete_confirm error: %s", e)
        await log_error(user.id, chat.id, "/delete", type(e).__name__, str(e))
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


# ── Cancel deletion ───────────────────────────────────────────────────────────

async def delete_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("No worries, kept it on your list 😊")
