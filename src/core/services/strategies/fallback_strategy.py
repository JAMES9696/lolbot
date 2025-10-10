"""Fallback Analysis Strategy for Unsupported Game Modes (V2.3).

This strategy provides graceful degradation for unsupported or unknown game modes.
It returns basic match statistics with a generic message explaining that deep
analysis is not yet available for the mode.

Design Goals:
- Graceful Degradation: System never crashes on unknown queueIds
- Transparency: Users understand why deep analysis is unavailable
- Basic Value: Still provides KDA, damage, and gold stats
- Extensibility: Easy to upgrade to full analysis when new modes are supported

Author: CLI 2 (Backend)
Date: 2025-10-07
Phase: V2.3
"""

import logging
from typing import Any

from src.contracts.v23_multi_mode_analysis import (
    AnalysisStrategy,
    detect_game_mode,
    V23FallbackAnalysisReport,
)

logger = logging.getLogger(__name__)


class FallbackStrategy(AnalysisStrategy):
    """Fallback strategy for unsupported game modes.

    This strategy provides basic analysis when mode-specific algorithms
    are not available (e.g., URF, One For All, Nexus Blitz, Tournament Realm).

    Features:
    - Extracts basic stats from Match-V5 (KDA, damage, gold)
    - Returns generic message explaining lack of deep analysis
    - Optionally generates simple V1-style summary
    - No LLM calls (zero cost for unsupported modes)

    Thread Safety: Stateless, can be used concurrently.
    """

    def get_mode_label(self) -> str:
        """Get lowercase mode label for metrics and logging.

        Returns:
            "fallback" for unsupported modes
        """
        return "fallback"

    async def execute_analysis(
        self,
        match_data: dict[str, Any],
        timeline_data: dict[str, Any],
        requester_puuid: str,
        discord_user_id: str,
        user_profile_context: str | None = None,
        timeline_evidence: Any | None = None,
    ) -> dict[str, Any]:
        """Execute basic fallback analysis for unsupported game modes.

        Args:
            match_data: Raw Match-V5 match details
            timeline_data: Raw Match-V5 timeline data (unused for fallback)
            requester_puuid: PUUID of user who requested analysis
            discord_user_id: Discord user ID (unused for fallback)
            user_profile_context: V2.2 personalization context (unused for fallback)
            timeline_evidence: V2.1 Timeline evidence (unused for fallback)

        Returns:
            Dict with keys:
                - score_data: V23FallbackAnalysisReport as dict
                - metrics: LLM metrics (all zeros, no LLM call made)
                - mode: "fallback"

        Raises:
            Exception: Logged and handled gracefully (returns minimal data)
        """
        result: dict[str, Any] = {
            "metrics": {
                "v2_degraded": False,  # Not degradation - this is expected behavior
                "degradation_reason": None,
                "llm_input_tokens": 0,
                "llm_output_tokens": 0,
                "llm_api_cost_usd": 0.0,
                "llm_latency_ms": 0,
            },
            "score_data": {},
            "mode": self.get_mode_label(),
        }

        try:
            # Step 1: Extract basic match info
            info = match_data.get("info", {})
            participants = info.get("participants", [])
            queue_id = int(info.get("queueId", 0))

            # Step 2: Find requester's participant data
            target_participant = next(
                (p for p in participants if p.get("puuid") == requester_puuid),
                None,
            )

            if not target_participant:
                logger.warning(
                    "fallback_participant_not_found",
                    extra={
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                        "requester_puuid": requester_puuid,
                    },
                )
                # Return minimal data
                result["score_data"] = {
                    "match_id": match_data.get("metadata", {}).get("matchId", "unknown"),
                    "summoner_name": "Unknown",
                    "champion_name": "Unknown",
                    "match_result": "defeat",
                    "detected_mode": detect_game_mode(queue_id).model_dump(),
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "total_damage_dealt": 0,
                    "gold_earned": 0,
                    "fallback_message": "该游戏模式的专业分析功能正在开发中。",
                    "generic_summary": None,
                    "algorithm_version": "v2.3-fallback",
                }
                return result

            # Step 3: Extract basic stats from participant data
            kills = target_participant.get("kills", 0)
            deaths = target_participant.get("deaths", 0)
            assists = target_participant.get("assists", 0)
            total_damage_dealt = target_participant.get("totalDamageDealtToChampions", 0)
            gold_earned = target_participant.get("goldEarned", 0)
            summoner_name = target_participant.get("summonerName", "Unknown")
            champion_name = target_participant.get("championName", "Unknown")
            win = target_participant.get("win", False)
            match_result = "victory" if win else "defeat"

            # Step 4: Detect game mode
            game_mode = detect_game_mode(queue_id)

            # Step 5: Generate optional generic summary
            generic_summary = self._generate_generic_summary(
                champion_name=champion_name,
                kills=kills,
                deaths=deaths,
                assists=assists,
                match_result=match_result,
            )

            # Step 6: Build fallback report
            fallback_report = V23FallbackAnalysisReport(
                match_id=match_data.get("metadata", {}).get("matchId", "unknown"),
                summoner_name=summoner_name,
                champion_name=champion_name,
                match_result=match_result,
                detected_mode=game_mode,
                kills=kills,
                deaths=deaths,
                assists=assists,
                total_damage_dealt=total_damage_dealt,
                gold_earned=gold_earned,
                generic_summary=generic_summary,
            )

            result["score_data"] = fallback_report.model_dump(mode="json")

            logger.info(
                "fallback_analysis_completed",
                extra={
                    "match_id": fallback_report.match_id,
                    "queue_id": queue_id,
                    "detected_mode": game_mode.mode,
                    "queue_name": game_mode.queue_name,
                },
            )

        except Exception as e:
            # Execution error - return minimal data
            logger.error(
                "fallback_analysis_failed",
                extra={
                    "error": str(e),
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                },
            )
            result["score_data"] = {
                "match_id": match_data.get("metadata", {}).get("matchId", "unknown"),
                "summoner_name": "Unknown",
                "champion_name": "Unknown",
                "match_result": "defeat",
                "detected_mode": detect_game_mode(0).model_dump(),  # Default fallback mode
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "total_damage_dealt": 0,
                "gold_earned": 0,
                "fallback_message": "数据处理失败，请稍后重试。",
                "generic_summary": None,
                "algorithm_version": "v2.3-fallback",
            }

        return result

    def _generate_generic_summary(
        self,
        champion_name: str,
        kills: int,
        deaths: int,
        assists: int,
        match_result: str,
    ) -> str:
        """Generate simple generic summary without LLM call.

        Args:
            champion_name: Champion played
            kills: Kill count
            deaths: Death count
            assists: Assist count
            match_result: "victory" or "defeat"

        Returns:
            Simple generic summary in Chinese
        """
        result_text = "获得了胜利" if match_result == "victory" else "遗憾落败"
        kda_ratio = (kills + assists) / max(deaths, 1)

        summary = (
            f"本场比赛你使用 {champion_name}，取得了 {kills}/{deaths}/{assists} 的战绩，{result_text}。"
            f"KDA比率为 {kda_ratio:.2f}。"
        )

        # Add simple evaluation based on KDA
        if kda_ratio >= 3.0:
            summary += "你的战斗表现非常优秀。"
        elif kda_ratio >= 2.0:
            summary += "你的战斗表现良好。"
        elif kda_ratio >= 1.0:
            summary += "你的战斗表现中规中矩。"
        else:
            summary += "建议在下一场比赛中注意生存和团队配合。"

        return summary
