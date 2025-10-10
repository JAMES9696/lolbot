"""
Timeline event models for Match-V5 API.
Each event type has its own model for type safety.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import Field

from .common import BaseContract, Position


class EventType(str, Enum):
    """All possible event types in Match Timeline."""

    PAUSE_START = "PAUSE_START"
    PAUSE_END = "PAUSE_END"
    SKILL_LEVEL_UP = "SKILL_LEVEL_UP"
    ITEM_PURCHASED = "ITEM_PURCHASED"
    ITEM_SOLD = "ITEM_SOLD"
    ITEM_DESTROYED = "ITEM_DESTROYED"
    ITEM_UNDO = "ITEM_UNDO"
    TURRET_PLATE_DESTROYED = "TURRET_PLATE_DESTROYED"
    CHAMPION_KILL = "CHAMPION_KILL"
    WARD_PLACED = "WARD_PLACED"
    WARD_KILL = "WARD_KILL"
    BUILDING_KILL = "BUILDING_KILL"
    ELITE_MONSTER_KILL = "ELITE_MONSTER_KILL"
    CHAMPION_SPECIAL_KILL = "CHAMPION_SPECIAL_KILL"
    GAME_END = "GAME_END"
    CHAMPION_TRANSFORM = "CHAMPION_TRANSFORM"
    DRAGON_SOUL_GIVEN = "DRAGON_SOUL_GIVEN"
    OBJECTIVE_BOUNTY_PRESTART = "OBJECTIVE_BOUNTY_PRESTART"
    OBJECTIVE_BOUNTY_FINISH = "OBJECTIVE_BOUNTY_FINISH"


class WardType(str, Enum):
    """Types of wards that can be placed."""

    YELLOW_TRINKET = "YELLOW_TRINKET"
    CONTROL_WARD = "CONTROL_WARD"
    SIGHT_WARD = "SIGHT_WARD"
    BLUE_TRINKET = "BLUE_TRINKET"
    TEEMO_MUSHROOM = "TEEMO_MUSHROOM"
    UNDEFINED = "UNDEFINED"


class MonsterType(str, Enum):
    """Elite monster types."""

    DRAGON = "DRAGON"
    BARON_NASHOR = "BARON_NASHOR"
    RIFTHERALD = "RIFTHERALD"


class MonsterSubType(str, Enum):
    """Dragon subtypes."""

    CLOUD_DRAGON = "CLOUD_DRAGON"
    INFERNAL_DRAGON = "INFERNAL_DRAGON"
    MOUNTAIN_DRAGON = "MOUNTAIN_DRAGON"
    OCEAN_DRAGON = "OCEAN_DRAGON"
    HEXTECH_DRAGON = "HEXTECH_DRAGON"
    CHEMTECH_DRAGON = "CHEMTECH_DRAGON"
    ELDER_DRAGON = "ELDER_DRAGON"


class BuildingType(str, Enum):
    """Building types."""

    TOWER_BUILDING = "TOWER_BUILDING"
    INHIBITOR_BUILDING = "INHIBITOR_BUILDING"


class TowerType(str, Enum):
    """Tower types."""

    OUTER_TURRET = "OUTER_TURRET"
    INNER_TURRET = "INNER_TURRET"
    BASE_TURRET = "BASE_TURRET"
    NEXUS_TURRET = "NEXUS_TURRET"


class KillType(str, Enum):
    """Special kill types."""

    KILL_ACE = "KILL_ACE"
    KILL_FIRST_BLOOD = "KILL_FIRST_BLOOD"
    KILL_MULTI = "KILL_MULTI"


class LaneType(str, Enum):
    """Lane types for minion kills."""

    TOP_LANE = "TOP_LANE"
    MID_LANE = "MID_LANE"
    BOT_LANE = "BOT_LANE"


class BaseEvent(BaseContract):
    """Base class for all timeline events."""

    timestamp: int = Field(..., description="Game time in milliseconds when event occurred")
    type: EventType = Field(..., description="Type of the event")
    real_timestamp: int | None = Field(None, description="Real world timestamp")


class PauseEvent(BaseEvent):
    """Game pause/unpause events."""

    type: Literal[EventType.PAUSE_START, EventType.PAUSE_END]


class SkillLevelUpEvent(BaseEvent):
    """Skill level up event."""

    type: Literal[EventType.SKILL_LEVEL_UP]
    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    skill_slot: int = Field(..., ge=1, le=4, description="Skill slot (1=Q, 2=W, 3=E, 4=R)")
    level_up_type: str = Field(..., description="NORMAL or EVOLVE")


class ItemEvent(BaseEvent):
    """Base class for item-related events."""

    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    item_id: int = Field(..., description="Item ID from Data Dragon")


class ItemPurchasedEvent(ItemEvent):
    """Item purchase event."""

    type: Literal[EventType.ITEM_PURCHASED]


class ItemSoldEvent(ItemEvent):
    """Item sold event."""

    type: Literal[EventType.ITEM_SOLD]


class ItemDestroyedEvent(ItemEvent):
    """Item destroyed event."""

    type: Literal[EventType.ITEM_DESTROYED]


class ItemUndoEvent(BaseEvent):
    """Item undo event."""

    type: Literal[EventType.ITEM_UNDO]
    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    before_id: int = Field(..., description="Item ID before undo")
    after_id: int = Field(..., description="Item ID after undo")
    gold_gain: int = Field(..., description="Gold gained from undo")


class ChampionKillEvent(BaseEvent):
    """Champion kill event with detailed information."""

    type: Literal[EventType.CHAMPION_KILL]
    killer_id: int = Field(..., ge=0, le=10, description="0 for execute")
    victim_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    position: Position
    assisting_participant_ids: list[int] = Field(default_factory=list)
    bounty: int = Field(0, description="Base bounty gold")
    shutdown_bounty: int = Field(0, description="Shutdown bounty gold")
    kill_streak_length: int = Field(0)
    victim_damage_dealt: list[dict[str, Any]] | None = Field(None)
    victim_damage_received: list[dict[str, Any]] | None = Field(None)


class WardPlacedEvent(BaseEvent):
    """Ward placement event."""

    type: Literal[EventType.WARD_PLACED]
    creator_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    ward_type: WardType


class WardKillEvent(BaseEvent):
    """Ward kill event."""

    type: Literal[EventType.WARD_KILL]
    killer_id: int = Field(..., ge=1, le=10)
    ward_type: WardType


class BuildingKillEvent(BaseEvent):
    """Building destruction event."""

    type: Literal[EventType.BUILDING_KILL]
    killer_id: int = Field(..., ge=0, le=16)  # Support Arena (2v2v2v2)
    assisting_participant_ids: list[int] = Field(default_factory=list)
    building_type: BuildingType
    position: Position
    team_id: int = Field(..., description="100 (blue) or 200 (red)")
    tower_type: TowerType | None = Field(None)
    lane_type: LaneType | None = Field(None)


class EliteMonsterKillEvent(BaseEvent):
    """Elite monster kill event."""

    type: Literal[EventType.ELITE_MONSTER_KILL]
    killer_id: int = Field(..., ge=1, le=10)
    killer_team_id: int = Field(..., description="100 (blue) or 200 (red)")
    monster_type: MonsterType
    monster_sub_type: MonsterSubType | None = Field(None)
    position: Position
    bounty: int | None = Field(None)


class TurretPlateDestroyedEvent(BaseEvent):
    """Turret plate destruction event."""

    type: Literal[EventType.TURRET_PLATE_DESTROYED]
    killer_id: int = Field(..., ge=1, le=10)
    position: Position
    team_id: int
    lane_type: LaneType | None = Field(None)


class ChampionSpecialKillEvent(BaseEvent):
    """Special kill events (ace, first blood, multikill)."""

    type: Literal[EventType.CHAMPION_SPECIAL_KILL]
    killer_id: int = Field(..., ge=1, le=10)
    kill_type: KillType
    multi_kill_length: int | None = Field(None, description="For multikills only")
    position: Position | None = Field(None)


class ChampionTransformEvent(BaseEvent):
    """Champion transformation event (Kayn, etc)."""

    type: Literal[EventType.CHAMPION_TRANSFORM]
    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    transform_type: str


class DragonSoulGivenEvent(BaseEvent):
    """Dragon soul given event."""

    type: Literal[EventType.DRAGON_SOUL_GIVEN]
    team_id: int = Field(..., description="100 (blue) or 200 (red)")
    name: str = Field(..., description="Soul type name")


class ObjectiveBountyEvent(BaseEvent):
    """Objective bounty events."""

    type: Literal[EventType.OBJECTIVE_BOUNTY_PRESTART, EventType.OBJECTIVE_BOUNTY_FINISH]
    team_id: int = Field(..., description="100 (blue) or 200 (red)")
    actual_start_time: int | None = Field(None)


class GameEndEvent(BaseEvent):
    """Game end event."""

    type: Literal[EventType.GAME_END]
    real_timestamp: int | None = Field(None)
    winning_team: int = Field(..., description="100 (blue) or 200 (red)")


# Union type for all possible events
TimelineEvent = (
    PauseEvent
    | SkillLevelUpEvent
    | ItemPurchasedEvent
    | ItemSoldEvent
    | ItemDestroyedEvent
    | ItemUndoEvent
    | ChampionKillEvent
    | WardPlacedEvent
    | WardKillEvent
    | BuildingKillEvent
    | EliteMonsterKillEvent
    | TurretPlateDestroyedEvent
    | ChampionSpecialKillEvent
    | ChampionTransformEvent
    | DragonSoulGivenEvent
    | ObjectiveBountyEvent
    | GameEndEvent
)
