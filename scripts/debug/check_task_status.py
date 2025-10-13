#!/usr/bin/env python3
"""Check current task execution status."""
import asyncio
import sys
from src.adapters.database import DatabaseAdapter
from src.adapters.redis_adapter import RedisAdapter
from src.config.settings import Settings


async def check_task_status():
    """Check current task status in Redis and database."""
    Settings()
    db = DatabaseAdapter()
    redis = RedisAdapter()

    await db.connect()
    await redis.connect()

    print("🔍 检查任务执行状态...\n")

    # 1. 检查Redis中的任务队列
    try:
        # 检查各个队列的长度
        queues = ["matches", "ai", "default"]
        for queue_name in queues:
            queue_key = f"celery:queue:{queue_name}"
            length = await redis._client.llen(queue_key)
            if length > 0:
                print(f"📋 队列 {queue_name}: {length} 个待处理任务")
    except Exception as e:
        print(f"⚠️  Redis队列检查失败: {e}")

    # 2. 检查最近的match_analytics记录
    try:
        query = """
            SELECT
                match_id,
                puuid,
                status,
                created_at,
                updated_at,
                processing_duration_ms,
                score_data->>'game_duration_minutes' as duration_min
            FROM match_analytics
            ORDER BY created_at DESC
            LIMIT 5
        """
        rows = await db._pool.fetch(query)

        if rows:
            print("\n📊 最近的分析记录 (最新5条):\n")
            print(f"{'Match ID':<20} {'Status':<12} {'Duration':<10} {'Created':<20} {'Updated'}")
            print("-" * 90)

            for row in rows:
                match_id = row["match_id"]
                status = row["status"]
                duration = row["duration_min"] or "N/A"
                created = row["created_at"].strftime("%m-%d %H:%M:%S")
                updated = (
                    row["updated_at"].strftime("%m-%d %H:%M:%S") if row["updated_at"] else "N/A"
                )

                marker = (
                    "🔄" if status == "processing" else ("✅" if status == "completed" else "❌")
                )
                print(
                    f"{marker} {match_id:<20} {status:<12} {duration:<10} {created:<20} {updated}"
                )
        else:
            print("\n📊 数据库中暂无分析记录")

    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")

    # 3. 检查最近的match_data记录（看是否重新拉取了Arena数据）
    try:
        query2 = """
            SELECT
                match_id,
                match_data->'info'->>'queueId' as queue_id,
                match_data->'info'->>'gameMode' as game_mode,
                match_data->'info'->>'gameDuration' as duration_sec,
                created_at
            FROM match_data
            ORDER BY created_at DESC
            LIMIT 5
        """
        rows2 = await db._pool.fetch(query2)

        if rows2:
            print("\n📦 最近的对局数据记录:\n")
            print(f"{'Match ID':<20} {'Queue':<7} {'Mode':<10} {'Duration(s)':<12} {'Created'}")
            print("-" * 80)

            for row in rows2:
                match_id = row["match_id"]
                queue = row["queue_id"] or "N/A"
                mode = row["game_mode"] or "N/A"
                duration = row["duration_sec"] or "N/A"
                created = row["created_at"].strftime("%m-%d %H:%M:%S")

                is_arena = queue == "1700"
                marker = "🎯 " if is_arena else "   "
                print(f"{marker}{match_id:<20} {queue:<7} {mode:<10} {duration:<12} {created}")

    except Exception as e:
        print(f"❌ 对局数据查询失败: {e}")

    await db.disconnect()
    await redis.disconnect()

    return True


if __name__ == "__main__":
    success = asyncio.run(check_task_status())
    sys.exit(0 if success else 1)
