"""V1 Scoring Algorithm - Five-Dimensional Performance Evaluation.

This module implements the core scoring logic for League of Legends match analysis.
Adheres to SOLID principles with pure domain logic (zero I/O operations).

Five Dimensions:
1. Combat Efficiency (30%)
2. Economic Management (25%)
3. Objective Control (25%)
4. Vision & Map Control (10%)
5. Team Contribution (10%)
"""

from src.core.scoring.calculator import (
    analyze_full_match,
    calculate_total_score,
    generate_llm_input,
)
from src.core.scoring.models import MatchAnalysisOutput, PlayerScore

__all__ = [
    "PlayerScore",
    "MatchAnalysisOutput",
    "calculate_total_score",
    "analyze_full_match",
    "generate_llm_input",
]
