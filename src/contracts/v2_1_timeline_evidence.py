"""V2.1 Timeline Evidence Data Contracts.

This module defines Pydantic V2 data contracts for extracting structured evidence
from Match-V5 Timeline data to support V2.1 Instructional Analysis.

Purpose:
- Provide concrete evidence (specific events, timestamps, positions) for LLM guidance
- Enable fact-based improvement suggestions (e.g., "You used Flash at 12:34 but died
  immediately after - consider saving it for team fights")
- Support multi-dimensional analysis with granular event data

Architecture:
- CLI 2 (Backend): Implements evidence extraction from Timeline API
- CLI 4 (Lab): Designs prompt templates that reference evidence structures
- CLI 1 (Frontend): May display evidence summaries in Discord embeds (optional)
"""

from typing import Literal

from pydantic import BaseModel, Field


# ===== Ward Placement Evidence =====


class WardPlacementEvent(BaseModel):
    """Individual ward placement event from Timeline.

    Evidence for Vision Control analysis and improvement suggestions.
    """

    timestamp_ms: int = Field(
        description="Timestamp of ward placement (milliseconds since game start)"
    )
    timestamp_display: str = Field(description="Human-readable timestamp (e.g., '12:34')")
    ward_type: Literal["YELLOW_TRINKET", "CONTROL_WARD", "BLUE_TRINKET", "SIGHT_WARD"] = Field(
        description="Type of ward placed"
    )
    position_x: int = Field(description="X coordinate on map")
    position_y: int = Field(description="Y coordinate on map")
    position_label: str | None = Field(
        default=None,
        description="Semantic label for position (e.g., 'Dragon Pit', 'Baron Bush')",
    )


class WardControlEvidence(BaseModel):
    """Aggregated ward control evidence for a player.

    Provides factual basis for vision-related improvement suggestions.
    """

    total_wards_placed: int = Field(description="Total wards placed by player")
    control_wards_placed: int = Field(description="Control wards placed")
    wards_destroyed: int = Field(description="Enemy wards destroyed")
    critical_objective_wards: int = Field(
        description="Wards placed near major objectives (Dragon, Baron, etc.)"
    )
    ward_events: list[WardPlacementEvent] = Field(
        default_factory=list,
        description="Sample of ward placement events (max 5 for context)",
        max_length=5,
    )


# ===== Champion Kill Evidence =====


class AbilityUsage(BaseModel):
    """Ability/summoner spell usage context in a kill event."""

    ability_type: Literal["FLASH", "ULTIMATE", "HEAL", "TELEPORT", "OTHER"] = Field(
        description="Type of ability/spell used"
    )
    used_by_victim: bool = Field(
        description="True if victim used the ability, False if killer used it"
    )
    timestamp_before_death_ms: int | None = Field(
        default=None,
        description="Time before death when ability was used (for victim analysis)",
    )


class ChampionKillEvent(BaseModel):
    """Individual champion kill event with combat context.

    Evidence for Combat Efficiency and decision-making analysis.
    """

    timestamp_ms: int = Field(description="Timestamp of kill (milliseconds since game start)")
    timestamp_display: str = Field(description="Human-readable timestamp (e.g., '15:23')")
    victim_participant_id: int = Field(description="Participant ID of killed champion")
    killer_participant_id: int = Field(description="Participant ID of killer")
    was_target_player_victim: bool = Field(
        description="True if target player was killed in this event"
    )
    was_target_player_killer: bool = Field(description="True if target player got the kill")
    was_target_player_assist: bool = Field(description="True if target player assisted in kill")

    # Combat context
    kill_bounty: int | None = Field(default=None, description="Gold bounty for kill (if available)")
    abilities_used: list[AbilityUsage] = Field(
        default_factory=list, description="Key abilities/spells used in kill context"
    )
    position_x: int = Field(description="X coordinate of kill")
    position_y: int = Field(description="Y coordinate of kill")
    position_label: str | None = Field(
        default=None, description="Semantic label (e.g., 'Mid Lane', 'Enemy Jungle')"
    )


class CombatEvidence(BaseModel):
    """Aggregated combat evidence for a player.

    Provides factual basis for combat efficiency and decision-making guidance.
    """

    total_kills: int = Field(description="Total kills by player")
    total_deaths: int = Field(description="Total deaths")
    total_assists: int = Field(description="Total assists")
    solo_kills: int = Field(description="Kills without assist")
    early_flash_usage_count: int = Field(
        description="Deaths where player used Flash <5s before dying (potential misuse)"
    )
    kill_events: list[ChampionKillEvent] = Field(
        default_factory=list,
        description="Sample of kill events (max 3 deaths + 2 kills for instructional context)",
        max_length=5,
    )


# ===== Top-Level Evidence Container =====


class V2_1_TimelineEvidence(BaseModel):
    """Complete timeline evidence package for V2.1 Instructional Analysis.

    This contract defines the structured evidence that CLI 2 extracts from
    Match-V5 Timeline and provides to the LLM for generating specific,
    fact-based improvement suggestions.

    Design Constraints:
    - Evidence must be sampled (not all events) to fit in LLM context window
    - Prioritize events relevant to player's weakest dimensions
    - Include timestamps and positions for concrete guidance
    """

    match_id: str = Field(description="Match ID for reference")
    target_player_participant_id: int = Field(description="Target player's participant ID")

    # Evidence by dimension
    ward_control_evidence: WardControlEvidence = Field(
        description="Vision control evidence (relevant if vision_score is low)"
    )
    combat_evidence: CombatEvidence = Field(
        description="Combat decision-making evidence (relevant if combat_score is low)"
    )

    # Future evidence types (V2.2+)
    # objective_evidence: ObjectiveControlEvidence (Dragon/Baron fight contexts)
    # economy_evidence: EconomyManagementEvidence (CS misses, item timing)
    # teamplay_evidence: TeamplayEvidence (team fight positioning, CC usage)


# ===== Example Data =====

EXAMPLE_V2_1_TIMELINE_EVIDENCE = {
    "match_id": "NA1_5387390374",
    "target_player_participant_id": 1,
    "ward_control_evidence": {
        "total_wards_placed": 8,
        "control_wards_placed": 2,
        "wards_destroyed": 3,
        "critical_objective_wards": 1,
        "ward_events": [
            {
                "timestamp_ms": 420000,
                "timestamp_display": "7:00",
                "ward_type": "CONTROL_WARD",
                "position_x": 9500,
                "position_y": 4200,
                "position_label": "Dragon Pit Bush",
            }
        ],
    },
    "combat_evidence": {
        "total_kills": 5,
        "total_deaths": 7,
        "total_assists": 8,
        "solo_kills": 1,
        "early_flash_usage_count": 2,
        "kill_events": [
            {
                "timestamp_ms": 840000,
                "timestamp_display": "14:00",
                "victim_participant_id": 1,
                "killer_participant_id": 6,
                "was_target_player_victim": True,
                "was_target_player_killer": False,
                "was_target_player_assist": False,
                "kill_bounty": 300,
                "abilities_used": [
                    {
                        "ability_type": "FLASH",
                        "used_by_victim": True,
                        "timestamp_before_death_ms": 2000,
                    }
                ],
                "position_x": 5200,
                "position_y": 8100,
                "position_label": "Mid Lane",
            }
        ],
    },
}
