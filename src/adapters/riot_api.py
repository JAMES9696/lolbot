"""Riot API adapter using Cassiopeia library.

This adapter handles all Riot API interactions with automatic rate limiting,
caching, and error handling. Cassiopeia provides built-in rate limiting that
respects Retry-After headers to prevent API key suspension.
"""

import asyncio
import logging
from typing import Any
from collections.abc import AsyncIterator

import cassiopeia as cass
from cassiopeia import Match, Summoner

from src.config import settings


class RiotAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimitError(RiotAPIError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded", status_code=429, retry_after=retry_after)
from src.contracts import SummonerDTO
from src.core.ports import RiotAPIPort

logger = logging.getLogger(__name__)


class RiotAPIAdapter(RiotAPIPort):
    """Riot API adapter implementation using Cassiopeia.

    Cassiopeia provides:
    - Automatic rate limiting with Retry-After header respect
    - Built-in caching to reduce API calls
    - Automatic retries on transient failures
    - Lazy loading of data
    """

    def __init__(self) -> None:
        """Initialize Cassiopeia with production-ready configuration."""
        # Configure Cassiopeia settings
        cass_settings = {
            "api_key": settings.riot_api_key,
            "default_region": "NA",
            "rate_limiter": {
                "type": "application",
                "limiting_share": 1.0,  # Use 100% of rate limit
                "include_429s": False,  # Don't count 429s against rate limit
            },
            "cache": {
                "type": "lru",
                "expiration_time": {
                    "summoner": 3600,  # 1 hour
                    "match": 86400,  # 24 hours
                    "match_timeline": 86400,  # 24 hours
                },
            },
        }

        # Apply settings to Cassiopeia
        cass.apply_settings(cass_settings)
        logger.info("Riot API adapter initialized with Cassiopeia")

    async def get_summoner_by_discord_id(
        self, discord_id: str
    ) -> dict[str, Any] | None:
        """Get summoner data by Discord ID.

        This requires a prior binding in our database.
        The actual implementation would query the database first.
        """
        # This is a stub - actual implementation would query database
        # for the PUUID associated with this Discord ID
        logger.warning(
            f"get_summoner_by_discord_id not fully implemented for {discord_id}"
        )
        return None

    async def get_summoner_by_puuid(
        self, puuid: str, region: str = "NA"
    ) -> SummonerDTO | None:
        """Get summoner data by PUUID.

        Args:
            puuid: Player Universally Unique Identifier
            region: Riot region (default: NA)

        Returns:
            SummonerDTO if found, None otherwise
        """
        try:
            # Convert to Cassiopeia region format
            cass_region = self._convert_region(region)

            # Cassiopeia handles rate limiting automatically
            summoner = await asyncio.to_thread(
                Summoner, puuid=puuid, region=cass_region
            )

            # Load the summoner data (lazy loading)
            await asyncio.to_thread(summoner.load)

            # Convert to our Pydantic model
            return SummonerDTO(
                accountId=summoner.account_id,
                profileIconId=summoner.profile_icon.id,
                revisionDate=int(summoner.revision_date.timestamp()),
                id=summoner.id,
                puuid=summoner.puuid,
                summonerLevel=summoner.level,
                name=summoner.name,
            )

        except Exception as e:
            logger.error(f"Error fetching summoner for PUUID {puuid}: {e}")
            return None

    async def get_match_timeline(
        self, match_id: str, region: str
    ) -> dict[str, Any] | None:
        """Get detailed match timeline data.

        Cassiopeia automatically handles:
        - Rate limiting with exponential backoff
        - 429 errors with Retry-After header respect
        - Caching to reduce duplicate API calls

        Args:
            match_id: Match ID to fetch timeline for
            region: Riot region

        Returns:
            Timeline data as dictionary if successful, None otherwise
        """
        try:
            cass_region = self._convert_region(region)

            # Get the match first
            match = await asyncio.to_thread(Match, id=match_id, region=cass_region)

            # Get timeline (Cassiopeia handles rate limiting)
            timeline = await asyncio.to_thread(match.timeline)

            if timeline is None:
                logger.warning(f"No timeline data available for match {match_id}")
                return None

            # Convert to dictionary for our contracts
            # Note: Cassiopeia objects are complex, we need to extract the data
            timeline_data = self._extract_timeline_data(timeline)

            return timeline_data

        except cass.datastores.riotapi.common.APIError as e:
            if e.code == 429:
                retry_after = getattr(e, "retry_after", None) or 60
                raise RateLimitError(retry_after)
            elif e.code == 403:
                raise RiotAPIError("Forbidden: Check API key permissions", status_code=403)
            else:
                raise RiotAPIError(f"API error fetching timeline for {match_id}: {e}", status_code=e.code)
        except Exception as e:
            raise RiotAPIError(f"Unexpected error fetching timeline for {match_id}: {e}")

    async def get_match_history(
        self, puuid: str, region: str, count: int = 20
    ) -> list[str]:
        """Get recent match IDs for a summoner.

        Args:
            puuid: Player Universally Unique Identifier
            region: Riot region
            count: Number of matches to fetch (default: 20)

        Returns:
            List of match IDs
        """
        try:
            cass_region = self._convert_region(region)

            # Get summoner
            summoner = await asyncio.to_thread(
                Summoner, puuid=puuid, region=cass_region
            )

            # Get match history (Cassiopeia handles pagination)
            match_history: Any = (
                await asyncio.to_thread(  # MatchHistory (untyped library)
                    summoner.match_history
                )
            )

            # Extract match IDs
            match_ids = []
            async for match in self._async_match_generator(match_history, count):
                match_ids.append(match.id)

            logger.info(f"Fetched {len(match_ids)} match IDs for {puuid}")
            return match_ids

        except Exception as e:
            logger.error(f"Error fetching match history for {puuid}: {e}")
            return []

    async def get_match_details(
        self, match_id: str, region: str
    ) -> dict[str, Any] | None:
        """Get match details from Match-V5 API.

        Args:
            match_id: Match ID to fetch
            region: Riot region

        Returns:
            Match data as dictionary if successful, None otherwise
        """
        try:
            cass_region = self._convert_region(region)

            # Get match (Cassiopeia handles rate limiting)
            match = await asyncio.to_thread(Match, id=match_id, region=cass_region)

            # Load match data
            await asyncio.to_thread(match.load)

            # Extract match data
            match_data = self._extract_match_data(match)

            return match_data

        except cass.datastores.riotapi.common.APIError as e:
            if e.code == 429:
                retry_after = getattr(e, "retry_after", None) or 60
                raise RateLimitError(retry_after)
            elif e.code == 403:
                raise RiotAPIError("Forbidden: Check API key permissions", status_code=403)
            else:
                raise RiotAPIError(f"API error fetching match {match_id}: {e}", status_code=e.code)
        except Exception as e:
            raise RiotAPIError(f"Unexpected error fetching match {match_id}: {e}")

    def _convert_region(self, region: str) -> str:
        """Convert region string to Cassiopeia format.

        Args:
            region: Region in our format (e.g., "na1", "euw1")

        Returns:
            Region in Cassiopeia format (e.g., "NA", "EUW")
        """
        region_mapping = {
            "na1": "NA",
            "euw1": "EUW",
            "eune1": "EUNE",
            "kr": "KR",
            "br1": "BR",
            "la1": "LAN",
            "la2": "LAS",
            "oce1": "OCE",
            "ru": "RU",
            "tr1": "TR",
            "jp1": "JP",
        }
        return region_mapping.get(region.lower(), "NA")

    def _extract_timeline_data(
        self, timeline: Any
    ) -> dict[str, Any]:  # Timeline (untyped library)
        """Extract timeline data from Cassiopeia Timeline object.

        Args:
            timeline: Cassiopeia Timeline object

        Returns:
            Dictionary with timeline data
        """
        # This is a simplified extraction - full implementation would
        # convert all Timeline properties to match our MatchTimelineDTO
        timeline_data = {
            "metadata": {
                "dataVersion": "2",
                "matchId": timeline.match.id,
                "participants": [p.puuid for p in timeline.match.participants],
            },
            "info": {
                "frameInterval": timeline.frame_interval,
                "frames": [],
                "gameId": timeline.match.id,
                "participants": [],
            },
        }

        # Extract frames
        for frame in timeline.frames:
            frame_data = {
                "timestamp": frame.timestamp,
                "events": [],
                "participantFrames": {},
            }

            # Extract events
            for event in frame.events:
                event_data = {
                    "timestamp": event.timestamp,
                    "type": event.type,
                }
                # Add more event fields based on event type
                if hasattr(event, "participant_id"):
                    event_data["participantId"] = event.participant_id
                if hasattr(event, "position"):
                    event_data["position"] = {
                        "x": event.position.x,
                        "y": event.position.y,
                    }

                frame_data["events"].append(event_data)

            timeline_data["info"]["frames"].append(frame_data)

        return timeline_data

    def _extract_match_data(
        self, match: Any
    ) -> dict[str, Any]:  # Match (untyped library)
        """Extract match data from Cassiopeia Match object.

        Args:
            match: Cassiopeia Match object

        Returns:
            Dictionary with match data
        """
        # Extract basic match info
        match_data = {
            "metadata": {
                "dataVersion": "2",
                "matchId": match.id,
                "participants": [p.summoner.puuid for p in match.participants],
            },
            "info": {
                "gameId": match.id,
                "gameCreation": int(match.creation.timestamp() * 1000),
                "gameDuration": match.duration.seconds,
                "gameStartTimestamp": int(match.start.timestamp() * 1000),
                "gameEndTimestamp": int(
                    (match.start.timestamp() + match.duration.seconds) * 1000
                ),
                "gameMode": match.mode.value,
                "gameName": match.name if hasattr(match, "name") else "",
                "gameType": match.type.value,
                "gameVersion": match.version,
                "mapId": match.map.id,
                "platformId": match.platform.value,
                "queueId": match.queue.id if match.queue else 0,
                "participants": [],
                "teams": [],
            },
        }

        # Extract participant data
        for participant in match.participants:
            participant_data = {
                "puuid": participant.summoner.puuid,
                "summonerId": participant.summoner.id,
                "summonerName": participant.summoner.name,
                "teamId": participant.team.side.value,
                "participantId": participant.id,
                "championId": participant.champion.id,
                "championName": participant.champion.name,
                "kills": participant.stats.kills,
                "deaths": participant.stats.deaths,
                "assists": participant.stats.assists,
                "goldEarned": participant.stats.gold_earned,
                "totalDamageDealt": participant.stats.total_damage_dealt,
                "visionScore": participant.stats.vision_score,
                "win": participant.stats.win,
                # Add more fields as needed
            }
            match_data["info"]["participants"].append(participant_data)

        return match_data

    async def _async_match_generator(
        self,
        match_history: Any,
        limit: int,  # Cassiopeia MatchHistory (untyped)
    ) -> AsyncIterator[Any]:  # Cassiopeia Match (untyped)
        """Async generator for match history.

        Args:
            match_history: Cassiopeia MatchHistory object
            limit: Maximum number of matches to yield

        Yields:
            Match objects
        """
        count = 0
        for match in match_history:
            if count >= limit:
                break
            yield match
            count += 1
            # Small delay to be nice to the API
            await asyncio.sleep(0.1)
