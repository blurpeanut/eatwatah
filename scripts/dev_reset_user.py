"""
Dev-only: delete a user record so /start treats them as a new user again.
Usage:
    set ENV_FILE=.env.dev && python scripts/dev_reset_user.py YOUR_TELEGRAM_ID
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"))

from sqlalchemy import delete, select
from db.connection import AsyncSessionLocal
from db.models import User


async def reset(telegram_id: str) -> None:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            print(f"No user found with telegram_id={telegram_id}")
            return
        print(f"Deleting user: {user.display_name} (id={telegram_id})")
        await session.execute(delete(User).where(User.telegram_id == telegram_id))
        await session.commit()
        print("Done — /start will now show the new user welcome.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/dev_reset_user.py YOUR_TELEGRAM_ID")
        sys.exit(1)
    asyncio.run(reset(sys.argv[1]))
