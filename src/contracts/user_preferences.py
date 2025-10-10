"""User preferences contract for personalization features.

This module defines data structures for user preference updates,
primarily used for the /settings command and modal interactions.

Note: For complete V2.2 user profile functionality, see v22_user_profile.py
"""

from typing import Literal

from pydantic import BaseModel, Field


class PreferenceUpdateRequest(BaseModel):
    """Request payload for updating user preferences via /settings modal.

    All fields are optional - only provided fields will be updated.
    Empty/None fields indicate no change to existing preference.
    """

    main_role: Literal["top", "jungle", "mid", "bot", "support", "fill"] | None = Field(
        default=None,
        description="Primary role preference",
    )

    secondary_role: Literal["top", "jungle", "mid", "bot", "support", "fill"] | None = Field(
        default=None,
        description="Secondary role preference",
    )

    analysis_tone: Literal["competitive", "casual", "balanced"] | None = Field(
        default=None,
        description="Preferred analysis tone",
    )

    advice_detail_level: Literal["concise", "detailed"] | None = Field(
        default=None,
        description="Preferred detail level for suggestions",
    )

    show_timeline_references: bool | None = Field(
        default=None,
        description="Whether to show timeline references in analysis",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "main_role": "jungle",
                "analysis_tone": "competitive",
                "advice_detail_level": "detailed",
                "show_timeline_references": True,
            }
        }
