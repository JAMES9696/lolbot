"""Analysis tasks for /讲道理 (Argument) command.

This module implements the atomic analyze_match_task that orchestrates:
1. Data Fetch (RiotAPIAdapter + Cassiopeia)
2. V1 Scoring (Pure domain logic from src/core/scoring/)
3. Result Persistence (DatabaseAdapter → match_analytics table)

Architectural Principles:
- Task Atomicity: Single task completes entire workflow
- Dependency Inversion: Uses Port interfaces (not concrete adapters)
- Observability: @llm_debug_wrapper on all critical operations
- Error Resilience: Handles 429 rate limits, retries, and failure tracking
"""

import asyncio
import logging
import re
import time
from typing import Any

from celery import Task

from src.adapters.database import DatabaseAdapter
from src.adapters.ddragon_adapter import DDragonAdapter
from src.adapters.redis_adapter import RedisAdapter
from src.adapters.discord_webhook import DiscordWebhookAdapter, DiscordWebhookError
from src.adapters.gemini_llm import GeminiAPIError, GeminiLLMAdapter
from src.adapters.riot_api import RateLimitError, RiotAPIAdapter, RiotAPIError
from src.adapters.tts_adapter import TTSAdapter, TTSError
from src.config.settings import settings
from src.contracts.analysis_task import AnalysisTaskPayload, AnalysisTaskResult
from src.contracts.analysis_results import (
    AnalysisErrorReport,
    FinalAnalysisReport,
    V1ScoreSummary,
)
from src.contracts.timeline import MatchTimeline
from src.core.domain.team_policies import tldr_contains_hallucination
from src.core.observability import llm_debug_wrapper, set_correlation_id, clear_correlation_id
from src.core.metrics import (
    observe_analyze_e2e,
    chimera_riot_api_requests_total,
    mark_llm,
    mark_riot_429,
    chimera_external_api_errors_total,
    observe_request_latency,
    mark_request_outcome,
)
from src.core.scoring import generate_llm_input
from src.core.scoring.arena_v1_lite import detect_arena_rounds
from src.prompts.system_prompts import get_system_prompt
from src.contracts.v23_multi_mode_analysis import detect_game_mode
from src.tasks.celery_app import celery_app
import os as _os
from src.core.services.team_builds_enricher import (
    DataDragonClient,
    OPGGAdapter,
    TeamBuildsEnricher,
)

logger = logging.getLogger(__name__)


_TTS_MAX_CHARS = 220


