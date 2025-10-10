"""Fallback narrative generator used when LLM is unavailable.

KISS: Deterministic, template-based summary using V1 scoring output only.
No external calls, no randomness. Output is kept under ~800 chars.

Input schema: `MatchAnalysisOutput.model_dump(mode="json")` dict or equivalent.
"""

from __future__ import annotations

from typing import Any


def _pick_player(match_data: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the focused player: prefer MVP; otherwise first player."""
    players = match_data.get("player_scores") or []
    if not players:
        return None
    mvp_id = match_data.get("mvp_id")
    if mvp_id:
        for p in players:
            if p.get("participant_id") == mvp_id:
                return p
    return players[0]


def _format_strengths_improvements(p: dict[str, Any]) -> tuple[str, str]:
    strengths = p.get("strengths") or []
    improvements = p.get("improvements") or []
    s_part = "、".join(strengths[:3]) if strengths else "输出节奏"  # default sensible hint
    i_part = "、".join(improvements[:3]) if improvements else "视野布控"
    return s_part, i_part


def generate_fallback_narrative(match_data: dict[str, Any]) -> str:
    """Return a concise Chinese narrative when LLM fails.

    The tone matches the analytical style of /讲道理：
    - 一句话总评
    - 三点客观事实（来自 V1 维度）
    - 一条可执行建议
    """
    match_id = match_data.get("match_id", "unknown")
    duration_min = float(match_data.get("game_duration_minutes", 0.0) or 0.0)
    duration = f"{duration_min:.1f}"

    player = _pick_player(match_data)
    if not player:
        return (
            "本局数据解析服务临时不可用，已提供安全降级结果：\n"
            "- 比赛节奏稳定，关键事件分布均衡。\n"
            "- 建议稍后重试以获取完整 AI 叙事。"
        )

    name = player.get("participant_id", 0)
    total = float(player.get("total_score", 0.0) or 0.0)
    combat = float(player.get("combat_efficiency", 0.0) or 0.0)
    economy = float(player.get("economic_management", 0.0) or 0.0)
    vision = float(player.get("vision_control", 0.0) or 0.0)
    obj = float(player.get("objective_control", 0.0) or 0.0)
    team = float(player.get("team_contribution", 0.0) or 0.0)
    kda = player.get("kda", 0)
    cs = player.get("cs_per_min", 0.0)
    kp = float(player.get("kill_participation", 0.0) or 0.0)

    s_part, i_part = _format_strengths_improvements(player)

    summary = "优势明显" if total >= 80 else "发挥稳定" if total >= 60 else "有待提升"

    # Simple guidance based on the weakest dimension
    dims = {
        "对线/对拼": combat,
        "经济/发育": economy,
        "物件/推进": obj,
        "视野/控图": vision,
        "团队协同": team,
    }
    weakest_name = min(dims, key=dims.get)

    return (
        f"[降级模式] Match {match_id} | 用时 {duration} 分钟\n"
        f"总体结论：{summary}（综合 {total:.1f} 分）\n"
        f"客观事实：\n"
        f"- KDA {kda:.2f}，参团率 {kp:.0f}% ，分均补刀 {cs:.1f}\n"
        f"- 物件控制 {obj:.1f}，团队协同 {team:.1f}，视野 {vision:.1f}\n"
        f"- 优势点：{s_part}；改进点：{i_part}\n"
        f"执行建议：优先补强『{weakest_name}』维度，结合阵容节奏做一次小目标（先锋/一塔/河道视野）来转化优势。"
    )
