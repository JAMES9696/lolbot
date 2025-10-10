"""V2 Team Analysis Data Contracts.

Defines the data contracts between CLI components for V2 team-relative analysis:
- CLI 4 (Lab): Defines data requirements and output formats
- CLI 2 (Backend): Implements data fetching and processing
- CLI 1 (Frontend): Renders Discord Embed views

Architecture:
- V2TeamAnalysisInput: Data requirements for multi-player analysis
- V2PlayerAnalysisResult: Individual player analysis result
- V2TeamAnalysisReport: Complete team analysis report (for Discord Embed)
- ABTestingMetadata: A/B experiment tracking metadata
"""

from typing import Literal

from pydantic import BaseModel, Field


class V2PlayerScoreData(BaseModel):
    """Individual player's V1 score data for team analysis.

    This is a subset of the full V1ScoreSummary, containing only
    the fields needed for team-relative comparisons.
    """

    puuid: str = Field(description="Player's PUUID (Riot unique identifier)")
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion name")
    champion_id: int = Field(description="Champion ID for assets")
    position: int = Field(description="Team position (0-4)", ge=0, le=4)

    # V1 Five-dimensional scores
    combat_score: float = Field(description="Combat performance (0-100)", ge=0, le=100)
    economy_score: float = Field(description="Economy/farming (0-100)", ge=0, le=100)
    vision_score: float = Field(description="Vision control (0-100)", ge=0, le=100)
    objective_score: float = Field(description="Objective control (0-100)", ge=0, le=100)
    teamplay_score: float = Field(description="Teamplay/cooperation (0-100)", ge=0, le=100)
    overall_score: float = Field(description="Weighted overall (0-100)", ge=0, le=100)


class V2TeamAnalysisInput(BaseModel):
    """Input data requirements for V2 team analysis.

    This contract defines what CLI 2 must fetch and provide to the
    team analysis engine for processing.
    """

    # Match metadata
    match_id: str = Field(description="Match ID in Match-V5 format")
    match_result: Literal["victory", "defeat"] = Field(
        description="Match outcome for the analyzed team"
    )

    # Target player (user who requested analysis)
    target_player_index: int = Field(
        description="Index of target player in team_players list (0-4)", ge=0, le=4
    )

    # All 5 team members' score data
    team_players: list[V2PlayerScoreData] = Field(
        description="Score data for all 5 team members (must be exactly 5 players)",
        min_length=5,
        max_length=5,
    )

    # A/B testing metadata
    discord_user_id: str = Field(description="Discord user ID for A/B cohort assignment")
    ab_cohort: Literal["A", "B"] | None = Field(
        default=None, description="Assigned A/B cohort (None if A/B testing disabled)"
    )
    variant_id: str | None = Field(
        default=None, description="Prompt variant identifier (e.g., 'v2_team_summary_20251006')"
    )


class V2PlayerAnalysisResult(BaseModel):
    """Individual player's analysis result in V2 team context.

    This compact format is suitable for Discord Embed rendering
    showing multiple players in a single message.
    """

    puuid: str = Field(description="Player's PUUID")
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion name")
    champion_icon_url: str = Field(description="Champion icon URL for embed")

    # Core performance metrics (for compact display)
    overall_score: float = Field(description="Overall score (0-100)", ge=0, le=100)
    team_rank: int = Field(description="Rank within team (1-5, 1=best)", ge=1, le=5)

    # Top strength and weakness (1 each for compact display)
    top_strength_dimension: str = Field(
        description="Highest-scoring dimension name (e.g., 'Combat')"
    )
    top_strength_score: float = Field(description="Score for top strength (0-100)")
    top_strength_team_rank: int = Field(description="Team rank for top strength (1-5)")

    top_weakness_dimension: str = Field(
        description="Lowest-scoring dimension name (e.g., 'Vision')"
    )
    top_weakness_score: float = Field(description="Score for top weakness (0-100)")
    top_weakness_team_rank: int = Field(description="Team rank for top weakness (1-5)")

    # AI narrative (condensed for multi-player view)
    narrative_summary: str = Field(
        description="Condensed narrative summary (max 150 chars for compact embed)",
        max_length=150,
    )