def _compress_tts_text(text: str, limit: int) -> str:
    """Trim text to the target length without breaking sentences mid-way."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text

    sentences = re.split(r"(?<=[。！？.!?])", text)
    pieces: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{''.join(pieces)}{sentence}" if pieces else sentence
        if len(candidate) > limit:
            remaining = limit - len("".join(pieces))
            if remaining > 0:
                truncated = sentence[:remaining].rstrip("，、；:, ")
                if truncated:
                    pieces.append(truncated)
            break
        pieces.append(sentence)

    result = "".join(pieces).strip("；:, ")
    if result and not result.endswith(("。", "！", "？")):
        result = f"{result}。"
    return result


def _sanitize_tts_summary(raw: str, score_summary: V1ScoreSummary) -> str:
    """Remove markdown/换行并压缩长度，返回适合朗读的句子。"""
    fragments: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[#>*•\\-\\+\\s]+", "", stripped)
        stripped = stripped.replace("**", "")
        stripped = stripped.replace("*", "")
        stripped = stripped.strip()
        if stripped:
            fragments.append(stripped)

    if not fragments:
        return ""

    # 统一语气，每句话以句号结束
    sentences: list[str] = []
    for frag in fragments:
        frag = re.sub(r"\s{2,}", " ", frag).strip()
        frag = re.sub(r"^[-\u2022·•]+\s*", "", frag)
        frag = frag.rstrip("，,；;")
        if not frag:
            continue
        if not frag.endswith(("。", "！", "？")):
            frag = f"{frag}。"
        sentences.append(frag)

    if not sentences:
        return ""

    text = "".join(sentences)
    text = re.sub(r"[。]{2,}", "。", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=。)[-–—]\s*", "", text)
    text = re.sub(r"^[-–—]+\s*", "", text)
    text = _compress_tts_text(text, _TTS_MAX_CHARS)

    if text and len(text) >= 60:
        return text

    return ""


def _repair_arena_subject(text: str, champion_name: str | None, game_mode: str | None) -> str:
    """确保 Arena 播报主语使用英雄名，避免误读为“Arena”。"""
    if not text:
        return text
    gm = (game_mode or "").strip().lower()
    subject = (champion_name or "").strip()
    if gm != "arena" or not subject:
        return text

    # 常见标题替换，兼容大小写
    replacements: tuple[tuple[str, str], ...] = (
        ("Arena战况分析", f"{subject}战况分析"),
        ("Arena战报", f"{subject}战报"),
        ("Arena表现", f"{subject}表现"),
        ("Arena选手", subject),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # 若依然存在裸露的 Arena，则替换首个匹配
    lower = text.lower()
    idx = lower.find("arena")
    if idx != -1:
        text = f"{text[:idx]}{subject}{text[idx + len('arena'):]}"

    # 清理重复主语（例如 “Irelia战况分析：Irelia”）
    text = re.sub(
        rf"({re.escape(subject)}战况分析[：:])\s*{re.escape(subject)}",
        r"\1",
        text,
    )
    text = re.sub(
        rf"({re.escape(subject)}表现[：:])\s*{re.escape(subject)}",
        r"\1",
        text,
    )
    text = text.replace("：：", "：")
    return text


def _build_tts_fallback(
    score_summary: V1ScoreSummary,
    champion_name: str | None,
    game_mode: str | None,
) -> str:
    """Fallback 朗读模版：利用量化维度生成确定性摘要。"""
    dims = {
        "战斗": score_summary.combat_score,
        "经济": score_summary.economy_score,
        "团队": score_summary.teamplay_score,
        "生存": score_summary.survivability_score,
        "坦度": score_summary.tankiness_score,
        "伤害": score_summary.damage_composition_score,
    }

    best_label, best_value = max(dims.items(), key=lambda item: item[1])
    worst_label, worst_value = min(dims.items(), key=lambda item: item[1])

    raw = score_summary.raw_stats or {}
    subject = (
        champion_name or raw.get("champion_name") or raw.get("champion") or "这位选手"
    ).strip()

    mode = (game_mode or raw.get("game_mode") or "").strip().lower()
    if mode == "arena":
        scene = "在Arena赛场"
    elif mode in {"sr", "summoners_rift"}:
        scene = "在召唤师峡谷"
    elif mode == "aram":
        scene = "在嚎哭深渊"
    else:
        scene = ""

    placement = raw.get("placement")
    placement_text = ""
    if isinstance(placement, (int, float)) and placement:
        placement_text = f"第{int(placement)}名，"

    prefix = f"{subject}{scene}" if scene else subject
    base = f"{prefix}{placement_text}综合评分{score_summary.overall_score:.0f}分。"
    contrast = f"优势在{best_label}{best_value:.0f}，短板在{worst_label}{worst_value:.0f}。"

    if worst_label == "生存" or score_summary.survivability_score <= 45:
        advice = "建议延后进场、保留位移，先稳住存活再谋求反打。"
    elif worst_label == "经济":
        advice = "建议保证刷野与补刀节奏，别让经济掉速。"
    elif worst_label == "团队":
        advice = "建议多和队友沟通集火节奏，提升双人协同。"
    else:
        advice = "建议根据阵容先做试探再开启决胜操作。"

    return _compress_tts_text(f"{base}{contrast}{advice}", _TTS_MAX_CHARS)


class AnalyzeMatchTask(Task):
    """Custom Celery task class with adapter dependency injection.

    This pattern allows us to reuse database/API connections across task executions
    while maintaining testability through dependency injection.

    P4 Extensions:
    - LLM adapter for narrative generation (Gemini)
    - Webhook adapter for Discord async responses

    P5 Extensions:
    - TTS adapter for voice narration (豆包 TTS)
    """

    _db_adapter: DatabaseAdapter | None = None
    _riot_adapter: RiotAPIAdapter | None = None
    _llm_adapter: GeminiLLMAdapter | None = None
    _webhook_adapter: DiscordWebhookAdapter | None = None
    _tts_adapter: TTSAdapter | None = None
    _cache_adapter: RedisAdapter | None = None

    @property
    def db_adapter(self) -> DatabaseAdapter:
        """Lazy-init database adapter (connection pooling)."""
        if self._db_adapter is None:
            self._db_adapter = DatabaseAdapter()
            # Connection will be established on first use
        return self._db_adapter

    @property
    def riot_adapter(self) -> RiotAPIAdapter:
        """Lazy-init Riot API adapter (Cassiopeia with rate limiting)."""
        if self._riot_adapter is None:
            self._riot_adapter = RiotAPIAdapter()
        return self._riot_adapter

    @property
    def llm_adapter(self) -> GeminiLLMAdapter:
        """Lazy-init Gemini LLM adapter for narrative generation."""
        if self._llm_adapter is None:
            self._llm_adapter = GeminiLLMAdapter()
        return self._llm_adapter

    @property
    def webhook_adapter(self) -> DiscordWebhookAdapter:
        """Lazy-init Discord webhook adapter for async responses."""
        if self._webhook_adapter is None:
            self._webhook_adapter = DiscordWebhookAdapter()
        return self._webhook_adapter

    @property
    def tts_adapter(self) -> TTSAdapter:
        """Lazy-init TTS adapter for voice narration (P5)."""
        if self._tts_adapter is None:
            self._tts_adapter = TTSAdapter()
        return self._tts_adapter

    @property
    def cache_adapter(self) -> RedisAdapter:
        """Lazy-init Redis adapter for caching."""
        if self._cache_adapter is None:
            self._cache_adapter = RedisAdapter()
        return self._cache_adapter


async def _run_analysis_workflow(
    self: AnalyzeMatchTask,
    task_payload: AnalysisTaskPayload,
    task_start: float,
) -> dict[str, Any]:
    """Single async context for all async operations.

    Runs all async operations in a single event loop to avoid 'Event loop is closed'
    errors in Celery worker threads.
    """
    # Result tracking
    result = AnalysisTaskResult(success=False, match_id=task_payload.match_id)

    try:
        # Bind correlation id for end-to-end tracing across async calls
        try:
            _cid = (
                task_payload.correlation_id
                or f"{task_payload.match_id}:{int(time.time()*1000)%100000}"
            )
            set_correlation_id(_cid)
            v1_summary.raw_stats = rs
        except Exception:
            pass
        # ===== STAGE 1: Fetch MatchTimeline =====
        fetch_start = time.perf_counter()
        timeline_data = await _fetch_timeline_with_observability(
            self.riot_adapter,
            task_payload.match_id,
            task_payload.region,
        )
        if timeline_data is None:
            result.error_stage = "fetch"
            result.error_message = "Failed to fetch MatchTimeline from Riot API"
            try:
                chimera_riot_api_requests_total.labels(endpoint="timeline", status="error").inc()
            except Exception:
                pass
            return result.model_dump()
        result.fetch_duration_ms = (time.perf_counter() - fetch_start) * 1000

        # ===== STAGE 2: Fetch Match Details =====
        try:
            match_details = await self.riot_adapter.get_match_details(
                task_payload.match_id, task_payload.region
            )
        except Exception:
            match_details = None
        # Fallback: try cached match_data from DB if live details unavailable
        if not match_details:
            try:
                await self.db_adapter.connect()
                cached = await self.db_adapter.get_match_data(task_payload.match_id)
                match_details = (cached or {}).get("match_data") if cached else None
            except Exception:
                match_details = None
            finally:
                try:
                    await self.db_adapter.disconnect()
                except Exception:
                    pass

        # ===== STAGE 3: Execute V1 Scoring =====
        scoring_start = time.perf_counter()
        timeline = MatchTimeline(**timeline_data)
        analysis_output = generate_llm_input(timeline, match_details)
        result.scoring_duration_ms = (time.perf_counter() - scoring_start) * 1000

        # ===== STAGE 4: Persist Results =====
        save_start = time.perf_counter()
        # If still no match_details, synthesize minimal structure to allow persistence & downstream rendering
        if not match_details:
            match_details = {
                "metadata": {"matchId": task_payload.match_id},
                "info": {"participants": []},
            }
        try:
            await self.db_adapter.connect()
            ok1 = await self.db_adapter.save_match_data(
                task_payload.match_id,
                match_details,
                timeline_data,
            )
            if not ok1:
                logger.warning("save_match_data degraded: proceeding without DB match_data upsert")

            ok2 = await _save_analysis_with_observability(
                self.db_adapter,
                task_payload.match_id,
                task_payload.puuid,
                analysis_output.model_dump(mode="json"),
                task_payload.region,
                result.scoring_duration_ms,
            )
            if not ok2:
                result.error_stage = "save"
                result.error_message = "Failed to save analysis result to database"
                return result.model_dump()
        finally:
            try:
                await self.db_adapter.disconnect()
            except Exception:
                pass
        result.save_duration_ms = (time.perf_counter() - save_start) * 1000
        result.score_data_saved = True

        # ===== Resolve target metadata =====
        participant_id = timeline.get_participant_by_puuid(task_payload.puuid)
        # Fallback: derive participant_id from match_details if timeline mapping is missing
        if participant_id is None and match_details and "info" in match_details:
            try:
                _parts = match_details.get("info", {}).get("participants", []) or []
                _p = next(
                    (p for p in _parts if str(p.get("puuid", "")) == str(task_payload.puuid)), None
                )
                if _p is not None:
                    _pid = _p.get("participantId")
                    if _pid is not None:
                        participant_id = int(_pid)
            except Exception:
                participant_id = None
        summoner_name = "Unknown"
        champion_name = "Unknown"
        champion_name_zh = "Unknown"
        champion_id = 0
        match_result: str = "defeat"
        champion_assets_url = ""

        # Match ID cross-check
        timeline_match_id = timeline_data.get("metadata", {}).get("matchId", "")
        details_match_id = (
            match_details.get("metadata", {}).get("matchId", "") if match_details else ""
        )
        if timeline_match_id and details_match_id and timeline_match_id != details_match_id:
            logger.error(
                "🚨 CRITICAL: Match ID mismatch! Timeline: %s | Details: %s | Expected: %s",
                timeline_match_id,
                details_match_id,
                task_payload.match_id,
            )
            result.error_stage = "validation"
            result.error_message = (
                "Match ID mismatch: Timeline vs Details API returned different matches"
            )
            return result.model_dump()

        if match_details and "info" in match_details:
            participants = match_details["info"].get("participants", [])
            for p in participants:
                if p.get("puuid") == task_payload.puuid:
                    name_core = (
                        p.get("riotIdGameName") or p.get("summonerName") or p.get("gameName")
                    )
                    name_tag = p.get("riotIdTagline") or p.get("tagLine")
                    if name_core and name_tag:
                        summoner_name = f"{name_core}#{name_tag}"
                    elif name_core:
                        summoner_name = str(name_core)
                    champion_name = p.get("championName") or "Unknown"
                    champion_id = int(p.get("championId", 0) or 0)
                    details_win = p.get("win", False)
                    match_result = "victory" if details_win else "defeat"
                    if participant_id is None:
                        pid = p.get("participantId")
                        if pid is not None:
                            try:
                                participant_id = int(pid)
                            except (TypeError, ValueError):
                                participant_id = None
                    break

        # Champion asset URL (best-effort)
        if champion_id:
            try:
                async with DDragonAdapter() as ddrag:
                    c = await ddrag.get_champion_by_id(champion_id)
                    if c and c.get("image_url"):
                        champion_assets_url = str(c["image_url"])
            except Exception:
                pass

        # ===== Build V1 summary for view + emotion =====
        player_score = None
        if participant_id is not None:
            for ps in analysis_output.player_scores:
                if ps.participant_id == participant_id:
                    player_score = ps
                    break
        # Secondary heuristic: match by champion name if participant mapping failed
        if (
            player_score is None
            and analysis_output.player_scores
            and champion_name
            and match_details
        ):
            try:
                # Build pid->champion map from match_details
                _parts = match_details.get("info", {}).get("participants", []) or []
                _pid_by_champ = {
                    str(p.get("championName", "")): int(p.get("participantId", 0) or 0)
                    for p in _parts
                }
                _pid_guess = _pid_by_champ.get(str(champion_name))
                if _pid_guess:
                    for ps in analysis_output.player_scores:
                        if ps.participant_id == _pid_guess:
                            player_score = ps
                            break
            except Exception:
                pass

        v1_summary = V1ScoreSummary(
            combat_score=(player_score.combat_efficiency if player_score else 0.0),
            economy_score=(player_score.economic_management if player_score else 0.0),
            vision_score=(player_score.vision_control if player_score else 0.0),
            objective_score=(player_score.objective_control if player_score else 0.0),
            teamplay_score=(player_score.team_contribution if player_score else 0.0),
            growth_score=(player_score.growth_score if player_score else 0.0),
            tankiness_score=(player_score.tankiness_score if player_score else 0.0),
            damage_composition_score=(
                player_score.damage_composition_score if player_score else 0.0
            ),
            survivability_score=(player_score.survivability_score if player_score else 0.0),
            cc_contribution_score=(player_score.cc_contribution_score if player_score else 0.0),
            overall_score=(player_score.total_score if player_score else 0.0),
            raw_stats=(player_score.raw_stats if player_score else {}),
        )

        # Guard: if all core dimensions are zero but we have a participant_id,
        # attempt to backfill from the exact participant entry in analysis_output
        try:
            core_dims = [
                v1_summary.combat_score,
                v1_summary.economy_score,
                v1_summary.vision_score,
                v1_summary.objective_score,
                v1_summary.teamplay_score,
            ]
            if participant_id and all(float(x) == 0.0 for x in core_dims):
                _ps = next(
                    (
                        ps
                        for ps in analysis_output.player_scores
                        if ps.participant_id == participant_id
                    ),
                    None,
                )
                if _ps is not None:
                    v1_summary = V1ScoreSummary(
                        combat_score=_ps.combat_efficiency,
                        economy_score=_ps.economic_management,
                        vision_score=_ps.vision_control,
                        objective_score=_ps.objective_control,
                        teamplay_score=_ps.team_contribution,
                        growth_score=_ps.growth_score,
                        tankiness_score=_ps.tankiness_score,
                        damage_composition_score=_ps.damage_composition_score,
                        survivability_score=_ps.survivability_score,
                        cc_contribution_score=_ps.cc_contribution_score,
                        overall_score=_ps.total_score,
                        raw_stats=_ps.raw_stats,
                    )
        except Exception:
            pass

        # ===== Mode detection + Arena extras =====
        queue_id = match_details.get("info", {}).get("queueId", 420) if match_details else 420
        game_mode = detect_game_mode(queue_id)

        # Enrich raw_stats for view & emotion & prompt grounding
        try:
            rs = v1_summary.raw_stats or {}
            if champion_name and champion_name != "Unknown":
                rs.setdefault("champion_name", champion_name)
            if champion_name_zh and champion_name_zh != "Unknown":
                rs.setdefault("champion_name_zh", champion_name_zh)
            rs["queue_id"] = queue_id
            rs["game_mode"] = game_mode.mode
            rs["is_arena"] = game_mode.mode == "Arena"
            if game_mode.mode == "Arena" and match_details and "info" in match_details:
                t_parts = match_details["info"].get("participants", [])
                t_p = next((p for p in t_parts if p.get("puuid") == task_payload.puuid), None)
                if t_p and "placement" in t_p:
                    rs["placement"] = int(t_p.get("placement") or 0)

                # Augments + partner (best-effort)
                try:
                    from src.core.scoring.arena_v1_lite import analyze_arena_augments

                    aug_report = analyze_arena_augments(match_details, task_payload.puuid, None)
                    if getattr(aug_report, "augments_selected", None):
                        rs["arena_augments"] = list(aug_report.augments_selected)
                except Exception:
                    pass

                try:
                    partner = None
                    if t_p and "subteamId" in t_p:
                        partner = next(
                            (
                                p
                                for p in t_parts
                                if p.get("subteamId") == t_p.get("subteamId")
                                and p.get("puuid") != t_p.get("puuid")
                            ),
                            None,
                        )
                    if partner:
                        rs["arena_partner_champion"] = partner.get("championName")
                        if partner.get("summonerName"):
                            rs["arena_partner_name"] = partner.get("summonerName")
                except Exception:
                    pass

                # Rounds (best-effort)
                try:
                    rounds = detect_arena_rounds(timeline_data, task_payload.puuid)
                    rs["arena_rounds"] = [
                        {
                            "n": r.round_number,
                            "r": r.round_result,
                            "dd": r.damage_dealt,
                            "dt": r.damage_taken,
                            "k": r.kills,
                            "d": r.deaths,
                            "pos": r.positioning_score,
                        }
                        for r in rounds
                    ]
                    if rounds:
                        best = max(rounds, key=lambda x: (x.kills, x.damage_dealt))
                        worst = max(rounds, key=lambda x: (x.deaths, x.damage_taken))
                        rs["arena_key_rounds"] = {
                            "best": {
                                "n": best.round_number,
                                "k": best.kills,
                                "dd": best.damage_dealt,
                                "r": best.round_result,
                            },
                            "worst": {
                                "n": worst.round_number,
                                "d": worst.deaths,
                                "dt": worst.damage_taken,
                                "r": worst.round_result,
                            },
                        }
                except Exception:
                    pass

                # Duo synergy tip (very light heuristic)
                try:
                    me_champ = champion_name
                    pa_champ = rs.get("arena_partner_champion")
                    tank = {"Malphite", "Ornn", "Shen", "Braum", "Sion", "Zac", "Sejuani"}
                    if pa_champ:
                        if (me_champ in tank) != (pa_champ in tank):
                            rs["arena_duo_tip"] = "前排+后排分工清晰，连招更容易。保持先手节奏。"
                        elif me_champ in tank and pa_champ in tank:
                            rs["arena_duo_tip"] = "双前排容错高，但缺收割。考虑增强控制/留人。"
                        else:
                            rs["arena_duo_tip"] = "双输出爆发高，缺前排。注意等控制交掉后再进场。"
                except Exception:
                    pass

            elif game_mode.mode == "SR" and participant_id is not None and match_details:
                try:
                    from src.core.services.sr_enrichment import extract_sr_enrichment

                    sr_extra = extract_sr_enrichment(
                        timeline_data, match_details, int(participant_id)
                    )
                    if sr_extra:
                        rs["sr_enrichment"] = sr_extra
                except Exception:
                    pass

                # Teamfight summaries (lightweight, best-effort)
                try:
                    from src.core.services.teamfight_reconstructor import (
                        extract_teamfight_summaries,
                    )

                    tf_lines = extract_teamfight_summaries(timeline_data, match_details)
                    if tf_lines:
                        rs.setdefault("sr_enrichment", {})["teamfight_paths"] = tf_lines
                except Exception:
                    pass
        except Exception:
            pass

        # ===== STAGE 4: LLM Narrative =====
        tts_audio_url: str | None = None

        try:
            # Ensure Redis connected (best-effort)
            await _ensure_redis_connection(self.cache_adapter)

            # Prepare LLM input with target player focus
            llm_input = analysis_output.model_dump(mode="json")
            if participant_id is not None and player_score is not None:
                llm_input["target_participant_id"] = participant_id
                target_payload = player_score.model_dump(mode="json")
                if summoner_name:
                    target_payload["summoner_name"] = summoner_name
                if champion_name:
                    target_payload["champion_name"] = champion_name
                    target_payload["champion_name_zh"] = champion_name_zh
                target_payload["match_result"] = match_result
                llm_input["target_player"] = target_payload
                llm_input["target_summoner_name"] = summoner_name
                llm_input["target_champion_name"] = champion_name
                llm_input["target_champion_name_zh"] = champion_name_zh

                # Add Arena extras (placement/augments/partner)
                try:
                    extras = v1_summary.raw_stats or {}
                    if extras.get("placement"):
                        target_payload["arena_placement"] = extras.get("placement")
                    if extras.get("arena_augments"):
                        target_payload["arena_augments"] = list(extras.get("arena_augments") or [])
                    if extras.get("arena_partner_champion"):
                        target_payload["arena_partner_champion"] = extras.get(
                            "arena_partner_champion"
                        )
                    # Provide per-round details for stronger grounding
                    if extras.get("arena_rounds"):
                        target_payload["arena_rounds"] = list(extras.get("arena_rounds") or [])
                except Exception:
                    pass
                # SR extras to LLM
                try:
                    extras = v1_summary.raw_stats or {}
                    if extras.get("sr_enrichment"):
                        target_payload["sr_enrichment"] = extras.get("sr_enrichment")
                except Exception:
                    pass

            # Prompt selection by mode
            prompt_mapping = {
                "Arena": "arena_v1",
                "ARAM": "aram_v1",
                # Switch Summoner's Rift default to narrative storytelling (v2)
                "SR": "v2_storytelling",
                "Fallback": "v2_storytelling",
            }
            prompt_version = prompt_mapping.get(game_mode.mode, "v1_analytical")
            system_prompt = get_system_prompt(prompt_version)
            logger.info(
                "🎮 Game mode detected: %s (queue_id=%d) | Using prompt: %s",
                game_mode.mode,
                queue_id,
                prompt_version,
            )

            llm_start = time.perf_counter()
            narrative = await _generate_narrative_with_cache(
                self.llm_adapter,
                self.cache_adapter,
                llm_input,
                system_prompt,
            )

            # Enforce Discord-safe length
            def _truncate_for_discord(text: str, limit: int = 1800) -> str:
                t = (text or "").strip()
                return t if len(t) <= limit else t[:limit]

            narrative = _truncate_for_discord(narrative, 1800)

            # ===== Optional: Full-token TL;DR (prepend) =====
            try:
                if (
                    _os.getenv("TEAM_FULL_TOKEN_MODE", "").lower() in ("1", "true", "yes", "on")
                    and match_details
                ):
                    # Build compact full-context payload (10 players + objectives)
                    players = []
                    ps_index = {int(ps.participant_id): ps for ps in analysis_output.player_scores}
                    parts = match_details.get("info", {}).get("participants", [])
                    for p in parts:
                        pid = int(p.get("participantId", 0) or 0)
                        ps = ps_index.get(pid)
                        if not ps:
                            continue
                        players.append(
                            {
                                "pid": pid,
                                "tid": 100 if pid <= 5 else 200,
                                "name": p.get("riotIdGameName")
                                or p.get("summonerName")
                                or p.get("gameName"),
                                "champ": p.get("championName"),
                                "combat": ps.combat_efficiency,
                                "econ": ps.economic_management,
                                "vision": ps.vision_control,
                                "obj": ps.objective_control,
                                "team": ps.team_contribution,
                                "overall": ps.total_score,
                            }
                        )
                    info = match_details.get("info", {})
                    # Use duration from analysis_output (already validated and correct)
                    # This prevents context loss issues in distributed async tasks
                    duration_min = analysis_output.game_duration_minutes

                    # Contract validation: Prevent LLM hallucination from zero duration
                    if duration_min <= 0:
                        logger.warning(
                            "tldr_skipped_invalid_duration",
                            extra={"duration_min": duration_min, "match_id": match_id},
                        )
                        # Skip TLDR generation if duration is invalid
                        raise ValueError(f"Invalid duration for TLDR: {duration_min}")

                    payload = {
                        "match_id": info.get("gameId")
                        or match_details.get("metadata", {}).get("matchId"),
                        "duration_min": duration_min,
                        "players": players,
                        "target_pid": int(participant_id or 0) if participant_id else 0,
                        "mode": game_mode.mode,
                    }
                    logger.info(
                        "tldr_payload_constructed",
                        extra={
                            "duration_min": duration_min,
                            "players_count": len(players),
                            "match_id": payload.get("match_id"),
                        },
                    )
                    # Minimal TL;DR system prompt (Chinese, 3 lines max)
                    tldr_sys = (
                        "你是英雄联盟战报压缩器。严格用中文输出一段不超过3行的 TL;DR，总结目标玩家在团队相对维度上的表现，"
                        "格式示例：‘强项 +X% | 弱项 -Y% | 关键建议’。不要重复原文，不要超3行。"
                    )
                    tldr_text = await self.llm_adapter.analyze_match(payload, tldr_sys)
                    if tldr_text:
                        tldr_text = tldr_text.strip()

                        # LLM输出校验：统一使用 team_policies 的幻觉检测
                        if tldr_contains_hallucination(tldr_text):
                            logger.warning(
                                "tldr_hallucination_detected",
                                extra={
                                    "tldr_text": tldr_text[:200],
                                    "match_id": match_id,
                                    "duration_min": duration_min,
                                },
                            )
                            # Skip invalid TLDR to avoid misleading users
                            raise ValueError(f"TLDR hallucination detected: {tldr_text[:50]}")

                        if len(tldr_text) > 400:
                            tldr_text = tldr_text[:400]
                        narrative = f"🎯 TLDR\n{tldr_text}\n\n---\n" + narrative
                        logger.info(
                            "tldr_generated_successfully",
                            extra={"tldr_length": len(tldr_text), "match_id": match_id},
                        )
            except Exception:
                # TL;DR is optional; ignore failures
                pass

            # Metrics: LLM success
            mark_llm(status="success", model=settings.gemini_model)

            # Emotion mapping (Arena-aware via emotion_mapper)
            from src.core.services.emotion_mapper import map_score_to_emotion

            emotion = map_score_to_emotion(v1_summary)

            # Champion drift heuristic
            try:
                if champion_name_zh and champion_name_zh not in narrative:
                    suspicious_aliases = ("加里奥", "Galio")
                    if any(a in narrative for a in suspicious_aliases):
                        logger.warning(
                            "Champion drift suspicion: target_zh=%s target_en=%s narrative_contains=%s | match_id=%s",
                            champion_name_zh,
                            champion_name,
                            ",".join([a for a in suspicious_aliases if a in narrative]),
                            task_payload.match_id,
                        )
            except Exception:
                pass

            # Save narrative
            base_llm_metadata: dict[str, Any] = {
                "emotion": emotion,
                "model": settings.gemini_model,
                "cache": True,
            }

            try:
                await self.db_adapter.connect()
                await self.db_adapter.update_llm_narrative(
                    match_id=task_payload.match_id,
                    llm_narrative=narrative,
                    llm_metadata=base_llm_metadata,
                )
            finally:
                try:
                    await self.db_adapter.disconnect()
                except Exception:
                    pass

            result.llm_duration_ms = (time.perf_counter() - llm_start) * 1000

            # ===== STAGE 4.5: TTS (optional) =====
            tts_start = time.perf_counter()
            tts_text: str | None = None
            try:
                # Generate TTS-optimized summary (200-300 chars) to prevent timeout
                tts_text = await _generate_tts_summary(
                    self.llm_adapter,
                    narrative,
                    v1_summary,
                    emotion,
                    champion_name,
                    (game_mode.mode if game_mode else None),
                )

                # Silent degradation: Skip TTS if summary generation failed
                if tts_text is None:
                    logger.info(
                        "TTS summary generation returned None, skipping TTS synthesis (silent degradation)"
                    )
                    result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000
                else:
                    tts_audio_url = await _synthesize_tts_with_observability(
                        self.tts_adapter, tts_text, emotion
                    )
                    if tts_audio_url:
                        enriched_metadata = {
                            **base_llm_metadata,
                            "tts_summary": tts_text,
                            "tts_audio_url": tts_audio_url,
                        }
                        try:
                            await self.db_adapter.connect()
                            await self.db_adapter.update_llm_narrative(
                                match_id=task_payload.match_id,
                                llm_narrative=narrative,
                                llm_metadata=enriched_metadata,
                            )
                        finally:
                            try:
                                await self.db_adapter.disconnect()
                            except Exception:
                                pass
                        logger.info(f"TTS synthesis succeeded: {tts_audio_url}")
                    else:
                        logger.info("TTS synthesis returned None (graceful degradation)")
                        try:
                            await self.db_adapter.connect()
                            await self.db_adapter.update_llm_narrative(
                                match_id=task_payload.match_id,
                                llm_narrative=narrative,
                                llm_metadata={
                                    **base_llm_metadata,
                                    "tts_summary": tts_text,
                                },
                            )
                        finally:
                            try:
                                await self.db_adapter.disconnect()
                            except Exception:
                                pass
                    result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000
            except TTSError as e:
                logger.warning(f"TTS synthesis failed (degraded): {e}", exc_info=True)
                if tts_text:
                    try:
                        await self.db_adapter.connect()
                        await self.db_adapter.update_llm_narrative(
                            match_id=task_payload.match_id,
                            llm_narrative=narrative,
                            llm_metadata={
                                **base_llm_metadata,
                                "tts_summary": tts_text,
                            },
                        )
                    finally:
                        try:
                            await self.db_adapter.disconnect()
                        except Exception:
                            pass
                result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000

        except GeminiAPIError as e:
            # LLM failed → fallback narrative
            logger.warning(f"LLM failed; using fallback narrative: {e}")
            mark_llm(status="error", model=settings.gemini_model)
            from src.core.fallbacks.llm_fallback import generate_fallback_narrative

            narrative = generate_fallback_narrative(analysis_output.model_dump(mode="json"))
            from src.core.services.emotion_mapper import map_score_to_emotion

            emotion = map_score_to_emotion(v1_summary)
            try:
                await self.db_adapter.connect()
                await self.db_adapter.update_llm_narrative(
                    match_id=task_payload.match_id,
                    llm_narrative=narrative,
                    llm_metadata={
                        "emotion": emotion,
                        "model": "fallback-template",
                        "fallback": True,
                        "source_error": str(e),
                    },
                )
            finally:
                try:
                    await self.db_adapter.disconnect()
                except Exception:
                    pass
            mark_llm(status="fallback", model=settings.gemini_model)
            result.llm_duration_ms = (time.perf_counter() - fetch_start) * 1000

        # ===== STAGE 5: Webhook =====
        webhook_start = time.perf_counter()
        try:
            # Normalize emotion to Chinese tag for contract
            sentiment_map: dict[str, str] = {
                "excited": "激动",
                "positive": "鼓励",
                "proud": "鼓励",
                "motivational": "鼓励",
                "encouraging": "鼓励",
                "mocking": "嘲讽",
                "critical": "遗憾",
                "concerned": "遗憾",
                "disappointed": "遗憾",
                "sympathetic": "遗憾",
                "neutral": "平淡",
                "analytical": "平淡",
                "reflective": "平淡",
                "calm": "平淡",
                "cautious": "平淡",
            }
            sentiment_tag: str = sentiment_map.get(locals().get("emotion", "neutral"), "平淡")

            processing_duration_ms = (time.perf_counter() - task_start) * 1000
            algorithm_version = "v1"

            observability_payload: dict[str, Any] = {
                "session_id": str(task_payload.correlation_id or task_payload.match_id),
                "execution_branch_id": f"analyze_{algorithm_version}",
            }
            metrics_map = {
                "fetch_ms": result.fetch_duration_ms,
                "scoring_ms": result.scoring_duration_ms,
                "save_ms": result.save_duration_ms,
                "llm_ms": result.llm_duration_ms,
                "tts_ms": result.tts_duration_ms,
            }
            for key, value in metrics_map.items():
                if value is None:
                    continue
                try:
                    observability_payload[key] = float(value)
                except Exception:
                    continue
            observability_payload["overall_ms"] = float(processing_duration_ms)
            try:
                raw_stats_payload = dict(v1_summary.raw_stats or {})
                raw_stats_payload["observability"] = observability_payload
                v1_summary.raw_stats = raw_stats_payload
            except Exception:
                logger.warning(
                    "attach_observability_failed",
                    extra={"match_id": task_payload.match_id},
                )

            builds_summary_text: str | None = None
            builds_metadata: dict[str, Any] | None = None
            try:
                if str(_os.getenv("CHIMERA_TEAM_BUILD_ENRICH", "0")).lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }:
                    dd_client = DataDragonClient(locale=_os.getenv("CHIMERA_LOCALE", "zh_CN"))
                    opgg_adapter = None
                    if str(_os.getenv("CHIMERA_OPGG_ENABLED", "0")).lower() in {
                        "1",
                        "true",
                        "yes",
                        "on",
                    }:
                        try:
                            opgg_adapter = OPGGAdapter()
                        except Exception:
                            opgg_adapter = None

                enricher = TeamBuildsEnricher(dd_client, opgg_adapter)
                b_text, b_payload = enricher.build_summary_for_target(
                    match_details or {},
                    target_puuid=task_payload.puuid,
                    target_name=summoner_name,
                    enable_opgg=bool(opgg_adapter and opgg_adapter.available),
                )
                if b_text:
                    builds_summary_text = b_text[:600]
                if b_payload:
                    builds_metadata = dict(b_payload)
                    builds_metadata.pop("resolved_puuid", None)
                    builds_metadata.setdefault("visuals", [])
            except Exception as enrich_err:
                logger.warning(
                    "personal_builds_enrich_failed",
                    extra={
                        "match_id": task_payload.match_id,
                        "puuid": task_payload.puuid,
                        "error": str(enrich_err),
                    },
                )

            report = FinalAnalysisReport(
                match_id=task_payload.match_id,
                match_result=match_result,  # type: ignore[arg-type]
                summoner_name=summoner_name,
                champion_name=champion_name,
                champion_id=champion_id,
                ai_narrative_text=locals().get("narrative", ""),
                llm_sentiment_tag=sentiment_tag,  # type: ignore[arg-type]
                v1_score_summary=v1_summary,
                champion_assets_url=champion_assets_url,
                processing_duration_ms=processing_duration_ms,
                algorithm_version=algorithm_version,
                tts_audio_url=locals().get("tts_audio_url", None),
                trace_task_id=str(getattr(self.request, "id", "") or ""),
                builds_summary_text=builds_summary_text,
                builds_metadata=builds_metadata,
            )

            webhook_success = await _send_final_report_webhook(
                self.webhook_adapter,
                task_payload.application_id,
                task_payload.interaction_token,
                report,
                task_payload.channel_id,
            )
            if not webhook_success:
                result.error_stage = "webhook"
                result.error_message = "Discord webhook delivery failed (15min token expired?)"
                result.webhook_delivered = False
            else:
                result.webhook_delivered = True
            result.webhook_duration_ms = (time.perf_counter() - webhook_start) * 1000

        except DiscordWebhookError as e:
            result.error_stage = "webhook"
            result.error_message = f"Webhook error: {e}"
            result.webhook_delivered = False
            result.webhook_duration_ms = (time.perf_counter() - webhook_start) * 1000
            try:
                chimera_external_api_errors_total.labels("discord", "webhook_error").inc()
            except Exception:
                pass

        # ===== SUCCESS =====
        try:
            await self.db_adapter.connect()
            await self.db_adapter.update_analysis_status(
                task_payload.match_id, status="completed", error_message=None
            )
        finally:
            try:
                await self.db_adapter.disconnect()
            except Exception:
                pass

        result.success = True
        result.total_duration_ms = (time.perf_counter() - task_start) * 1000
        observe_analyze_e2e(
            total_ms=result.total_duration_ms,
            stages_ms={
                "fetch": result.fetch_duration_ms,
                "score": result.scoring_duration_ms,
                "save": result.save_duration_ms,
                "llm": result.llm_duration_ms,
                "webhook": result.webhook_duration_ms,
                "tts": result.tts_duration_ms,
            },
        )
        mark_request_outcome("analyze", "success")
        observe_request_latency("analyze", result.total_duration_ms / 1000.0)
        return result.model_dump()

    except RateLimitError as e:
        result.error_stage = "fetch"
        result.error_message = f"Rate limit exceeded, retry after {e.retry_after}s"
        mark_riot_429(endpoint="timeline")
        mark_request_outcome("analyze", "failed")
        raise

    except RiotAPIError as e:
        result.error_stage = "fetch"
        result.error_message = f"Riot API error: {e}"
        result.total_duration_ms = (time.perf_counter() - task_start) * 1000
        try:
            status = "error" if getattr(e, "status_code", None) != 429 else "rate_limited"
            chimera_riot_api_requests_total.labels(endpoint="timeline", status=status).inc()
        except Exception:
            pass
        mark_request_outcome("analyze", "failed")
        return result.model_dump()

    except Exception as e:
        result.error_stage = "unknown"
        result.error_message = f"Unexpected error: {e}"
        result.total_duration_ms = (time.perf_counter() - task_start) * 1000
        try:
            chimera_external_api_errors_total.labels("backend", "unexpected").inc()
        except Exception:
            pass
        mark_request_outcome("analyze", "failed")
        return result.model_dump()
    finally:
        # Ensure correlation id does not leak across tasks
        try:
            clear_correlation_id()
        except Exception:
            pass


@celery_app.task(
    bind=True,
    base=AnalyzeMatchTask,
    name="src.tasks.analysis_tasks.analyze_match_task",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(RateLimitError,),  # Auto-retry on 429
    retry_backoff=True,  # Exponential backoff
    retry_jitter=True,  # Add randomness to backoff
)
@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"task_type": "match_analysis", "layer": "celery_task"},
)
def analyze_match_task(
    self: AnalyzeMatchTask,
    *,
    application_id: str,
    interaction_token: str,
    channel_id: str,
    discord_user_id: str,
    puuid: str,
    match_id: str,
    region: str,
    match_index: int = 1,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Atomic task: Complete /讲道理 workflow (P3 + P4 integrated).

    This task implements the complete end-to-end backend workflow:
    1. Fetch MatchTimeline from Riot API (with 429 retry handling)
    2. Execute V1 Scoring Algorithm (pure domain logic)
    3. Persist results to match_analytics table
    4. Generate LLM narrative using Gemini (P4)
    5. Send async response to Discord via webhook (P4)

    Workflow States (tracked in match_analytics.status):
    - 'pending': Task queued
    - 'processing': Scoring in progress
    - 'analyzing': LLM inference in progress
    - 'completed': All stages succeeded, webhook delivered
    - 'failed': Any stage failed, error webhook sent

    Args:
        application_id: Discord application ID for webhook
        interaction_token: Discord interaction token (15min validity)
        channel_id: Discord channel ID
        discord_user_id: Discord user ID
        puuid: Riot PUUID
        match_id: Match ID to analyze
        region: Regional routing value
        match_index: Match index in history (1-based)
        correlation_id: Optional correlation ID for end-to-end tracing

    Returns:
        AnalysisTaskResult dictionary with metrics

    Raises:
        RateLimitError: If Riot API rate limit exceeded (triggers auto-retry)
        RiotAPIError: If API fetch fails (non-retryable)
        GeminiAPIError: If LLM inference fails (degrades to error webhook)
        DiscordWebhookError: If webhook delivery fails (logged but not re-raised)
    """
    # Reconstruct payload object for backward compatibility
    task_payload = AnalysisTaskPayload(
        application_id=application_id,
        interaction_token=interaction_token,
        channel_id=channel_id,
        discord_user_id=discord_user_id,
        puuid=puuid,
        match_id=match_id,
        region=region,
        match_index=match_index,
        correlation_id=correlation_id,
    )

    # Track task execution time
    task_start = time.perf_counter()

    # Run entire workflow using get_event_loop() for Celery worker compatibility
    # CRITICAL: Do NOT use asyncio.run() in Celery workers as it creates/closes loops
    # which causes "Event loop is closed" errors on subsequent tasks
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no loop exists in current thread, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_run_analysis_workflow(self, task_payload, task_start))


