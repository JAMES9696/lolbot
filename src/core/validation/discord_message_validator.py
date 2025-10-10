"""Discord Message & Interaction Validator.

Validates ALL types of Discord data before sending:
- Text messages (content)
- Embeds (already covered by discord_embed_validator)
- TTS audio URLs
- Webhook payloads
- Component interactions (buttons, modals)

Usage:
    from src.core.validation.discord_message_validator import validate_message_payload

    # Before sending any Discord message
    payload = {"content": "...", "embeds": [...], "components": [...]}
    result = validate_message_payload(payload)

    if not result.is_valid:
        logger.error(f"Invalid payload: {result.errors}")
"""

from __future__ import annotations

import logging
from typing import Any

from .discord_embed_validator import ValidationResult, validate_embed_strict

logger = logging.getLogger(__name__)


# Discord API Limits for messages
MESSAGE_LIMITS = {
    "content": 2000,  # Plain text content
    "tts_url_length": 2048,  # URL length limit
    "webhook_username": 80,  # Webhook username override
    "component_rows": 5,  # Max action rows
    "buttons_per_row": 5,  # Max buttons per action row
    "select_options": 25,  # Max select menu options
}


def validate_message_content(content: str | None) -> ValidationResult:
    """Validate plain text message content.

    Args:
        content: Message text content

    Returns:
        ValidationResult with errors if content exceeds limits
    """
    result = ValidationResult(is_valid=True)

    if content is None:
        return result

    content_len = len(content)
    if content_len > MESSAGE_LIMITS["content"]:
        result.is_valid = False
        result.errors.append(
            f"Content exceeds limit: {content_len}/{MESSAGE_LIMITS['content']} chars"
        )
    elif content_len > MESSAGE_LIMITS["content"] * 0.9:
        result.warnings.append(
            f"Content near limit: {content_len}/{MESSAGE_LIMITS['content']} chars"
        )

    result.total_chars = content_len
    return result


def validate_tts_audio_url(audio_url: str | None) -> ValidationResult:
    """Validate TTS audio URL format and length.

    Args:
        audio_url: URL to TTS audio file

    Returns:
        ValidationResult with errors if URL is invalid
    """
    result = ValidationResult(is_valid=True)

    if audio_url is None:
        return result

    # Check URL length
    url_len = len(audio_url)
    if url_len > MESSAGE_LIMITS["tts_url_length"]:
        result.is_valid = False
        result.errors.append(
            f"TTS URL too long: {url_len}/{MESSAGE_LIMITS['tts_url_length']} chars"
        )

    # Check URL format (basic validation)
    if not audio_url.startswith(("http://", "https://")):
        result.warnings.append(f"TTS URL should use HTTP(S) protocol: {audio_url[:50]}...")

    # Check file extension (if present)
    valid_extensions = [".mp3", ".ogg", ".wav", ".m4a"]
    if not any(audio_url.lower().endswith(ext) for ext in valid_extensions):
        result.warnings.append(
            f"TTS URL may not be a valid audio file (expected {valid_extensions})"
        )

    return result


