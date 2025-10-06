"""
Data contracts for user binding between Discord and Riot accounts.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BindingStatus(str, Enum):
    """Status of user binding process."""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"


class UserBinding(BaseModel):
    """Represents a binding between Discord user and Riot account."""

    discord_id: str = Field(
        ...,
        description="Discord User ID (snowflake)",
        pattern=r"^\d{17,20}$"
    )

    puuid: str | None = Field(
        None,
        description="Riot PUUID (Player Universally Unique ID)",
        min_length=78,
        max_length=78
    )

    summoner_name: str | None = Field(
        None,
        description="Summoner name (game name)",
        min_length=3,
        max_length=16
    )

    region: str = Field(
        "na1",
        description="Riot server region",
        pattern=r"^(br1|eun1|euw1|jp1|kr|la1|la2|na1|oc1|ph2|ru|sg2|th2|tr1|tw2|vn2)$"
    )

    status: BindingStatus = Field(
        BindingStatus.PENDING,
        description="Current binding status"
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Binding creation timestamp"
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )

    verification_token: str | None = Field(
        None,
        description="Temporary token for RSO verification"
    )

    token_expires_at: datetime | None = Field(
        None,
        description="Token expiration timestamp"
    )


class BindingRequest(BaseModel):
    """Request model for initiating a binding."""

    discord_id: str = Field(
        ...,
        description="Discord User ID"
    )

    region: str = Field(
        "na1",
        description="Preferred region"
    )


class BindingResponse(BaseModel):
    """Response model for binding operations."""

    success: bool = Field(
        ...,
        description="Whether operation succeeded"
    )

    message: str = Field(
        ...,
        description="Human-readable message"
    )

    auth_url: str | None = Field(
        None,
        description="RSO authorization URL if applicable"
    )

    binding: UserBinding | None = Field(
        None,
        description="User binding data if available"
    )

    error: str | None = Field(
        None,
        description="Error details if operation failed"
    )


class RSOCallback(BaseModel):
    """Model for RSO OAuth callback data."""

    code: str = Field(
        ...,
        description="OAuth authorization code"
    )

    state: str = Field(
        ...,
        description="State parameter for security validation"
    )


class RiotAccount(BaseModel):
    """Riot account information from RSO."""

    puuid: str = Field(
        ...,
        description="Player Universally Unique ID"
    )

    game_name: str = Field(
        ...,
        description="Riot ID game name"
    )

    tag_line: str = Field(
        ...,
        description="Riot ID tag line"
    )

    summoner_id: str | None = Field(
        None,
        description="Summoner ID for the region"
    )

    account_id: str | None = Field(
        None,
        description="Account ID"
    )

    profile_icon_id: int | None = Field(
        None,
        description="Profile icon ID"
    )

    summoner_level: int | None = Field(
        None,
        description="Summoner level"
    )