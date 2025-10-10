"""Analysis view

Transforms FinalAnalysisReport into visually rich Discord Embeds following the
"表现力决定一切" (Presentation is everything) principle.
"""

import logging
import os
from typing import Any

import discord
from src.core.utils.clamp import clamp_code_block, clamp_field, clamp_text
from src.core.views.ascii_card import build_ascii_card
from src.core.views.emoji_registry import resolve_emoji

logger = logging.getLogger(__name__)


def _style() -> str:
    return os.getenv("CHIMERA_UI_STYLE", "emoji").lower()  # emoji|block|ansi


def _format_duration_ms(ms: float) -> str:
    """Format duration from milliseconds to human-readable string.

    Args:
        ms: Duration in milliseconds

    Returns:
        Formatted string: "X.X分钟" for >= 60s, "XX秒" for < 60s

    Examples:
        52898 -> "0.9分钟"
        26239 -> "26秒"
        91000 -> "1.5分钟"
    """
    try:
        seconds = ms / 1000.0
        if seconds >= 60:
            minutes = seconds / 60.0
            return f"{minutes:.1f}分钟"
        else:
            return f"{int(round(seconds))}秒"
    except Exception:
        return f"{ms:.0f}ms"  # Fallback to raw ms on error


def _bar(v: float | int) -> str:
    """Legacy bar function with emoji tail - kept for backward compatibility.

    New code should use _progress_bar() for consistency with Team view.
    """
    try:
        x = max(0.0, min(100.0, float(v)))
        filled = int(round(x / 10))
        empty = 10 - filled
        style = _style()
        if style == "block":
            tail = "▓" if x >= 70 else ("▒" if x >= 40 else "░")
            return ("█" * filled + "░" * empty) + " " + tail
        if style == "ansi":
            # color whole bar by threshold
            color = "32" if x >= 70 else ("33" if x >= 40 else "31")
            bar_txt = "█" * filled + "░" * empty
            return f"\x1b[{color}m{bar_txt}\x1b[0m"
        # default emoji tail
        tail = "🟩" if x >= 70 else ("🟨" if x >= 40 else "🟥")
        return ("█" * filled + "░" * empty) + " " + tail
    except Exception:
        return ""


def _progress_bar(score: float, width: int = 10, *, ascii_safe: bool | None = None) -> str:
    """Return a bracketed bar string (team/personal unified style)."""
    try:
        value = float(score)
    except Exception:
        value = 0.0
    value = max(0.0, min(100.0, value))

    filled = int(round((value / 100.0) * width))
    filled = min(width, max(0, filled))
    empty = width - filled

    if ascii_safe is None:
        ascii_flag = str(
            os.getenv("UI_ASCII_SAFE", os.getenv("CHIMERA_ASCII_SAFE", "0"))
        ).lower() in ("1", "true", "yes", "on")
    else:
        ascii_flag = ascii_safe

    filled_char = "#" if ascii_flag else "█"
    empty_char = "-" if ascii_flag else "▒"
    bar = filled_char * filled + empty_char * empty
    return f"[{bar}]"


def _fmt_rate(x: Any) -> str:
    """Adaptive rate formatting: show 2 decimals when <0.1/min to avoid 0.0."""
    try:
        v = float(x or 0.0)
    except Exception:
        v = 0.0
    if 0.0 < v < 0.1:
        return f"{v:.2f}"
    return f"{v:.1f}"


_CONVERSION_TOKEN_MAP = {
    "To": "塔",
    "Dr": "小龙",
    "Ba": "大龙",
    "He": "先锋",
}


def _translate_conversion_path(path: str | None) -> str:
    if not path or path.lower() == "none":
        return "-"
    segments: list[str] = []
    for token in path.split(">"):
        t = token.strip().title()
        segments.append(_CONVERSION_TOKEN_MAP.get(t, t))
    return "→".join(segments) if segments else "-"


def _fmt_sr_diff(value: Any) -> str:
    try:
        v = int(value)
    except Exception:
        return "—"
    if v == 0:
        return "±0"
    return f"{v:+d}"