def validate_components(components: list[dict[str, Any]] | None) -> ValidationResult:
    """Validate Discord message components (buttons, select menus).

    Args:
        components: List of action row components

    Returns:
        ValidationResult with errors if components are invalid
    """
    result = ValidationResult(is_valid=True)

    if components is None:
        return result

    # Check number of action rows
    if len(components) > MESSAGE_LIMITS["component_rows"]:
        result.is_valid = False
        result.errors.append(
            f"Too many action rows: {len(components)}/{MESSAGE_LIMITS['component_rows']}"
        )

    for i, row in enumerate(components):
        if not isinstance(row, dict):
            result.errors.append(f"Action row {i} is not a dict")
            continue

        # Validate action row type
        if row.get("type") != 1:
            result.errors.append(f"Action row {i} has invalid type: {row.get('type')}")

        # Validate components within the row
        row_components = row.get("components", [])
        if len(row_components) > MESSAGE_LIMITS["buttons_per_row"]:
            result.is_valid = False
            result.errors.append(
                f"Row {i} has too many components: "
                f"{len(row_components)}/{MESSAGE_LIMITS['buttons_per_row']}"
            )

        for j, component in enumerate(row_components):
            # Validate button
            if component.get("type") == 2:  # Button
                if "custom_id" not in component and "url" not in component:
                    result.errors.append(f"Row {i} button {j} missing custom_id or url")
                if "label" not in component and "emoji" not in component:
                    result.warnings.append(f"Row {i} button {j} should have label or emoji")

            # Validate select menu
            elif component.get("type") == 3:  # Select menu
                options = component.get("options", [])
                if len(options) > MESSAGE_LIMITS["select_options"]:
                    result.is_valid = False
                    result.errors.append(
                        f"Row {i} select {j} has too many options: "
                        f"{len(options)}/{MESSAGE_LIMITS['select_options']}"
                    )

    return result


def validate_message_payload(payload: dict[str, Any]) -> ValidationResult:
    """Validate a complete Discord message/webhook payload.

    This is the main validation function that checks all aspects of a
    Discord message before sending.

    Args:
        payload: Complete Discord message payload (JSON dict)

    Returns:
        Combined ValidationResult from all sub-validators

    Example:
        >>> payload = {
        ...     "content": "Hello!",
        ...     "embeds": [embed.to_dict()],
        ...     "components": [...]
        ... }
        >>> result = validate_message_payload(payload)
        >>> if not result.is_valid:
        ...     logger.error(f"Invalid payload: {result.errors}")
    """
    combined = ValidationResult(is_valid=True)

    # Validate content
    if "content" in payload:
        content_result = validate_message_content(payload["content"])
        combined.errors.extend(content_result.errors)
        combined.warnings.extend(content_result.warnings)
        combined.total_chars += content_result.total_chars
        if not content_result.is_valid:
            combined.is_valid = False

    # Validate embeds
    if "embeds" in payload:
        import discord

        for i, embed_dict in enumerate(payload["embeds"]):
            try:
                # Convert dict back to discord.Embed for validation
                embed = discord.Embed.from_dict(embed_dict)
                embed_result = validate_embed_strict(embed)
                combined.errors.extend([f"Embed[{i}]: {err}" for err in embed_result.errors])
                combined.warnings.extend([f"Embed[{i}]: {warn}" for warn in embed_result.warnings])
                combined.total_chars += embed_result.total_chars
                if not embed_result.is_valid:
                    combined.is_valid = False
            except Exception as e:
                combined.errors.append(f"Embed[{i}] failed to parse: {e}")
                combined.is_valid = False

    # Validate components
    if "components" in payload:
        comp_result = validate_components(payload["components"])
        combined.errors.extend(comp_result.errors)
        combined.warnings.extend(comp_result.warnings)
        if not comp_result.is_valid:
            combined.is_valid = False

    # Check for empty payload
    if not any(key in payload for key in ["content", "embeds", "components"]):
        combined.warnings.append("Empty payload: no content, embeds, or components provided")

    return combined


def validate_webhook_delivery(
    application_id: str,
    interaction_token: str,
    payload: dict[str, Any],
) -> ValidationResult:
    """Validate a webhook delivery before sending to Discord.

    This combines message payload validation with webhook-specific checks.

    Args:
        application_id: Discord application ID
        interaction_token: Interaction token
        payload: Message payload

    Returns:
        ValidationResult with webhook-specific errors
    """
    result = validate_message_payload(payload)

    # Validate application_id format
    if not application_id or not application_id.isdigit():
        result.errors.append(f"Invalid application_id: {application_id}")
        result.is_valid = False

    # Validate interaction_token format (should be non-empty string)
    if not interaction_token or len(interaction_token) < 10:
        result.errors.append("Invalid or missing interaction_token")
        result.is_valid = False

    return result
