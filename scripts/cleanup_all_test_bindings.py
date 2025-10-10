"""Cleanup all test bindings from database."""

import asyncio
from src.adapters.database import DatabaseAdapter


async def cleanup_all():
    """Remove all test bindings with mock PUUIDs."""
    db = DatabaseAdapter()
    await db.connect()

    print("Cleaning up all mock test bindings...")

    # Mock PUUIDs from our test accounts
    mock_puuids = [
        "0" * 78,  # test_code_1
        "1" * 78,  # test_code_2
        "2" * 78,  # test_code_3
    ]

    for puuid in mock_puuids:
        # Find and delete any binding with this PUUID
        query = "DELETE FROM user_bindings WHERE puuid = $1 RETURNING discord_id"
        result = await db._pool.fetch(query, puuid)
        if result:
            for row in result:
                print(
                    f"✅ Deleted binding: Discord ID {row['discord_id']} -> PUUID {puuid[:20]}..."
                )

    print("✅ Cleanup complete")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(cleanup_all())
