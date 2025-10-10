"""Analysis result contracts for P4 phase.

Defines the structured data contract between CLI 2 (Backend) and CLI 1 (Frontend)
for delivering final match analysis results.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class V1ScoreSummary(BaseModel):
    """V1 scoring algorithm output summary (expanded to 10 dimensions).

    Ten-dimensional performance metrics from the V1 scoring algorithm.
    """

    # Original 5 core dimensions
    combat_score: float = Field(description="Combat performance score (0-100)", ge=0, le=100)
    economy_score: float = Field(description="Economy/farming score (0-100)", ge=0, le=100)
    vision_score: float = Field(description="Vision control score (0-100)", ge=0, le=100)
    objective_score: float = Field(description="Objective control score (0-100)", ge=0, le=100)
    teamplay_score: float = Field(description="Teamplay/cooperation score (0-100)", ge=0, le=100)

    # New 5 extended dimensions
    growth_score: float = Field(description="Growth curve score (0-100)", ge=0, le=100)
    tankiness_score: float = Field(description="Tankiness/frontline score (0-100)", ge=0, le=100)
    damage_composition_score: float = Field(
        description="Damage composition score (0-100)", ge=0, le=100
    )
    survivability_score: float = Field(description="Survivability score (0-100)", ge=0, le=100)
    cc_contribution_score: float = Field(description="CC contribution score (0-100)", ge=0, le=100)

    # Overall weighted score
    overall_score: float = Field(description="Weighted overall score (0-100)", ge=0, le=100)

    # Raw stats for static display
    raw_stats: dict[str, Any] = Field(
        default_factory=dict, description="Raw performance metrics for detailed display"
    )


class FinalAnalysisReport(BaseModel):
    """Final analysis report delivered by CLI 2 to CLI 1.

    This is the complete data contract for rendering the final Discord embed.
    """

    # Core match metadata
    match_id: str = Field(description="Match ID in Match-V5 format")
    match_result: Literal["victory", "defeat"] = Field(
        description="Match outcome for the analyzed player"
    )

    # Player information
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion name (e.g., 'Yasuo')")
    champion_id: int = Field(description="Champion ID for DDragon assets")

    # AI narrative (LLM-generated)
    ai_narrative_text: str = Field(
        description="LLM-generated match review narrative (max 1900 chars)",
        max_length=1900,
    )
    llm_sentiment_tag: Literal["激动", "遗憾", "嘲讽", "鼓励", "平淡"] = Field(
        description="Emotion tag for TTS voice modulation"
    )

    # V1 Scoring results
    v1_score_summary: V1ScoreSummary = Field(
        description="Five-dimensional performance scores from V1 algorithm"
    )

    # Visual assets
    champion_assets_url: str = Field(
        description="DDragon champion icon/splash art URL for embed thumbnail"
    )

    builds_summary_text: str | None = Field(
        default=None,
        max_length=600,
        description="Compact build & rune summary appended to the embed",
    )
    builds_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Structured build/rune payload (items, diff, visuals, etc.)",
    )

    # Performance metadata
    processing_duration_ms: float = Field(description="Total task execution time in milliseconds")
    algorithm_version: str = Field(default="v1", description="Scoring algorithm version identifier")

    # Observability: Optional Celery task id for traceability
    trace_task_id: str | None = Field(default=None, description="Celery task UUID")

    # Optional TTS audio
    tts_audio_url: str | None = Field(
        default=None, description="Optional TTS audio file URL (if generated)"
    )


class AnalysisErrorReport(BaseModel):
    """Error report when analysis fails.

    Delivered by CLI 2 to CLI 1 when task encounters unrecoverable errors.
    """

    match_id: str = Field(description="Match ID that failed analysis")
    error_type: str = Field(description="Error classification (e.g., 'RIOT_API_ERROR')")
    error_message: str = Field(
        description="Human-readable error description (max 500 chars)", max_length=500
    )
    retry_suggested: bool = Field(
        default=True, description="Whether user should retry the analysis"
    )
