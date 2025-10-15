"""Team (multi-player) data acquisition task for V2.0.

This Celery task upgrades the data pipeline from single-player to
10-player collection for a given match. It fetches:
- Match details (participants, teams)
- Match timeline (per-minute frames + events)

It persists raw data into `match_data` (JSONB) and stores processed
V1 score outputs into `match_analytics` (single row per match, using
existing schema with upsert).

Additional responsibilities (V2.0):
- Structured logging via llm_debug_wrapper for all critical steps
- V2 team-relative analysis with strict JSON validation
- Graceful degradation to V1 on validation failures
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Literal

from celery import Task
from pydantic import ValidationError

from src.adapters.database import DatabaseAdapter
from src.adapters.gemini_llm import GeminiLLMAdapter
from src.adapters.riot_api import RateLimitError, RiotAPIAdapter, RiotAPIError
from src.config.settings import settings
from src.contracts.timeline import MatchTimeline
from src.contracts.v2_1_timeline_evidence import V2_1_TimelineEvidence
from src.contracts.v2_team_analysis import V2TeamAnalysisReport
from src.core.domain.team_policies import (
    should_run_team_full_token,
    tldr_contains_hallucination,
)
from src.core.observability import clear_correlation_id, llm_debug_wrapper, set_correlation_id

# 测试健壮性：在缺少科学计算依赖（如numpy）时，延迟/宽容导入
try:
    from src.core.scoring import generate_llm_input
except Exception:  # pragma: no cover - 测试环境可跳过重计算

    def generate_llm_input(*args, **kwargs):
        raise ImportError("generate_llm_input unavailable (missing optional deps)")


from src.core.metrics import (
    mark_request_outcome,
    observe_request_latency,
)
from src.core.services.ab_testing import PromptSelectorService
from src.core.services.timeline_evidence_extractor import extract_timeline_evidence
from src.core.services.user_profile_service import UserProfileService
from src.prompts.v2_team_relative_prompt import V2_TEAM_RELATIVE_SYSTEM_PROMPT
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _map_game_mode_to_contract(
    mode_str: str,
) -> Literal["summoners_rift", "aram", "arena", "unknown"]:
    """Map game mode string to TeamAnalysisReport contract format.

    Args:
        mode_str: Game mode from detect_game_mode (e.g., "SR", "ARAM", "Arena", "Fallback")

    Returns:
        Contract-compliant mode: "summoners_rift", "aram", "arena", or "unknown"
    """
    mapping: dict[str, Literal["summoners_rift", "aram", "arena", "unknown"]] = {
        "SR": "summoners_rift",
        "ARAM": "aram",
        "Arena": "arena",
        "Fallback": "unknown",
    }
    return mapping.get(mode_str, "unknown")


def _normalize_game_version(raw_version: str | None) -> str | None:
    """Normalize game version string to X.Y.Z format for DDragon.

    Handles various Riot API version formats:
    - "14.10.1.534" -> "14.10.1"
    - "14.10.1_14.10.1.454" -> "14.10.1" (underscore-separated duplicates)
    - "14.10" -> "14.10.1" (missing patch, append .1)
    - None/empty -> None

    Args:
        raw_version: Raw version string from match_details["info"]["gameVersion"]

    Returns:
        Normalized version string (X.Y.Z) or None if invalid
    """
    if not raw_version:
        return None

    version_str = str(raw_version).strip()
    if not version_str:
        return None

    # Handle underscore-separated duplicates (e.g., "14.10.1_14.10.1.454")
    # Take the first segment before underscore
    if "_" in version_str:
        version_str = version_str.split("_")[0]

    # Split by dots and take first 3 components
    parts = version_str.split(".")

    # Ensure at least major.minor (e.g., "14.10")
    if len(parts) < 2:
        return None

    # Normalize to X.Y.Z (append .1 if patch missing)
    if len(parts) == 2:
        return f"{parts[0]}.{parts[1]}.1"

    # Take first 3 components (X.Y.Z)
    return ".".join(parts[:3])


def _champion_icon_url(champion_name: str, game_version: str | None = None) -> str:
    """Resolve champion icon URL via DDragon with dynamic version support.

    Args:
        champion_name: Champion name (e.g., "Qiyana")
        game_version: Optional game version from match_details (e.g., "14.10.1.123").
                      Will be normalized via _normalize_game_version().

    Returns:
        CDN URL for champion icon
    """
    # Prefer game version from match, fallback to env, then DDragon latest
    version = _normalize_game_version(game_version)

    if not version:
        version = os.getenv("DDRAGON_VERSION", "")

    if not version:
        try:
            from src.core.services.team_builds_enricher import DataDragonClient

            dd = DataDragonClient()
            version = dd.get_latest_version()
        except Exception:
            version = "14.23.1"  # Conservative fallback

    safe_name = champion_name or "Unknown"
    return f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{safe_name}.png"


def _resolve_mode_label_by_sources(
    qid: int, raw_gamemode: str | None, participants_len: int | None
) -> str:
    """Resolve canonical mode label using queueId + gameMode + participants.

    Returns one of: "summoners_rift" | "aram" | "arena" | "unknown".
    Prefers agreement between queueId mapping and raw gameMode; applies
    minimal heuristics (participants count) to avoid label drift.
    """
    from src.contracts.v23_multi_mode_analysis import detect_game_mode

    def _map(mode_str: str) -> str:
        return {
            "SR": "summoners_rift",
            "ARAM": "aram",
            "Arena": "arena",
            "Fallback": "unknown",
        }.get(mode_str, "unknown")

    base = _map(detect_game_mode(int(qid or 0)).mode)
    gm_upper = (raw_gamemode or "").upper()
    from_str = {
        "CLASSIC": "summoners_rift",
        "ARAM": "aram",
        "CHERRY": "arena",
    }.get(gm_upper)

    # If both known and disagree, log and prefer string when clearly mapped
    if base != "unknown" and from_str and base != from_str:
        logger.warning(
            "queue_vs_gamemode_disagree",
            extra={"queue_id": qid, "queue_label": base, "gameMode": raw_gamemode},
        )
        resolved = from_str
    elif from_str:
        resolved = from_str
    else:
        resolved = base

    # Heuristics (light): participants count hints
    try:
        n = int(participants_len or 0)
        if resolved == "arena" and n == 10:
            resolved = "summoners_rift"
        # Note: ARAM 也是 10 人，此处不做 n==10→ARAM 的推断，避免误判
    except Exception:
        pass
    return resolved


class AnalyzeTeamTask(Task):
    """Celery task base with lazy adapters (keeps SOLID via DI)."""

    _db_adapter: DatabaseAdapter | None = None
    _riot_adapter: RiotAPIAdapter | None = None

    @property
    def db(self) -> DatabaseAdapter:
        if self._db_adapter is None:
            self._db_adapter = DatabaseAdapter()
        return self._db_adapter

    @property
    def riot(self) -> RiotAPIAdapter:
        if self._riot_adapter is None:
            self._riot_adapter = RiotAPIAdapter()
        return self._riot_adapter


from src.contracts.team_analysis import TeamAggregates, TeamAnalysisReport, TeamPlayerEntry
import contextlib


@celery_app.task(
    bind=True,
    base=AnalyzeTeamTask,
    name="src.tasks.team_tasks.analyze_team_task",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(RateLimitError,),
    retry_backoff=True,
    retry_jitter=True,
)
@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"task_type": "team_analysis", "layer": "celery_task"},
)
def analyze_team_task(
    self: AnalyzeTeamTask,
    *,
    match_id: str,
    puuid: str,
    region: str,
    discord_user_id: str,
    application_id: str,
    interaction_token: str,
    channel_id: str | None = None,
    guild_id: str | None = None,
    match_index: int = 1,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Fetch 10-player data for a match and execute mode-specific analysis.

    V2.4 Production Flow: Uses Strategy Pattern for multi-mode analysis,
    then delivers results to Discord via Webhook (P0 critical fix).

    Async Delivery Mechanism:
    - CLI 1 sends deferred response (type 5) within 3 seconds
    - CLI 2 completes analysis in background (Celery worker)
    - CLI 2 PATCHes original response via Discord Interaction Webhook
    - Guarantees delivery in all scenarios (success/degraded/failed)

    Mode Routing (via AnalysisStrategyFactory):
    - SR (queueId 420/440): Full V2.2 stack (personalization + timeline evidence)
    - ARAM (queueId 450): V1-Lite ARAM-specific analysis
    - Arena (queueId 1700/1710): V1-Lite Arena-specific analysis
    - Fallback (URF/OFA/Nexus Blitz): Basic stats + generic message

    Feature Flags:
    - V2.1 Timeline Evidence: settings.feature_v21_prescriptive_enabled
    - V2.2 Personalization: settings.feature_v22_personalization_enabled

    Args:
        match_id: Target match ID (Match-V5)
        requester_puuid: PUUID of the user who triggered analysis
        region: Platform region (e.g., "na1")
        discord_user_id: User ID for personalization features
        application_id: Discord application ID (for webhook URL)
        interaction_token: Interaction token (15min validity window)
        channel_id: Discord channel ID (optional, for webhook fallback)

    Returns:
        Dict with processing metrics and outcome flags
    """
    started = time.perf_counter()
    metrics: dict[str, Any] = {"success": False, "match_id": match_id}
    # Align parameter naming with payload contract (puuid) while
    # keeping internal variable name requester_puuid for clarity.
    requester_puuid = puuid

    # Bind correlation ID for end-to-end tracing
    try:
        _cid = correlation_id or f"{match_id}:{int(time.time() * 1000) % 100000}"
        set_correlation_id(_cid)
    except Exception:
        pass

    try:
        # Create and bind a dedicated event loop for this task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Connect DB if not connected
        loop.run_until_complete(self.db.connect())

        match_details = loop.run_until_complete(self.riot.get_match_details(match_id, region))
        if not match_details:
            metrics.update({"error_stage": "fetch_match", "error": "match_details_none"})
            return metrics

        timeline = loop.run_until_complete(self.riot.get_match_timeline(match_id, region))
        if not timeline:
            metrics.update({"error_stage": "fetch_timeline", "error": "timeline_none"})
            return metrics

        # Persist raw match + timeline
        loop.run_until_complete(self.db.save_match_data(match_id, match_details, timeline))

        # ===== V2.3 Game Mode Detection & Strategy Selection =====
        # Detect game mode for by-mode monitoring and strategy routing
        try:
            from src.contracts.v23_multi_mode_analysis import detect_game_mode
            from src.core.services.analysis_strategy_factory import (
                AnalysisStrategyFactory,
            )

            q_info = match_details.get("info", {}) or {}
            qid = int(q_info.get("queueId", 0) or 0)
            raw_gamemode = q_info.get("gameMode") or q_info.get("game_mode") or ""
            participants_len = len(q_info.get("participants", []) or [])

            # Early unification using both sources
            resolved_label = _resolve_mode_label_by_sources(qid, raw_gamemode, participants_len)
            metrics["game_mode"] = resolved_label

            # Get appropriate strategy with factory double-guard (queueId + gameMode + participants)
            factory = AnalysisStrategyFactory()
            strategy = factory.get_strategy_safeguarded(
                detect_game_mode(qid),
                raw_gamemode=raw_gamemode,
                participants_len=participants_len,
            )

            logger.info(
                "v2.3_strategy_selected",
                extra={
                    "match_id": match_id,
                    "queue_id": qid,
                    "raw_game_mode": raw_gamemode,
                    "participants": participants_len,
                    "detected_mode": _map_game_mode_to_contract(detect_game_mode(qid).mode),
                    "resolved_label": resolved_label,
                    "strategy": strategy.__class__.__name__,
                },
            )
        except Exception as e:
            logger.warning(
                "v2.3_strategy_selection_failed",
                extra={"match_id": match_id, "error": str(e)},
            )
            metrics["game_mode"] = "unknown"
            # Fallback to legacy flow if strategy selection fails
            from src.core.services.strategies.fallback_strategy import FallbackStrategy

            strategy = FallbackStrategy()

        # ===== V2.1 Timeline Evidence Extraction (feature-flagged) =====
        timeline_evidence: V2_1_TimelineEvidence | None = None
        if settings.feature_v21_prescriptive_enabled:
            try:
                # Determine target participant ID (1-10 in Riot API)
                participants = match_details.get("info", {}).get("participants", [])
                target_participant = next(
                    (p for p in participants if p.get("puuid") == requester_puuid), None
                )
                if target_participant:
                    target_participant_id = target_participant.get("participantId", 0)
                    if target_participant_id > 0:
                        timeline_evidence = extract_timeline_evidence(
                            timeline_data=timeline,
                            target_participant_id=target_participant_id,
                            match_id=match_id,
                        )
                        logger.info(
                            "v2.1_evidence_extracted",
                            extra={
                                "match_id": match_id,
                                "participant_id": target_participant_id,
                                "wards_placed": timeline_evidence.ward_control_evidence.total_wards_placed,
                                "total_kills": timeline_evidence.combat_evidence.total_kills,
                                "solo_kills": timeline_evidence.combat_evidence.solo_kills,
                            },
                        )
            except Exception as e:
                logger.warning(
                    "v2.1_evidence_extraction_failed",
                    extra={"match_id": match_id, "error": str(e)},
                )
                # Continue without evidence (graceful degradation)

        # ===== V2.2 User Profile Loading (feature-flagged) =====
        user_profile_context: str | None = None
        if settings.feature_v22_personalization_enabled:
            try:
                profile_service = UserProfileService(db_adapter=self.db)
                user_profile = loop.run_until_complete(
                    profile_service.get_or_create_profile(
                        discord_user_id=discord_user_id,
                        puuid=requester_puuid,
                    )
                )
                # Generate simple user context for V2 prompt injection
                user_profile_context = _generate_user_profile_context(user_profile)
                logger.info(
                    "v2.2_profile_loaded",
                    extra={
                        "discord_user_id": discord_user_id,
                        "total_matches": user_profile.total_matches_analyzed,
                        "has_trends": bool(user_profile.performance_trends),
                    },
                )
            except Exception as e:
                logger.warning(
                    "v2.2_profile_loading_failed",
                    extra={"discord_user_id": discord_user_id, "error": str(e)},
                )
                # Continue without personalization (graceful degradation)

        # ===== V2.3 Strategy-Based Analysis (Multi-Mode Support) =====
        # Execute mode-specific analysis using Strategy Pattern
        strategy_result = loop.run_until_complete(
            strategy.execute_analysis(
                match_data=match_details,
                timeline_data=timeline,
                requester_puuid=requester_puuid,
                discord_user_id=discord_user_id,
                user_profile_context=user_profile_context,
                timeline_evidence=timeline_evidence,
            )
        )
        metrics.update(strategy_result["metrics"])

        # Upsert processed score_data as one JSONB blob per match
        loop.run_until_complete(
            self.db.save_analysis_result(
                match_id=match_id,
                puuid=requester_puuid,  # anchor row by requester
                score_data=strategy_result["score_data"],
                region=region,
                status="completed",
                processing_duration_ms=None,
            )
        )

        metrics["participants"] = len(match_details.get("info", {}).get("participants", []))
        metrics["success"] = True

        # ===== V2.4 P0 Fix: Webhook Delivery =====
        # Deliver TEAM overview as the main message (distinct from single-player view)
        try:
            from src.adapters.discord_webhook import DiscordWebhookAdapter

            # Build TeamAnalysisReport for TEAM-first UI
            team_report = asyncio.get_event_loop().run_until_complete(
                _build_team_overview_report(
                    match_details=match_details,
                    timeline_data=timeline,
                    requester_puuid=requester_puuid,
                    region=region,
                    resolved_game_mode=metrics.get("game_mode"),
                    arena_score_data=(
                        strategy_result.get("score_data")
                        if metrics.get("game_mode") == "arena"
                        else None
                    ),
                    workflow_metrics=metrics,
                )
            )
            # Attach Celery task id for observability (footer trace)
            with contextlib.suppress(Exception):
                team_report.trace_task_id = str(getattr(self.request, "id", "") or "")

            # Optional: enrich with full-token TL;DR (no extra message spam)
            # Skip for Arena - Arena有专门的双人分析，不走Team TLDR
            if metrics.get("game_mode") != "arena":
                try:
                    ft = _run_full_token_team_analysis(
                        match_details=match_details,
                        timeline_data=timeline,
                        requester_puuid=requester_puuid,
                    )
                    # Prefer TL;DR when available; otherwise fall back to compressed narrative
                    summary = (ft.get("tldr") or ft.get("ai_narrative_text") or "").strip()
                    if summary:
                        # Trim to discord-safe size for a field
                        summary = summary[:600]
                        team_report.summary_text = summary

                        # Generate TTS-optimized summary if voice features enabled (非Arena)
                        tts_summary = None
                        if (
                            settings.feature_voice_enabled
                            and metrics.get("game_mode") != "arena"
                            and len(summary) > 300
                        ):
                            try:
                                from src.adapters.gemini_llm import GeminiLLMAdapter

                                llm_for_tts = GeminiLLMAdapter()
                                tts_summary = loop.run_until_complete(
                                    _generate_team_tts_summary(llm_for_tts, summary)
                                )
                                logger.info(
                                    "team_tts_summary_generated_for_storage",
                                    extra={
                                        "original_len": len(summary),
                                        "tts_len": len(tts_summary),
                                    },
                                )
                            except Exception as tts_err:
                                logger.warning(
                                    "team_tts_summary_generation_failed",
                                    extra={"error": str(tts_err)},
                                )
                                # Fallback: use original summary
                                tts_summary = summary

                        # Persist TL;DR and TTS summary for voice playback reuse
                        try:
                            metadata = {
                                "emotion": "平淡",
                                "source": "team_tldr",
                                "team_summary_text": summary,
                            }
                            if tts_summary:
                                metadata["team_tts_summary"] = tts_summary
                                metadata["team_tts_source"] = "llm"

                            existing_record = loop.run_until_complete(
                                self.db.get_analysis_result(match_id)
                            )
                            existing_meta: dict[str, Any] = {}
                            existing_narrative = summary
                            if existing_record:
                                existing_meta_raw = existing_record.get("llm_metadata")
                                if isinstance(existing_meta_raw, str):
                                    try:
                                        existing_meta = json.loads(existing_meta_raw)
                                    except Exception:
                                        existing_meta = {}
                                elif isinstance(existing_meta_raw, dict):
                                    existing_meta = existing_meta_raw
                                existing_narrative = (
                                    existing_record.get("llm_narrative") or existing_narrative
                                )

                            merged_meta = {**existing_meta, **metadata}

                            loop.run_until_complete(
                                self.db.update_llm_narrative(
                                    match_id=match_id,
                                    llm_narrative=existing_narrative,
                                    llm_metadata=merged_meta,
                                )
                            )
                        except Exception:
                            pass
                except Exception as _e_ft:
                    logger.warning("full_token_summary_failed", extra={"error": str(_e_ft)})
            else:
                logger.info(
                    "team_full_token_skipped",
                    extra={"reason": "arena_mode", "game_mode": metrics.get("game_mode")},
                )
                # Fallback: Generate basic summary from timeline when Match Details unavailable
                if team_report.game_mode == "summoners_rift":
                    try:
                        t_info = timeline.get("info", {}) or {}
                        frames = t_info.get("frames", []) or []
                        duration_min = 0.0
                        if len(frames) >= 2:
                            first_ts = int(frames[0].get("timestamp", 0) or 0)
                            last_ts = int(frames[-1].get("timestamp", 0) or 0)
                            duration_s = (last_ts - first_ts) / 1000.0
                            if duration_s <= 0:
                                # Some payloads have identical timestamps; fall back to frame interval * (n-1)
                                interval_ms = int(
                                    t_info.get("frame_interval") or t_info.get("frameInterval") or 0
                                )
                                if interval_ms > 0:
                                    duration_s = (interval_ms / 1000.0) * max(0, len(frames) - 1)
                            duration_s = max(0.0, duration_s)
                            duration_min = round(duration_s / 60.0, 1)

                        win_text = "胜利" if team_report.team_result == "victory" else "失败"
                        fallback_summary = f"本局{win_text}，比赛时长 {duration_min} 分钟。数据加载受限，仅显示基础评分。"
                        team_report.summary_text = fallback_summary
                        logger.info(
                            "fallback_summary_generated", extra={"duration_min": duration_min}
                        )
                    except Exception:
                        pass

            # If feature flag is OFF or TL;DR empty, ensure a minimal summary exists
            if (
                not getattr(team_report, "summary_text", None)
                and team_report.game_mode == "summoners_rift"
            ):
                try:
                    t_info = timeline.get("info", {}) or {}
                    frames = t_info.get("frames", []) or []
                    duration_min = 0.0
                    if len(frames) >= 2:
                        first_ts = int(frames[0].get("timestamp", 0) or 0)
                        last_ts = int(frames[-1].get("timestamp", 0) or 0)
                        duration_s = (last_ts - first_ts) / 1000.0
                        if duration_s <= 0:
                            interval_ms = int(
                                t_info.get("frame_interval") or t_info.get("frameInterval") or 0
                            )
                            if interval_ms > 0:
                                duration_s = (interval_ms / 1000.0) * max(0, len(frames) - 1)
                        duration_s = max(0.0, duration_s)
                        duration_min = round(duration_s / 60.0, 1)
                    win_text = "胜利" if team_report.team_result == "victory" else "失败"
                    team_report.summary_text = f"本局{win_text}，比赛时长 {duration_min} 分钟。数据加载受限，仅显示基础评分。"
                    logger.info(
                        "fallback_summary_generated",
                        extra={
                            "duration_min": duration_min,
                            "reason": "empty_summary",
                        },
                    )
                except Exception:
                    pass

            # Append Top-1 teamfight path into summary (SR only, lightweight)
            try:
                from src.core.services.teamfight_reconstructor import extract_teamfight_summaries

                # Use raw Riot timeline/detail
                if team_report.game_mode == "summoners_rift":
                    tf_lines = extract_teamfight_summaries(timeline, match_details)
                    if tf_lines:
                        tf_line = f"• 团战: {tf_lines[0]}"
                        if getattr(team_report, "summary_text", None):
                            merged = f"{team_report.summary_text}\n{tf_line}"
                            team_report.summary_text = merged[:600]
                        else:
                            team_report.summary_text = tf_line
            except Exception:
                pass

            webhook_adapter = DiscordWebhookAdapter()
            webhook_success = loop.run_until_complete(
                webhook_adapter.publish_team_overview(
                    application_id=application_id,
                    interaction_token=interaction_token,
                    team_report=team_report,
                    channel_id=channel_id,
                )
            )
            loop.run_until_complete(webhook_adapter.close())

            metrics["webhook_delivered"] = webhook_success
            logger.info(
                "webhook_delivery_success",
                extra={
                    "match_id": match_id,
                    "mode": strategy_result.get("mode", "unknown"),
                },
            )

        except Exception as webhook_error:
            # Webhook delivery failure should NOT fail the task
            # (analysis completed successfully, only delivery failed)
            logger.error(
                "webhook_delivery_failed",
                extra={
                    "match_id": match_id,
                    "error": str(webhook_error),
                },
                exc_info=True,
            )
            metrics["webhook_delivered"] = False
            metrics["webhook_error"] = str(webhook_error)

        # Optional: auto TTS playback of team TL;DR to user's voice channel
        # NOTE: The broadcast endpoint (src/api/rso_callback.py:_broadcast_match_tts) should:
        #   1. Fetch llm_metadata from database
        #   2. Use metadata["tts_summary"] if available (200-300 chars, TTS-optimized)
        #   3. Fallback to llm_narrative if tts_summary not present
        #   4. This prevents Volcengine TTS timeout on long texts (600+ chars)
        try:
            if (
                settings.feature_voice_enabled
                and settings.feature_team_auto_tts_enabled
                and guild_id
            ):
                from aiohttp import ClientSession

                server = getattr(settings, "broadcast_server_url", "http://localhost:8080").rstrip(
                    "/"
                )
                url = f"{server}/broadcast"
                headers = {"Content-Type": "application/json"}
                if settings.broadcast_webhook_secret:
                    headers["X-Auth-Token"] = settings.broadcast_webhook_secret
                payload = {
                    "match_id": match_id,
                    "guild_id": int(guild_id),
                    "user_id": int(discord_user_id),
                }

                async def _post():
                    async with ClientSession() as sess:
                        async with sess.post(url, json=payload, headers=headers) as resp:
                            _ = await resp.text()
                            return resp.status

                status = loop.run_until_complete(_post())
                # Log http_status inside message for environments that don't render `extra` fields.
                logger.info(
                    f"team_auto_tts_triggered http_status={status}",
                    extra={"guild_id": guild_id, "user_id": discord_user_id, "http_status": status},
                )
        except Exception as e:
            logger.warning("team_auto_tts_failed", extra={"error": str(e)})

        # Mark success and latency SLI
        mark_request_outcome("team_analyze", "success")
        # Compute duration now to avoid KeyError before finally{} writes it
        _dur_ms = (time.perf_counter() - started) * 1000
        metrics["duration_ms"] = _dur_ms
        observe_request_latency("team_analyze", _dur_ms / 1000.0)
        return metrics

    except RateLimitError as e:
        metrics.update({"error_stage": "rate_limit", "retry_after": e.retry_after})
        # Do NOT send webhook for rate limit (task will auto-retry)
        raise  # trigger Celery auto-retry
    except RiotAPIError as e:
        metrics.update({"error_stage": "riot_api", "error": str(e)})
        mark_request_outcome("team_analyze", "failed")

        # Send error webhook for Riot API failures
        _send_error_webhook(
            loop=loop,
            application_id=application_id,
            interaction_token=interaction_token,
            match_id=match_id,
            error_type="RIOT_API_ERROR",
            error_message=f"Riot API 错误：{str(e)}。请稍后重试。",
            channel_id=channel_id,
        )
        return metrics
    except Exception as e:
        metrics.update({"error_stage": "unknown", "error": str(e)})
        mark_request_outcome("team_analyze", "failed")

        # Send error webhook for unknown failures
        _send_error_webhook(
            loop=loop,
            application_id=application_id,
            interaction_token=interaction_token,
            match_id=match_id,
            error_type="INTERNAL_ERROR",
            error_message="分析任务执行失败��请联系管理员或稍后重试。",
            channel_id=channel_id,
        )
        return metrics
    finally:
        # Clear correlation ID from context
        with contextlib.suppress(Exception):
            clear_correlation_id()

        # Preserve earlier computed duration if present; otherwise compute now
        if "duration_ms" not in metrics:
            metrics["duration_ms"] = (time.perf_counter() - started) * 1000
        # Ensure network sessions are closed and loop cleaned up to avoid cross-loop reuse
        with contextlib.suppress(Exception):
            loop.run_until_complete(self.riot.close())
        with contextlib.suppress(Exception):
            loop.run_until_complete(self.db.disconnect())
        with contextlib.suppress(Exception):
            loop.close()

    # Full-token Team analysis switch (analyzes full 10-player + timeline context)
    import os as _os

    if should_run_team_full_token(metrics.get("game_mode"), _os.getenv("TEAM_FULL_TOKEN_MODE", "")):
        try:
            _run_full_token_team_analysis(
                match_details=match_details,
                timeline_data=timeline,
                requester_puuid=requester_puuid,
            )
            # Build TeamOverview for delivery (TEAM-first)
            team_report = loop.run_until_complete(
                _build_team_overview_report(
                    match_details=match_details,
                    timeline_data=timeline,
                    requester_puuid=requester_puuid,
                    region=region,
                    workflow_metrics=metrics,
                )
            )
            webhook_adapter = DiscordWebhookAdapter()
            webhook_success = loop.run_until_complete(
                webhook_adapter.publish_team_overview(
                    application_id=application_id,
                    interaction_token=interaction_token,
                    team_report=team_report,
                    channel_id=channel_id,
                )
            )
            loop.run_until_complete(webhook_adapter.close())
            metrics["webhook_delivered"] = webhook_success
            mark_request_outcome("team_analyze", "success")
            # compute duration immediately to avoid missing metrics
            _dur_ms = (time.perf_counter() - started) * 1000
            metrics["duration_ms"] = _dur_ms
            observe_request_latency("team_analyze", _dur_ms / 1000.0)
            return metrics
        except Exception as e:
            logger.error("full_token_team_analysis_failed", extra={"error": str(e)}, exc_info=True)
    else:
        logger.info(
            "team_full_token_switch_skipped",
            extra={"reason": "arena_mode", "game_mode": metrics.get("game_mode")},
        )