# ===== Helper Functions with Observability =====


@llm_debug_wrapper(
    capture_result=False,  # Timeline data is large, skip logging
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "riot_api_fetch", "layer": "adapter"},
    warn_over_ms=2500,
)
async def _fetch_timeline_with_observability(
    riot_adapter: RiotAPIAdapter,
    match_id: str,
    region: str,
) -> dict[str, Any] | None:
    """Fetch MatchTimeline with observability wrapper.

    This wrapper ensures all API calls are logged for performance analysis.
    Cassiopeia handles retry logic internally.
    """
    return await riot_adapter.get_match_timeline(match_id, region)


@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "database_save", "layer": "adapter"},
    warn_over_ms=500,
)
async def _save_analysis_with_observability(
    db_adapter: DatabaseAdapter,
    match_id: str,
    puuid: str,
    score_data: dict[str, Any],
    region: str,
    processing_duration_ms: float | None,
) -> bool:
    """Save analysis result with observability wrapper."""
    return await db_adapter.save_analysis_result(
        match_id=match_id,
        puuid=puuid,
        score_data=score_data,
        region=region,
        status="completed",
        processing_duration_ms=processing_duration_ms,
    )


async def _ensure_db_connection(db_adapter: DatabaseAdapter) -> None:
    """Ensure database connection pool is initialized."""
    if db_adapter._pool is None:
        await db_adapter.connect()


