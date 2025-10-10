"""Task payload contracts for async job queue (Celery).

This module defines Pydantic models for task payloads that will be
serialized and sent to the Celery task queue for background processing.
"""

from pydantic import BaseModel, Field


class AnalysisTaskPayload(BaseModel):
    """Payload for match analysis task sent to Celery queue.

    This contract ensures type-safe task distribution between CLI 1 (Frontend)
    and CLI 2 (Backend). All fields are required to maintain data integrity.
    """

    # Discord interaction context for async response
    application_id: str = Field(description="Discord application ID for webhook URL construction")
    interaction_token: str = Field(
        description="Discord interaction token (15min validity) for editing original response"
    )
    channel_id: str = Field(description="Discord channel ID where command was invoked")

    # User identity
    discord_user_id: str = Field(description="Discord user ID who invoked the command")
    puuid: str = Field(description="Riot's persistent, globally unique ID for the player")

    # Match context
    match_id: str = Field(
        description="Target match ID to analyze (Match-V5 format: REGION_MATCH_ID)"
    )
    region: str = Field(
        description="Regional routing value for Riot API calls (e.g., 'americas', 'asia')"
    )

    # Optional metadata
    match_index: int = Field(
        default=1, description="Index in user's match history (1-based, for display)"
    )

    # Observability
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID propagated from Discord entrypoint for end-to-end tracing",
    )


class TeamAnalysisTaskPayload(BaseModel):
    """Payload for V2 team analysis task sent to Celery queue.

    This extends the single-player analysis to include team-relative comparisons
    for all 5 players on the user's team.
    """

    # Discord interaction context for async response
    application_id: str = Field(description="Discord application ID for webhook URL construction")
    interaction_token: str = Field(
        description="Discord interaction token (15min validity) for editing original response"
    )
    channel_id: str = Field(description="Discord channel ID where command was invoked")
    guild_id: str | None = Field(default=None, description="Discord guild ID (for voice auto-play)")

    # User identity
    discord_user_id: str = Field(description="Discord user ID who invoked the command")
    puuid: str = Field(description="Riot's persistent, globally unique ID for the player")

    # Match context
    match_id: str = Field(
        description="Target match ID to analyze (Match-V5 format: REGION_MATCH_ID)"
    )
    region: str = Field(
        description="Regional routing value for Riot API calls (e.g., 'americas', 'asia')"
    )

    # Optional metadata
    match_index: int = Field(
        default=1, description="Index in user's match history (1-based, for display)"
    )

    # Observability
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID propagated from Discord entrypoint for end-to-end tracing",
    )


# Task name constants (shared contract between CLI 1 and CLI 2)
TASK_ANALYZE_MATCH = "src.tasks.analysis_tasks.analyze_match_task"
"""Celery task name for match analysis job (fully-qualified)."""

TASK_ANALYZE_TEAM = "src.tasks.team_tasks.analyze_team_task"
"""Celery task name for V2 team analysis job (fully-qualified)."""
