"""A/B Testing Framework for V2 Prompt Engineering.

This module implements cohort assignment and prompt selection services
for systematically evaluating LLM prompt variants through user feedback.

Architecture:
- CohortAssignmentService: Deterministic user-to-variant assignment
- PromptSelectorService: Variant-based prompt template selection
- Team summary statistics generation for V2 prompts
"""

import hashlib
from typing import Literal, Any

from pydantic import BaseModel, Field


class PromptVariantMetadata(BaseModel):
    """Metadata for a specific prompt variant."""

    variant_id: str = Field(
        description="Unique variant identifier (e.g., 'v2_team_summary_20251006')"
    )
    prompt_version: Literal["v1", "v2"] = Field(description="Major prompt version")
    prompt_template: str = Field(description="Template identifier for prompt generation")
    description: str = Field(description="Human-readable variant description")


class TeamSummaryStatistics(BaseModel):
    """Compressed team statistics for V2 prompt engineering.

    This compact representation reduces token costs by ~40% compared to
    sending full score data for all 5 players, while preserving comparative context.
    """

    # Combat dimension
    combat_score_avg: float = Field(description="Team average combat score")
    combat_score_max: float = Field(description="Highest combat score in team")
    combat_score_min: float = Field(description="Lowest combat score in team")

    # Economy dimension
    economy_score_avg: float = Field(description="Team average economy score")
    economy_score_max: float = Field(description="Highest economy score in team")
    economy_score_min: float = Field(description="Lowest economy score in team")

    # Vision dimension
    vision_score_avg: float = Field(description="Team average vision score")
    vision_score_max: float = Field(description="Highest vision score in team")
    vision_score_min: float = Field(description="Lowest vision score in team")

    # Objective dimension
    objective_score_avg: float = Field(description="Team average objective score")
    objective_score_max: float = Field(description="Highest objective score in team")
    objective_score_min: float = Field(description="Lowest objective score in team")

    # Teamplay dimension
    teamplay_score_avg: float = Field(description="Team average teamplay score")
    teamplay_score_max: float = Field(description="Highest teamplay score in team")
    teamplay_score_min: float = Field(description="Lowest teamplay score in team")

    # Target player's rankings (1 = best, 5 = worst)
    target_player_rank: dict[str, int] = Field(
        description="Target player's rank in each dimension (1-5)"
    )

    team_size: int = Field(default=5, description="Number of players in team (always 5)")


class CohortAssignmentService:
    """Deterministic A/B cohort assignment service.

    Uses consistent hashing to assign users to prompt variants while ensuring:
    - Consistency: Same user always gets same variant across sessions
    - Balance: Configurable distribution (e.g., 50/50 or 80/20)
    - Reproducibility: Seed-based assignment for experiment tracking
    """

    def __init__(
        self,
        variant_a_weight: float = 0.5,
        variant_b_weight: float = 0.5,
        seed: str = "prompt_ab_2025_q4",
    ) -> None:
        """Initialize cohort assignment service.

        Args:
            variant_a_weight: Probability of assigning Variant A (V1 baseline)
            variant_b_weight: Probability of assigning Variant B (V2 team-relative)
            seed: Randomization seed (change to trigger new cohort assignments)

        Raises:
            ValueError: If variant weights don't sum to 1.0
        """
        if abs((variant_a_weight + variant_b_weight) - 1.0) > 0.01:
            raise ValueError(
                f"Variant weights must sum to 1.0, got {variant_a_weight + variant_b_weight}"
            )

        self.variant_a_weight = variant_a_weight
        self.variant_b_weight = variant_b_weight
        self.seed = seed

    def assign_variant(self, user_id: str) -> Literal["A", "B"]:
        """Assign user to a prompt variant cohort using consistent hashing.

        Uses SHA-256 hash of (user_id + seed) to deterministically assign
        cohorts while maintaining statistical balance.

        Args:
            user_id: Discord user ID or any unique user identifier

        Returns:
            "A" for V1 baseline variant, "B" for V2 team-relative variant

        Example:
            >>> assigner = CohortAssignmentService(variant_a_weight=0.5, variant_b_weight=0.5)
            >>> assigner.assign_variant("123456789")
            "B"
            >>> assigner.assign_variant("123456789")  # Consistent across calls
            "B"
        """
        # Generate deterministic hash
        hash_input = f"{user_id}:{self.seed}".encode()
        hash_digest = hashlib.sha256(hash_input).hexdigest()

        # Convert first 8 hex chars to integer (0-4294967295)
        hash_int = int(hash_digest[:8], 16)

        # Normalize to 0.0-1.0 range
        hash_normalized = hash_int / 0xFFFFFFFF

        # Assign based on threshold
        if hash_normalized < self.variant_a_weight:
            return "A"
        else:
            return "B"

    def get_variant_metadata(self, cohort: Literal["A", "B"]) -> PromptVariantMetadata:
        """Get metadata for the assigned variant.

        Args:
            cohort: Assigned cohort ("A" or "B")

        Returns:
            PromptVariantMetadata with variant configuration details
        """
        metadata_map = {
            "A": PromptVariantMetadata(
                variant_id="v1_baseline_20251006",
                prompt_version="v1",
                prompt_template="single_player_analysis",
                description="V1 Baseline: Single-player analysis (no team context)",
            ),
            "B": PromptVariantMetadata(
                variant_id="v2_team_summary_20251006",
                prompt_version="v2",
                prompt_template="team_relative_summary",
                description="V2 Team-Relative: Analysis with compressed team statistics",
            ),
        }
        return metadata_map[cohort]


