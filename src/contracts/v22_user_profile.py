"""V2.2 User Profile Data Contracts.

Engineering delivery for V2.2 personalization feature.
Defines structured data contracts for user profiles, preferences, and personalization logic.

Author: CLI 4 (The Lab)
Date: 2025-10-06
Research Foundation: notebooks/v2.2_personalization.ipynb
Status: ✅ Production Ready

Design Principles:
- User-Centric: Combines explicit preferences (/settings) with implicit patterns
- Privacy-Aware: Only stores aggregated stats, never raw match details
- Incremental Updates: Profile updated after each new match analysis
- Backward Compatible: All fields have sensible defaults for new users
"""

from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# User Preference Contracts (Explicit Configuration via /settings)
# =============================================================================


class V22UserPreferences(BaseModel):
    """User's explicit preferences configured via /settings command.

    These preferences are directly controlled by the user and override
    any inferred behaviors from historical data.
    """

    # Analysis customization
    preferred_analysis_tone: Literal["competitive", "casual"] = Field(
        default="casual",
        description=(
            "User's preferred analysis tone. "
            "'competitive': Concise, data-heavy, critical feedback. "
            "'casual': Friendly, explanatory, encouraging tone."
        ),
    )

    preferred_role: Literal["Top", "Jungle", "Mid", "ADC", "Support", "Fill"] | None = Field(
        default=None,
        description=(
            "User's primary role preference. "
            "If set, enables role-specific suggestions. "
            "If None, inferred from match history."
        ),
    )

    # Notification preferences (future V2.3+)
    enable_tts: bool = Field(
        default=False,
        description="Enable text-to-speech for analysis reports (V2.3+)",
    )

    # Privacy preferences
    allow_historical_analysis: bool = Field(
        default=True,
        description=(
            "Allow bot to use historical match data for personalization. "
            "If False, only current match data is used."
        ),
    )


# =============================================================================
# User Profile Contracts (Inferred from Historical Data)
# =============================================================================


class V22PerformanceTrends(BaseModel):
    """User's performance trends calculated from recent matches.

    All statistics are calculated from the last 20 matches where
    the user received a V1 analysis.
    """

    # Dimension averages (V1 scoring)
    avg_combat_score: float = Field(
        description="Average Combat dimension score (0-100)", ge=0, le=100
    )
    avg_economy_score: float = Field(
        description="Average Economy dimension score (0-100)", ge=0, le=100
    )
    avg_vision_score: float = Field(
        description="Average Vision dimension score (0-100)", ge=0, le=100
    )
    avg_objective_control_score: float = Field(
        description="Average Objective Control dimension score (0-100)", ge=0, le=100
    )
    avg_teamplay_score: float = Field(
        description="Average Teamplay dimension score (0-100)", ge=0, le=100
    )

    # Persistent weakness identification
    persistent_weak_dimension: (
        Literal["Combat", "Economy", "Vision", "Objective Control", "Teamplay"] | None
    ) = Field(
        default=None,
        description=(
            "Dimension where user scored below team average in ≥70% of recent matches. "
            "Used to prioritize suggestions in V2.2 analysis. "
            "None if no dimension meets the threshold."
        ),
    )

    weak_dimension_frequency: float | None = Field(
        default=None,
        description=(
            "Percentage of matches where user scored below team average "
            "in persistent_weak_dimension (0.0-1.0). "
            "None if persistent_weak_dimension is None."
        ),
        ge=0.0,
        le=1.0,
    )

    # Win rate context
    recent_win_rate: float = Field(
        description="Win rate in last 20 matches (0.0-1.0)", ge=0.0, le=1.0
    )


class V22ChampionProfile(BaseModel):
    """User's champion mastery and role patterns."""

    # Top played champions
    top_3_champions: list[str] = Field(
        default_factory=list,
        description="User's 3 most-played champions in last 20 matches",
        max_length=3,
    )

    champion_play_counts: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Play count for each champion in last 20 matches. "
            "Example: {'Jinx': 5, 'Caitlyn': 3, 'Kai'Sa': 2}"
        ),
    )

    # Role distribution
    role_distribution: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Play count for each role in last 20 matches. "
            "Example: {'ADC': 12, 'Mid': 5, 'Support': 3}"
        ),
    )

    inferred_primary_role: Literal["Top", "Jungle", "Mid", "ADC", "Support", "Fill"] | None = Field(
        default=None,
        description=(
            "Inferred primary role (≥40% of recent matches). "
            "None if no role meets threshold (Fill player)."
        ),
    )