async def _ensure_redis_connection(cache_adapter: RedisAdapter) -> None:
    """Ensure Redis client is connected (graceful on errors)."""
    try:
        if not await cache_adapter.health_check():
            await cache_adapter.connect()
    except Exception:
        # Degrade silently; caching is optional
        pass


# ===== P4 Helper Functions =====


@llm_debug_wrapper(
    capture_result=False,  # Narrative can be long, skip logging content
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "llm_inference", "layer": "adapter"},
    warn_over_ms=9000,
)
async def _generate_narrative_with_observability(
    llm_adapter: GeminiLLMAdapter,
    match_data: dict[str, Any],
    system_prompt: str,
) -> str:
    """Generate narrative with observability wrapper.

    Args:
        llm_adapter: Gemini LLM adapter
        match_data: Structured scoring data
        system_prompt: System instruction for LLM

    Returns:
        Generated narrative text
    """
    return await llm_adapter.analyze_match(match_data, system_prompt)


@llm_debug_wrapper(
    capture_result=False,  # Narrative can be long; skip full result content
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "llm_cache", "layer": "cache"},
    warn_over_ms=2000,
)
async def _generate_narrative_with_cache(
    llm_adapter: GeminiLLMAdapter,
    cache_adapter: RedisAdapter,
    match_data: dict[str, Any],
    system_prompt: str,
) -> str:
    """Return cached narrative when available; otherwise call LLM and cache.

    Cache key factors: model name + SHA256 of (system_prompt + sorted JSON of match_data).
    TTL: settings.redis_cache_ttl.
    """
    import hashlib
    import json as _json

    # Allow cache bypass via environment toggle (LLM_CACHE_ENABLED=false)
    cache_enabled = getattr(settings, "llm_cache_enabled", True)

    # Determine provider and model name
    if settings.openai_api_base and settings.openai_api_key:
        provider = "openai"
        model_name = settings.openai_model
    else:
        provider = "gemini"
        model_name = settings.gemini_model

    if not cache_enabled:
        # Directly invoke LLM without reading/writing cache (useful for prompt debugging)
        return await llm_adapter.analyze_match(match_data, system_prompt)

    # Build deterministic hash of inputs
    payload = {
        "provider": provider,
        "model": model_name,
        "system_prompt": system_prompt,
        "match_data": match_data,
    }
    serialized = _json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    cache_key = f"cache:llm:narrative:v1:{provider}:{model_name}:{digest}"

    # Try cache (graceful if Redis unavailable)
    try:
        cached = await cache_adapter.get(cache_key)
        if isinstance(cached, str) and cached:
            logger.info(f"LLM cache hit key={cache_key[:32]}…")
            return cached
    except Exception:
        pass

    # Miss → invoke LLM
    narrative = await llm_adapter.analyze_match(match_data, system_prompt)

    # Store in cache
    try:
        await cache_adapter.set(cache_key, narrative, ttl=settings.redis_cache_ttl)
        logger.info(f"LLM cache set key={cache_key[:32]}… ttl={settings.redis_cache_ttl}s")
    except Exception:
        pass

    return narrative


