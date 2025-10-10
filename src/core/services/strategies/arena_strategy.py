"""Arena Analysis Strategy — V1-Lite (V2.5 Delivery).

Implements CLI 4's Arena V1-Lite algorithm with strict Riot policy compliance.

Compliance (P0):
- MUST NOT output Augment/Item win rates or predictive guidance
- Degrade to FallbackStrategy if LLM text violates compliance guard
"""

from __future__ import annotations

import json
import logging
from typing import Any


from src.adapters.gemini_llm import GeminiLLMAdapter
from src.contracts.v23_multi_mode_analysis import (
    AnalysisStrategy,
    V23ArenaAnalysisReport,
)
from src.core.compliance import check_arena_text_compliance, ComplianceError
from src.core.scoring.arena_v1_lite import generate_arena_analysis_report
from src.core.services.strategies.fallback_strategy import FallbackStrategy

logger = logging.getLogger(__name__)


class ArenaStrategy(AnalysisStrategy):
    def __init__(self) -> None:
        self._fallback = FallbackStrategy()

    def get_mode_label(self) -> str:
        return "arena"

    async def execute_analysis(
        self,
        match_data: dict[str, Any],
        timeline_data: dict[str, Any],
        requester_puuid: str,
        discord_user_id: str,
        user_profile_context: str | None = None,
        timeline_evidence: Any | None = None,
    ) -> dict[str, Any]:
        """Execute Arena V1-Lite with compliance guard + strict validation."""
        result: dict[str, Any] = {
            "metrics": {
                "v2_degraded": False,
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
            # 1) Numeric analysis (no LLM)
            participants = match_data.get("info", {}).get("participants", [])
            summoner_name = next(
                (
                    p.get("summonerName", "Unknown")
                    for p in participants
                    if p.get("puuid") == requester_puuid
                ),
                "Unknown",
            )
            base_report = generate_arena_analysis_report(
                match_data=match_data,
                timeline_data=timeline_data,
                player_puuid=requester_puuid,
                summoner_name=summoner_name,
            )

            # 2) LLM JSON
            from pathlib import Path

            prompt_path = Path(__file__).resolve().parents[3] / "prompts" / "v23_arena_analysis.txt"
            system_prompt = prompt_path.read_text(encoding="utf-8")

            rounds_json = [r.model_dump(mode="json") for r in base_report.round_performances]
            user_prompt = (
                f"召唤师: {base_report.summoner_name}\n"
                f"英雄: {base_report.champion_name}\n"
                f"最终排名: {base_report.final_placement}\n"
                f"综合评分: {base_report.overall_score}\n"
                f"回合数/获胜: {base_report.rounds_played}/{base_report.rounds_won}\n"
                "\n[回合表现]\n"
                f"{json.dumps(rounds_json, ensure_ascii=False, indent=2)}\n"
                "\n[增强符文分析]\n"
                f"{base_report.augment_analysis.model_dump_json(exclude_none=True, indent=2)}\n"
                "\n[维度评分]\n"
                f"战斗: {base_report.combat_score}\n双人协同: {base_report.duo_synergy_score}\n"
                "\n(请输出严格的 JSON 格式，且不得包含任何胜率/预测性描述)\n"
            )

            llm = GeminiLLMAdapter()
            llm_json = await llm.analyze_match(
                match_data={
                    "prompt": user_prompt,
                    "match_id": match_data.get("metadata", {}).get("matchId", "unknown"),
                },
                system_prompt=system_prompt,
                game_mode=self.get_mode_label(),
            )

            try:
                payload = json.loads(llm_json)
            except json.JSONDecodeError as e:  # pragma: no cover - defensive
                raise ValueError(f"LLM returned invalid JSON: {e}")

            # 3) Hallucination detection (detect LLM claiming data is missing)
            analysis_summary = payload.get("analysis_summary", "")
            hallucination_patterns = [
                "数据缺失",
                "数据为空",
                "数据异常",
                "无法生成有效分析",
                "无法进行有效分析",
                "比赛ID.*是否正确",  # Pattern: asking user to verify match ID
                "检查API数据源",
                "稍后重试获取",
            ]
            if any(pattern in analysis_summary for pattern in hallucination_patterns):
                logger.warning(
                    "arena_hallucination_detected_degrading",
                    extra={
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                        "analysis_summary_preview": analysis_summary[:200],
                        "rounds_played": base_report.rounds_played,
                        "rounds_won": base_report.rounds_won,
                    },
                )
                # Data exists (we have base_report with rounds), but LLM hallucinated error
                # Degrade to fallback to avoid misleading users
                result["metrics"].update(
                    {"v2_degraded": True, "degradation_reason": "arena_hallucination"}
                )
                fallback = await self._fallback.execute_analysis(
                    match_data=match_data,
                    timeline_data=timeline_data,
                    requester_puuid=requester_puuid,
                    discord_user_id=discord_user_id,
                    user_profile_context=user_profile_context,
                    timeline_evidence=timeline_evidence,
                )
                fallback["mode"] = self.get_mode_label()
                return fallback

            # 4) Compliance guard (critical - check for winrate/predictive language)
            try:
                check_arena_text_compliance(analysis_summary)
                for tip in payload.get("improvement_suggestions", []) or []:
                    check_arena_text_compliance(tip)
            except ComplianceError as ce:
                # Degrade to fallback on policy violation
                logger.warning(
                    "arena_compliance_violation_degrading",
                    extra={
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                        "error": str(ce),
                    },
                )
                result["metrics"].update(
                    {"v2_degraded": True, "degradation_reason": "arena_compliance"}
                )
                fallback = await self._fallback.execute_analysis(
                    match_data=match_data,
                    timeline_data=timeline_data,
                    requester_puuid=requester_puuid,
                    discord_user_id=discord_user_id,
                    user_profile_context=user_profile_context,
                    timeline_evidence=timeline_evidence,
                )
                fallback["mode"] = self.get_mode_label()
                return fallback

            # 5) Strict validation
            merged = base_report.model_dump(mode="json")
            merged.update(
                {
                    "analysis_summary": payload.get("analysis_summary", ""),
                    "improvement_suggestions": payload.get("improvement_suggestions", []),
                }
            )
            validated = V23ArenaAnalysisReport.model_validate(merged)
            result["score_data"] = validated.model_dump(mode="json")

            logger.info(
                "arena_v1_lite_completed",
                extra={
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                    "summoner": base_report.summoner_name,
                },
            )

        except Exception as e:
            logger.error(
                "arena_v1_lite_failed_degrading",
                extra={
                    "error": str(e),
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                },
                exc_info=True,
            )
            result["metrics"].update(
                {"v2_degraded": True, "degradation_reason": "arena_pipeline_error"}
            )
            fallback = await self._fallback.execute_analysis(
                match_data=match_data,
                timeline_data=timeline_data,
                requester_puuid=requester_puuid,
                discord_user_id=discord_user_id,
                user_profile_context=user_profile_context,
                timeline_evidence=timeline_evidence,
            )
            fallback["mode"] = self.get_mode_label()
            return fallback

        return result