class V2TeamAnalysisReport(BaseModel):
    """Complete V2 team analysis report for Discord Embed rendering.

    This contract defines the final output format that CLI 1 will use
    to render the /team-analysis command response.

    Design Constraints:
    - Discord Embed field limit: 25 fields max
    - Compact layout for 5 players: ~5 fields per player
    - Paginated view support (optional): Multiple embeds for detailed view

    V2.3 Enhancement: Mode-aware rendering support for ARAM, Arena, and SR.
    """

    # Match metadata
    match_id: str = Field(description="Match ID")
    match_result: Literal["victory", "defeat"] = Field(description="Match outcome")
    game_mode: Literal["summoners_rift", "aram", "arena", "unknown"] = Field(
        default="summoners_rift",
        description=(
            "Game mode identifier for mode-aware UI rendering. "
            "'summoners_rift': 5v5 Ranked/Normal, "
            "'aram': ARAM (Howling Abyss), "
            "'arena': 2v2v2v2 Arena mode, "
            "'unknown': Unsupported/future modes (fallback)"
        ),
    )

    # Target player identification
    target_player_puuid: str = Field(description="Target player's PUUID")
    target_player_name: str = Field(description="Target player's summoner name")

    # All 5 players' analysis results
    team_analysis: list[V2PlayerAnalysisResult] = Field(
        description="Analysis results for all 5 team members (sorted by team_rank)",
        min_length=5,
        max_length=5,
    )

    # Team-level insights (optional summary)
    team_summary_insight: str | None = Field(
        default=None,
        description="Optional team-level insight (e.g., 'Team excelled in objectives but struggled with vision')",
        max_length=200,
    )

    # A/B testing metadata
    ab_cohort: Literal["A", "B"] | None = Field(
        default=None, description="A/B cohort assignment (for tracking)"
    )
    variant_id: str | None = Field(default=None, description="Prompt variant ID (for tracking)")

    # Performance metrics
    processing_duration_ms: float = Field(description="Total processing time (ms)")
    algorithm_version: str = Field(default="v2", description="Analysis algorithm version")

    # Arena extras (optional) — allow PaginatedTeamAnalysisView to be fully self-contained
    class ArenaDuo(BaseModel):
        me_name: str
        me_champion: str
        partner_name: str | None = None
        partner_champion: str | None = None
        placement: int | None = None

    class ArenaTopRound(BaseModel):
        round_number: int
        kills: int | None = None
        deaths: int | None = None
        damage_dealt: int | None = None
        damage_taken: int | None = None

    class ArenaTrajectory(BaseModel):
        sequence_compact: str | None = None  # e.g., "W2 L1 W1 L2"
        longest_win_len: int | None = None
        longest_win_range: tuple[int, int] | None = None  # (start,end)
        longest_lose_len: int | None = None
        longest_lose_range: tuple[int, int] | None = None

    arena_duo: ArenaDuo | None = Field(default=None)
    arena_rounds_block: str | None = Field(default=None)
    arena_trajectory: ArenaTrajectory | None = Field(default=None)
    arena_top_kills: list[ArenaTopRound] | None = Field(default=None, max_length=3)
    arena_top_damage_dealt: list[ArenaTopRound] | None = Field(default=None, max_length=3)
    arena_top_damage_taken: list[ArenaTopRound] | None = Field(default=None, max_length=3)


