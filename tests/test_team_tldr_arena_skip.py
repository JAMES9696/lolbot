import pytest
from src.core.domain.team_policies import (
    find_soft_hallucination_tokens,
    should_run_team_full_token,
    tldr_contains_hallucination,
)


def test_should_run_team_full_token_arena_false():
    # 环境开启，但Arena模式必须跳过
    assert should_run_team_full_token("arena", "1") is False
    assert should_run_team_full_token("ARENA", "true") is False
    assert should_run_team_full_token("arena", "on") is False


def test_should_run_team_full_token_sr_true():
    # SR/ARAM在开关开启时应运行
    for mode in ("summoners_rift", "aram", "unknown", None):
        assert should_run_team_full_token(mode, "1") is True


@pytest.mark.parametrize(
    "msg",
    [
        "由于比赛数据完全缺失（0分钟时长、所有指标为0），无法生成有效的战报分析。",
        "数据缺失，时长为零，无法进行有效分析",
        "请提供完整的比赛数据",
        "无法生成战报 | 比赛数据完全缺失 | 建议：请检查比赛ID是否正确",
        "强项 暂无 | 弱项 暂无",
    ],
)
def test_tldr_contains_hallucination_true(msg: str):
    assert tldr_contains_hallucination(msg) is True


def test_tldr_contains_hallucination_false():
    ok = "强项：前期节奏；短板：团战站位；建议：先拉扯后进场。"
    assert tldr_contains_hallucination(ok) is False


def test_find_soft_hints() -> None:
    text = "数据加载受限，仅显示基础评分，但并非完全缺失。"
    soft_hits = find_soft_hallucination_tokens(text)
    assert soft_hits == {"数据加载受限", "仅显示基础评分"}
