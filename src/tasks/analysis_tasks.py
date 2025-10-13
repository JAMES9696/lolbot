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
from collections.abc import Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
import logging
import re
import threading
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

_match_guard_lock = threading.Lock()
_match_inflight: set[str] = set()

_SR_ENRICH_REASON_LABELS: dict[str, str] = {
    "non_sr_mode": "非召唤师峡谷赛局，跳过时间线增强",
    "timeline_missing": "Timeline 接口无响应",
    "timeline_missing_frames": "Timeline 数据缺失",
    "participant_not_resolved": "未能在 Timeline/Details 中定位目标选手",
    "participant_frame_missing": "Timeline 帧缺少目标选手数据",
    "details_missing": "Match Details 接口返回为空",
    "empty_enrichment": "Riot API 未返回时间线增强指标",
    "extraction_error": "提取增强指标时发生异常",
}


def diagnose_sr_enrichment_gap(
    *,
    game_mode: str | None,
    timeline_data: dict[str, Any] | None,
    match_details: dict[str, Any] | None,
    participant_id: int | None,
    sr_extra: Mapping[str, Any] | None,
    target_puuid: str,
    extraction_error: str | None = None,
) -> dict[str, Any]:
    """Diagnose why SR enrichment data is missing so downstream layers can react."""

    mode = (game_mode or "").upper()
    if mode != "SR":
        return {
            "state": "skipped",
            "reason": "non_sr_mode",
            "friendly_reason": _SR_ENRICH_REASON_LABELS["non_sr_mode"],
            "details": {"mode": mode or None},
        }

    # Enrichment is present -> report as available.
    if sr_extra:
        try:
            keys = sorted(str(k) for k in sr_extra)
        except Exception:
            keys = []
        return {
            "state": "available",
            "payload": {"keys": keys},
        }

    details: dict[str, Any] = {}

    info = (timeline_data or {}).get("info", {}) if isinstance(timeline_data, Mapping) else {}
    frames: list[dict[str, Any]] = []
    try:
        frames = list(info.get("frames") or [])
    except Exception:
        frames = []
    details["timeline_frames"] = len(frames)

    metadata = (
        (timeline_data or {}).get("metadata", {}) if isinstance(timeline_data, Mapping) else {}
    )
    md_participants = metadata.get("participants") or []
    try:
        details["puuid_in_timeline_metadata"] = target_puuid in md_participants
    except Exception:
        details["puuid_in_timeline_metadata"] = None

    try:
        info_participants = info.get("participants") or []
        timeline_puuids = {str(p.get("puuid")) for p in info_participants if isinstance(p, Mapping)}
        details["puuid_in_timeline_participants"] = target_puuid in timeline_puuids
    except Exception:
        details["puuid_in_timeline_participants"] = None

    details["has_match_details"] = bool(match_details)
    details["participant_resolved"] = participant_id is not None

    if isinstance(match_details, Mapping):
        try:
            md_parts = match_details.get("info", {}).get("participants", []) or []
            details["puuid_in_details"] = any(
                str(p.get("puuid")) == str(target_puuid) for p in md_parts if isinstance(p, Mapping)
            )
        except Exception:
            details["puuid_in_details"] = None

    reason = "empty_enrichment"
    if extraction_error:
        reason = "extraction_error"
        details["extraction_error"] = extraction_error[:256]
    elif not timeline_data:
        reason = "timeline_missing"
    elif details["timeline_frames"] == 0:
        reason = "timeline_missing_frames"
    elif participant_id is None:
        reason = "participant_not_resolved"
    else:
        try:
            has_frame = any(
                isinstance(frame.get("participantFrames"), Mapping)
                and str(participant_id) in frame.get("participantFrames", {})
                for frame in frames
            )
        except Exception:
            has_frame = False
        if not has_frame:
            reason = "participant_frame_missing"
        elif not match_details:
            reason = "details_missing"

    friendly = _SR_ENRICH_REASON_LABELS.get(reason, "原因未知")

    return {
        "state": "missing",
        "reason": reason,
        "friendly_reason": friendly,
        "details": details,
    }


async def _acquire_match_slot(match_id: str, poll_interval: float = 0.05) -> None:
    while True:
        with _match_guard_lock:
            if match_id not in _match_inflight:
                _match_inflight.add(match_id)
                return
        await asyncio.sleep(poll_interval)


def _release_match_slot(match_id: str) -> None:
    with _match_guard_lock:
        _match_inflight.discard(match_id)


@asynccontextmanager
async def match_execution_guard(match_id: str) -> Any:
    await _acquire_match_slot(match_id)
    try:
        yield
    finally:
        _release_match_slot(match_id)


def _reset_match_guard_state_for_tests() -> None:
    with _match_guard_lock:
        _match_inflight.clear()


_TTS_MAX_CHARS = 220
_TTS_PROMPT_DROP_LINES = (
    "数据加载受限",
    "仅显示基础评分",
    "暂无时间线增强数据",
    "暂无出装",
    "暂无符文",
    "AI 分析中",
    "正在对您的第",
    "预计耗时",
    "Task ID",
    "✅ 已开始在你的语音频道播报",
    "❌",
)
_TTS_DISALLOWED_OUTCOME_TOKENS = (
    "抱歉",
    "很抱歉",
    "无法生成",
    "无法提供",
    "请稍后",
    "请稍候",
    "请重试",
    "稍后重试",
    "数据为空",
    "数据异常",
    "暂无数据",
    "数据加载受限",
    "数据加载",
    "数据迷雾",
    "数据一片空白",
    "技术故障",
    "错误",
    "失败",
    "记录失效",
    "比赛未正常完成",
    "请检查比赛id",
    "请检查比赛ID",
    "确认这局是否正常",
    "0分综合评分",
)
_TTS_MIN_CHARS = 60
_TTS_MAX_CHARS_HARD = 230  # 降低以缩小与 _TTS_MAX_CHARS (220) 的差距
_TTS_SENTENCE_SPLIT = re.compile(r"[。！？!?]+")


@dataclass(slots=True)
class TtsSummaryOutcome:
    """Container for TTS summary generation result."""

    text: str
    source: str  # "llm" or "fallback"
    raw_excerpt: str | None = None
    processed_excerpt: str | None = None
    soft_hints: tuple[str, ...] = ()


