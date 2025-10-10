"""Pydantic contracts for V1 Scoring Algorithm.

These contracts define the input/output structure for the scoring algorithm.
They serve as the interface between CLI 2 (task orchestration) and CLI 4 (algorithm implementation).
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class VisionScore(BaseModel):
    """Vision-related scoring metrics."""

    ward_score: float = Field(
        ge=0.0, le=100.0, description="Score based on wards placed and destroyed"
    )
    vision_denial_score: float = Field(
        ge=0.0, le=100.0, description="Score for enemy vision denial"
    )
    control_ward_score: float = Field(ge=0.0, le=100.0, description="Control ward effectiveness")
    overall_vision_score: float = Field(
        ge=0.0, le=100.0, description="Weighted combination of vision metrics"
    )


class TeamFightScore(BaseModel):
    """Team fight participation and impact scoring."""

    participation_rate: float = Field(ge=0.0, le=1.0, description="Kill participation rate")
    damage_share: float = Field(
        ge=0.0, le=1.0, description="Share of team's total damage in fights"
    )
    survival_rate: float = Field(ge=0.0, le=1.0, description="Survival rate in team fights")
    positioning_score: float = Field(
        ge=0.0, le=100.0, description="Quality of positioning during fights"
    )
    overall_teamfight_score: float = Field(
        ge=0.0, le=100.0, description="Weighted teamfight contribution"
    )


class PlayerPerformanceScore(BaseModel):
    """Individual player performance scoring."""

    puuid: str = Field(min_length=78, max_length=78, description="Player PUUID")
    summoner_name: str = Field(max_length=255, description="Summoner name at time of match")

    # Core performance metrics
    cs_score: float = Field(ge=0.0, le=100.0, description="Creep score efficiency")
    gold_efficiency: float = Field(ge=0.0, le=100.0, description="Gold generation efficiency")
    kda_score: float = Field(ge=0.0, le=100.0, description="KDA-based performance score")

    # Advanced metrics
    vision_score: VisionScore = Field(description="Vision-related metrics")
    teamfight_score: TeamFightScore = Field(description="Team fight contribution")

    # Aggregated score
    overall_score: float = Field(ge=0.0, le=100.0, description="Weighted overall performance score")

    # Metadata
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of score calculation"
    )


class MatchScoreResult(BaseModel):
    """Output contract for V1 Scoring Algorithm.

    This structure will be stored as JSONB in PostgreSQL's match_analytics table.
    It serves as the input for LLM analysis in P4.
    """

    match_id: str = Field(min_length=1, description="Match identifier")
    algorithm_version: str = Field(default="v1", description="Algorithm version identifier")

    # Player scores (all 10 players)
    player_scores: list[PlayerPerformanceScore] = Field(
        min_length=10, max_length=10, description="Individual player performance scores"
    )

    # Match-level insights (for future LLM context)
    match_insights: dict[str, str | float | int] = Field(
        default_factory=dict,
        description="Match-level insights (e.g., 'game_pace': 'fast', 'snowball_factor': 0.8)",
    )

    # Metadata
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when scores were calculated",
    )
    processing_duration_ms: float | None = Field(
        default=None, description="Time taken to calculate scores (milliseconds)"
    )


# Example structure for future reference
EXAMPLE_MATCH_SCORE_RESULT = {
    "match_id": "NA1_1234567890",
    "algorithm_version": "v1",
    "player_scores": [
        {
            "puuid": "a" * 78,
            "summoner_name": "ExamplePlayer",
            "cs_score": 85.5,
            "gold_efficiency": 78.2,
            "kda_score": 92.0,
            "vision_score": {
                "ward_score": 70.0,
                "vision_denial_score": 60.0,
                "control_ward_score": 80.0,
                "overall_vision_score": 68.5,
            },
            "teamfight_score": {
                "participation_rate": 0.75,
                "damage_share": 0.28,
                "survival_rate": 0.80,
                "positioning_score": 82.0,
                "overall_teamfight_score": 78.5,
            },
            "overall_score": 82.3,
            "calculated_at": "2025-10-05T12:00:00Z",
        }
        # ... 9 more players
    ],
    "match_insights": {
        "game_pace": "fast",
        "snowball_factor": 0.75,
        "average_vision_score": 65.2,
    },
    "calculated_at": "2025-10-05T12:00:05Z",
    "processing_duration_ms": 125.8,
}
