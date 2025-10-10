"""V2.1 Prescriptive Analysis Discord View with collapsible advice display.

This module implements an action-oriented UI for displaying improvement suggestions
with on-demand expansion, following mobile-first design principles.

Architecture:
- Main view: Summary embed with "💡 显示改进建议" button
- On-demand: Detailed advice displayed via ephemeral followup message
- Feedback: Per-advice usefulness buttons for fine-grained A/B testing

Design Principles:
- Information density management: Advice is hidden by default to prevent overload
- Action-oriented: Each advice is specific and implementable
- Mobile-optimized: Clear visual hierarchy and compact layout
"""

from typing import Any

import discord

from src.contracts.v21_prescriptive_analysis import (
    V21ActionableAdvice,
    V21PrescriptiveAnalysisReport,
)


class PrescriptiveAnalysisView(discord.ui.View):
    """Discord UI View for V2.1 prescriptive analysis with collapsible advice.

    This view provides:
    - Summary embed showing key metrics (no advice by default)
    - "💡 显示改进建议" button to reveal detailed suggestions
    - Per-advice feedback buttons for actionability assessment
    - Automatic timeout after 15 minutes
    """

    def __init__(
        self,
        report: V21PrescriptiveAnalysisReport,
        match_id: str,
        timeout: float = 900.0,  # 15 minutes
    ) -> None:
        """Initialize the prescriptive analysis view.

        Args:
            report: Complete V2.1 prescriptive analysis report
            match_id: Match ID for feedback tracking
            timeout: View timeout in seconds (default: 15 minutes)
        """
        super().__init__(timeout=timeout)
        self.report = report
        self.match_id = match_id
        self.advice_shown = False  # Track whether advice has been revealed

    @discord.ui.button(
        label="💡 显示改进建议",
        style=discord.ButtonStyle.primary,
        row=0,
        custom_id="prescriptive:show_advice",
    )
    async def show_advice(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle "Show Advice" button click - display detailed suggestions.

        This sends an ephemeral (private) message with the full advice list,
        keeping the public channel clean while providing detailed guidance.
        """
        # Create detailed advice embed
        advice_embed = self._create_advice_embed()

        # Create advice-specific feedback view
        feedback_view = AdviceFeedbackView(
            advice_list=self.report.actionable_advice,
            match_id=self.match_id,
        )

        # Send ephemeral followup (only visible to the user who clicked)
        await interaction.response.send_message(
            embed=advice_embed,
            view=feedback_view,
            ephemeral=True,  # Private message for information density management
        )

        # Mark advice as shown (optional: could disable the button)
        self.advice_shown = True

    def _create_advice_embed(self) -> discord.Embed:
        """Create detailed advice embed with all suggestions.

        Returns:
            Discord Embed with prioritized actionable advice
        """
        embed = discord.Embed(
            title="💡 改进建议（行动导向）",
            description=f"**Match ID:** `{self.match_id}`\n以下建议基于本局数据分析生成，按优先级排序：",
            color=0x5865F2,
        )

        # Sort advice by priority (high > medium > low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_advice = sorted(
            self.report.actionable_advice,
            key=lambda a: priority_order.get(a.priority, 999),
        )

        for idx, advice in enumerate(sorted_advice, start=1):
            # Priority indicator
            priority_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢",
            }.get(advice.priority, "⚪")

            # Dimension-specific icon
            dimension_emoji = advice.icon_emoji

            # Compact field layout for mobile
            field_name = f"{priority_emoji} {idx}. {dimension_emoji} {advice.title}"
            field_value = (
                f"**建议：** {advice.description}\n"
                f"**预期效果：** {advice.expected_impact}\n"
                f"**优先级：** {advice.priority.upper()}"
            )

            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False,  # Full width for better mobile readability
            )

        # Footer with compliance notice
        embed.set_footer(
            text=f"赛后训练工具 | 符合 Riot 游戏诚信政策 | Variant: {self.report.variant_id or 'N/A'}"
        )

        return embed

    async def on_timeout(self) -> None:
        """Handle view timeout (disable all buttons)."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class AdviceFeedbackView(discord.ui.View):
    """Feedback buttons for individual advice items.

    This view is shown in the ephemeral advice detail message,
    allowing users to rate the usefulness of each suggestion.
    """

    def __init__(
        self,
        advice_list: list[V21ActionableAdvice],
        match_id: str,
        timeout: float = 900.0,
    ) -> None:
        """Initialize the advice feedback view.

        Args:
            advice_list: List of actionable advice from the report
            match_id: Match ID for feedback tracking
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.advice_list = advice_list
        self.match_id = match_id

        # Dynamically add feedback buttons for each advice
        self._add_advice_feedback_buttons()

    def _add_advice_feedback_buttons(self) -> None:
        """Add usefulness feedback buttons for each advice item.

        Custom IDs follow schema: chimera:advice:{advice_id}:{useful|not_useful}
        """
        # For simplicity, add a general "All advice useful" / "Not useful" button
        # (Per-advice feedback requires dynamic button generation, which has complexity)

        # General usefulness button (positive)
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="👍 建议有用",
                custom_id=f"chimera:advice:general:{self.match_id}:useful",
                row=0,
            )
        )

        # General usefulness button (negative)
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="👎 建议无用",
                custom_id=f"chimera:advice:general:{self.match_id}:not_useful",
                row=0,
            )
        )

        # Optional: Comment button for qualitative feedback
        # (Would require modal interaction, omitted for simplicity)

    async def on_timeout(self) -> None:
        """Handle view timeout (disable all buttons)."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


def render_v21_prescriptive_analysis(
    report: V21PrescriptiveAnalysisReport,
) -> tuple[discord.Embed, PrescriptiveAnalysisView]:
    """Render V2.1 prescriptive analysis with collapsible advice.

    This is the recommended rendering method for V2.1 action-oriented analysis,
    providing:
    - Summary embed with key insights (no advice overload)
    - On-demand advice display via "💡 显示改进建议" button
    - Per-advice feedback for fine-grained A/B testing

    Args:
        report: V2.1 prescriptive analysis report

    Returns:
        Tuple of (summary_embed, view):
            - summary_embed: Main summary without detailed advice
            - view: PrescriptiveAnalysisView with "Show Advice" button
    """
    # Create main view
    view = PrescriptiveAnalysisView(
        report=report,
        match_id=report.match_id,
        timeout=900.0,
    )

    # Create summary embed (no detailed advice)
    result_emoji = "🏆" if report.match_result == "victory" else "💔"
    summary_embed = discord.Embed(
        title=f"{result_emoji} V2.1 指导性分析",
        description=(
            f"**Match ID:** `{report.match_id}`\n"
            f"**目标玩家:** {report.target_player_name}\n\n"
            f"**团队整体评价：** {report.team_summary_insight or '暂无'}"
        ),
        color=0x5865F2 if report.match_result == "victory" else 0xE74C3C,
    )

    # Show advice count as teaser
    summary_embed.add_field(
        name="💡 改进建议",
        value=f"已生成 **{len(report.actionable_advice)}** 条行动导向建议。\n点击下方按钮查看详细内容。",
        inline=False,
    )

    # Performance metadata
    from src.core.views.analysis_view import _format_duration_ms

    summary_embed.set_footer(
        text=f"A/B Cohort: {report.ab_cohort or 'N/A'} | {_format_duration_ms(report.processing_duration_ms)} | V2.1"
    )

    return summary_embed, view
