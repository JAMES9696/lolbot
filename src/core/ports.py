"""Port interfaces for hexagonal architecture.

These ports define the contracts between the core domain and external adapters.
All external dependencies must implement these interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any


class RiotAPIPort(ABC):
    """Port for Riot Games API operations."""

    @abstractmethod
    async def get_summoner_by_discord_id(
        self, discord_id: str
    ) -> dict[str, Any] | None:
        """Get summoner data by Discord ID (requires prior binding)."""
        pass

    @abstractmethod
    async def get_match_timeline(
        self, match_id: str, region: str
    ) -> dict[str, Any] | None:
        """Get detailed match timeline data from Match-V5 API."""
        pass

    @abstractmethod
    async def get_match_history(
        self, puuid: str, region: str, count: int = 20
    ) -> list[str]:
        """Get recent match IDs for a summoner."""
        pass

    @abstractmethod
    async def get_match_details(
        self, match_id: str, region: str
    ) -> dict[str, Any] | None:
        """Get match details from Match-V5 API."""
        pass


class DatabasePort(ABC):
    """Port for database operations."""

    @abstractmethod
    async def save_user_binding(
        self, discord_id: str, puuid: str, summoner_name: str
    ) -> bool:
        """Save Discord ID to PUUID binding."""
        pass

    @abstractmethod
    async def get_user_binding(self, discord_id: str) -> dict[str, Any] | None:
        """Get user binding by Discord ID."""
        pass

    @abstractmethod
    async def save_match_data(
        self, match_id: str, match_data: dict[str, Any], timeline_data: dict[str, Any]
    ) -> bool:
        """Save match and timeline data to database."""
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
    async def analyze_match(
        self, match_data: dict[str, Any], system_prompt: str
    ) -> str:
        """Analyze match data using LLM and return narrative analysis."""
        pass


class TTSPort(ABC):
    """Port for Text-to-Speech operations."""

    @abstractmethod
    async def synthesize_speech(self, text: str, emotion: str | None = None) -> bytes:
        """Convert text to speech with optional emotion."""
        pass
