import os
from typing import Any

from src.core.views.ascii_card import _bar20  # reuse bar renderer


def _style() -> str:
    return os.getenv("CHIMERA_UI_STYLE", "emoji").lower()


def _fmt(x: float) -> str:
    try:
        return f"{float(x):.1f}"
    except Exception:
        return "0.0"


def _avg(vals: list[float]) -> float:
    return round(sum(vals) / max(1, len(vals)), 1)


def build_team_receipt(report: Any) -> str:
    """Build a receipt-style overview for team analysis summary.

    Expects a V2TeamAnalysisReport-like object with team_analysis list.
    Will compute team averages and target player's six-dim bars.
    """
    players = getattr(report, "team_analysis", []) or []
    target_name = getattr(report, "target_player_name", "-")
    mode = getattr(report, "game_mode", "summoners_rift")

    dims = [
        ("Combat", [float(getattr(p, "combat_score", 0.0)) for p in players]),
        ("Econ", [float(getattr(p, "economy_score", 0.0)) for p in players]),
        ("Vision", [float(getattr(p, "vision_score", 0.0)) for p in players]),
        ("Obj", [float(getattr(p, "objective_score", 0.0)) for p in players]),
        ("Team", [float(getattr(p, "teamplay_score", 0.0)) for p in players]),
    ]
    if players and hasattr(players[0], "survivability_score"):
        dims.append(("Surv", [float(getattr(p, "survivability_score", 0.0)) for p in players]))

    # pick target (rank 1 in team_analysis indicates best; otherwise just player 0)
    target = None
    try:
        target = next(p for p in players if getattr(p, "summoner_name", "") == target_name)
    except StopIteration:
        target = players[0] if players else None

    # Header
    ascii_safe = str(os.getenv("UI_ASCII_SAFE", os.getenv("CHIMERA_ASCII_SAFE", "0"))).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    title = (
        f"[RECEIPT] TEAM | {mode.upper()}" if ascii_safe else f"🧾 TEAM RECEIPT | {mode.upper()}"
    )
    sub = f"Target: {target_name}"[:54]
    line = "-" * 54

    rows = []
    if target:
        for label, vals in dims:
            if not vals:
                continue
            avg = _avg(vals)
            val = getattr(
                target,
                {
                    "Combat": "combat_score",
                    "Econ": "economy_score",
                    "Vision": "vision_score",
                    "Obj": "objective_score",
                    "Team": "teamplay_score",
                    "Surv": "survivability_score",
                }[label],
                0.0,
            )
            rows.append(
                f"{label.ljust(8,'.')} {_fmt(val)}  {_bar20(float(val))}  (avg {_fmt(avg)})"
            )

    out = [title, line, sub, line]
    out.extend(rows[:3])
    out.extend(rows[3:6])
    out.append(line)
    return "\n".join(out)
