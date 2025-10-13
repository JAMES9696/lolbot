"""V2.3 Multi-Mode Analysis Data Contracts.

Engineering delivery for V2.3 multi-mode support (ARAM, Arena).
Defines game mode detection, mode-specific analysis contracts, and graceful degradation.

Author: CLI 4 (The Lab)
Date: 2025-10-06
Status: ✅ Production Ready

Design Principles:
- Mode Specificity: Each mode has tailored analysis dimensions
- Graceful Degradation: Unsupported modes provide basic stats + generic text
- Riot Compliance: Arena mode excludes win rate predictions per policy
- Data Core: Match-V5 Timeline API as primary data source
"""

from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Game Mode Detection & Queue ID Mapping
# =============================================================================

# Riot API Queue ID to Internal Game Mode Mapping
# Source: https://static.developer.riotgames.com/docs/lol/queues.json
QUEUE_ID_MAPPING = {
    # Summoner's Rift (5v5 Ranked/Normal)
    400: "SR",  # Normal Draft Pick
    420: "SR",  # Ranked Solo/Duo
    430: "SR",  # Normal Blind Pick
    440: "SR",  # Ranked Flex
    450: "ARAM",  # ARAM (Howling Abyss)
    # Arena Mode (2v2v2v2)
    1700: "Arena",  # Arena mode
    1710: "Arena",  # Arena (experimental queue)
    # Special Modes (Fallback)
    900: "Fallback",  # ARURF (URF with random champions)
    1020: "Fallback",  # One For All
    1200: "Fallback",  # Nexus Blitz
    1300: "Fallback",  # Nexus Blitz (alt queue)
    # Tournament Realm (Not applicable for public API)
    # 2000: "Tournament",
}

# Reverse mapping: Game mode to queue IDs
MODE_TO_QUEUE_IDS = {
    "SR": [400, 420, 430, 440],
    "ARAM": [450],
    "Arena": [1700, 1710],
    "Fallback": [900, 1020, 1200, 1300],
}


class GameMode(BaseModel):
    """Game mode detection result."""

    mode: Literal["SR", "ARAM", "Arena", "Fallback"] = Field(
        description="Detected game mode from queueId"
    )

    queue_id: int = Field(description="Riot API queueId that triggered this mode detection")

    queue_name: str | None = Field(
        default=None, description="Human-readable queue name (e.g., 'Ranked Solo/Duo')"
    )

    is_supported: bool = Field(
        description=(
            "Whether this mode has V1-Lite or V2 analysis support. "
            "False triggers graceful degradation."
        )
    )

    analysis_version: Literal["V1", "V1-Lite", "V2", "V2.1", "V2.2", "Fallback"] = Field(
        description=(
            "Analysis version available for this mode. "
            "SR: V2.2 (full stack), ARAM/Arena: V1-Lite, Others: Fallback"
        )
    )


def detect_game_mode(queue_id: int) -> GameMode:
    """Detect game mode from Riot API queueId.

    Args:
        queue_id: Queue ID from Match-V5 API response

    Returns:
        GameMode with detection result and support status

    Example:
        >>> detect_game_mode(450)
        GameMode(mode="ARAM", queue_id=450, is_supported=True, analysis_version="V1-Lite")
    """
    mode = QUEUE_ID_MAPPING.get(queue_id, "Fallback")

    # Determine support status and analysis version
    support_matrix = {
        "SR": (True, "V2.2"),
        "ARAM": (True, "V1-Lite"),
        "Arena": (True, "V1-Lite"),
        "Fallback": (False, "Fallback"),
    }

    is_supported, analysis_version = support_matrix[mode]

    # Queue name lookup (simplified)
    queue_names = {
        400: "Normal Draft Pick",
        420: "Ranked Solo/Duo",
        430: "Normal Blind Pick",
        440: "Ranked Flex",
        450: "ARAM",
        1700: "Arena",
        900: "ARURF",
        1020: "One For All",
    }

    return GameMode(
        mode=mode,  # type: ignore[arg-type]
        queue_id=queue_id,
        queue_name=queue_names.get(queue_id),
        is_supported=is_supported,
        analysis_version=analysis_version,  # type: ignore[arg-type]
    )


