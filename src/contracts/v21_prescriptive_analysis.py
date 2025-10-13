"""V2.1 Prescriptive Analysis Data Contracts.

Engineering delivery for V2.1 prescriptive (actionable) analysis feature.
Defines structured data contracts for generating and storing improvement suggestions.

Author: CLI 4 (The Lab)
Date: 2025-10-06
Research Foundation: notebooks/v2.1_prescriptive_analysis.ipynb
Status: ✅ Production Ready

Design Principles:
- Evidence-Grounded: All suggestions backed by Match-V5 Timeline events
- SMART Criteria: Specific, Measurable, Achievable, Relevant, Time-bound
- Riot Policy Compliant: Post-game training only (no real-time advantage)
- Structured Output: JSON schema enforcement to reduce LLM hallucination
"""

from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Input Contracts: Data Requirements for V2.1 Analysis
# =============================================================================


class V21TimelineEvidence(BaseModel):
    """Single timeline event providing evidence for a prescriptive suggestion.

    This represents a specific in-game event (ward placed, objective lost, etc.)
    that serves as factual grounding for improvement advice.
    """

    event_type: str = Field(
        description=(
            "Timeline event type from Match-V5 API. "
            "Examples: WARD_PLACED, WARD_KILL, ELITE_MONSTER_KILL, "
            "BUILDING_KILL, CHAMPION_KILL"
        )
    )

    timestamp_ms: int = Field(description="Event timestamp in milliseconds from game start", ge=0)

    formatted_timestamp: str = Field(
        description="Human-readable timestamp in MM:SS format (e.g., '24:16')",
        pattern=r"^\d{1,2}:\d{2}$",
    )

    details: dict[str, str | int | float | bool] = Field(
        description=(
            "Event-specific details. "
            "For WARD_PLACED: {item, location, lifetime_seconds}. "
            "For ELITE_MONSTER_KILL: {monster_type, killer_team}. "
            "For BUILDING_KILL: {building_type, player_damage_pct}"
        )
    )

    player_context: str | None = Field(
        default=None,
        description=(
            "Optional context about target player's action during this event. "
            "Example: 'You were farming bot wave at 23:30, missed Baron contest'"
        ),
        max_length=200,
    )


class V21WeakDimension(BaseModel):
    """Analysis of a performance dimension where player underperformed.

    Combines V1 scoring results with timeline evidence to enable
    data-grounded prescriptive suggestions.
    """

    dimension: Literal["Combat", "Economy", "Vision", "Objective Control", "Teamplay"] = Field(
        description="Performance dimension name"
    )

    score: float = Field(description="Player's score in this dimension (0-100)", ge=0, le=100)

    team_rank: int = Field(description="Player's rank within team (1=best, 5=worst)", ge=1, le=5)

    team_avg: float = Field(description="Team average score for this dimension", ge=0, le=100)

    gap_from_avg: float = Field(
        description=(
            "Percentage point difference from team average. Negative indicates underperformance."
        )
    )

    evidence: list[V21TimelineEvidence] = Field(
        description=(
            "Timeline events supporting this weakness assessment. "
            "Minimum 1 event required for factual grounding."
        ),
        min_length=1,
    )

    critical_impact_event: V21TimelineEvidence | None = Field(
        default=None,
        description=(
            "Optional: Most critical event where this weakness impacted match outcome. "
            "Example: Baron stolen due to lack of vision."
        ),
    )


class V21PrescriptiveAnalysisInput(BaseModel):
    """Complete input data for V2.1 prescriptive analysis.

    This contract defines what CLI 2 must provide to the LLM for generating
    actionable improvement suggestions.
    """

    # Player identification
    summoner_name: str = Field(description="Target player's summoner name")
    champion_name: str = Field(description="Played champion name")
    match_id: str = Field(description="Match ID in Match-V5 format")

    # Match context
    match_result: Literal["victory", "defeat"] = Field(
        description="Match outcome for player's team"
    )
    overall_score: float = Field(description="Player's overall V1 score (0-100)", ge=0, le=100)

    # Weak dimensions with evidence
    weak_dimensions: list[V21WeakDimension] = Field(
        description=(
            "Dimensions where player scored below team average. "
            "Sorted by gap_from_avg (worst first). "
            "Maximum 3 dimensions to avoid overwhelming user."
        ),
        min_length=1,
        max_length=3,
    )

    # Optional user context (for future V2.2 personalization)
    user_skill_level: Literal["beginner", "intermediate", "advanced"] | None = Field(
        default=None,
        description="Optional: User's skill level for tone customization (V2.2)",
    )


# =============================================================================
# Output Contracts: Structured Improvement Suggestions
# =============================================================================


