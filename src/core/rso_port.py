"""RSO (Riot Sign-On) OAuth port for authentication."""

from abc import ABC, abstractmethod

from src.contracts.user_binding import RiotAccount


class RSOPort(ABC):
    """Port for Riot Sign-On OAuth operations."""

    @abstractmethod
    async def generate_auth_url(self, discord_id: str, region: str = "na1") -> tuple[str, str]:
        """Generate RSO authorization URL.

        Args:
            discord_id: Discord user ID to bind
            region: Preferred Riot region

        Returns:
            Tuple of (auth_url, state_token)
        """
        pass

    @abstractmethod
    async def exchange_code(self, code: str) -> RiotAccount | None:
        """Exchange authorization code for Riot account information.

        Args:
            code: OAuth authorization code from Riot

        Returns:
            RiotAccount if successful, None otherwise
        """
        pass

    @abstractmethod
    async def validate_state(self, state: str) -> str | None:
        """Validate state token and return associated Discord ID.

        Args:
            state: State token from OAuth callback

        Returns:
            Discord ID if valid, None otherwise
        """
        pass

    @abstractmethod
    async def store_state(self, state: str, discord_id: str, ttl: int = 600) -> bool:
        """Store state token for CSRF validation.

        Args:
            state: State token
            discord_id: Associated Discord ID
            ttl: Time to live in seconds (default 10 minutes)

        Returns:
            True if successful
        """
        pass