def _generate_user_profile_context(profile: Any) -> str:
    """Generate user profile context string for V2 prompt injection.

    Args:
        profile: V22UserProfile instance

    Returns:
        Formatted user context string in Chinese
    """
    from src.contracts.v22_user_profile import V22UserProfile

    if not isinstance(profile, V22UserProfile):
        return ""

    context_parts = []

    # Role information
    role = profile.preferences.preferred_role or profile.champion_profile.inferred_primary_role
    if role and role != "Fill":
        context_parts.append(f"该用户主要游玩 {role} 位置")

    # Persistent weakness (most important for personalization)
    if profile.performance_trends and profile.performance_trends.persistent_weak_dimension:
        weak_dim = profile.performance_trends.persistent_weak_dimension
        frequency_pct = int((profile.performance_trends.weak_dimension_frequency or 0) * 100)
        context_parts.append(
            f"在最近的比赛中，{weak_dim} 维度表现持续偏���（{frequency_pct}% 的比赛低于队伍平均），建议重点关注此维度的改进建议"
        )

    # Tone preference
    if profile.preferences.preferred_analysis_tone == "competitive":
        context_parts.append("该用户偏好竞技风格的分析（简洁、数据导向、直接批评）")
    else:
        context_parts.append("该用户偏好休闲风格的分析（友好、解释性、鼓励为主）")

    if not context_parts:
        return ""

    return "**用户画像（个性化上下文）**: " + "。".join(context_parts) + "。"