class ABTestingMetadata(BaseModel):
    """A/B testing experiment metadata for database storage.

    This contract defines the metadata that CLI 2 stores in the
    ab_experiment_metadata table for tracking and analysis.
    """

    match_id: str = Field(description="Match ID (primary key)")
    discord_user_id: str = Field(description="Discord user who requested analysis")

    # Cohort assignment
    ab_cohort: Literal["A", "B"] = Field(description="Assigned A/B cohort")
    variant_id: str = Field(description="Prompt variant identifier")
    prompt_version: Literal["v1", "v2"] = Field(description="Major prompt version")
    prompt_template: str = Field(description="Template identifier")

    # Experiment metadata
    ab_seed: str = Field(description="Seed used for assignment (for reproducibility)")

    # Performance metrics (auto-populated)
    llm_input_tokens: int | None = Field(default=None, description="LLM input token count")
    llm_output_tokens: int | None = Field(default=None, description="LLM output token count")
    llm_api_cost_usd: float | None = Field(default=None, description="Calculated API cost (USD)")
    llm_latency_ms: int | None = Field(default=None, description="LLM API latency (ms)")
    total_processing_time_ms: int | None = Field(
        default=None, description="Total task processing time (ms)"
    )


class UserFeedbackEvent(BaseModel):
    """User feedback event for A/B testing analysis.

    This contract defines the feedback data that CLI 1 collects via
    Discord reactions/buttons and sends to CLI 2 for storage.
    """

    match_id: str = Field(description="Match ID the feedback relates to")
    discord_user_id: str = Field(description="User who provided feedback")

    # Feedback type
    feedback_type: Literal["thumbs_up", "thumbs_down", "star", "report"] = Field(
        description="Type of feedback interaction"
    )
    feedback_value: int | None = Field(
        default=None, description="Numeric value (1=thumbs_up, -1=thumbs_down, 2=star)"
    )
    feedback_comment: str | None = Field(
        default=None, description="Optional user comment (if 'report' type)", max_length=500
    )

    # Metadata
    interaction_id: str = Field(description="Discord interaction ID (for deduplication)")

    # A/B context (denormalized for faster queries)
    ab_cohort: Literal["A", "B"] | None = Field(
        default=None, description="A/B cohort assignment (denormalized)"
    )
    variant_id: str | None = Field(default=None, description="Prompt variant ID (denormalized)")


# Example data for documentation
EXAMPLE_V2_TEAM_ANALYSIS_INPUT = {
    "match_id": "NA1_5387390374",
    "match_result": "victory",
    "target_player_index": 0,
    "team_players": [
        {
            "puuid": "a" * 78,
            "summoner_name": "TestADC",
            "champion_name": "Jinx",
            "champion_id": 222,
            "position": 0,
            "combat_score": 85.3,
            "economy_score": 92.1,
            "vision_score": 62.4,
            "objective_score": 78.9,
            "teamplay_score": 71.2,
            "overall_score": 77.8,
        },
        # ... 4 more players
    ],
    "discord_user_id": "123456789012345678",
    "ab_cohort": "B",
    "variant_id": "v2_team_summary_20251006",
}

EXAMPLE_V2_TEAM_ANALYSIS_REPORT = {
    "match_id": "NA1_5387390374",
    "match_result": "victory",
    "game_mode": "summoners_rift",
    "target_player_puuid": "a" * 78,
    "target_player_name": "TestADC",
    "team_analysis": [
        {
            "puuid": "a" * 78,
            "summoner_name": "TestADC",
            "champion_name": "Jinx",
            "champion_icon_url": "https://ddragon.leagueoflegends.com/cdn/13.24.1/img/champion/Jinx.png",
            "overall_score": 77.8,
            "team_rank": 2,
            "top_strength_dimension": "Economy",
            "top_strength_score": 92.1,
            "top_strength_team_rank": 1,
            "top_weakness_dimension": "Vision",
            "top_weakness_score": 62.4,
            "top_weakness_team_rank": 4,
            "narrative_summary": "经济领先队伍，但视野控制需提升",
        },
        # ... 4 more players
    ],
    "team_summary_insight": "Team excelled in economy but struggled with vision control",
    "ab_cohort": "B",
    "variant_id": "v2_team_summary_20251006",
    "processing_duration_ms": 2345.67,
    "algorithm_version": "v2",
}
