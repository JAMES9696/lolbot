"""Utility helpers for safely clamping text destined for Discord embeds.

These helpers guarantee that we never exceed Discord's strict length
constraints while keeping markdown/code block delimiters intact.
"""

from __future__ import annotations

from typing import Final

ELLIPSIS: Final[str] = "…"


def clamp_text(text: str, limit: int, *, preserve_markdown: bool = False) -> str:
    """Clamp arbitrary text to the given limit with a trailing ellipsis.

    When ``preserve_markdown`` is True, the helper attempts to keep matching
    code-fence delimiters (`````), preventing malformed embeds.
    """

    if not text:
        return ""

    if limit <= 0:
        return ""

    value = text.strip()
    if len(value) <= limit:
        return value

    truncated = value[: max(0, limit - len(ELLIPSIS))] + ELLIPSIS

    if not preserve_markdown:
        return truncated

    return _restore_markdown(truncated, original=value)


def clamp_field(text: str, limit: int = 950) -> str:
    """Clamp a Discord Embed field value (default <= 950 chars for safety)."""

    return clamp_text(text, limit, preserve_markdown=True)


def clamp_code_block(text: str, limit: int = 1000) -> str:
    """Clamp a code-block payload and ensure closing fences remain balanced."""

    if not text:
        return "``````"

    if limit <= 0:
        return "``````"

    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped

    truncated = clamp_text(stripped, limit, preserve_markdown=True)
    if truncated.startswith("```") and not truncated.endswith("```"):
        truncated = f"{truncated}\n```"
    return truncated


def _restore_markdown(candidate: str, *, original: str) -> str:
    """Attempt to restore matching markdown fences after truncation."""

    if candidate.count("```") % 2 == 1:
        # The opening fence is likely intact while the closing fence was trimmed.
        candidate = candidate.rstrip("`").rstrip() + "\n```"

    return candidate
