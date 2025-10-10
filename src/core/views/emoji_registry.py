"""Lightweight emoji registry with env overrides.

KISS: Provide a simple key→emoji lookup so views can decorate texts
without hard-coding guild-specific custom emoji IDs.

Usage:
    from src.core.views.emoji_registry import resolve_emoji
    e = resolve_emoji(f"champion:{champion_name}")

Override:
    Set CHIMERA_EMOJI_MAP env var to a JSON dict, e.g.
        {
          "champion:Garen": "<:Garen:123456789012345678>",
          "rune:Conqueror": "<:Conqueror:234567890123456789>"
        }
"""

from __future__ import annotations

import json
import os


_DEFAULTS: dict[str, str] = {
    # Champions (popular picks; fallback to thematic emoji)
    "champion:Garen": "🛡️",
    "champion:Darius": "🩸",
    "champion:Yasuo": "🌪️",
    "champion:Yone": "⚔️",
    "champion:Zed": "🗡️",
    "champion:Ahri": "🦊",
    "champion:Lux": "✨",
    "champion:Ashe": "🏹",
    "champion:Caitlyn": "🎯",
    "champion:Ezreal": "🔷",
    "champion:Vayne": "🦇",
    "champion:Lee Sin": "🥋",
    "champion:Thresh": "🪝",
    "champion:Leona": "☀️",
    "champion:Morgana": "🌑",
    # Runes (generic)
    "rune:Conqueror": "⚔️",
    "rune:Electrocute": "⚡",
    "rune:Summon Aery": "🕊️",
    "rune:Aftershock": "💥",
    "rune:Grasp of the Undying": "🌿",
    # Ranks (generic badges)
    "rank:Challenger": "🏆",
    "rank:Master": "💎",
    "rank:Diamond": "🔷",
    "rank:Platinum": "🧊",
    "rank:Gold": "🥇",
    "rank:Silver": "🥈",
    "rank:Bronze": "🥉",
}


def _load_overrides() -> dict[str, str]:
    raw = os.getenv("CHIMERA_EMOJI_MAP", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            # stringify keys/values defensively
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


_OVERRIDES = _load_overrides()


def resolve_emoji(key: str, default: str = "") -> str:
    """Resolve an emoji by key with env override and defaults.

    Args:
        key: lookup key, e.g., "champion:Garen" or "rune:Conqueror"
        default: fallback when not found

    Returns:
        Emoji string suitable for Discord, may be custom emoji markup.
    """
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    return _DEFAULTS.get(key, default)
