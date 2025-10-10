"""Cleanup test bindings from database."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters.database import DatabaseAdapter


async def cleanup():
    """Remove all test bindings."""
    db = DatabaseAdapter()
    await db.connect()

    test_discord_id = "123456789012345678"

    print(f"Cleaning up test binding for Discord ID: {test_discord_id}")

    await db.delete_user_binding(test_discord_id)

    print("✅ Cleanup complete")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(cleanup())