def _format_cc_duration(raw_seconds: Any) -> str:
    try:
        seconds = float(raw_seconds or 0.0)
    except (TypeError, ValueError):
        return "0.0s"

    if seconds >= 60.0:
        minutes = seconds / 60.0
        return f"{minutes:.1f}min"
    return f"{seconds:.1f}s"


def _format_ms_metric(value: Any) -> str | None:
    try:
        return f"{int(round(float(value)))}ms"
    except Exception:
        return None


def _format_footer_text(
    *,
    algorithm_version: str,
    processing_time_ms: float,
    task_id: str | None,
    observability: dict[str, Any] | None,
) -> str:
    base = "蔚-上城人 | V1 Analyze"
    segments: list[str] = [base]

    if isinstance(observability, dict):
        session = observability.get("session_id")
        branch = observability.get("execution_branch_id")
        if session and branch:
            segments[0] += f" | {session}:{branch}"

        metric_labels = [
            ("fetch_ms", "Φfetch"),
            ("scoring_ms", "Φscore"),
            ("save_ms", "Φsave"),
            ("llm_ms", "Φllm"),
            ("tts_ms", "Φtts"),
            ("webhook_ms", "Φwebhook"),
            ("overall_ms", "Φtotal"),
        ]
        metric_parts: list[str] = []
        for key, label in metric_labels:
            metric_text = _format_ms_metric(observability.get(key))
            if metric_text:
                metric_parts.append(f"{label}={metric_text}")
        if metric_parts:
            segments.append(" ".join(metric_parts))

    duration_segment = (
        f"算法 {algorithm_version.upper()} | ⏱️ {_format_duration_ms(processing_time_ms)}"
    )
    if task_id:
        duration_segment += f" | Task {task_id}"
    segments.append(duration_segment)

    return " | ".join(segment for segment in segments if segment)


def _format_builds_field(report_dict: dict[str, Any]) -> str | None:
    summary = (report_dict.get("builds_summary_text") or "").strip()
    metadata = report_dict.get("builds_metadata") or {}

    lines: list[str] = []

    if summary:
        lines.append(summary)
    else:
        items = metadata.get("items") or []
        if items:
            items_text = " · ".join(str(item) for item in list(items)[:6])
            lines.append(f"出装: {items_text}")

        primary = metadata.get("primary_tree_name")
        keystone = metadata.get("primary_keystone")
        secondary = metadata.get("secondary_tree_name")
        rune_segments: list[str] = []
        if primary:
            rune_segments.append(str(primary))
        if keystone:
            rune_segments.append(str(keystone))
        if secondary:
            rune_segments.append(f"次系 {secondary}")
        if rune_segments:
            lines.append("符文: " + " - ".join(rune_segments))

    diff = metadata.get("diff") or {}
    if isinstance(diff, dict):
        missing = diff.get("missing_items") or []
        extra = diff.get("extra_items") or []
        keystone_match = diff.get("keystone_match")
        recommended_keystone = diff.get("recommended_keystone")
        if missing:
            lines.append("缺少推荐: " + " / ".join(str(item) for item in missing[:3]))
        if extra:
            lines.append("额外出装: " + " / ".join(str(item) for item in extra[:3]))
        if keystone_match is True:
            lines.append("主系基石与 OP.GG 推荐匹配")
        elif keystone_match is False:
            if recommended_keystone:
                lines.append(f"建议基石: {recommended_keystone}")
            else:
                lines.append("主系基石与 OP.GG 推荐不同")

    visuals = metadata.get("visuals") or []
    if visuals:
        captions: list[str] = []
        for visual in visuals[:3]:
            if not isinstance(visual, dict):
                continue
            caption = str(
                visual.get("caption")
                or visual.get("title")
                or visual.get("name")
                or visual.get("file")
                or ""
            ).strip()
            if caption:
                captions.append(caption)
        if captions:
            lines.append("图表: " + " / ".join(captions))

    if not lines:
        return None

    return clamp_field("\n".join(lines))


