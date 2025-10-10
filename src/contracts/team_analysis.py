"""V2 Team Analysis contracts (Frontend <-> Backend).

Defines compact, strictly-typed models for team-level reports rendered
by the /team-analysis command. These are Pydantic v2 models and should
pass strict MyPy checks when used with `from __future__ import annotations`.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


class TeamPlayerEntry(BaseModel):
    """Minimal player entry for team report."""

    puuid: str = Field(min_length=32, description="Riot PUUID (78 chars typical)")
    summoner_name: str = Field(description="Player game name with tag if available")
    champion_name: str = Field(description="Champion played")
    role: Role = Field(description="Position/role in team")

    # Core V1 metrics (0-100)
    combat_score: float = Field(ge=0, le=100)
    economy_score: float = Field(ge=0, le=100)
    vision_score: float = Field(ge=0, le=100)
    objective_score: float = Field(ge=0, le=100)
    teamplay_score: float = Field(ge=0, le=100)
    overall_score: float = Field(ge=0, le=100)
    survivability_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional survivability dimension (if available)",
    )
    team_rank: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Rank within friendly team (1=best) when available",
    )
    champion_icon_url: HttpUrl | None = Field(
        default=None, description="Champion icon asset for thumbnail rendering"
    )


class TeamAggregates(BaseModel):
    """Aggregated summary statistics for the team."""

    combat_avg: float
    economy_avg: float
    vision_avg: float
    objective_avg: float
    teamplay_avg: float
    overall_avg: float


class TeamAnalysisReport(BaseModel):
    """Top-level V2 team report contract."""

    match_id: str = Field(description="Match-V5 ID")
    team_result: Literal["victory", "defeat"]
    team_region: str = Field(min_length=2, description="Platform region code (e.g., na1)")

    # V2.3: Add game mode for correct card labeling in V1 overview
    game_mode: Literal["summoners_rift", "aram", "arena", "unknown"] = Field(
        default="summoners_rift", description="Detected game mode for this match"
    )

    players: list[TeamPlayerEntry] = Field(min_length=5, max_length=5)
    aggregates: TeamAggregates

    # Optional narrative or highlights (backend-provided)
    summary_text: str | None = Field(default=None, max_length=1900)
    builds_summary_text: str | None = Field(
        default=None,
        max_length=600,
        description="Compact build & rune summary (<=600 chars) for Embed field",
    )
    builds_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Structured build/rune payload (items, runes, overlap metrics)",
    )
    tts_audio_url: str | None = Field(
        default=None,
        description="Optional TTS audio file URL exposed to Discord voice controls",
    )
    target_player_name: str = Field(
        default="-", description="Display name of the primary player under analysis"
    )
    target_player_puuid: str | None = Field(
        default=None, description="PUUID of the primary player under analysis"
    )

    class DimensionHighlight(BaseModel):
        dimension: str = Field(description="Internal dimension key (e.g., combat_efficiency)")
        label: str = Field(description="Human readable label (e.g., 战斗效率)")
        score: float = Field(description="Dimension score for the target player")
        delta_vs_team: float | None = Field(
            default=None,
            description="Difference vs friendly team average (positive means better)",
        )
        delta_vs_opponent: float | None = Field(
            default=None,
            description="Difference vs opposing matchup when available",
        )

    strengths: list[DimensionHighlight] = Field(
        default_factory=list,
        description="Top strengths for target player (sorted descending by impact)",
    )
    weaknesses: list[DimensionHighlight] = Field(
        default_factory=list,
        description="Top weaknesses for target player (sorted ascending by impact)",
    )

    class EnhancementMetrics(BaseModel):
        gold_diff_10: int | None = Field(
            default=None, description="Gold difference at 10 minutes (friendly - enemy)"
        )
        xp_diff_10: int | None = Field(
            default=None, description="XP difference at 10 minutes (friendly - enemy)"
        )
        conversion_rate: float | None = Field(
            default=None,
            description="Kill-to-objective conversion rate within 120s windows (0-1)",
        )
        ward_rate_per_min: float | None = Field(
            default=None, description="Wards placed per minute (including control wards)"
        )

    enhancements: EnhancementMetrics | None = Field(
        default=None, description="Timeline-derived enhancement metrics"
    )

    class ObservabilitySnapshot(BaseModel):
        session_id: str = Field(description="Session identifier for tracing")
        execution_branch_id: str = Field(description="Execution branch identifier")
        fetch_ms: float | None = Field(default=None, description="Timeline fetch duration (ms)")
        scoring_ms: float | None = Field(default=None, description="Scoring duration (ms)")
        llm_ms: float | None = Field(default=None, description="LLM inference duration (ms)")
        webhook_ms: float | None = Field(default=None, description="Webhook delivery duration (ms)")
        overall_ms: float | None = Field(default=None, description="End-to-end duration (ms)")

    observability: ObservabilitySnapshot | None = Field(
        default=None, description="Observability snapshot for footer telemetry"
    )

    # Arena-specific optional context (for Duo receipt rendering)
    class ArenaDuo(BaseModel):
        me_name: str
        me_champion: str
        partner_name: str | None = None
        partner_champion: str | None = None
        placement: int | None = None

    arena_duo: ArenaDuo | None = Field(
        default=None, description="Arena duo context for specialized view"
    )
    arena_rounds_block: str | None = Field(
        default=None, description="Arena rounds summary block for overview"
    )

    # Observability: carry Celery task id for traceability (optional)
    trace_task_id: str | None = Field(default=None, description="Celery task UUID for tracing")
