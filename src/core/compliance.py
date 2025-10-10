"""Compliance utilities for mode-specific policy enforcement (V2.4).

Focus: Riot policy for Arena mode — DO NOT display win rates, percent-based
predictions, or any competitive advantage information.

Usage:
    from src.core.compliance import check_arena_text_compliance, ComplianceError
    check_arena_text_compliance(text)

KISS: string-based detection with curated sensitive keywords; extend as needed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


class ComplianceError(ValueError):
    """Raised when content violates policy for a given game mode."""


_ARENA_BANNED_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Chinese terms
    re.compile(r"胜率"),
    re.compile(r"预测"),
    # Percentages (e.g., 12%, 55.3 %). Allow harmless things like time 100%? We block % conservatively for Arena.
    re.compile(r"\d+\s*%"),
    # English fallbacks
    re.compile(r"win\s*rate", re.IGNORECASE),
    re.compile(r"prediction|predicts|predicted", re.IGNORECASE),
)


def find_patterns(text: str, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    for pat in patterns:
        m = pat.search(text)
        if m:
            hits.append(pat.pattern)
    return hits


def check_arena_text_compliance(text: str) -> None:
    """Validate Arena text is free of policy-violating phrasing.

    Raises:
        ComplianceError: when any banned pattern is detected.
    """
    if not text:
        return
    hits = find_patterns(text, _ARENA_BANNED_PATTERNS)
    if hits:
        raise ComplianceError(f"Arena compliance violation: {', '.join(hits)}")