# ===== P5 Helper Functions =====


@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "tts_summary", "layer": "llm"},
    warn_over_ms=5000,
)
async def _generate_tts_summary(
    llm_adapter: GeminiLLMAdapter,
    full_narrative: str,
    score_summary: V1ScoreSummary,
    emotion: str | None,
    champion_name: str | None,
    game_mode: str | None,
) -> str | None:
    """Generate TTS-optimized summary from full narrative.

    Reduces full narrative (1800+ chars) to 200-300 chars suitable for voice synthesis,
    preventing TTS timeout while preserving key information.

    Args:
        llm_adapter: LLM adapter
        full_narrative: Full narrative text (may include TLDR)
        score_summary: Scoring data for fallback
        emotion: Emotion tag for context
        champion_name: Champion name for personalized fallback
        game_mode: Game mode label (e.g., \"Arena\", \"SR\")

    Returns:
        Summarized text (200-300 chars) for TTS, or None if generation fails
        (silent degradation per user requirement)

    Design:
        - Uses LLM to intelligently summarize narrative
        - Preserves: overall score, top strength, main weakness, key suggestion
        - Returns None on failure (no fallback text) for silent degradation
    """
    try:
        # TTS summary system prompt (Chinese, ultra-concise)
        tts_prompt = (
            "你是英雄联盟赛后语音播报生成器。将以下分析压缩为一段200-300字的语音播报文本，"
            "必须包含：综合评分、最大优势、最弱环节、核心建议。语气要自然、适合朗读。"
            f"\n\n原始分析:\n{full_narrative[:1500]}"  # Limit input to avoid token overflow
        )

        # Construct minimal payload for LLM
        payload = {
            "match_id": "tts_summary",
            "game_duration_minutes": 0,  # Not needed for summarization
            "player_scores": [],  # Not needed
        }

        summary_raw = await llm_adapter.analyze_match(payload, tts_prompt)
        if summary_raw and len(summary_raw) >= 50:
            if tldr_contains_hallucination(summary_raw):
                logger.warning(
                    "tts_summary_hallucination_detected",
                    extra={"summary_excerpt": summary_raw[:200]},
                )
                fallback_direct = _build_tts_fallback(score_summary, champion_name, game_mode)
                if fallback_direct:
                    logger.info(
                        "tts_summary_fallback_used",
                        extra={"summary_length": len(fallback_direct)},
                    )
                    return fallback_direct
                raise ValueError("TTS summary hallucination detected")

            processed = _sanitize_tts_summary(summary_raw, score_summary)
            if processed:
                processed = _repair_arena_subject(processed, champion_name, game_mode)
                if tldr_contains_hallucination(processed):
                    logger.warning(
                        "tts_summary_hallucination_detected_after_sanitize",
                        extra={"summary_excerpt": processed[:200]},
                    )
                else:
                    logger.info(
                        "tts_summary_generated",
                        extra={"summary_length": len(processed)},
                    )
                    return processed

            fallback_from_processed = _build_tts_fallback(score_summary, champion_name, game_mode)
            if fallback_from_processed:
                logger.info(
                    "tts_summary_fallback_used",
                    extra={"summary_length": len(fallback_from_processed)},
                )
                return fallback_from_processed

        # Fallback: Structured summary from score data
        raise ValueError("LLM summary too short or empty")

    except Exception as e:
        logger.warning(f"TTS summary generation failed, returning None for silent degradation: {e}")
        # 用户要求：若仍失败则直接跳过 TTS（静默降级）
        return None


