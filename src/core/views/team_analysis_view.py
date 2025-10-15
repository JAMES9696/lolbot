from __future__ import annotations

import os
from collections.abc import Iterable

import discord

from src.contracts.team_analysis import TeamAnalysisReport
from src.core.utils.clamp import clamp_code_block, clamp_field, clamp_text
from src.core.views.emoji_registry import resolve_emoji

_ASCII_TRUE = {"1", "true", "yes", "on"}

_MODE_META = {
    "summoners_rift": ("🗺️", "召唤师峡谷"),
    "aram": ("❄️", "极地大乱斗"),
    "arena": ("⚔️", "斗魂竞技场"),
    "unknown": ("❓", "未知模式"),
}

_DIMENSION_META = {
    "combat_efficiency": ("⚔️", "战斗效率"),
    "economic_management": ("💰", "经济管理"),
    "objective_control": ("🎯", "目标控制"),
    "vision_control": ("👁️", "视野控制"),
    "team_contribution": ("🤝", "团队协同"),
    "survivability": ("🛡️", "生存能力"),
}


def _is_ascii_safe() -> bool:
    value = os.getenv("UI_ASCII_SAFE", os.getenv("CHIMERA_ASCII_SAFE", "0"))
    return str(value).lower() in _ASCII_TRUE


def _progress_bar(score: float, width: int = 10) -> str:
    clamped = max(0.0, min(100.0, float(score)))
    filled = int((clamped / 100.0) * width + 0.5)
    filled = min(width, filled)
    empty = width - filled
    return f"[{'█' * filled}{'▒' * empty}]"


def _mode_meta(mode: str) -> tuple[str, str]:
    return _MODE_META.get(mode, _MODE_META["unknown"])


def _dimension_display(dimension: str, fallback_label: str, ascii_safe: bool) -> tuple[str, str]:
    emoji, label = _DIMENSION_META.get(dimension, ("•", fallback_label))
    if ascii_safe:
        emoji = ""
    return emoji, label


def _select_target(report: TeamAnalysisReport) -> TeamAnalysisReport.TeamPlayerEntry:
    if report.players:
        for player in report.players:
            if player.summoner_name == report.target_player_name:
                return player
        return max(report.players, key=lambda p: p.overall_score)
    raise ValueError("TeamAnalysisReport.players is empty")


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


def _ddragon_icon(champion_name: str, version: str | None = None) -> str:
    """Generate Data Dragon champion icon URL.

    Args:
        champion_name: Champion name (e.g., "Qiyana")
        version: Optional game version (e.g., "14.10.1.534" or "14.10.1_14.10.1.454").
                 Will be normalized via _normalize_game_version().

    Returns:
        CDN URL for champion icon
    """
    # Normalize version string to X.Y.Z format
    normalized_version = _normalize_game_version(version)

    # Fallback: use latest stable version if not provided or invalid
    if not normalized_version:
        try:
            from src.core.services.team_builds_enricher import DataDragonClient

            dd = DataDragonClient()
            normalized_version = dd.get_latest_version()
        except Exception:
            normalized_version = "14.23.1"  # Conservative fallback to recent stable

    safe_name = champion_name or "Unknown"
    return (
        f"https://ddragon.leagueoflegends.com/cdn/{normalized_version}/img/champion/{safe_name}.png"
    )