class V21ImprovementSuggestion(BaseModel):
    """Single actionable improvement suggestion.

    This contract enforces the SMART criteria for suggestions:
    - Specific: Clear action item with time/location/priority
    - Measurable: Expected outcome with quantifiable metric
    - Achievable: Grounded in player's actual performance data
    - Relevant: Addresses a documented weak dimension
    - Time-bound: References specific match timestamps
    """

    suggestion_id: str = Field(
        description=(
            "Unique identifier for this suggestion. "
            "Format: '{dimension}_{timestamp_ms}' for feedback tracking. "
            "Example: 'Vision_1456000'"
        ),
        pattern=r"^[A-Z][a-z]+(_[A-Z][a-z]+)*_\d+$",
    )

    dimension: Literal["Combat", "Economy", "Vision", "Objective Control", "Teamplay"] = Field(
        description="Performance dimension this suggestion addresses"
    )

    issue_identified: str = Field(
        description=(
            "Clear description of the problem identified from evidence. "
            "Must reference team comparison. "
            "Example: '视野控制弱于队友（评分62.4，队伍排名第4），导致24:16大龙被敌方偷取'"
        ),
        min_length=20,
        max_length=200,
    )

    evidence_timestamp: str = Field(
        description=(
            "Primary evidence timestamp in MM:SS format. "
            "References the critical event supporting this suggestion."
        ),
        pattern=r"^\d{1,2}:\d{2}$",
    )

    action_item: str = Field(
        description=(
            "Specific, actionable advice in Chinese. "
            "MUST include:\n"
            "  - Exact timing (e.g., '大龙刷新前60秒')\n"
            "  - Specific location (e.g., '大龙坑上方河道草丛')\n"
            "  - Clear priority (e.g., '即使延迟回城购买装备，视野优先级更高')\n"
            "AVOID vague advice like '提升视野意识' or '多放眼'."
        ),
        min_length=50,
        max_length=400,
    )

    expected_outcome: str = Field(
        description=(
            "Quantifiable expected result of following this advice. "
            "Must include measurable metric. "
            "Example: '提升团队对大龙区域的视野控制率从0%到至少50%，"
            "避免被敌方偷龙。数据显示，有视野控制的大龙争夺战，你的队伍胜率提升35%。'"
        ),
        min_length=30,
        max_length=300,
    )

    learning_resource: str | None = Field(
        default=None,
        description=(
            "Optional: Specific learning resource or teammate reference. "
            "Example: '建议观看你的辅助队友在本场比赛中的视野布局回放（17:00-24:00时间段）'"
        ),
        max_length=200,
    )

    priority: Literal["critical", "high", "medium"] = Field(
        default="medium",
        description=(
            "Suggestion priority based on impact on match outcome. "
            "'critical': Directly caused match loss (e.g., Baron stolen). "
            "'high': Significant impact (e.g., missed Dragon). "
            "'medium': Incremental improvement opportunity."
        ),
    )


class V21PrescriptiveAnalysisReport(BaseModel):
    """Complete V2.1 prescriptive analysis output.

    This contract defines the final structured report that CLI 2 will store
    in the database and CLI 1 will render in Discord.
    """

    # Match metadata
    match_id: str = Field(description="Match ID")
    summoner_name: str = Field(description="Target player's summoner name")
    champion_name: str = Field(description="Played champion name")
    match_result: Literal["victory", "defeat"] = Field(description="Match outcome")

    # Improvement suggestions (sorted by priority)
    improvement_suggestions: list[V21ImprovementSuggestion] = Field(
        description=(
            "Actionable improvement suggestions, sorted by priority "
            "(critical → high → medium). "
            "Maximum 5 suggestions to avoid overwhelming user."
        ),
        min_length=1,
        max_length=5,
    )

    # Metadata
    total_weak_dimensions: int = Field(
        description="Total number of weak dimensions analyzed", ge=1, le=3
    )

    coaching_summary: str | None = Field(
        default=None,
        description=(
            "Optional: Overall coaching message (2-3 sentences). "
            "Example: '本场比赛你的个人实力优秀，但在团队协作和视野控制上还有明显提升空间。"
            "重点关注大龙刷新前的视野布局和目标争夺的提前集结。'"
        ),
        max_length=300,
    )

    # Performance metrics
    llm_input_tokens: int | None = Field(
        default=None, description="LLM input token count (for cost tracking)"
    )
    llm_output_tokens: int | None = Field(
        default=None, description="LLM output token count (for cost tracking)"
    )
    generation_latency_ms: int | None = Field(
        default=None, description="LLM generation latency (milliseconds)"
    )

    # Version tracking
    algorithm_version: str = Field(
        default="v2.1",
        description="Analysis algorithm version (for A/B testing tracking)",
    )


