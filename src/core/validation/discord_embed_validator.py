"""Discord Embed Validation Module.

Provides pre-flight validation for Discord embeds before webhook delivery.
Catches common formatting errors and API limit violations early in development.

Usage:
    from src.core.validation.discord_embed_validator import validate_embed_strict

    # Before sending to Discord
    embed = render_analysis_embed(data)
    validation_result = validate_embed_strict(embed)

    if not validation_result.is_valid:
        print(f"❌ Validation failed: {validation_result.errors}")
        print(f"⚠️  Warnings: {validation_result.warnings}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import discord

logger = logging.getLogger(__name__)


# Discord API Limits (as of 2024)
# Reference: https://discord.com/developers/docs/resources/channel#embed-limits
DISCORD_LIMITS = {
    "embed_title": 256,
    "embed_description": 4096,
    "embed_fields": 25,
    "embed_field_name": 256,
    "embed_field_value": 1024,
    "embed_footer_text": 2048,
    "embed_author_name": 256,
    "embed_total_chars": 6000,  # Sum of all text fields
}


@dataclass
class ValidationResult:
    """Result of embed validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_chars: int = 0

    def __str__(self) -> str:
        """Human-readable validation report."""
        lines = [f"✓ Valid: {self.is_valid}"]
        lines.append(f"📊 Total chars: {self.total_chars}/{DISCORD_LIMITS['embed_total_chars']}")

        if self.errors:
            lines.append("\n❌ Errors:")
            for err in self.errors:
                lines.append(f"  - {err}")

        if self.warnings:
            lines.append("\n⚠️  Warnings:")
            for warn in self.warnings:
                lines.append(f"  - {warn}")

        return "\n".join(lines)


def validate_embed_strict(embed: discord.Embed) -> ValidationResult:
    """Validate a Discord embed against API limits (STRICT mode).

    This function performs comprehensive validation to catch errors BEFORE
    sending to Discord API. Use in development and testing.

    Args:
        embed: discord.Embed object to validate

    Returns:
        ValidationResult with detailed error/warning information

    Example:
        >>> embed = discord.Embed(title="Test", description="x" * 5000)
        >>> result = validate_embed_strict(embed)
        >>> assert not result.is_valid
        >>> assert "description exceeds" in result.errors[0].lower()
    """
    result = ValidationResult(is_valid=True)
    total_chars = 0

    # Validate title
    if embed.title:
        title_len = len(embed.title)
        total_chars += title_len
        if title_len > DISCORD_LIMITS["embed_title"]:
            result.is_valid = False
            result.errors.append(
                f"Title exceeds limit: {title_len}/{DISCORD_LIMITS['embed_title']} chars"
            )
        elif title_len > DISCORD_LIMITS["embed_title"] * 0.9:
            result.warnings.append(
                f"Title near limit: {title_len}/{DISCORD_LIMITS['embed_title']} chars"
            )

    # Validate description
    if embed.description:
        desc_len = len(embed.description)
        total_chars += desc_len
        if desc_len > DISCORD_LIMITS["embed_description"]:
            result.is_valid = False
            result.errors.append(
                f"Description exceeds limit: {desc_len}/{DISCORD_LIMITS['embed_description']} chars"
            )
        elif desc_len > DISCORD_LIMITS["embed_description"] * 0.9:
            result.warnings.append(
                f"Description near limit: {desc_len}/{DISCORD_LIMITS['embed_description']} chars"
            )

    # Validate fields
    if embed.fields:
        field_count = len(embed.fields)
        if field_count > DISCORD_LIMITS["embed_fields"]:
            result.is_valid = False
            result.errors.append(f"Too many fields: {field_count}/{DISCORD_LIMITS['embed_fields']}")

        for i, field_obj in enumerate(embed.fields):
            # Field name
            if field_obj.name:
                name_len = len(field_obj.name)
                total_chars += name_len
                if name_len > DISCORD_LIMITS["embed_field_name"]:
                    result.is_valid = False
                    result.errors.append(
                        f"Field[{i}] name exceeds limit: {name_len}/{DISCORD_LIMITS['embed_field_name']}"
                    )

            # Field value
            if field_obj.value:
                value_len = len(field_obj.value)
                total_chars += value_len
                if value_len > DISCORD_LIMITS["embed_field_value"]:
                    result.is_valid = False
                    result.errors.append(
                        f"Field[{i}] '{field_obj.name}' value exceeds limit: "
                        f"{value_len}/{DISCORD_LIMITS['embed_field_value']}"
                    )

    # Validate footer
    if embed.footer and embed.footer.text:
        footer_len = len(embed.footer.text)
        total_chars += footer_len
        if footer_len > DISCORD_LIMITS["embed_footer_text"]:
            result.is_valid = False
            result.errors.append(
                f"Footer text exceeds limit: {footer_len}/{DISCORD_LIMITS['embed_footer_text']}"
            )

    # Validate author
    if embed.author and embed.author.name:
        author_len = len(embed.author.name)
        total_chars += author_len
        if author_len > DISCORD_LIMITS["embed_author_name"]:
            result.is_valid = False
            result.errors.append(
                f"Author name exceeds limit: {author_len}/{DISCORD_LIMITS['embed_author_name']}"
            )

    # Validate total character count
    result.total_chars = total_chars
    if total_chars > DISCORD_LIMITS["embed_total_chars"]:
        result.is_valid = False
        result.errors.append(
            f"Total embed size exceeds limit: {total_chars}/{DISCORD_LIMITS['embed_total_chars']}"
        )
    elif total_chars > DISCORD_LIMITS["embed_total_chars"] * 0.9:
        result.warnings.append(
            f"Total embed size near limit: {total_chars}/{DISCORD_LIMITS['embed_total_chars']}"
        )

    # Validate color (must be valid integer or discord.Colour)
    if embed.color is not None:
        # discord.Embed.color returns discord.Colour object, extract value
        try:
            import discord

            if isinstance(embed.color, discord.Colour):
                color_value = embed.color.value
            else:
                color_value = int(embed.color)

            if color_value < 0 or color_value > 0xFFFFFF:
                result.is_valid = False
                result.errors.append(
                    f"Invalid color value: {color_value} (must be 0x000000-0xFFFFFF)"
                )
        except (ValueError, TypeError) as e:
            result.is_valid = False
            result.errors.append(f"Invalid color type: {embed.color} - {e}")

    return result


