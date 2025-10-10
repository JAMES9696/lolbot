"""Helper for adding voice playback button with correlation_id tracking.

Implements voice button integration from DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from src.contracts.team_analysis import TeamAnalysisReport

logger = logging.getLogger(__name__)


def add_voice_button_if_available(
    view: discord.ui.View,
    *,
    report: TeamAnalysisReport | dict[str, Any],
    match_id: str,
    row: int = 1,
) -> bool:
    """Add voice playback button to view if TTS audio is available.

    Args:
        view: Discord UI View to add button to
        report: TeamAnalysisReport or dict payload with observability data
        match_id: Match ID for button custom_id
        row: Button row (default: 1)

    Returns:
        True if button was added, False otherwise

    Example:
        >>> view = PaginatedTeamAnalysisView(report, match_id)
        >>> add_voice_button_if_available(view, report=report, match_id=match_id)
    """
    # Extract TTS URL from report
    tts_url = None
    if isinstance(report, dict):
        tts_url = report.get("tts_audio_url")
    else:
        # Try from observability or other fields
        tts_url = getattr(report, "tts_audio_url", None)

    def _has_textual_source() -> bool:
        if isinstance(report, dict):
            candidates = (
                report.get("tts_summary"),
                report.get("summary_text"),
                report.get("ai_narrative_text"),
            )
        else:
            candidates = (
                getattr(report, "tts_summary", None),
                getattr(report, "summary_text", None),
                getattr(report, "ai_narrative_text", None),
            )
        return any(str(item).strip() for item in candidates if item)

    if not (tts_url or _has_textual_source()):
        logger.debug(
            "No TTS audio or textual source available, skipping voice button",
            extra={"match_id": match_id},
        )
        return False

    # Add voice button
    button = discord.ui.Button(
        style=discord.ButtonStyle.primary,
        label="▶ 播放语音",
        emoji="🔊",
        custom_id=f"chimera:voice:play:{match_id}",
        row=row,
    )
    view.add_item(button)

    logger.debug(
        "Voice button added",
        extra={
            "match_id": match_id,
            "tts_url": tts_url,
            "row": row,
            "uses_fallback": tts_url is None,
        },
    )
    return True


def get_voice_button_payload(
    *,
    tts_audio_url: str,
    guild_id: int,
    user_id: int | None = None,
    voice_channel_id: int | None = None,
    correlation_id: str,
) -> dict[str, Any]:
    """Build voice broadcast API payload aligned with backend contract.

    Based on DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md spec for POST /broadcast

    Args:
        tts_audio_url: TTS audio CDN URL
        guild_id: Discord guild ID
        user_id: User ID (backend will infer their voice channel)
        voice_channel_id: Explicit voice channel ID
        correlation_id: Format: "{session_id}:{execution_branch_id}"

    Returns:
        JSON payload dict for POST /broadcast

    Example:
        >>> payload = get_voice_button_payload(
        ...     tts_audio_url="https://cdn.example.com/audio.mp3",
        ...     guild_id=123,
        ...     user_id=456,
        ...     correlation_id="session-x:branch-y",
        ... )
    """
    payload: dict[str, Any] = {
        "audio_url": tts_audio_url,
        "guild_id": guild_id,
        "correlation_id": correlation_id,
    }

    # Add target (priority: voice_channel_id > user_id)
    if voice_channel_id:
        payload["voice_channel_id"] = voice_channel_id
    elif user_id:
        payload["user_id"] = user_id
    else:
        logger.warning(
            "No voice target specified (user_id or voice_channel_id)",
            extra={"correlation_id": correlation_id},
        )

    return payload


def extract_correlation_id(report: TeamAnalysisReport | dict[str, Any]) -> str:
    """Extract correlation_id from report observability data.

    Format: "{session_id}:{execution_branch_id}"

    Args:
        report: TeamAnalysisReport or dict payload

    Returns:
        Correlation ID string or "unknown:unknown" fallback

    Example:
        >>> corr_id = extract_correlation_id(report)
        >>> assert ":" in corr_id
    """
    # Try from observability field
    if isinstance(report, dict):
        obs = report.get("observability", {})
        session_id = obs.get("session_id", "unknown")
        branch_id = obs.get("execution_branch_id", "unknown")
    else:
        obs = getattr(report, "observability", None)
        if obs:
            session_id = getattr(obs, "session_id", "unknown")
            branch_id = getattr(obs, "execution_branch_id", "unknown")
        else:
            session_id = "unknown"
            branch_id = "unknown"

    return f"{session_id}:{branch_id}"