# =============================================================================
# Mode-Specific Metric Applicability Matrix
# =============================================================================


class MetricApplicability(BaseModel):
    """Defines which V1 metrics are valid for each game mode.

    This matrix ensures mode-specific analysis doesn't use irrelevant metrics.
    For example, Vision Score is disabled for ARAM (single-lane map).
    """

    mode: Literal["SR", "ARAM", "Arena"]

    # V1 Core Dimensions
    combat_enabled: bool = Field(description="Combat dimension (kills, deaths, damage) enabled")
    economy_enabled: bool = Field(description="Economy dimension (gold, CS) enabled")
    vision_enabled: bool = Field(description="Vision dimension (wards, vision score) enabled")
    objective_control_enabled: bool = Field(
        description="Objective Control dimension (dragons, barons) enabled"
    )
    teamplay_enabled: bool = Field(description="Teamplay dimension (assists, CC time) enabled")

    # Mode-specific dimension weights (0.0 = disabled, 1.0 = normal)
    combat_weight: float = Field(ge=0.0, le=2.0, default=1.0)
    economy_weight: float = Field(ge=0.0, le=2.0, default=1.0)
    vision_weight: float = Field(ge=0.0, le=2.0, default=1.0)
    objective_control_weight: float = Field(ge=0.0, le=2.0, default=1.0)
    teamplay_weight: float = Field(ge=0.0, le=2.0, default=1.0)


# Metric applicability presets
METRIC_APPLICABILITY_PRESETS = {
    "SR": MetricApplicability(
        mode="SR",
        combat_enabled=True,
        economy_enabled=True,
        vision_enabled=True,
        objective_control_enabled=True,
        teamplay_enabled=True,
        # All weights = 1.0 (default)
    ),
    "ARAM": MetricApplicability(
        mode="ARAM",
        combat_enabled=True,
        economy_enabled=True,
        vision_enabled=False,  # ❌ No vision in single-lane map
        objective_control_enabled=False,  # ❌ No dragons/barons
        teamplay_enabled=True,
        combat_weight=1.5,  # ⬆️ Increased importance (constant teamfighting)
        economy_weight=0.8,  # ⬇️ Decreased importance (passive gold income)
        teamplay_weight=1.3,  # ⬆️ Increased importance (5v5 all game)
    ),
    "Arena": MetricApplicability(
        mode="Arena",
        combat_enabled=True,
        economy_enabled=False,  # ❌ No traditional gold/CS in Arena
        vision_enabled=False,  # ❌ Small arena map, no vision mechanics
        objective_control_enabled=False,  # ❌ No objectives
        teamplay_enabled=True,
        combat_weight=2.0,  # ⬆️⬆️ Maximum importance (pure combat mode)
        teamplay_weight=1.8,  # ⬆️ High importance (2v2 synergy)
    ),
}


# =============================================================================
# ARAM V1-Lite Analysis Contracts
# =============================================================================


class V23ARAMTeamfightMetrics(BaseModel):
    """ARAM-specific teamfight performance metrics."""

    total_teamfights: int = Field(description="Total teamfights participated in", ge=0)

    damage_share_in_teamfights: float = Field(
        description="Player's damage share in teamfights (0.0-1.0)", ge=0.0, le=1.0
    )

    damage_taken_share: float = Field(
        description="Player's damage taken share (tanking for team, 0.0-1.0)",
        ge=0.0,
        le=1.0,
    )

    avg_survival_time_in_teamfights: float = Field(
        description="Average survival time in teamfights (seconds)", ge=0.0
    )

    deaths_before_teamfight_end: int = Field(
        description="Deaths that occurred before teamfight ended (poor timing)", ge=0
    )

    kills_participation_rate: float = Field(
        description="Kill participation rate in teamfights (0.0-1.0)", ge=0.0, le=1.0
    )