@llm_debug_wrapper(
    capture_result=True,  # Log TTS URL for debugging
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "tts_synthesis", "layer": "adapter"},
    warn_over_ms=6000,
)
async def _synthesize_tts_with_observability(
    tts_adapter: TTSAdapter,
    narrative: str,
    emotion: str | None,
) -> str | None:
    """Synthesize TTS audio with observability wrapper.

    Args:
        tts_adapter: TTS adapter
        narrative: Narrative text to synthesize
        emotion: Emotion tag for voice modulation

    Returns:
        Public URL to audio file, or None if synthesis fails

    P5 Graceful Degradation:
        - Returns None on TTS service failures
        - Does not raise exceptions (wrapped in try/catch in caller)
        - Allows task to continue without TTS
    """
    return await tts_adapter.synthesize_speech_to_url(narrative, emotion)


@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "webhook_delivery", "layer": "adapter", "contract": "final_report"},
    warn_over_ms=1500,
)
async def _send_final_report_webhook(
    webhook_adapter: DiscordWebhookAdapter,
    application_id: str,
    interaction_token: str,
    report: FinalAnalysisReport,
    channel_id: str | None,
) -> bool:
    """Send FinalAnalysisReport via webhook (P5 contract)."""
    return await webhook_adapter.publish_match_analysis(
        application_id=application_id,
        interaction_token=interaction_token,
        analysis_report=report,
        channel_id=channel_id,
    )


