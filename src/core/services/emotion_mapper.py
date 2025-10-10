"""Emotion mapping service for TTS voice modulation.

This service transforms V1 scoring algorithm output into emotion tags
for TTS (豆包 TTS) voice synthesis. Emotion tags control speech parameters
like speed, pitch, volume, and energy.

Architecture Notes:
- Pure function - no side effects
- Based on V1 five-dimensional scoring framework
- Supports 15 emotion tags from P4 research
- Used by CLI 2's analyze_match_task before database storage
"""

from typing import Any, Literal

from src.contracts.analysis_results import V1ScoreSummary

# Emotion tag type definition (from P4 TTS research)
EmotionTag = Literal[
    "excited",  # Exceptional performance, high scores
    "positive",  # Above-average, good game
    "proud",  # Strong achievement in specific dimension
    "neutral",  # Average/balanced performance
    "analytical",  # Close game, balanced scores
    "encouraging",  # Below average but showing potential
    "concerned",  # Poor performance, needs improvement
    "sympathetic",  # Struggled significantly
    "disappointed",  # Failed to meet expectations
    "critical",  # Critical failures, major issues
    "mocking",  # Extremely poor, sarcastic tone (use sparingly)
    "motivational",  # Comeback potential despite setbacks
    "cautious",  # Risky plays, unstable performance
    "reflective",  # Learning moment, growth opportunity
    "calm",  # Steady, consistent performance
]


def _arena_placement_to_emotion(placement: int, overall: float) -> EmotionTag:
    """Arena-specific emotion mapping by final placement with slight score influence.

    1 -> excited/proud, 2 -> positive, 3 -> reflective/neutral, 4 -> concerned/disappointed.
    Tie-breakers use overall score to pick the upbeat/neutral/concerned variant.
    """
    if placement <= 1:
        return "excited" if overall >= 80 else "proud"
    if placement == 2:
        return "positive" if overall >= 60 else "encouraging"
    if placement == 3:
        return "neutral" if overall >= 55 else "reflective"
    # placement >= 4
    return "concerned" if overall >= 40 else "disappointed"


def map_score_to_emotion(score_summary: V1ScoreSummary) -> EmotionTag:
    """Map V1 scoring output to TTS emotion tag.

    This function implements the emotion mapping logic designed in P4 phase.
    It analyzes the five-dimensional scores and overall performance to determine
    the most appropriate emotional tone for voice synthesis.

    Extended: Arena-aware mapping. If raw_stats indicate Arena placement,
    prioritize placement-based emotion mapping to better reflect Arena outcomes.

    Mapping Logic:
    1. If Arena placement available → map via placement heuristics
    2. Otherwise, check overall score first (primary indicator)
    3. Analyze dimension imbalances (e.g., high combat but low vision)
    4. Identify standout strengths or critical weaknesses
    5. Return emotion tag that best represents performance character

    Args:
        score_summary: V1 algorithm output with five-dimensional scores

    Returns:
        Emotion tag for TTS voice modulation
    """
    overall = score_summary.overall_score

    # Arena-aware override based on placement (if present)
    try:
        rs = getattr(score_summary, "raw_stats", {}) or {}
        if rs and (
            rs.get("is_arena")
            or rs.get("game_mode") == "Arena"
            or rs.get("queue_id") in (1700, 1710)
        ):
            placement = int(rs.get("placement") or 0)
            if placement:
                return _arena_placement_to_emotion(placement, overall)
    except Exception:
        # Non-fatal: fall back to score-based mapping
        pass

    # Tier 1: Exceptional Performance (90-100)
    if overall >= 90:
        return "excited"

    # Tier 2: Strong Performance (80-89)
    if overall >= 80:
        # Check for standout strengths
        if score_summary.combat_score >= 90 or score_summary.objective_score >= 90:
            return "proud"
        return "positive"

    # Tier 3: Above Average (70-79)
    if overall >= 70:
        # Check for balanced performance
        scores = [
            score_summary.combat_score,
            score_summary.economy_score,
            score_summary.vision_score,
            score_summary.objective_score,
            score_summary.teamplay_score,
        ]
        score_range = max(scores) - min(scores)

        if score_range < 15:  # Balanced across dimensions
            return "calm"
        return "positive"

    # Tier 4: Average Performance (60-69)
    if overall >= 60:
        # Check for volatile performance (high variance)
        scores = [
            score_summary.combat_score,
            score_summary.economy_score,
            score_summary.vision_score,
            score_summary.objective_score,
            score_summary.teamplay_score,
        ]
        score_range = max(scores) - min(scores)

        if score_range > 30:  # High imbalance
            return "cautious"

        # Check for growth potential (some dimensions strong)
        if any(s >= 70 for s in scores):
            return "encouraging"

        return "neutral"

    # Tier 5: Below Average (50-59)
    if overall >= 50:
        # Check for specific dimension failures
        if score_summary.vision_score < 40:  # Vision crisis
            return "concerned"

        # Check for comeback potential (strong combat despite loss)
        if score_summary.combat_score >= 65:
            return "motivational"

        return "reflective"

    # Tier 6: Poor Performance (40-49)
    if overall >= 40:
        # Check for critical weaknesses
        if score_summary.economy_score < 35:  # Economy disaster
            return "disappointed"

        # Check for multiple failures
        weak_dimensions = sum(
            1
            for s in [
                score_summary.combat_score,
                score_summary.economy_score,
                score_summary.objective_score,
            ]
            if s < 45
        )

        if weak_dimensions >= 2:
            return "critical"

        return "concerned"

    # Tier 7: Critical Performance (0-39)
    # Extremely poor performance - use supportive but serious tone
    if overall < 25:  # Catastrophic failure
        # Check if this was a complete mismatch (all dimensions terrible)
        if all(
            s < 30
            for s in [
                score_summary.combat_score,
                score_summary.economy_score,
                score_summary.objective_score,
            ]
        ):
            return "sympathetic"  # Player was clearly outmatched

        # Otherwise, critical but constructive
        return "critical"

    # Default for 25-39 range
    return "disappointed"


