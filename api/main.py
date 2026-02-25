import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from api.routes.wishlist import router as wishlist_router

logger = logging.getLogger(__name__)

_WEBAPP_PATH = Path(__file__).parent.parent / "webapp" / "index.html"

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(wishlist_router)


@app.get("/webapp/index.html", response_class=HTMLResponse)
async def serve_webapp() -> HTMLResponse:
    """Serve the /viewwishlist WebApp HTML with Google Maps API key injected."""
    try:
        html = _WEBAPP_PATH.read_text(encoding="utf-8")
        maps_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        html = html.replace("__GOOGLE_MAPS_API_KEY__", maps_key)
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error("Failed to serve webapp: %s", e)
        return HTMLResponse(
            content="<h1>WebApp temporarily unavailable. Try again in a moment.</h1>",
            status_code=500,
        )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
