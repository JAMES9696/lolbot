"""Fallback strategies for graceful degradation (no external calls)."""

from .llm_fallback import generate_fallback_narrative

__all__ = ["generate_fallback_narrative"]
