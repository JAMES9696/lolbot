"""Unit tests for sanitized LLM context construction."""

from __future__ import annotations

from typing import Any

from src.contracts.analysis_results import V1ScoreSummary
from src.tasks import analysis_tasks


def _sample_summary(raw_stats: dict[str, Any]) -> V1ScoreSummary:
    return V1ScoreSummary(
        combat_score=70.0,
        economy_score=65.0,
        vision_score=55.0,
        objective_score=60.0,
        teamplay_score=72.0,
        growth_score=68.0,
        tankiness_score=50.0,
        damage_composition_score=62.0,
        survivability_score=58.0,
        cc_contribution_score=40.0,
        overall_score=67.5,
        raw_stats=raw_stats,
    )


def test_build_llm_context_includes_appendix_and_masks_ids() -> None:
    """Sanitized context should include appendix guidance and anonymized IDs."""

    raw_stats = {
        "kills": 7,
        "deaths": 3,
        "assists": 5,
        "cs": 210,
        "cs_per_min": 8.2,
        "vision_score": 25,
        "damage_dealt": 18000,
        "damage_taken": 14000,
    }
    summary = _sample_summary(raw_stats)

    llm_input = {
        "match_id": "NA1_1234567890",
        "game_duration_minutes": 25.5,
        "team_blue_avg_score": 61.2,
        "team_red_avg_score": 57.8,
        "player_scores": [{"participant_id": 1}, {"participant_id": 2}],
    }

    target_payload = {
        "summoner_name": "Tester",
        "champion_name": "Ahri",
        "champion_name_zh": "阿狸",
        "total_score": 70.0,
        "combat_efficiency": 71.0,
        "economic_management": 66.0,
        "objective_control": 60.0,
        "vision_control": 55.0,
        "team_contribution": 74.0,
        "kill_participation": 68.0,
        "cs_per_min": 8.2,
        "strengths": ["视野控图"],
        "improvements": ["经济节奏"],
    }

    context = analysis_tasks._build_llm_context(  # type: ignore[attr-defined]
        llm_input=llm_input,
        target_payload=target_payload,
        v1_summary=summary,
        match_id="NA1_1234567890",
        region="na1",
        queue_id=420,
        match_result="victory",
        game_mode_label="SR",
        correlation_id="correlation-abcdef123456",
        discord_user_id="123456789012345678",
        workflow_durations={"fetch": 123.4, "scoring": None},
    )

    assert "## Target Player Overview" in context
    assert "Tester" in context and "阿狸" in context
    assert "## Appendix (Only consult the appendix if the answer requires extra detail.)" in context
    assert "anon:5678" in context  # discord id masked suffix
    assert "Workflow Timings" in context
    assert "Match ID: NA1_1234567890" in context