class V22UserClassification(BaseModel):
    """User classification for tone and complexity customization."""

    skill_level: Literal["beginner", "intermediate", "advanced"] = Field(
        default="intermediate",
        description=(
            "Inferred skill level based on ranked tier: "
            "Iron/Bronze = beginner, "
            "Silver/Gold = intermediate, "
            "Platinum+ = advanced"
        ),
    )

    player_type: Literal["casual", "competitive"] = Field(
        default="casual",
        description=(
            "Inferred player type based on match frequency and ranked tier: "
            "≥5 ranked matches/week + Gold+ tier = competitive, "
            "otherwise casual"
        ),
    )

    ranked_tier: str | None = Field(
        default=None,
        description=(
            "User's current ranked tier from Riot API. "
            "Example: 'GOLD', 'PLATINUM', 'IRON'. "
            "None if unranked or data unavailable."
        ),
    )

    matches_per_week: float = Field(
        default=0.0,
        description="Average ranked matches played per week (last 4 weeks)",
        ge=0.0,
    )


# =============================================================================
# Complete User Profile Contract
# =============================================================================


class V22UserProfile(BaseModel):
    """Complete V2.2 user profile for personalization.

    This profile combines:
    1. Explicit preferences (configured via /settings)
    2. Performance trends (calculated from match history)
    3. Champion/role patterns (inferred from play history)
    4. User classification (for tone customization)

    The profile is incrementally updated after each match analysis
    and persisted in the database.
    """

    # User identification
    discord_user_id: str = Field(description="Discord user ID")
    puuid: str = Field(description="Riot PUUID")

    # Explicit preferences (user-controlled)
    preferences: V22UserPreferences = Field(
        default_factory=V22UserPreferences,
        description="User's explicit preferences from /settings command",
    )

    # Inferred performance trends
    performance_trends: V22PerformanceTrends | None = Field(
        default=None,
        description=(
            "Performance trends calculated from last 20 matches. "
            "None if user has <5 analyzed matches (insufficient data)."
        ),
    )

    # Champion and role patterns
    champion_profile: V22ChampionProfile = Field(
        default_factory=V22ChampionProfile,
        description="User's champion mastery and role distribution",
    )

    # User classification
    classification: V22UserClassification = Field(
        default_factory=V22UserClassification,
        description="User classification for tone customization",
    )

    # Metadata
    total_matches_analyzed: int = Field(
        default=0, description="Total matches analyzed for this user", ge=0
    )

    last_updated: str = Field(description="Profile last update timestamp (ISO 8601 format)")

    profile_version: str = Field(
        default="v2.2",
        description="Profile schema version (for migration tracking)",
    )


# =============================================================================
# Profile Update Event Contract
# =============================================================================


class V22ProfileUpdateEvent(BaseModel):
    """Event triggered after a new match analysis to update user profile.

    CLI 2's UserProfileService listens to this event and incrementally
    updates the user's profile.
    """

    discord_user_id: str = Field(description="Discord user ID")
    puuid: str = Field(description="Riot PUUID")

    # New match data
    match_id: str = Field(description="Match ID that triggered this update")
    match_result: Literal["victory", "defeat"] = Field(description="Match outcome")
    played_role: str = Field(description="Role played in this match")
    played_champion: str = Field(description="Champion played in this match")

    # V1 dimension scores from this match
    dimension_scores: dict[str, float] = Field(
        description=(
            "V1 dimension scores from this match. "
            "Keys: 'Combat', 'Economy', 'Vision', 'Objective Control', 'Teamplay'"
        )
    )

    team_avg_scores: dict[str, float] = Field(description="Team average scores for comparison")

    # Timestamp
    analyzed_at: str = Field(description="Match analysis timestamp (ISO 8601 format)")


# =============================================================================
# Example Data (for Documentation & Testing)
# =============================================================================

EXAMPLE_V22_USER_PROFILE = V22UserProfile(
    discord_user_id="123456789",
    puuid="test-puuid-abc123",
    preferences=V22UserPreferences(
        preferred_analysis_tone="competitive",
        preferred_role="Jungle",
        enable_tts=False,
        allow_historical_analysis=True,
    ),
    performance_trends=V22PerformanceTrends(
        avg_combat_score=78.5,
        avg_economy_score=82.3,
        avg_vision_score=45.2,
        avg_objective_control_score=71.8,
        avg_teamplay_score=68.9,
        persistent_weak_dimension="Vision",
        weak_dimension_frequency=0.75,
        recent_win_rate=0.52,
    ),
    champion_profile=V22ChampionProfile(
        top_3_champions=["Lee Sin", "Graves", "Kha'Zix"],
        champion_play_counts={"Lee Sin": 7, "Graves": 5, "Kha'Zix": 4},
        role_distribution={"Jungle": 18, "Mid": 2},
        inferred_primary_role="Jungle",
    ),
    classification=V22UserClassification(
        skill_level="intermediate",
        player_type="competitive",
        ranked_tier="GOLD",
        matches_per_week=6.5,
    ),
    total_matches_analyzed=23,
    last_updated="2025-10-06T15:30:00Z",
    profile_version="v2.2",
)
