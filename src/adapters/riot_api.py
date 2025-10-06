"""Riot Games API adapter implementation.

This module handles all interactions with the Riot API,
including rate limiting, error handling, and data transformation.
"""

import asyncio
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp
from pydantic import BaseModel, Field

from src.core.observability import trace_adapter

# HTTP Status Code Constants
HTTP_BAD_REQUEST = 400
HTTP_TOO_MANY_REQUESTS = 429

logger = logging.getLogger(__name__)


class RiotRegion(str, Enum):
    """Riot API regions."""

    AMERICAS = "americas"
    ASIA = "asia"
    EUROPE = "europe"
    SEA = "sea"

    # Game servers
    BR1 = "br1"
    EUN1 = "eun1"
    EUW1 = "euw1"
    JP1 = "jp1"
    KR = "kr"
    LA1 = "la1"
    LA2 = "la2"
    NA1 = "na1"
    OC1 = "oc1"
    PH2 = "ph2"
    RU = "ru"
    SG2 = "sg2"
    TH2 = "th2"
    TR1 = "tr1"
    TW2 = "tw2"
    VN2 = "vn2"


class MatchTimeline(BaseModel):
    """Simplified Match Timeline data model."""

    match_id: str = Field(description="Unique match identifier")
    game_duration: int = Field(description="Game duration in seconds")
    game_version: str = Field(description="Game patch version")
    participants: list[dict[str, Any]] = Field(default_factory=list)
    frames: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RiotAPIError(Exception):
    """Base exception for Riot API errors."""

    def __init__(self, message: str, status_code: int | None = None, headers: dict[str, str] | None = None) -> None:
        """Initialize Riot API error.

        Args:
            message: Error message
            status_code: HTTP status code
            headers: Response headers
        """
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


