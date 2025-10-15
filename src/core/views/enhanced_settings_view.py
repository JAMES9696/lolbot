"""Enhanced Settings View with visual Select Menus and Buttons.

V2.2 UX Optimization: Replace text input modal with interactive
visual components (Select Menu + Buttons) for fool-proof settings configuration.

Architecture Pattern: Follows AccountManagerView approach (B+D solution)
- Main View: Settings overview with Select Menus
- Action Buttons: Save/Reset controls
- Real-time preview of changes before saving
"""

import logging
from typing import Any

import discord

from src.contracts.user_preferences import PreferenceUpdateRequest

logger = logging.getLogger(__name__)


class EnhancedSettingsView(discord.ui.View):
    """Interactive settings configuration view with visual components.

    Provides dropdown menus and buttons for fool-proof preference editing,
    eliminating the need for users to remember valid input values.

    Design Principles:
    - Visual feedback: Emojis and clear labels
    - Real-time preview: Show changes before saving
    - Validation-free: Only valid options available
    - Mobile-friendly: Tap-based instead of typing
    """

    def __init__(
        self,
        user_id: str,
        current_preferences: dict[str, Any] | None,
        db_adapter: Any,
        timeout: float = 300.0,
    ):
        """Initialize enhanced settings view.

        Args:
            user_id: Discord user ID
            current_preferences: Current user preferences (None if default)
            db_adapter: Database adapter for persistence
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.current_preferences = current_preferences or {}
        self.db_adapter = db_adapter

        # Pending changes (not yet saved)
        self.pending_changes: dict[str, Any] = {}

        # Build UI components
        self._add_role_select()
        self._add_tone_select()
        self._add_detail_select()
        self._add_timeline_toggle()
        self._add_action_buttons()

    def _add_role_select(self) -> None:
        """Add main role selection dropdown."""
        current_role = self.current_preferences.get("main_role", "fill")

        options = [
            discord.SelectOption(
                label="上路 (Top)",
                value="top",
                emoji="⚔️",
                description="坚韧的前排战士",
                default=(current_role == "top"),
            ),
            discord.SelectOption(
                label="打野 (Jungle)",
                value="jungle",
                emoji="🌲",
                description="游走支援的节奏大师",
                default=(current_role == "jungle"),
            ),
            discord.SelectOption(
                label="中路 (Mid)",
                value="mid",
                emoji="⚡",
                description="爆发伤害的法师刺客",
                default=(current_role == "mid"),
            ),
            discord.SelectOption(
                label="下路 (Bot/ADC)",
                value="bot",
                emoji="🎯",
                description="持续输出的核心射手",
                default=(current_role == "bot"),
            ),
            discord.SelectOption(
                label="辅助 (Support)",
                value="support",
                emoji="💚",
                description="保护队友的视野管家",
                default=(current_role == "support"),
            ),
            discord.SelectOption(
                label="补位 (Fill)",
                value="fill",
                emoji="🔀",
                description="灵活应对任何位置",
                default=(current_role == "fill"),
            ),
        ]

        select = discord.ui.Select(
            placeholder="📍 选择你的主要位置...",
            options=options,
            custom_id="role_select",
            min_values=1,
            max_values=1,
        )
        select.callback = self._role_selected
        self.add_item(select)

    def _add_tone_select(self) -> None:
        """Add analysis tone selection dropdown."""
        current_tone = self.current_preferences.get("analysis_tone", "balanced")

        options = [
            discord.SelectOption(
                label="竞争型 (Competitive)",
                value="competitive",
                emoji="🔥",
                description="数据驱动，追求最优",
                default=(current_tone == "competitive"),
            ),
            discord.SelectOption(
                label="休闲型 (Casual)",
                value="casual",
                emoji="😊",
                description="鼓励式，轻松氛围",
                default=(current_tone == "casual"),
            ),
            discord.SelectOption(
                label="平衡型 (Balanced)",
                value="balanced",
                emoji="⚖️",
                description="客观中立，混合风格",
                default=(current_tone == "balanced"),
            ),
        ]

        select = discord.ui.Select(
            placeholder="🎯 选择分析语气风格...",
            options=options,
            custom_id="tone_select",
            min_values=1,
            max_values=1,
        )
        select.callback = self._tone_selected
        self.add_item(select)

    def _add_detail_select(self) -> None:
        """Add advice detail level selection dropdown."""
        current_detail = self.current_preferences.get("advice_detail_level", "detailed")

        options = [
            discord.SelectOption(
                label="简洁 (Concise)",
                value="concise",
                emoji="📝",
                description="50-100字符，快速扫读",
                default=(current_detail == "concise"),
            ),
            discord.SelectOption(
                label="详细 (Detailed)",
                value="detailed",
                emoji="📚",
                description="200-400字符，深度分析",
                default=(current_detail == "detailed"),
            ),
        ]

        select = discord.ui.Select(
            placeholder="📊 选择建议详细程度...",
            options=options,
            custom_id="detail_select",
            min_values=1,
            max_values=1,
        )
        select.callback = self._detail_selected
        self.add_item(select)

    def _add_timeline_toggle(self) -> None:
        """Add timeline references toggle button."""
        current_timeline = self.current_preferences.get("show_timeline_references", True)

        # Create toggle button with current state
        button_style = (
            discord.ButtonStyle.success if current_timeline else discord.ButtonStyle.secondary
        )
        button_label = "⏱️ 时间轴引用: 开启" if current_timeline else "⏱️ 时间轴引用: 关闭"

        button = discord.ui.Button(
            label=button_label,
            style=button_style,
            custom_id="timeline_toggle",
        )
        button.callback = self._timeline_toggled
        self.add_item(button)

    def _add_action_buttons(self) -> None:
        """Add save and reset action buttons."""
        # Save button (green, enabled only when changes exist)
        save_button = discord.ui.Button(
            label="💾 保存设置",
            style=discord.ButtonStyle.success,
            custom_id="save_button",
            disabled=True,  # Initially disabled until changes made
            row=4,  # Separate row for action buttons
        )
        save_button.callback = self._save_settings
        self.add_item(save_button)

        # Reset button (red, revert pending changes)
        reset_button = discord.ui.Button(
            label="🔄 重置修改",
            style=discord.ButtonStyle.danger,
            custom_id="reset_button",
            disabled=True,
            row=4,
        )
        reset_button.callback = self._reset_changes
        self.add_item(reset_button)

    async def _role_selected(self, interaction: discord.Interaction) -> None:
        """Handle role selection from dropdown."""
        selected_role = interaction.data["values"][0]  # type: ignore[index]
        self.pending_changes["main_role"] = selected_role

        await self._update_preview(interaction)

    async def _tone_selected(self, interaction: discord.Interaction) -> None:
        """Handle tone selection from dropdown."""
        selected_tone = interaction.data["values"][0]  # type: ignore[index]
        self.pending_changes["analysis_tone"] = selected_tone

        await self._update_preview(interaction)

    async def _detail_selected(self, interaction: discord.Interaction) -> None:
        """Handle detail level selection from dropdown."""
        selected_detail = interaction.data["values"][0]  # type: ignore[index]
        self.pending_changes["advice_detail_level"] = selected_detail

        await self._update_preview(interaction)

    async def _timeline_toggled(self, interaction: discord.Interaction) -> None:
        """Handle timeline toggle button click."""
        current_value = self.pending_changes.get(
            "show_timeline_references",
            self.current_preferences.get("show_timeline_references", True),
        )

        # Toggle value
        new_value = not current_value
        self.pending_changes["show_timeline_references"] = new_value

        # Update button appearance
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == "timeline_toggle":
                item.style = (
                    discord.ButtonStyle.success if new_value else discord.ButtonStyle.secondary
                )
                item.label = f"⏱️ 时间轴引用: {'开启' if new_value else '关闭'}"

        await self._update_preview(interaction)

    async def _update_preview(self, interaction: discord.Interaction) -> None:
        """Update settings preview and enable action buttons.

        Args:
            interaction: Discord interaction to respond to
        """
        # Enable action buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in [
                "save_button",
                "reset_button",
            ]:
                item.disabled = False

        # Create updated preview embed
        embed = self._create_preview_embed()

        await interaction.response.edit_message(embed=embed, view=self)

    async def _save_settings(self, interaction: discord.Interaction) -> None:
        """Save pending changes to database.

        Args:
            interaction: Discord interaction to respond to
        """
        await interaction.response.defer(ephemeral=True)

        if not self.pending_changes:
            await interaction.followup.send("❌ 没有待保存的更改。", ephemeral=True)
            return

        try:
            # Create PreferenceUpdateRequest from pending changes
            update_request = PreferenceUpdateRequest(**self.pending_changes)

            # Persist to database
            success = await self.db_adapter.save_user_preferences(
                self.user_id, update_request.model_dump(exclude_none=True)
            )

            if success:
                # Update current preferences
                self.current_preferences.update(self.pending_changes)
                self.pending_changes.clear()

                # Rebuild UI components to reflect new values
                self.clear_items()
                self._add_role_select()
                self._add_tone_select()
                self._add_detail_select()
                self._add_timeline_toggle()
                self._add_action_buttons()

                # Disable action buttons since no pending changes
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id in [
                        "save_button",
                        "reset_button",
                    ]:
                        item.disabled = True

                # Create success embed
                success_embed = discord.Embed(
                    title="✅ 设置已保存",
                    description="您的个性化配置已成功更新！",
                    color=0x57F287,
                )

                # Show what was updated
                updated_fields = []
                if update_request.main_role is not None:
                    role_emoji = {
                        "top": "⚔️",
                        "jungle": "🌲",
                        "mid": "⚡",
                        "bot": "🎯",
                        "support": "💚",
                        "fill": "🔀",
                    }.get(update_request.main_role, "")
                    updated_fields.append(f"**主要位置:** {role_emoji} {update_request.main_role}")

                if update_request.analysis_tone is not None:
                    tone_display = {
                        "competitive": "🔥 竞争型",
                        "casual": "😊 休闲型",
                        "balanced": "⚖️ 平衡型",
                    }.get(update_request.analysis_tone, update_request.analysis_tone)
                    updated_fields.append(f"**分析语气:** {tone_display}")

                if update_request.advice_detail_level is not None:
                    detail_display = {
                        "concise": "📝 简洁",
                        "detailed": "📚 详细",
                    }.get(update_request.advice_detail_level, update_request.advice_detail_level)
                    updated_fields.append(f"**建议详细程度:** {detail_display}")

                if update_request.show_timeline_references is not None:
                    timeline_text = (
                        "✅ 显示" if update_request.show_timeline_references else "❌ 隐藏"
                    )
                    updated_fields.append(f"**时间轴引用:** {timeline_text}")

                if updated_fields:
                    success_embed.add_field(
                        name="已更新的设置",
                        value="\n".join(updated_fields),
                        inline=False,
                    )

                success_embed.set_footer(text="这些设置将在下次分析时生效")

                # Try to update original message to reflect saved state
                try:
                    saved_embed = self._create_settings_embed(show_pending=False)
                    # For ephemeral messages, we need to edit the original response
                    await interaction.edit_original_response(embed=saved_embed, view=self)
                except Exception as edit_error:
                    # If editing fails (e.g., message expired), just log it
                    logger.warning(f"Could not edit original message: {edit_error}")

                await interaction.followup.send(embed=success_embed, ephemeral=True)

            else:
                error_embed = discord.Embed(
                    title="❌ 保存设置失败",
                    description=(
                        "无法保存您的设置。可能的原因：\n\n"
                        "• 您还没有绑定 Riot 账号\n"
                        "• 数据库连接问题\n\n"
                        "**解决方法：**\n"
                        "1. 先使用 `/bind` 命令绑定您的游戏账号\n"
                        "2. 然后再次尝试修改设置"
                    ),
                    color=0xED4245,
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Failed to save settings for user {self.user_id}: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ 保存设置时发生错误：{type(e).__name__}\n请重试或联系管理员。",
                ephemeral=True,
            )

    async def _reset_changes(self, interaction: discord.Interaction) -> None:
        """Reset pending changes to current saved values.

        Args:
            interaction: Discord interaction to respond to
        """
        self.pending_changes.clear()

        # Disable action buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in [
                "save_button",
                "reset_button",
            ]:
                item.disabled = True

        # Reset dropdown default selections
        # (Discord doesn't support programmatic default updates in edit,
        # so we recreate the view)
        new_view = EnhancedSettingsView(
            user_id=self.user_id,
            current_preferences=self.current_preferences,
            db_adapter=self.db_adapter,
        )

        embed = new_view._create_settings_embed(show_pending=False)
        await interaction.response.edit_message(embed=embed, view=new_view)

    def _create_preview_embed(self) -> discord.Embed:
        """Create embed showing current + pending changes.

        Returns:
            Discord Embed with settings preview
        """
        return self._create_settings_embed(show_pending=True)

    def _create_settings_embed(self, show_pending: bool = False) -> discord.Embed:
        """Create settings display embed.

        Args:
            show_pending: Whether to show pending changes

        Returns:
            Discord Embed with formatted settings
        """
        # Merge current + pending for preview
        if show_pending and self.pending_changes:
            effective_settings = {**self.current_preferences, **self.pending_changes}
            title = "⚙️ 个性化设置（预览）"
            description = "以下是您的配置（包含未保存的更改）："
            color = 0xFEE75C  # Yellow for pending state
        else:
            effective_settings = self.current_preferences
            title = "⚙️ 个性化设置"
            description = "使用下方的选项调整您的偏好设置："
            color = 0x5865F2  # Discord blurple

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
        )

        # Role settings
        main_role = effective_settings.get("main_role", "fill")
        role_display = {
            "top": "⚔️ 上路 (Top)",
            "jungle": "🌲 打野 (Jungle)",
            "mid": "⚡ 中路 (Mid)",
            "bot": "🎯 下路 (Bot)",
            "support": "💚 辅助 (Support)",
            "fill": "🔀 补位 (Fill)",
        }.get(main_role, main_role)

        embed.add_field(
            name="📍 主要位置",
            value=role_display,
            inline=True,
        )

        # Tone settings
        analysis_tone = effective_settings.get("analysis_tone", "balanced")
        tone_display = {
            "competitive": "🔥 竞争型（数据驱动）",
            "casual": "😊 休闲型（鼓励式）",
            "balanced": "⚖️ 平衡型（混合）",
        }.get(analysis_tone, analysis_tone)

        embed.add_field(
            name="🎯 分析语气",
            value=tone_display,
            inline=True,
        )

        # Detail settings
        detail_level = effective_settings.get("advice_detail_level", "detailed")
        detail_display = {
            "concise": "📝 简洁（50-100字符）",
            "detailed": "📚 详细（200-400字符）",
        }.get(detail_level, detail_level)

        embed.add_field(
            name="📊 建议详细程度",
            value=detail_display,
            inline=True,
        )

        # Timeline settings
        show_timeline = effective_settings.get("show_timeline_references", True)
        timeline_text = "✅ 显示时间戳" if show_timeline else "❌ 隐藏时间戳"

        embed.add_field(
            name="⏱️ 时间轴引用",
            value=timeline_text,
            inline=True,
        )

        # Show pending changes indicator
        if show_pending and self.pending_changes:
            pending_list = ", ".join(
                [
                    {
                        "main_role": "位置",
                        "analysis_tone": "语气",
                        "advice_detail_level": "详细程度",
                        "show_timeline_references": "时间轴",
                    }[key]
                    for key in self.pending_changes
                ]
            )
            embed.set_footer(text=f'⚠️ 待保存的更改: {pending_list} | 点击"保存设置"以应用')
        else:
            embed.set_footer(text='使用下方的选项修改配置 | 修改后点击"保存设置"')

        return embed


async def create_enhanced_settings_view(
    user_id: str, db_adapter: Any
) -> tuple[discord.Embed, EnhancedSettingsView]:
    """Factory function to create enhanced settings view with current preferences.

    Args:
        user_id: Discord user ID
        db_adapter: Database adapter for fetching/saving preferences

    Returns:
        Tuple of (embed, view) ready to send to user
    """
    # Fetch current preferences
    current_preferences = await db_adapter.get_user_preferences(user_id)

    # Create view
    view = EnhancedSettingsView(
        user_id=user_id,
        current_preferences=current_preferences,
        db_adapter=db_adapter,
    )

    # Create initial embed
    embed = view._create_settings_embed(show_pending=False)

    return embed, view
