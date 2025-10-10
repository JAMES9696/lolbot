"""Analysis Strategy Factory for V2.3 Multi-Mode Support.

This factory implements the Strategy Pattern by dynamically selecting
the appropriate analysis strategy based on the detected game mode.

Design Principles:
- Open/Closed Principle: New game modes can be added without modifying existing code
- Dependency Inversion: Depends on AnalysisStrategy abstraction, not concrete strategies
- Lazy Initialization: Avoids circular imports by importing concrete strategies on-demand

Author: CLI 2 (Backend)
Date: 2025-10-07
Phase: V2.3
"""

from typing import TYPE_CHECKING

from src.contracts.v23_multi_mode_analysis import GameMode

if TYPE_CHECKING:
    # Type-checking only imports to avoid circular dependencies
    from src.contracts.v23_multi_mode_analysis import AnalysisStrategy


class AnalysisStrategyFactory:
    """Factory for creating mode-specific analysis strategies.

    This factory uses lazy initialization to avoid circular imports and
    implements the Factory Pattern for dynamic strategy selection.

    Thread Safety: Instances are stateless and thread-safe.
    Caching: No caching is implemented - strategies are lightweight to instantiate.

    Example Usage:
        >>> from src.contracts.v23_multi_mode_analysis import detect_game_mode
        >>> factory = AnalysisStrategyFactory()
        >>> game_mode = detect_game_mode(match_data)
        >>> strategy = factory.get_strategy(game_mode)
        >>> result = await strategy.execute_analysis(match_data, timeline_data, ...)
    """

    def get_strategy(self, game_mode: GameMode) -> "AnalysisStrategy":
        """Get the appropriate analysis strategy for the given game mode.

        This method uses lazy imports to avoid circular dependencies and
        defaults to FallbackStrategy for unknown or unsupported modes.

        Args:
            game_mode: Detected game mode from match data (via detect_game_mode())

        Returns:
            Concrete AnalysisStrategy implementation for the mode

        Strategy Mapping:
            - GameMode(mode="SR") → SRStrategy (full V2.2 analysis)
            - GameMode(mode="ARAM") → ARAMStrategy (V1-Lite + ARAM-specific)
            - GameMode(mode="Arena") → ArenaStrategy (V1-Lite + Arena-specific)
            - GameMode(mode="Fallback") → FallbackStrategy (basic analysis)
            - Unknown/Invalid → FallbackStrategy (graceful degradation)

        Raises:
            ImportError: If concrete strategy module is missing (should not happen in production)
        """
        mode_str = game_mode.mode.lower()

        try:
            if mode_str == "sr":
                # Summoner's Rift: Full V2.2 analysis (personalization + timeline evidence)
                from src.core.services.strategies.sr_strategy import SRStrategy

                return SRStrategy()

            elif mode_str == "aram":
                # ARAM: V1-Lite analysis (CLI 4's ARAM-specific metrics)
                from src.core.services.strategies.aram_strategy import ARAMStrategy

                return ARAMStrategy()

            elif mode_str == "arena":
                # Arena: V1-Lite analysis (CLI 4's Arena-specific metrics)
                from src.core.services.strategies.arena_strategy import ArenaStrategy

                return ArenaStrategy()

            else:
                # Fallback: Basic analysis for unsupported/unknown modes
                from src.core.services.strategies.fallback_strategy import (
                    FallbackStrategy,
                )

                return FallbackStrategy()

        except ImportError as e:
            # Graceful degradation: If strategy module is missing, use FallbackStrategy
            # This should never happen in production (indicates deployment issue)
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                "Failed to import strategy for mode %s: %s. Falling back to FallbackStrategy.",
                mode_str,
                str(e),
                exc_info=True,
            )

            # Import FallbackStrategy as last resort
            from src.core.services.strategies.fallback_strategy import FallbackStrategy

            return FallbackStrategy()

    def get_strategy_safeguarded(
        self,
        game_mode: GameMode,
        *,
        raw_gamemode: str | None = None,
        participants_len: int | None = None,
    ) -> "AnalysisStrategy":
        """Double-guard mode resolution using queueId + gameMode + participants.

        This method mirrors the early unification logic used by tasks so callers
        can rely on a single entry point for stable strategy selection.
        """
        # Base from queueId
        base = game_mode.mode.lower()
        # From raw string
        gm_upper = (raw_gamemode or "").upper()
        from_str = {
            "CLASSIC": "sr",
            "ARAM": "aram",
            "CHERRY": "arena",
        }.get(gm_upper)

        resolved = from_str or base
        # Heuristic: Arena + 10 participants → SR
        try:
            n = int(participants_len or 0)
            if resolved == "arena" and n == 10:
                resolved = "sr"
        except Exception:
            pass

        # Build a lightweight GameMode-like with resolved label
        from types import SimpleNamespace as _NS

        gm_like = _NS(mode=resolved.upper())
        return self.get_strategy(gm_like)  # type: ignore[arg-type]


def create_strategy_for_queue(queue_id: int) -> "AnalysisStrategy":
    """Convenience function: Detect game mode from queueId and return strategy.

    This is a higher-level utility that combines mode detection and strategy
    creation into a single call for common use cases.

    Args:
        queue_id: Riot API queueId from match data (e.g., 420=Ranked Solo, 450=ARAM)

    Returns:
        Appropriate AnalysisStrategy for the detected game mode

    Example:
        >>> strategy = create_strategy_for_queue(queue_id=420)  # Returns SRStrategy
        >>> result = await strategy.execute_analysis(...)
    """
    from src.contracts.v23_multi_mode_analysis import detect_game_mode

    game_mode = detect_game_mode(queue_id)
    factory = AnalysisStrategyFactory()
    return factory.get_strategy(game_mode)
