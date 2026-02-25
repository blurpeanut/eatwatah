"""Unified entry point: runs the PTB Telegram bot + FastAPI in the same asyncio event loop.

Used by Railway via `Procfile: web: python start.py`.
For bot-only local dev, use `python bot/main.py` instead.

Webhook mode (Railway): when WEBAPP_BASE_URL is set, Telegram pushes updates to
/webhook — no polling, no Conflict errors on redeploy.
Polling mode (local): when WEBAPP_BASE_URL is not set, falls back to long-polling.
"""
import asyncio
import logging
import os

# Load env file BEFORE any other project imports so all modules see correct vars.
from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"), override=True)

import uvicorn
from fastapi import Request
from fastapi.responses import Response
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
    webapp_base = os.getenv("WEBAPP_BASE_URL", "").strip().rstrip("/")
    use_webhook = bool(webapp_base)

    # Register Telegram webhook endpoint on the FastAPI app
    @fastapi_app.post("/webhook")
    async def telegram_webhook(request: Request) -> Response:
        try:
            data = await request.json()
            update = Update.de_json(data, ptb_app.bot)
            await ptb_app.process_update(update)
        except Exception as e:
            logger.error("Webhook processing error: %s", e)
        return Response(status_code=200)

    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        loop="none",      # reuse the existing asyncio event loop
        lifespan="off",
    )
    server = uvicorn.Server(config)

    async with ptb_app:
        await ptb_app.start()

        if use_webhook:
            webhook_url = f"{webapp_base}/webhook"
            await ptb_app.bot.set_webhook(url=webhook_url)
            logger.info("Webhook mode: %s — FastAPI on port %d", webhook_url, port)
        else:
            await ptb_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("Polling mode — FastAPI on port %d", port)

        try:
            await server.serve()
        finally:
            logger.info("Shutting down...")
            if use_webhook:
                await ptb_app.bot.delete_webhook()
            else:
                await ptb_app.updater.stop()
            await ptb_app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Stopped by keyboard interrupt")
