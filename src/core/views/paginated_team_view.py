"""Paginated Discord View for V2 Team Analysis.

This module implements a multi-page Discord UI for displaying team analysis
results with pagination controls, following Discord's best practices for
interactive message components.

Architecture:
- Page 1: Team-level summary and key insights
- Page 2: Friendly team (5 players) detailed analysis
- Page 3: Enemy team (5 players) detailed analysis (optional future enhancement)
"""

import asyncio
import importlib
import logging
import os
from typing import Any

import discord

from src.contracts.v2_team_analysis import V2PlayerAnalysisResult, V2TeamAnalysisReport
from src.core.observability import llm_debug_wrapper
from src.core.utils.clamp import clamp_field
from src.core.views.ascii_card import _bar20
from src.core.views.emoji_registry import resolve_emoji

logger = logging.getLogger(__name__)


def _clamp_field(text: str, limit: int = 1000) -> str:
    value = (text or "").strip()
    if not value:
        return "（无数据）"
    return clamp_field(value, limit=limit)


class PaginatedTeamAnalysisView(discord.ui.View):
    """Discord UI View with pagination for team analysis results.

    This view provides:
    - Multi-page navigation for displaying 10 players (5 friendly + 5 enemy)
    - Feedback buttons (👍/👎/⭐) for A/B testing
    - Automatic timeout after 15 minutes of inactivity

    Design follows Mobalytics Builds Widget patterns for compact data display.
    """

    def __init__(
        self,
        report: V2TeamAnalysisReport,
        match_id: str,
        timeout: float = 900.0,  # 15 minutes
    ) -> None:
        """Initialize the paginated view.

        Args:
            report: Complete team analysis report with all player data
            match_id: Match ID for feedback tracking
            timeout: View timeout in seconds (default: 15 minutes)
        """
        super().__init__(timeout=timeout)
        self.report = report
        self.match_id = match_id
        self.current_page = 0
        # Default pages: summary + team details. Arena adds a dedicated page.
        self.max_pages = 3 if report.game_mode == "arena" else 2

        # Add feedback buttons (persistent across all pages)
        self._add_feedback_buttons()

        self._arena_sections: dict[str, str] = {}
        self._arena_section = "overview"
        if report.game_mode == "arena":
            self._arena_sections = self._build_arena_sections()
            if self._arena_sections:
                if self._arena_section not in self._arena_sections:
                    self._arena_section = next(iter(self._arena_sections))
                self.add_item(_ArenaSectionSelect(self))

    def _get_mode_emoji_and_label(self) -> tuple[str, str]:
        """Get emoji and label for game mode.

        V2.3 Enhancement: Mode-aware UI with clear visual identifiers.

        Returns:
            Tuple of (emoji, mode_label) for display
        """
        mode_map = {
            "aram": ("❄️", "ARAM（极地大乱斗）"),
            "arena": ("⚔️", "Arena（斗魂竞技场）"),
            "summoners_rift": ("🏞️", "召唤师峡谷"),
            "unknown": ("❓", "未知模式"),
        }
        emoji, label = mode_map.get(self.report.game_mode, ("🎮", "游戏模式"))
        return emoji, label

    def _should_show_vision_control(self) -> bool:
        """Determine if vision control metric should be displayed.

        V2.3 Enhancement: Mode-specific metric filtering.

        Returns:
            True if vision control is relevant for current game mode
        """
        # Vision control is not meaningful in ARAM (single lane, no wards)
        return self.report.game_mode not in ["aram", "unknown"]

    def _add_feedback_buttons(self) -> None:
        """Add feedback buttons for A/B testing.

        Custom IDs follow schema: chimera:fb:{type}:{match_id}
        where type in {up, down, star}
        """
        # Thumbs up button
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="👍",
                custom_id=f"chimera:fb:up:{self.match_id}",
                row=4,  # Bottom row to avoid conflict with navigation
            )
        )

    async def on_timeout(self) -> None:
        """Disable interactive components when the view times out."""
        for item in self.children:
            item.disabled = True

    def _use_async_section_fetch(self) -> bool:
        return os.getenv("CHIMERA_ARENA_SECTION_ASYNC", "0").lower() in {"1", "true", "yes", "on"}

    async def _handle_async_section(
        self,
        interaction: discord.Interaction,
        section_key: str,
    ) -> None:
        """Load arena section content asynchronously and refresh the message."""

        correlation_id = "unknown:unknown"
        observability = getattr(self.report, "observability", None)
        if observability:
            session_id = getattr(observability, "session_id", "unknown") or "unknown"
            branch_id = getattr(observability, "execution_branch_id", "unknown") or "unknown"
            correlation_id = f"{session_id}:{branch_id}"

        updated = False
        try:
            logger.info(
                "arena_section_fetch_start",
                extra={
                    "match_id": self.match_id,
                    "section": section_key,
                    "correlation_id": correlation_id,
                },
            )
            new_value = await self._fetch_arena_section_async(section_key)
            if isinstance(new_value, str) and new_value.strip():
                self._arena_sections[section_key] = new_value.strip()
                updated = True
            elif section_key not in self._arena_sections:
                await interaction.followup.send(
                    "⚠️ 该分段暂无可用数据，请稍后再试。", ephemeral=True
                )
                return

            await interaction.followup.edit_message(embed=self._create_page_embed(), view=self)
            logger.info(
                "arena_section_fetch_complete",
                extra={
                    "match_id": self.match_id,
                    "section": section_key,
                    "correlation_id": correlation_id,
                    "updated": updated,
                },
            )
        except Exception:
            logger.exception(
                "arena_section_fetch_error",
                extra={
                    "match_id": self.match_id,
                    "section": section_key,
                    "correlation_id": correlation_id,
                },
            )
            await interaction.followup.send("❌ 加载失败，请稍后重试。", ephemeral=True)

    async def _fetch_arena_section_async(self, section_key: str) -> str | None:
        """Fetch Arena section content asynchronously via configured handler.

        Environment variable: CHIMERA_ARENA_SECTION_HANDLER
        Expected format: "module.path.function_name"

        Args:
            section_key: Section identifier (e.g., "overview", "highlights")

        Returns:
            Section content string, or None if handler unavailable/fails
        """
        handler_path = os.getenv("CHIMERA_ARENA_SECTION_HANDLER")
        if not handler_path:
            logger.debug(
                "arena_section_handler_not_configured",
                extra={"section_key": section_key, "match_id": self.match_id},
            )
            return self._arena_sections.get(section_key)

        try:
            # Parse and import handler
            module_name, func_name = handler_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            handler = getattr(module, func_name)

            logger.info(
                "arena_section_handler_invoked",
                extra={
                    "section_key": section_key,
                    "match_id": self.match_id,
                    "handler": handler_path,
                },
            )

            @llm_debug_wrapper(capture_args=True, capture_result=True, log_level="INFO")
            async def _invoke(func, *args, **kwargs):
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            result = await _invoke(
                handler,
                section_key=section_key,
                report_payload=self.report.model_dump(mode="json"),
            )

            # Validate return type
            if result is None:
                logger.warning(
                    "arena_section_handler_returned_none",
                    extra={
                        "section_key": section_key,
                        "match_id": self.match_id,
                        "fallback_used": True,
                    },
                )
                return self._arena_sections.get(section_key)

            if not isinstance(result, str):
                logger.warning(
                    "arena_section_handler_invalid_type",
                    extra={
                        "section_key": section_key,
                        "match_id": self.match_id,
                        "result_type": type(result).__name__,
                        "fallback_used": True,
                    },
                )
                return self._arena_sections.get(section_key)

            if not result.strip():
                logger.warning(
                    "arena_section_handler_empty_result",
                    extra={
                        "section_key": section_key,
                        "match_id": self.match_id,
                        "fallback_used": True,
                    },
                )
                return self._arena_sections.get(section_key)

            logger.info(
                "arena_section_handler_success",
                extra={
                    "section_key": section_key,
                    "match_id": self.match_id,
                    "result_length": len(result),
                },
            )
            return result

        except Exception as exc:
            logger.exception(
                "arena_section_handler_failed",
                extra={
                    "handler": handler_path,
                    "section_key": section_key,
                    "match_id": self.match_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "fallback_used": True,
                },
            )
            return self._arena_sections.get(section_key)

    def _build_arena_sections(self) -> dict[str, str]:
        sections: dict[str, str] = {}
        block = getattr(self.report, "arena_rounds_block", None)
        lines = [line.strip() for line in str(block or "").splitlines() if line.strip()]

        if lines:
            summary_lines = [
                line for line in lines if line.startswith("名次") or line.startswith("战绩")
            ]
            if summary_lines:
                sections["overview"] = "\n".join(summary_lines)

            # High-light rounds (header + bullet items)
            if "高光回合:" in lines:
                idx = lines.index("高光回合:")
                highlights = [lines[idx]]
                cursor = idx + 1
                while cursor < len(lines) and lines[cursor].startswith("•"):
                    highlights.append(lines[cursor])
                    cursor += 1
                if len(highlights) > 1:
                    sections["highlights"] = "\n".join(highlights)

            tough_line = next((line for line in lines if line.startswith("艰难回合")), None)
            if tough_line:
                sections["tough"] = tough_line

            streak_line = next((line for line in lines if "连胜" in line and "连败" in line), None)
            if streak_line:
                sections["streak"] = streak_line

            traj_line = next((line for line in lines if line.startswith("轨迹")), None)
            if traj_line:
                sections["trajectory"] = traj_line

            sections.setdefault("full", "\n".join(lines))

        # Enrich trajectory details from structured payload when available
        traj = getattr(self.report, "arena_trajectory", None)
        traj_parts: list[str] = []
        if traj:
            sequence = getattr(traj, "sequence_compact", None)
            if sequence:
                traj_parts.append(f"轨迹: {sequence}")
            longest_win = getattr(traj, "longest_win_len", None)
            if longest_win:
                win_range = getattr(traj, "longest_win_range", None)
                if win_range:
                    traj_parts.append(
                        f"最长连胜 {longest_win} 局 (R{win_range[0]}–R{win_range[1]})"
                    )
                else:
                    traj_parts.append(f"最长连胜 {longest_win} 局")
            longest_lose = getattr(traj, "longest_lose_len", None)
            if longest_lose:
                lose_range = getattr(traj, "longest_lose_range", None)
                if lose_range:
                    traj_parts.append(
                        f"最长连败 {longest_lose} 局 (R{lose_range[0]}–R{lose_range[1]})"
                    )
                else:
                    traj_parts.append(f"最长连败 {longest_lose} 局")
        if traj_parts and "trajectory" not in sections:
            sections["trajectory"] = "\n".join(traj_parts)

        if not sections and traj_parts:
            sections["overview"] = "\n".join(traj_parts)

        return sections

    @staticmethod
    def _arena_section_title(key: str) -> str:
        mapping = {
            "overview": "📊 战绩总结",
            "highlights": "🌟 高光回合",
            "tough": "⚠️ 艰难回合",
            "streak": "📈 连胜/连败",
            "trajectory": "🧭 回合轨迹",
            "full": "🗂️ 全部摘要",
        }
        return mapping.get(key, "Arena 摘要")

    @discord.ui.button(
        label="◀️ 上一页",
        style=discord.ButtonStyle.secondary,
        row=0,
        custom_id="team_analysis:prev",
    )
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle previous page button click."""
        self.current_page = max(0, self.current_page - 1)
        await self._update_message(interaction)

    @discord.ui.button(
        label="▶️ 下一页",
        style=discord.ButtonStyle.secondary,
        row=0,
        custom_id="team_analysis:next",
    )
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle next page button click."""
        self.current_page = min(self.max_pages - 1, self.current_page + 1)
        await self._update_message(interaction)

    async def _update_message(self, interaction: discord.Interaction) -> None:
        """Update the message with current page content.

        Args:
            interaction: Discord interaction to respond to
        """
        embed = self._create_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def _create_page_embed(self) -> discord.Embed:
        """Create embed for current page.

        Returns:
            Discord Embed configured for the current page
        """
        if self.current_page == 0:
            return self._create_summary_page()
        elif self.current_page == 1:
            return self._create_team_details_page()
        elif self.current_page == 2 and self.report.game_mode == "arena":
            return self._create_arena_page()
        else:
            # Fallback (should never reach here with current max_pages=2)
            return self._create_summary_page()

    def _create_summary_page(self) -> discord.Embed:
        """Create Page 1: Team summary and key insights.

        V2.1 Enhancement: Added clear page indicator in title for mobile UX.
        V2.3 Enhancement: Mode-aware display with emoji identifiers.

        Returns:
            Discord Embed with team-level summary
        """
        result_emoji = "🏆" if self.report.match_result == "victory" else "💔"
        mode_emoji, mode_label = self._get_mode_emoji_and_label()

        # V2.3: Include mode emoji in title for immediate recognition
        # V2.1: Page indicator in title for mobile visibility
        embed = discord.Embed(
            title=f"{result_emoji} {mode_emoji} 团队分析总览 [第 1/{self.max_pages} 页]",
            description=(
                f"**游戏模式:** {mode_label}\n"
                f"**Match ID:** `{self.report.match_id}`\n"
                f"**目标玩家:** {self.report.target_player_name}"
            ),
            color=0x5865F2 if self.report.match_result == "victory" else 0xE74C3C,
        )

        # Team-level insight
        if self.report.team_summary_insight:
            embed.add_field(
                name="📊 团队整体评价",
                value=self.report.team_summary_insight,
                inline=False,
            )

        # Top 3 performers (by team_rank)
        sorted_players = sorted(self.report.team_analysis, key=lambda p: p.team_rank)
        top_3 = sorted_players[:3]

        def _line(p: V2PlayerAnalysisResult) -> str:
            ce = resolve_emoji(f"champion:{p.champion_name}", "")
            ctag = (ce + " ") if ce else ""
            return f"**#{p.team_rank}** {p.summoner_name} ({ctag}{p.champion_name}) - {p.overall_score:.1f}分"

        top_3_text = "\n".join([_line(p) for p in top_3])
        embed.add_field(name="🌟 队内前三名", value=top_3_text, inline=False)

        # V2.1: Simplified footer for mobile readability
        from src.core.views.analysis_view import _format_duration_ms

        embed.set_footer(
            text=f"A/B Cohort: {self.report.ab_cohort or 'N/A'} | {_format_duration_ms(self.report.processing_duration_ms)}"
        )

        return embed

    def _create_team_details_page(self) -> discord.Embed:
        """Create Page 2: Detailed analysis for all 5 team members.

        V2.1 Enhancement:
        - Added page indicator in title
        - Optimized field layout for mobile readability

        V2.3 Enhancement:
        - Mode-aware metric filtering (e.g., hide Vision in ARAM)
        - Conditional rendering based on game mode

        Returns:
            Discord Embed with per-player analysis details
        """
        result_emoji = "🏆" if self.report.match_result == "victory" else "💔"
        mode_emoji, mode_label = self._get_mode_emoji_and_label()

        # V2.3: Include mode emoji in title
        # V2.1: Page indicator in title for mobile visibility
        embed = discord.Embed(
            title=f"{result_emoji} {mode_emoji} 团队成员详细分析 [第 2/{self.max_pages} 页]",
            description=f"**游戏模式:** {mode_label}\n**Match ID:** `{self.report.match_id}`",
            color=0x5865F2 if self.report.match_result == "victory" else 0xE74C3C,
        )

        # Sort by team_rank for display
        sorted_players = sorted(self.report.team_analysis, key=lambda p: p.team_rank)

        for player in sorted_players:
            # V2.1: Compact player field optimized for mobile screens
            # V2.3: Conditional rendering based on game mode
            # Uses inline=False for full width to prevent text truncation

            # Build field value with mode-aware metric filtering
            ce = resolve_emoji(f"champion:{player.champion_name}", "")
            ctag = (ce + " ") if ce else ""
            field_value = (
                f"**{ctag}{player.champion_name}** | 综合得分: **{player.overall_score:.1f}** (队内#{player.team_rank})\n"
                f"{_bar20(player.overall_score)}\n"
            )

            # V2.3: Only show strength if it's not Vision in ARAM mode
            # (or if vision control is relevant for this mode)
            show_strength = (
                self._should_show_vision_control() or player.top_strength_dimension != "Vision"
            )
            show_weakness = (
                self._should_show_vision_control() or player.top_weakness_dimension != "Vision"
            )

            if show_strength:
                field_value += (
                    f"✨ 优势: {player.top_strength_dimension} "
                    f"({player.top_strength_score:.1f}, 队内#{player.top_strength_team_rank})\n"
                )

            if show_weakness:
                field_value += (
                    f"⚠️ 劣势: {player.top_weakness_dimension} "
                    f"({player.top_weakness_score:.1f}, 队内#{player.top_weakness_team_rank})\n"
                )

            field_value += f"📝 {player.narrative_summary}"

            embed.add_field(
                name=f"#{player.team_rank} {player.summoner_name}", value=field_value, inline=False
            )

        # V2.1: Simplified footer for mobile readability
        embed.set_footer(text=f"Variant: {self.report.variant_id or 'N/A'}")

        return embed

    def _create_arena_page(self) -> discord.Embed:
        """Create Arena-only page: Duo info + round trajectory summary.

        Note: V2 report schema may not carry Arena extras. We best-effort read
        optional attributes that upstream may attach (e.g., arena_duo, arena_rounds_block).
        """
        result_emoji = "🏆" if self.report.match_result == "victory" else "💔"
        embed = discord.Embed(
            title=f"{result_emoji} ⚔️ Arena 专页 [第 3/{self.max_pages} 页]",
            description=f"**Match ID:** `{self.report.match_id}`\n**目标玩家:** {self.report.target_player_name}",
            color=0x5865F2 if self.report.match_result == "victory" else 0xE74C3C,
        )

        # Duo (best-effort)
        duo = getattr(self.report, "arena_duo", None)
        if duo:
            me = getattr(duo, "me_name", "-")
            mech = getattr(duo, "me_champion", "-")
            pa = getattr(duo, "partner_name", None)
            pach = getattr(duo, "partner_champion", None)
            place = getattr(duo, "placement", None)
            duo_line = f"{me} · {mech}"
            if pa or pach:
                duo_line += f"  +  {pa or '-'} · {pach or '-'}"
            if place:
                duo_line += f"  |  第{place}名"
            embed.add_field(name="Duo", value=duo_line, inline=False)
        else:
            embed.add_field(name="Duo", value="（无 Duo 元数据；请查看概览卡）", inline=False)

        # Rounds (best-effort)
        if self._arena_sections:
            section_key = (
                self._arena_section
                if self._arena_section in self._arena_sections
                else next(iter(self._arena_sections))
            )
            section_title = self._arena_section_title(section_key)
            embed.add_field(
                name=section_title,
                value=_clamp_field(self._arena_sections.get(section_key, "")),
                inline=False,
            )
        else:
            rounds_block = getattr(self.report, "arena_rounds_block", None)
            if rounds_block:
                embed.add_field(
                    name="Arena 摘要", value=_clamp_field(str(rounds_block)), inline=False
                )
            else:
                embed.add_field(name="Arena 摘要", value="（无回合摘要）", inline=False)

        # Top-3 events (kills / damage dealt / damage taken)
        def _round_line(r: Any) -> str:
            return (
                f"R{getattr(r, 'round_number', getattr(r, 'n', '?'))}: "
                f"{getattr(r, 'kills', getattr(r, 'k', 0))}杀/"
                f"{getattr(r, 'deaths', getattr(r, 'd', 0))}死, "
                f"伤害{getattr(r, 'damage_dealt', getattr(r, 'dd', 0))} 承伤{getattr(r, 'damage_taken', getattr(r, 'dt', 0))}"
            )

        top_k = getattr(self.report, "arena_top_kills", None)
        top_dd = getattr(self.report, "arena_top_damage_dealt", None)
        top_dt = getattr(self.report, "arena_top_damage_taken", None)

        if top_k or top_dd or top_dt:
            lines = []
            if top_k:
                lines.append("击杀 Top-3:")
                lines += [f"• {_round_line(r)}" for r in top_k][:3]
            if top_dd:
                lines.append("输出 Top-3:")
                lines += [f"• {_round_line(r)}" for r in top_dd][:3]
            if top_dt:
                lines.append("承伤 Top-3:")
                lines += [f"• {_round_line(r)}" for r in top_dt][:3]
            embed.add_field(name="回合事件 Top-3", value="\n".join(lines)[:1000], inline=False)

        embed.set_footer(text="Arena 专页：展示 Duo 与回合摘要（试验性）")
        return embed


class _ArenaSectionSelect(discord.ui.Select[Any]):
    """Select menu for Arena data sections."""

    LABELS = {
        "overview": "📊 战绩总结",
        "highlights": "🌟 高光回合",
        "tough": "⚠️ 艰难回合",
        "streak": "📈 连胜/连败",
        "trajectory": "🧭 回合轨迹",
        "full": "🗂️ 全部摘要",
    }

    def __init__(self, parent: PaginatedTeamAnalysisView) -> None:
        options = []
        for key in parent._arena_sections.keys():
            label = self.LABELS.get(key, key)
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    default=(key == parent._arena_section),
                )
            )
        super().__init__(
            placeholder="选择 Arena 数据段",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )
        self._view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        section_key = self.values[0]
        self._view._arena_section = section_key
        if self._view._use_async_section_fetch():
            await interaction.response.defer()
            await self._view._handle_async_section(interaction, section_key)
        else:
            await self._view._update_message(interaction)
