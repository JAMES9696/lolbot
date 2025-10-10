#!/usr/bin/env python3
"""Check recent match analyses for Arena matches."""
import asyncio
import sys
from src.adapters.database import DatabaseAdapter
from src.config.settings import Settings


async def check_recent_analyses():
    """Check recent analyses, especially failed ones."""
    settings = Settings()
    db = DatabaseAdapter()
    await db.connect()

    try:
        # Get recent analyses, especially failed or completed ones
        query = """
            SELECT
                ma.match_id,
                ma.status,
                ma.created_at,
                ma.updated_at,
                md.match_data->'info'->>'queueId' as queue_id,
                md.match_data->'info'->>'gameMode' as game_mode,
                md.match_data->'info'->>'gameDuration' as api_duration
            FROM match_analytics ma
            LEFT JOIN match_data md ON ma.match_id = md.match_id
            ORDER BY ma.created_at DESC
            LIMIT 10
        """
        rows = await db._pool.fetch(query)

        print("📊 Recent Match Analyses (last 10):\n")
        print(
            f"{'Match ID':<20} {'Queue':<7} {'Mode':<10} {'Status':<12} {'Duration':<10} {'Created'}"
        )
        print("-" * 90)

        for row in rows:
            match_id = row["match_id"]
            status = row["status"]
            queue = row["queue_id"] or "N/A"
            mode = row["game_mode"] or "N/A"
            duration = row["api_duration"] or "N/A"
            created = row["created_at"].strftime("%m-%d %H:%M:%S")

            # Highlight Arena matches
            is_arena = queue == "1700"
            marker = "🎯 " if is_arena else "   "

            print(
                f"{marker}{match_id:<20} {queue:<7} {mode:<10} {status:<12} {duration:<10} {created}"
            )

        # Check for any failed Arena analyses
        failed_query = """
            SELECT
                ma.match_id,
                ma.status,
                ma.score_data,
                md.match_data->'info'->>'queueId' as queue_id
            FROM match_analytics ma
            LEFT JOIN match_data md ON ma.match_id = md.match_id
            WHERE ma.status = 'failed'
            ORDER BY ma.created_at DESC
            LIMIT 5
        """
        failed_rows = await db._pool.fetch(failed_query)

        if failed_rows:
            print("\n\n❌ Recent Failed Analyses:")
            for row in failed_rows:
                match_id = row["match_id"]
                queue = row["queue_id"] or "N/A"
                score_data = row["score_data"]

                print(f"\n   Match: {match_id} (Queue: {queue})")
                if score_data:
                    # Try to extract error info
                    try:
                        error_msg = score_data.get("error_message", "No error message")
                        error_stage = score_data.get("error_stage", "Unknown stage")
                        print(f"   Error: {error_msg}")
                        print(f"   Stage: {error_stage}")
                    except:
                        print(f"   Score data: {str(score_data)[:100]}...")

        await db.disconnect()
        return True

    except Exception as e:
        print(f"❌ Error checking analyses: {e}")
        import traceback

        traceback.print_exc()
        await db.disconnect()
        return False


if __name__ == "__main__":
    success = asyncio.run(check_recent_analyses())
    sys.exit(0 if success else 1)