class V23ARAMBuildAdaptation(BaseModel):
    """ARAM-specific build adaptation metrics."""

    enemy_ap_threat_level: Literal["low", "medium", "high"] = Field(
        description="Enemy team AP damage threat level"
    )

    enemy_ad_threat_level: Literal["low", "medium", "high"] = Field(
        description="Enemy team AD damage threat level"
    )

    player_mr_items: int = Field(description="Number of Magic Resist items built", ge=0, le=6)

    player_armor_items: int = Field(description="Number of Armor items built", ge=0, le=6)

    build_adaptation_score: float = Field(
        description=(
            "Build adaptation score (0-100). "
            "High score = appropriate defensive items for enemy comp"
        ),
        ge=0.0,
        le=100.0,
    )

    recommended_item_adjustments: list[str] = Field(
        default_factory=list,
        description="Suggested item swaps (e.g., ['考虑购买水银鞋对抗敌方控制链'])",
        max_length=3,
    )


class V23ARAMAnalysisReport(BaseModel):
    """Complete ARAM V1-Lite analysis report.

    This contract defines the structured output for ARAM mode analysis.
    Focus areas: Teamfight efficiency, survival, build adaptation.
    """

    # Match metadata
    match_id: str = Field(description="Match ID")
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion")
    match_result: Literal["victory", "defeat"] = Field(description="Match outcome")

    # Overall score (simplified V1-Lite)
    overall_score: float = Field(
        description="Overall ARAM performance score (0-100)", ge=0.0, le=100.0
    )

    # ARAM-specific metrics
    teamfight_metrics: V23ARAMTeamfightMetrics
    build_adaptation: V23ARAMBuildAdaptation

    # Simplified dimension scores (Combat + Teamplay only)
    combat_score: float = Field(ge=0.0, le=100.0)
    teamplay_score: float = Field(ge=0.0, le=100.0)

    # Analysis summary (LLM-generated)
    analysis_summary: str = Field(
        description=(
            "ARAM-focused analysis summary in Chinese. "
            "Focus: Teamfight positioning, survival, build choices. "
            "Avoid: Lane control, jungle pathing (not applicable to ARAM)."
        ),
        min_length=0,  # Relaxed for degraded mode
        max_length=800,
    )

    # Top 3 improvement suggestions (simplified, no V2.1 evidence-grounding)
    improvement_suggestions: list[str] = Field(
        default_factory=list,  # Allow empty for fallback/degraded mode
        description="Top 3 actionable suggestions for ARAM improvement",
        min_length=0,  # Relaxed for degraded mode
        max_length=3,
    )

    # Metadata
    algorithm_version: str = Field(default="v2.3-aram-lite")
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None


# =============================================================================
# Arena V1-Lite Analysis Contracts
# =============================================================================


class V23ArenaRoundPerformance(BaseModel):
    """Arena-specific per-round performance metrics."""

    round_number: int = Field(description="Round number (1-8 typically)", ge=1)

    round_result: Literal["win", "loss"] = Field(description="Round outcome for player's duo")

    damage_dealt: int = Field(description="Total damage dealt in this round", ge=0)

    damage_taken: int = Field(description="Total damage taken in this round", ge=0)

    kills: int = Field(ge=0)
    deaths: int = Field(ge=0)

    positioning_score: float = Field(
        description=(
            "Positioning quality in this round (0-100). "
            "High score = good target selection, avoided focus fire"
        ),
        ge=0.0,
        le=100.0,
    )