class RateLimitError(RiotAPIError):
    """Rate limit exceeded error."""

    def __init__(self, retry_after: int, message: str = "Rate limit exceeded") -> None:
        """Initialize rate limit error.

        Args:
            retry_after: Seconds to wait before retry
            message: Error message
        """
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class RiotAPIAdapter:
    """Adapter for Riot Games API interactions."""

    def __init__(self, api_key: str, region: RiotRegion = RiotRegion.NA1) -> None:
        """Initialize Riot API adapter.

        Args:
            api_key: Riot API key
            region: Default region for API calls
        """
        self.api_key = api_key
        self.region = region
        self.base_url = "https://{region}.api.riotgames.com"
        self.session: aiohttp.ClientSession | None = None

        # Rate limiting state
        self._rate_limit_reset: dict[str, float] = {}
        self._request_count: dict[str, int] = {}

    async def __aenter__(self) -> "RiotAPIAdapter":
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers={
                "X-Riot-Token": self.api_key,
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    @trace_adapter
    async def get_match_timeline(self, match_id: str, region: RiotRegion | None = None) -> MatchTimeline:
        """Fetch match timeline data from Riot API.

        This method implements:
        - Automatic rate limit handling with exponential backoff
        - 429 error recovery using Retry-After header
        - Data transformation to Pydantic model

        Args:
            match_id: Riot match ID (e.g., "NA1_4812345678")
            region: Optional region override

        Returns:
            MatchTimeline: Parsed and validated timeline data

        Raises:
            RiotAPIError: For API errors
            RateLimitError: When rate limited (with retry_after)
            ValueError: For invalid match ID format
        """
        # Validate match ID format
        if not match_id or "_" not in match_id:
            msg = f"Invalid match ID format: {match_id}"
            raise ValueError(msg)

        # Determine the correct regional endpoint
        region = region or self.region
        regional_url = self._get_regional_url(region)

        # Construct API endpoint
        endpoint = f"{regional_url}/lol/match/v5/matches/{match_id}/timeline"

        # Implement retry logic with exponential backoff
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                response = await self._make_request(endpoint)

                # Parse response into Pydantic model
                timeline_data = await response.json()
                info = timeline_data.get("info", {})
                frames = info.get("frames", []) or []
                frame_interval = info.get("frameInterval") or info.get("frame_interval")
                if isinstance(frame_interval, (int, float)) and frames:
                    game_duration = int((len(frames) * frame_interval) / 1000)
                else:
                    game_duration = info.get("gameLength") or 0

                # Transform to our domain model
                return MatchTimeline(
                    match_id=match_id,
                    game_duration=game_duration,
                    game_version=timeline_data.get("info", {}).get("gameVersion", "unknown"),
                    participants=timeline_data.get("info", {}).get("participants", []),
                    frames=timeline_data.get("info", {}).get("frames", []),
                    metadata=timeline_data.get("metadata", {}),
                )

            except RateLimitError as e:
                # Handle rate limiting with Retry-After header
                await asyncio.sleep(e.retry_after)
                continue

            except aiohttp.ClientError as e:
                # Retry on network errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                msg = f"Network error fetching match timeline: {e}"
                raise RiotAPIError(msg) from e

        msg = f"Failed to fetch match timeline after {max_retries} attempts"
        raise RiotAPIError(msg)

    @trace_adapter
    async def _make_request(self, url: str) -> aiohttp.ClientResponse:
        """Make HTTP request with rate limit handling.

        Args:
            url: Full URL to request

        Returns:
            aiohttp.ClientResponse: Response object

        Raises:
            RateLimitError: When rate limited
            RiotAPIError: For other API errors
        """
        if not self.session:
            msg = "Session not initialized. Use async context manager."
            raise RuntimeError(msg)

        async with self.session.get(url) as response:
            # Handle rate limiting (429)
            if response.status == HTTP_TOO_MANY_REQUESTS:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise RateLimitError(retry_after=retry_after)

            # Handle other errors
            if response.status >= HTTP_BAD_REQUEST:
                error_text = await response.text()
                msg = f"Riot API error {response.status}: {error_text}"
                raise RiotAPIError(msg, status_code=response.status, headers=dict(response.headers))

            return response

    def _get_regional_url(self, region: RiotRegion) -> str:
        """Get the correct regional URL for the API endpoint.

        Args:
            region: Region to use

        Returns:
            str: Regional base URL
        """
        # Map game servers to regional endpoints
        regional_mapping = {
            RiotRegion.BR1: RiotRegion.AMERICAS,
            RiotRegion.LA1: RiotRegion.AMERICAS,
            RiotRegion.LA2: RiotRegion.AMERICAS,
            RiotRegion.NA1: RiotRegion.AMERICAS,
            RiotRegion.EUN1: RiotRegion.EUROPE,
            RiotRegion.EUW1: RiotRegion.EUROPE,
            RiotRegion.RU: RiotRegion.EUROPE,
            RiotRegion.TR1: RiotRegion.EUROPE,
            RiotRegion.JP1: RiotRegion.ASIA,
            RiotRegion.KR: RiotRegion.ASIA,
            RiotRegion.OC1: RiotRegion.SEA,
            RiotRegion.PH2: RiotRegion.SEA,
            RiotRegion.SG2: RiotRegion.SEA,
            RiotRegion.TH2: RiotRegion.SEA,
            RiotRegion.TW2: RiotRegion.SEA,
            RiotRegion.VN2: RiotRegion.SEA,
        }

        # Use regional endpoint for match data
        regional = regional_mapping.get(region, region)
        return self.base_url.format(region=regional.value)


# Example usage demonstrating the decorator in action
async def example_usage() -> None:
    """Example of using the Riot API adapter with observability."""
    # This would normally come from environment variables
    api_key = "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # pragma: allowlist secret

    async with RiotAPIAdapter(api_key=api_key) as adapter:
        try:
            # This call will be fully traced by the decorator
            timeline = await adapter.get_match_timeline("NA1_4812345678")
            logger.info("Match duration: %d seconds", timeline.game_duration)
        except RateLimitError as e:
            logger.warning("Rate limited. Retry after %d seconds", e.retry_after)
        except RiotAPIError:
            logger.exception("API Error occurred")


if __name__ == "__main__":
    # For testing purposes only
    asyncio.run(example_usage())
