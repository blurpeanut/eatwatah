import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import ensure_user_and_chat, log_error, reactivate_if_needed

logger = logging.getLogger(__name__)


# ── Pure helpers ───────────────────────────────────────────────────────────────

def _main_help_text(in_group: bool, group_name: str | None) -> str:
    text = (
        "Here's everything I can do 👇\n\n"
        "📌 /add — Save a food spot to your wishlist\n"
        "📋 /viewwishlist — Browse saved spots by area\n"
        "✅ /visit — Log a meal with rating + review\n"
        "📖 /viewvisited — See your full visit history\n"
        "🤖 /ask — Get AI-powered recommendations\n"
        "🗑 /delete — Remove a spot from your list\n\n"
        "Tap to learn more 👇"
    )
    if in_group and group_name:
        text += f"\n\n👥 You're in <b>{html.escape(group_name)}</b> — commands here affect the shared group list."
    return text


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📌 How to /add",      callback_data="help:add"),
            InlineKeyboardButton("🤖 How /ask works",   callback_data="help:ask"),
        ],
        [
            InlineKeyboardButton("✅ Logging visits",   callback_data="help:visit"),
            InlineKeyboardButton("👥 Using in a group", callback_data="help:group"),
        ],
    ])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← Back", callback_data="help:back")],
    ])


# ── /help command ──────────────────────────────────────────────────────────────

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/help called by user %s in chat %s", user.id, chat.id)

    try:
        is_private = is_private_chat(chat.id, user.id)
        await ensure_user_and_chat(
            telegram_id=user.id,
            display_name=user.full_name or user.username or "Friend",
            chat_id=chat.id,
            chat_type=chat.type,
            chat_name=None if is_private else (chat.title or "Group"),
        )
        await reactivate_if_needed(user.id, chat.id, context.bot)

        text = _main_help_text(
            in_group=not is_private,
            group_name=chat.title if not is_private else None,
        )
        await update.message.reply_html(text, reply_markup=_main_keyboard())

    except Exception as e:
        logger.error("/help unhandled error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/help", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


# ── help: callback handler ─────────────────────────────────────────────────────

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    action = query.data.replace("help:", "")

    try:
        is_private = is_private_chat(chat.id, user.id)

        if action == "back":
            text = _main_help_text(
                in_group=not is_private,
                group_name=chat.title if not is_private else None,
            )
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=_main_keyboard(),
            )
            return

        if action == "add":
            text = (
                "<b>📌 How to add a spot</b>\n\n"
                "Just send: /add followed by the place name.\n\n"
                "Examples:\n"
                "· /add Burnt Ends Dempsey\n"
                "· /add Din Tai Fung VivoCity\n"
                "· /add Newton Food Centre\n\n"
                "I'll search Google Places and show you the top match to confirm. "
                "Once saved, you can add a note, log a visit, or remove it — "
                "all from the buttons that appear right after.\n\n"
                "Tip: include the area name for more accurate results 📍"
            )

        elif action == "ask":
            text = (
                "<b>🤖 How /ask works</b>\n\n"
                "I pull from 3 sources to give you personalised picks:\n"
                "1. Your visit history and ratings\n"
                "2. Your group's wishlist\n"
                "3. Google Places for things you haven't tried yet\n\n"
                "Example queries:\n"
                "· /ask something cosy in Bugis\n"
                "· /ask birthday dinner, not too formal\n"
                "· /ask good ramen near Orchard\n"
                "· /ask cheap eats in the East\n\n"
                "The more you log with /visit, the smarter my recs get 👀"
            )

        elif action == "visit":
            text = (
                "<b>✅ How to log a visit</b>\n\n"
                "Use /visit to record a meal you've had. Here's the flow:\n\n"
                "1. Pick a place from your wishlist\n"
                "2. Rate it (1–5 stars)\n"
                "3. Leave a quick review\n"
                "4. Tag the occasion (date night, family, solo, etc.)\n"
                "5. Add photos if you want\n\n"
                "Every visit builds your taste profile — so /ask gets sharper the more you log 🍜"
            )

        elif action == "group":
            bot_username = context.bot.username
            text = (
                "<b>👥 Using eatwatah in a group</b>\n\n"
                "<b>Private DM</b> → your personal list, just for you.\n"
                "<b>Group chat</b> → shared list for everyone in the group. "
                "All commands work on the group's wishlist when used here.\n\n"
                "To add me to a group:\n"
                f"1. Open the group chat\n"
                f"2. Tap the group name → Add Members\n"
                f"3. Search for <b>@{html.escape(bot_username)}</b>\n"
                f"4. Add me, then send /start in the group to kick things off\n\n"
                "Everyone in the group can add spots, log visits, and /ask for recs — "
                "all shared in one place 🎉"
            )

        else:
            await query.edit_message_text(
                "Hmm, not sure what that was. Try /help again 😅"
            )
            return

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )

    except Exception as e:
        logger.error("help_callback error for user %s, action=%s: %s", user.id, action, e)
        await log_error(user.id, chat.id, f"help:{action}", type(e).__name__, str(e))
        await query.edit_message_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
