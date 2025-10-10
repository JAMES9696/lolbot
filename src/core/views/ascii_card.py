from __future__ import annotations

"""ASCII/ANSI summary card renderer

Environment variables:
- CHIMERA_UI_THEME: "dark" | "neon" | "teamcolor" (borders/accent)
- CHIMERA_UI_STYLE: "emoji" | "block" | "ansi" (bar tail & coloring)
"""

from typing import Any
import os
import unicodedata

THEMES = {
    "dark": {"border": ("+", "-", "|"), "accent": "🕹️"},
    "neon": {"border": ("*", "=", "|"), "accent": "✨"},
    "teamcolor": {"border": ("#", "-", "|"), "accent": "🟦"},
}

# Notes:
# - CHIMERA_UI_THEME controls border/accent only.
# - CHIMERA_UI_STYLE chooses bar rendering:
#     * emoji (default): 20-seg bar + 🟩/🟨/🟥 tail
#     * block: 20-seg bar + ▓/▒/░ tail (high/med/low)
#     * ansi: colorized bar inside ```ansi code block


def _mode_is_arena(raw_stats: dict[str, Any] | None) -> bool:
    rs = raw_stats or {}
    return bool(
        rs.get("is_arena") or rs.get("game_mode") == "Arena" or rs.get("queue_id") in (1700, 1710)
    )


def _mode_is_aram(raw_stats: dict[str, Any] | None) -> bool:
    rs = raw_stats or {}
    return bool(rs.get("game_mode") == "ARAM" or rs.get("queue_id") == 450)


def _fmt(v: float | int | str | None) -> str:
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v or "-")


def _to_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Attr/dict-safe getter."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _display_width(text: str) -> int:
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        east = unicodedata.east_asian_width(ch)
        if east in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def _pad_to_width(text: str, width: int) -> str:
    pad = width - _display_width(text)
    if pad <= 0:
        return text
    return text + (" " * pad)


def _bar20(x: float) -> str:
    try:
        v = max(0.0, min(100.0, float(x)))
        filled = int(round(v / 5))  # 20 segments
        ascii_safe = str(
            os.getenv("UI_ASCII_SAFE", os.getenv("CHIMERA_ASCII_SAFE", "0"))
        ).lower() in ("1", "true", "yes", "on")
        if ascii_safe:
            bar = "#" * filled + "-" * (20 - filled)
            return bar
        bar = "█" * filled + "░" * (20 - filled)
        style = os.getenv("CHIMERA_UI_STYLE", "emoji").lower()
        if style == "block":
            tail = "▓" if v >= 70 else ("▒" if v >= 40 else "░")
            return bar + " " + tail
        if style == "ansi":
            color = "32" if v >= 70 else ("33" if v >= 40 else "31")
            return f"\x1b[{color}m{bar}\x1b[0m"
        # default emoji tail
        tail = "🟩" if v >= 70 else ("🟨" if v >= 40 else "🟥")
        return bar + " " + tail
    except Exception:
        return ""


def _top2(dim: dict[str, float]) -> list[tuple[str, float]]:
    items = sorted(dim.items(), key=lambda kv: kv[1], reverse=True)
    return items[:2]


