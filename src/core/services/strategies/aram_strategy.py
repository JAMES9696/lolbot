"""ARAM Analysis Strategy — V1-Lite (V2.5 Delivery).

Implements CLI 4's ARAM V1-Lite algorithm under the Strategy Pattern.

KISS/YAGNI:
- Use existing scoring utilities (pure functions) to compute metrics
- Single LLM call with dedicated ARAM prompt (JSON mode)
- Strict Pydantic V2 validation for structured output

Mode Specificity:
- Disable/ignore ARAM-inapplicable dimensions (e.g., Vision, Objective)
- Focus on teamfight efficiency + build adaptation + simplified scores

Outputs:
- V23ARAMAnalysisReport (dict) + metrics + mode label
"""

from __future__ import annotations

import json
import logging
from typing import Any


from src.adapters.gemini_llm import GeminiLLMAdapter
from src.contracts.v23_multi_mode_analysis import (
    AnalysisStrategy,
    V23ARAMAnalysisReport,
)
from src.core.services.strategies.fallback_strategy import FallbackStrategy
from src.core.scoring.aram_v1_lite import generate_aram_analysis_report

logger = logging.getLogger(__name__)


class ARAMStrategy(AnalysisStrategy):
    """ARAM analysis strategy using V1-Lite algorithm + JSON LLM."""

    def __init__(self) -> None:
        self._fallback = FallbackStrategy()

    def get_mode_label(self) -> str:
        return "aram"

    async def execute_analysis(
        self,
        match_data: dict[str, Any],
        timeline_data: dict[str, Any],
        requester_puuid: str,
        discord_user_id: str,
        user_profile_context: str | None = None,
        timeline_evidence: Any | None = None,
    ) -> dict[str, Any]:
        """Execute ARAM V1-Lite pipeline with strict validation.

        Steps:
        1) Compute ARAM metrics via scoring utilities (no LLM)
        2) Call LLM with ARAM prompt (JSON mode) to generate narrative fields
        3) Validate with V23ARAMAnalysisReport and return dict
        4) On any failure, degrade to FallbackStrategy
        """
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
            # 1) Deterministic numeric analysis (no LLM)
            participants = match_data.get("info", {}).get("participants", [])
            summoner_name = next(
                (
                    p.get("summonerName", "Unknown")
                    for p in participants
                    if p.get("puuid") == requester_puuid
                ),
                "Unknown",
            )
            base_report = generate_aram_analysis_report(
                match_data=match_data,
                timeline_data=timeline_data,
                player_puuid=requester_puuid,
                summoner_name=summoner_name,
            )

            # 2) LLM JSON: dedicated ARAM prompt (system) + compact user payload
            # Load prompt text
            from pathlib import Path

            prompt_path = Path(__file__).resolve().parents[3] / "prompts" / "v23_aram_analysis.txt"
            system_prompt = prompt_path.read_text(encoding="utf-8")

            user_prompt = (
                f"召唤师: {base_report.summoner_name}\n"
                f"英雄: {base_report.champion_name}\n"
                f"比赛结果: {base_report.match_result}\n"
                f"综合评分: {base_report.overall_score}\n"
                "\n[团队战斗指标]\n"
                f"{base_report.teamfight_metrics.model_dump_json(exclude_none=True, indent=2)}\n"
                "\n[出装适应性]\n"
                f"{base_report.build_adaptation.model_dump_json(exclude_none=True, indent=2)}\n"
                "\n[维度评分]\n"
                f"战斗: {base_report.combat_score}\n团队协作: {base_report.teamplay_score}\n"
            )

            llm = GeminiLLMAdapter()
            llm_json = await llm.analyze_match_json(
                match_data={
                    "prompt": user_prompt,
                    "match_id": match_data.get("metadata", {}).get("matchId", "unknown"),
                },
                system_prompt=system_prompt,
                game_mode=self.get_mode_label(),
            )

            # 3) Strict JSON validation via Pydantic
            try:
                payload = json.loads(llm_json)
            except json.JSONDecodeError as e:  # pragma: no cover - defensive
                raise ValueError(f"LLM returned invalid JSON: {e}")

            # 4) Hallucination detection (detect LLM claiming data is missing)
            analysis_summary = payload.get("analysis_summary", "")
            hallucination_patterns = [
                "数据缺失",
                "数据为空",
                "数据异常",
                "无法生成有效分析",
                "无法进行有效分析",
                "比赛ID.*是否正确",
                "检查API数据源",
                "稍后重试获取",
            ]
            if any(pattern in analysis_summary for pattern in hallucination_patterns):
                logger.warning(
                    "aram_hallucination_detected_degrading",
                    extra={
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                        "analysis_summary_preview": analysis_summary[:200],
                        "base_data_exists": True,
                    },
                )
                # Data exists (we have base_report), but LLM hallucinated error
                # Raise to trigger degradation to fallback
                raise ValueError(f"ARAM hallucination detected: {analysis_summary[:50]}")

            # 5) Merge LLM narrative fields into base numeric report
            merged = base_report.model_dump(mode="json")
            merged.update(
                {
                    "analysis_summary": payload.get("analysis_summary", ""),
                    "improvement_suggestions": payload.get("improvement_suggestions", []),
                }
            )

            validated = V23ARAMAnalysisReport.model_validate(merged)
            result["score_data"] = validated.model_dump(mode="json")

            # LLM accounting (best-effort; adapter pushes metrics elsewhere)
            # Keep zeros locally to avoid double counting

            logger.info(
                "aram_v1_lite_completed",
                extra={
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                    "summoner": base_report.summoner_name,
                },
            )

        except Exception as e:
            # Degrade to fallback
            logger.error(
                "aram_v1_lite_failed_degrading",
                extra={
                    "error": str(e),
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                },
                exc_info=True,
            )
            result["metrics"].update(
                {"v2_degraded": True, "degradation_reason": "aram_pipeline_error"}
            )
            fallback = await self._fallback.execute_analysis(
                match_data=match_data,
                timeline_data=timeline_data,
                requester_puuid=requester_puuid,
                discord_user_id=discord_user_id,
                user_profile_context=user_profile_context,
                timeline_evidence=timeline_evidence,
            )
            # Ensure mode label sticks to ARAM for downstream rendering decisions
            fallback["mode"] = self.get_mode_label()
            return fallback

        return result