# =============================================================================
# Feedback Collection Contract (for V2.1 Evaluation)
# =============================================================================


class V21SuggestionFeedback(BaseModel):
    """User feedback on a specific V2.1 improvement suggestion.

    This contract enables fine-grained feedback collection to evaluate
    individual suggestions rather than entire reports.
    """

    match_id: str = Field(description="Match ID the suggestion relates to")
    suggestion_id: str = Field(description="Unique suggestion ID (from V21ImprovementSuggestion)")
    discord_user_id: str = Field(description="User who provided feedback")

    # Actionability rating (new metric for V2.1)
    is_actionable: bool = Field(
        description="User's assessment: Is this suggestion specific and actionable?"
    )

    is_helpful: bool = Field(
        description="User's assessment: Would following this advice improve performance?"
    )

    feedback_comment: str | None = Field(
        default=None,
        description="Optional: User's free-form comment on this suggestion",
        max_length=500,
    )

    # Metadata
    created_at: str = Field(description="Feedback timestamp (ISO 8601 format)")
    interaction_id: str = Field(description="Discord interaction ID (for deduplication)")


# =============================================================================
# Example Data (for Documentation & Testing)
# =============================================================================

EXAMPLE_V21_INPUT = V21PrescriptiveAnalysisInput(
    summoner_name="TestADC",
    champion_name="Jinx",
    match_id="NA1_5387390374",
    match_result="defeat",
    overall_score=77.8,
    weak_dimensions=[
        V21WeakDimension(
            dimension="Vision",
            score=62.4,
            team_rank=4,
            team_avg=75.3,
            gap_from_avg=-12.9,
            evidence=[
                V21TimelineEvidence(
                    event_type="WARD_PLACED",
                    timestamp_ms=734000,
                    formatted_timestamp="12:14",
                    details={
                        "item": "Control Ward",
                        "location": "Baron pit",
                        "lifetime_seconds": 68,
                    },
                    player_context=None,
                ),
                V21TimelineEvidence(
                    event_type="WARD_STATS",
                    timestamp_ms=1800000,
                    formatted_timestamp="30:00",
                    details={
                        "player_total_wards": 8,
                        "support_total_wards": 22,
                        "player_avg_lifetime": 52,
                        "support_avg_lifetime": 87,
                    },
                    player_context=None,
                ),
            ],
            critical_impact_event=V21TimelineEvidence(
                event_type="ELITE_MONSTER_KILL",
                timestamp_ms=1456000,
                formatted_timestamp="24:16",
                details={
                    "monster_type": "BARON_NASHOR",
                    "killer_team": "ENEMY",
                    "team_vision_in_area": False,
                },
                player_context="You were farming bot wave at 23:30, missed Baron contest",
            ),
        ),
    ],
    user_skill_level=None,
)

EXAMPLE_V21_OUTPUT = V21PrescriptiveAnalysisReport(
    match_id="NA1_5387390374",
    summoner_name="TestADC",
    champion_name="Jinx",
    match_result="defeat",
    improvement_suggestions=[
        V21ImprovementSuggestion(
            suggestion_id="Vision_1456000",
            dimension="Vision",
            issue_identified=("视野控制弱于队友（评分62.4，队伍排名第4），导致24:16大龙被敌方偷取"),
            evidence_timestamp="24:16",
            action_item=(
                "在大龙刷新前60秒（游戏时间20分钟后），"
                "优先购买并放置真眼在大龙坑上方河道草丛。"
                "即使需要延迟回城购买装备，视野优先级更高，"
                "因为大龙失误可能直接导致比赛失利。"
            ),
            expected_outcome=(
                "提升团队对大龙区域的视野控制率从0%到至少50%，"
                "避免被敌方偷龙。数据显示，有视野控制的大龙争夺战，"
                "你的队伍胜率提升35%。"
            ),
            learning_resource=(
                "建议观看你的辅助队友在本场比赛中的视野布局回放（17:00-24:00时间段），"
                "他放置了22个眼，平均存活87秒，是你的2.75倍。"
            ),
            priority="critical",
        ),
    ],
    total_weak_dimensions=1,
    coaching_summary=(
        "本场比赛你的个人实力优秀，但在团队协作和视野控制上还有明显提升空间。"
        "重点关注大龙刷新前的视野布局和目标争夺的提前集结。"
    ),
    llm_input_tokens=1245,
    llm_output_tokens=423,
    generation_latency_ms=3420,
    algorithm_version="v2.1",
)
