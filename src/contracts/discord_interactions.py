"""
Data contracts for Discord interactions and commands.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InteractionType(str, Enum):
    """Discord interaction types."""

    PING = "ping"
    SLASH_COMMAND = "slash_command"
    BUTTON = "button"
    SELECT_MENU = "select_menu"
    MODAL_SUBMIT = "modal_submit"


class CommandName(str, Enum):
    """Available slash commands."""

    BIND = "bind"
    UNBIND = "unbind"
    PROFILE = "profile"
    ANALYZE = "analyze"  # V1: Single-player analysis (/讲道理)
    TEAM_ANALYZE = "team-analyze"  # V2: Team-relative analysis (5-player comparison)
    SETTINGS = "settings"  # V2.2: User preference configuration
    TRASH_TALK = "trash_talk"  # Future: /垃圾话模式 command


class EmbedColor(int, Enum):
    """Discord embed colors for different states."""

    INFO = 0x3498DB  # Blue
    SUCCESS = 0x2ECC71  # Green
    WARNING = 0xF39C12  # Orange
    ERROR = 0xE74C3C  # Red
    PROCESSING = 0x9B59B6  # Purple


class InteractionResponse(BaseModel):
    """Standard response for Discord interactions."""

    success: bool = Field(..., description="Whether the interaction was successful")

    ephemeral: bool = Field(True, description="Whether response should be visible only to user")

    embed_title: str = Field(..., description="Title for Discord embed")

    embed_description: str = Field(..., description="Description for Discord embed")

    embed_color: int = Field(EmbedColor.INFO, description="Color for Discord embed")

    embed_fields: list[dict[str, Any]] = Field(
        default_factory=list, description="Additional fields for embed"
    )

    embed_footer: str | None = Field(None, description="Footer text for embed")

    embed_thumbnail_url: str | None = Field(None, description="Thumbnail URL for embed")

    buttons: list[dict[str, Any]] = Field(
        default_factory=list, description="Interactive buttons to add"
    )

    should_defer: bool = Field(
        False, description="Whether to defer the response (for long operations)"
    )


class BindCommandOptions(BaseModel):
    """Options for /bind command."""

    region: str | None = Field(
        None,
        description="Preferred region for account binding",
        pattern=r"^(br1|eun1|euw1|jp1|kr|la1|la2|na1|oc1|ph2|ru|sg2|th2|tr1|tw2|vn2)$",
    )

    force_rebind: bool = Field(False, description="Force rebinding even if already bound")


class DeferredTask(BaseModel):
    """Model for deferred tasks sent to backend."""

    task_id: str = Field(..., description="Unique task identifier")

    task_type: str = Field(..., description="Type of task (e.g., 'match_analysis')")

    interaction_token: str = Field(..., description="Discord interaction token for follow-up")

    discord_id: str = Field(..., description="Discord user ID")

    channel_id: str = Field(..., description="Discord channel ID")

    guild_id: str | None = Field(None, description="Discord guild ID if applicable")

    payload: dict[str, Any] = Field(default_factory=dict, description="Task-specific payload")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Task creation timestamp"
    )

    expires_at: datetime | None = Field(None, description="Task expiration timestamp")