@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "webhook_delivery", "layer": "adapter"},
    warn_over_ms=1500,
)
async def _send_analysis_webhook_with_observability(
    webhook_adapter: DiscordWebhookAdapter,
    application_id: str,
    interaction_token: str,
    match_id: str,
    narrative: str,
    score_data: dict[str, Any],
    emotion: str | None,
) -> bool:
    """Send analysis webhook with observability wrapper.

    Args:
        webhook_adapter: Discord webhook adapter
        application_id: Discord application ID
        interaction_token: Interaction token
        match_id: Match ID
        narrative: LLM-generated narrative
        score_data: Structured scoring data
        emotion: Emotion tag for TTS

    Returns:
        True if webhook delivery succeeded
    """
    return await webhook_adapter.send_match_analysis(
        application_id=application_id,
        interaction_token=interaction_token,
        match_id=match_id,
        narrative=narrative,
        score_data=score_data,
        emotion=emotion,
    )


async def _send_error_webhook_safe(
    webhook_adapter: DiscordWebhookAdapter,
    application_id: str,
    interaction_token: str,
    error_type: str,
    user_message: str,
) -> bool:
    """Send error webhook with graceful degradation (no exceptions raised).

    This function never raises exceptions - used for error recovery paths.

    Args:
        webhook_adapter: Discord webhook adapter
        application_id: Discord application ID
        interaction_token: Interaction token
        error_type: Error classification
        user_message: User-friendly error message

    Returns:
        True if delivery succeeded, False otherwise
    """
    try:
        return await webhook_adapter.send_error_message(
            application_id=application_id,
            interaction_token=interaction_token,
            error_type=error_type,
            user_friendly_message=user_message,
        )
    except Exception as e:
        # Log but don't raise - this is error recovery path
        logger = logging.getLogger(__name__)
        logger.error(f"Error webhook delivery failed: {e}", exc_info=True)
        return False


@llm_debug_wrapper(
    capture_result=True,
    capture_args=True,
    log_level="INFO",
    add_metadata={"operation": "webhook_delivery", "layer": "adapter", "contract": "error_report"},
)
async def _send_error_notification(
    webhook_adapter: DiscordWebhookAdapter,
    application_id: str,
    interaction_token: str,
    error_report: AnalysisErrorReport,
    channel_id: str | None,
) -> bool:
    """Send error notification via webhook using P5 contract."""
    try:
        return await webhook_adapter.send_error_notification(
            application_id=application_id,
            interaction_token=interaction_token,
            error_report=error_report,
            channel_id=channel_id,
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error webhook delivery failed: {e}", exc_info=True)
        return False
