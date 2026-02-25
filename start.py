"""Unified entry point: runs the PTB Telegram bot + FastAPI in the same asyncio event loop.

Used by Railway via `Procfile: web: python start.py`.
For bot-only local dev, use `python bot/main.py` instead.
"""
import asyncio
import logging
import os
import sys

# Load env file BEFORE any other project imports so all modules see correct vars.
# bot/main.py also calls load_dotenv() at its top level, but since override=True
# on both sides, the second call (during import) wins — which is fine.
from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"), override=True)

import uvicorn
from telegram import Update

from api.main import app as fastapi_app
from bot.main import build_app

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def run() -> None:
    ptb_app = build_app()

    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        loop="none",          # use the existing asyncio event loop
        lifespan="off",
    )
    server = uvicorn.Server(config)

    async with ptb_app:
        await ptb_app.start()
        await ptb_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot started + FastAPI listening on port %d", port)

        try:
            await server.serve()
        finally:
            logger.info("Shutting down bot...")
            await ptb_app.updater.stop()
            await ptb_app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Stopped by keyboard interrupt")