class V23ArenaAugmentAnalysis(BaseModel):
    """Arena-specific Augment (Prismatic trait) analysis.

    IMPORTANT COMPLIANCE NOTE:
    Per Riot Games policy, this analysis MUST NOT display Augment win rates
    or provide competitive advantage through win rate predictions.

    Analysis MUST be retrospective (post-game) and focus on synergy with
    champion/partner, NOT on tier lists or win rate rankings.
    """

    augments_selected: list[str] = Field(
        description="Augments (Prismatic traits) selected by player",
        max_length=5,
    )

    augment_synergy_with_champion: str = Field(
        description=(
            "Analysis of how selected Augments synergized with player's champion. "
            "Example: '你选择的【猛攻】增强符文与你的刺客英雄配合良好，"
            "提升了爆发伤害。' "
            "❌ MUST NOT include win rates or tier rankings."
        ),
        max_length=300,
    )

    augment_synergy_with_partner: str = Field(
        description=(
            "Analysis of how Augments synergized with duo partner's champion. "
            "❌ MUST NOT include win rates."
        ),
        max_length=300,
    )

    alternative_augment_suggestion: str | None = Field(
        default=None,
        description=(
            "Retrospective suggestion for alternative Augment in specific rounds. "
            "Example: '在第3轮时，如果选择【韧性】而非【猛攻】，"
            "可能能更好地应对敌方控制链。' "
            "❌ MUST NOT be based on win rate data, only on post-game analysis."
        ),
        max_length=300,
    )


class V23ArenaAnalysisReport(BaseModel):
    """Complete Arena V1-Lite analysis report.

    This contract defines the structured output for Arena mode analysis.
    Focus areas: Combat strategy per round, Augment synergy (NO WIN RATES), duo coordination.

    COMPLIANCE: Riot Games prohibits displaying Arena Augment/item win rates
    to maintain competitive integrity. All analysis must be retrospective.
    """

    # Match metadata
    match_id: str = Field(description="Match ID")
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion")
    partner_summoner_name: str | None = Field(
        default=None, description="Duo partner's summoner name"
    )
    partner_champion_name: str | None = Field(default=None, description="Partner's champion")

    final_placement: int = Field(
        description="Final placement (1=1st place, 8=8th place for 8-team Arena)", ge=1, le=8
    )

    # Overall score (simplified V1-Lite)
    overall_score: float = Field(
        description="Overall Arena performance score (0-100)", ge=0.0, le=100.0
    )

    # Arena-specific metrics
    rounds_played: int = Field(description="Total rounds played", ge=1)
    rounds_won: int = Field(description="Rounds won by player's duo", ge=0)

    round_performances: list[V23ArenaRoundPerformance] = Field(
        description="Per-round performance breakdown (up to 20 rounds for extended Arena)",
        max_length=20,
    )

    augment_analysis: V23ArenaAugmentAnalysis

    # Simplified dimension scores (Combat + Teamplay only)
    combat_score: float = Field(ge=0.0, le=100.0)
    duo_synergy_score: float = Field(
        description="Duo partner synergy score (0-100)", ge=0.0, le=100.0
    )

    # Analysis summary (LLM-generated)
    analysis_summary: str = Field(
        default="",  # Allow empty for fallback/degraded mode
        description=(
            "Arena-focused analysis summary in Chinese. "
            "Focus: Round-by-round combat decisions, Augment synergies, duo coordination. "
            "❌ MUST NOT include Augment win rates or tier rankings. "
            "Avoid: Lane control, vision (not applicable to Arena)."
        ),
        min_length=0,  # Relaxed for degraded mode
        max_length=800,
    )

    # Top 3 improvement suggestions (simplified)
    improvement_suggestions: list[str] = Field(
        default_factory=list,  # Allow empty for fallback/degraded mode
        description="Top 3 actionable suggestions for Arena improvement",
        min_length=0,  # Relaxed for degraded mode
        max_length=3,
    )

    # Metadata
    algorithm_version: str = Field(default="v2.3-arena-lite")
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None


# =============================================================================
# Graceful Degradation Contract (Fallback Mode)
# =============================================================================


