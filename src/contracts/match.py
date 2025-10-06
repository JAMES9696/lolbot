"""
Match information data contracts for Riot API Match-V5.
"""

from datetime import datetime
from typing import Any, Dict, List

from pydantic import Field, computed_field

from .common import BaseContract, Platform, Queue


class Ban(BaseContract):
    """Champion ban information."""

    champion_id: int = Field(..., description="Champion ID that was banned")
    pick_turn: int = Field(..., description="Turn during which the champion was banned")


class Team(BaseContract):
    """Team information in a match."""

    team_id: int = Field(..., description="100 (blue) or 200 (red)")
    win: bool = Field(..., description="Whether this team won")
    bans: List[Ban] = Field(default_factory=list, description="Champion bans")

    # Objectives
    baron_kills: int = Field(0, ge=0)
    champion_kills: int = Field(0, ge=0)
    dragon_kills: int = Field(0, ge=0)
    inhibitor_kills: int = Field(0, ge=0)
    rift_herald_kills: int = Field(0, ge=0)
    tower_kills: int = Field(0, ge=0)

    # First objectives
    first_baron: bool = Field(False)
    first_blood: bool = Field(False)
    first_dragon: bool = Field(False)
    first_inhibitor: bool = Field(False)
    first_rift_herald: bool = Field(False)
    first_tower: bool = Field(False)

    # Additional objectives
    horce_kills: int | None = Field(None, ge=0, description="Voidgrub kills")


class Perks(BaseContract):
    """Rune/Perk information for a participant."""

    stat_perks: Dict[str, Any] = Field(..., description="Stat shards")
    styles: List[Dict[str, Any]] = Field(..., description="Primary and secondary rune trees")


class Challenges(BaseContract):
    """Challenge/achievement stats for a participant."""

    assists_per_minute: float | None = Field(None, ge=0)
    baron_takedowns: int | None = Field(None, ge=0)
    control_ward_time_coverage: float | None = Field(None, ge=0, le=100)
    damage_per_minute: float | None = Field(None, ge=0)
    damage_taken_on_team_percentage: float | None = Field(None, ge=0, le=100)
    dragon_takedowns: int | None = Field(None, ge=0)
    effective_heal_and_shielding: float | None = Field(None, ge=0)
    elite_monster_takedowns: int | None = Field(None, ge=0)
    gold_per_minute: float | None = Field(None, ge=0)
    kill_participation: float | None = Field(None, ge=0, le=100)
    kda: float | None = Field(None, ge=0)
    skill_shots_dodged: int | None = Field(None, ge=0)
    solo_kills: int | None = Field(None, ge=0)
    team_damage_percentage: float | None = Field(None, ge=0, le=100)
    turret_plate_takedowns: int | None = Field(None, ge=0)
    turret_takedowns: int | None = Field(None, ge=0)
    vision_score_per_minute: float | None = Field(None, ge=0)