def _compress_tts_text(text: str, limit: int) -> str:
    """Trim text to the target length without breaking sentences mid-way."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ""

    # 捕获带标点的句子，确保最多三句且总长度不超过 limit。
    segments = re.findall(r"[^。！？!?]+[。！？!?]?", normalized)
    pieces: list[str] = []
    current_len = 0
    for segment in segments:
        sentence = segment.strip()
        if not sentence:
            continue
        next_len = current_len + len(sentence)
        if next_len > limit:
            remaining = max(limit - current_len, 0)
            if remaining > 0:
                truncated = sentence[:remaining].rstrip("，、；:, ")
                if truncated:
                    if truncated[-1] not in "。！？!?":
                        truncated = f"{truncated}。"
                    pieces.append(truncated)
            break

        pieces.append(sentence)
        current_len = next_len
        if len(pieces) >= 3:
            break

    result = "".join(pieces).strip("；:, ")
    if result and result[-1] not in "。！？!?":
        result = f"{result}。"
    return result


def _cleanse_tts_narrative(text: str) -> str:
    """Remove placeholder lines that会误导 TTS 解说的上下文。"""

    if not text:
        return ""

    cleaned_lines: list[str] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(token.lower() in lowered for token in _TTS_PROMPT_DROP_LINES):
            continue
        cleaned_lines.append(line)
    sanitized = "\n".join(cleaned_lines).strip()
    for token in _TTS_DISALLOWED_OUTCOME_TOKENS:
        if token:
            sanitized = sanitized.replace(token, "")
    return sanitized


def _validate_tts_candidate(text: str) -> tuple[bool, tuple[str, ...]]:
    """Ensure TTS 摘要满足最小长度要求，其余交给播报本身。"""

    candidate = (text or "").strip()
    reasons: list[str] = []
    length = len(candidate)
    if length < _TTS_MIN_CHARS:
        reasons.append("too_short")
    if length > _TTS_MAX_CHARS_HARD:
        reasons.append("too_long")

    fatal = not candidate or length < _TTS_MIN_CHARS
    return (not fatal, tuple(reasons))


def _sanitize_tts_summary(raw: str, _score_summary: V1ScoreSummary | None = None) -> str:
    """Strip markdown符号，保留自然段落与原始语气。"""

    paragraphs: list[str] = []
    current: list[str] = []

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraph = " ".join(current).strip()
                if paragraph:
                    paragraphs.append(paragraph)
                current = []
            continue

        cleaned = re.sub(r"^[#>*•+\-\s]+", "", stripped)
        cleaned = cleaned.replace("**", "").replace("*", "")
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned:
            current.append(cleaned)

    if current:
        paragraph = " ".join(current).strip()
        if paragraph:
            paragraphs.append(paragraph)

    text = "\n\n".join(paragraphs).strip()

    # 移除禁用词（在压缩之前清理，确保长度计算准确）
    for token in _TTS_DISALLOWED_OUTCOME_TOKENS:
        if token:
            text = text.replace(token, "")

    return text.strip()


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
        text = f"{text[:idx]}{subject}{text[idx + len('arena') :]}"

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


def _mask_identifier(value: Any | None, keep: int = 4) -> str:
    """Return anonymized suffix for potentially sensitive identifiers."""

    if value is None:
        return "n/a"

    try:
        text = str(value).strip()
    except Exception:
        return "n/a"

    if not text:
        return "n/a"

    suffix = text[-keep:]
    return f"anon:{suffix}"


def _format_ms(value: float | int | None) -> str:
    """Format millisecond durations for appendix display."""

    if value is None:
        return "—"
    try:
        return f"{float(value):.0f}ms"
    except Exception:
        return "—"


def _build_llm_context(
    *,
    llm_input: Mapping[str, Any],
    target_payload: Mapping[str, Any] | None,
    v1_summary: V1ScoreSummary,
    match_id: str,
    region: str | None,
    queue_id: int,
    match_result: str | None,
    game_mode_label: str | None,
    correlation_id: str | None,
    discord_user_id: str | None,
    workflow_durations: Mapping[str, float | None],
) -> str:
    """Construct sanitized LLM context with appendix guidance."""

    def _as_float(raw: Any, default: float = 0.0) -> float:
        try:
            return float(raw)
        except Exception:
            return default

    def _fmt_score(value: Any) -> str:
        return f"{_as_float(value):.1f}"

    game_duration = _as_float(llm_input.get("game_duration_minutes"))
    target = target_payload or llm_input.get("target_player") or {}
    raw_stats = v1_summary.raw_stats or {}

    target_name = (
        target.get("summoner_name")
        or llm_input.get("target_summoner_name")
        or raw_stats.get("summoner_name")
        or "Unknown"
    )
    champion_zh = target.get("champion_name_zh") or raw_stats.get("champion_name_zh")
    champion_name = (
        target.get("champion_name")
        or llm_input.get("target_champion_name")
        or raw_stats.get("champion_name")
        or "Unknown"
    )
    champion_label = (
        f"{champion_zh} ({champion_name})"
        if champion_zh and champion_zh != champion_name
        else champion_name
    )

    score_map = {
        "Overall": target.get("total_score", v1_summary.overall_score),
        "Combat": target.get("combat_efficiency", v1_summary.combat_score),
        "Economy": target.get("economic_management", v1_summary.economy_score),
        "Objectives": target.get("objective_control", v1_summary.objective_score),
        "Vision": target.get("vision_control", v1_summary.vision_score),
        "Teamwork": target.get("team_contribution", v1_summary.teamplay_score),
    }

    kills = raw_stats.get("kills")
    deaths = raw_stats.get("deaths")
    assists = raw_stats.get("assists")
    cs_total = raw_stats.get("cs") or raw_stats.get("total_cs")
    cs_per_min = raw_stats.get("cs_per_min") or target.get("cs_per_min")
    kp = target.get("kill_participation") or raw_stats.get("kill_participation")
    vision_score = raw_stats.get("vision_score")
    damage_dealt = raw_stats.get("damage_dealt") or raw_stats.get("damage_dealt_to_champions")
    damage_taken = raw_stats.get("damage_taken")

    strengths = target.get("strengths") or []
    improvements = target.get("improvements") or []

    lines: list[str] = []
    lines.append("## Target Player Overview")
    lines.append(f"- Summoner: {target_name}")
    lines.append(f"- Champion: {champion_label}")
    lines.append(f"- Match Result: {match_result or 'unknown'}")
    lines.append(f"- Duration: {game_duration:.1f} 分钟")
    lines.append("")

    lines.append("## Performance Scores (0-100)")
    for label, value in score_map.items():
        lines.append(f"- {label}: {_fmt_score(value)}")
    lines.append("")

    metric_lines: list[str] = []
    if kills is not None and deaths is not None and assists is not None:
        metric_lines.append(f"K/D/A: {kills}/{deaths}/{assists}")
    if kp is not None:
        metric_lines.append(f"Kill Participation: {_as_float(kp):.1f}%")
    if cs_total is not None:
        if cs_per_min is not None:
            metric_lines.append(f"CS: {int(cs_total)} ({_as_float(cs_per_min):.1f}/min)")
        else:
            metric_lines.append(f"CS: {int(cs_total)}")
    if vision_score is not None:
        metric_lines.append(f"Vision Score: {_as_float(vision_score):.1f}")
    if damage_dealt is not None and damage_taken is not None:
        metric_lines.append(
            f"Damage (Dealt/Taken): {int(_as_float(damage_dealt))}/{int(_as_float(damage_taken))}"
        )

    if metric_lines:
        lines.append("## Key Metrics")
        for entry in metric_lines:
            lines.append(f"- {entry}")
        lines.append("")

    if strengths or improvements:
        lines.append("## Tags")
        if strengths:
            lines.append(f"- Strengths: {', '.join(strengths)}")
        if improvements:
            lines.append(f"- Improvements: {', '.join(improvements)}")
        lines.append("")

    blue_avg = llm_input.get("team_blue_avg_score")
    red_avg = llm_input.get("team_red_avg_score")
    if blue_avg is not None or red_avg is not None:
        lines.append("## Team Averages")
        if blue_avg is not None:
            lines.append(f"- Blue Team Avg Score: {_fmt_score(blue_avg)}")
        if red_avg is not None:
            lines.append(f"- Red Team Avg Score: {_fmt_score(red_avg)}")
        lines.append("")

    lines.append("## Appendix (Only consult the appendix if the answer requires extra detail.)")
    lines.append(f"- Match ID: {match_id}")
    lines.append(f"- Region: {region or 'n/a'}")
    lines.append(f"- Queue ID: {queue_id}")
    lines.append(f"- Game Mode: {game_mode_label or 'unknown'}")
    lines.append(f"- Correlation Tag: {_mask_identifier(correlation_id)}")
    lines.append(f"- Discord User: {_mask_identifier(discord_user_id)}")

    if workflow_durations:
        duration_parts = [f"{key}={_format_ms(value)}" for key, value in workflow_durations.items()]
        if duration_parts:
            lines.append(f"- Workflow Timings: {', '.join(duration_parts)}")

    try:
        player_count = len(llm_input.get("player_scores") or [])
    except Exception:
        player_count = 0
    if player_count:
        lines.append(f"- Player Scores Provided: {player_count}")

    context = "\n".join(lines).strip()
    if len(context) > 4000:
        context = f"{context[:4000]}\n(…truncated…)"
    return context


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
    scene = ""
    if mode == "arena":
        scene = "Arena"
    elif mode in {"sr", "summoners_rift"}:
        scene = "峡谷"
    elif mode == "aram":
        scene = "嚎哭深渊"

    opening = (
        f"{subject}{scene}本局综合{score_summary.overall_score:.0f}分，局面不利，需要稳住节奏先保发育。"
        if scene
        else f"{subject}本局综合{score_summary.overall_score:.0f}分，局面不利，需要稳住节奏先保发育。"
    )

    highlight = (
        f"亮点落在{best_label}{best_value:.0f}分，说明核心操作仍在线，要继续把握这一项优势。"
    )

    if worst_label == "生存" or score_summary.survivability_score <= 45:
        advice_core = "进场要等控制交完，保留位移再收割"
    elif worst_label == "经济":
        advice_core = "补刀与控线别松懈，保持经济节奏"
    elif worst_label == "团队":
        advice_core = "多跟打野报点，等队友开团再跟进"
    elif worst_label == "视野":
        advice_core = "每波回城买真眼，提前铺河道视野"
    elif worst_label == "目标":
        advice_core = "大龙前1分钟集合占位，陪打野抢资源"
    else:
        advice_core = "注意节奏转换，找稳定开团窗口"

    closing = (
        f"短板处在{worst_label}{worst_value:.0f}分，{advice_core}，并及时与队友沟通下一波计划。"
    )
    if not closing.endswith("。"):
        closing += "。"

    fallback_text = "".join((opening, highlight, closing))
    return _compress_tts_text(fallback_text, _TTS_MAX_CHARS)


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
        await _acquire_match_slot(task_payload.match_id)
        # Bind correlation id for end-to-end tracing across async calls
        try:
            _cid = (
                task_payload.correlation_id
                or f"{task_payload.match_id}:{int(time.time() * 1000) % 100000}"
            )
            set_correlation_id(_cid)
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
            with suppress(Exception):
                chimera_riot_api_requests_total.labels(endpoint="timeline", status="error").inc()
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
                with suppress(Exception):
                    await self.db_adapter.disconnect()

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
            with suppress(Exception):
                await self.db_adapter.disconnect()
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

            # SR enrichment diagnostics + extraction
            sr_extract_error: str | None = None
            sr_extra: Mapping[str, Any] | None = None
            if game_mode.mode == "SR":
                if participant_id is not None and match_details:
                    try:
                        from src.core.services.sr_enrichment import extract_sr_enrichment

                        sr_extra = extract_sr_enrichment(
                            timeline_data, match_details, int(participant_id)
                        )
                        if sr_extra:
                            rs["sr_enrichment"] = sr_extra
                    except Exception as exc:  # pragma: no cover - observational
                        sr_extract_error = str(exc)
                        logger.warning(
                            "sr_enrichment_extraction_failed",
                            extra={
                                "match_id": task_payload.match_id,
                                "puuid": task_payload.puuid,
                                "participant_id": participant_id,
                            },
                            exc_info=True,
                        )

                # Teamfight summaries (lightweight, best-effort)
                if match_details:
                    try:
                        from src.core.services.teamfight_reconstructor import (
                            extract_teamfight_summaries,
                        )

                        tf_lines = extract_teamfight_summaries(timeline_data, match_details)
                        if tf_lines:
                            rs.setdefault("sr_enrichment", {})["teamfight_paths"] = tf_lines
                    except Exception:
                        pass

                sr_diag = diagnose_sr_enrichment_gap(
                    game_mode=game_mode.mode,
                    timeline_data=timeline_data,
                    match_details=match_details,
                    participant_id=participant_id,
                    sr_extra=rs.get("sr_enrichment"),
                    target_puuid=task_payload.puuid,
                    extraction_error=sr_extract_error,
                )
                if sr_diag:
                    obs = rs.setdefault("observability", {})
                    if isinstance(obs, Mapping):
                        obs = dict(obs)
                    rs["observability"] = obs
                    obs["sr_enrichment"] = sr_diag
                    if sr_diag.get("state") != "available":
                        logger.warning(
                            "sr_enrichment_missing",
                            extra={
                                "match_id": task_payload.match_id,
                                "puuid": task_payload.puuid,
                                "participant_id": participant_id,
                                "reason": sr_diag.get("reason"),
                                "friendly_reason": sr_diag.get("friendly_reason"),
                                "details": sr_diag.get("details"),
                            },
                        )
        except Exception:
            pass

        # ===== STAGE 4: LLM Narrative =====
        tts_audio_url: str | None = None
        sanitized_context_str: str | None = None

        try:
            # Ensure Redis connected (best-effort)
            await _ensure_redis_connection(self.cache_adapter)

            # Prepare LLM input with target player focus
            llm_input = analysis_output.model_dump(mode="json")
            target_payload: dict[str, Any] | None = None
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

            workflow_snapshot = {
                "fetch": result.fetch_duration_ms,
                "scoring": result.scoring_duration_ms,
                "save": result.save_duration_ms,
            }

            sanitized_context_str = _build_llm_context(
                llm_input=llm_input,
                target_payload=target_payload,
                v1_summary=v1_summary,
                match_id=task_payload.match_id,
                region=task_payload.region,
                queue_id=queue_id,
                match_result=match_result,
                game_mode_label=game_mode.mode if game_mode else None,
                correlation_id=task_payload.correlation_id,
                discord_user_id=task_payload.discord_user_id,
                workflow_durations=workflow_snapshot,
            )
            if sanitized_context_str:
                llm_input["llm_context"] = sanitized_context_str

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
                            extra={"duration_min": duration_min, "match_id": task_payload.match_id},
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
                                    "match_id": task_payload.match_id,
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
                            extra={
                                "tldr_length": len(tldr_text),
                                "match_id": task_payload.match_id,
                            },
                        )
            except Exception:
                # TL;DR is optional; ignore failures
                pass

            # Metrics: LLM success
            mark_llm(status="success", model=settings.gemini_model)

            # Emotion mapping (Arena-aware via emotion_mapper)
            emotion: str = "neutral"
            emotion_profile: dict[str, Any] = {"emotion": "neutral"}
            try:
                from src.core.services.emotion_mapper import (
                    map_score_to_emotion,
                    map_score_to_emotion_dict,
                )

                emotion = map_score_to_emotion(v1_summary)
                emotion_profile = map_score_to_emotion_dict(v1_summary)
            except Exception as mapping_err:
                logger.warning(
                    "emotion_mapping_failed",
                    extra={"match_id": task_payload.match_id, "error": str(mapping_err)},
                )

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
            if emotion_profile:
                base_llm_metadata["tts_recommended_params"] = emotion_profile
            if sanitized_context_str:
                base_llm_metadata["sanitized_context"] = sanitized_context_str

            persisted_llm_metadata: dict[str, Any] = dict(base_llm_metadata)

            async def _save_metadata(meta: dict[str, Any]) -> None:
                try:
                    await self.db_adapter.connect()
                    await self.db_adapter.update_llm_narrative(
                        match_id=task_payload.match_id,
                        llm_narrative=narrative,
                        llm_metadata=meta,
                    )
                finally:
                    with suppress(Exception):
                        await self.db_adapter.disconnect()

            await _save_metadata(persisted_llm_metadata)

            result.llm_duration_ms = (time.perf_counter() - llm_start) * 1000

            # ===== STAGE 4.5: TTS (optional) =====
            tts_start = time.perf_counter()
            tts_outcome: TtsSummaryOutcome | None = None
            try:
                # Generate TTS-optimized summary (200-300 chars) to prevent timeout
                tts_outcome = await _generate_tts_summary(
                    self.llm_adapter,
                    narrative,
                    v1_summary,
                    emotion,
                    champion_name,
                    (game_mode.mode if game_mode else None),
                )

                # Silent degradation: Skip TTS if summary generation failed
                if tts_outcome is None:
                    logger.info(
                        "TTS summary generation returned None, skipping TTS synthesis (silent degradation)"
                    )
                    result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000
                else:
                    tts_text = tts_outcome.text
                    tts_options = dict(emotion_profile or {})
                    tts_options["match_id"] = task_payload.match_id
                    tts_audio_url = await _synthesize_tts_with_observability(
                        self.tts_adapter,
                        tts_text,
                        emotion,
                        tts_options,
                    )
                    metadata_debug = {
                        key: value
                        for key, value in {
                            "tts_summary": tts_text,
                            "tts_summary_source": tts_outcome.source,
                            "tts_summary_soft_hints": list(tts_outcome.soft_hints)
                            if tts_outcome.soft_hints
                            else None,
                            "tts_summary_raw_excerpt": tts_outcome.raw_excerpt,
                            "tts_summary_processed_excerpt": tts_outcome.processed_excerpt,
                        }.items()
                        if value is not None
                    }
                    voice_settings = self.tts_adapter.last_voice_settings
                    if voice_settings:
                        metadata_debug["tts_voice_type"] = voice_settings.voice_type
                        if voice_settings.emotion_code:
                            metadata_debug["tts_emotion_code"] = voice_settings.emotion_code
                        metadata_debug["tts_speed_ratio"] = round(voice_settings.speed_ratio, 3)
                        metadata_debug["tts_pitch_ratio"] = round(voice_settings.pitch_ratio, 3)
                        metadata_debug["tts_volume_ratio"] = round(voice_settings.volume_ratio, 3)
                    if tts_audio_url:
                        persisted_llm_metadata = {
                            **persisted_llm_metadata,
                            "tts_audio_url": tts_audio_url,
                            **metadata_debug,
                        }
                        await _save_metadata(persisted_llm_metadata)
                        logger.info(f"TTS synthesis succeeded: {tts_audio_url}")
                    else:
                        logger.info("TTS synthesis returned None (graceful degradation)")
                        persisted_llm_metadata = {
                            **persisted_llm_metadata,
                            **metadata_debug,
                        }
                        await _save_metadata(persisted_llm_metadata)
                    result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000
            except TTSError as e:
                logger.warning(f"TTS synthesis failed (degraded): {e}", exc_info=True)
                if tts_outcome:
                    persisted_llm_metadata = {
                        **persisted_llm_metadata,
                        "tts_summary": tts_outcome.text,
                        "tts_summary_source": tts_outcome.source,
                    }
                    if tts_outcome.soft_hints:
                        persisted_llm_metadata["tts_summary_soft_hints"] = list(
                            tts_outcome.soft_hints
                        )
                    await _save_metadata(persisted_llm_metadata)
                result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000
            except Exception as e:
                # Generic exception handler for any TTS-related failures
                # (e.g., LLM API errors, network timeouts, unexpected ValueError)
                logger.warning(
                    "TTS stage failed with unhandled exception (graceful degradation)",
                    exc_info=True,
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                if tts_outcome:
                    persisted_llm_metadata = {
                        **persisted_llm_metadata,
                        "tts_summary": tts_outcome.text,
                        "tts_summary_source": tts_outcome.source,
                        "tts_error": str(e),
                        "tts_error_type": type(e).__name__,
                    }
                    if tts_outcome.soft_hints:
                        persisted_llm_metadata["tts_summary_soft_hints"] = list(
                            tts_outcome.soft_hints
                        )
                    await _save_metadata(persisted_llm_metadata)
                result.tts_duration_ms = (time.perf_counter() - tts_start) * 1000

        except GeminiAPIError as e:
            logger.error(
                "LLM failed during narrative generation", extra={"error": str(e)}, exc_info=True
            )
            mark_llm(status="error", model=settings.gemini_model)
            raise

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
                existing_obs = raw_stats_payload.get("observability")
                merged_obs = dict(existing_obs) if isinstance(existing_obs, Mapping) else {}
                merged_obs.update(observability_payload)
                raw_stats_payload["observability"] = merged_obs
                v1_summary.raw_stats = raw_stats_payload
            except Exception:
                logger.warning(
                    "attach_observability_failed",
                    extra={"match_id": task_payload.match_id},
                )

            builds_summary_text: str | None = None
            builds_metadata: dict[str, Any] | None = None
            try:
                env_flag = str(_os.getenv("CHIMERA_TEAM_BUILD_ENRICH", "")).strip().lower()
                feature_enabled = (
                    env_flag in {"1", "true", "yes", "on"}
                    if env_flag
                    else settings.feature_team_build_enrichment_enabled
                )

                dd_client: DataDragonClient | None = None
                opgg_adapter: OPGGAdapter | None = None

                if feature_enabled:
                    dd_client = DataDragonClient(locale=_os.getenv("CHIMERA_LOCALE", "zh_CN"))

                    opgg_flag = str(_os.getenv("CHIMERA_OPGG_ENABLED", "")).strip().lower()
                    opgg_enabled = (
                        opgg_flag in {"1", "true", "yes", "on"}
                        if opgg_flag
                        else settings.feature_opgg_enrichment_enabled
                    )

                    if opgg_enabled:
                        try:
                            opgg_adapter = OPGGAdapter()
                        except Exception:
                            opgg_adapter = None

                if dd_client:
                    enricher = TeamBuildsEnricher(dd_client, opgg_adapter)
                    b_text, b_payload = await enricher.build_summary_for_target(
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

            if builds_summary_text or builds_metadata:
                updated_meta: dict[str, Any] = dict(persisted_llm_metadata)
                if builds_summary_text:
                    updated_meta["builds_summary_text"] = builds_summary_text
                if builds_metadata:
                    updated_meta["builds_metadata"] = builds_metadata
                # Persist once to expose在缓存命中/语音播放场景下的出装数据
                persisted_llm_metadata = updated_meta
                await _save_metadata(persisted_llm_metadata)

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

            # Auto TTS playback (single-match) using broadcast service
            if (
                result.webhook_delivered
                and tts_audio_url
                and settings.feature_voice_enabled
                and settings.feature_team_auto_tts_enabled
                and task_payload.guild_id
            ):
                try:
                    guild_id_int = int(task_payload.guild_id)
                    user_id_int = int(task_payload.discord_user_id)
                except (TypeError, ValueError):
                    guild_id_int = None
                    user_id_int = None

                if guild_id_int and user_id_int:
                    try:
                        from aiohttp import ClientSession

                        server = getattr(
                            settings, "broadcast_server_url", "http://localhost:8080"
                        ).rstrip("/")
                        broadcast_url = f"{server}/broadcast"
                        headers = {"Content-Type": "application/json"}
                        if settings.broadcast_webhook_secret:
                            headers["X-Auth-Token"] = settings.broadcast_webhook_secret
                        payload = {
                            "match_id": task_payload.match_id,
                            "guild_id": guild_id_int,
                            "user_id": user_id_int,
                        }
                        async with (
                            ClientSession() as session,
                            session.post(broadcast_url, json=payload, headers=headers) as resp,
                        ):
                            await resp.text()
                            status = resp.status
                        logger.info(
                            f"match_auto_tts_triggered http_status={status}",
                            extra={
                                "guild_id": task_payload.guild_id,
                                "user_id": task_payload.discord_user_id,
                                "match_id": task_payload.match_id,
                                "http_status": status,
                            },
                        )
                    except Exception as e:
                        logger.warning("match_auto_tts_failed", extra={"error": str(e)})

        except DiscordWebhookError as e:
            result.error_stage = "webhook"
            result.error_message = f"Webhook error: {e}"
            result.webhook_delivered = False
            result.webhook_duration_ms = (time.perf_counter() - webhook_start) * 1000
            with suppress(Exception):
                chimera_external_api_errors_total.labels("discord", "webhook_error").inc()

        # ===== SUCCESS =====
        try:
            await self.db_adapter.connect()
            await self.db_adapter.update_analysis_status(
                task_payload.match_id, status="completed", error_message=None
            )
        finally:
            with suppress(Exception):
                await self.db_adapter.disconnect()

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
        with suppress(Exception):
            chimera_external_api_errors_total.labels("backend", "unexpected").inc()
        mark_request_outcome("analyze", "failed")
        return result.model_dump()
    finally:
        # Ensure correlation id does not leak across tasks
        with suppress(Exception):
            _release_match_slot(task_payload.match_id)
        with suppress(Exception):
            clear_correlation_id()


def _materialize_analysis_payload(
    task_args: tuple[Any, ...],
    task_kwargs: dict[str, Any],
) -> AnalysisTaskPayload:
    """Normalize Celery task arguments into AnalysisTaskPayload."""
    if task_kwargs:
        return AnalysisTaskPayload.model_validate(task_kwargs)

    if not task_args:
        raise ValueError("analysis_match_task requires payload data (received empty args/kwargs)")

    if len(task_args) != 1:
        raise ValueError(
            "analysis_match_task legacy positional invocation must pass a single payload mapping"
        )

    candidate = task_args[0]

    if isinstance(candidate, AnalysisTaskPayload):
        return candidate.model_copy()

    if isinstance(candidate, Mapping):
        return AnalysisTaskPayload.model_validate(dict(candidate))

    if hasattr(candidate, "model_dump"):
        try:
            return AnalysisTaskPayload.model_validate(candidate.model_dump())
        except Exception as exc:
            raise ValueError(
                "analysis_match_task failed to coerce payload from model_dump output"
            ) from exc

    raise ValueError(
        f"analysis_match_task received unsupported positional payload type: {type(candidate)!r}"
    )


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
    /,
    *task_args: Any,
    **task_kwargs: Any,
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
        task_args: Legacy Celery positional payload (single mapping or AnalysisTaskPayload).
        task_kwargs: Preferred keyword payload matching AnalysisTaskPayload fields.

    Returns:
        AnalysisTaskResult dictionary with metrics.

    Raises:
        ValueError: If task payload cannot be materialized from Celery args.
    """
    try:
        task_payload = _materialize_analysis_payload(task_args, task_kwargs)
    except ValueError as exc:
        logger.error(
            "Invalid analyze_match_task payload",
            extra={
                "task_args_types": [type(arg).__name__ for arg in task_args],
                "task_kwargs_keys": list(task_kwargs.keys()),
                "error": str(exc),
            },
        )
        raise

    # Track task execution time
    task_start = time.perf_counter()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run_analysis_workflow(self, task_payload, task_start))
    finally:
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        with suppress(Exception):
            loop.close()


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
) -> TtsSummaryOutcome | None:
    """Generate speech-friendly narration using the 七宗罪老大哥 persona."""

    raw_excerpt: str | None = None
    processed_excerpt: str | None = None
    soft_hints: tuple[str, ...] = ()
    cleaned_narrative = _cleanse_tts_narrative(full_narrative)
    narrative_source = cleaned_narrative or full_narrative

    try:
        raw_stats = score_summary.raw_stats if isinstance(score_summary.raw_stats, Mapping) else {}

        def _dimension_hint(name: str) -> str:
            return {
                "战斗效率": "描摹团战切入与收割的瞬间",
                "经济管理": "讲清补刀与节奏如何滚雪球",
                "视野掌控": "描述照亮战场、伏击与反伏击",
                "目标压制": "强调推塔、控龙、先锋这些攻城节点",
                "团队协同": "点出与队友的配合与呼应",
                "成长节奏": "描写装备成型与节拍",
                "前排坦度": "让听众感受到顶在前面的压力",
                "伤害构成": "说明爆发点来自哪种伤害",
                "生存能力": "凸显走位、拉扯与保命细节",
                "控制影响": "点名关键控制命中与失误",
            }.get(name, "结合比赛画面去描写它的起伏")

        def _overall_mood(score: float) -> str:
            if score >= 70:
                return "几乎全程把节奏握在手里"
            if score >= 55:
                return "战线拉锯，需要靠细节抢主动"
            if score >= 45:
                return "逆风拉扯，偶尔能博到反攻窗口"
            return "压力山大，需要把败局写成复仇剧本"

        dimension_pairs = [
            ("战斗效率", score_summary.combat_score),
            ("经济管理", score_summary.economy_score),
            ("视野掌控", score_summary.vision_score),
            ("目标压制", score_summary.objective_score),
            ("团队协同", score_summary.teamplay_score),
            ("成长节奏", score_summary.growth_score),
            ("前排坦度", score_summary.tankiness_score),
            ("伤害构成", score_summary.damage_composition_score),
            ("生存能力", score_summary.survivability_score),
            ("控制影响", score_summary.cc_contribution_score),
        ]
        strength_dim = max(dimension_pairs, key=lambda item: float(item[1] or 0.0))
        weakness_dim = min(dimension_pairs, key=lambda item: float(item[1] or 0.0))

        anchor_lines: list[str] = []
        anchor_lines.append(
            f"* 战场基调: 综合评分 {score_summary.overall_score:.1f} 分，{_overall_mood(score_summary.overall_score)}"
        )
        anchor_lines.append(
            "* 优势瞬间: "
            f"{strength_dim[0]} {float(strength_dim[1] or 0.0):.1f} 分，讲成{_dimension_hint(strength_dim[0])}"
        )
        anchor_lines.append(
            "* 警示信号: "
            f"{weakness_dim[0]} {float(weakness_dim[1] or 0.0):.1f} 分，提醒{_dimension_hint(weakness_dim[0])}"
        )
        if champion_name:
            anchor_lines.append(f"* 身份标签: 本局操刀 {champion_name}")
        if emotion:
            anchor_lines.append(f"* 情绪氛围: 上游分析标记为「{emotion}」")

        kills = raw_stats.get("kills")
        deaths = raw_stats.get("deaths")
        assists = raw_stats.get("assists")
        cs_total = raw_stats.get("cs") or raw_stats.get("total_cs")
        cs_per_min = raw_stats.get("cs_per_min")
        damage_dealt = raw_stats.get("damage_dealt")
        damage_taken = raw_stats.get("damage_taken")
        data_points: list[str] = []
        if kills is not None and deaths is not None and assists is not None:
            data_points.append(f"K/D/A {int(kills)}/{int(deaths)}/{int(assists)}")
        if cs_total is not None and cs_per_min is not None:
            with suppress(TypeError, ValueError):
                data_points.append(f"CS 节奏 {int(cs_total)} ({float(cs_per_min):.1f} 每分)")
        if damage_dealt is not None or damage_taken is not None:
            try:
                dealt = int(float(damage_dealt or 0))
                taken = int(float(damage_taken or 0))
                data_points.append(f"输出 {dealt:,} 对比 承伤 {taken:,}")
            except (TypeError, ValueError):
                pass

        sr_enrichment = raw_stats.get("sr_enrichment")
        timeline_beats: list[str] = []
        if isinstance(sr_enrichment, Mapping):
            breakdown = sr_enrichment.get("objective_breakdown") or {}
            try:
                towers = int(breakdown.get("towers", 0) or 0)
                drakes = int(breakdown.get("drakes", 0) or 0)
                heralds = int(breakdown.get("heralds", 0) or 0)
                barons = int(breakdown.get("barons", 0) or 0)
                resource_bits = []
                if towers:
                    resource_bits.append(f"推塔 {towers}")
                if drakes:
                    resource_bits.append(f"控龙 {drakes}")
                if heralds:
                    resource_bits.append(f"先锋 {heralds}")
                if barons:
                    resource_bits.append(f"大龙 {barons}")
                if resource_bits:
                    anchor_lines.append("* 资源战果: " + "、".join(resource_bits))
            except (TypeError, ValueError):
                pass

            conversions = sr_enrichment.get("post_kill_objective_conversions")
            team_kills = sr_enrichment.get("team_kills_considered")
            rate = sr_enrichment.get("conversion_rate")
            conversion_rate_value: float | None = None
            try:
                if conversions is not None:
                    conversions_i = int(conversions)
                    percent = ""
                    if rate is not None:
                        try:
                            conversion_rate_value = float(rate)
                            percent = f"成功率约 {int(conversion_rate_value * 100)}%"
                        except (TypeError, ValueError):
                            conversion_rate_value = None
                            percent = ""
                    if team_kills:
                        team_kills_i = int(team_kills)
                        anchor_lines.append(
                            "* 击杀转目标: "
                            f"{conversions_i} 次（母样本 {team_kills_i} 次击杀，{percent}）".rstrip(
                                "，"
                            )
                        )
                    else:
                        text = f"* 击杀转目标: {conversions_i} 次"
                        if percent:
                            text += f"（{percent}）"
                        anchor_lines.append(text)
            except (TypeError, ValueError):
                pass

            if conversion_rate_value is not None and conversion_rate_value >= 0.8:
                hint_percent = int(round(conversion_rate_value * 100))
                anchor_lines.append(
                    f"* 语气提示: 转目标效率约 {hint_percent}% ，请避免使用“只”“仅”等贬义副词，保持正向节奏。"
                )
                soft_hints = tuple(sorted(set((*soft_hints, "high_conversion_positive_tone"))))

            tf_paths = sr_enrichment.get("teamfight_paths") or []
            replacements = {
                "Dragon Pit": "龙坑",
                "Baron Pit": "大龙坑",
                "Jungle": "野区",
                "River": "河道",
                "Mid Lane": "中路",
                "Bot Lane": "下路",
                "Top Lane": "上路",
            }
            for path in tf_paths[:2]:
                if not isinstance(path, str) or "|" not in path:
                    continue
                ts_raw, detail_raw = (seg.strip() for seg in path.split("|", 1))
                if " " in ts_raw:
                    time_stamp, location = ts_raw.split(" ", 1)
                else:
                    time_stamp, location = ts_raw, ""
                for src, dest in replacements.items():
                    location = location.replace(src, dest)
                detail = detail_raw.replace("击杀", "打出").replace("Assist", "助攻")
                timeline_beats.append(f"{time_stamp} {location}".strip() + f" {detail}".strip())

            preferred_path = sr_enrichment.get("preferred_conversion_path")
            if isinstance(preferred_path, str) and preferred_path:
                node_map = {
                    "To": "推塔",
                    "Dr": "控龙",
                    "He": "先锋",
                    "Ba": "大龙",
                    "In": "拆晶",
                    "Vo": "虚空幼体",
                    "At": "阿塔坎",
                }
                seq = [
                    node_map.get(segment.strip(), segment.strip())
                    for segment in preferred_path.split(">")
                    if segment.strip()
                ]
                if seq:
                    anchor_lines.append("* 资源节奏: " + "→".join(seq))

        try:
            sr_diag_obs = raw_stats.get("observability", {}).get("sr_enrichment")
        except Exception:
            sr_diag_obs = None
        if isinstance(sr_diag_obs, Mapping) and sr_diag_obs.get("state") != "available":
            friendly = sr_diag_obs.get("friendly_reason") or sr_diag_obs.get("reason")
            if friendly:
                anchor_lines.append(f"* 数据缺口: Timeline 增强缺失（{friendly}）")

        if timeline_beats:
            anchor_lines.append("* 关键战点: " + "；".join(timeline_beats))

        if data_points:
            anchor_lines.append(
                "* 可引用数字: " + "；".join(data_points) + "（播报时挑一两个即可）"
            )

        def _safe_float(value: Any) -> float | None:
            try:
                if value is None:
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None

        duration_min = _safe_float(raw_stats.get("duration_min"))
        if duration_min is None:
            duration_min = _safe_float(raw_stats.get("game_duration_minutes"))
        if duration_min is None and raw_stats.get("game_duration_seconds") is not None:
            try:
                duration_min = float(raw_stats.get("game_duration_seconds")) / 60.0
            except (TypeError, ValueError):
                duration_min = None
        if duration_min is None and isinstance(raw_stats.get("sr_enrichment"), Mapping):
            duration_min = _safe_float(raw_stats["sr_enrichment"].get("duration_min"))

        focus_name = raw_stats.get("summoner_name") or raw_stats.get("summoner") or "Summoner"
        focus_champion = champion_name or raw_stats.get("champion_name") or "Unknown"

        llm_context_lines: list[str] = ["## 播报素材"]
        llm_context_lines.append(f"- Summoner: {focus_name}")
        llm_context_lines.append(f"- Champion: {focus_champion}")
        if duration_min is not None:
            llm_context_lines.append(f"- Duration: {duration_min:.1f} 分钟")
        llm_context_lines.append(f"- 综合评分: {score_summary.overall_score:.1f}")
        llm_context_lines.append(
            f"- 亮点维度: {strength_dim[0]} {float(strength_dim[1] or 0.0):.1f} 分"
        )
        llm_context_lines.append(
            f"- 待补强: {weakness_dim[0]} {float(weakness_dim[1] or 0.0):.1f} 分"
        )
        if data_points:
            llm_context_lines.append("- 关键数据: " + "；".join(data_points))
        if timeline_beats:
            llm_context_lines.append("\n## 时间线片段")
            llm_context_lines.extend(f"- {beat}" for beat in timeline_beats[:3])

        llm_context_lines.append("\n## 战局骨架")
        llm_context_lines.extend(anchor_lines)

        context_section = ""
        if anchor_lines:
            context_section = "\n\n=== 战局骨架（只做脑内脚本，勿逐条朗读） ===\n" + "\n".join(
                anchor_lines
            )

        persona_banner = (
            "你是一位用'七宗罪'自我救赎的传奇ADC解说，经历职业巅峰与低谷。"
            "傲慢提醒你尊重团队、嫉妒让你理解竞争、暴怒教你控情绪、"
            "懒惰警示保持基本功、贪婪让你珍惜资源、暴食提醒照顾状态、色欲教你专注。"
            "口吻像阅尽风雨的老大哥，对年轻选手推心置腹。"
        )

        tts_prompt = (
            "你是英雄联盟官方直播间的赛后主持人，请用中文第一人称复盘本局。"
            f"{persona_banner}"
            "播报需兼容豆包TTS男声/女声：语速中等偏稳，语调沉着且有热度，结尾自然收束。"
            "请输出2~4句，每句不超过40个汉字；保持口语化，禁用Markdown、编号、emoji、引号包裹。"
            "结构建议：先点题说明综合评分与整体走势，再用真实数据点亮亮点，最后给出具体可执行的改进。"
            "严禁捏造数据；若上下文缺信息，请绕开，不要道歉或提示稍后重试。"
            f"{context_section}"
            f"\n\n=== 播报原文参考 ===\n{narrative_source[:2000]}"
        )

        match_id_hint = (
            raw_stats.get("match_id")
            or raw_stats.get("matchId")
            or raw_stats.get("game_id")
            or raw_stats.get("metadata", {}).get("matchId")
            if isinstance(raw_stats.get("metadata"), Mapping)
            else None
        )

        player_entry: dict[str, Any] = {
            "participant_id": raw_stats.get("participant_id")
            or raw_stats.get("participantId")
            or 0,
            "summoner_name": focus_name,
            "champion_name": focus_champion,
            "total_score": float(score_summary.overall_score),
            "combat_efficiency": float(score_summary.combat_score),
            "economic_management": float(score_summary.economy_score),
            "objective_control": float(score_summary.objective_score),
            "vision_control": float(score_summary.vision_score),
            "team_contribution": float(score_summary.teamplay_score),
            "cs_per_min": raw_stats.get("cs_per_min"),
            "kill_participation": raw_stats.get("kill_participation"),
            "gold_difference": raw_stats.get("gold_diff"),
            "strengths": [strength_dim[0]],
            "improvements": [weakness_dim[0]],
        }
        if raw_stats.get("champion_id") or raw_stats.get("championId"):
            player_entry["champion_id"] = raw_stats.get("champion_id") or raw_stats.get(
                "championId"
            )
        if raw_stats.get("kda") is not None:
            player_entry["kda"] = raw_stats.get("kda")

        payload = {
            "match_id": match_id_hint or "tts_summary",
            "game_duration_minutes": float(duration_min or 0.0),
            "player_scores": [player_entry],
            "llm_context": "\n".join(llm_context_lines).strip(),
        }

        summary_raw = await llm_adapter.analyze_match(payload, tts_prompt)
        if summary_raw:
            summary_raw = summary_raw.strip()
            raw_excerpt = summary_raw[:400]

        if summary_raw and len(summary_raw) >= 8:
            processed = _sanitize_tts_summary(summary_raw, score_summary)
            processed = _repair_arena_subject(processed, champion_name, game_mode)
            processed = _compress_tts_text(processed.strip(), _TTS_MAX_CHARS)

            if processed:
                is_valid, validation_hints = _validate_tts_candidate(processed)
                if validation_hints:
                    soft_hints = tuple(sorted(set((*soft_hints, *validation_hints))))
                if not is_valid:
                    logger.info(
                        "tts_summary_invalid_candidate",
                        extra={
                            "hints": list(soft_hints),
                            "preview": processed[:120],
                        },
                    )

                    fallback_text = _build_tts_fallback(score_summary, champion_name, game_mode)
                    fallback_processed = _sanitize_tts_summary(fallback_text, score_summary)
                    fallback_processed = _repair_arena_subject(
                        fallback_processed, champion_name, game_mode
                    )
                    fallback_processed = _compress_tts_text(
                        fallback_processed.strip(), _TTS_MAX_CHARS
                    )

                    if fallback_processed:
                        fallback_valid, fallback_hints = _validate_tts_candidate(fallback_processed)
                        hint_set = set(soft_hints)
                        hint_set.update(fallback_hints or ())
                        hint_set.add("fallback_used")
                        soft_hints = tuple(sorted(hint_set))
                        if fallback_valid:
                            logger.info(
                                "tts_summary_fallback_used",
                                extra={
                                    "summary_length": len(fallback_processed),
                                    "processed_excerpt": fallback_processed[:120],
                                },
                            )
                            return TtsSummaryOutcome(
                                text=fallback_processed,
                                source="fallback",
                                raw_excerpt=raw_excerpt,
                                processed_excerpt=fallback_processed[:400],
                                soft_hints=soft_hints,
                            )

                    logger.warning(
                        "tts_summary_fallback_invalid",
                        extra={
                            "hints": list(soft_hints),
                            "preview": (fallback_processed or processed)[:120],
                        },
                    )
                    return None

                processed_excerpt = processed[:400]
                logger.info(
                    "tts_summary_generated",
                    extra={
                        "summary_length": len(processed),
                        "processed_excerpt": processed_excerpt,
                    },
                )
                return TtsSummaryOutcome(
                    text=processed,
                    source="llm",
                    raw_excerpt=raw_excerpt,
                    processed_excerpt=processed_excerpt,
                    soft_hints=soft_hints,
                )

        fallback_text = _build_tts_fallback(score_summary, champion_name, game_mode)
        fallback_processed = _sanitize_tts_summary(fallback_text, score_summary)
        fallback_processed = _repair_arena_subject(fallback_processed, champion_name, game_mode)
        fallback_processed = _compress_tts_text(fallback_processed.strip(), _TTS_MAX_CHARS)

        if fallback_processed:
            fallback_valid, fallback_hints = _validate_tts_candidate(fallback_processed)
            if fallback_valid:
                logger.info(
                    "tts_summary_fallback_used",
                    extra={
                        "summary_length": len(fallback_processed),
                        "processed_excerpt": fallback_processed[:120],
                    },
                )
                hints = tuple(sorted(set((*soft_hints, "fallback_used", *(fallback_hints or [])))))
                return TtsSummaryOutcome(
                    text=fallback_processed,
                    source="fallback",
                    raw_excerpt=raw_excerpt,
                    processed_excerpt=fallback_processed[:400],
                    soft_hints=hints,
                )

        logger.warning(
            "tts_summary_unavailable_after_fallback",
            extra={"raw_excerpt": raw_excerpt, "hints": list(soft_hints)},
        )
        return None

    except Exception as e:
        logger.error(
            "tts_summary_generation_failed",
            exc_info=False,
            extra={"error": str(e), "raw_excerpt": raw_excerpt},
        )
        raise


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
    options: dict[str, Any] | None = None,
) -> str | None:
    """Synthesize TTS audio with observability wrapper.

    Args:
        tts_adapter: TTS adapter
        narrative: Narrative text to synthesize
        emotion: Emotion tag for voice modulation
        options: Additional TTS options (speed/pitch/voice metadata)

    Returns:
        Public URL to audio file, or None if synthesis fails

    P5 Graceful Degradation:
        - Returns None on TTS service failures
        - Does not raise exceptions (wrapped in try/catch in caller)
        - Allows task to continue without TTS
    """
    return await tts_adapter.synthesize_speech_to_url(narrative, emotion, options=options)


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