def _average(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _derive_highlights(
    report: TeamAnalysisReport,
    target: TeamAnalysisReport.TeamPlayerEntry,
    *,
    top: bool,
) -> list[TeamAnalysisReport.DimensionHighlight]:
    dims: list[TeamAnalysisReport.DimensionHighlight] = []
    aggregates = report.aggregates
    base_dimensions = [
        ("combat_efficiency", "战斗效率", target.combat_score, aggregates.combat_avg),
        ("economic_management", "经济管理", target.economy_score, aggregates.economy_avg),
        ("objective_control", "目标控制", target.objective_score, aggregates.objective_avg),
        ("vision_control", "视野控制", target.vision_score, aggregates.vision_avg),
        ("team_contribution", "团队协同", target.teamplay_score, aggregates.teamplay_avg),
    ]
    if report.game_mode == "aram":
        base_dimensions = [
            entry
            for entry in base_dimensions
            if entry[0] not in {"objective_control", "vision_control"}
        ]
    for key, label, score, avg in base_dimensions:
        dims.append(
            TeamAnalysisReport.DimensionHighlight(
                dimension=key,
                label=label,
                score=round(float(score), 1),
                delta_vs_team=round(float(score) - float(avg), 1),
            )
        )
    if target.survivability_score is not None:
        avg_surv = _average(p.survivability_score for p in report.players)
        dims.append(
            TeamAnalysisReport.DimensionHighlight(
                dimension="survivability",
                label="生存能力",
                score=round(float(target.survivability_score), 1),
                delta_vs_team=round(float(target.survivability_score) - avg_surv, 1),
            )
        )
    dims.sort(key=lambda h: h.delta_vs_team or 0.0, reverse=top)
    return dims[:3]


def _format_highlights(
    highlights: Iterable[TeamAnalysisReport.DimensionHighlight],
    *,
    ascii_safe: bool,
    empty_text: str,
) -> str:
    lines: list[str] = []
    for item in highlights:
        emoji, label = _dimension_display(item.dimension, item.label, ascii_safe)
        delta_parts: list[str] = []
        if item.delta_vs_team is not None:
            sign = "+" if item.delta_vs_team >= 0 else ""
            delta_parts.append(f"{sign}{item.delta_vs_team:.1f} vs 队均")
        if item.delta_vs_opponent is not None:
            sign = "+" if item.delta_vs_opponent >= 0 else ""
            delta_parts.append(f"{sign}{item.delta_vs_opponent:.1f} vs 对位")
        delta = f" ({' / '.join(delta_parts)})" if delta_parts else ""
        bar = _progress_bar(item.score)
        lines.append(f"{emoji} {label}: {bar} {item.score:.1f}分{delta}".strip())
    return "\n".join(lines) if lines else empty_text


def _format_enhancements(
    metrics: TeamAnalysisReport.EnhancementMetrics | None,
    *,
    mode: str,
) -> str:
    if mode == "aram":
        return "ARAM 模式暂无时间线增强指标"
    if metrics is None:
        return "暂无时间线增强数据"
    parts: list[str] = []
    if metrics.gold_diff_10 is not None:
        parts.append(f"GoldΔ10 {metrics.gold_diff_10:+}")
    if metrics.xp_diff_10 is not None:
        parts.append(f"XPΔ10 {metrics.xp_diff_10:+}")
    if metrics.conversion_rate is not None:
        parts.append(f"转化率 {metrics.conversion_rate * 100:.1f}%")
    if metrics.ward_rate_per_min is not None:
        parts.append(f"插眼/分 {metrics.ward_rate_per_min:.2f}")
    return " • ".join(parts) if parts else "暂无时间线增强数据"


def _format_builds_section(report: TeamAnalysisReport) -> str:
    """Render build/rune enhancement into a Discord-safe snippet.

    Enhanced version supporting:
    - Priority: builds_summary_text (pre-formatted)
    - Fallback: builds_metadata with items, runes, diff, visuals
    - Emoji resolution for champions/items (with fallback)
    """
    from src.core.utils.safe_truncate import safe_truncate

    # Priority: use pre-formatted summary
    summary = (report.builds_summary_text or "").strip()
    if summary:
        return safe_truncate(summary, 950)

    # Fallback: construct from metadata
    metadata = report.builds_metadata or {}
    lines: list[str] = []

    # Items (with emoji support)
    items = metadata.get("items")
    if items:
        # Limit to first 6 items for readability
        item_names = []
        for item in list(items)[:6]:
            item_str = str(item)
            # Try emoji resolution (e.g., "item:破败王者之刃")
            item_emoji = resolve_emoji(f"item:{item_str}", "")
            if item_emoji:
                item_names.append(f"{item_emoji} {item_str}")
            else:
                item_names.append(item_str)
        joined = " · ".join(item_names)
        lines.append(f"出装: {joined}")

    # Runes
    primary = metadata.get("primary_tree_name")
    keystone = metadata.get("primary_keystone")
    secondary = metadata.get("secondary_tree_name")
    rune_parts = []
    if primary:
        rune_parts.append(str(primary))
    if keystone:
        rune_parts.append(str(keystone))
    if secondary:
        rune_parts.append(f"次系 {secondary}")
    if rune_parts:
        lines.append("符文: " + " - ".join(rune_parts))

    # Diff (recommended vs actual)
    diff = metadata.get("diff", [])
    if diff and len(diff) > 0:
        diff_text = " vs ".join(str(d) for d in diff[:2])  # Limit to 2 items
        lines.append(f"差异: {diff_text}")

    # Visuals hint
    visuals = metadata.get("visuals", [])
    if visuals:
        lines.append("📊 (见附件：出装对比图)")

    # OPGG availability
    if metadata.get("opgg_available"):
        lines.append("OPGG 推荐对比：数据已加载")

    if not lines:
        return "暂无出装/符文增强"

    return safe_truncate("\n".join(lines), 950)


def _format_team_snapshot(
    friendly: list[TeamAnalysisReport.TeamPlayerEntry],
    opponents: list[TeamAnalysisReport.TeamPlayerEntry] | None,
    *,
    ascii_safe: bool,
) -> str:
    friends_sorted = sorted(
        friendly,
        key=lambda p: (p.team_rank if p.team_rank is not None else 999, -p.overall_score),
    )
    opponents_sorted = sorted(
        opponents or [],
        key=lambda p: (p.team_rank if p.team_rank is not None else 999, -p.overall_score),
    )

    def _entry_line(player: TeamAnalysisReport.TeamPlayerEntry | None) -> str:
        if player is None:
            return "-"
        rank = player.team_rank if player.team_rank is not None else "-"
        name = player.summoner_name
        if not ascii_safe:
            champ_emoji = resolve_emoji(f"champion:{player.champion_name}", "")
            if champ_emoji:
                name = f"{champ_emoji} {name}"
        name = clamp_text(name, 14)
        dmg_k = player.damage_dealt / 1000.0
        dmg_display = f"{dmg_k:.1f}k" if dmg_k >= 1 else str(player.damage_dealt)
        kda = f"{player.kills}/{player.deaths}/{player.assists}"
        vs_display = f"{player.vision_score:.1f}" if player.vision_score else "0"
        return (
            f"#{rank:<2} {name:<14} G{player.overall_score:>5.1f} "
            f"C{player.combat_score:>5.0f} T{player.teamplay_score:>5.0f} "
            f"KDA {kda:<9} Dmg {dmg_display:<6} VS {vs_display:>5}"
        )

    max_rows = max(len(friends_sorted), len(opponents_sorted)) or 0
    header_left = "我方阵容"
    header_right = "敌方阵容"
    lines = [f"{header_left:<45} | {header_right}"]
    for idx in range(max_rows):
        left = _entry_line(friends_sorted[idx] if idx < len(friends_sorted) else None)
        right = _entry_line(opponents_sorted[idx] if idx < len(opponents_sorted) else None)
        lines.append(f"{left:<45} | {right}")

    snapshot = "\n".join(lines)
    return f"```\n{clamp_code_block(snapshot, limit=1800)}\n```"


def _build_fallback_narrative(
    report: TeamAnalysisReport,
    strengths: list[TeamAnalysisReport.DimensionHighlight],
    weaknesses: list[TeamAnalysisReport.DimensionHighlight],
) -> str:
    if not strengths or not weaknesses:
        return (
            f"{report.target_player_name} 的队伍整体评分 {report.aggregates.overall_avg:.1f} 分，"
            "建议结合语音沟通，保持资源布控节奏。"
        )
    top_strength = strengths[0]
    top_weakness = weaknesses[0]
    strength_delta = top_strength.delta_vs_team or 0.0
    weakness_delta = top_weakness.delta_vs_team or 0.0
    return (
        f"{report.target_player_name} 在{top_strength.label}表现突出（{top_strength.score:.1f}分，"
        f"领先队均{strength_delta:+.1f}）。然而在{top_weakness.label}仅有{top_weakness.score:.1f}分"
        f"（落后{weakness_delta:+.1f}），建议赛中提前布控关键资源点，"
        "并与队友共享视野与抱团时机。"
    )


def _format_footer(report: TeamAnalysisReport) -> str:
    footer = "蔚-上城人 | V2 Team Analysis"
    telemetry = report.observability
    trace_id = getattr(report, "trace_task_id", None)
    parts: list[str] = []
    if telemetry:
        footer = f"{footer} | {telemetry.session_id}:{telemetry.execution_branch_id}"
        if telemetry.fetch_ms is not None:
            parts.append(f"Φfetch={telemetry.fetch_ms:.0f}ms")
        if telemetry.scoring_ms is not None:
            parts.append(f"Φscore={telemetry.scoring_ms:.0f}ms")
        if telemetry.llm_ms is not None:
            parts.append(f"Φllm={telemetry.llm_ms:.0f}ms")
        if telemetry.webhook_ms is not None:
            parts.append(f"Φwebhook={telemetry.webhook_ms:.0f}ms")
    if trace_id:
        footer = f"{footer} | Task {trace_id}"
    if parts:
        footer = f"{footer} | {' '.join(parts)}"
    return footer


def render_team_overview_embed(report: TeamAnalysisReport) -> discord.Embed:
    # Render the single-embed TEAM overview with narrative + metrics.

    if not report.players:
        raise ValueError("TeamAnalysisReport.players cannot be empty")

    ascii_safe = _is_ascii_safe()
    target = _select_target(report)

    strengths = report.strengths or _derive_highlights(report, target, top=True)
    weaknesses = report.weaknesses or _derive_highlights(report, target, top=False)

    summary = report.summary_text or _build_fallback_narrative(report, strengths, weaknesses)
    description = clamp_text(summary or "", 3920, preserve_markdown=True)

    result_emoji = "🏆" if report.team_result == "victory" else "💔"
    mode_emoji, mode_label = _mode_meta(report.game_mode)
    title = f"{result_emoji} {mode_emoji} 团队综合分析 | {target.champion_name}"
    if ascii_safe:
        title = title.replace(result_emoji + " ", "").replace(mode_emoji + " ", "")

    color = 0x2ECC71 if report.team_result == "victory" else 0xE74C3C
    embed = discord.Embed(title=title, description=description, color=color)

    thumbnail = target.champion_icon_url or _ddragon_icon(target.champion_name)
    embed.set_thumbnail(url=thumbnail)

    embed.add_field(
        name="⚡ 核心优势",
        value=_format_highlights(strengths, ascii_safe=ascii_safe, empty_text="暂无优势数据"),
        inline=False,
    )
    embed.add_field(
        name="⚠️ 重点补强",
        value=_format_highlights(
            weaknesses,
            ascii_safe=ascii_safe,
            empty_text="暂无需要补强的维度",
        ),
        inline=False,
    )
    embed.add_field(
        name="🕒 时间线增强",
        value=_format_enhancements(report.enhancements, mode=report.game_mode),
        inline=False,
    )
    embed.add_field(
        name="🧠 团队阵容",
        value=_format_team_snapshot(
            report.players,
            report.opponent_players or [],
            ascii_safe=ascii_safe,
        ),
        inline=False,
    )
    embed.add_field(
        name="🛠 出装 & 符文",
        value=_format_builds_section(report),
        inline=False,
    )

    if report.game_mode == "arena" and report.arena_duo:
        duo = report.arena_duo
        duo_line = f"{duo.me_name} · {duo.me_champion}"
        if duo.partner_name or duo.partner_champion:
            duo_line += f"  +  {duo.partner_name or '-'} · {duo.partner_champion or '-'}"
        if duo.placement:
            duo_line += f"  |  第{duo.placement}名"
        embed.add_field(name="Arena Duo", value=duo_line, inline=False)
    elif report.arena_rounds_block:
        embed.add_field(
            name="Arena 轮次摘要",
            value=clamp_field(str(report.arena_rounds_block), limit=1000),
            inline=False,
        )

    embed.add_field(
        name="比赛信息",
        value=f"`{report.match_id}` • `{report.team_region.upper()}` • {mode_label}",
        inline=False,
    )

    embed.set_footer(text=_format_footer(report))
    return embed
