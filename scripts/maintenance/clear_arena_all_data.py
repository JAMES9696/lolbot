#!/usr/bin/env python3
"""Clear all cached data for Arena match to force complete re-fetch."""
import asyncio
import sys
from src.adapters.database import DatabaseAdapter
from src.adapters.redis_adapter import RedisAdapter
from src.config.settings import Settings


async def clear_all_arena_data():
    """Clear all cached data for Arena match NA1_5388494924."""
    settings = Settings()
    db = DatabaseAdapter()
    redis = RedisAdapter()

    await db.connect()
    await redis.connect()

    match_id = "NA1_5388494924"

    print(f"🧹 清除Arena对局 {match_id} 的所有数据...\n")

    # 1. 清除数据库 - match_analytics表
    try:
        query1 = "DELETE FROM match_analytics WHERE match_id = $1 RETURNING match_id"
        result1 = await db._pool.fetch(query1, match_id)
        if result1:
            print(f"✅ 已删除 match_analytics: {len(result1)} 条记录")
        else:
            print("ℹ️  match_analytics: 无记录")
    except Exception as e:
        print(f"⚠️  删除 match_analytics 失败: {e}")

    # 2. 清除数据库 - match_data表
    try:
        query2 = "DELETE FROM match_data WHERE match_id = $1 RETURNING match_id"
        result2 = await db._pool.fetch(query2, match_id)
        if result2:
            print(f"✅ 已删除 match_data: {len(result2)} 条记录")
        else:
            print("ℹ️  match_data: 无记录")
    except Exception as e:
        print(f"⚠️  删除 match_data 失败: {e}")

    # 3. 清除Redis缓存 - match相关的所有key
    try:
        # 匹配所有可能的cache key模式
        patterns = [
            f"cache:match:{match_id}*",
            f"cache:timeline:{match_id}*",
            f"cache:llm:*{match_id}*",
            f"lock:match:{match_id}*",
        ]

        total_deleted = 0
        for pattern in patterns:
            keys = await redis._client.keys(pattern)
            if keys:
                deleted = await redis._client.delete(*keys)
                total_deleted += deleted
                print(f"✅ 已删除 Redis keys ({pattern}): {deleted} 个")

        if total_deleted == 0:
            print("ℹ️  Redis: 无缓存")
        else:
            print(f"✅ Redis总计删除: {total_deleted} 个key")

    except Exception as e:
        print(f"⚠️  清除 Redis 缓存失败: {e}")

    # 4. 验证清除结果
    print("\n🔍 验证清除结果:")

    try:
        verify1 = await db._pool.fetchval(
            "SELECT COUNT(*) FROM match_analytics WHERE match_id = $1", match_id
        )
        verify2 = await db._pool.fetchval(
            "SELECT COUNT(*) FROM match_data WHERE match_id = $1", match_id
        )

        print(f"   match_analytics: {verify1} 条记录")
        print(f"   match_data: {verify2} 条记录")

        if verify1 == 0 and verify2 == 0:
            print("\n🎉 ✅ 所有数据已清除！")
            print("📝 下次执行 /讲道理 或 /战队分析 时将从Riot API重新拉取")
            success = True
        else:
            print(f"\n⚠️  警告: 仍有 {verify1 + verify2} 条记录残留")
            success = False

    except Exception as e:
        print(f"⚠️  验证失败: {e}")
        success = False

    await db.disconnect()
    await redis.disconnect()

    return success


if __name__ == "__main__":
    success = asyncio.run(clear_all_arena_data())
    sys.exit(0 if success else 1)
