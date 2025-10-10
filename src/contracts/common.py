"""
Common data types and base models for 蔚-上城人.
All models use Pydantic V2 with strict type checking.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Region(str, Enum):
    """Riot API Regions."""

    AMERICAS = "americas"
    EUROPE = "europe"
    ASIA = "asia"
    SEA = "sea"


class Platform(str, Enum):
    """Riot API Platforms (game servers)."""

    BR1 = "br1"  # Brazil
    EUN1 = "eun1"  # Europe Nordic & East
    EUW1 = "euw1"  # Europe West
    JP1 = "jp1"  # Japan
    KR = "kr"  # Korea
    LA1 = "la1"  # Latin America North
    LA2 = "la2"  # Latin America South
    NA1 = "na1"  # North America
    OC1 = "oc1"  # Oceania
    PH2 = "ph2"  # Philippines
    RU = "ru"  # Russia
    SG2 = "sg2"  # Singapore
    TH2 = "th2"  # Thailand
    TR1 = "tr1"  # Turkey
    TW2 = "tw2"  # Taiwan
    VN2 = "vn2"  # Vietnam


class Queue(int, Enum):
    """Game queue types."""

    RANKED_SOLO_5x5 = 420
    RANKED_FLEX_SR = 440
    NORMAL_DRAFT_PICK = 400
    NORMAL_BLIND_PICK = 430
    ARAM = 450
    CLASH = 700


class Tier(str, Enum):
    """Ranked tiers."""

    IRON = "IRON"
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"
    EMERALD = "EMERALD"
    DIAMOND = "DIAMOND"
    MASTER = "MASTER"
    GRANDMASTER = "GRANDMASTER"
    CHALLENGER = "CHALLENGER"


class Division(str, Enum):
    """Ranked divisions."""

    DIV_I = "I"
    DIV_II = "II"
    DIV_III = "III"
    DIV_IV = "IV"


class Position(BaseModel):
    """2D position on the map."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    x: int = Field(..., description="X coordinate on the map")
    y: int = Field(..., description="Y coordinate on the map")


class BaseContract(BaseModel):
    """Base model for all data contracts with common configuration."""

    model_config = ConfigDict(
        # Validate data on assignment
        validate_assignment=True,
        # Use enum values in JSON
        use_enum_values=True,
        # Include all fields in JSON
        json_schema_extra={"examples": []},
        # Forbid extra fields to ensure data integrity
        extra="forbid",
    )