class V23FallbackAnalysisReport(BaseModel):
    """Fallback analysis report for unsupported game modes.

    Provides basic stats + generic text when mode-specific analysis
    is not available. Ensures system never crashes on unknown queueIds.
    """

    # Match metadata
    match_id: str = Field(description="Match ID")
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion")
    match_result: Literal["victory", "defeat"] = Field(description="Match outcome")

    # Game mode detection
    detected_mode: GameMode = Field(description="Detected game mode (will show is_supported=False)")

    # Basic stats (always available from Match-V5)
    kills: int = Field(ge=0)
    deaths: int = Field(ge=0)
    assists: int = Field(ge=0)
    total_damage_dealt: int = Field(ge=0)
    gold_earned: int = Field(ge=0)

    # Generic message
    fallback_message: str = Field(
        default=(
            "该游戏模式的专业分析功能正在开发中。"
            "当前仅提供基础数据展示。我们将在未来版本中支持更多模式的深度分析。"
        ),
        description="Generic message explaining lack of deep analysis",
    )

    # Optional: LLM-generated generic summary (V1 template-based)
    generic_summary: str | None = Field(
        default=None,
        description=(
            "Optional generic summary using V1 template logic. "
            "Example: '本场比赛你使用 {champion}，取得了 {kills}/{deaths}/{assists} 的战绩。'"
        ),
        max_length=500,
    )

    # Metadata
    algorithm_version: str = Field(default="v2.3-fallback")


# =============================================================================
# Example Data (for Documentation & Testing)
# =============================================================================

EXAMPLE_ARAM_REPORT = V23ARAMAnalysisReport(
    match_id="NA1_5500000000",
    summoner_name="TestPlayer",
    champion_name="Jinx",
    match_result="victory",
    overall_score=78.5,
    teamfight_metrics=V23ARAMTeamfightMetrics(
        total_teamfights=12,
        damage_share_in_teamfights=0.28,
        damage_taken_share=0.15,
        avg_survival_time_in_teamfights=18.5,
        deaths_before_teamfight_end=2,
        kills_participation_rate=0.82,
    ),
    build_adaptation=V23ARAMBuildAdaptation(
        enemy_ap_threat_level="high",
        enemy_ad_threat_level="medium",
        player_mr_items=2,
        player_armor_items=1,
        build_adaptation_score=75.0,
        recommended_item_adjustments=["考虑将最后一件输出装备替换为女妖面纱，提升对敌方AP的生存率"],
    ),
    combat_score=82.3,
    teamplay_score=74.2,
    analysis_summary=(
        "本场ARAM比赛你的整体表现优秀。在团战中，你的伤害占比达到28%，"
        "排名队伍第二，说明你的输出能力很强。但是，你有2次在团战结束前阵亡，"
        "这些过早死亡导致团队失去了后续的输出火力。建议在团战中注意走位，"
        "优先击杀敌方威胁目标（如敌方ADC），同时保持安全距离避免被集火。"
        "出装方面，你针对敌方高AP阵容购买了2件魔抗装备，这是正确的选择。"
    ),
    improvement_suggestions=[
        "在团战中保持后排站位，避免提前进场被敌方控制链击杀",
        "优先攻击敌方ADC和法师，而非前排坦克",
        "考虑购买水银鞋替换攻速鞋，以应对敌方多重控制",
    ],
    algorithm_version="v2.3-aram-lite",
)