def render_analysis_embed(analysis_data: dict[str, Any]) -> discord.Embed:
    """Render FinalAnalysisReport as a rich Discord Embed with ASCII/8-bit flavor."""

    # Extract core metadata
    match_result = analysis_data["match_result"]
    summoner_name = analysis_data["summoner_name"]
    champion_name = analysis_data["champion_name"]
    ai_narrative = analysis_data["ai_narrative_text"]
    sentiment_tag = analysis_data["llm_sentiment_tag"]
    v1_scores = analysis_data["v1_score_summary"]
    champion_url = analysis_data["champion_assets_url"]
    processing_time = analysis_data["processing_duration_ms"]
    algorithm_version = analysis_data.get("algorithm_version", "v1")
    raw_stats = v1_scores.get("raw_stats", {})

    is_arena = bool(
        raw_stats.get("is_arena")
        or raw_stats.get("game_mode") == "Arena"
        or raw_stats.get("queue_id") in (1700, 1710)
    )
    is_aram = bool(raw_stats.get("game_mode") == "ARAM" or raw_stats.get("queue_id") == 450)

    # Title & color
    champ_emoji = resolve_emoji(f"champion:{champion_name}", "")
    champ_tag = (champ_emoji + " ") if champ_emoji else ""
    if is_arena:
        embed_color = 0x5865F2
        title_text = f"{champ_tag}📊 Arena战绩分析 | {champion_name}"
    elif match_result == "victory":
        embed_color = 0x00FF00
        title_text = f"{champ_tag}🏆 胜利分析 | {champion_name}"
    else:
        embed_color = 0xFF0000
        title_text = f"{champ_tag}💔 失败分析 | {champion_name}"

    # ASCII/ANSI header card (layout switchable)
    # Prefer team receipt if present (Team analysis) to match "小票"风格
    team_receipt = None
    try:
        team_receipt = (raw_stats or {}).get("team_receipt")
    except Exception:
        team_receipt = None
    if team_receipt:
        ascii_card = team_receipt
    else:
        layout = os.getenv("CHIMERA_UI_LAYOUT", "card").lower()  # card|receipt
        if layout == "receipt":
            try:
                from src.core.views.ascii_receipt import build_ascii_receipt

                ascii_card = build_ascii_receipt(analysis_data)
            except Exception:
                ascii_card = build_ascii_card(analysis_data)
        else:
            ascii_card = build_ascii_card(analysis_data)

    # Force non-ANSI code block to avoid mojibake on some clients
    # (ANSI can produce replacement characters '�' on certain mobile/desktop Discord builds)
    code_lang = ""
    header_block = f"```{code_lang}\n{ascii_card}\n```\n"

    description = (
        header_block
        + f"**召唤师**: {summoner_name}\n\n"
        + f"🤖 AI 评价 [{sentiment_tag}]\n{ai_narrative}"
    )

    # Optional: theme→embed color mapping
    theme = os.getenv("CHIMERA_UI_THEME", "dark").lower()
    theme_color = {"dark": 0x2F3136, "neon": 0x39FF14, "teamcolor": embed_color}.get(
        theme, embed_color
    )

    embed = discord.Embed(
        title=title_text,
        description=clamp_text(description, 4000, preserve_markdown=True),
        color=theme_color,
    )

    # === 统一字段：核心优势、重点补强、时间线增强、个人快照 ===
    dimension_map: list[tuple[str, str, str, Any]] = [
        ("combat_score", "⚔️", "战斗效率", v1_scores.get("combat_score")),
        ("economy_score", "💰", "经济管理", v1_scores.get("economy_score")),
        ("objective_score", "🎯", "目标控制", v1_scores.get("objective_score")),
        ("vision_score", "👁️", "视野控制", v1_scores.get("vision_score")),
        ("teamplay_score", "🤝", "团队协同", v1_scores.get("teamplay_score")),
        ("growth_score", "📊", "成长", v1_scores.get("growth_score")),
        ("tankiness_score", "🛡️", "坦度", v1_scores.get("tankiness_score")),
        ("damage_composition_score", "⚡", "伤害", v1_scores.get("damage_composition_score")),
        ("survivability_score", "💚", "生存能力", v1_scores.get("survivability_score")),
        ("cc_contribution_score", "🎯", "控制", v1_scores.get("cc_contribution_score")),
    ]

    ascii_safe = str(os.getenv("UI_ASCII_SAFE", os.getenv("CHIMERA_ASCII_SAFE", "0"))).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    def _title(label: str) -> str:
        if not ascii_safe:
            return label
        return label.split(" ", 1)[1] if " " in label else label

    def _format_dim_line(emoji: str, label: str, score_value: float) -> str:
        bar = _progress_bar(score_value, ascii_safe=ascii_safe)
        prefix = "" if ascii_safe else f"{emoji} "
        return f"{prefix}{label}: {bar} {score_value:.1f}分"

    dimension_candidates: list[tuple[str, str, str, float]] = []
    for key, emoji, label, raw_value in dimension_map:
        try:
            numeric = float(raw_value if raw_value is not None else 0.0)
        except (TypeError, ValueError):
            numeric = 0.0
        dimension_candidates.append((key, emoji, label, numeric))
    dimension_candidates.sort(key=lambda item: item[3], reverse=True)

    top3 = dimension_candidates[:3]
    bottom3 = dimension_candidates[-3:] if len(dimension_candidates) >= 3 else dimension_candidates

    def _render_dimension_section(items: list[tuple[str, str, str, float]]) -> str:
        if not items:
            return "暂无评分数据"
        return "\n".join(_format_dim_line(emoji, label, score) for _, emoji, label, score in items)

    embed.add_field(
        name=_title("⚡ 核心优势"),
        value=clamp_field(_render_dimension_section(top3)),
        inline=False,
    )
    embed.add_field(
        name=_title("⚠️ 重点补强"),
        value=clamp_field(_render_dimension_section(bottom3)),
        inline=False,
    )

    sr_enrichment = raw_stats.get("sr_enrichment") if isinstance(raw_stats, dict) else None
    is_summoners_rift = not (is_arena or is_aram)
    timeline_text = "暂无时间线增强数据"
    if is_summoners_rift and isinstance(sr_enrichment, dict) and sr_enrichment:
        parts: list[str] = []

        def _fmt_delta(value: Any) -> str:
            try:
                return f"{int(round(float(value))):+d}"
            except (TypeError, ValueError):
                return "+0"

        if sr_enrichment.get("gold_diff_10") is not None:
            parts.append(f"GoldΔ10 {_fmt_delta(sr_enrichment.get('gold_diff_10'))}")
        if sr_enrichment.get("xp_diff_10") is not None:
            parts.append(f"XPΔ10 {_fmt_delta(sr_enrichment.get('xp_diff_10'))}")
        if sr_enrichment.get("conversion_rate") is not None:
            try:
                conv_pct = int(round(float(sr_enrichment["conversion_rate"]) * 100))
            except (TypeError, ValueError):
                conv_pct = 0
            parts.append(f"转化率 {conv_pct}%")
        if sr_enrichment.get("ward_rate_per_min") is not None:
            try:
                ward_rate = float(sr_enrichment["ward_rate_per_min"])
                parts.append(f"插眼/分 {ward_rate:.2f}")
            except (TypeError, ValueError):
                parts.append("插眼/分 —")

        if parts:
            timeline_text = " • ".join(parts)

    embed.add_field(
        name=_title("🕒 时间线增强"),
        value=clamp_field(timeline_text),
        inline=False,
    )

    builds_field = _format_builds_field(analysis_data)
    if builds_field:
        embed.add_field(
            name=_title("🛠 出装 & 符文"),
            value=builds_field,
            inline=False,
        )

    snapshot_block = "```\n数据不可用\n```"
    if isinstance(raw_stats, dict) and raw_stats:
        kills = int(raw_stats.get("kills", 0) or 0)
        deaths = int(raw_stats.get("deaths", 0) or 0)
        assists = int(raw_stats.get("assists", 0) or 0)
        cs_total = int(raw_stats.get("cs", raw_stats.get("total_cs", 0)) or 0)

        cs_per_min: float | None
        try:
            cs_per_min_raw = raw_stats.get("cs_per_min")
            cs_per_min = float(cs_per_min_raw) if cs_per_min_raw is not None else None
        except (TypeError, ValueError):
            cs_per_min = None
        if cs_per_min is None:
            duration_min = None
            if isinstance(sr_enrichment, dict):
                duration_min = sr_enrichment.get("duration_min")
            if duration_min:
                try:
                    cs_per_min = cs_total / max(1.0, float(duration_min))
                except (TypeError, ValueError):
                    cs_per_min = None
        cs_value_text = str(cs_total) if cs_per_min is None else f"{cs_total} ({cs_per_min:.1f})"

        vision_score = int(raw_stats.get("vision_score", 0) or 0)
        damage_dealt = int(round(float(raw_stats.get("damage_dealt", 0) or 0.0)))
        damage_taken = int(round(float(raw_stats.get("damage_taken", 0) or 0.0)))
        level_val = int(raw_stats.get("level", 0) or 0)

        cc_time_val = float(raw_stats.get("cc_time", 0.0) or 0.0)
        cc_score_raw = raw_stats.get("cc_score", 0.0) or 0.0
        try:
            cc_score_int = int(round(float(cc_score_raw)))
        except (TypeError, ValueError):
            cc_score_int = 0

        control_segments: list[str] = []
        if cc_time_val:
            control_segments.append(_format_cc_duration(cc_time_val))
        if cc_score_int:
            control_segments.append(f"{cc_score_int} pts")
        control_value = " / ".join(control_segments) if control_segments else "—"

        snapshot_entries = [
            ("K/D/A", f"{kills} / {deaths} / {assists}"),
            ("CS/分", cs_value_text),
            ("视野", str(vision_score)),
            ("输出/承伤", f"{damage_dealt:,} / {damage_taken:,}"),
            ("等级", str(level_val)),
            ("控制", control_value),
        ]
        label_width = 8
        snapshot_lines = [f"{label:<{label_width}}{value}" for label, value in snapshot_entries]
        snapshot_block = "```text\n" + "\n".join(snapshot_lines) + "\n```"

    embed.add_field(
        name=_title("🧠 个人快照"),
        value=clamp_code_block(snapshot_block),
        inline=False,
    )

    # Author & thumbnail
    try:
        embed.set_author(name=f"{summoner_name} · {champion_name}", icon_url=champion_url)
    except Exception:
        pass
    embed.set_thumbnail(url=champion_url)

    observability = raw_stats.get("observability") if isinstance(raw_stats, dict) else None
    task_id = analysis_data.get("trace_task_id")
    footer_text = _format_footer_text(
        algorithm_version=algorithm_version,
        processing_time_ms=processing_time,
        task_id=str(task_id) if task_id else None,
        observability=observability if isinstance(observability, dict) else None,
    )
    embed.set_footer(text=footer_text)

    if analysis_data.get("tts_audio_url"):
        embed.add_field(
            name="🔊 语音播报",
            value=clamp_field(f"[点击收听 AI 语音]({analysis_data['tts_audio_url']})", limit=1024),
            inline=False,
        )

    return embed


