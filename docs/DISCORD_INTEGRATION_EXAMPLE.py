"""Complete Discord Frontend Integration Example

This example demonstrates how to integrate all components from the
DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md into your Discord bot.

Usage:
    # In your Discord bot's interaction handler:
    from docs.DISCORD_INTEGRATION_EXAMPLE import create_analysis_view, send_analysis_message

    # Create view with all enhancements
    view = create_analysis_view(report, match_id)

    # Send with dev validation
    await send_analysis_message(interaction, view)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from src.contracts.team_analysis import TeamAnalysisReport

logger = logging.getLogger(__name__)


def create_analysis_view(
    report: TeamAnalysisReport,
    match_id: str,
    *,
    timeout: float = 900.0,
) -> discord.ui.View:
    """Create enhanced PaginatedTeamAnalysisView with all features.

    Features:
    - Safe truncation with Markdown boundaries
    - Enhanced builds section (visuals + diff)
    - Voice playback button (if TTS available)
    - Dev-time validation (CHIMERA_DEV_VALIDATE_DISCORD=1)
    - Correlation ID tracking

    Args:
        report: Team analysis report
        match_id: Match ID for tracking
        timeout: View timeout in seconds

    Returns:
        Configured Discord UI View

    Example:
        >>> view = create_analysis_view(report, "NA1_123456")
        >>> await interaction.followup.send(embed=view.create_embed(), view=view)
    """
    from src.core.views.paginated_team_view import PaginatedTeamAnalysisView
    from src.core.views.voice_button_helper import add_voice_button_if_available

    # Create base view
    view = PaginatedTeamAnalysisView(
        report=report,
        match_id=match_id,
        timeout=timeout,
    )

    # Add voice button if TTS available
    add_voice_button_if_available(
        view,
        report=report,
        match_id=match_id,
        row=1,  # Row 1 for voice/arena controls
    )

    return view


async def send_analysis_message(
    interaction: discord.Interaction,
    view: discord.ui.View,
    *,
    ephemeral: bool = False,
) -> bool:
    """Send analysis message with dev-time validation.

    Args:
        interaction: Discord interaction to respond to
        view: Configured PaginatedTeamAnalysisView
        ephemeral: Whether response should be ephemeral

    Returns:
        True if sent successfully, False otherwise

    Example:
        >>> view = create_analysis_view(report, match_id)
        >>> success = await send_analysis_message(interaction, view)
    """
    from src.core.views.discord_dev_validator import dev_validate_embed

    # Create embed from view
    embed = view.create_embed()

    # Dev validation (fails fast if CHIMERA_DEV_STRICT=1)
    try:
        if not dev_validate_embed(embed):
            logger.error(
                "Embed validation failed (non-strict mode)",
                extra={"match_id": getattr(view, "match_id", "unknown")},
            )
            # Continue anyway in non-strict mode
    except ValueError as e:
        logger.error("Embed validation failed (strict mode)", extra={"error": str(e)})
        # Fail-fast: send error message to user
        await interaction.followup.send(
            "❌ 分析数据格式错误，请联系管理员（Embed validation failed）",
            ephemeral=True,
        )
        return False

    # Send to Discord
    try:
        await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=ephemeral,
        )
        return True
    except discord.HTTPException as e:
        logger.error(
            "Failed to send Discord message",
            extra={
                "error": str(e),
                "status": e.status,
                "code": e.code,
            },
        )
        return False


# ===== Voice Button Interaction Handler =====


async def handle_voice_button_click(
    interaction: discord.Interaction,
    match_id: str,
) -> None:
    """Handle voice playback button click.

    This should be registered in your bot's interaction handler:

    @bot.event
    async def on_interaction(interaction):
        if interaction.data.get("custom_id", "").startswith("chimera:voice:play:"):
            match_id = interaction.data["custom_id"].split(":")[-1]
            await handle_voice_button_click(interaction, match_id)

    Args:
        interaction: Discord button interaction
        match_id: Extracted from custom_id
    """
    from src.core.views.voice_button_helper import (
        extract_correlation_id,
        get_voice_button_payload,
    )
    import aiohttp
    import os

    # Defer response (voice playback may take time)
    await interaction.response.defer(ephemeral=True)

    # Fetch analysis result to get TTS URL and correlation_id
    # (Replace with your DB adapter)
    from src.adapters.database import DatabaseAdapter

    db = DatabaseAdapter()
    result = await db.get_analysis_result(match_id)

    if not result or "llm_metadata" not in result:
        await interaction.followup.send(
            "❌ 未找到该对局的分析结果",
            ephemeral=True,
        )
        return

    tts_url = result.get("llm_metadata", {}).get("tts_audio_url")
    if not tts_url:
        await interaction.followup.send(
            "❌ 该对局没有可用的语音播报",
            ephemeral=True,
        )
        return

    # Extract correlation_id
    correlation_id = extract_correlation_id(result)

    # Build payload
    payload = get_voice_button_payload(
        tts_audio_url=tts_url,
        guild_id=interaction.guild_id,
        user_id=interaction.user.id,  # Backend will infer voice channel
        correlation_id=correlation_id,
    )

    # Call backend /broadcast endpoint
    broadcast_url = os.getenv("BROADCAST_ENDPOINT", "http://localhost:8000/broadcast")
    auth_token = os.getenv("BROADCAST_WEBHOOK_SECRET", "")

    headers = {"X-Auth-Token": auth_token} if auth_token else {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                broadcast_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info(
                        "Voice broadcast triggered",
                        extra={
                            "match_id": match_id,
                            "correlation_id": correlation_id,
                            "user_id": interaction.user.id,
                        },
                    )
                    await interaction.followup.send(
                        "✅ 语音播报已发送到你的语音频道",
                        ephemeral=True,
                    )
                else:
                    error_text = await resp.text()
                    logger.error(
                        "Voice broadcast failed",
                        extra={
                            "status": resp.status,
                            "error": error_text,
                            "correlation_id": correlation_id,
                        },
                    )
                    await interaction.followup.send(
                        f"❌ 语音播报失败 ({resp.status})",
                        ephemeral=True,
                    )
    except Exception as e:
        logger.exception(
            "Exception during voice broadcast", extra={"match_id": match_id, "error": str(e)}
        )
        await interaction.followup.send(
            "❌ 语音播报请求异常，请稍后重试",
            ephemeral=True,
        )


# ===== Arena Section Select Handler =====


async def handle_arena_section_change(
    interaction: discord.Interaction,
    section_key: str,
) -> None:
    """Handle Arena section select menu change.

    This uses the CHIMERA_ARENA_SECTION_HANDLER env var to fetch new content.

    Args:
        interaction: Discord select menu interaction
        section_key: Selected section (e.g., "highlights", "trajectory")
    """
    # Implementation already exists in PaginatedTeamAnalysisView._handle_async_section
    # This is just a reference example

    logger.info(
        "Arena section changed",
        extra={
            "section_key": section_key,
            "user_id": interaction.user.id,
        },
    )

    # The actual logic is handled by the View's Select callback
    # See src/core/views/paginated_team_view.py:_ArenaSectionSelect


# ===== Complete Example: Bot Command =====


async def analyze_match_command(
    interaction: discord.Interaction,
    match_id: str,
) -> None:
    """Complete example: /analyze-match command.

    This demonstrates the full flow:
    1. Fetch analysis report from backend
    2. Create enhanced view with all features
    3. Send with dev validation
    4. Log correlation_id for tracking

    Args:
        interaction: Discord slash command interaction
        match_id: User-provided match ID
    """
    # Defer (analysis may take time)
    await interaction.response.defer()

    # Fetch from backend (replace with your API call)
    try:
        # Example: Call your backend API
        from src.tasks.team_tasks import run_team_analysis

        report = await run_team_analysis(match_id=match_id)

        if not report:
            await interaction.followup.send(
                "❌ 未找到该对局或分析失败",
                ephemeral=True,
            )
            return

    except Exception as e:
        logger.exception("Failed to analyze match", extra={"match_id": match_id, "error": str(e)})
        await interaction.followup.send(
            "❌ 分析失败，请稍后重试",
            ephemeral=True,
        )
        return

    # Create enhanced view
    view = create_analysis_view(report, match_id)

    # Extract correlation_id for logging
    from src.core.views.voice_button_helper import extract_correlation_id

    correlation_id = extract_correlation_id(report)

    logger.info(
        "Sending analysis to Discord",
        extra={
            "match_id": match_id,
            "correlation_id": correlation_id,
            "user_id": interaction.user.id,
            "guild_id": interaction.guild_id,
        },
    )

    # Send with validation
    success = await send_analysis_message(interaction, view, ephemeral=False)

    if success:
        logger.info(
            "Analysis sent successfully",
            extra={
                "match_id": match_id,
                "correlation_id": correlation_id,
            },
        )
