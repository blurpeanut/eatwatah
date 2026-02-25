"""
Audit script — reads current state of WishlistEntries area/location data.
Read-only: makes no changes to the database.

Run with dev DB:
    ENV_FILE=.env.dev python scripts/audit_area_data.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"))

from sqlalchemy import func, or_, select, text
from db.connection import AsyncSessionLocal
from db.models import WishlistEntry


async def run_audit() -> None:
    async with AsyncSessionLocal() as session:
        # 1. Count rows where area = 'Others' or area is null
        bad_area_count_q = await session.execute(
            select(func.count()).where(
                or_(WishlistEntry.area == "Others", WishlistEntry.area.is_(None))
            )
        )
        bad_area_count = bad_area_count_q.scalar()

        # 2. Count rows where lat or lng is null
        null_latlong_q = await session.execute(
            select(func.count()).where(
                or_(WishlistEntry.lat.is_(None), WishlistEntry.lng.is_(None))
            )
        )
        null_latlong_count = null_latlong_q.scalar()

        # 3. Total row count (for context)
        total_q = await session.execute(select(func.count()).select_from(WishlistEntry))
        total_count = total_q.scalar()

        # 4. Sample up to 20 rows where area = 'Others' or null
        sample_q = await session.execute(
            select(
                WishlistEntry.id,
                WishlistEntry.name,
                WishlistEntry.address,
                WishlistEntry.area,
                WishlistEntry.lat,
                WishlistEntry.lng,
            )
            .where(
                or_(WishlistEntry.area == "Others", WishlistEntry.area.is_(None))
            )
            .limit(20)
        )
        sample_rows = sample_q.all()

    print("=" * 60)
    print("eatwatah — WishlistEntries Area/Location Audit")
    print("=" * 60)
    print(f"Total WishlistEntry rows:             {total_count}")
    print(f"Rows with area='Others' or null:      {bad_area_count}")
    print(f"Rows with null lat or lng:            {null_latlong_count}")
    print()
    print(f"Sample (up to 20) rows with bad area:")
    print("-" * 60)
    if not sample_rows:
        print("  (none)")
    else:
        for row in sample_rows:
            name_safe = row.name.encode("ascii", "replace").decode()
            addr_safe = (row.address or "").encode("ascii", "replace").decode()
            print(
                f"  id={row.id} | name={name_safe!r} | area={row.area!r} "
                f"| lat={row.lat} | lng={row.lng}"
            )
            print(f"    address: {addr_safe!r}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_audit())
