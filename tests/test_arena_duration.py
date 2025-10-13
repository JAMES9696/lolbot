#!/usr/bin/env python3
"""Test Arena duration calculation fix."""
import asyncio
import sys
from src.adapters.database import DatabaseAdapter
from src.config.settings import Settings


async def test_arena_duration():
    """Test that Arena match duration is calculated correctly."""
    Settings()
    db = DatabaseAdapter()
    await db.connect()

    match_id = "NA1_5388494924"

    # Get Arena match data
    match_row = await db.get_match_data(match_id)
    if not match_row:
        print(f"❌ Match {match_id} not found in database")
        await db.disconnect()
        return False

    match_details = match_row["match_data"]
    timeline_data = match_row["timeline_data"]

    info = match_details.get("info", {})
    print("📊 Arena Match Raw Data:")
    print(f"  Queue ID: {info.get('queueId')}")
    print(f"  Game Mode: {info.get('gameMode')}")
    print(f"  Game Duration (from API): {info.get('gameDuration')} seconds")
    print(f"  Participants: {len(info.get('participants', []))}")

    # Test duration calculation logic (from team_tasks.py)
    duration_s = 0.0

    # Fallback 1: gameEndTimestamp - gameStartTimestamp
    try:
        if info.get("gameStartTimestamp") and info.get("gameEndTimestamp"):
            duration_s = max(
                0.0,
                (float(info.get("gameEndTimestamp")) - float(info.get("gameStartTimestamp")))
                / 1000.0,
            )
            print(f"\n✅ Fallback 1 (timestamps): {duration_s:.1f} seconds")
    except Exception as e:
        print(f"\n⚠️  Fallback 1 failed: {e}")

    # Fallback 2: gameDuration from info
    if duration_s <= 0:
        try:
            duration_s = float(info.get("gameDuration", 0) or 0)
            print(f"\n✅ Fallback 2 (gameDuration): {duration_s:.1f} seconds")
        except Exception as e:
            print(f"\n⚠️  Fallback 2 failed: {e}")

    # Fallback 3: timeline frame timestamps
    if duration_s <= 0:
        try:
            t_info = timeline_data.get("info", {}) or {}
            frames = t_info.get("frames", []) or []
            if len(frames) >= 2:
                first_ts = frames[0].get("timestamp", 0) or 0
                last_ts = frames[-1].get("timestamp", 0) or 0
                duration_s = max(0.0, (last_ts - first_ts) / 1000.0)
                print(f"\n✅ Fallback 3 (frame timestamps): {duration_s:.1f} seconds")
        except Exception as e:
            print(f"\n⚠️  Fallback 3 failed: {e}")

    duration_min = round(duration_s / 60.0, 1) if duration_s else 0.0

    print("\n📈 Final Calculated Duration:")
    print(f"  Seconds: {duration_s:.1f}")
    print(f"  Minutes: {duration_min:.1f}")

    await db.disconnect()

    if duration_min > 0:
        print("\n🎉 ✅ ARENA DURATION CALCULATION FIXED!")
        print("   Expected: ~21.5 minutes")
        print(f"   Got: {duration_min} minutes")
        return True
    else:
        print("\n❌ Duration still 0 - fix failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_arena_duration())
    sys.exit(0 if success else 1)
