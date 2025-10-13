"""sr_enrichment 诊断逻辑的单元测试."""

from __future__ import annotations

import pytest

from src.tasks.analysis_tasks import diagnose_sr_enrichment_gap


def _make_timeline(frames: list[dict] | None = None, participants: list[str] | None = None) -> dict:
    """构造最小化的 Timeline 数据."""
    return {
        "info": {"frames": frames or []},
        "metadata": {"participants": participants or []},
    }


def _make_match_details(puuid: str = "target", participant_id: int = 3) -> dict:
    """构造最小化的 Match Details 数据."""
    return {
        "info": {
            "participants": [
                {
                    "puuid": puuid,
                    "participantId": participant_id,
                    "teamId": 100,
                    "individualPosition": "MIDDLE",
                }
            ]
        }
    }


@pytest.mark.parametrize(
    "timeline,match_details,participant_id,expected_reason",
    [
        (_make_timeline(frames=[]), _make_match_details(), None, "timeline_missing_frames"),
        (
            _make_timeline(
                frames=[{"participantFrames": {}}],
                participants=["ally", "target"],
            ),
            _make_match_details(puuid="another"),
            None,
            "participant_not_resolved",
        ),
    ],
)
def test_diagnose_sr_enrichment_missing_cases(
    timeline: dict,
    match_details: dict,
    participant_id: int | None,
    expected_reason: str,
) -> None:
    """验证当 Timeline/Details 缺失导致增强失败时能给出缺失原因."""
    result = diagnose_sr_enrichment_gap(
        game_mode="SR",
        timeline_data=timeline,
        match_details=match_details,
        participant_id=participant_id,
        sr_extra=None,
        target_puuid="target",
    )

    assert result["state"] == "missing"
    assert result["reason"] == expected_reason


def test_diagnose_sr_enrichment_available() -> None:
    """验证当增强数据存在时返回 available 状态."""
    sr_extra = {"gold_diff_10": 120, "duration_min": 28.5}
    result = diagnose_sr_enrichment_gap(
        game_mode="SR",
        timeline_data=_make_timeline(frames=[{"participantFrames": {"3": {"minionsKilled": 80}}}]),
        match_details=_make_match_details(),
        participant_id=3,
        sr_extra=sr_extra,
        target_puuid="target",
    )

    assert result["state"] == "available"
    assert result["payload"] == {"keys": sorted(sr_extra.keys())}