EXAMPLE_ARENA_REPORT = V23ArenaAnalysisReport(
    match_id="NA1_5600000000",
    summoner_name="TestPlayer",
    champion_name="Yasuo",
    partner_summoner_name="Partner1",
    partner_champion_name="Malphite",
    final_placement=2,
    overall_score=81.2,
    rounds_played=6,
    rounds_won=4,
    round_performances=[
        V23ArenaRoundPerformance(
            round_number=1,
            round_result="win",
            damage_dealt=3500,
            damage_taken=1200,
            kills=2,
            deaths=0,
            positioning_score=85.0,
        ),
        # ... more rounds
    ],
    augment_analysis=V23ArenaAugmentAnalysis(
        augments_selected=["猛攻", "韧性", "疾行"],
        augment_synergy_with_champion=(
            "你选择的【猛攻】增强符文与你的刺客英雄Yasuo配合良好，提升了爆发伤害。"
            "【韧性】在后期对抗敌方控制链时发挥了关键作用。"
        ),
        augment_synergy_with_partner=(
            "你的队友Malphite选择了【坚韧】符文，配合你的输出型符文形成了前排+后排的平衡组合。"
        ),
        alternative_augment_suggestion=(
            "在第3轮时，如果选择【生命窃取】而非【疾行】，"
            "可能能更好地应对敌方的消耗战术，提升持续作战能力。"
        ),
    ),
    combat_score=85.6,
    duo_synergy_score=78.3,
    analysis_summary=(
        "本场Arena比赛你与队友配合良好，最终获得第2名。你和Malphite的组合（Yasuo+Malphite）"
        "具有强大的控制链和爆发能力。在前4轮中，你们充分利用了Malphite的大招开团优势，"
        "配合Yasuo的后续输出，成功击败了多个对手。然而，在第5轮对阵第一名队伍时，"
        "你在团战中过早进场，导致被集火击杀，队友Malphite独木难支。建议在面对实力相近的对手时，"
        "等待队友先手开团，你作为输出位应该在敌方技能交完后再进场收割。"
    ),
    improvement_suggestions=[
        "等待队友Malphite大招开团后再进场，避免提前暴露被集火",
        "在选择增强符文时，考虑队伍整体缺少的属性（如生存、控制、输出）",
        "在劣势回合中，优先保护队友而非单独追击敌方，保持2v2的数量优势",
    ],
    algorithm_version="v2.3-arena-lite",
)


# =============================================================================
# Strategy Pattern Interface (CLI 2 Addition for V2.3)
# =============================================================================

from abc import ABC, abstractmethod
from typing import Any


class AnalysisStrategy(ABC):
    """Abstract strategy interface for mode-specific analysis (Strategy Pattern).

    Each game mode (SR, ARAM, Arena, Fallback) implements this interface
    with mode-specific logic for data processing, scoring, and LLM analysis.

    Design Principles:
    - Single Responsibility: Each strategy handles ONE game mode
    - Open/Closed: New modes can be added without modifying existing strategies
    - Dependency Inversion: Celery task depends on abstraction, not concrete strategies
    """

    @abstractmethod
    async def execute_analysis(
        self,
        match_data: dict[str, Any],
        timeline_data: dict[str, Any],
        requester_puuid: str,
        discord_user_id: str,
        user_profile_context: str | None = None,
        timeline_evidence: Any | None = None,
    ) -> dict[str, Any]:
        """Execute mode-specific analysis pipeline.

        This method encapsulates the entire analysis flow for a specific game mode:
        1. Data extraction and mode-specific cleaning
        2. Score calculation using mode-appropriate metrics
        3. LLM prompt construction with mode-specific templates
        4. JSON validation using mode-specific Pydantic schemas
        5. Graceful error handling and degradation

        Args:
            match_data: Raw Match-V5 match details
            timeline_data: Raw Match-V5 timeline data
            requester_puuid: PUUID of user who requested analysis
            discord_user_id: Discord user ID (for personalization)
            user_profile_context: V2.2 personalization context (optional)
            timeline_evidence: V2.1 Timeline evidence (optional, SR only)

        Returns:
            Dict with keys:
                - score_data: Analysis results (dict from Pydantic model)
                - metrics: LLM metrics (tokens, latency, cost, degraded)
                - mode: Game mode label (e.g., "sr", "aram", "fallback")

        Raises:
            Exception: Strategy-specific errors (logged by implementation)
        """
        pass

    @abstractmethod
    def get_mode_label(self) -> str:
        """Get lowercase mode label for metrics and logging.

        Returns:
            Mode string (e.g., "sr", "aram", "arena", "fallback")
        """
        pass
