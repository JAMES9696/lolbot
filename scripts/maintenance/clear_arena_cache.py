#!/usr/bin/env python3
"""Clear cached analysis for Arena match to force fresh calculation."""
import asyncio
import sys
from src.adapters.database import DatabaseAdapter
from src.config.settings import Settings


async def clear_arena_cache():
    """Clear cached analysis for Arena match NA1_5388494924."""
    settings = Settings()
    db = DatabaseAdapter()
    await db.connect()

    match_id = "NA1_5388494924"

    # Delete cached analysis from match_analytics table
    try:
        query = """
            DELETE FROM match_analytics
            WHERE match_id = $1
            RETURNING match_id, status, created_at
        """
        deleted_rows = await db._pool.fetch(query, match_id)

        if deleted_rows:
            print(f"✅ Cleared {len(deleted_rows)} cached analysis record(s) for {match_id}")
            for row in deleted_rows:
                print(f"   - Status: {row['status']}, Created: {row['created_at']}")
        else:
            print(f"ℹ️  No cached analysis found for {match_id} (may already be cleared)")

        # Verify deletion
        verify_query = "SELECT COUNT(*) as count FROM match_analytics WHERE match_id = $1"
        result = await db._pool.fetchrow(verify_query, match_id)
        remaining = result["count"]

        if remaining == 0:
            print("\n🎉 Cache successfully cleared! Next analysis will be fresh.")
        else:
            print(f"\n⚠️  Warning: {remaining} record(s) still remain")

        await db.disconnect()
        return remaining == 0

    except Exception as e:
        print(f"❌ Error clearing cache: {e}")
        await db.disconnect()
        return False


if __name__ == "__main__":
    success = asyncio.run(clear_arena_cache())
    sys.exit(0 if success else 1)