def map_score_to_emotion_dict(score_summary: V1ScoreSummary) -> dict[str, Any]:
    """Map score to emotion tag with additional TTS metadata.

    Extended version that returns emotion tag plus recommended TTS parameters
    based on P4 phase TTS research (豆包 emotion mapping).

    Args:
        score_summary: V1 algorithm output

    Returns:
        Dictionary with emotion tag and TTS parameters
        {
            "emotion": str,
            "speed": float (0.8-1.2),
            "pitch": float (0.9-1.1),
            "volume": float (0.9-1.1),
            "energy": str ("low"|"medium"|"high")
        }
    """
    emotion = map_score_to_emotion(score_summary)

    # TTS parameter mapping (from P4 research)
    tts_params = {
        "excited": {"speed": 1.1, "pitch": 1.05, "volume": 1.0, "energy": "high"},
        "positive": {"speed": 1.05, "pitch": 1.02, "volume": 1.0, "energy": "medium-high"},
        "proud": {"speed": 1.0, "pitch": 1.03, "volume": 1.05, "energy": "high"},
        "neutral": {"speed": 1.0, "pitch": 1.0, "volume": 1.0, "energy": "medium"},
        "analytical": {"speed": 0.98, "pitch": 1.0, "volume": 0.98, "energy": "medium"},
        "encouraging": {"speed": 1.02, "pitch": 1.01, "volume": 1.0, "energy": "medium"},
        "concerned": {"speed": 0.95, "pitch": 0.98, "volume": 0.95, "energy": "medium-low"},
        "sympathetic": {"speed": 0.92, "pitch": 0.97, "volume": 0.93, "energy": "low"},
        "disappointed": {"speed": 0.94, "pitch": 0.96, "volume": 0.95, "energy": "low"},
        "critical": {"speed": 0.96, "pitch": 0.98, "volume": 0.97, "energy": "medium"},
        "mocking": {"speed": 1.08, "pitch": 1.04, "volume": 1.0, "energy": "high"},
        "motivational": {"speed": 1.03, "pitch": 1.02, "volume": 1.02, "energy": "high"},
        "cautious": {"speed": 0.97, "pitch": 0.99, "volume": 0.97, "energy": "medium"},
        "reflective": {"speed": 0.93, "pitch": 0.98, "volume": 0.95, "energy": "low"},
        "calm": {"speed": 0.98, "pitch": 1.0, "volume": 0.98, "energy": "medium"},
    }

    return {"emotion": emotion, **tts_params[emotion]}
