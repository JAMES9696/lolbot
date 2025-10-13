"""Port interfaces for hexagonal architecture.

These ports define the contracts between the core domain and external adapters.
All external dependencies must implement these interfaces.

P5 Unified: Merged core ports (from ports.py) and P3 ports into single package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from src.core.rso_port import RSOPort

# P3 ports from submodules
from src.core.ports.match_history_port import IMatchHistoryService
from src.core.ports.task_port import IAsyncTaskService

if TYPE_CHECKING:
    from src.contracts.analysis_results import AnalysisErrorReport, FinalAnalysisReport

__all__ = [
    # Core ports (originally from ports.py)
    "RiotAPIPort",
    "DatabasePort",
    "CachePort",
    "LLMPort",
    "TTSPort",
    "RSOPort",
    "DiscordWebhookPort",
    # P3 service ports
    "IAsyncTaskService",
    "IMatchHistoryService",
]


# ===== Core Ports (P0-P2) =====


class RiotAPIPort(ABC):
    """Port for Riot Games API operations."""

    @abstractmethod
    async def get_summoner_by_discord_id(self, discord_id: str) -> dict[str, Any] | None:
        """Get summoner data by Discord ID (requires prior binding)."""
        pass

    @abstractmethod
    async def get_match_timeline(self, match_id: str, region: str) -> dict[str, Any] | None:
        """Get detailed match timeline data from Match-V5 API."""
        pass

    @abstractmethod
    async def get_match_history(self, puuid: str, region: str, count: int = 20) -> list[str]:
        """Get recent match IDs for a summoner."""
        pass

    @abstractmethod
    async def get_match_details(self, match_id: str, region: str) -> dict[str, Any] | None:
        """Get match details from Match-V5 API."""
        pass


class DatabasePort(ABC):
    """Port for database operations."""

    @abstractmethod
    async def save_user_binding(self, discord_id: str, puuid: str, summoner_name: str) -> bool:
        """Save Discord ID to PUUID binding."""
        pass

    @abstractmethod
    async def get_user_binding(self, discord_id: str) -> dict[str, Any] | None:
        """Get user binding by Discord ID."""
        pass

    @abstractmethod
    async def list_user_bindings(self) -> list[dict[str, Any]]:
        """List all user bindings for downstream workflows."""
        pass

    @abstractmethod
    async def save_match_data(
        self, match_id: str, match_data: dict[str, Any], timeline_data: dict[str, Any]
    ) -> bool:
        """Save match and timeline data to database."""
        pass

    @abstractmethod
    async def get_analysis_result(self, match_id: str) -> dict[str, Any] | None:
        """Retrieve stored analysis record for match."""
        pass

    @abstractmethod
    async def get_match_data(self, match_id: str) -> dict[str, Any] | None:
        """Retrieve cached match data from database."""
        pass


class CachePort(ABC):
    """Port for caching operations."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass


class LLMPort(ABC):
    """Port for Large Language Model operations."""

    @abstractmethod
    async def analyze_match(self, match_data: dict[str, Any], system_prompt: str) -> str:
        """Analyze match data using LLM and return narrative analysis."""
        pass


class GuildResolverPort(ABC):
    """Resolve active guilds for a Discord user."""

    @abstractmethod
    async def get_user_guilds(self, user_id: int) -> list[int]:
        """Return guild IDs where the user is currently known."""
        pass


class VoiceBroadcastPort(ABC):
    """Trigger Discord voice playback for synthesized audio."""

    @abstractmethod
    async def broadcast_to_user(
        self, *, guild_id: int, user_id: int, match_id: str
    ) -> tuple[bool, str]:
        """Broadcast match narration to a user's current voice channel."""
        pass


