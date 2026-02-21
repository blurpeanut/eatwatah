import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import anonymise_and_delete_account, ensure_user_and_chat, log_error

logger = logging.getLogger(__name__)


async def delete_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/deleteaccount called by user %s in chat %s", user.id, chat.id)

    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )

    keyboard = [[
        InlineKeyboardButton("Yes, delete my data 🗑", callback_data="da_confirm"),
        InlineKeyboardButton("No, keep my account 😊", callback_data="da_cancel"),
    ]]
    await update.message.reply_text(
        "⚠️ This will permanently delete all your personal data from eatwatah. "
        "Your contributions to group wishlists will be anonymised so group lists aren't broken. "
        "Sure anot? This cannot be undone.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat

    try:
        success = await anonymise_and_delete_account(user.id)
    except Exception as e:
        logger.error("delete_account_confirm error for user %s: %s", user.id, e)
        success = False

    if success:
        await query.edit_message_text(
            "All done. Your data has been removed from eatwatah. Take care ah 👋"
        )
    else:
        await log_error(user.id, chat.id, "/deleteaccount", "DeletionFailed", f"user={user.id}")
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


async def delete_account_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("No worries, your account is safe 😊")
