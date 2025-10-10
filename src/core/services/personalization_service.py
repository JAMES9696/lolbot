"""V2.2 Personalization Service.

Core service for personalizing V2.1 prescriptive analysis based on user profiles.
Implements prompt dynamic injection and tone customization logic.

Author: CLI 4 (The Lab)
Date: 2025-10-06
Research Foundation: notebooks/v2.2_personalization.ipynb
Status: ✅ Production Ready

Key Responsibilities:
- Load user profile from database
- Select appropriate prompt template based on preferences
- Generate personalized context for LLM prompt injection
- Coordinate with V2.1 LLM adapter for suggestion generation
"""

from pathlib import Path

from src.contracts.v21_prescriptive_analysis import (
    V21PrescriptiveAnalysisInput,
    V21PrescriptiveAnalysisReport,
)
from src.contracts.v22_user_profile import V22UserProfile


class PersonalizationService:
    """Service for personalizing V2.1 prescriptive analysis.

    This service acts as a bridge between user profiles and LLM generation,
    ensuring that suggestions are tailored to each user's preferences,
    skill level, and performance patterns.
    """

    def __init__(self, prompt_templates_dir: Path):
        """Initialize personalization service.

        Args:
            prompt_templates_dir: Directory containing V2.2 prompt templates
                (e.g., v22_coaching_competitive.txt, v22_coaching_casual.txt)
        """
        self.prompt_templates_dir = prompt_templates_dir
        self._prompt_cache: dict[str, str] = {}

    def select_prompt_template(self, user_profile: V22UserProfile) -> str:
        """Select appropriate prompt template based on user profile.

        Selection logic:
        1. If user explicitly set preferred_analysis_tone in /settings, use that
        2. Otherwise, use inferred player_type from classification

        Args:
            user_profile: User's complete profile

        Returns:
            Prompt template filename (e.g., "v22_coaching_competitive.txt")
        """
        # Priority 1: Explicit preference from /settings
        tone = user_profile.preferences.preferred_analysis_tone

        # Priority 2: Inferred player type (if no explicit preference)
        if tone is None:
            tone = user_profile.classification.player_type

        # Map tone to template filename
        template_map = {
            "competitive": "v22_coaching_competitive.txt",
            "casual": "v22_coaching_casual.txt",
        }

        return template_map[tone]

    def load_prompt_template(self, template_filename: str) -> str:
        """Load prompt template from disk with caching.

        Args:
            template_filename: Template filename (e.g., "v22_coaching_competitive.txt")

        Returns:
            Prompt template content as string

        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        # Check cache first
        if template_filename in self._prompt_cache:
            return self._prompt_cache[template_filename]

        # Load from disk
        template_path = self.prompt_templates_dir / template_filename
        if not template_path.exists():
            raise FileNotFoundError(
                f"Prompt template not found: {template_path}. "
                f"Ensure V2.2 prompt templates are deployed to {self.prompt_templates_dir}"
            )

        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        # Cache for future use
        self._prompt_cache[template_filename] = content

        return content

    def generate_user_context(
        self,
        user_profile: V22UserProfile,
        current_match_input: V21PrescriptiveAnalysisInput,
    ) -> str:
        """Generate personalized user context for prompt injection.

        This context is injected into the LLM's system prompt to influence
        suggestion generation based on user's historical patterns.

        Args:
            user_profile: User's complete profile
            current_match_input: Current match analysis input (for context)

        Returns:
            Formatted user context string (Chinese)

        Example output:
            "**用户画像**: 该用户是一个 Jungle 位置玩家，在最近20场比赛中，
            Vision 维度得分持续偏低（平均 45.2 分），这是需要优先改进的维度。
            Jinx 是该用户的常用英雄之一。"
        """
        context_parts = []

        # Section 1: Role context
        role = (
            user_profile.preferences.preferred_role
            or user_profile.champion_profile.inferred_primary_role
        )
        if role and role != "Fill":
            context_parts.append(f"该用户是一个 {role} 位置玩家")

        # Section 2: Persistent weakness context (most important)
        if (
            user_profile.performance_trends
            and user_profile.performance_trends.persistent_weak_dimension
        ):
            dim = user_profile.performance_trends.persistent_weak_dimension
            avg_score = self._get_dimension_avg_score(user_profile, dim)
            frequency_pct = int(
                (user_profile.performance_trends.weak_dimension_frequency or 0) * 100
            )

            context_parts.append(
                f"在最近20场比赛中，{dim} 维度得分持续偏低（平均 {avg_score:.1f} 分，"
                f"有 {frequency_pct}% 的比赛中低于队伍平均水平），这是需要优先改进的维度"
            )

        # Section 3: Champion familiarity context
        current_champion = current_match_input.champion_name
        if current_champion in user_profile.champion_profile.top_3_champions:
            context_parts.append(f"{current_champion} 是该用户的常用英雄之一")

        # Section 4: Skill level context (for casual tone only)
        if user_profile.preferences.preferred_analysis_tone == "casual":
            skill_hints = {
                "beginner": "该用户是新手玩家，请使用简单易懂的语言",
                "intermediate": "",  # No hint for intermediate (default)
                "advanced": "该用户是高水平玩家，可以使用更专业的术语",
            }
            hint = skill_hints.get(user_profile.classification.skill_level, "")
            if hint:
                context_parts.append(hint)

        # Combine all parts
        if not context_parts:
            return ""  # No personalization context available

        return "**用户画像**: " + "。".join(context_parts) + "。"

    def _get_dimension_avg_score(self, user_profile: V22UserProfile, dimension: str) -> float:
        """Helper to get average score for a specific dimension."""
        if not user_profile.performance_trends:
            return 0.0

        dimension_map = {
            "Combat": user_profile.performance_trends.avg_combat_score,
            "Economy": user_profile.performance_trends.avg_economy_score,
            "Vision": user_profile.performance_trends.avg_vision_score,
            "Objective Control": user_profile.performance_trends.avg_objective_control_score,
            "Teamplay": user_profile.performance_trends.avg_teamplay_score,
        }

        return dimension_map.get(dimension, 0.0)

    def format_personalized_prompt(
        self,
        user_profile: V22UserProfile,
        analysis_input: V21PrescriptiveAnalysisInput,
    ) -> tuple[str, str]:
        """Format personalized prompt for LLM generation.

        This is the main integration point with V2.1 LLM adapter.

        Args:
            user_profile: User's complete profile
            analysis_input: V2.1 prescriptive analysis input

        Returns:
            Tuple of (prompt_template_content, user_context_string)
            The LLM adapter should inject user_context into the template's
            {user_profile_context} placeholder.

        Example usage in LLM adapter:
            ```python
            prompt_template, user_context = personalization_service.format_personalized_prompt(
                user_profile, analysis_input
            )
            formatted_prompt = prompt_template.format(
                user_profile_context=user_context,
                summoner_name=analysis_input.summoner_name,
                champion_name=analysis_input.champion_name,
                # ... other V2.1 fields
            )
            ```
        """
        # Step 1: Select prompt template based on tone preference
        template_filename = self.select_prompt_template(user_profile)

        # Step 2: Load template content
        prompt_template = self.load_prompt_template(template_filename)

        # Step 3: Generate user context for injection
        user_context = self.generate_user_context(user_profile, analysis_input)

        return prompt_template, user_context

    async def generate_personalized_analysis(
        self,
        user_profile: V22UserProfile,
        analysis_input: V21PrescriptiveAnalysisInput,
        llm_adapter,  # Type: adapters.gemini_llm.GeminiLLMAdapter
    ) -> V21PrescriptiveAnalysisReport:
        """Generate personalized V2.1 prescriptive analysis.

        This is the high-level orchestration method that CLI 2 will call
        from the analyze_team_task Celery task.

        Args:
            user_profile: User's complete profile
            analysis_input: V2.1 prescriptive analysis input (with evidence)
            llm_adapter: Gemini LLM adapter instance (for generation)

        Returns:
            V21PrescriptiveAnalysisReport with personalized suggestions

        Integration example (in CLI 2's analyze_team_task):
            ```python
            # Load user profile
            user_profile = await user_profile_service.get_or_create_profile(
                discord_user_id, puuid
            )

            # Generate personalized analysis
            report = await personalization_service.generate_personalized_analysis(
                user_profile=user_profile,
                analysis_input=v21_input,
                llm_adapter=gemini_adapter,
            )
            ```
        """
        # Format personalized prompt
        prompt_template, user_context = self.format_personalized_prompt(
            user_profile, analysis_input
        )

        # Call LLM adapter with personalized prompt
        # Note: This assumes the LLM adapter has a method that accepts
        # custom prompt templates. CLI 2 may need to add this method.
        report = await llm_adapter.generate_prescriptive_analysis_v22(
            input_data=analysis_input,
            prompt_template=prompt_template,
            user_context=user_context,
        )

        return report


# =============================================================================
# Example Usage (for Documentation)
# =============================================================================

if __name__ == "__main__":
    # Example: How CLI 2 would use PersonalizationService

    from src.contracts.v22_user_profile import EXAMPLE_V22_USER_PROFILE

    # Initialize service
    service = PersonalizationService(prompt_templates_dir=Path("src/prompts"))

    # Example user profile (competitive Jungle player with Vision weakness)
    user_profile = EXAMPLE_V22_USER_PROFILE

    # Example V2.1 analysis input (mock)
    from src.contracts.v21_prescriptive_analysis import (
        EXAMPLE_V21_INPUT,
    )

    analysis_input = EXAMPLE_V21_INPUT

    # Generate personalized prompt
    prompt_template, user_context = service.format_personalized_prompt(user_profile, analysis_input)

    print("=" * 80)
    print("Selected Prompt Template:", service.select_prompt_template(user_profile))
    print("=" * 80)
    print("Generated User Context:")
    print(user_context)
    print("=" * 80)
    print("Prompt Template Preview (first 500 chars):")
    print(prompt_template[:500] + "...")
    print("=" * 80)
