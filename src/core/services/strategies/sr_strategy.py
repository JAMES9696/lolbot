"""Summoner's Rift Analysis Strategy (V2.3 Multi-Mode Support).

This strategy implements the full V2.2 analysis stack for Summoner's Rift:
- V2.1 Timeline Evidence Extraction (fact-based prescriptive analysis)
- V2.2 Personalization (user profile context injection)
- V2 Team-Relative Analysis with strict JSON validation
- Graceful degradation to V1 template on validation failures

Author: CLI 2 (Backend)
Date: 2025-10-07
Phase: V2.3
"""

import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from src.adapters.gemini_llm import GeminiLLMAdapter
from src.contracts.timeline import MatchTimeline
from src.contracts.v2_team_analysis import V2TeamAnalysisReport
from src.contracts.v2_1_timeline_evidence import V2_1_TimelineEvidence
from src.contracts.v23_multi_mode_analysis import AnalysisStrategy
from src.core.scoring import generate_llm_input
from src.core.services.ab_testing import PromptSelectorService
from src.prompts.v2_team_relative_prompt import V2_TEAM_RELATIVE_SYSTEM_PROMPT
from src.core.metrics import mark_json_validation_error_by_mode

logger = logging.getLogger(__name__)


class SRStrategy(AnalysisStrategy):
    """Summoner's Rift analysis strategy with full V2.2 stack.

    This strategy encapsulates the complete SR analysis pipeline:
    1. V1 scoring for all 10 players (baseline metrics)
    2. V2.1 Timeline evidence extraction (optional, feature-flagged)
    3. V2.2 User profile loading (optional, feature-flagged)
    4. V2 team-relative LLM analysis with compressed prompts
    5. Strict JSON validation with V1 template fallback

    Thread Safety: Each instance is stateless and can be used concurrently.
    """

    def get_mode_label(self) -> str:
        """Get lowercase mode label for metrics and logging.

        Returns:
            "sr" for Summoner's Rift
        """
        return "sr"

    async def execute_analysis(
        self,
        match_data: dict[str, Any],
        timeline_data: dict[str, Any],
        requester_puuid: str,
        discord_user_id: str,
        user_profile_context: str | None = None,
        timeline_evidence: V2_1_TimelineEvidence | None = None,
    ) -> dict[str, Any]:
        """Execute full V2.2 Summoner's Rift analysis pipeline.

        Args:
            match_data: Raw Match-V5 match details
            timeline_data: Raw Match-V5 timeline data
            requester_puuid: PUUID of user who requested analysis
            discord_user_id: Discord user ID (for personalization)
            user_profile_context: V2.2 personalization context (optional)
            timeline_evidence: V2.1 Timeline evidence (optional)

        Returns:
            Dict with keys:
                - score_data: Analysis results (dict from V2TeamAnalysisReport or V1 fallback)
                - metrics: LLM metrics (tokens, latency, cost, degraded)
                - mode: "sr"

        Raises:
            Exception: Logged and handled gracefully (returns V1 fallback)
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
            # Step 1: Calculate V1 scores for all 10 players (baseline)
            timeline_model = MatchTimeline(**timeline_data)
            analysis_output = generate_llm_input(timeline_model)

            # Step 2: Identify requester's participant index (0-9)
            participants = match_data.get("info", {}).get("participants", [])

            # Early exit: Match Details unavailable (API failure or rate limit)
            if not participants:
                logger.warning(
                    "sr_match_details_unavailable_degrading_to_v1",
                    extra={
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                        "reason": "participants_empty",
                    },
                )
                result["metrics"].update(
                    {
                        "v2_degraded": True,
                        "degradation_reason": "match_details_unavailable",
                    }
                )
                result["score_data"] = generate_llm_input(
                    timeline_model,
                    match_details=match_data,
                ).model_dump(mode="json")
                return result

            target_player_index = next(
                (i for i, p in enumerate(participants) if p.get("puuid") == requester_puuid),
                0,
            )

            # Step 3: Convert PlayerScore models to dict for team summary calculation
            # Field mapping: combat_efficiency -> combat_score, etc.
            all_players_scores_dict = []
            for player_score in analysis_output.player_scores:
                player_dict = {
                    "combat_score": player_score.combat_efficiency,
                    "economy_score": player_score.economic_management,
                    "vision_score": player_score.vision_control,
                    "objective_score": player_score.objective_control,
                    "teamplay_score": player_score.team_contribution,
                }
                all_players_scores_dict.append(player_dict)

            # Step 4: Compress team data (saves ~40% tokens)
            team_summary = PromptSelectorService.calculate_team_summary(
                all_players_scores=all_players_scores_dict,
                target_player_index=target_player_index,
            )

            # Step 5: Build V2 system prompt (no variant logic needed in V2.2)
            system_prompt = V2_TEAM_RELATIVE_SYSTEM_PROMPT

            # Step 6: Determine match result for requester
            target_participant = participants[target_player_index]
            win = target_participant.get("win", False)
            match_result = "victory" if win else "defeat"

            # Step 7: Format target player scores for prompt
            target_player_dict = {
                "combat_score": analysis_output.player_scores[
                    target_player_index
                ].combat_efficiency,
                "economy_score": analysis_output.player_scores[
                    target_player_index
                ].economic_management,
                "vision_score": analysis_output.player_scores[target_player_index].vision_control,
                "objective_score": analysis_output.player_scores[
                    target_player_index
                ].objective_control,
                "teamplay_score": analysis_output.player_scores[
                    target_player_index
                ].team_contribution,
            }

            # Step 8: Build timeline evidence section (V2.1 enhancement)
            evidence_section = self._build_evidence_section(timeline_evidence)

            # Step 9: Build user profile section (V2.2 enhancement)
            profile_section = ""
            if user_profile_context:
                profile_section = f"\n{user_profile_context}\n"

            # Step 10: Build user prompt with all context
            user_prompt = f"""请根据以下数据为目标玩家生成一段**团队相对**的中文评价：