class PromptSelectorService:
    """Prompt template selection service based on A/B cohort assignment.

    Provides the appropriate system prompt and constructs prompt context
    based on the assigned experiment variant.
    """

    @staticmethod
    def calculate_team_summary(
        all_players_scores: list[dict[str, Any]], target_player_index: int = 0
    ) -> TeamSummaryStatistics:
        """Generate compressed team summary statistics for V2 prompts.

        This method reduces token costs by ~40% compared to sending full
        score data for all 5 players, while preserving comparative context.

        Args:
            all_players_scores: List of score dictionaries for all 5 players
            target_player_index: Index of target player in the list (default: 0)

        Returns:
            TeamSummaryStatistics with aggregated metrics and rankings

        Example:
            >>> scores = [
            ...     {"combat_score": 85.3, "economy_score": 92.1, ...},
            ...     {"combat_score": 68.2, "economy_score": 65.3, ...},
            ...     # ... 3 more players
            ... ]
            >>> summary = PromptSelectorService.calculate_team_summary(scores, target_player_index=0)
            >>> summary.combat_score_avg
            81.6
            >>> summary.target_player_rank["combat"]
            2  # Target player ranks 2nd in combat
        """
        dimensions = [
            "combat_score",
            "economy_score",
            "vision_score",
            "objective_score",
            "teamplay_score",
        ]

        # Initialize summary dict
        summary_data: dict[str, Any] = {
            "target_player_rank": {},
            "team_size": len(all_players_scores),
        }

        for dim in dimensions:
            # Extract scores for this dimension
            scores = [float(player[dim]) for player in all_players_scores]

            # Calculate statistics
            summary_data[f"{dim}_avg"] = round(sum(scores) / len(scores), 1)
            summary_data[f"{dim}_max"] = round(max(scores), 1)
            summary_data[f"{dim}_min"] = round(min(scores), 1)

            # Calculate target player's rank (1 = best, 5 = worst)
            sorted_scores = sorted(scores, reverse=True)
            target_score = all_players_scores[target_player_index][dim]
            rank = sorted_scores.index(target_score) + 1
            dim_name = dim.replace("_score", "")
            summary_data["target_player_rank"][dim_name] = rank

        return TeamSummaryStatistics(**summary_data)

    @staticmethod
    def get_prompt_template(variant_metadata: PromptVariantMetadata) -> str:
        """Get the system prompt template for a given variant.

        Args:
            variant_metadata: Metadata for the selected prompt variant

        Returns:
            System prompt template string

        Note:
            V1 prompts use the existing JIANGLI_SYSTEM_PROMPT.
            V2 prompts use the new team-relative prompt template.
        """
        if variant_metadata.prompt_version == "v1":
            # Use existing V1 system prompt
            from src.prompts.jiangli_prompt import JIANGLI_SYSTEM_PROMPT

            return JIANGLI_SYSTEM_PROMPT
        else:
            # Use V2 team-relative prompt
            from src.prompts.v2_team_relative_prompt import V2_TEAM_RELATIVE_SYSTEM_PROMPT

            return V2_TEAM_RELATIVE_SYSTEM_PROMPT

    @staticmethod
    def format_prompt_context(
        variant_metadata: PromptVariantMetadata,
        target_player_score: dict[str, Any],
        match_result: Literal["victory", "defeat"],
        team_summary: TeamSummaryStatistics | None = None,
    ) -> str:
        """Format the user prompt context based on variant type.

        Args:
            variant_metadata: Metadata for the selected prompt variant
            target_player_score: Target player's V1 score data
            match_result: Match outcome ("victory" or "defeat")
            team_summary: Team summary statistics (required for V2 variants)

        Returns:
            Formatted user prompt string to send to LLM

        Raises:
            ValueError: If V2 variant is selected but team_summary is None
        """
        import json

        if variant_metadata.prompt_version == "v1":
            # V1: Single-player analysis
            return f"""请根据以下数据为玩家生成一段中文评价：

**玩家数据**:
{json.dumps(target_player_score, ensure_ascii=False, indent=2)}

**比赛结果**: {match_result}

要求：
1. 200字左右的中文叙事
2. 基于五个维度（战斗、经济、视野、目标、团队配合）评价
3. 突出优势和改进点
4. 语气鼓励但客观
"""
        else:
            # V2: Team-relative analysis
            if team_summary is None:
                raise ValueError("team_summary is required for V2 prompt variants")

            return f"""请根据以下数据为目标玩家生成一段**团队相对**的中文评价：

**目标玩家数据**:
{json.dumps(target_player_score, ensure_ascii=False, indent=2)}

**团队统计摘要**:
{team_summary.model_dump_json(indent=2, exclude_none=True)}

**比赛结果**: {match_result}

要求：
1. 200字左右的中文叙事
2. 使用团队统计摘要进行对比分析（"你的战斗评分高于队伍平均15%"）
3. 突出相对排名（"在队伍中排名第X"）
4. 提供具体改进建议（对比队友强项）
5. 语气鼓励但客观

输出格式示例：
"在这场{match_result}中，你的{{champion_name}}在经济维度表现卓越，经济评分{{economy_score}}高于队伍平均{{economy_avg}}约{{pct_diff}}%，在队伍中排名第{{economy_rank}}。..."
"""
