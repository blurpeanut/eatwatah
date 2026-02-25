"""
Backfill area and cuisine_type on all existing WishlistEntry rows.

- Re-derives area via reverse_geocode_area() (skips rows with null lat/lng)
- Classifies cuisine_type via classify_cuisine() using Place Details API
  For rows whose place_id starts with "manual:" no API call is made.
- Commits in batches of 50 to avoid long-running transactions
- Dry-run mode (--dry-run) prints what would change without writing

Run ONLY after the Alembic migration a1b2c3d4e5f6 has been applied:
    set ENV_FILE=.env.dev && python scripts/backfill_area_cuisine.py --dry-run
    set ENV_FILE=.env.dev && python scripts/backfill_area_cuisine.py
"""
import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

import httpx
from sqlalchemy import select

from db.connection import AsyncSessionLocal
from db.models import WishlistEntry
from services.places_service import (
    PLACES_API_KEY,
    classify_cuisine,
    reverse_geocode_area,
)

BATCH_SIZE = 50

# Place Details endpoint (new Places API v1) — fetches by place_id directly
_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


async def fetch_place_types(place_id: str) -> list[str]:
    """Fetch the types array for a single Google Place ID using Place Details.

    Returns [] on any error or if the place isn't found.
    """
    if not PLACES_API_KEY:
        return []
    url = _PLACE_DETAILS_URL.format(place_id=place_id)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                url,
                headers={
                    "X-Goog-Api-Key": PLACES_API_KEY,
                    "X-Goog-FieldMask": "types",
                },
            )
            resp.raise_for_status()
            return resp.json().get("types", [])
    except Exception as e:
        logger.warning("fetch_place_types failed for %s: %s", place_id, e)
    return []


async def run_backfill(dry_run: bool = False) -> None:
    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info("Starting backfill — mode: %s", mode)

    async with AsyncSessionLocal() as session:
        rows = list((await session.scalars(select(WishlistEntry))).all())

    total = len(rows)
    logger.info("Total WishlistEntry rows to process: %d", total)

    would_update_area = 0
    would_update_cuisine = 0
    skipped_no_coords = 0
    skipped_manual = 0
    errors = 0

    batch: list[WishlistEntry] = []

    for i, entry in enumerate(rows, start=1):
        new_area = entry.area
        new_cuisine = entry.cuisine_type

        is_manual = entry.google_place_id.startswith("manual:")

        # ── Area ──────────────────────────────────────────────────────────
        if entry.lat is not None and entry.lng is not None:
            try:
                geocoded = await reverse_geocode_area(entry.lat, entry.lng)
                if geocoded != (entry.area or ""):
                    new_area = geocoded
                    would_update_area += 1
                    logger.info(
                        "[%d/%d] area %r → %r  (%s)",
                        i, total, entry.area, geocoded, entry.name,
                    )
            except Exception as e:
                logger.warning("[%d/%d] reverse_geocode_area error for id=%d: %s", i, total, entry.id, e)
                errors += 1
        else:
            skipped_no_coords += 1

        # ── Cuisine ───────────────────────────────────────────────────────
        if is_manual:
            skipped_manual += 1
        elif entry.cuisine_type is None:
            try:
                types = await fetch_place_types(entry.google_place_id)
                if types:
                    classified = classify_cuisine(types)
                    new_cuisine = classified
                    would_update_cuisine += 1
                    logger.info(
                        "[%d/%d] cuisine None → %r  (%s)",
                        i, total, classified, entry.name,
                    )
                else:
                    logger.info(
                        "[%d/%d] cuisine — no types returned, leaving None  (%s)",
                        i, total, entry.name,
                    )
            except Exception as e:
                logger.warning("[%d/%d] cuisine fetch error for id=%d: %s", i, total, entry.id, e)
                errors += 1

        # ── Stage update (live only) ──────────────────────────────────────
        if not dry_run:
            entry.area = new_area
            entry.cuisine_type = new_cuisine
            batch.append(entry)

        # ── Commit batch ──────────────────────────────────────────────────
        if not dry_run and len(batch) >= BATCH_SIZE:
            async with AsyncSessionLocal() as session:
                try:
                    for obj in batch:
                        await session.merge(obj)
                    await session.commit()
                    logger.info("Committed batch of %d rows", len(batch))
                except Exception as e:
                    await session.rollback()
                    logger.error("Batch commit failed: %s", e)
                    errors += 1
            batch.clear()

    # ── Final batch ───────────────────────────────────────────────────────
    if not dry_run and batch:
        async with AsyncSessionLocal() as session:
            try:
                for obj in batch:
                    await session.merge(obj)
                await session.commit()
                logger.info("Committed final batch of %d rows", len(batch))
            except Exception as e:
                await session.rollback()
                logger.error("Final batch commit failed: %s", e)
                errors += 1

    action = "would update" if dry_run else "updated"
    logger.info(
        "Backfill complete — mode: %s | total: %d | area %s: %d "
        "| cuisine %s: %d | skipped (no coords): %d "
        "| skipped (manual): %d | errors: %d",
        mode, total,
        action, would_update_area,
        action, would_update_cuisine,
        skipped_no_coords, skipped_manual, errors,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill area + cuisine_type on WishlistEntries")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()
    asyncio.run(run_backfill(dry_run=args.dry_run))
