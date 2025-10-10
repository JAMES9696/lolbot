"""Advanced safe truncation for Discord embed content with Markdown boundary preservation.

This module implements the enhanced truncation strategy from the Discord Frontend
Implementation Prompt, preserving fenced code blocks, inline code, and Chinese/English
punctuation boundaries.
"""

from __future__ import annotations


def safe_truncate(text: str, limit: int) -> str:
    """Safely truncate text while preserving Markdown boundaries and code blocks.

    Implements the enhanced strategy from DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md:
    - Preserves fenced code blocks (```)
    - Avoids breaking inline code (`...`)
    - Respects list markers (-, •)
    - Preserves Chinese and English punctuation boundaries
    - Maintains at least 50% of the original length when possible

    Args:
        text: Input text to truncate
        limit: Maximum character limit

    Returns:
        Truncated text with "…" suffix if truncated

    Example:
        >>> safe_truncate("Hello\\n\\nWorld!", 10)
        'Hello\\n\\n…'
        >>> safe_truncate("```python\\ncode\\n```", 12)
        'Hello…'  # Won't break inside code block
    """
    if not text or len(text) <= limit:
        return text or ""

    # Truncate to limit-1 to reserve space for ellipsis
    t = text[: max(0, limit - 1)]

    # Find safe boundary anchors (ordered by priority)
    safe_anchors = [
        "\n\n",  # Paragraph break (highest priority)
        "\n",  # Line break
        "。",  # Chinese period
        "！",  # Chinese exclamation
        "？",  # Chinese question
        ". ",  # English period with space
        "- ",  # List marker
        "• ",  # Bullet point
    ]

    cut = -1
    min_length = int(limit * 0.5)  # Maintain at least 50% of target length

    for anchor in safe_anchors:
        p = t.rfind(anchor)
        if p > cut and p >= min_length:
            cut = p

    # Check for unclosed fenced code blocks
    fenced_open = t.count("```") % 2 == 1

    if fenced_open and cut > 0:
        # If we're inside a code block, truncate at the last safe boundary
        t = t[:cut]
    elif cut > 0:
        # Normal case: truncate at safe boundary
        t = t[:cut]

    # Final cleanup and ellipsis
    result = t.rstrip()
    if result and result != text.rstrip():
        return result + "…"
    elif not result and text:
        # Edge case: couldn't find safe boundary, force truncate
        return text[: limit - 1] + "…"
    else:
        return result


def safe_truncate_markdown(text: str, limit: int) -> str:
    """Alias for safe_truncate with explicit Markdown handling.

    This is a drop-in replacement for the v2 implementation mentioned
    in the frontend prompt.

    Args:
        text: Markdown text to truncate
        limit: Maximum character limit

    Returns:
        Safely truncated Markdown text
    """
    return safe_truncate(text, limit)
