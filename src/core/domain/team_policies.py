"""Team-level domain policies (pure functions).

保持零外部依赖，作为测试缝使用；供任务层按需调用。
"""

from __future__ import annotations


# 以严重程度区分的幻觉模式，确保“温和提示”不会误触降级流程
CRITICAL_HALLUCINATION_PATTERNS: tuple[str, ...] = (
    "数据完全缺失",
    "比赛数据完全缺失",
    "比赛数据未同步",
    "数据为空",
    "数据异常",
    "时长为零",
    "0分钟时长",
    "所有指标为0",
    "无法进行有效",
    "无法生成有效",
    "无法生成战报",
    "请提供完整的比赛数据",
    "检查比赛ID是否正确",
    "等待5-10分钟后重新查询",
    "强项 暂无 | 弱项 暂无",
)

SOFT_HALLUCINATION_HINTS: tuple[str, ...] = (
    "数据缺失",
    "比赛数据缺失",
    "数据加载受限",
    "暂无时间线增强数据",
    "仅显示基础评分",
)


def detect_hallucination_tokens(text: str) -> tuple[set[str], set[str]]:
    """Return sets of matched critical and soft hallucination tokens."""
    t = (text or "").strip()
    if not t:
        return set(), set()

    critical_hits = {pattern for pattern in CRITICAL_HALLUCINATION_PATTERNS if pattern in t}
    # 避免 soft 与 critical 重复统计
    soft_hits = {
        pattern
        for pattern in SOFT_HALLUCINATION_HINTS
        if pattern in t and pattern not in critical_hits
    }
    return critical_hits, soft_hits


def tldr_contains_hallucination(text: str) -> bool:
    critical_hits, _ = detect_hallucination_tokens(text)
    return bool(critical_hits)


def find_soft_hallucination_tokens(text: str) -> set[str]:
    _, soft_hits = detect_hallucination_tokens(text)
    return soft_hits


def should_run_team_full_token(game_mode: str | None, team_ft_env_value: str | None) -> bool:
    ft_on = (team_ft_env_value or "").lower() in ("1", "true", "yes", "on")
    if not ft_on:
        return False
    return (game_mode or "").lower() != "arena"


__all__ = [
    "CRITICAL_HALLUCINATION_PATTERNS",
    "SOFT_HALLUCINATION_HINTS",
    "detect_hallucination_tokens",
    "tldr_contains_hallucination",
    "find_soft_hallucination_tokens",
    "should_run_team_full_token",
]