**目标玩家数据**:
{json.dumps(target_player_dict, ensure_ascii=False, indent=2)}

**团队统计摘要**:
{team_summary.model_dump_json(indent=2, exclude_none=True)}
{evidence_section}{profile_section}
**比赛结果**: {match_result}

要求：
1. 200字左右的中文叙事
2. 使用团队统计摘要进行对比分析（"你的战斗评分高于队伍平均15%"）
3. 突出相对排名（"在队伍中排名第X"）
4. 提供具体改进建议（对比队友强项）
5. 语气鼓励但客观
6. (V2.1) 如果提供了 Timeline 证据，结合具体事件提供改进建议（例如：视野布置位置、战斗时机选择等）
7. (V2.2) 如果提供了用户画像，结合用户的历史表现和偏好调整分析语气和建议重点
"""

            # Step 11: Call LLM with JSON mode enforced
            llm_adapter = GeminiLLMAdapter()
            llm_start = time.perf_counter()

            llm_response_text = await llm_adapter.analyze_match_json(
                match_data={"prompt": user_prompt},
                system_prompt=system_prompt,
                game_mode=self.get_mode_label(),
            )
            llm_latency = (time.perf_counter() - llm_start) * 1000

            # Token metrics placeholder (logged internally by adapter)
            llm_input_tokens = 0
            llm_output_tokens = 0
            llm_api_cost_usd = 0.0

            # Step 12: Validate JSON (STRICT)
            try:
                parsed = json.loads(llm_response_text)
                validated = V2TeamAnalysisReport.model_validate(parsed)
                result["score_data"] = validated.model_dump(mode="json")
                result["metrics"].update(
                    {
                        "llm_input_tokens": llm_input_tokens,
                        "llm_output_tokens": llm_output_tokens,
                        "llm_api_cost_usd": llm_api_cost_usd,
                        "llm_latency_ms": llm_latency,
                    }
                )
            except (json.JSONDecodeError, ValidationError) as e:
                # JSON validation failed - degrade to V1 template
                logger.error(
                    "sr_v2_validation_failed",
                    extra={
                        "error": str(e),
                        "response_preview": llm_response_text[:200],
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                    },
                )
                result["metrics"].update(
                    {
                        "v2_degraded": True,
                        "degradation_reason": (
                            "json_parse_error"
                            if isinstance(e, json.JSONDecodeError)
                            else "validation_error"
                        ),
                        "llm_input_tokens": llm_input_tokens,
                        "llm_output_tokens": llm_output_tokens,
                        "llm_api_cost_usd": llm_api_cost_usd,
                        "llm_latency_ms": llm_latency,
                    }
                )
                try:
                    mark_json_validation_error_by_mode(
                        "v2_team_analysis",
                        "json_parse_error"
                        if isinstance(e, json.JSONDecodeError)
                        else "validation_error",
                        self.get_mode_label(),
                    )
                except Exception:
                    pass

                # Generate V1 fallback
                # Include Match-V5 details so raw_stats carries accurate vision_score etc.
                result["score_data"] = generate_llm_input(
                    timeline_model,
                    match_details=match_data,
                ).model_dump(mode="json")

        except Exception as e:
            # Execution error - degrade to V1 template
            logger.error(
                "sr_analysis_execution_failed",
                extra={
                    "error": str(e),
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                },
            )
            result["metrics"].update(
                {
                    "v2_degraded": True,
                    "degradation_reason": "execution_error",
                }
            )
            # Generate V1 fallback
            timeline_model = MatchTimeline(**timeline_data)
            # Degrade to V1 but enrich from Match-V5 details for better raw_stats
            result["score_data"] = generate_llm_input(
                timeline_model,
                match_details=match_data,
            ).model_dump(mode="json")

        return result

    def _build_evidence_section(self, timeline_evidence: V2_1_TimelineEvidence | None) -> str:
        """Build timeline evidence section for prompt injection (V2.1 enhancement).

        Args:
            timeline_evidence: V2.1 Timeline evidence or None

        Returns:
            Formatted evidence string or empty string if no evidence
        """
        if not timeline_evidence:
            return ""

        ward_evidence = timeline_evidence.ward_control_evidence
        combat_evidence = timeline_evidence.combat_evidence
        evidence_section = f"""

