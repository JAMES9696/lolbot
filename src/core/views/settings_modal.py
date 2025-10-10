"""Discord Modal for V2.2 User Preferences Configuration.

Implements an interactive form (Modal) for users to configure their
personalized analysis preferences, including role and tone settings.

Architecture:
- UserSettingsModal: Main modal form with input fields
- Settings submission handler integrated with discord_adapter

Design Principles:
- User-Friendly: Clear labels and placeholders for each field
- Validation: Discord-side validation for select fields
- Async Persistence: Non-blocking save to backend UserProfileService
"""

from typing import Any

import discord

from src.contracts.user_preferences import PreferenceUpdateRequest


class UserSettingsModal(discord.ui.Modal, title="⚙️ 个性化设置"):
    """Discord Modal for user preference configuration.

    This modal collects user preferences through a popup form,
    providing a better UX than slash command parameters for
    multiple configuration options.

    V2.2 Enhancement: Replaces command-based configuration with
    interactive form UI for improved mobile accessibility.
    """

    # Input field: Main Role
    main_role = discord.ui.TextInput(
        label="主要位置",
        placeholder="输入: top, jungle, mid, bot, support, 或 fill",
        required=False,
        max_length=10,
        style=discord.TextStyle.short,
    )

    # Input field: Analysis Tone
    analysis_tone = discord.ui.TextInput(
        label="分析语气",
        placeholder="输入: competitive（竞争型）, casual（休闲型）, 或 balanced（平衡型）",
        required=False,
        max_length=15,
        style=discord.TextStyle.short,
    )

    # Input field: Advice Detail Level
    advice_detail_level = discord.ui.TextInput(
        label="建议详细程度",
        placeholder="输入: concise（简洁）或 detailed（详细）",
        required=False,
        max_length=10,
        style=discord.TextStyle.short,
    )

    # Input field: Show Timeline References (Yes/No)
    show_timeline = discord.ui.TextInput(
        label="显示时间轴引用",
        placeholder="输入: yes（显示时间戳）或 no（隐藏时间戳）",
        required=False,
        max_length=3,
        style=discord.TextStyle.short,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission.

        This method is automatically called when user clicks "Submit".
        It validates input, constructs PreferenceUpdateRequest,
        and triggers backend persistence.
        """
        # Defer response quickly (<3s rule)
        await interaction.response.defer(ephemeral=True)

        # Parse and validate inputs
        update_request = self._parse_inputs()

        # Validate parsed request
        validation_error = self._validate_inputs(update_request)
        if validation_error:
            error_embed = discord.Embed(
                title="❌ 配置错误",
                description=validation_error,
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        # Store validated update request for external handler
        # (discord_adapter will retrieve this and call backend)
        self.update_request = update_request
        self.interaction = interaction

    def _parse_inputs(self) -> PreferenceUpdateRequest:
        """Parse modal inputs into PreferenceUpdateRequest.

        Returns:
            PreferenceUpdateRequest with non-empty fields populated
        """
        request_data = {}

        # Main role
        if self.main_role.value and self.main_role.value.strip():
            role_value = self.main_role.value.strip().lower()
            if role_value in ["top", "jungle", "mid", "bot", "support", "fill"]:
                request_data["main_role"] = role_value

        # Analysis tone
        if self.analysis_tone.value and self.analysis_tone.value.strip():
            tone_value = self.analysis_tone.value.strip().lower()
            if tone_value in ["competitive", "casual", "balanced"]:
                request_data["analysis_tone"] = tone_value

        # Advice detail level
        if self.advice_detail_level.value and self.advice_detail_level.value.strip():
            detail_value = self.advice_detail_level.value.strip().lower()
            if detail_value in ["concise", "detailed"]:
                request_data["advice_detail_level"] = detail_value

        # Show timeline references
        if self.show_timeline.value and self.show_timeline.value.strip():
            timeline_value = self.show_timeline.value.strip().lower()
            if timeline_value in ["yes", "y", "是", "true", "1"]:
                request_data["show_timeline_references"] = True
            elif timeline_value in ["no", "n", "否", "false", "0"]:
                request_data["show_timeline_references"] = False

        return PreferenceUpdateRequest(**request_data)

    def _validate_inputs(self, request: PreferenceUpdateRequest) -> str | None:
        """Validate parsed inputs for business logic errors.

        Args:
            request: Parsed preference update request

        Returns:
            Error message if validation fails, None if valid
        """
        # Check if at least one field is provided
        provided_fields = [
            request.main_role,
            request.analysis_tone,
            request.advice_detail_level,
            request.show_timeline_references,
        ]

        if not any(field is not None for field in provided_fields):
            return "请至少填写一个配置项。\n" "留空的字段将保持原有设置不变。"

        # All validations passed
        return None

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal submission errors.

        Args:
            interaction: Discord interaction object
            error: Exception that occurred during submission
        """
        error_embed = discord.Embed(
            title="❌ 提交失败",
            description=f"配置提交时发生错误：{type(error).__name__}\n请重试或联系管理员。",
            color=0xE74C3C,
        )

        try:
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=error_embed, ephemeral=True)


def create_current_settings_embed(
    preferences: dict[str, Any] | None,
) -> discord.Embed:
    """Create an embed showing user's current settings.

    Args:
        preferences: User's current preferences (None if not set)

    Returns:
        Discord Embed with formatted settings display
    """
    if preferences is None:
        embed = discord.Embed(
            title="⚙️ 您的当前设置",
            description="您尚未配置个性化偏好。使用默认设置。",
            color=0x5865F2,
        )
        embed.add_field(
            name="默认配置",
            value=(
                "**主要位置:** 未设置（显示所有位置）\n"
                "**分析语气:** balanced（平衡型）\n"
                "**建议详细程度:** balanced（平衡型）\n"
                "**时间轴引用:** 显示"
            ),
            inline=False,
        )
    else:
        embed = discord.Embed(
            title="⚙️ 您的当前设置",
            description="以下是您的个性化配置：",
            color=0x5865F2,
        )

        # Role settings
        main_role = preferences.get("main_role", "未设置")
        secondary_role = preferences.get("secondary_role", "未设置")
        embed.add_field(
            name="📍 位置偏好",
            value=f"**主要:** {main_role}\n**次要:** {secondary_role}",
            inline=True,
        )

        # Tone settings
        analysis_tone = preferences.get("analysis_tone", "balanced")
        tone_display = {
            "competitive": "竞争型（数据驱动）",
            "casual": "休闲型（鼓励式）",
            "balanced": "平衡型（混合）",
        }.get(analysis_tone, analysis_tone)

        embed.add_field(
            name="🎯 分析风格",
            value=f"**语气:** {tone_display}",
            inline=True,
        )

        # Detail settings
        detail_level = preferences.get("advice_detail_level", "balanced")
        show_timeline = preferences.get("show_timeline_references", True)

        detail_display = {
            "concise": "简洁（50-100字符）",
            "detailed": "详细（200-400字符）",
        }.get(detail_level, detail_level)

        embed.add_field(
            name="📝 建议呈现",
            value=(
                f"**详细程度:** {detail_display}\n"
                f"**时间轴引用:** {'显示' if show_timeline else '隐藏'}"
            ),
            inline=False,
        )

    embed.set_footer(text="使用 /settings 命令修改配置")
    return embed
