"""
Match Timeline data contracts for Riot API Match-V5.
This is the core data structure for match analysis.
"""

from typing import Any

from pydantic import Field, field_validator

from .common import BaseContract, Position


class ChampionStats(BaseContract):
    """Champion stats at a specific frame."""

    ability_haste: int = Field(0)
    ability_power: int = Field(0)
    armor: int = Field(0)
    armor_pen: int = Field(0)
    armor_pen_percent: int = Field(0)
    attack_damage: int = Field(0)
    attack_speed: int = Field(100)
    bonus_armor_pen_percent: int = Field(0)
    bonus_magic_pen_percent: int = Field(0)
    cc_reduction: int = Field(0)
    cooldown_reduction: int = Field(0)
    health: int = Field(0)
    health_max: int = Field(0)
    health_regen: int = Field(0)
    lifesteal: int = Field(0)
    magic_pen: int = Field(0)
    magic_pen_percent: int = Field(0)
    magic_resist: int = Field(0)
    movement_speed: int = Field(0)
    omnivamp: int = Field(0)
    physical_vamp: int = Field(0)
    power: int = Field(0, description="Mana or Energy")
    power_max: int = Field(0)
    power_regen: int = Field(0)
    spell_vamp: int = Field(0)


class DamageStats(BaseContract):
    """Damage statistics at a specific frame."""

    magic_damage_done: int = Field(0)
    magic_damage_done_to_champions: int = Field(0)
    magic_damage_taken: int = Field(0)
    physical_damage_done: int = Field(0)
    physical_damage_done_to_champions: int = Field(0)
    physical_damage_taken: int = Field(0)
    total_damage_done: int = Field(0)
    total_damage_done_to_champions: int = Field(0)
    total_damage_taken: int = Field(0)
    true_damage_done: int = Field(0)
    true_damage_done_to_champions: int = Field(0)
    true_damage_taken: int = Field(0)


class ParticipantFrame(BaseContract):
    """Participant state at a specific frame."""

    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    champion_stats: ChampionStats
    damage_stats: DamageStats
    current_gold: int = Field(0)
    gold_per_second: int = Field(0)
    jungle_minions_killed: int = Field(0)
    level: int = Field(1, ge=1, le=30)  # Arena mode can exceed 18
    minions_killed: int = Field(0)
    position: Position
    time_enemy_spent_controlled: int = Field(0)
    total_gold: int = Field(0)
    xp: int = Field(0)


class Frame(BaseContract):
    """A single frame in the match timeline."""

    timestamp: int = Field(..., description="Frame timestamp in milliseconds")
    participant_frames: dict[str, ParticipantFrame] = Field(
        ..., description="Participant states indexed by participant ID string"
    )
    events: list[dict[str, Any]] = Field(
        default_factory=list, description="Events that occurred during this frame"
    )

    @field_validator("participant_frames", mode="before")
    @classmethod
    def convert_participant_frames(cls, v: Any) -> dict[str, ParticipantFrame]:
        """Convert raw participant frames to typed models."""
        if isinstance(v, dict):
            result = {}
            for key, value in v.items():
                if isinstance(value, dict):
                    # Ensure participant_id is in the data
                    if "participantId" in value:
                        value["participant_id"] = value["participantId"]
                    result[key] = (
                        ParticipantFrame(**value)
                        if not isinstance(value, ParticipantFrame)
                        else value
                    )
                else:
                    result[key] = value
            return result
        return v  # type: ignore[no-any-return]


class TimelineParticipant(BaseContract):
    """Participant mapping in timeline."""

    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    puuid: str = Field(..., description="Player's PUUID")


class TimelineInfo(BaseContract):
    """Timeline information containing frames and metadata."""

    frame_interval: int = Field(60000, description="Milliseconds between frames (usually 60000)")
    frames: list[Frame] = Field(..., description="List of all frames in the match")
    game_id: int = Field(..., description="Game ID")
    participants: list[TimelineParticipant] = Field(
        ..., description="Participant ID to PUUID mapping"
    )


class TimelineMetadata(BaseContract):
    """Timeline metadata."""

    data_version: str = Field(..., description="Data version")
    match_id: str = Field(..., description="Match ID")
    participants: list[str] = Field(..., description="List of participant PUUIDs")


class MatchTimeline(BaseContract):
    """Complete match timeline from Riot API Match-V5."""

    metadata: TimelineMetadata
    info: TimelineInfo

    def get_participant_by_puuid(self, puuid: str) -> int | None:
        """Get participant ID by PUUID."""
        for participant in self.info.participants:
            if participant.puuid == puuid:
                return participant.participant_id
        return None

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type."""
        events = []
        for frame in self.info.frames:
            for event in frame.events:
                if event.get("type") == event_type:
                    events.append(event)
        return events

    def get_participant_frame_at_time(
        self, participant_id: int, timestamp: int
    ) -> ParticipantFrame | None:
        """Get participant frame at or before a specific timestamp."""
        for frame in reversed(self.info.frames):
            if frame.timestamp <= timestamp:
                return frame.participant_frames.get(str(participant_id))
        return None

    def get_kill_participation(self, participant_id: int) -> float:
        """Calculate kill participation percentage for a participant."""
        total_team_kills = 0
        participant_kills = 0

        # Determine team
        team_id = 100 if participant_id <= 5 else 200
        team_participants = range(1, 6) if team_id == 100 else range(6, 11)

        for frame in self.info.frames:
            for event in frame.events:
                if event.get("type") == "CHAMPION_KILL":
                    killer_id = event.get("killerId", 0)

                    # Count team kills
                    if killer_id in team_participants:
                        total_team_kills += 1

                        # Count participant involvement
                        if killer_id == participant_id or participant_id in event.get(
                            "assistingParticipantIds", []
                        ):
                            participant_kills += 1

        if total_team_kills == 0:
            return 0.0

        return (participant_kills / total_team_kills) * 100