def build_ascii_card(report: Any) -> str:
    """Return an ASCII/ANSI-friendly summary card for Discord code block."""
    name = str(_get(report, "summoner_name", ""))[:28]
    champ = str(_get(report, "champion_name", ""))[:18]
    sent = str(_get(report, "llm_sentiment_tag", ""))

    scores = _get(report, "v1_score_summary", {}) or {}
    overall = (
        scores.get("overall_score")
        if isinstance(scores, dict)
        else getattr(scores, "overall_score", 0.0)
    )
    raw = (
        scores.get("raw_stats", {})
        if isinstance(scores, dict)
        else getattr(scores, "raw_stats", {})
    )

    # Theme
    theme = os.getenv("CHIMERA_UI_THEME", "dark").lower()
    t = THEMES.get(theme, THEMES["dark"])
    b_t, b_h, b_v = t["border"]
    accent = t["accent"]

    # Header & top2
    # Avoid blank title when any side is empty
    left = champ if champ else "-"
    right = name if name else "-"
    title = f"{left} | {right}"[:50]

    def _val(key: str) -> float:
        if isinstance(scores, dict):
            return _to_float(scores.get(key, 0.0))
        return _to_float(getattr(scores, key, 0.0))

    if _mode_is_arena(raw if isinstance(raw, dict) else {}):
        dims = {
            "Combat": _val("combat_score"),
            "Duo": _val("teamplay_score"),
            "Surv": _val("survivability_score"),
            "Tank": _val("tankiness_score"),
            "DMG": _val("damage_composition_score"),
            "CC": _val("cc_contribution_score"),
        }
    elif _mode_is_aram(raw if isinstance(raw, dict) else {}):
        dims = {
            "Teamfight": _val("combat_score"),
            "Presence": _val("teamplay_score"),
            "Surv": _val("survivability_score"),
            "Tank": _val("tankiness_score"),
            "DMG": _val("damage_composition_score"),
            "CC": _val("cc_contribution_score"),
        }
    else:
        dims = {
            "Combat": _val("combat_score"),
            "Econ": _val("economy_score"),
            "Obj": _val("objective_score"),
            "Vision": _val("vision_score"),
            "Team": _val("teamplay_score"),
            "Surv": _val("survivability_score"),
        }
        # Extended SR dims (to align with embed fields)
        ext_dims = {
            "Growth": _val("growth_score"),
            "Tank": _val("tankiness_score"),
            "DMG": _val("damage_composition_score"),
            "CC": _val("cc_contribution_score"),
        }

    top = _top2(dims)

    # Get actual position/lane from raw_stats
    position = "-"
    if isinstance(raw, dict):
        # Priority: team_position > individual_position > lane
        pos = raw.get("team_position") or raw.get("individual_position") or raw.get("lane") or ""
        # Normalize position names
        pos_map = {
            "JUNGLE": "JG",
            "TOP": "TOP",
            "MIDDLE": "MID",
            "MID": "MID",
            "BOTTOM": "ADC",
            "BOT": "ADC",
            "UTILITY": "SUP",
            "SUPPORT": "SUP",
        }
        position = pos_map.get(pos.upper(), pos[:3].upper() if pos else "-")

    # Combine actual position + top 2 dimensions
    top_line = f"{accent} {position}: {top[0][0]} {top[0][1]:.1f} | {top[1][0]} {top[1][1]:.1f}"

    # Mode & rows
    is_arena = _mode_is_arena(raw if isinstance(raw, dict) else {})
    is_aram = _mode_is_aram(raw if isinstance(raw, dict) else {})
    if is_arena or is_aram:
        place = raw.get("placement") or "-"
        mode_tag = "Arena" if is_arena else "ARAM"
        mode_line = f"{mode_tag} | Place: {place} | Score: {_fmt(overall)}"
        c = _val("combat_score")
        duo = _val("teamplay_score")
        surv = _val("survivability_score")
        tank = _val("tankiness_score")
        dmg = _val("damage_composition_score")
        cc = _val("cc_contribution_score")
        rows = [
            f"⚔ Combat {_bar20(c)}",
            f"🤝 Duo    {_bar20(duo)}",
            f"💚 Surv   {_bar20(surv)}",
            f"🛡 Tank   {_bar20(tank)}",
            f"⚡ DMG    {_bar20(dmg)}",
            f"🎯 CC     {_bar20(cc)}",
        ]
    else:
        mode_line = f"SR | Overall: {_fmt(overall)}"
        c = _val("combat_score")
        e = _val("economy_score")
        o = _val("objective_score")
        v = _val("vision_score")
        t = _val("teamplay_score")
        s = _val("survivability_score")
        rows = [
            f"⚔ Combat {_bar20(c)}",
            f"💰 Econ   {_bar20(e)}",
            f"🎯 Obj    {_bar20(o)}",
            f"👁 Vision {_bar20(v)}",
            f"🤝 Team   {_bar20(t)}",
            f"💚 Surv   {_bar20(s)}",
        ]
        # Append extended SR rows
        g = ext_dims["Growth"]
        tk = ext_dims["Tank"]
        dm = ext_dims["DMG"]
        cc = ext_dims["CC"]
        rows_ext = [
            f"📊 Growth {_bar20(g)}",
            f"🛡 Tank   {_bar20(tk)}",
            f"⚡ DMG    {_bar20(dm)}",
            f"🎯 CC     {_bar20(cc)}",
        ]

    # Build box
    inner = [
        f" {title}",
        f" {top_line}",
        f" {mode_line}",
        *[f" {r}" for r in rows[:4]],
        *[f" {r}" for r in rows[4:6]],
    ]
    # Add extended rows only for SR mode
    if not (is_arena or is_aram):
        inner.extend([f" {r}" for r in rows_ext])
    inner += [
        f" Sentiment: [{sent}]",
    ]
    inner_width = max(_display_width(s) for s in inner)
    width = max(56, inner_width + 2)
    top_border = b_t + (b_h * (width - 2)) + b_t
    mid = [b_v + _pad_to_width(s, width - 2) + b_v for s in inner]
    bottom_border = top_border
    return "\n".join([top_border, *mid, bottom_border])
