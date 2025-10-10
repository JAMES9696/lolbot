"""Compatibility module for TTS port.

Exposes the `TTSPort` interface from the unified `src.core.ports` package.
Keeping this shim preserves import paths referenced in design docs while
avoiding duplication and ensuring a single source of truth.
"""

from src.core.ports import TTSPort

__all__ = ["TTSPort"]
