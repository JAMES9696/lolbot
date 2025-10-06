"""
Summoner and account-related data contracts.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from .common import BaseContract, Division, Tier


class SummonerProfile(BaseContract):
    """Summoner profile information from Riot API."""

    account_id: str = Field(..., description="Encrypted account ID")
    profile_icon_id: int = Field(..., description="Profile icon ID")
    revision_date: int = Field(
        ..., description="Date summoner was last modified (epoch milliseconds)"
    )
    id: str = Field(..., description="Encrypted summoner ID")
    puuid: str = Field(..., description="Encrypted PUUID")
    summoner_level: int = Field(..., ge=1, description="Summoner level")
    name: str = Field(..., description="Summoner name")
    tag_line: str = Field(..., description="Tag line (e.g., #NA1)")

    @property
    def game_name(self) -> str:
        """Get full game name with tagline."""
        return f"{self.name}#{self.tag_line}"

    @property
    def last_modified(self) -> datetime:
        """Convert revision date to datetime."""
        return datetime.fromtimestamp(self.revision_date / 1000)


class Account(BaseContract):
    """Riot account information."""

    puuid: str = Field(..., description="Player's PUUID")
    game_name: str = Field(..., description="Game name")
    tag_line: str = Field(..., description="Tag line")


class LeagueEntry(BaseContract):
    """League/Ranked information for a summoner."""

    league_id: str | None = Field(None, description="League ID")
    summoner_id: str = Field(..., description="Encrypted summoner ID")
    summoner_name: str = Field(..., description="Summoner name")
    queue_type: str = Field(..., description="Queue type (e.g., RANKED_SOLO_5x5)")
    tier: Tier | None = Field(None, description="Tier (IRON to CHALLENGER)")
    rank: Division | None = Field(None, description="Division within tier")
    league_points: int = Field(0, description="League points")
    wins: int = Field(0, description="Number of wins")
    losses: int = Field(0, description="Number of losses")
    hot_streak: bool = Field(False, description="Is on hot streak")
    veteran: bool = Field(False, description="Is a veteran in this tier")
    fresh_blood: bool = Field(False, description="Is new to this tier")
    inactive: bool = Field(False, description="Is inactive")
    mini_series: dict[str, Any] | None = Field(None, description="Promotion series info")

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        total_games = self.wins + self.losses
        if total_games == 0:
            return 0.0
        return (self.wins / total_games) * 100

    @property
    def full_rank(self) -> str:
        """Get full rank string (e.g., 'Gold II')."""
        if not self.tier:
            return "Unranked"
        if self.tier in [Tier.MASTER, Tier.GRANDMASTER, Tier.CHALLENGER]:
            return self.tier
        return f"{self.tier} {self.rank}" if self.rank else self.tier


class MasteryInfo(BaseContract):
    """Champion mastery information."""

    puuid: str = Field(..., description="Player's PUUID")
    champion_id: int = Field(..., description="Champion ID")
    champion_level: int = Field(..., ge=1, le=7, description="Mastery level (1-7)")
    champion_points: int = Field(..., ge=0, description="Total mastery points")
    last_play_time: int = Field(..., description="Last play time in epoch milliseconds")
    champion_points_since_last_level: int = Field(..., ge=0)
    champion_points_until_next_level: int = Field(..., ge=0)
    chest_granted: bool = Field(False, description="Has chest been granted")
    tokens_earned: int = Field(0, ge=0, le=3, description="Mastery tokens earned")
    marks_of_mastery: int = Field(0, ge=0, description="Marks of mastery earned")
    next_season_milestone: dict[str, Any] | None = Field(
        None, description="Next season milestone info"
    )

    @property
    def last_played(self) -> datetime:
        """Convert last play time to datetime."""
        return datetime.fromtimestamp(self.last_play_time / 1000)


class ChallengeInfo(BaseContract):
    """Player challenge/achievement information."""

    challenge_id: int = Field(..., description="Challenge ID")
    percentile: float | None = Field(None, ge=0, le=100, description="Percentile ranking")
    level: str | None = Field(None, description="Challenge level achieved")
    value: int | None = Field(None, description="Challenge value/score")
    achieved_time: int | None = Field(None, description="Achievement timestamp")

    @property
    def achieved_date(self) -> datetime | None:
        """Convert achieved time to datetime."""
        if self.achieved_time:
            return datetime.fromtimestamp(self.achieved_time / 1000)
        return None


class PlayerInfo(BaseContract):
    """Complete player information aggregating multiple API endpoints."""

    # Account data
    puuid: str = Field(..., description="Player's PUUID")
    game_name: str = Field(..., description="Game name")
    tag_line: str = Field(..., description="Tag line")

    # Summoner data
    summoner_id: str = Field(..., description="Encrypted summoner ID")
    account_id: str = Field(..., description="Encrypted account ID")
    profile_icon_id: int = Field(..., description="Profile icon ID")
    summoner_level: int = Field(..., ge=1, description="Summoner level")

    # Ranked data
    league_entries: list[LeagueEntry] = Field(default_factory=list, description="Ranked queue info")

    # Mastery data
    top_masteries: list[MasteryInfo] = Field(
        default_factory=list, description="Top champion masteries"
    )
    total_mastery_score: int | None = Field(None, ge=0, description="Total mastery score")

    # Discord binding (for our bot)
    discord_id: str | None = Field(None, description="Discord user ID if bound")
    discord_username: str | None = Field(None, description="Discord username")

    @property
    def display_name(self) -> str:
        """Get display name with tag."""
        return f"{self.game_name}#{self.tag_line}"

    @property
    def solo_queue_rank(self) -> LeagueEntry | None:
        """Get solo queue rank info."""
        for entry in self.league_entries:
            if entry.queue_type == "RANKED_SOLO_5x5":
                return entry
        return None

    @property
    def flex_queue_rank(self) -> LeagueEntry | None:
        """Get flex queue rank info."""
        for entry in self.league_entries:
            if entry.queue_type == "RANKED_FLEX_SR":
                return entry
        return None
