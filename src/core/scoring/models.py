"""Scoring data models with strict type safety.

SOLID: Single Responsibility - Data structures only, no business logic.
"""

from typing import Any

from pydantic import BaseModel, Field


class PlayerScore(BaseModel):
    """Structured player performance score with validation."""

    participant_id: int = Field(..., ge=1, le=16)  # Support Arena (2v2v2v2)
    total_score: float = Field(..., ge=0, le=100)

    # Core dimension scores (0-100 scale) - Original 5
    combat_efficiency: float = Field(..., ge=0, le=100)
    economic_management: float = Field(..., ge=0, le=100)
    objective_control: float = Field(..., ge=0, le=100)
    vision_control: float = Field(..., ge=0, le=100)
    team_contribution: float = Field(..., ge=0, le=100)

    # Extended dimension scores (0-100 scale) - New 5
    growth_score: float = Field(..., ge=0, le=100)  # 成长曲线: Level/XP advantage
    tankiness_score: float = Field(..., ge=0, le=100)  # 坦度: Damage taken ratio
    damage_composition_score: float = Field(..., ge=0, le=100)  # 伤害构成: Damage diversity
    survivability_score: float = Field(..., ge=0, le=100)  # 生存质量: Death quality
    cc_contribution_score: float = Field(..., ge=0, le=100)  # 控制贡献: CC duration

    # Raw metrics for LLM context
    kda: float = Field(..., ge=0)
    cs_per_min: float = Field(..., ge=0)
    gold_difference: float
    kill_participation: float = Field(..., ge=0, le=100)

    # Raw stats for static Discord display (all available metrics)
    raw_stats: dict[str, Any] = Field(default_factory=dict)

    # LLM integration metadata
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    emotion_tag: str = Field(default="neutral")


class MatchAnalysisOutput(BaseModel):
    """Structured match analysis for LLM consumption."""

    match_id: str
    game_duration_minutes: float = Field(..., gt=0)
    player_scores: list[PlayerScore]
    mvp_id: int = Field(..., ge=1, le=10)
    team_blue_avg_score: float = Field(..., ge=0, le=100)
    team_red_avg_score: float = Field(..., ge=0, le=100)
