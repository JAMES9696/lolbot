"""Validation utilities for data contracts and Discord API compliance."""

from .discord_embed_validator import (
    DISCORD_LIMITS,
    ValidationResult,
    test_embed_rendering,
    validate_analysis_data,
    validate_embed_strict,
)
from .discord_message_validator import (
    MESSAGE_LIMITS,
    validate_components,
    validate_message_content,
    validate_message_payload,
    validate_tts_audio_url,
    validate_webhook_delivery,
)

__all__ = [
    # Embed validation
    "DISCORD_LIMITS",
    "ValidationResult",
    "validate_embed_strict",
    "validate_analysis_data",
    "test_embed_rendering",
    # Message validation
    "MESSAGE_LIMITS",
    "validate_message_content",
    "validate_tts_audio_url",
    "validate_components",
    "validate_message_payload",
    "validate_webhook_delivery",
]
