#!/usr/bin/env python3
"""Check Redis connection and Celery queue status."""
import asyncio
import sys
from src.adapters.redis_adapter import RedisAdapter
from src.config.settings import Settings


async def check_redis_queues():
    """Check Redis queues for pending tasks."""
    settings = Settings()
    redis = RedisAdapter()

    try:
        await redis.connect()
        print("✅ Redis连接成功\n")

        # 检查队列中的任务
        queues = ["celery", "matches", "ai", "default"]

        print("📋 Celery队列状态:\n")
        total_tasks = 0

        for queue_name in queues:
            # Celery uses different key formats
            queue_key = queue_name
            length = await redis._client.llen(queue_key)

            if length > 0:
                print(f"  {queue_name}: {length} 个待处理任务 ⚠️")
                total_tasks += length

                # Show first task in queue
                task_data = await redis._client.lindex(queue_key, 0)
                if task_data:
                    print(f"    首个任务预览: {str(task_data)[:100]}...")
            else:
                print(f"  {queue_name}: 0 个任务")

        print(f"\n总计待处理任务: {total_tasks}")

        # 检查所有与celery相关的key
        print("\n🔑 所有Celery相关的Redis keys:")
        all_keys = await redis._client.keys("celery*")
        if all_keys:
            for key in all_keys[:20]:  # 只显示前20个
                key_type = await redis._client.type(key)
                if key_type == b"list":
                    length = await redis._client.llen(key)
                    print(f"  {key.decode()}: {key_type.decode()} (长度: {length})")
                else:
                    print(f"  {key.decode()}: {key_type.decode()}")

            if len(all_keys) > 20:
                print(f"  ... 还有 {len(all_keys) - 20} 个keys未显示")
        else:
            print("  ❌ 没有找到任何celery相关的keys")

        # 测试ping
        pong = await redis._client.ping()
        print(f"\n🏓 Redis PING: {pong}")

        await redis.disconnect()
        return True

    except Exception as e:
        print(f"❌ Redis检查失败: {e}")
        import traceback

        traceback.print_exc()
        try:
            await redis.disconnect()
        except:
            pass
        return False


if __name__ == "__main__":
    success = asyncio.run(check_redis_queues())
    sys.exit(0 if success else 1)
