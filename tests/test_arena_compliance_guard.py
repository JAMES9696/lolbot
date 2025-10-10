import pytest

from src.core.compliance import check_arena_text_compliance, ComplianceError


def test_arena_compliance_blocks_winrate_and_percent():
    with pytest.raises(ComplianceError):
        check_arena_text_compliance("该增益的胜率为 55% ，推荐选择")
    with pytest.raises(ComplianceError):
        check_arena_text_compliance("win rate predicted at 68%")


def test_arena_compliance_allows_neutral_tips():
    # Should not raise
    check_arena_text_compliance("专注走位与控制技能衔接，避免无意义换血")