def render_error_embed(
    error_message: str,
    match_id: str | None = None,
    retry_suggested: bool = True,
) -> discord.Embed:
    """Render error notification as Discord Embed with smart suggestions.

    Args:
        error_message: Human-readable error description
        match_id: Optional problematic match ID
        retry_suggested: Whether user should retry (feeds the suggestion text)
    """
    try:
        message = (error_message or "Unknown error").strip()
        # Clamp long internal errors to avoid Discord limits
        message = message if len(message) <= 500 else message[:497] + "…"
    except Exception:
        message = "Unknown error"

    if retry_suggested:
        suggestion = "💡 **建议**: 请稍后重试，问题可能是临时性的（如 Riot API 繁忙）。"
    else:
        suggestion = "⚠️ **注意**: 数据不完整或不支持该对局，重试可能无效。"

    desc_parts: list[str] = [
        "很抱歉，AI 分析过程中发生错误：\n",
        f"`{message}`\n",
        suggestion,
    ]
    if match_id:
        desc_parts.insert(0, f"**Match ID**: `{match_id}`\n")

    embed = discord.Embed(
        title="❌ 分析失败",
        description=clamp_text("\n".join(desc_parts), 4000, preserve_markdown=True),
        color=0xFF0000,
    )
    embed.set_footer(text="蔚-上城人 | 错误通知")
    return embed
    # === 统一字段：核心优势、重点补强、时间线增强、个人快照 ===
    dimension_map: list[tuple[str, str, str, Any]] = [
        ("combat_score", "⚔️", "战斗效率", v1_scores.get("combat_score")),
        ("economy_score", "💰", "经济管理", v1_scores.get("economy_score")),
        ("objective_score", "🎯", "目标控制", v1_scores.get("objective_score")),
        ("vision_score", "👁️", "视野控制", v1_scores.get("vision_score")),
        ("teamplay_score", "🤝", "团队协同", v1_scores.get("teamplay_score")),
        ("growth_score", "📊", "成长", v1_scores.get("growth_score")),
        ("tankiness_score", "🛡️", "坦度", v1_scores.get("tankiness_score")),
        ("damage_composition_score", "⚡", "伤害", v1_scores.get("damage_composition_score")),
        ("survivability_score", "💚", "生存能力", v1_scores.get("survivability_score")),
        ("cc_contribution_score", "🎯", "控制", v1_scores.get("cc_contribution_score")),
    ]

    ascii_safe = str(os.getenv("UI_ASCII_SAFE", os.getenv("CHIMERA_ASCII_SAFE", "0"))).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    def _title(label: str) -> str:
        if not ascii_safe:
            return label
        return label.split(" ", 1)[1] if " " in label else label

    def _format_dim_line(emoji: str, label: str, score_value: float) -> str:
        bar = _progress_bar(score_value, ascii_safe=ascii_safe)
        prefix = "" if ascii_safe else f"{emoji} "
        return f"{prefix}{label}: {bar} {score_value:.1f}分"

    dimension_candidates: list[tuple[str, str, str, float]] = []
    for key, emoji, label, raw_value in dimension_map:
        try:
            numeric = float(raw_value if raw_value is not None else 0.0)
        except (TypeError, ValueError):
            numeric = 0.0
        dimension_candidates.append((key, emoji, label, numeric))
    dimension_candidates.sort(key=lambda item: item[3], reverse=True)

    top3 = dimension_candidates[:3]
    bottom3 = dimension_candidates[-3:] if len(dimension_candidates) >= 3 else dimension_candidates

    def _render_dimension_section(items: list[tuple[str, str, str, float]]) -> str:
        if not items:
            return "暂无评分数据"
        return "\n".join(_format_dim_line(emoji, label, score) for _, emoji, label, score in items)

    embed.add_field(
        name=_title("⚡ 核心优势"),
        value=clamp_field(_render_dimension_section(top3)),
        inline=False,
    )
    embed.add_field(
        name=_title("⚠️ 重点补强"),
        value=clamp_field(_render_dimension_section(bottom3)),
        inline=False,
    )

    sr_enrichment = raw_stats.get("sr_enrichment") if isinstance(raw_stats, dict) else None
    is_summoners_rift = not (is_arena or is_aram)
    timeline_text = "暂无时间线增强数据"
    if is_summoners_rift and isinstance(sr_enrichment, dict) and sr_enrichment:
        parts: list[str] = []

        def _fmt_delta(value: Any) -> str:
            try:
                return f"{int(round(float(value))):+d}"
            except (TypeError, ValueError):
                return "+0"

        if sr_enrichment.get("gold_diff_10") is not None:
            parts.append(f"GoldΔ10 {_fmt_delta(sr_enrichment.get('gold_diff_10'))}")
        if sr_enrichment.get("xp_diff_10") is not None:
            parts.append(f"XPΔ10 {_fmt_delta(sr_enrichment.get('xp_diff_10'))}")
        if sr_enrichment.get("conversion_rate") is not None:
            try:
                conv_pct = int(round(float(sr_enrichment["conversion_rate"]) * 100))
            except (TypeError, ValueError):
                conv_pct = 0
            parts.append(f"转化率 {conv_pct}%")
        if sr_enrichment.get("ward_rate_per_min") is not None:
            try:
                ward_rate = float(sr_enrichment["ward_rate_per_min"])
                parts.append(f"插眼/分 {ward_rate:.2f}")
            except (TypeError, ValueError):
                parts.append("插眼/分 —")

        if parts:
            timeline_text = " • ".join(parts)

    embed.add_field(
        name=_title("🕒 时间线增强"),
        value=clamp_field(timeline_text),
        inline=False,
    )

    snapshot_block = "```\n数据不可用\n```"
    if isinstance(raw_stats, dict) and raw_stats:
        kills = int(raw_stats.get("kills", 0) or 0)
        deaths = int(raw_stats.get("deaths", 0) or 0)
        assists = int(raw_stats.get("assists", 0) or 0)
        cs_total = int(raw_stats.get("cs", raw_stats.get("total_cs", 0)) or 0)

        cs_per_min: float | None
        try:
            cs_per_min_raw = raw_stats.get("cs_per_min")
            cs_per_min = float(cs_per_min_raw) if cs_per_min_raw is not None else None
        except (TypeError, ValueError):
            cs_per_min = None
        if cs_per_min is None:
            duration_min = None
            if isinstance(sr_enrichment, dict):
                duration_min = sr_enrichment.get("duration_min")
            if duration_min:
                try:
                    cs_per_min = cs_total / max(1.0, float(duration_min))
                except (TypeError, ValueError):
                    cs_per_min = None
        cs_value_text = str(cs_total) if cs_per_min is None else f"{cs_total} ({cs_per_min:.1f})"

        vision_score = int(raw_stats.get("vision_score", 0) or 0)
        damage_dealt = int(round(float(raw_stats.get("damage_dealt", 0) or 0.0)))
        damage_taken = int(round(float(raw_stats.get("damage_taken", 0) or 0.0)))
        level_val = int(raw_stats.get("level", 0) or 0)

        cc_time_val = float(raw_stats.get("cc_time", 0.0) or 0.0)
        cc_score_raw = raw_stats.get("cc_score", 0.0) or 0.0
        try:
            cc_score_int = int(round(float(cc_score_raw)))
        except (TypeError, ValueError):
            cc_score_int = 0

        control_segments: list[str] = []
        if cc_time_val:
            control_segments.append(_format_cc_duration(cc_time_val))
        if cc_score_int:
            control_segments.append(f"{cc_score_int} pts")
        control_value = " / ".join(control_segments) if control_segments else "—"

        snapshot_entries = [
            ("K/D/A", f"{kills} / {deaths} / {assists}"),
            ("CS/分", cs_value_text),
            ("视野", str(vision_score)),
            ("输出/承伤", f"{damage_dealt:,} / {damage_taken:,}"),
            ("等级", str(level_val)),
            ("控制", control_value),
        ]
        label_width = 8
        snapshot_lines = [f"{label:<{label_width}}{value}" for label, value in snapshot_entries]
        snapshot_block = "```text\n" + "\n".join(snapshot_lines) + "\n```"

    embed.add_field(
        name=_title("🧠 个人快照"),
        value=clamp_code_block(snapshot_block),
        inline=False,
    )
