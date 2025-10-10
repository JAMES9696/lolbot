"""Development-time strict Discord embed validation with env toggle.

Implements CHIMERA_DEV_VALIDATE_DISCORD feature from the frontend prompt.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)


def dev_validate_embed(embed: discord.Embed) -> bool:
    """Validate embed in development mode if CHIMERA_DEV_VALIDATE_DISCORD=1.

    Args:
        embed: Discord embed to validate

    Returns:
        True if valid or validation disabled, False if invalid

    Raises:
        ValueError: If CHIMERA_DEV_STRICT=1 and validation fails
    """
    # Check if validation is enabled
    if not _is_dev_validation_enabled():
        return True

    from src.core.validation import validate_embed_strict

    result = validate_embed_strict(embed)

    if not result.is_valid:
        error_msg = f"Discord embed validation failed:\n{result}"
        logger.error(
            "Dev validation failed",
            extra={
                "validation_result": str(result),
                "errors": result.errors,
                "warnings": result.warnings,
                "total_chars": result.total_chars,
            },
        )

        # Fail-fast if strict mode enabled
        if _is_dev_strict_enabled():
            raise ValueError(error_msg)

        return False

    # Log warnings even if valid
    if result.warnings:
        logger.warning(
            "Discord embed validation warnings",
            extra={
                "warnings": result.warnings,
                "total_chars": result.total_chars,
            },
        )

    return True


def _is_dev_validation_enabled() -> bool:
    """Check if CHIMERA_DEV_VALIDATE_DISCORD=1."""
    val = str(os.getenv("CHIMERA_DEV_VALIDATE_DISCORD", "0")).lower()
    return val in ("1", "true", "yes", "on")


def _is_dev_strict_enabled() -> bool:
    """Check if CHIMERA_DEV_STRICT=1."""
    val = str(os.getenv("CHIMERA_DEV_STRICT", "0")).lower()
    return val in ("1", "true", "yes", "on")
