"""Pydantic models for Riot API responses.

These models ensure type safety for all Riot API data flowing through the system.
Based on Match-V5 and Summoner-V4 API specifications.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# Summoner API Models
class SummonerDTO(BaseModel):
    """Summoner data from Summoner-V4 API."""

    account_id: str = Field(..., alias="accountId")
    profile_icon_id: int = Field(..., alias="profileIconId")
    revision_date: int = Field(..., alias="revisionDate")
    id: str  # Encrypted summoner ID
    puuid: str  # Player Universally Unique Identifier
    summoner_level: int = Field(..., alias="summonerLevel")
    name: str  # Summoner name


# Match-V5 API Models
class MatchMetadata(BaseModel):
    """Metadata for a match."""

    data_version: str = Field(..., alias="dataVersion")
    match_id: str = Field(..., alias="matchId")
    participants: list[str]  # List of PUUIDs


class PerkStyleSelection(BaseModel):
    """Perks selected by a player."""

    perk: int
    var1: int
    var2: int
    var3: int


class PerkStyle(BaseModel):
    """Perk style information."""

    description: str
    selections: list[PerkStyleSelection]
    style: int


class Perks(BaseModel):
    """Player perks (runes)."""

    stat_perks: dict[str, int] = Field(..., alias="statPerks")
    styles: list[PerkStyle]


class Challenges(BaseModel):
    """Challenge statistics for a participant."""

    kda_player: float | None = Field(None, alias="kda")
    ability_uses: int | None = Field(None, alias="abilityUses")
    ace_before_15_minutes: int | None = Field(None, alias="acesBefore15Minutes")
    allied_jungle_monster_kills: int | None = Field(None, alias="alliedJungleMonsterKills")
    baron_takedowns: int | None = Field(None, alias="baronTakedowns")
    blast_cone_opposite_opponent_count: int | None = Field(
        None, alias="blastConeOppositeOpponentCount"
    )
    bounty_gold: int | None = Field(None, alias="bountyGold")
    buffs_stolen: int | None = Field(None, alias="buffsStolen")


class ParticipantDTO(BaseModel):
    """Participant data from a match."""

    # Identity
    puuid: str
    summoner_id: str = Field(..., alias="summonerId")
    summoner_name: str = Field(..., alias="summonerName")
    riot_id_game_name: str = Field(..., alias="riotIdGameName")
    riot_id_tagline: str = Field(..., alias="riotIdTagline")
    team_id: int = Field(..., alias="teamId")
    participant_id: int = Field(..., alias="participantId")

    # Champion and position
    champion_id: int = Field(..., alias="championId")
    champion_name: str = Field(..., alias="championName")
    champ_level: int = Field(..., alias="champLevel")
    team_position: str = Field(..., alias="teamPosition")
    individual_position: str = Field(..., alias="individualPosition")
    lane: str
    role: str

    # Performance metrics
    kills: int
    deaths: int
    assists: int
    kda: float
    kill_participation: float = Field(..., alias="killParticipation")

    # Damage stats
    total_damage_dealt: int = Field(..., alias="totalDamageDealt")
    total_damage_dealt_to_champions: int = Field(..., alias="totalDamageDealtToChampions")
    total_damage_taken: int = Field(..., alias="totalDamageTaken")
    damage_self_mitigated: int = Field(..., alias="damageSelfMitigated")

    # Economy
    gold_earned: int = Field(..., alias="goldEarned")
    gold_spent: int = Field(..., alias="goldSpent")
    total_minions_killed: int = Field(..., alias="totalMinionsKilled")
    neutral_minions_killed: int = Field(..., alias="neutralMinionsKilled")

    # Vision
    vision_score: int = Field(..., alias="visionScore")
    wards_placed: int = Field(..., alias="wardsPlaced")
    wards_killed: int = Field(..., alias="wardsKilled")
    detector_wards_placed: int = Field(..., alias="detectorWardsPlaced")

    # Game outcome
    win: bool
    game_ended_in_early_surrender: bool = Field(..., alias="gameEndedInEarlySurrender")
    game_ended_in_surrender: bool = Field(..., alias="gameEndedInSurrender")

    # Items
    item0: int
    item1: int
    item2: int
    item3: int
    item4: int
    item5: int
    item6: int

    # Summoner spells and perks
    summoner1_id: int = Field(..., alias="summoner1Id")
    summoner2_id: int = Field(..., alias="summoner2Id")
    perks: Perks | None = None

    # Additional stats
    challenges: Challenges | None = None
    time_played: int = Field(..., alias="timePlayed")
    time_ccing_others: int = Field(..., alias="timeCCingOthers")
    longest_time_spent_living: int = Field(..., alias="longestTimeSpentLiving")


class TeamObjective(BaseModel):
    """Team objective information (baron, dragon, etc.)."""

    first: bool
    kills: int


class TeamDTO(BaseModel):
    """Team information from a match."""

    team_id: int = Field(..., alias="teamId")
    win: bool
    bans: list[dict[str, Any]]
    objectives: dict[str, TeamObjective]


class MatchInfoDTO(BaseModel):
    """Detailed match information."""

    # Game metadata
    game_id: int = Field(..., alias="gameId")
    game_creation: int = Field(..., alias="gameCreation")
    game_duration: int = Field(..., alias="gameDuration")
    game_start_timestamp: int = Field(..., alias="gameStartTimestamp")
    game_end_timestamp: int = Field(..., alias="gameEndTimestamp")
    game_mode: str = Field(..., alias="gameMode")
    game_name: str = Field(..., alias="gameName")
    game_type: str = Field(..., alias="gameType")
    game_version: str = Field(..., alias="gameVersion")
    map_id: int = Field(..., alias="mapId")
    platform_id: str = Field(..., alias="platformId")
    queue_id: int = Field(..., alias="queueId")
    tournament_code: str | None = Field(None, alias="tournamentCode")

    # Participants and teams
    participants: list[ParticipantDTO]
    teams: list[TeamDTO]


class MatchDTO(BaseModel):
    """Complete match data from Match-V5 API."""

    metadata: MatchMetadata
    info: MatchInfoDTO


# Timeline API Models
class Position(BaseModel):
    """Position on the map."""

    x: int
    y: int


class VictimDamage(BaseModel):
    """Damage dealt to a victim."""

    basic: bool
    magic_damage: int = Field(..., alias="magicDamage")
    name: str
    participant_id: int = Field(..., alias="participantId")
    physical_damage: int = Field(..., alias="physicalDamage")
    spell_name: str = Field(..., alias="spellName")
    spell_slot: int = Field(..., alias="spellSlot")
    true_damage: int = Field(..., alias="trueDamage")
    type: str


class TimelineEvent(BaseModel):
    """Event in a match timeline."""

    timestamp: int
    type: str
    participant_id: int | None = Field(None, alias="participantId")
    item_id: int | None = Field(None, alias="itemId")
    skill_slot: int | None = Field(None, alias="skillSlot")
    level_up_type: str | None = Field(None, alias="levelUpType")
    ward_type: str | None = Field(None, alias="wardType")
    creator_id: int | None = Field(None, alias="creatorId")
    position: Position | None = None
    victim_id: int | None = Field(None, alias="victimId")
    kill_streak_length: int | None = Field(None, alias="killStreakLength")
    killer_id: int | None = Field(None, alias="killerId")
    assisting_participant_ids: list[int] | None = Field(None, alias="assistingParticipantIds")
    victim_damage_dealt: list[VictimDamage] | None = Field(None, alias="victimDamageDealt")
    victim_damage_received: list[VictimDamage] | None = Field(None, alias="victimDamageReceived")

    # Building and monster events
    building_type: str | None = Field(None, alias="buildingType")
    lane_type: str | None = Field(None, alias="laneType")
    team_id: int | None = Field(None, alias="teamId")
    monster_type: str | None = Field(None, alias="monsterType")
    monster_sub_type: str | None = Field(None, alias="monsterSubType")

    # Objective bounty
    bounty: int | None = None
    kill_type: str | None = Field(None, alias="killType")

    # Shutdown
    shutdown_bounty: int | None = Field(None, alias="shutdownBounty")

    # Gold and other
    gold_gain: int | None = Field(None, alias="goldGain")
    actual_start_time: int | None = Field(None, alias="actualStartTime")


class ParticipantFrame(BaseModel):
    """Participant state at a specific frame."""

    champion_stats: dict[str, Any] = Field(..., alias="championStats")
    current_gold: int = Field(..., alias="currentGold")
    damage_stats: dict[str, Any] = Field(..., alias="damageStats")
    gold_per_second: int = Field(..., alias="goldPerSecond")
    jungle_minions_killed: int = Field(..., alias="jungleMinionsKilled")
    level: int
    minions_killed: int = Field(..., alias="minionsKilled")
    participant_id: int = Field(..., alias="participantId")
    position: Position
    time_enemy_spent_controlled: int = Field(..., alias="timeEnemySpentControlled")
    total_gold: int = Field(..., alias="totalGold")
    xp: int


class TimelineFrame(BaseModel):
    """Frame in a match timeline."""

    events: list[TimelineEvent]
    participant_frames: dict[str, ParticipantFrame] = Field(..., alias="participantFrames")
    timestamp: int


class TimelineParticipant(BaseModel):
    """Participant information in timeline."""

    participant_id: int = Field(..., alias="participantId")
    puuid: str


class TimelineInfo(BaseModel):
    """Timeline information."""

    end_of_game_result: str | None = Field(None, alias="endOfGameResult")
    frame_interval: int = Field(..., alias="frameInterval")
    frames: list[TimelineFrame]
    game_id: int = Field(..., alias="gameId")
    participants: list[TimelineParticipant]


class MatchTimelineDTO(BaseModel):
    """Complete match timeline from Match-V5 Timeline API."""

    metadata: MatchMetadata
    info: TimelineInfo


# User binding models
class UserBinding(BaseModel):
    """User binding between Discord and Riot accounts."""

    discord_id: str
    puuid: str
    summoner_name: str
    summoner_id: str
    region: str = "na1"
    created_at: datetime
    updated_at: datetime


# Match analysis models
class MatchAnalysis(BaseModel):
    """Analyzed match data ready for LLM processing."""

    match_id: str
    game_duration: int
    participants: list[ParticipantDTO]
    timeline_events: list[TimelineEvent]
    key_moments: list[dict[str, Any]]  # Extracted key moments
    team_objectives: dict[int, dict[str, Any]]  # Team objectives by team ID
    performance_scores: dict[str, float]  # PUUID to performance score mapping