class TTSPort(ABC):
    """Port for Text-to-Speech operations.

    P5 Update: TTS adapter now returns public URL instead of audio bytes,
    allowing Discord to fetch and play audio directly without file attachment handling.
    """

    @abstractmethod
    async def synthesize_speech_to_url(
        self,
        text: str,
        emotion: str | None = None,
        *,
        options: dict[str, Any] | None = None,
    ) -> str | None:
        """Convert text to speech and upload to CDN/S3.

        Args:
            text: Narrative text to convert to speech (max ~1900 chars)
            emotion: Optional emotion tag for voice modulation
                     ('激动', '遗憾', '嘲讽', '鼓励', '平淡')
            options: Optional synthesis parameters (speed/pitch/voice metadata)

        Returns:
            Public URL to the generated audio file (MP3/OGG format)
            Returns None if TTS synthesis fails (graceful degradation)

        Raises:
            TTSError: If TTS service is unavailable or request fails
        """
        pass


class DiscordWebhookPort(ABC):
    """Port for Discord webhook operations (async interaction followup).

    This port defines the contracts for sending asynchronous responses back to Discord
    after a deferred interaction. Used by background tasks to edit the original response
    with analysis results or error messages.

    P5 Update: Added new methods using FinalAnalysisReport/AnalysisErrorReport contracts.
    Legacy methods (send_match_analysis, send_error_message) kept for backward compatibility.
    P5.1 Update: Added channel_id parameter for fallback message sending.
    """

    # ===== New Contract-Based Methods (P5) =====

    @abstractmethod
    async def publish_match_analysis(
        self,
        application_id: str,
        interaction_token: str,
        analysis_report: FinalAnalysisReport,
        channel_id: str | None = None,
    ) -> bool:
        """Publish match analysis results using FinalAnalysisReport contract.

        Args:
            application_id: Discord application ID
            interaction_token: Interaction token (15min validity)
            analysis_report: Structured FinalAnalysisReport Pydantic object
            channel_id: Optional channel ID for fallback message sending

        Returns:
            True if webhook delivery succeeded

        Raises:
            DiscordWebhookError: If webhook delivery fails
        """
        pass

    @abstractmethod
    async def send_error_notification(
        self,
        application_id: str,
        interaction_token: str,
        error_report: AnalysisErrorReport,
        channel_id: str | None = None,
    ) -> bool:
        """Send error notification using AnalysisErrorReport contract.

        Args:
            application_id: Discord application ID
            interaction_token: Interaction token (15min validity)
            error_report: Structured AnalysisErrorReport Pydantic object
            channel_id: Optional channel ID for fallback message sending

        Returns:
            True if webhook delivery succeeded
        """
        pass

    # ===== Legacy Methods (Backward Compatibility) =====

    @abstractmethod
    async def send_match_analysis(
        self,
        application_id: str,
        interaction_token: str,
        match_id: str,
        narrative: str,
        score_data: dict[str, Any],
        emotion: str | None = None,
    ) -> bool:
        """[DEPRECATED] Send match analysis results to Discord via webhook.

        This method is deprecated. Use publish_match_analysis() with FinalAnalysisReport.

        Args:
            application_id: Discord application ID for webhook URL
            interaction_token: Interaction token (15min validity)
            match_id: Match ID for display
            narrative: LLM-generated narrative text
            score_data: Structured scoring data for embed
            emotion: Optional emotion tag for TTS

        Returns:
            True if webhook delivery succeeded, False otherwise
        """
        pass

    @abstractmethod
    async def send_error_message(
        self,
        application_id: str,
        interaction_token: str,
        error_type: str,
        user_friendly_message: str,
    ) -> bool:
        """[DEPRECATED] Send error notification to Discord via webhook.

        This method is deprecated. Use send_error_notification() with AnalysisErrorReport.

        Args:
            application_id: Discord application ID for webhook URL
            interaction_token: Interaction token (15min validity)
            error_type: Internal error classification (for logging)
            user_friendly_message: User-facing error description

        Returns:
            True if webhook delivery succeeded, False otherwise
        """
        pass