**Timeline 证据数据 (V2.1)**:
- 视野控制: 放置眼位 {ward_evidence.total_wards_placed} 个（真眼 {ward_evidence.control_wards_placed} 个），排除眼位 {ward_evidence.wards_destroyed} 个
- 战斗表现: {combat_evidence.total_kills} 击杀 / {combat_evidence.total_deaths} 死亡 / {combat_evidence.total_assists} 助攻（单杀 {combat_evidence.solo_kills} 次）
- 提前闪现次数（死亡前5秒内）: {combat_evidence.early_flash_usage_count} 次
"""

        # Include sample ward placements if available
        if ward_evidence.ward_events:
            evidence_section += "- 关键眼位:\n"
            for event in ward_evidence.ward_events[:3]:  # Show max 3 examples
                evidence_section += f"  * {event.timestamp} {event.ward_type} @ {event.position_label or '未知位置'}\n"

        # Include sample kill events if available
        if combat_evidence.kill_events:
            evidence_section += "- 关键战斗:\n"
            for event in combat_evidence.kill_events[:3]:  # Show max 3 examples
                involvement = (
                    "击杀者"
                    if event.killer_id == timeline_evidence.target_participant_id
                    else "被击杀"
                    if event.victim_id == timeline_evidence.target_participant_id
                    else "助攻"
                )
                evidence_section += (
                    f"  * {event.timestamp} {involvement} @ {event.position_label or '未知位置'}"
                )
                if event.abilities_used:
                    evidence_section += f" (使用技能: {', '.join([a.ability_name for a in event.abilities_used[:2]])})"
                evidence_section += "\n"

        return evidence_section

    def _generate_v1_fallback(
        self,
        timeline_model: MatchTimeline,
        requester_puuid: str,
    ) -> dict[str, Any]:
        """Generate V1 template-based narrative as fallback.

        Args:
            timeline_model: Validated timeline model
            requester_puuid: PUUID of requester (unused in V1)

        Returns:
            V1 analysis output as dict
        """
        analysis_output = generate_llm_input(timeline_model)
        return analysis_output.model_dump(mode="json")