class Participant(BaseContract):
    """Participant (player) information in a match."""

    # Identity
    puuid: str = Field(..., description="Player's PUUID")
    summoner_id: str = Field(..., description="Encrypted summoner ID")
    summoner_name: str = Field(..., description="Summoner name")
    riot_id_game_name: str | None = Field(None, description="Riot ID game name")
    riot_id_tagline: str | None = Field(None, description="Riot ID tagline")
    participant_id: int = Field(..., ge=1, le=10)
    team_id: int = Field(..., description="100 (blue) or 200 (red)")

    # Champion and role
    champion_id: int = Field(..., description="Champion ID")
    champion_name: str = Field(..., description="Champion name")
    champion_level: int = Field(..., ge=1, le=18)
    champion_transform: int | None = Field(None, description="Champion transformation (e.g., Kayn)")
    team_position: str | None = Field(None, description="Assigned position")
    individual_position: str | None = Field(None, description="Detected position")
    role: str | None = Field(None, description="Role (DUO, SOLO, etc.)")
    lane: str | None = Field(None, description="Lane (TOP, JUNGLE, MIDDLE, BOTTOM)")

    # Summoner spells and runes
    summoner1_id: int = Field(..., description="First summoner spell ID")
    summoner2_id: int = Field(..., description="Second summoner spell ID")
    summoner1_casts: int | None = Field(None, ge=0)
    summoner2_casts: int | None = Field(None, ge=0)
    perks: Perks | None = Field(None, description="Rune information")

    # Core stats
    kills: int = Field(0, ge=0)
    deaths: int = Field(0, ge=0)
    assists: int = Field(0, ge=0)
    double_kills: int = Field(0, ge=0)
    triple_kills: int = Field(0, ge=0)
    quadra_kills: int = Field(0, ge=0)
    penta_kills: int = Field(0, ge=0)
    unreal_kills: int = Field(0, ge=0)
    killing_sprees: int = Field(0, ge=0)
    largest_killing_spree: int = Field(0, ge=0)
    largest_multi_kill: int = Field(0, ge=0)

    # Damage
    total_damage_dealt: int = Field(0, ge=0)
    total_damage_dealt_to_champions: int = Field(0, ge=0)
    total_damage_taken: int = Field(0, ge=0)
    damage_self_mitigated: int = Field(0, ge=0)
    physical_damage_dealt: int = Field(0, ge=0)
    physical_damage_dealt_to_champions: int = Field(0, ge=0)
    physical_damage_taken: int = Field(0, ge=0)
    magic_damage_dealt: int = Field(0, ge=0)
    magic_damage_dealt_to_champions: int = Field(0, ge=0)
    magic_damage_taken: int = Field(0, ge=0)
    true_damage_dealt: int = Field(0, ge=0)
    true_damage_dealt_to_champions: int = Field(0, ge=0)
    true_damage_taken: int = Field(0, ge=0)
    largest_critical_strike: int = Field(0, ge=0)

    # Healing and shielding
    total_heal: int = Field(0, ge=0)
    total_heals_on_teammates: int = Field(0, ge=0)
    total_damage_shielded_on_teammates: int = Field(0, ge=0)
    total_units_healed: int = Field(0, ge=0)

    # Economy
    gold_earned: int = Field(0, ge=0)
    gold_spent: int = Field(0, ge=0)
    item0: int = Field(0, description="Item in slot 0")
    item1: int = Field(0, description="Item in slot 1")
    item2: int = Field(0, description="Item in slot 2")
    item3: int = Field(0, description="Item in slot 3")
    item4: int = Field(0, description="Item in slot 4")
    item5: int = Field(0, description="Item in slot 5")
    item6: int = Field(0, description="Item in slot 6 (trinket)")
    items_purchased: int = Field(0, ge=0)
    consumables_purchased: int = Field(0, ge=0)

    # Farming
    total_minions_killed: int = Field(0, ge=0)
    neutral_minions_killed: int = Field(0, ge=0)
    cs_per_minute: float | None = Field(None, ge=0)

    # Vision
    vision_score: int = Field(0, ge=0)
    vision_wards_bought_in_game: int = Field(0, ge=0)
    sight_wards_bought_in_game: int = Field(0, ge=0)
    detector_wards_placed: int | None = Field(None, ge=0)
    wards_placed: int | None = Field(None, ge=0)
    wards_killed: int | None = Field(None, ge=0)

    # Objectives
    baron_kills: int | None = Field(None, ge=0)
    dragon_kills: int | None = Field(None, ge=0)
    inhibitor_kills: int | None = Field(None, ge=0)
    inhibitor_takedowns: int | None = Field(None, ge=0)
    inhibitors_lost: int | None = Field(None, ge=0)
    nexus_kills: int | None = Field(None, ge=0)
    nexus_takedowns: int | None = Field(None, ge=0)
    nexus_lost: int | None = Field(None, ge=0)
    turret_kills: int | None = Field(None, ge=0)
    turret_takedowns: int | None = Field(None, ge=0)
    turrets_lost: int | None = Field(None, ge=0)

    # First events
    first_blood_assist: bool = Field(False)
    first_blood_kill: bool = Field(False)
    first_tower_assist: bool = Field(False)
    first_tower_kill: bool = Field(False)

    # Game flow
    game_ended_in_early_surrender: bool = Field(False)
    game_ended_in_surrender: bool = Field(False)
    team_early_surrendered: bool = Field(False)
    win: bool = Field(False)

    # Time stats
    longest_time_spent_living: int | None = Field(None, ge=0, description="Seconds")
    time_ccing_others: int | None = Field(None, ge=0, description="Seconds")
    time_played: int | None = Field(None, ge=0, description="Seconds")
    total_time_cc_dealt: int | None = Field(None, ge=0, description="Seconds")
    total_time_spent_dead: int | None = Field(None, ge=0, description="Seconds")

    # Challenges
    challenges: Challenges | None = Field(None)

    # Missions/Bounties
    missions: Dict[str, Any] | None = Field(None)
    placement: int | None = Field(None, ge=1, le=10)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kda(self) -> float:
        """Calculate KDA ratio."""
        if self.deaths == 0:
            return float(self.kills + self.assists)
        return (self.kills + self.assists) / self.deaths

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kill_participation_percent(self) -> float | None:
        """Get kill participation from challenges or return None."""
        if self.challenges and self.challenges.kill_participation is not None:
            return self.challenges.kill_participation
        return None

    @property
    def items(self) -> List[int]:
        """Get list of all items (excluding empty slots)."""
        items = []
        for i in range(7):
            item_id = getattr(self, f"item{i}", 0)
            if item_id > 0:
                items.append(item_id)
        return items


