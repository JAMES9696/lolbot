#!/usr/bin/env python3
"""重新处理指定对局的分析任务"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tasks.celery_app import celery_app


async def reprocess_match(match_id: str) -> None:
    """重新触发对局分析任务"""
    from src.adapters.database import DatabaseAdapter
    from src.adapters.riot_api import RiotAPIAdapter

    db = DatabaseAdapter()
    await db.connect()
    riot_api = RiotAPIAdapter()

    print(f"🔍 正在检查对局 {match_id}...")

    # 获取对局数据
    match_data = await riot_api.get_match_details(match_id, "americas")
    if not match_data:
        print("❌ 对局数据未找到")
        return

    print("✅ 对局数据已找到")

    # 删除旧的分析结果
    print("🗑️  删除旧的分析结果...")
    await db.execute("DELETE FROM analysis_results WHERE match_id = $1", match_id)

    print("✅ 旧结果已删除")

    # 触发新的分析任务
    print("🚀 触发新的分析任务...")

    # 模拟 Discord 交互参数
    task_payload = {
        "application_id": "test_app_id",
        "interaction_token": "test_token",
        "channel_id": "test_channel",
        "discord_user_id": "test_user",
        "puuid": match_data["metadata"]["participants"][0],  # 第一个玩家
        "match_id": match_id,
        "region": "americas",
        "match_index": 1,
        "correlation_id": f"reprocess_{match_id}",
    }

    result = celery_app.send_task(
        "src.tasks.analysis_tasks.analyze_match_task", kwargs=task_payload
    )

    print(f"✅ 任务已提交: {result.id}")
    print("📊 等待任务完成...")

    # 等待任务完成
    try:
        result.get(timeout=300)  # 5分钟超时
        print("✅ 任务完成！")

        # 读取新的分析结果
        print("\n📋 读取新的分析结果...")
        new_result = await db.get_analysis_result(match_id)

        if new_result:
            print("✅ 分析结果已保存")
            print("\n📊 分析摘要:")
            print(f"   召唤师: {new_result.get('summoner_name', 'N/A')}")
            print(f"   英雄: {new_result.get('champion_name', 'N/A')}")
            print(f"   结果: {new_result.get('match_result', 'N/A').upper()}")

            # 检查 AI 评价
            llm_meta = new_result.get("llm_metadata", {})
            if isinstance(llm_meta, str):
                import json

                try:
                    llm_meta = json.loads(llm_meta)
                except:
                    llm_meta = {}

            ai_review = llm_meta.get("ai_review_cn")
            if ai_review:
                print("\n🤖 AI 评价:")
                print(f"   {ai_review[:200]}...")

            # 检查 score_data 中的团队分析
            score_data = new_result.get("score_data", {})
            if isinstance(score_data, str):
                import json

                try:
                    score_data = json.loads(score_data)
                except:
                    score_data = {}

            team_summary = score_data.get("team_summary", {})
            if team_summary:
                print("\n👥 团队摘要:")
                team_tldr = team_summary.get("team_tldr")
                if team_tldr:
                    print(f"   {team_tldr[:200]}...")
        else:
            print("❌ 未找到分析结果")

    except Exception as e:
        print(f"❌ 任务失败: {e}")
        import traceback

        traceback.print_exc()

    await db.close()


if __name__ == "__main__":
    match_id = sys.argv[1] if len(sys.argv) > 1 else "NA1_5151928908"
    asyncio.run(reprocess_match(match_id))
