"""Contracts for /讲道理 (Analysis) async task system.

These contracts define the interface between CLI 1 (Discord Bot) and CLI 2 (Backend)
for the atomic match analysis workflow.

DRY: To avoid duplicate definitions, the payload contract is centralized in
`src/contracts/tasks.py`. This module re-exports it for backward compatibility
with existing imports.
"""

from pydantic import BaseModel, Field

# Re-export the canonical payload definition to maintain a single source of truth
from .tasks import AnalysisTaskPayload

__all__ = ["AnalysisTaskPayload", "AnalysisTaskResult"]


class AnalysisTaskResult(BaseModel):
    """Result returned by analyze_match_task."""

    success: bool = Field(description="Whether task completed successfully")
    match_id: str = Field(description="Match ID that was analyzed")

    # Data locations (for verification)
    score_data_saved: bool = Field(default=False, description="Whether score data was saved")
    timeline_cached: bool = Field(default=False, description="Whether timeline was cached")

    # Performance metrics
    # P4: Webhook delivery status
    webhook_delivered: bool = Field(
        default=False, description="Whether Discord webhook was successfully delivered"
    )

    # Performance metrics (for observability)
    fetch_duration_ms: float | None = Field(default=None, description="Time to fetch MatchTimeline")
    scoring_duration_ms: float | None = Field(default=None, description="Time to compute scores")
    save_duration_ms: float | None = Field(default=None, description="Time to save results")
    llm_duration_ms: float | None = Field(
        default=None, description="Time for LLM narrative generation (P4)"
    )
    tts_duration_ms: float | None = Field(
        default=None, description="Time for TTS voice synthesis (P5)"
    )
    webhook_duration_ms: float | None = Field(
        default=None, description="Time for Discord webhook delivery (P4)"
    )
    total_duration_ms: float | None = Field(default=None, description="Total task duration")

    # Error handling
    error_message: str | None = Field(default=None, description="Error message if failed")
    error_stage: str | None = Field(
        default=None, description="Stage where error occurred (fetch/score/save/llm/webhook)"
    )


# Example payload structure for documentation
EXAMPLE_ANALYSIS_PAYLOAD = {
    "application_id": "123456789012345678",
    "interaction_token": "discord_webhook_token_here",
    "channel_id": "123456789012345678",
    "guild_id": "987654321098765432",
    "discord_user_id": "123456789012345678",
    "puuid": "a" * 78,
    "match_id": "NA1_1234567890",
    "region": "americas",
    "match_index": 1,
}