class MatchInfo(BaseContract):
    """Complete match information."""

    # Metadata
    game_creation: int = Field(..., description="Game creation timestamp (epoch milliseconds)")
    game_duration: int = Field(..., description="Game duration in seconds")
    game_end_timestamp: int | None = Field(None, description="Game end timestamp (epoch milliseconds)")
    game_id: int = Field(..., description="Game ID")
    game_mode: str = Field(..., description="Game mode")
    game_name: str = Field(..., description="Game name")
    game_start_timestamp: int = Field(..., description="Game start timestamp (epoch milliseconds)")
    game_type: str = Field(..., description="Game type")
    game_version: str = Field(..., description="Game version/patch")
    map_id: int = Field(..., description="Map ID")
    platform_id: str = Field(..., description="Platform ID")
    queue_id: int = Field(..., description="Queue ID")
    tournament_code: str | None = Field(None, description="Tournament code if applicable")

    # Teams and participants
    teams: List[Team] = Field(..., min_length=2, max_length=2)
    participants: List[Participant] = Field(..., min_length=10, max_length=10)

    @property
    def game_creation_date(self) -> datetime:
        """Convert game creation to datetime."""
        return datetime.fromtimestamp(self.game_creation / 1000)

    @property
    def game_start_date(self) -> datetime:
        """Convert game start to datetime."""
        return datetime.fromtimestamp(self.game_start_timestamp / 1000)

    @property
    def game_end_date(self) -> datetime | None:
        """Convert game end to datetime."""
        if self.game_end_timestamp:
            return datetime.fromtimestamp(self.game_end_timestamp / 1000)
        return None

    @property
    def winning_team_id(self) -> int:
        """Get winning team ID."""
        for team in self.teams:
            if team.win:
                return team.team_id
        return 0

    def get_participant_by_puuid(self, puuid: str) -> Participant | None:
        """Get participant by PUUID."""
        for participant in self.participants:
            if participant.puuid == puuid:
                return participant
        return None

    def get_team_participants(self, team_id: int) -> List[Participant]:
        """Get all participants for a team."""
        return [p for p in self.participants if p.team_id == team_id]


class MatchMetadata(BaseContract):
    """Match metadata."""

    data_version: str = Field(..., description="Data version")
    match_id: str = Field(..., description="Match ID")
    participants: List[str] = Field(..., description="List of participant PUUIDs")


class Match(BaseContract):
    """Complete match data from Riot API."""

    metadata: MatchMetadata
    info: MatchInfo