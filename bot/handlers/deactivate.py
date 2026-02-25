import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from db.connection import AsyncSessionLocal
from db.context import is_private_chat
from db.helpers import ensure_user_and_chat, log_error, reactivate_if_needed
from db.models import User

logger = logging.getLogger(__name__)


async def deactivate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/deactivate called by user %s in chat %s", user.id, chat.id)

    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )

    # If user was deactivated, reactivate_if_needed re-activates them and sends the
    # welcome-back message — the /deactivate command then proceeds and would immediately
    # deactivate again. This matches the spec edge case: the guard below catches it.
    await reactivate_if_needed(user.id, chat.id, context.bot)

    try:
        async with AsyncSessionLocal() as session:
            try:
                db_user = await session.scalar(
                    select(User).where(User.telegram_id == str(user.id))
                )
                # Guard: already deactivated (reactivate_if_needed should have caught this,
                # but handle defensively just in case)
                if not db_user or db_user.is_deactivated:
                    return

                db_user.is_deactivated = True
                await session.commit()

            except Exception as e:
                await session.rollback()
                logger.error("/deactivate DB error for user %s: %s", user.id, e)
                await log_error(user.id, chat.id, "/deactivate", type(e).__name__, str(e))
                await update.message.reply_text(
                    "Something went wrong on our end — not your fault! Try again in a bit 🙏"
                )
                return

    except Exception as e:
        logger.error("/deactivate session error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/deactivate", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
        return

    await update.message.reply_text(
        "Your account has been deactivated. Your wishlist is saved and you can return any time. "
        "To permanently delete all your data, use /deleteaccount."
    )
