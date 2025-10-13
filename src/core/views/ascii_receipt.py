"""Receipt-style ASCII/ANSI header for Discord embeds.

Inspired by thermal receipt visuals: compact, playful, readable.

Env toggles:
- CHIMERA_UI_STYLE: emoji|block|ansi (same semantics as ascii_card)
- CHIMERA_UI_THEME: dark|neon|teamcolor (affects some glyph choices)
"""

from typing import Any
import os

from .ascii_card import _bar20, _to_float  # reuse utilities


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _fmt1(x: float) -> str:
    try:
        return f"{float(x):.1f}"
    except Exception:
        return "0.0"


def _emojify(tag: str) -> str:
    style = os.getenv("CHIMERA_UI_STYLE", "emoji").lower()
    if style == "emoji":
        return tag
    return ""  # keep plain for block/ansi


def build_ascii_receipt(report: Any) -> str:
    name = str(_get(report, "summoner_name", "")).strip()[:28]
    champ = str(_get(report, "champion_name", "")).strip()[:18]
    sent = str(_get(report, "llm_sentiment_tag", ""))

    scores = _get(report, "v1_score_summary", {}) or {}
    raw = scores.get("raw_stats", {}) if isinstance(scores, dict) else _get(scores, "raw_stats", {})
    is_arena = bool(
        (raw or {}).get("is_arena")
        or (raw or {}).get("queue_id") in (1700, 1710)
        or (raw or {}).get("game_mode") == "Arena"
    )
    is_aram = bool((raw or {}).get("queue_id") == 450 or (raw or {}).get("game_mode") == "ARAM")

    # Dimensions (mode-aware)
    def v(k: str) -> float:
        return (
            _to_float(scores.get(k, 0.0))
            if isinstance(scores, dict)
            else _to_float(_get(scores, k, 0.0))
        )

    if is_arena or is_aram:
        dims = [
            ("Combat", v("combat_score")),
            ("Duo", v("teamplay_score")),
            ("Surv", v("survivability_score")),
            ("Tank", v("tankiness_score")),
            ("DMG", v("damage_composition_score")),
            ("CC", v("cc_contribution_score")),
        ]
        mode_tag = "ARENA" if is_arena else "ARAM"
    else:
        dims = [
            ("Combat", v("combat_score")),
            ("Econ", v("economy_score")),
            ("Obj", v("objective_score")),
            ("Vision", v("vision_score")),
            ("Team", v("teamplay_score")),
            ("Surv", v("survivability_score")),
        ]
        mode_tag = "SR"

    overall = v("overall_score")
    # Top2 dims
    top2 = sorted(dims, key=lambda kv: kv[1], reverse=True)[:2]

    # Header
    line = "-" * 54
    title = f"{_emojify('🧾 ')}CHIMERA {mode_tag} RECEIPT".ljust(54)
    sub = f"{champ or '-'} · {name or '-'}"[:54]

    # Items
    items: list[str] = [f"{k.ljust(10, '.')} {_fmt1(s)}  {_bar20(s)}" for k, s in dims[:3]] + [
        f"{k.ljust(10, '.')} {_fmt1(s)}  {_bar20(s)}" for k, s in dims[3:6]
    ]

    # Totals / highlights
    highlights = (
        f">> BEST: {top2[0][0]} {_fmt1(top2[0][1])} | NEXT: {top2[1][0]} {_fmt1(top2[1][1])}"
    )
    total = f"TOTAL SCORE: {overall:.1f}/100"
    emo = f"EMO: [{sent}]"

    # Footer fun: pseudo barcode
    barcode = "|| ||| | || |||| | ||| |"

    out = [
        title,
        line,
        sub,
        line,
        *items,
        line,
        highlights,
        total,
        emo,
        line,
        barcode,
    ]
    return "\n".join(out)
