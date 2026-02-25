import logging
import os
import sys
import traceback

# Load env file before any other imports so all modules see the correct values.
# services/places_service.py also calls load_dotenv() — if it ran first it would
# load .env, and a later load_dotenv(".env.dev") would not override already-set vars.
from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"), override=True)

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

# Ensure project root is on sys.path when running bot/main.py directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.handlers.add import add_conversation_handler, note_conversation_handler, post_add_callback
from bot.handlers.ask import ask_handler
from bot.handlers.delete import (
    delete_cancel,
    delete_confirm,
    delete_handler,
    delete_search_conversation_handler,
    delete_show_confirm,
)
from bot.handlers.delete_account import (
    delete_account_cancel,
    delete_account_confirm,
    delete_account_handler,
)
from bot.handlers.help import help_callback, help_handler
from bot.handlers.stats import stats_handler
from bot.handlers.start import curated_add_callback, quick_action_callback, start_handler
from bot.handlers.view_visited import view_visited_handler
from bot.handlers.view_wishlist import view_wishlist_handler
from bot.handlers.visit import visit_conversation_handler
from db.connection import test_connection
from db.helpers import log_error

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await test_connection()
    await application.bot.set_my_commands([
        BotCommand("start",         "Get started / see your stats"),
        BotCommand("help",          "How to use eatwatah"),
        BotCommand("add",           "Save a food spot to your wishlist"),
        BotCommand("viewwishlist",  "Browse your saved spots"),
        BotCommand("visit",         "Log a meal with rating and review"),
        BotCommand("viewvisited",   "See your visit history"),
        BotCommand("ask",           "Get AI-powered food recommendations"),
        BotCommand("delete",        "Remove a spot from your list"),
        BotCommand("deleteaccount", "Delete your account"),
    ])
    logger.info("eatwatah bot is up and running")


# ── Global error handler ──────────────────────────────────────────────────────

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Last-resort catch-all for unhandled exceptions that escape individual handlers."""
    err = context.error
    tb_str = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    logger.error("Unhandled exception: %s\n%s", err, tb_str)

    # Extract context from update if available
    user_id = chat_id = command = None
    try:
        if isinstance(update, Update):
            if update.effective_user:
                user_id = update.effective_user.id
            if update.effective_chat:
                chat_id = update.effective_chat.id
            if update.message and update.message.text:
                command = update.message.text.split()[0]
            elif update.callback_query:
                command = f"callback:{update.callback_query.data[:30]}"
    except Exception:
        pass

    # Log to Errors table
    await log_error(
        telegram_id=user_id,
        chat_id=chat_id,
        command=command or "unknown",
        error_type=type(err).__name__,
        message=f"{err}\n{tb_str[:1500]}",
    )

    # Alert developer
    dev_id = os.getenv("DEVELOPER_TELEGRAM_ID")
    if dev_id:
        summary = str(err)[:200]
        alert = (
            f"⚠️ eatwatah error: {command or 'unknown'} failed"
            f" for chat {chat_id} — {type(err).__name__}: {summary}"
        )
        try:
            await context.bot.send_message(chat_id=dev_id, text=alert)
        except Exception:
            pass



# ── Unrecognised free text ────────────────────────────────────────────────────

async def unrecognised_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch free-text messages that don't belong to any active conversation."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Place",     callback_data="quick:add"),
            InlineKeyboardButton("🤖 Get Recs",      callback_data="quick:recs"),
        ],
        [
            InlineKeyboardButton("📋 View Wishlist", callback_data="quick:wishlist"),
            InlineKeyboardButton("✅ Log a Visit",   callback_data="quick:visit"),
        ],
    ])
    await update.message.reply_text(
        "Not sure what you mean 😅 Here's what I can do:",
        reply_markup=keyboard,
    )


# ── Stale callback catch-all ──────────────────────────────────────────────────

async def unhandled_callback(update: Update, context) -> None:
    """Catch-all for stale or unrecognised callback queries."""
    await update.callback_query.answer(
        "This action has expired — try the command again 😄", show_alert=False
    )


def build_app() -> Application:
    """Build and return the configured PTB Application.

    Extracted from main() so start.py can run the bot alongside FastAPI
    in the same asyncio event loop without calling run_polling() (which
    blocks and creates its own loop).
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in environment")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # ── Global error handler ───────────────────────────────────────────────────
    app.add_error_handler(global_error_handler)

    # ── Command handlers ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",         start_handler))
    app.add_handler(CommandHandler("help",          help_handler))
    app.add_handler(CommandHandler("stats",         stats_handler))
    app.add_handler(CommandHandler("viewwishlist",  view_wishlist_handler))
    app.add_handler(CommandHandler("viewvisited",   view_visited_handler))
    app.add_handler(CommandHandler("delete",        delete_handler))
    app.add_handler(CommandHandler("ask",           ask_handler))
    app.add_handler(CommandHandler("deleteaccount", delete_account_handler))

    # ── ConversationHandlers (must be before generic CallbackQueryHandlers) ───
    app.add_handler(add_conversation_handler)      # /add
    app.add_handler(note_conversation_handler)     # post_add:note: entry point
    app.add_handler(visit_conversation_handler)    # /visit + wl_visit: + post_add:visit: entry points

    # ── Callback: /help flows ─────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(help_callback,         pattern=r"^help:"))

    # ── Callback: /start flows ────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(curated_add_callback,  pattern=r"^curated_add:"))
    app.add_handler(CallbackQueryHandler(quick_action_callback, pattern=r"^quick:"))

    # ── Callback: /add follow-up buttons ─────────────────────────────────────
    app.add_handler(CallbackQueryHandler(post_add_callback,     pattern=r"^post_add:"))

    # ── Callback: /deleteaccount flow ────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(delete_account_confirm, pattern=r"^da_confirm$"))
    app.add_handler(CallbackQueryHandler(delete_account_cancel,  pattern=r"^da_cancel$"))

    # ── Callback: /delete flow ────────────────────────────────────────────────
    app.add_handler(delete_search_conversation_handler)
    app.add_handler(CallbackQueryHandler(delete_show_confirm,   pattern=r"^(del_pick|wl_delete):"))
    app.add_handler(CallbackQueryHandler(delete_confirm,        pattern=r"^del_confirm:"))
    app.add_handler(CallbackQueryHandler(delete_cancel,         pattern=r"^del_cancel$"))

    # ── Unrecognised free text (after conversations, before catch-all) ────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unrecognised_text))

    # ── Catch-all (must be last) ──────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(unhandled_callback))

    return app


def main() -> None:
    """Run the bot standalone (without FastAPI). Used for local bot-only runs."""
    app = build_app()
    logger.info("Starting bot — press Ctrl+C to stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