def validate_analysis_data(data: dict[str, Any]) -> ValidationResult:
    """Validate FinalAnalysisReport data BEFORE rendering to embed.

    This catches data structure issues before they reach the view layer.

    Args:
        data: Dictionary from FinalAnalysisReport.model_dump()

    Returns:
        ValidationResult with schema validation errors
    """
    result = ValidationResult(is_valid=True)

    # Required fields check
    required_fields = [
        "match_result",
        "summoner_name",
        "champion_name",
        "ai_narrative_text",
        "llm_sentiment_tag",
        "v1_score_summary",
        "champion_assets_url",
        "processing_duration_ms",
    ]

    for field_name in required_fields:
        if field_name not in data:
            result.is_valid = False
            result.errors.append(f"Missing required field: {field_name}")
        elif data[field_name] is None:
            result.is_valid = False
            result.errors.append(f"Required field is None: {field_name}")

    # Type validation for critical fields
    if "v1_score_summary" in data:
        scores = data["v1_score_summary"]
        if not isinstance(scores, dict):
            result.is_valid = False
            result.errors.append(f"v1_score_summary must be dict, got {type(scores).__name__}")
        else:
            score_fields = [
                "combat_score",
                "economy_score",
                "vision_score",
                "objective_score",
                "teamplay_score",
                "overall_score",
            ]
            for score_field in score_fields:
                if score_field not in scores:
                    result.warnings.append(f"Missing score field: v1_score_summary.{score_field}")

    # Validate sentiment tag
    valid_sentiments = ["激动", "遗憾", "嘲讽", "鼓励", "平淡"]
    if "llm_sentiment_tag" in data:
        sentiment = data["llm_sentiment_tag"]
        if sentiment not in valid_sentiments:
            result.warnings.append(
                f"Unexpected sentiment tag: {sentiment} (expected one of {valid_sentiments})"
            )

    return result


def test_embed_rendering(analysis_report_dict: dict[str, Any]) -> tuple[bool, str]:
    """Test-render an embed and return validation results.

    This is a convenience function for development/testing. It validates both
    the input data and the rendered embed.

    Args:
        analysis_report_dict: Dict from FinalAnalysisReport.model_dump()

    Returns:
        Tuple of (success: bool, report: str)

    Example:
        >>> from src.contracts.analysis_results import FinalAnalysisReport
        >>> report = FinalAnalysisReport(...)
        >>> success, msg = test_embed_rendering(report.model_dump())
        >>> if not success:
        ...     print(f"Validation failed:\\n{msg}")
    """
    from src.core.views.analysis_view import render_analysis_embed

    # Step 1: Validate input data
    data_validation = validate_analysis_data(analysis_report_dict)
    if not data_validation.is_valid:
        return False, f"❌ Input data validation failed:\n{data_validation}"

    # Step 2: Render embed
    try:
        embed = render_analysis_embed(analysis_report_dict)
    except Exception as e:
        return False, f"❌ Embed rendering failed: {e}"

    # Step 3: Validate rendered embed
    embed_validation = validate_embed_strict(embed)
    if not embed_validation.is_valid:
        return False, f"❌ Embed validation failed:\n{embed_validation}"

    # Success
    report_lines = [
        "✅ Validation passed!",
        f"\n{data_validation}",
        f"\n{embed_validation}",
    ]
    return True, "\n".join(report_lines)
