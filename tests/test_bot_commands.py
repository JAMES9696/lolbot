#!/usr/bin/env python
"""直接测试 Discord Bot 命令功能.

不需要通过 Discord UI，直接调用底层功能进行测试。
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any

# 导入 bot 的核心功能
from src.adapters.riot_api import RiotAPIAdapter
from src.adapters.database import DatabaseAdapter
from src.tasks.analysis_tasks import analyze_match_task
from src.tasks.team_tasks import analyze_team_task
from src.config.settings import get_settings


class BotCommandTester:
    """Bot 命令测试器."""

    def __init__(self):
        self.settings = get_settings()
        self.riot_api = RiotAPIAdapter()
        self.db = DatabaseAdapter()  # 不需要传参数
        self.test_results = []

    async def setup(self):
        """初始化连接."""
        # RiotAPIAdapter 在构造函数中已经初始化
        await self.db.connect()

    async def teardown(self):
        """清理连接."""
        await self.db.disconnect()

    async def test_analyze_command(self, riot_id: str, match_index: int) -> dict[str, Any]:
        """测试 /analyze 命令."""
        print(f"\n🧪 测试 /analyze match_index:{match_index} riot_id:{riot_id}")

        start_time = time.perf_counter()
        result = {
            "command": "/analyze",
            "params": {"riot_id": riot_id, "match_index": match_index},
            "success": False,
            "error": None,
            "duration_ms": 0,
            "response": None,
        }

        try:
            # 1. 获取召唤师信息
            name, tag = riot_id.split("#")
            account = await self.riot_api.get_account_by_riot_id(name, tag)

            if not account:
                raise ValueError(f"Account not found: {riot_id}")

            puuid = account.get("puuid")
            if not puuid:
                raise ValueError(f"No PUUID in account response: {account}")
            print(f"  ✅ 找到账号 PUUID: {puuid[:8]}...")

            # 2. 获取比赛历史
            matches = await self.riot_api.get_match_history(puuid, region="americas")

            if not matches or len(matches) < match_index:
                raise ValueError(f"Match index {match_index} not found")

            match_id = matches[match_index - 1]
            print(f"  ✅ 找到比赛: {match_id}")

            # 3. 调用分析任务 (使用 apply_async 传递完整 payload)
            task_payload = {
                "application_id": self.settings.discord_application_id or "test_app_id",
                "interaction_token": "test_token",
                "channel_id": "test_channel",
                "discord_user_id": "test_user_123",
                "puuid": puuid,
                "match_id": match_id,
                "region": "americas",
                "match_index": match_index,
                "correlation_id": f"bot-test:{match_id}:{match_index}",
            }

            task_result = analyze_match_task.apply_async(kwargs=task_payload).get(timeout=60)

            result["success"] = True
            result["response"] = task_result
            print("  ✅ 分析完成")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ❌ 错误: {e}")

        result["duration_ms"] = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️ 耗时: {result['duration_ms']:.2f}ms")

        self.test_results.append(result)
        return result

    async def test_team_analyze_command(self, riot_id: str, match_index: int) -> dict[str, Any]:
        """测试 /team-analyze 命令."""
        print(f"\n🧪 测试 /team-analyze match_index:{match_index} riot_id:{riot_id}")

        start_time = time.perf_counter()
        result = {
            "command": "/team-analyze",
            "params": {"riot_id": riot_id, "match_index": match_index},
            "success": False,
            "error": None,
            "duration_ms": 0,
            "response": None,
        }

        try:
            # 1. 获取召唤师信息
            name, tag = riot_id.split("#")
            account = await self.riot_api.get_account_by_riot_id(name, tag)

            if not account:
                raise ValueError(f"Account not found: {riot_id}")

            puuid = account.get("puuid")
            if not puuid:
                raise ValueError(f"No PUUID in account response: {account}")
            print(f"  ✅ 找到账号 PUUID: {puuid[:8]}...")

            # 2. 获取比赛历史
            matches = await self.riot_api.get_match_history(puuid, region="americas")

            if not matches or len(matches) < match_index:
                raise ValueError(f"Match index {match_index} not found")

            match_id = matches[match_index - 1]
            print(f"  ✅ 找到比赛: {match_id}")

            # 3. 调用团队分析任务
            team_payload = {
                "match_id": match_id,
                "puuid": puuid,
                "region": "americas",
                "discord_user_id": "test_user_123",
                "application_id": self.settings.discord_application_id or "test_app_id",
                "interaction_token": "test_token",
                "channel_id": "test_channel",
                "guild_id": "test_guild",
                "match_index": match_index,
                "correlation_id": f"bot-team-test:{match_id}:{match_index}",
            }

            task_result = analyze_team_task.apply_async(kwargs=team_payload).get(timeout=90)

            result["success"] = True
            result["response"] = task_result
            print("  ✅ 团队分析完成")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ❌ 错误: {e}")

        result["duration_ms"] = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️ 耗时: {result['duration_ms']:.2f}ms")

        self.test_results.append(result)
        return result

    async def run_all_tests(self):
        """运行所有测试."""
        print("=" * 60)
        print("🚀 开始 Discord Bot 命令测试")
        print("=" * 60)

        riot_id = "FujiShanXia#NA1"

        # 测试 /analyze 命令
        await self.test_analyze_command(riot_id, 1)
        await asyncio.sleep(2)
        await self.test_analyze_command(riot_id, 2)
        await asyncio.sleep(2)

        # 测试 /team-analyze 命令
        await self.test_team_analyze_command(riot_id, 1)
        await asyncio.sleep(2)
        await self.test_team_analyze_command(riot_id, 2)

    def generate_report(self) -> dict[str, Any]:
        """生成测试报告."""
        success_count = sum(1 for r in self.test_results if r["success"])
        total_count = len(self.test_results)

        avg_duration = (
            sum(r["duration_ms"] for r in self.test_results) / total_count if total_count > 0 else 0
        )

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_count,
                "passed": success_count,
                "failed": total_count - success_count,
                "pass_rate": f"{(success_count/total_count*100):.1f}%" if total_count > 0 else "0%",
                "avg_duration_ms": avg_duration,
            },
            "test_results": self.test_results,
            "recommendations": [],
        }

        # 生成建议
        if avg_duration > 5000:
            report["recommendations"].append("⚠️ 平均响应时间过长，建议优化缓存策略")

        if success_count < total_count:
            report["recommendations"].append("❌ 存在失败的测试，请检查错误日志")

        if not report["recommendations"]:
            report["recommendations"].append("✅ 所有测试通过，性能良好")

        return report


async def main():
    """主测试函数."""
    tester = BotCommandTester()

    try:
        await tester.setup()
        await tester.run_all_tests()

        # 生成报告
        report = tester.generate_report()

        # 保存报告
        with open("tests/reports/bot_command_test_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 打印摘要
        print("\n" + "=" * 60)
        print("📊 测试报告摘要")
        print("=" * 60)
        print(f"总测试数: {report['summary']['total_tests']}")
        print(f"✅ 通过: {report['summary']['passed']}")
        print(f"❌ 失败: {report['summary']['failed']}")
        print(f"通过率: {report['summary']['pass_rate']}")
        print(f"平均耗时: {report['summary']['avg_duration_ms']:.2f}ms")
        print("\n💡 建议:")
        for rec in report["recommendations"]:
            print(f"  {rec}")
        print("=" * 60)

    finally:
        await tester.teardown()


if __name__ == "__main__":
    asyncio.run(main())
