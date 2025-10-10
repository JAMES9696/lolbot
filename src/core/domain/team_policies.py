"""Team-level domain policies (pure functions).

保持零外部依赖，作为测试缝使用；供任务层按需调用。
"""
from __future__ import annotations

HALLUCINATION_PATTERNS: list[str] = [
    "数据缺失",
    "数据完全缺失",
    "比赛数据缺失",
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
]


def tldr_contains_hallucination(text: str) -> bool:
    t = (text or "").strip()
    return any(p in t for p in HALLUCINATION_PATTERNS)


def should_run_team_full_token(game_mode: str | None, team_ft_env_value: str | None) -> bool:
    ft_on = (team_ft_env_value or "").lower() in ("1", "true", "yes", "on")
    if not ft_on:
        return False
    return (game_mode or "").lower() != "arena"


__all__ = [
    "HALLUCINATION_PATTERNS",
    "tldr_contains_hallucination",
    "should_run_team_full_token",
]