async def _execute_v2_analysis(
    self: AnalyzeTeamTask,
    match_data: dict[str, Any],
    timeline_model: MatchTimeline,
    requester_puuid: str,
    timeline_evidence: V2_1_TimelineEvidence | None = None,
    user_profile_context: str | None = None,
) -> dict[str, Any]:
    """Execute V2 team-relative analysis with JSON validation.

    V2.2 Production Flow: Uses V2_TEAM_RELATIVE_SYSTEM_PROMPT directly,
    no variant selection logic needed.

    V2.1 Enhancement: When timeline_evidence is provided, injects fact-based
    evidence into the prompt for instructional analysis.

    V2.2 Enhancement: When user_profile_context is provided, injects personalized
    user context for tone and suggestion customization.

    Returns:
        Dict with keys: success, report (V2TeamAnalysisReport | None),
        degraded (bool), degradation_reason (str | None),
        llm_metrics (token counts, latency), score_data (dict)
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
    }

    try:
        # Calculate V1 scores for all players
        analysis_output = generate_llm_input(timeline_model)

        # Identify requester's index in participants
        participants = match_data.get("info", {}).get("participants", [])
        target_player_index = next(
            (i for i, p in enumerate(participants) if p.get("puuid") == requester_puuid), 0
        )

        # Convert PlayerScore models to dict format expected by calculate_team_summary
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

        # Compress team data (saves ~40% tokens)
        team_summary = PromptSelectorService.calculate_team_summary(
            all_players_scores=all_players_scores_dict,
            target_player_index=target_player_index,
        )

        # Get V2 system prompt
        system_prompt = V2_TEAM_RELATIVE_SYSTEM_PROMPT

        # Determine match result for requester
        target_participant = participants[target_player_index]
        win = target_participant.get("win", False)
        match_result = "victory" if win else "defeat"

        # Format context with compressed data
        # Convert PlayerScore to dict for prompt formatting
        target_player_dict = {
            "combat_score": analysis_output.player_scores[target_player_index].combat_efficiency,
            "economy_score": analysis_output.player_scores[target_player_index].economic_management,
            "vision_score": analysis_output.player_scores[target_player_index].vision_control,
            "objective_score": analysis_output.player_scores[target_player_index].objective_control,
            "teamplay_score": analysis_output.player_scores[target_player_index].team_contribution,
        }

        # Build timeline evidence section (V2.1 enhancement)
        evidence_section = ""
        if timeline_evidence:
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
                    evidence_section += f"  * {event.timestamp_display} {event.ward_type} @ {event.position_label or '未知位置'}\n"

            # Include sample kill events if available
            if combat_evidence.kill_events:
                evidence_section += "- 关键战斗:\n"
                for kill_event in combat_evidence.kill_events[:3]:  # Show max 3 examples
                    involvement = (
                        "击杀者"
                        if kill_event.killer_participant_id
                        == timeline_evidence.target_player_participant_id
                        else "被击杀"
                        if kill_event.victim_participant_id
                        == timeline_evidence.target_player_participant_id
                        else "助攻"
                    )
                    evidence_section += f"  * {kill_event.timestamp_display} {involvement} @ {kill_event.position_label or '未知位置'}"
                    if kill_event.abilities_used:
                        evidence_section += f" (使用技能: {', '.join([a.ability_type for a in kill_event.abilities_used[:2]])})"
                    evidence_section += "\n"

        # Build user profile section (V2.2 enhancement)
        profile_section = ""
        if user_profile_context:
            profile_section = f"\n{user_profile_context}\n"

        # V2 prompt context (no variant logic needed)
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

        # Call LLM with V2.1 JSON mode (enforced JSON output from source)
        llm_adapter = GeminiLLMAdapter()
        llm_start = time.perf_counter()
        # Derive game_mode label for by-mode FinOps/SRE metrics
        try:
            from src.contracts.v23_multi_mode_analysis import detect_game_mode

            qid = int(match_data.get("info", {}).get("queueId", 0))
            gm = detect_game_mode(qid)
            game_mode_label = gm.mode.lower() if isinstance(gm.mode, str) else "unknown"
        except Exception:
            game_mode_label = "unknown"

        llm_response_text = await llm_adapter.analyze_match_json(
            match_data={"prompt": user_prompt},
            system_prompt=system_prompt,
            game_mode=game_mode_label,
        )
        llm_latency = (time.perf_counter() - llm_start) * 1000

        # Token metrics will be extracted from response metadata in future enhancement
        # For now, use placeholder values (metrics are logged internally by adapter)
        llm_input_tokens = 0
        llm_output_tokens = 0
        llm_api_cost_usd = 0.0

        # Arena compliance guard (text-level pre-check before JSON validation)
        if game_mode_label == "arena":
            try:
                from src.core.compliance import check_arena_text_compliance

                check_arena_text_compliance(llm_response_text)
            except Exception as e:
                logger.error(
                    "arena_compliance_violation",
                    extra={
                        "match_id": match_data.get("metadata", {}).get("matchId"),
                        "error": str(e),
                    },
                )
                raise

        # Validate JSON (STRICT)
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
        except (json.JSONDecodeError, ValidationError, Exception) as e:
            logger.error(
                "v2_validation_failed",
                extra={
                    "error": str(e),
                    "response_preview": llm_response_text[:200],
                    "match_id": match_data.get("metadata", {}).get("matchId"),
                },
            )
            # Degradation - fall back to V1 template
            result["metrics"].update(
                {
                    "v2_degraded": True,
                    "degradation_reason": (
                        "json_parse_error"
                        if isinstance(e, json.JSONDecodeError)
                        else (
                            "validation_error"
                            if isinstance(e, ValidationError)
                            else "arena_compliance_violation"
                        )
                    ),
                    "llm_input_tokens": llm_input_tokens,
                    "llm_output_tokens": llm_output_tokens,
                    "llm_api_cost_usd": llm_api_cost_usd,
                    "llm_latency_ms": llm_latency,
                }
            )
            try:
                from src.core.metrics import mark_json_validation_error_by_mode

                mark_json_validation_error_by_mode(
                    "v2_team_analysis",
                    "json_parse_error"
                    if isinstance(e, json.JSONDecodeError)
                    else (
                        "validation_error"
                        if isinstance(e, ValidationError)
                        else "arena_compliance_violation"
                    ),
                    game_mode_label,
                )
            except Exception:
                pass
            # Generate V1 fallback
            result["score_data"] = _generate_v1_fallback_narrative(
                timeline_model=timeline_model,
                requester_puuid=requester_puuid,
            )

    except Exception as e:
        logger.error(
            "v2_analysis_failed",
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
        result["score_data"] = _generate_v1_fallback_narrative(
            timeline_model=timeline_model,
            requester_puuid=requester_puuid,
        )

    return result


def _generate_v1_fallback_narrative(
    timeline_model: MatchTimeline,
    requester_puuid: str,
) -> dict[str, Any]:
    """Generate V1 template-based narrative as fallback."""
    analysis_output = generate_llm_input(timeline_model)
    return analysis_output.model_dump(mode="json")


def _run_full_token_team_analysis(
    *,
    match_details: dict[str, Any],
    timeline_data: dict[str, Any],
    requester_puuid: str,
) -> dict[str, Any]:
    """Build a full-token team context and ask LLM to generate a team-relative narrative.

    Returns a score_data-like dict with keys compatible to _build_final_analysis_report
    (ai_narrative_text, llm_sentiment_tag optional, team_summary optional), while raw_stats
    will be constructed downstream from match_details.
    """
    from src.adapters.gemini_llm import GeminiLLMAdapter
    from src.core.scoring import generate_llm_input
    from src.core.services.timeline_evidence_extractor import extract_timeline_evidence
    from src.prompts.v2_team_full_token_prompt import TEAM_FULL_TOKEN_SYSTEM_PROMPT

    # Build V1-allplayers scores from timeline
    analysis_output = generate_llm_input(MatchTimeline(**timeline_data))
    analysis_output.model_dump(mode="json")

    # Build per-player compact dict (10 players)
    players: list[dict[str, Any]] = []
    ps_index: dict[int, Any] = {int(ps.participant_id): ps for ps in analysis_output.player_scores}

    parts = match_details.get("info", {}).get("participants", [])

    # Early exit: Match Details unavailable (cannot build full player context)
    if not parts:
        logger.warning(
            "full_token_match_details_unavailable",
            extra={
                "match_id": match_details.get("metadata", {}).get("matchId"),
                "reason": "participants_empty",
            },
        )
        # Return minimal valid structure (will be caught by try/except in caller)
        raise ValueError("Match Details unavailable - participants list is empty")
    for p in parts:
        pid = int(p.get("participantId", 0) or 0)
        ps = ps_index.get(pid)
        if ps is None:
            continue
        players.append(
            {
                "participant_id": pid,
                "team_id": 100 if pid <= 5 else 200,
                "puuid": p.get("puuid"),
                "summoner_name": p.get("riotIdGameName")
                or p.get("summonerName")
                or p.get("gameName"),
                "champion_name": p.get("championName"),
                "role": p.get("teamPosition") or p.get("individualPosition"),
                "total_score": ps.total_score,
                "combat_score": ps.combat_efficiency,
                "economy_score": ps.economic_management,
                "vision_score": ps.vision_control,
                "objective_score": ps.objective_control,
                "teamplay_score": ps.team_contribution,
                "growth_score": getattr(ps, "growth_score", 0.0),
                "tankiness_score": getattr(ps, "tankiness_score", 0.0),
                "damage_composition_score": getattr(ps, "damage_composition_score", 0.0),
                "survivability_score": getattr(ps, "survivability_score", 0.0),
                "cc_contribution_score": getattr(ps, "cc_contribution_score", 0.0),
            }
        )

    def _build_structured_team_tldr_fallback(target_pid: int) -> str:
        """Construct deterministic TLDR when LLM output is invalid."""
        if not players or target_pid <= 0:
            return (
                "强项：团队节奏稳定；短板：视野协同需要补强；建议：临场携带真眼，提前布控关键野区。"
            )

        try:
            target_player = next(p for p in players if p.get("participant_id") == target_pid)
        except StopIteration:
            return (
                "强项：团队节奏稳定；短板：视野协同需要补强；建议：临场携带真眼，提前布控关键野区。"
            )

        team_id = target_player.get("team_id")
        team_players = [p for p in players if p.get("team_id") == team_id] or players[:5]

        dimensions = [
            ("combat_score", "战斗"),
            ("economy_score", "经济"),
            ("vision_score", "视野"),
            ("objective_score", "目标"),
            ("teamplay_score", "团队"),
        ]

        diffs: list[tuple[str, float]] = []
        for key, label in dimensions:
            try:
                average = sum(float(tp.get(key, 0.0) or 0.0) for tp in team_players) / max(
                    1, len(team_players)
                )
                diff = float(target_player.get(key, 0.0) or 0.0) - average
                diffs.append((label, diff))
            except Exception:
                continue

        if not diffs:
            return (
                "强项：团队节奏稳定；短板：视野协同需要补强；建议：临场携带真眼，提前布控关键野区。"
            )

        strength_label, strength_diff = max(diffs, key=lambda item: item[1])
        weakness_label, weakness_diff = min(diffs, key=lambda item: item[1])

        return (
            f"强项：{strength_label}相对队伍平均{strength_diff:+.1f}；"
            f"短板：{weakness_label}相对队伍平均{weakness_diff:+.1f}；"
            "建议：结合语音沟通，提前布控关键资源点。"
        )

    target_part = next((p for p in parts if p.get("puuid") == requester_puuid), None)
    target_pid = int(target_part.get("participantId", 0) or 0) if target_part else 0

    # Team objectives from details
    info = match_details.get("info", {})
    teams = info.get("teams", [])
    objectives = {}
    for t in teams:
        tid = t.get("teamId")
        o = t.get("objectives", {}) or {}
        objectives[tid] = {
            "baron": (o.get("baron", {}) or {}).get("kills", 0),
            "dragon": (o.get("dragon", {}) or {}).get("kills", 0),
            "herald": (o.get("riftHerald", {}) or {}).get("kills", 0),
            "tower": (o.get("tower", {}) or {}).get("kills", 0),
        }

    # Phase summary (early/mid/late by minutes) with robust fallbacks
    duration_s = float(info.get("gameDuration", 0.0) or 0.0)
    # Fallback 1: derive from gameStart/EndTimestamp if present (ms)
    try:
        if duration_s <= 0 and info.get("gameStartTimestamp") and info.get("gameEndTimestamp"):
            duration_s = max(
                0.0,
                (float(info.get("gameEndTimestamp")) - float(info.get("gameStartTimestamp")))
                / 1000.0,
            )
    except Exception:
        pass
    # Fallback 2: use gameDuration from match details info
    if duration_s <= 0:
        with contextlib.suppress(Exception):
            duration_s = float(info.get("gameDuration", 0) or 0)
    # Fallback 3: derive from timeline frame timestamps (works for Arena + SR)
    if duration_s <= 0:
        try:
            t_info = timeline_data.get("info", {}) or {}
            frames = t_info.get("frames", []) or []
            if len(frames) >= 2:
                # Calculate from actual timestamps (Arena doesn't have fixed frameInterval)
                first_ts = frames[0].get("timestamp", 0) or 0
                last_ts = frames[-1].get("timestamp", 0) or 0
                duration_s = max(0.0, (last_ts - first_ts) / 1000.0)
                logger.info(
                    "duration_from_timeline_frames",
                    extra={
                        "frames_count": len(frames),
                        "first_ts": first_ts,
                        "last_ts": last_ts,
                        "duration_s": duration_s,
                    },
                )
            else:
                logger.warning(
                    "timeline_frames_insufficient",
                    extra={"frames_count": len(frames)},
                )
        except Exception as e:
            logger.error(
                "duration_fallback3_failed",
                extra={"error": str(e)},
            )
    duration_min = round(duration_s / 60.0, 1) if duration_s else 0.0
    phase_bounds = {"early": 10.0, "mid": 20.0, "late": duration_min}

    # Stage 1: Full-context narrative
    full_payload = {
        "match_id": str(
            info.get("gameId") or match_details.get("metadata", {}).get("matchId") or "unknown"
        ),
        "duration_min": round(duration_min, 1),
        "players": players,
        "objectives": objectives,
        "phase_minutes": phase_bounds,
    }

    # 延迟导入以避免测试环境缺少 google.generativeai 导致导入失败

    def _build_degraded_narrative(reason: str, tldr_text: str) -> str:
        """构造降级模式下的结构化叙事，保证用户看到可执行的信息。"""

        reason_clean = (reason.strip() or "LLM unavailable")[:160]
        match_id = str(full_payload.get("match_id") or "unknown")
        target_name = (
            (
                target_part.get("riotIdGameName")
                or target_part.get("summonerName")
                or target_part.get("gameName")
                or "-"
            )
            if target_part
            else "-"
        )

        lines = [
            "[降级模式] LLM 链路不可用，已自动生成结构化摘要。",
            f"• 原因: {reason_clean}",
            f"• 比赛ID: {match_id}",
        ]
        if duration_min:
            lines.append(f"• 比赛时长: {duration_min:.1f} 分钟")
        lines.append(f"• 目标召唤师: {target_name}")
        lines.append(f"• TL;DR: {tldr_text}")
        return "\n".join(lines)

    try:
        llm = GeminiLLMAdapter()
        narrative = (
            asyncio.run(llm.analyze_match(full_payload, TEAM_FULL_TOKEN_SYSTEM_PROMPT)) or ""
        )
        narrative = narrative.strip()
        if not narrative:
            logger.error(
                "team_narrative_invalid",
                extra={
                    "match_id": full_payload.get("match_id"),
                    "snippet": narrative[:160],
                    "reason": "empty_narrative",
                },
            )
            raise RuntimeError("LLM returned empty team narrative")

        if tldr_contains_hallucination(narrative):
            logger.error(
                "team_narrative_invalid",
                extra={
                    "match_id": full_payload.get("match_id"),
                    "snippet": narrative[:160],
                    "reason": "hallucination_detected",
                },
            )
            raise RuntimeError("LLM returned invalid team narrative")
        if len(narrative) > 1800:
            narrative = narrative[:1800]
    except Exception as exc:  # noqa: BLE001 - 我们需要将任意异常转换为降级摘要
        fallback_reason = str(exc).strip() or exc.__class__.__name__
        fallback_tldr = _build_structured_team_tldr_fallback(target_pid)
        logger.warning(
            "team_llm_unavailable",
            extra={
                "match_id": full_payload.get("match_id"),
                "error": fallback_reason,
                "duration_min": duration_min,
            },
        )
        degraded_narrative = _build_degraded_narrative(fallback_reason, fallback_tldr)
        return {
            "ai_narrative_text": degraded_narrative,
            "tldr": fallback_tldr,
            "llm_sentiment_tag": "平淡",
            "team_summary": {
                "fallback_reasons": ["llm_unavailable"],
                "llm_error": fallback_reason[:120],
            },
            "algorithm_version": "v2_full_token",
        }

    team_summary_metadata: dict[str, Any] = {}

    # TL;DR (3 lines max) for Team Overview
    try:
        # Contract validation: Prevent LLM hallucination from zero duration
        if duration_min <= 0:
            logger.warning(
                "team_tldr_skipped_invalid_duration",
                extra={
                    "duration_min": duration_min,
                    "match_id": full_payload.get("match_id"),
                },
            )
            raise ValueError(f"Invalid duration for team TLDR: {duration_min}")

        tldr_sys = (
            "你是资深教练。严格用中文输出一段不超过3行的 TL;DR，"
            "只包含：强项TOP1 | 短板TOP1 | 关键建议（动作+对象）。"
            "不要复述背景或解释规则，不要超过3行。"
        )
        tldr_payload = {
            "duration_min": duration_min,
            "players": [
                {
                    "pid": p["participant_id"],
                    "team": p["team_id"],
                    "overall": p["overall_score"],
                    "combat": p["combat_score"],
                    "econ": p["economy_score"],
                    "vision": p["vision_score"],
                    "obj": p["objective_score"],
                    "teamplay": p["teamplay_score"],
                }
                for p in players
            ],
            "target_pid": target_pid,
        }
        logger.info(
            "team_tldr_payload_constructed",
            extra={
                "duration_min": duration_min,
                "players_count": len(tldr_payload["players"]),
                "match_id": full_payload.get("match_id"),
            },
        )

        tldr_text = asyncio.run(llm.analyze_match(tldr_payload, tldr_sys)) or ""
        tldr_text = tldr_text.strip()

        # LLM输出校验：检测幻觉式错误信息（统一使用可测试常量/函数）
        if tldr_contains_hallucination(tldr_text):
            logger.warning(
                "team_tldr_hallucination_detected",
                extra={
                    "tldr_text": tldr_text[:200],
                    "match_id": full_payload.get("match_id"),
                    "duration_min": duration_min,
                },
            )
            # Skip invalid TLDR to avoid misleading users
            raise ValueError(f"Team TLDR hallucination detected: {tldr_text[:50]}")

        if len(tldr_text) > 400:
            tldr_text = tldr_text[:400]

        logger.info(
            "team_tldr_generated_successfully",
            extra={"tldr_length": len(tldr_text), "match_id": full_payload.get("match_id")},
        )
    except Exception as e:
        logger.warning(
            "team_tldr_generation_failed",
            extra={"error": str(e), "match_id": full_payload.get("match_id")},
        )
        tldr_text = _build_structured_team_tldr_fallback(target_pid)
        logger.info(
            "team_tldr_fallback_applied",
            extra={"match_id": full_payload.get("match_id"), "reason": str(e)},
        )
        team_summary_metadata.setdefault("fallback_reasons", []).append("tldr_fallback")

    # Stage 2: Key-events focus (V2.1 evidence → 2-3 行关键片段)
    try:
        evidence = (
            extract_timeline_evidence(timeline_data, target_pid, full_payload["match_id"])
            if target_pid
            else None
        )
        if evidence:
            key_prompt = (
                "请基于以下证据（ward与击杀片段）总结2-3行关键回合/转折点，"
                "只写要点（例如：'14:00 中路被抓：闪现2s前交，建议保留；10-15分连丢2条龙后雪球'）。\n\n证据：\n"
            ) + evidence.model_dump_json(indent=2, exclude_none=True)
            key_lines = asyncio.run(llm.analyze_match({"evidence": True}, key_prompt)) or ""
            narrative = (narrative + "\n\n关键回合：\n" + key_lines)[:1800]
    except Exception:
        pass

    if "fallback_reasons" in team_summary_metadata:
        reasons = team_summary_metadata["fallback_reasons"]
        if isinstance(reasons, list):
            team_summary_metadata["fallback_reasons"] = sorted(set(reasons))

    return {
        "ai_narrative_text": narrative,
        "tldr": tldr_text,
        "llm_sentiment_tag": "平淡",
        "team_summary": team_summary_metadata,
        "algorithm_version": "v2_full_token",
    }


@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "team_tts_summary", "layer": "llm"},
    warn_over_ms=5000,
)
async def _generate_team_tts_summary(
    llm_adapter: GeminiLLMAdapter,
    full_team_tldr: str,
) -> str:
    """Generate TTS-optimized summary from full team TLDR.

    Reduces full team TLDR (up to 600 chars) to 200-300 chars suitable for voice synthesis,
    preventing TTS timeout (Volcengine 15s limit) while preserving key team insights.

    Args:
        llm_adapter: LLM adapter for text summarization
        full_team_tldr: Full team TLDR text (may be up to 600 chars)

    Returns:
        Summarized text (200-300 chars) for TTS, or fallback summary

    Design:
        - Uses LLM to intelligently summarize team TLDR
        - Preserves: team top strength, main weakness, core suggestion
        - Falls back to structured summary if LLM fails
        - Optimized for Chinese TTS voice synthesis

    Reference: Mirrors individual analysis _generate_tts_summary() (src/tasks/analysis_tasks.py:1133-1205)
    """
    try:
        # TTS summary system prompt (Chinese, ultra-concise, team-focused)
        tts_prompt = (
            "你是英雄联盟团队分析语音播报生成器。将以下团队分析压缩为一段200-300字的语音播报文本，"
            "必须包含：团队主要优势、主要劣势、核心战术建议。语气要自然、适合朗读。"
            f"\n\n原始团队分析:\n{full_team_tldr[:800]}"  # Limit input to avoid token overflow
        )

        # Construct minimal payload for LLM
        payload = {
            "match_id": "team_tts_summary",
            "game_duration_minutes": 0,  # Not needed for summarization
            "player_scores": [],  # Not needed
        }

        summary = await llm_adapter.analyze_match(payload, tts_prompt)
        if summary and len(summary) >= 50:  # Validate minimum length
            summary = summary.strip()
            if len(summary) > 350:
                summary = summary[:350]
            logger.info(
                "team_tts_summary_generated",
                extra={"summary_length": len(summary)},
            )
            return summary

        # Fallback: Structured summary
        raise ValueError("LLM team summary too short or empty")

    except Exception as e:
        logger.warning(f"Team TTS summary generation failed, using fallback: {e}")
        # Fallback: Extract key points from full TLDR
        # Simple truncation with sentence boundary awareness
        fallback = full_team_tldr.strip()
        if len(fallback) > 300:
            # Find last sentence boundary before 300 chars
            truncated = fallback[:300]
            last_boundary = max(
                truncated.rfind("。"),
                truncated.rfind("！"),
                truncated.rfind("？"),
                truncated.rfind("\n"),
            )
            # Only use boundary if it's not too early
            fallback = truncated[: last_boundary + 1] if last_boundary > 100 else truncated + "..."

        return fallback


def _build_final_analysis_report(
    strategy_result: dict[str, Any],
    match_data: dict[str, Any],
    requester_puuid: str,
    processing_duration_ms: float,
    timeline_data: dict[str, Any] | None = None,
) -> Any:
    """Build FinalAnalysisReport from strategy result (V2.4 adapter).

    This function adapts different strategy output formats to the unified
    FinalAnalysisReport contract expected by CLI 1's view layer.

    Strategy Output Formats:
    - SRStrategy: V2TeamAnalysisReport (narrative + scores)
    - ARAMStrategy: V23ARAMAnalysisReport (V2.4) or V23FallbackAnalysisReport (V2.3)
    - ArenaStrategy: V23ArenaAnalysisReport (V2.4) or V23FallbackAnalysisReport (V2.3)
    - FallbackStrategy: V23FallbackAnalysisReport
    """
    from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary

    def _make_v1_summary(
        *,
        combat_score: float | None = None,
        economy_score: float | None = None,
        vision_score: float | None = None,
        objective_score: float | None = None,
        teamplay_score: float | None = None,
        growth_score: float | None = None,
        tankiness_score: float | None = None,
        damage_composition_score: float | None = None,
        survivability_score: float | None = None,
        cc_contribution_score: float | None = None,
        overall_score: float | None = None,
        raw_stats: dict[str, Any] | None = None,
    ) -> V1ScoreSummary:
        def _val(value: float | None) -> float:
            try:
                return float(value if value is not None else 0.0)
            except Exception:
                return 0.0

        return V1ScoreSummary(
            combat_score=_val(combat_score),
            economy_score=_val(economy_score),
            vision_score=_val(vision_score),
            objective_score=_val(objective_score),
            teamplay_score=_val(teamplay_score),
            growth_score=_val(growth_score),
            tankiness_score=_val(tankiness_score),
            damage_composition_score=_val(damage_composition_score),
            survivability_score=_val(survivability_score),
            cc_contribution_score=_val(cc_contribution_score),
            overall_score=_val(overall_score),
            raw_stats=raw_stats or {},
        )

    def _compute_arena_sentiment(
        score_data: dict[str, Any],
        raw_stats: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        placement = int(raw_stats.get("placement") or score_data.get("final_placement") or 4)
        overall = float(score_data.get("overall_score") or 0.0)

        rounds = [r for r in (score_data.get("round_performances") or []) if isinstance(r, dict)]
        rounds_sorted = sorted(
            rounds,
            key=lambda item: int((item.get("round_number") or 0) or 0),
        )
        rounds_played = int(score_data.get("rounds_played") or len(rounds_sorted) or 0)
        rounds_won = int(score_data.get("rounds_won") or 0)
        if rounds_won == 0 and rounds_sorted:
            rounds_won = sum(
                1
                for r in rounds_sorted
                if str(r.get("round_result", "")).lower() in {"win", "victory", "w"}
            )
        win_rate = rounds_won / max(1, rounds_played)

        deaths_from_raw = int(raw_stats.get("deaths") or 0)
        deaths_from_rounds = sum(int(r.get("deaths", 0) or 0) for r in rounds_sorted)
        deaths = max(deaths_from_raw, deaths_from_rounds)
        death_rate = deaths / max(1, rounds_played)

        damage_dealt = float(raw_stats.get("damage_dealt") or 0.0)
        damage_taken = float(raw_stats.get("damage_taken") or 0.0)
        damage_ratio = damage_dealt / max(1.0, damage_taken)

        longest_death_streak = 0
        current_streak = 0
        for r in rounds_sorted:
            if int(r.get("deaths", 0) or 0) > 0:
                current_streak += 1
            else:
                current_streak = 0
            if current_streak > longest_death_streak:
                longest_death_streak = current_streak

        severity = 0
        trigger_flags: list[str] = []
        if placement >= 6:
            severity += 1
            trigger_flags.append("placement_low")
        if overall < 45.0:
            severity += 1
            trigger_flags.append("overall_low")
        if death_rate >= 0.6:
            severity += 1
            trigger_flags.append("death_rate_high")
        if longest_death_streak >= 3:
            severity += 1
            trigger_flags.append("death_streak")
        if damage_ratio < 0.55:
            severity += 1
            trigger_flags.append("damage_ratio_low")
        if win_rate <= 0.33:
            severity += 1
            trigger_flags.append("win_rate_low")

        if severity > 5:
            severity = 5

        severity_labels = ["stable", "watch", "caution", "risk", "critical", "critical"]
        severity_label = severity_labels[severity]

        factors = {
            "severity": severity_label,
            "severity_score": severity,
            "trigger_flags": sorted(set(trigger_flags)),
            "win_rate": round(win_rate, 2),
            "death_rate": round(death_rate, 2),
            "damage_ratio": round(damage_ratio, 2),
            "longest_death_streak": int(longest_death_streak),
            "rounds_played": rounds_played,
            "rounds_won": rounds_won,
            "baseline_overall": round(overall, 1),
        }

        if placement == 1:
            sentiment = "激动" if overall >= 80 else "自豪"
        elif placement == 2:
            sentiment = "积极" if overall >= 60 else "鼓励"
        elif placement == 3:
            sentiment = "平淡" if overall >= 55 else "反思"
        else:
            if severity >= 4:
                sentiment = "遗憾"
            elif severity == 3:
                sentiment = "反思"
            elif severity == 2:
                sentiment = "关注"
            elif severity == 1:
                sentiment = "关注" if overall < 45.0 else "鼓励"
            else:
                sentiment = "鼓励"

        factors["ui_sentiment"] = sentiment
        return sentiment, factors

    def _canonicalize_sentiment(tag: str) -> Literal["激动", "遗憾", "嘲讽", "鼓励", "平淡"]:
        allowed: set[Literal["激动", "遗憾", "嘲讽", "鼓励", "平淡"]] = {
            "激动",
            "遗憾",
            "嘲讽",
            "鼓励",
            "平淡",
        }
        if tag in allowed:
            return tag  # type: ignore[return-value]
        alias: dict[str, Literal["激动", "遗憾", "嘲讽", "鼓励", "平淡"]] = {
            "关注": "鼓励",
            "反思": "平淡",
            "积极": "鼓励",
            "自豪": "激动",
        }
        return alias.get(tag, "平淡")

    score_data = strategy_result["score_data"]
    mode = strategy_result.get("mode", "unknown")

    # Extract participant data
    participants = match_data.get("info", {}).get("participants", [])
    target_participant: dict[str, Any] = next(
        (p for p in participants if p.get("puuid") == requester_puuid),
        {},
    )

    # Prefer Riot ID if available
    riot_game = target_participant.get("riotIdGameName") or target_participant.get("gameName")
    riot_tag = target_participant.get("riotIdTagline") or target_participant.get("tagLine")
    if riot_game and riot_tag:
        summoner_name = f"{riot_game}#{riot_tag}"
    else:
        summoner_name = (
            target_participant.get("summonerName")
            or target_participant.get("gameName")
            or "Unknown"
        )

    champion_name = target_participant.get("championName", "Unknown")
    champion_id = target_participant.get("championId", 0)
    win = target_participant.get("win", False)
    match_result: Literal["victory", "defeat"] = "victory" if win else "defeat"

    # Build champion assets URL (static version OK for now)
    ddragon_version = "13.24.1"
    champion_assets_url = f"https://ddragon.leagueoflegends.com/cdn/{ddragon_version}/img/champion/{champion_name}.png"

    # Helper: build raw_stats using Match-V5 details (+ optional timeline)
    def _build_raw_stats_from_details(mp: dict[str, Any]) -> dict[str, Any]:
        info = match_data.get("info", {})
        qid = int(info.get("queueId", 420) or 420)

        # Robust duration calculation with 3-tier fallback
        game_duration_s = float(info.get("gameDuration", 0.0) or 0.0)

        # Fallback 1: derive from gameStart/EndTimestamp if present (ms)
        if game_duration_s <= 0:
            try:
                start_ts = info.get("gameStartTimestamp")
                end_ts = info.get("gameEndTimestamp")
                if start_ts and end_ts:
                    game_duration_s = max(0.0, (float(end_ts) - float(start_ts)) / 1000.0)
            except Exception:
                pass

        # Fallback 2: derive from timeline frame timestamps (works when Match Details unavailable)
        if game_duration_s <= 0 and timeline_data:
            try:
                t_info = timeline_data.get("info", {}) or {}
                frames = t_info.get("frames", []) or []
                if len(frames) >= 2:
                    first_ts = frames[0].get("timestamp", 0) or 0
                    last_ts = frames[-1].get("timestamp", 0) or 0
                    game_duration_s = max(0.0, (last_ts - first_ts) / 1000.0)
            except Exception:
                pass

        minutes = game_duration_s / 60.0 if game_duration_s else 0.0
        # Participant-level fields (best-effort across Riot versions)
        cs = (mp.get("totalMinionsKilled", 0) or 0) + (mp.get("neutralMinionsKilled", 0) or 0)
        cs_per_min = (cs / minutes) if minutes > 0 else 0.0
        gold = mp.get("goldEarned", 0) or 0
        dmg_to_champs = mp.get("totalDamageDealtToChampions", 0) or 0
        dmg_taken = mp.get("totalDamageTaken", 0) or 0
        dmg_phys = mp.get("physicalDamageDealtToChampions", 0) or 0
        dmg_mag = mp.get("magicDamageDealtToChampions", 0) or 0
        dmg_true = mp.get("trueDamageDealtToChampions", 0) or 0
        wards_placed = mp.get("wardsPlaced", 0) or 0
        wards_killed = mp.get("wardsKilled", 0) or 0
        vision_score = mp.get("visionScore", 0) or 0
        detector_wards = mp.get("detectorWardsPlaced", mp.get("visionWardsBoughtInGame", 0) or 0)
        cc_time = mp.get("timeCCingOthers", mp.get("totalTimeCCDealt", 0)) or 0
        cc_per_min_val = (float(cc_time) / minutes) if minutes > 0 else 0.0
        cc_score_val: float
        try:
            challenges = mp.get("challenges")
            cc_score = None
            if isinstance(challenges, dict):
                cc_score = challenges.get("crowdControlScore")
            if cc_score is None:
                cc_score = mp.get("crowdControlScore")
            cc_score_val = float(cc_score) if cc_score is not None else 0.0
        except (TypeError, ValueError):
            cc_score_val = 0.0
        except Exception:
            cc_score_val = 0.0
        level = mp.get("champLevel", 0) or 0
        dmg_mitigated = mp.get("damageSelfMitigated", 0) or 0
        # Takedowns (compat across versions)
        turret_kills = mp.get("turretTakedowns", mp.get("turretKills", 0) or 0)
        epic_monsters = (
            mp.get("dragonTakedowns", 0) or 0
        )  # conservative; full split not needed here
        # Roles/positions
        raw = {
            "kills": mp.get("kills", 0) or 0,
            "deaths": mp.get("deaths", 0) or 0,
            "assists": mp.get("assists", 0) or 0,
            "kda": ((mp.get("kills", 0) or 0) + (mp.get("assists", 0) or 0))
            / max(1, (mp.get("deaths", 0) or 0)),
            "cs": cs,
            "cs_per_min": cs_per_min,
            "gold": gold,
            "gold_diff": 0,  # team-view不做对线金差，保持为0
            "damage_dealt": dmg_to_champs,
            "damage_taken": dmg_taken,
            "damage_physical": dmg_phys,
            "damage_magic": dmg_mag,
            "damage_true": dmg_true,
            "wards_placed": wards_placed,
            "wards_killed": wards_killed,
            "vision_score": vision_score,
            "detector_wards_placed": detector_wards,
            "cc_time": float(cc_time),
            "cc_per_min": cc_per_min_val,
            "cc_score": cc_score_val,
            "level": level,
            "xp": 0,
            "turret_kills": turret_kills,
            "epic_monsters": epic_monsters,
            "double_kills": mp.get("doubleKills", 0) or 0,
            "triple_kills": mp.get("tripleKills", 0) or 0,
            "quadra_kills": mp.get("quadraKills", 0) or 0,
            "penta_kills": mp.get("pentaKills", 0) or 0,
            "killing_sprees": mp.get("killingSprees", 0) or 0,
            "largest_killing_spree": mp.get("largestKillingSpree", 0) or 0,
            "largest_multi_kill": mp.get("largestMultiKill", 0) or 0,
            "team_position": mp.get("teamPosition", "") or "",
            "individual_position": mp.get("individualPosition", "") or "",
            "lane": mp.get("lane", "") or "",
            "role": mp.get("role", "") or "",
            "damage_self_mitigated": dmg_mitigated,
            "queue_id": qid,
        }
        # Mode hints
        try:
            from src.contracts.v23_multi_mode_analysis import detect_game_mode

            gm = detect_game_mode(qid)
            raw["game_mode"] = gm.mode
            raw["is_arena"] = gm.mode == "Arena"
        except Exception:
            raw["game_mode"] = "SR"
            raw["is_arena"] = False
        # SR enrichment（仅当 timeline 可用时）
        try:
            if timeline_data and isinstance(mp.get("participantId"), int):
                from src.core.services.sr_enrichment import extract_sr_enrichment

                sr_extra = extract_sr_enrichment(
                    timeline_data, match_data, int(mp["participantId"])
                )
                if sr_extra:
                    raw["sr_enrichment"] = sr_extra
        except Exception:
            pass
        return raw

    # SR: prefer V2 structured; fallback to V1 player_scores mapping
    if mode == "sr":
        team_summary = score_data.get("team_summary")
        if isinstance(team_summary, dict) and team_summary.get("target_player"):
            ai_narrative = score_data.get("ai_narrative_text", "")
            sentiment = score_data.get("llm_sentiment_tag", "平淡")
            tp = team_summary.get("target_player", {})
            v1_scores = _make_v1_summary(
                combat_score=tp.get("combat_score"),
                economy_score=tp.get("economy_score"),
                vision_score=tp.get("vision_score"),
                objective_score=tp.get("objective_score"),
                teamplay_score=tp.get("teamplay_score"),
                growth_score=tp.get("growth_score"),
                tankiness_score=tp.get("tankiness_score"),
                damage_composition_score=tp.get("damage_composition_score"),
                survivability_score=tp.get("survivability_score"),
                cc_contribution_score=tp.get("cc_contribution_score"),
                overall_score=tp.get("overall_score"),
                raw_stats=team_summary.get("raw_stats", {}),
            )
        else:
            # V1 fallback
            ai_narrative = score_data.get("generic_summary") or score_data.get(
                "fallback_message", ""
            )

            # Find requester's participantId
            try:
                requester_pid = next(
                    (
                        int(p.get("participantId", 0))
                        for p in participants
                        if p.get("puuid") == requester_puuid
                    ),
                    None,
                )
            except Exception:
                requester_pid = None

            ps_list = score_data.get("player_scores") or []
            target_ps = None
            if requester_pid is not None:
                for ps in ps_list:
                    try:
                        if int(ps.get("participant_id", -1)) == requester_pid:
                            target_ps = ps
                            break
                    except Exception:
                        pass
            if target_ps is None and ps_list:
                target_ps = ps_list[0]

            def _f(val: Any) -> float:
                try:
                    return float(val)
                except Exception:
                    return 0.0

            raw_stats: dict[str, Any] = {}
            if isinstance(target_ps, dict):
                raw_stats = target_ps.get("raw_stats", {}) or {}
            # Enrich raw_stats with mode hints（不做 SR 要点注入，避免 timeline 缺失时的错误数值）
            try:
                from src.contracts.v23_multi_mode_analysis import detect_game_mode

                qid = int(match_data.get("info", {}).get("queueId", 420))
                gm = detect_game_mode(qid)
                raw_stats["queue_id"] = qid
                raw_stats["game_mode_label"] = gm.mode
                raw_stats["is_arena"] = gm.mode == "Arena"
            except Exception:
                pass

            v1_scores = _make_v1_summary(
                combat_score=_f(target_ps.get("combat_efficiency", 0.0)) if target_ps else 0.0,
                economy_score=_f(target_ps.get("economic_management", 0.0)) if target_ps else 0.0,
                vision_score=_f(target_ps.get("vision_control", 0.0)) if target_ps else 0.0,
                objective_score=_f(target_ps.get("objective_control", 0.0)) if target_ps else 0.0,
                teamplay_score=_f(target_ps.get("team_contribution", 0.0)) if target_ps else 0.0,
                growth_score=_f(target_ps.get("growth_score", 0.0)) if target_ps else 0.0,
                tankiness_score=_f(target_ps.get("tankiness_score", 0.0)) if target_ps else 0.0,
                damage_composition_score=_f(target_ps.get("damage_composition_score", 0.0))
                if target_ps
                else 0.0,
                survivability_score=_f(target_ps.get("survivability_score", 0.0))
                if target_ps
                else 0.0,
                cc_contribution_score=_f(target_ps.get("cc_contribution_score", 0.0))
                if target_ps
                else 0.0,
                overall_score=_f(target_ps.get("total_score", 0.0)) if target_ps else 0.0,
                raw_stats=raw_stats,
            )
            # Lightweight sentiment mapping
            sentiment = "鼓励" if v1_scores.overall_score >= 60 else "遗憾"
        # Inject team receipt into raw_stats for header rendering (prefer timeline; fallback to current score_data)
        try:
            from types import SimpleNamespace

            from src.core.views.team_ascii_receipt import build_team_receipt

            # Resolve friendly team participants
            parts = match_data.get("info", {}).get("participants", [])
            target_part = next((p for p in parts if p.get("puuid") == requester_puuid), None)
            t_team = (
                100 if (target_part and int(target_part.get("participantId", 0) or 0) <= 5) else 200
            )
            team_parts = [
                p
                for p in parts
                if (100 if int(p.get("participantId", 0) or 0) <= 5 else 200) == t_team
            ][:5]

            team_players_objs = []
            built_from = ""
            # First try: recompute with timeline+details for accuracy
            try:
                if timeline_data:
                    from src.contracts.timeline import MatchTimeline
                    from src.core.scoring.calculator import generate_llm_input

                    ao_all = generate_llm_input(
                        MatchTimeline(**timeline_data), match_details=match_data
                    )
                    idx = {int(ps.participant_id): ps for ps in ao_all.player_scores}
                    for p in team_parts:
                        pid = int(p.get("participantId", 0) or 0)
                        ps = idx.get(pid)
                        if not ps:
                            continue
                        is_aram_mode = raw_stats.get("game_mode_label", "").lower() == "aram"
                        team_players_objs.append(
                            SimpleNamespace(
                                summoner_name=p.get("riotIdGameName")
                                or p.get("summonerName")
                                or p.get("gameName"),
                                combat_score=ps.combat_efficiency,
                                economy_score=ps.economic_management,
                                vision_score=0.0 if is_aram_mode else ps.vision_control,
                                objective_score=0.0 if is_aram_mode else ps.objective_control,
                                teamplay_score=ps.team_contribution,
                                survivability_score=getattr(ps, "survivability_score", 0.0),
                                kills=int(p.get("kills", 0) or 0),
                                deaths=int(p.get("deaths", 0) or 0),
                                assists=int(p.get("assists", 0) or 0),
                                damage_dealt=int(p.get("totalDamageDealtToChampions", 0) or 0),
                            )
                        )
                    built_from = "timeline"
            except Exception:
                team_players_objs = []
            # Fallback: use score_data.player_scores from current result (no recompute)
            if not team_players_objs:
                ps_list = score_data.get("player_scores") or []
                # Map by participant_id
                idx = {}
                for ps in ps_list:
                    try:
                        idx[int(ps.get("participant_id", 0) or 0)] = ps
                    except Exception:
                        continue
                for p in team_parts:
                    pid = int(p.get("participantId", 0) or 0)
                    ps = idx.get(pid)
                    if not ps:
                        continue
                    is_aram_mode = raw_stats.get("game_mode_label", "").lower() == "aram"
                    team_players_objs.append(
                        SimpleNamespace(
                            summoner_name=p.get("riotIdGameName")
                            or p.get("summonerName")
                            or p.get("gameName"),
                            combat_score=float(ps.get("combat_efficiency", 0.0)),
                            economy_score=float(ps.get("economic_management", 0.0)),
                            vision_score=0.0
                            if is_aram_mode
                            else float(ps.get("vision_control", 0.0)),
                            objective_score=0.0
                            if is_aram_mode
                            else float(ps.get("objective_control", 0.0)),
                            teamplay_score=float(ps.get("team_contribution", 0.0)),
                            survivability_score=float(ps.get("survivability_score", 0.0)),
                            kills=int(p.get("kills", 0) or 0),
                            deaths=int(p.get("deaths", 0) or 0),
                            assists=int(p.get("assists", 0) or 0),
                            damage_dealt=int(p.get("totalDamageDealtToChampions", 0) or 0),
                        )
                    )
                built_from = built_from or "score_data"

            if team_players_objs:
                # Detect game mode for correct receipt labeling
                detected_mode = "summoners_rift"  # default
                try:
                    from src.contracts.v23_multi_mode_analysis import detect_game_mode

                    qid = int(match_data.get("info", {}).get("queueId", 0))
                    gm = detect_game_mode(qid)
                    detected_mode = _map_game_mode_to_contract(gm.mode)
                except Exception:
                    pass

                report_like = SimpleNamespace(
                    team_analysis=team_players_objs,
                    target_player_name=(
                        target_part.get("riotIdGameName")
                        or target_part.get("summonerName")
                        or target_part.get("gameName")
                        or "-"
                        if target_part
                        else "-"
                    ),
                    game_mode=detected_mode,
                )
                receipt = build_team_receipt(report_like)
                with contextlib.suppress(Exception):
                    v1_scores.raw_stats = {**(v1_scores.raw_stats or {}), "team_receipt": receipt}
        except Exception:
            # Non-fatal: header enhancement is optional
            pass
    else:
        # ARAM/Arena: Map V1-Lite → FinalReport; Fallback: generic text
        ai_narrative = ""
        sentiment = "平淡"

        if mode == "aram":
            # Narrative from V1-Lite
            ai_narrative = score_data.get("analysis_summary", "") or score_data.get(
                "generic_summary", ""
            )

            # Build raw_stats from target participant
            raw_stats = _build_raw_stats_from_details(target_participant)

            v1_scores = _make_v1_summary(
                combat_score=score_data.get("combat_score"),
                economy_score=0.0,  # Disabled in ARAM
                vision_score=0.0,  # Disabled in ARAM
                objective_score=0.0,  # Disabled in ARAM
                teamplay_score=score_data.get("teamplay_score"),
                growth_score=score_data.get("growth_score"),
                tankiness_score=score_data.get("tankiness_score"),
                damage_composition_score=score_data.get("damage_composition_score"),
                survivability_score=score_data.get("survivability_score"),
                cc_contribution_score=score_data.get("cc_contribution_score"),
                overall_score=score_data.get("overall_score"),
                raw_stats=raw_stats,
            )

            # Map sentiment based on ARAM performance
            overall = v1_scores.overall_score
            if win:
                sentiment = "激动" if overall >= 80 else ("自豪" if overall >= 70 else "积极")
            else:
                sentiment = "鼓励" if overall >= 60 else ("反思" if overall >= 40 else "遗憾")
        elif mode == "arena":
            # Narrative from V1-Lite
            ai_narrative = score_data.get("analysis_summary", "") or score_data.get(
                "generic_summary", ""
            )

            # Build raw_stats from target participant + Arena-specific enrichment
            raw_stats = _build_raw_stats_from_details(target_participant)

            # Arena-specific enrichment from strategy result
            raw_stats["placement"] = score_data.get("final_placement", 4)
            raw_stats["arena_partner_champion"] = score_data.get("partner_champion_name")
            raw_stats["arena_partner_name"] = score_data.get("partner_summoner_name")

            # Augments
            try:
                augment_analysis = score_data.get("augment_analysis", {})
                if isinstance(augment_analysis, dict):
                    augments: list[Any] = augment_analysis.get("augments_selected", [])
                    if augments:
                        raw_stats["arena_augments"] = list(augments)
            except Exception:
                pass

            # Round performances (compact format for display)
            try:
                rounds: list[dict[str, Any]] = score_data.get("round_performances", [])
                if rounds:
                    raw_stats["arena_rounds"] = [
                        {
                            "n": r.get("round_number"),
                            "r": r.get("round_result"),
                            "dd": r.get("damage_dealt", 0),
                            "dt": r.get("damage_taken", 0),
                            "k": r.get("kills", 0),
                            "d": r.get("deaths", 0),
                            "pos": r.get("positioning_score", 0),
                        }
                        for r in rounds
                    ]
                    # Key rounds summary
                    if rounds:
                        best = max(
                            rounds, key=lambda x: (x.get("kills", 0), x.get("damage_dealt", 0))
                        )
                        worst = max(
                            rounds, key=lambda x: (x.get("deaths", 0), x.get("damage_taken", 0))
                        )
                        arena_key_rounds: dict[str, dict[str, Any]] = {
                            "best": {
                                "n": best.get("round_number"),
                                "k": best.get("kills", 0),
                                "dd": best.get("damage_dealt", 0),
                                "r": best.get("round_result"),
                            },
                            "worst": {
                                "n": worst.get("round_number"),
                                "d": worst.get("deaths", 0),
                                "dt": worst.get("damage_taken", 0),
                                "r": worst.get("round_result"),
                            },
                        }
                        raw_stats["arena_key_rounds"] = arena_key_rounds
            except Exception:
                pass

            arena_sentiment, sentiment_factors = _compute_arena_sentiment(score_data, raw_stats)
            sentiment_factors_dict: dict[str, Any] = sentiment_factors
            raw_stats["arena_sentiment_factors"] = sentiment_factors_dict
            raw_stats.setdefault("arena_rounds_played", sentiment_factors["rounds_played"])
            raw_stats.setdefault("arena_round_count", sentiment_factors["rounds_played"])
            raw_stats.setdefault("arena_rounds_won", sentiment_factors["rounds_won"])
            raw_stats.setdefault("arena_win_rate", sentiment_factors["win_rate"])
            raw_stats.setdefault(
                "arena_longest_death_streak", sentiment_factors["longest_death_streak"]
            )
            raw_stats.setdefault("arena_death_rate", sentiment_factors["death_rate"])

            v1_scores = _make_v1_summary(
                combat_score=score_data.get("combat_score"),
                economy_score=0.0,
                vision_score=0.0,
                objective_score=0.0,
                teamplay_score=score_data.get("duo_synergy_score"),
                growth_score=score_data.get("growth_score"),
                tankiness_score=score_data.get("tankiness_score"),
                damage_composition_score=score_data.get("damage_composition_score"),
                survivability_score=score_data.get("survivability_score"),
                cc_contribution_score=score_data.get("cc_contribution_score"),
                overall_score=score_data.get("overall_score"),
                raw_stats=raw_stats,
            )

            sentiment = arena_sentiment
        else:
            # Fallback: Use generic summary/message, zero scores
            ai_narrative = score_data.get("generic_summary") or score_data.get(
                "fallback_message", ""
            )
            v1_scores = _make_v1_summary(
                combat_score=0.0,
                economy_score=0.0,
                vision_score=0.0,
                objective_score=0.0,
                teamplay_score=0.0,
                growth_score=0.0,
                tankiness_score=0.0,
                damage_composition_score=0.0,
                survivability_score=0.0,
                cc_contribution_score=0.0,
                overall_score=0.0,
            )

    sentiment = _canonicalize_sentiment(sentiment)

    return FinalAnalysisReport(
        match_id=match_data.get("metadata", {}).get("matchId", "unknown"),
        match_result=match_result,
        summoner_name=summoner_name,
        champion_name=champion_name,
        champion_id=champion_id,
        ai_narrative_text=ai_narrative[:1900],
        llm_sentiment_tag=sentiment,
        v1_score_summary=v1_scores,
        champion_assets_url=champion_assets_url,
        processing_duration_ms=processing_duration_ms,
        algorithm_version=score_data.get("algorithm_version", "v2.3"),
        tts_audio_url=None,
        builds_summary_text=None,
        builds_metadata=None,
    )


async def _build_team_overview_report(
    *,
    match_details: dict[str, Any],
    timeline_data: dict[str, Any],
    requester_puuid: str,
    region: str,
    resolved_game_mode: str | None = None,
    arena_score_data: dict[str, Any] | None = None,
    workflow_metrics: dict[str, Any] | None = None,
) -> TeamAnalysisReport:
    """Build TeamAnalysisReport (overview) from match details + timeline.

    - Picks friendly team (5 players) based on participantId of requester
    - Computes per-player V1 scores via generate_llm_input (with match_details for accuracy)
    - Aggregates team averages for 5 core dimensions + overall
    """
    from src.contracts.timeline import MatchTimeline
    from src.core.scoring.calculator import generate_llm_input

    info = match_details.get("info", {})
    participants = info.get("participants", [])
    game_version = info.get("gameVersion")  # Extract for DDragon icon URLs

    # Find requester's participant/team
    target_p = next((p for p in participants if p.get("puuid") == requester_puuid), None)
    target_pid = int(target_p.get("participantId", 0) or 0) if target_p else 0
    team_tag = 100 if target_pid and target_pid <= 5 else 200

    # Detect/correct game mode (prefer early-resolved label when provided)
    gm_label_str = resolved_game_mode or "unknown"
    if gm_label_str not in {"summoners_rift", "aram", "arena", "unknown"}:
        try:
            from src.contracts.v23_multi_mode_analysis import detect_game_mode

            qid = int(info.get("queueId", 0) or 0)
            gm = detect_game_mode(qid)
            gm_label_str = _map_game_mode_to_contract(
                gm.mode if isinstance(gm.mode, str) else "Fallback"
            )
            parts_len = len(info.get("participants", []) or [])
            if gm_label_str == "arena" and parts_len == 10:
                gm_label_str = "summoners_rift"
        except Exception:
            gm_label_str = "unknown"
    gm_label: Literal["summoners_rift", "aram", "arena", "unknown"] = gm_label_str  # type: ignore[assignment]

    # Scores for 10 players (SR path). For Arena this may be partial (1..10)
    ao = generate_llm_input(MatchTimeline(**timeline_data), match_details=match_details)
    idx = {int(ps.participant_id): ps for ps in ao.player_scores}

    # Helper: normalize role to contract literal
    def _role_of(p: dict[str, Any]) -> str:
        role = p.get("teamPosition") or p.get("individualPosition") or ""
        role = role.upper()
        mapping = {
            "TOP": "TOP",
            "JUNGLE": "JUNGLE",
            "MIDDLE": "MIDDLE",
            "MID": "MIDDLE",
            "BOTTOM": "BOTTOM",
            "ADC": "BOTTOM",
            "UTILITY": "UTILITY",
            "SUPPORT": "UTILITY",
        }
        return mapping.get(role, "UTILITY")

    def _find_lane_opponent(me: dict[str, Any]) -> dict[str, Any] | None:
        my_team_id = int(me.get("teamId", 0) or 0)
        lane = str(me.get("individualPosition") or "").upper()
        team_lane = str(me.get("teamPosition") or "").upper()

        def _norm(pos: Any) -> str:
            return str(pos or "").upper()

        enemies = [p for p in participants if int(p.get("teamId", 0) or 0) != my_team_id]

        if lane:
            for enemy in enemies:
                if _norm(enemy.get("individualPosition")) == lane:
                    return enemy

        if team_lane:
            for enemy in enemies:
                if _norm(enemy.get("teamPosition")) == team_lane:
                    return enemy

        for enemy in enemies:
            if _norm(enemy.get("individualPosition")) in {"MIDDLE", "MID"}:
                return enemy

        return None

    # Build 5 friendly players
    _player_payloads: list[dict[str, Any]] = []
    for p in participants:
        pid = int(p.get("participantId", 0) or 0)
        if (100 if pid <= 5 else 200) != team_tag:
            continue
        ps = idx.get(pid)
        if not ps:
            continue
        name_core = p.get("riotIdGameName") or p.get("summonerName") or p.get("gameName") or "-"
        tag = p.get("riotIdTagline") or p.get("tagLine")
        name = f"{name_core}#{tag}" if tag else name_core
        champion_name = p.get("championName") or "Unknown"
        is_aram_mode = gm_label == "aram"
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        damage = int(p.get("totalDamageDealtToChampions", 0) or 0)
        _player_payloads.append(
            {
                "puuid": p.get("puuid", ""),
                "summoner_name": name,
                "champion_name": champion_name,
                "role": _role_of(p),
                "combat_score": float(ps.combat_efficiency),
                "economy_score": float(ps.economic_management),
                "vision_score": 0.0 if is_aram_mode else float(ps.vision_control),
                "objective_score": 0.0 if is_aram_mode else float(ps.objective_control),
                "teamplay_score": float(ps.team_contribution),
                "overall_score": float(ps.total_score),
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "damage_dealt": damage,
                "survivability_score": (
                    float(getattr(ps, "survivability_score", 0.0))
                    if getattr(ps, "survivability_score", None) is not None
                    else None
                ),
                "champion_icon_url": _champion_icon_url(champion_name, game_version),
            }
        )
        if len(_player_payloads) == 5:
            break

    team_players: list[TeamPlayerEntry] = []
    for rank, payload in enumerate(
        sorted(_player_payloads, key=lambda item: item["overall_score"], reverse=True)[:5],
        start=1,
    ):
        payload["team_rank"] = rank
        team_players.append(TeamPlayerEntry(**payload))

    # Opponent team (5 players)
    enemy_tag = 200 if team_tag == 100 else 100
    _enemy_payloads: list[dict[str, Any]] = []
    for p in participants:
        pid = int(p.get("participantId", 0) or 0)
        side = 100 if pid and pid <= 5 else 200
        if side != enemy_tag:
            continue
        ps = idx.get(pid)
        if not ps:
            continue
        name_core = p.get("riotIdGameName") or p.get("summonerName") or p.get("gameName") or "-"
        tag = p.get("riotIdTagline") or p.get("tagLine")
        name = f"{name_core}#{tag}" if tag else name_core
        champion_name = p.get("championName") or "Unknown"
        is_aram_mode = gm_label == "aram"
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        damage = int(p.get("totalDamageDealtToChampions", 0) or 0)
        _enemy_payloads.append(
            {
                "puuid": p.get("puuid", ""),
                "summoner_name": name,
                "champion_name": champion_name,
                "role": _role_of(p),
                "combat_score": float(ps.combat_efficiency),
                "economy_score": float(ps.economic_management),
                "vision_score": 0.0 if is_aram_mode else float(ps.vision_control),
                "objective_score": 0.0 if is_aram_mode else float(ps.objective_control),
                "teamplay_score": float(ps.team_contribution),
                "overall_score": float(ps.total_score),
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "damage_dealt": damage,
                "survivability_score": (
                    float(getattr(ps, "survivability_score", 0.0))
                    if getattr(ps, "survivability_score", None) is not None
                    else None
                ),
                "champion_icon_url": _champion_icon_url(champion_name, game_version),
            }
        )
        if len(_enemy_payloads) == 5:
            break

    opponent_players: list[TeamPlayerEntry] = []
    for rank, payload in enumerate(
        sorted(_enemy_payloads, key=lambda item: item["overall_score"], reverse=True)[:5],
        start=1,
    ):
        payload["team_rank"] = rank
        opponent_players.append(TeamPlayerEntry(**payload))

    # Aggregates over 5
    def _avg(vals: list[float]) -> float:
        return round(sum(vals) / max(1, len(vals)), 1)

    aggregates = TeamAggregates(
        combat_avg=_avg([p.combat_score for p in team_players]),
        economy_avg=_avg([p.economy_score for p in team_players]),
        vision_avg=_avg([p.vision_score for p in team_players]),
        objective_avg=_avg([p.objective_score for p in team_players]),
        teamplay_avg=_avg([p.teamplay_score for p in team_players]),
        overall_avg=_avg([p.overall_score for p in team_players]),
    )

    opponent_aggregates = None
    if opponent_players:
        opponent_aggregates = TeamAggregates(
            combat_avg=_avg([p.combat_score for p in opponent_players]),
            economy_avg=_avg([p.economy_score for p in opponent_players]),
            vision_avg=_avg([p.vision_score for p in opponent_players]),
            objective_avg=_avg([p.objective_score for p in opponent_players]),
            teamplay_avg=_avg([p.teamplay_score for p in opponent_players]),
            overall_avg=_avg([p.overall_score for p in opponent_players]),
        )

    win = bool(target_p.get("win", False)) if target_p else False
    # Arena duo enrichment (for specialized view)
    arena_duo = None
    if gm_label == "arena" and target_p:
        try:
            sub_id = target_p.get("subteamId")
            partner = None
            if sub_id is not None:
                partner = next(
                    (
                        p
                        for p in participants
                        if p.get("subteamId") == sub_id and p.get("puuid") != requester_puuid
                    ),
                    None,
                )
            arena_duo = TeamAnalysisReport.ArenaDuo(
                me_name=(
                    target_p.get("riotIdGameName")
                    or target_p.get("summonerName")
                    or target_p.get("gameName")
                    or "-"
                ),
                me_champion=(target_p.get("championName") or "Unknown"),
                partner_name=(
                    partner.get("riotIdGameName")
                    or partner.get("summonerName")
                    or partner.get("gameName")
                )
                if partner
                else None,
                partner_champion=(partner.get("championName") if partner else None),
                placement=(
                    int(target_p.get("placement") or 0)
                    if target_p.get("placement") is not None
                    else None
                ),
            )
        except Exception:
            arena_duo = None

    # Optional: populate Arena summary_text using score_data (round_performances)
    summary_text = None
    arena_rounds_block = None
    if gm_label == "arena" and arena_score_data:
        try:
            rp = arena_score_data.get("round_performances") or []
            rounds = [r for r in rp if isinstance(r, dict)]
            # Top-3 by kills->damage
            top3 = sorted(
                rounds, key=lambda x: (x.get("kills", 0), x.get("damage_dealt", 0)), reverse=True
            )[:3]
            worst = (
                max(rounds, key=lambda x: (x.get("deaths", 0), x.get("damage_taken", 0)))
                if rounds
                else None
            )
            place = None
            try:
                place = int(arena_score_data.get("final_placement") or 0)
            except Exception:
                place = None

            # Win/Loss tally + longest streaks (with ranges) + ASCII trajectory
            norm = []
            for r in sorted(rounds, key=lambda x: int(x.get("round_number", 0) or 0)):
                tag = str((r.get("round_result") or "").lower())
                if tag in ("win", "victory", "w"):
                    norm.append(("W", int(r.get("round_number", 0) or 0)))
                else:
                    norm.append(("L", int(r.get("round_number", 0) or 0)))
            win_cnt = sum(1 for t, _ in norm if t == "W")
            lose_cnt = sum(1 for t, _ in norm if t == "L")

            def _longest(
                seq: list[tuple[str, int]], target: str
            ) -> tuple[int, int | None, int | None]:
                best_len = cur = 0
                best_start = best_end = None
                cur_start = None
                for t, rn in seq:
                    if t == target:
                        if cur == 0:
                            cur_start = rn
                        cur += 1
                        if cur > best_len:
                            best_len = cur
                            best_start = cur_start
                            best_end = rn
                    else:
                        cur = 0
                        cur_start = None
                return best_len, best_start, best_end

            longest_win, win_s, win_e = _longest(norm, "W")
            longest_lose, lose_s, lose_e = _longest(norm, "L")

            # Compressed ASCII trajectory, e.g., W2 L1 W1 L2
            comp = []
            if norm:
                last = norm[0][0]
                cnt = 1
                for t, _ in norm[1:]:
                    if t == last:
                        cnt += 1
                    else:
                        comp.append(f"{last}{cnt}")
                        last = t
                        cnt = 1
                comp.append(f"{last}{cnt}")
            ascii_traj = " ".join(comp)

            # Build lines
            lines = []
            if place:
                lines.append(f"名次: 第{place}名  |  战绩: {win_cnt}胜-{lose_cnt}负")
            elif rounds:
                lines.append(f"战绩: {win_cnt}胜-{lose_cnt}负")
            if top3:
                lines.append("高光回合:")
                for r in top3:
                    lines.append(
                        f"• R{r.get('round_number')}: {r.get('kills', 0)}杀/{r.get('deaths', 0)}死, 伤害{r.get('damage_dealt', 0)} 承伤{r.get('damage_taken', 0)}"
                    )
            if worst:
                lines.append(
                    f"艰难回合: R{worst.get('round_number')}: 阵亡{worst.get('deaths', 0)}次, 承伤{worst.get('damage_taken', 0)}"
                )
            if longest_win or longest_lose:
                lines.append(
                    f"连胜/连败: 最长连胜 {longest_win} 局{f' (R{win_s}–R{win_e})' if win_s and win_e else ''}，"
                    f"最长连败 {longest_lose} 局{f' (R{lose_s}–R{lose_e})' if lose_s and lose_e else ''}"
                )
            if ascii_traj:
                lines.append(f"轨迹: {ascii_traj}")

            # Condensed one-liner for summary_text; full block to arena_rounds_block
            if place or top3 or worst:
                summary_text = (
                    f"Placement: 第{place}名 | 顶尖回合 R{top3[0].get('round_number')}"
                    if place and top3
                    else None
                )
            arena_rounds_block = "\n".join(lines) if lines else None
        except Exception:
            summary_text = None
            arena_rounds_block = None
    target_name = "-"
    target_puuid = None
    if target_p:
        target_puuid = target_p.get("puuid")
        base_name = (
            target_p.get("riotIdGameName")
            or target_p.get("summonerName")
            or target_p.get("gameName")
            or "-"
        )
        tag = target_p.get("riotIdTagline") or target_p.get("tagLine")
        target_name = f"{base_name}#{tag}" if tag else base_name

    target_entry = None
    if team_players:
        for entry in team_players:
            if entry.summoner_name == target_name:
                target_entry = entry
                break
        if target_entry is None:
            target_entry = team_players[0]

    strengths: list[TeamAnalysisReport.DimensionHighlight] = []
    weaknesses: list[TeamAnalysisReport.DimensionHighlight] = []
    if target_entry:
        opponent_scores: dict[str, float] | None = None
        if gm_label == "summoners_rift" and target_p:
            opponent = _find_lane_opponent(target_p)
            if opponent:
                try:
                    opp_pid = int(opponent.get("participantId", 0) or 0)
                except Exception:
                    opp_pid = 0
                opp_ps = idx.get(opp_pid)
                if opp_ps:
                    opponent_scores = {
                        "combat_efficiency": float(opp_ps.combat_efficiency),
                        "economic_management": float(opp_ps.economic_management),
                        "objective_control": float(opp_ps.objective_control),
                        "vision_control": float(opp_ps.vision_control),
                        "team_contribution": float(opp_ps.team_contribution),
                    }
                    opp_surv = getattr(opp_ps, "survivability_score", None)
                    if opp_surv is not None:
                        opponent_scores["survivability"] = float(opp_surv)

        dimension_payload = [
            (
                "combat_efficiency",
                "战斗效率",
                target_entry.combat_score,
                aggregates.combat_avg,
            ),
            (
                "economic_management",
                "经济管理",
                target_entry.economy_score,
                aggregates.economy_avg,
            ),
            (
                "objective_control",
                "目标控制",
                target_entry.objective_score,
                aggregates.objective_avg,
            ),
            (
                "vision_control",
                "视野控制",
                target_entry.vision_score,
                aggregates.vision_avg,
            ),
            (
                "team_contribution",
                "团队协同",
                target_entry.teamplay_score,
                aggregates.teamplay_avg,
            ),
        ]
        if target_entry.survivability_score is not None:
            avg_surv = sum((p.survivability_score or 0.0) for p in team_players) / max(
                1, len(team_players)
            )
            dimension_payload.append(
                (
                    "survivability",
                    "生存能力",
                    target_entry.survivability_score or 0.0,
                    avg_surv,
                )
            )
        highlights = [
            TeamAnalysisReport.DimensionHighlight(
                dimension=dim_key,
                label=label,
                score=round(float(score), 1),
                delta_vs_team=round(float(score) - float(avg), 1),
                delta_vs_opponent=(
                    round(float(score) - opponent_scores[dim_key], 1)
                    if opponent_scores and dim_key in opponent_scores
                    else None
                ),
            )
            for dim_key, label, score, avg in dimension_payload
        ]
        strengths = sorted(highlights, key=lambda h: h.delta_vs_team or 0.0, reverse=True)[:3]
        weaknesses = sorted(highlights, key=lambda h: h.delta_vs_team or 0.0)[:3]

    enhancements: TeamAnalysisReport.EnhancementMetrics | None = None
    if gm_label == "summoners_rift" and target_pid:
        try:
            from src.core.services.sr_enrichment import extract_sr_enrichment

            sr_extra = extract_sr_enrichment(timeline_data, match_details, int(target_pid))
            if sr_extra:
                enhancements = TeamAnalysisReport.EnhancementMetrics(
                    gold_diff_10=sr_extra.get("gold_diff_10"),
                    xp_diff_10=sr_extra.get("xp_diff_10"),
                    conversion_rate=sr_extra.get("conversion_rate"),
                    ward_rate_per_min=sr_extra.get("ward_rate_per_min"),
                )
        except Exception:
            enhancements = None

    builds_summary_text: str | None = None
    builds_metadata: dict[str, Any] | None = None

    # V2.5: 出装/符文增强（Data Dragon + 可选 OPGG）
    try:
        import os as _os_enrich

        match_id = match_details.get("metadata", {}).get("matchId", "unknown")
        env_flag = str(_os_enrich.getenv("CHIMERA_TEAM_BUILD_ENRICH", "")).strip().lower()
        feature_enabled = (
            env_flag in ("1", "true", "yes", "on")
            if env_flag
            else settings.feature_team_build_enrichment_enabled
        )

        if feature_enabled:
            logger.info(
                "team_builds_enricher_enabled",
                extra={
                    "match_id": match_id,
                    "target_puuid": target_puuid or "",
                    "locale": _os_enrich.getenv("CHIMERA_LOCALE", "zh_CN"),
                },
            )
            try:
                from src.core.services.team_builds_enricher import (
                    DataDragonClient,
                    OPGGAdapter,
                    TeamBuildsEnricher,
                )

                dd = DataDragonClient(locale=_os_enrich.getenv("CHIMERA_LOCALE", "zh_CN"))

                opgg_flag = str(_os_enrich.getenv("CHIMERA_OPGG_ENABLED", "")).strip().lower()
                opgg_enabled = (
                    opgg_flag in ("1", "true", "yes", "on")
                    if opgg_flag
                    else settings.feature_opgg_enrichment_enabled
                )

                opgg = None
                if opgg_enabled:
                    try:
                        opgg = OPGGAdapter()
                        if not opgg.available:
                            logger.warning(
                                "team_builds_opgg_unavailable",
                                extra={"match_id": match_id, "reason": "OPGG library not found"},
                            )
                    except Exception as exc:
                        logger.warning(
                            "team_builds_opgg_init_failed",
                            extra={"match_id": match_id, "error": str(exc)},
                        )
                        opgg = None

                enricher = TeamBuildsEnricher(dd, opgg)
                enrich_text, enrich_payload = await enricher.build_summary_for_target(
                    match_details,
                    target_puuid=target_puuid or "",
                    target_name=target_name,
                    enable_opgg=bool(opgg and opgg.available),
                )
                resolved_puuid = None
                if enrich_payload:
                    resolved_puuid = enrich_payload.pop("resolved_puuid", None)
                if resolved_puuid and not target_puuid:
                    target_puuid = resolved_puuid
                if enrich_text:
                    builds_summary_text = enrich_text[:600]
                    if not summary_text:
                        summary_text = enrich_text[:600]
                    logger.info(
                        "team_builds_enrichment_success",
                        extra={
                            "match_id": match_id,
                            "text_length": len(enrich_text),
                            "has_metadata": bool(enrich_payload),
                        },
                    )
                else:
                    logger.warning(
                        "team_builds_enrichment_empty",
                        extra={
                            "match_id": match_id,
                            "target_puuid": target_puuid or "",
                            "reason": "No enrichment text returned",
                        },
                    )
                if enrich_payload:
                    builds_metadata = enrich_payload
            except Exception as exc:
                # 增强失败不影响主流程，但记录详细错误
                logger.exception(
                    "team_builds_enrichment_failed",
                    extra={
                        "match_id": match_id,
                        "target_puuid": target_puuid or "",
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
        else:
            logger.debug(
                "team_builds_enricher_disabled",
                extra={
                    "match_id": match_id,
                    "env_flag": _os_enrich.getenv("CHIMERA_TEAM_BUILD_ENRICH", ""),
                },
            )
    except Exception as exc:
        logger.error(
            "team_builds_enricher_outer_error",
            extra={"match_id": match_id, "error": str(exc)},
        )

    observability: TeamAnalysisReport.ObservabilitySnapshot | None = None
    if workflow_metrics:

        def _metric_value(*keys: str) -> float | None:
            if workflow_metrics is None:
                return None
            for key in keys:
                if key in workflow_metrics and workflow_metrics[key] is not None:
                    try:
                        return float(workflow_metrics[key])
                    except Exception:
                        continue
            return None

        session_identifier = str(
            workflow_metrics.get("correlation_id")
            or match_details.get("metadata", {}).get("matchId")
            or requester_puuid
        )
        branch_identifier = str(
            workflow_metrics.get("execution_branch_id")
            or workflow_metrics.get("game_mode")
            or "team_analyze"
        )
        observability = TeamAnalysisReport.ObservabilitySnapshot(
            session_id=session_identifier,
            execution_branch_id=branch_identifier,
            fetch_ms=_metric_value("fetch_duration_ms", "fetch_latency_ms"),
            scoring_ms=_metric_value("scoring_duration_ms", "scoring_latency_ms"),
            llm_ms=_metric_value("llm_duration_ms", "llm_latency_ms"),
            webhook_ms=_metric_value("webhook_duration_ms", "webhook_latency_ms"),
            overall_ms=_metric_value("duration_ms", "total_duration_ms"),
        )

    return TeamAnalysisReport(
        match_id=match_details.get("metadata", {}).get("matchId", "unknown"),
        team_result=("victory" if win else "defeat"),
        team_region=region,
        game_mode=gm_label,
        players=team_players,
        opponent_players=opponent_players or None,
        aggregates=aggregates,
        opponent_aggregates=opponent_aggregates,
        summary_text=summary_text,
        builds_summary_text=builds_summary_text,
        builds_metadata=builds_metadata,
        target_player_name=target_name,
        target_player_puuid=target_puuid,
        strengths=strengths,
        weaknesses=weaknesses,
        enhancements=enhancements,
        observability=observability,
        arena_duo=arena_duo,
        arena_rounds_block=arena_rounds_block,
    )


def _send_error_webhook(
    loop: Any,
    application_id: str,
    interaction_token: str,
    match_id: str,
    error_type: str,
    error_message: str,
    channel_id: str | None = None,
) -> None:
    """Send error notification via Discord webhook (V2.4 P0 fix).

    This function ensures error messages are delivered to users even when
    analysis fails, completing the async delivery mechanism.

    Args:
        loop: asyncio event loop
        application_id: Discord application ID
        interaction_token: Interaction token
        match_id: Match ID that failed
        error_type: Error classification
        error_message: User-friendly error description
        channel_id: Discord channel ID (optional, for webhook fallback)
    """
    try:
        from src.adapters.discord_webhook import DiscordWebhookAdapter
        from src.contracts.analysis_results import AnalysisErrorReport

        error_report = AnalysisErrorReport(
            match_id=match_id,
            error_type=error_type,
            error_message=error_message,
            retry_suggested=True,
        )

        webhook_adapter = DiscordWebhookAdapter()
        loop.run_until_complete(
            webhook_adapter.send_error_notification(
                application_id=application_id,
                interaction_token=interaction_token,
                error_report=error_report,
                channel_id=channel_id,
            )
        )
        loop.run_until_complete(webhook_adapter.close())

        logger.info(
            "error_webhook_delivered",
            extra={
                "match_id": match_id,
                "error_type": error_type,
            },
        )

    except Exception as e:
        # Webhook failure should not crash the task
        logger.error(
            "error_webhook_delivery_failed",
            extra={
                "match_id": match_id,
                "error": str(e),
            },
            exc_info=True,
        )
