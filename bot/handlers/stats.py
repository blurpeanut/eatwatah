import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from db.helpers import get_admin_stats, log_error

logger = logging.getLogger(__name__)


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/stats called by user %s", user.id)

    # Gate: silently ignore anyone who isn't the developer
    developer_id = os.getenv("DEVELOPER_TELEGRAM_ID", "")
    if str(user.id) != developer_id:
        return

    try:
        s = await get_admin_stats()
    except Exception as e:
        logger.error("/stats DB error: %s", e)
        await log_error(user.id, chat.id, "/stats", type(e).__name__, str(e))
        await update.message.reply_text("Couldn't fetch stats right now — check the logs.")
        return

    error_flag = " ⚠️" if s["errors_24h"] > 0 else ""

    await update.message.reply_text(
        f"📊 <b>eatwatah stats</b>\n\n"
        f"👤 Users: <b>{s['users']}</b>\n"
        f"💬 Chats: <b>{s['chats']}</b>\n"
        f"🔖 Wishlist entries: <b>{s['wishlist']}</b>\n"
        f"🍜 Visits logged: <b>{s['visits']}</b>\n"
        f"🚨 Errors (last 24h): <b>{s['errors_24h']}</b>{error_flag}",
        parse_mode="HTML",
    )
