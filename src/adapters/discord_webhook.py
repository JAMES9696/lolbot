"""Discord webhook adapter for asynchronous interaction responses.

This adapter implements the DiscordWebhookPort interface using Discord's
Interaction Webhook API to send followup messages after deferred responses.

Key Features:
- PATCH requests to edit original deferred response
- View-layer decoupling (delegates to render_analysis_embed)
- Structured data contracts (FinalAnalysisReport, AnalysisErrorReport)
- Error message delivery with user-friendly degradation
- 15-minute token validity window (Discord limitation)

Reference:
https://discord.com/developers/docs/interactions/receiving-and-responding#edit-original-interaction-response
"""

import logging
from typing import Any, Optional

import aiohttp

from src.config.settings import get_settings
from src.contracts.analysis_results import AnalysisErrorReport, FinalAnalysisReport
from src.core.ports import DiscordWebhookPort

logger = logging.getLogger(__name__)


class DiscordWebhookError(Exception):
    """Raised when Discord webhook API returns an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DiscordWebhookAdapter(DiscordWebhookPort):
    """Discord webhook adapter for async interaction followup.

    This adapter uses Discord's Interaction Webhook API to edit the original
    deferred response with match analysis results or error messages.

    Architecture:
    - Pure I/O adapter (HTTP PATCH requests)
    - Delegates view rendering to CLI 1's render_analysis_embed()
    - Robust error handling with user-friendly degradation
    - Rate limit compliance (follows Discord API guidelines)
    """

    WEBHOOK_BASE_URL = "https://discord.com/api/v10"
    REQUEST_TIMEOUT = 10  # seconds

    def __init__(self) -> None:
        """Initialize Discord webhook adapter."""
        self._session: aiohttp.ClientSession | None = None
        logger.info("Discord webhook adapter initialized")

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Lazy initialize aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            )
        return self._session

    def _mask_token(self, token: str) -> str:
        """Mask token for safe logging."""
        if len(token) <= 12:
            return "***"
        prefix = token[:4]
        suffix = token[-4:]
        return f"{prefix}***{suffix}"

    async def publish_channel_message(
        self, channel_id: str, embed_dict: dict[str, Any], content: Optional[str] = None
    ) -> bool:
        """Public wrapper to post a message to a channel using bot token."""
        settings = get_settings()
        if not settings.discord_bot_token:
            return False
        url = f"{self.WEBHOOK_BASE_URL}/channels/{channel_id}/messages"
        payload: dict[str, Any] = {
            "embeds": [embed_dict],
            "allowed_mentions": {"parse": []},
        }
        if content:
            payload["content"] = content
        session = await self._ensure_session()
        headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
        async with session.post(url, json=payload, headers=headers) as response:
            return response.status == 200

    async def _post_channel_message(
        self, channel_id: str, embed_dict: dict[str, Any], content: Optional[str] = None
    ) -> bool:
        """Post message to channel using bot token."""
        settings = get_settings()
        if not settings.discord_bot_token:
            return False

        url = f"{self.WEBHOOK_BASE_URL}/channels/{channel_id}/messages"
        payload: dict[str, Any] = {
            "embeds": [embed_dict],
            "allowed_mentions": {"parse": []},
        }
        if content:
            payload["content"] = content

        session = await self._ensure_session()
        headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
        async with session.post(url, json=payload, headers=headers) as response:
            return response.status == 200

    async def publish_match_analysis(
        self,
        application_id: str,
        interaction_token: str,
        analysis_report: FinalAnalysisReport,
        channel_id: str | None = None,
    ) -> bool:
        """Publish match analysis results to Discord via webhook.

        Delegates embed rendering to CLI 1's view layer (render_analysis_embed),
        then PATCHes the original deferred response.

        Args:
            application_id: Discord application ID
            interaction_token: Interaction token (15min validity)
            analysis_report: Structured FinalAnalysisReport Pydantic object
            channel_id: Optional channel ID for fallback delivery

        Returns:
            True if webhook delivery succeeded

        Raises:
            DiscordWebhookError: If webhook delivery fails or token expired
        """
        try:
            # Build webhook URL
            url = self._build_webhook_url(application_id, interaction_token)

            # [CRITICAL: View-Layer Decoupling]
            # Delegate to CLI 1's view renderer for consistent UX
            # [DEV MODE: Pre-flight validation]
            # Validate data contract before rendering
            import os

            from src.core.views.analysis_view import render_analysis_embed

            if os.getenv("CHIMERA_DEV_VALIDATE_DISCORD", "").lower() in ("1", "true", "yes"):
                from src.core.validation import validate_analysis_data

                data_validation = validate_analysis_data(analysis_report.model_dump())
                if not data_validation.is_valid:
                    logger.error(
                        f"❌ Analysis data validation failed before rendering:\n{data_validation}"
                    )
                    # In strict dev mode, fail fast
                    if os.getenv("CHIMERA_DEV_STRICT", "").lower() in ("1", "true"):
                        raise ValueError(f"Invalid analysis data: {data_validation.errors}")
                if data_validation.warnings:
                    logger.warning(f"⚠️  Data validation warnings:\n{data_validation}")

            embed = render_analysis_embed(analysis_report.model_dump())

            # [DEV MODE: Validate rendered embed]
            if os.getenv("CHIMERA_DEV_VALIDATE_DISCORD", "").lower() in ("1", "true", "yes"):
                from src.core.validation import validate_embed_strict

                embed_validation = validate_embed_strict(embed)
                if not embed_validation.is_valid:
                    logger.error(f"❌ Embed validation failed:\n{embed_validation}")
                    # In strict dev mode, fail fast
                    if os.getenv("CHIMERA_DEV_STRICT", "").lower() in ("1", "true"):
                        raise ValueError(f"Invalid Discord embed: {embed_validation.errors}")
                if embed_validation.warnings:
                    logger.warning(f"⚠️  Embed validation warnings:\n{embed_validation}")
                logger.info(
                    f"✅ Embed validation passed: {embed_validation.total_chars}/6000 chars"
                )

            # Prepare PATCH payload
            payload: dict[str, Any] = {
                "content": None,  # Clear the "thinking..." message
                "embeds": [embed.to_dict()],  # discord.Embed to dict
                "allowed_mentions": {"parse": []},  # Disable @mentions for safety
            }

            # Optionally attach feedback buttons as message components
            try:
                settings = get_settings()
                if settings.feature_feedback_enabled:
                    match_id = analysis_report.match_id
                    # Discord component payload (Action Row with buttons)
                    buttons = [
                        {
                            "type": 2,  # Button
                            "style": 3,  # Success (green)
                            "label": "有用",
                            "emoji": {"name": "👍"},
                            "custom_id": f"chimera:fb:up:{match_id}",
                        },
                        {
                            "type": 2,
                            "style": 4,  # Danger (red)
                            "label": "无用",
                            "emoji": {"name": "👎"},
                            "custom_id": f"chimera:fb:down:{match_id}",
                        },
                        {
                            "type": 2,
                            "style": 1,  # Primary (blurple)
                            "label": "收藏",
                            "emoji": {"name": "⭐"},
                            "custom_id": f"chimera:fb:star:{match_id}",
                        },
                    ]

                    # Add voice play button if voice feature enabled
                    if settings.feature_voice_enabled:
                        buttons.append(
                            {
                                "type": 2,  # Button
                                "style": 1,  # Primary (blurple)
                                "label": "播报到我所在频道",
                                "emoji": {"name": "🔊"},
                                "custom_id": f"chimera:voice:play:{match_id}",
                            }
                        )

                    payload["components"] = [
                        {
                            "type": 1,  # Action Row
                            "components": buttons[:5],  # Discord limit: max 5 buttons per row
                        }
                    ]
                # Team UI helper: add an extra row to open paginated team pages when available
                try:
                    report_dict = analysis_report.model_dump()
                    raw_stats = (report_dict.get("v1_score_summary") or {}).get("raw_stats") or {}
                    has_team_receipt = bool(raw_stats.get("team_receipt"))
                except Exception:
                    has_team_receipt = False
                if has_team_receipt or os.getenv("TEAM_UI_BUTTONS", "").lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                ):
                    team_row = {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 1,  # Primary
                                "label": "更多团队页",
                                "emoji": {"name": "🧾"},
                                "custom_id": f"team_analysis:open_pages:{analysis_report.match_id}",
                            }
                        ],
                    }
                    payload.setdefault("components", []).append(team_row)
            except Exception as e:
                # Components are optional; never fail webhook due to UI attachment
                logger.warning(f"Failed to attach feedback components: {e}")

            # [DEV MODE: Validate complete payload before sending]
            if os.getenv("CHIMERA_DEV_VALIDATE_DISCORD", "").lower() in ("1", "true", "yes"):
                from src.core.validation import validate_webhook_delivery

                payload_validation = validate_webhook_delivery(
                    application_id=application_id,
                    interaction_token=interaction_token,
                    payload=payload,
                )
                if not payload_validation.is_valid:
                    logger.error(f"❌ Webhook payload validation failed:\n{payload_validation}")
                    if os.getenv("CHIMERA_DEV_STRICT", "").lower() in ("1", "true"):
                        raise ValueError(f"Invalid webhook payload: {payload_validation.errors}")
                if payload_validation.warnings:
                    logger.warning(f"⚠️  Webhook payload warnings:\n{payload_validation}")
                logger.info(
                    f"✅ Webhook payload validation passed: "
                    f"{payload_validation.total_chars} chars total"
                )

            # Send PATCH request
            session = await self._ensure_session()
            async with session.patch(url, json=payload) as response:
                if response.status == 200:
                    logger.info(
                        f"Successfully published analysis for match {analysis_report.match_id} "
                        f"via webhook (token: {self._mask_token(interaction_token)})"
                    )
                    return True
                elif response.status in (404, 403, 400) and channel_id:
                    # Try fallback to channel message
                    settings = get_settings()
                    if settings.discord_bot_token:
                        content = "原交互响应已过期，这是分析结果的备用发送："
                        success = await self._post_channel_message(
                            channel_id, embed.to_dict(), content
                        )
                        if success:
                            logger.info(
                                f"Successfully published analysis via fallback channel message "
                                f"for match {analysis_report.match_id}"
                            )
                            return True
                        else:
                            logger.warning(
                                f"Failed to publish analysis via fallback for match {analysis_report.match_id}"
                            )
                    # Fall through to raise error if no fallback or fallback failed
                    if response.status == 404:
                        raise DiscordWebhookError(
                            "Interaction token expired or invalid (15min window)",
                            status_code=404,
                        )
                    else:
                        raise DiscordWebhookError(
                            f"Discord API error: {response.status}",
                            status_code=response.status,
                        )
                else:
                    error_text = await response.text()
                    raise DiscordWebhookError(
                        f"Discord API error: {response.status} - {error_text}",
                        status_code=response.status,
                    )

        except DiscordWebhookError:
            raise
        except Exception as e:
            error_msg = f"Failed to send webhook: {e}"
            logger.error(error_msg, exc_info=True)
            raise DiscordWebhookError(error_msg) from e

    async def publish_team_overview(
        self,
        application_id: str,
        interaction_token: str,
        team_report: "TeamAnalysisReport",
        channel_id: str | None = None,
    ) -> bool:
        """Publish team overview as the main webhook message.

        Uses the team-specific renderer and attaches a button to open paginated pages.
        """
        try:
            url = self._build_webhook_url(application_id, interaction_token)
            from src.core.views.team_analysis_view import render_team_overview_embed

            embed = render_team_overview_embed(team_report)

            payload: dict[str, Any] = {
                "content": None,
                "embeds": [embed.to_dict()],
                "allowed_mentions": {"parse": []},
                "components": [
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 1,
                                "label": "更多团队页",
                                "emoji": {"name": "🧾"},
                                "custom_id": f"team_analysis:open_pages:{team_report.match_id}",
                            }
                        ],
                    }
                ],
            }

            # Optionally attach voice play button for team overview (reuse single-match handler)
            try:
                settings = get_settings()
                if settings.feature_voice_enabled:
                    voice_button = {
                        "type": 2,
                        "style": 1,  # Primary
                        "label": "播报到我所在频道",
                        "emoji": {"name": "🔊"},
                        "custom_id": f"chimera:voice:play:{team_report.match_id}",
                    }
                    # Append to first action row if capacity allows (<=5), else create new row
                    if payload["components"] and len(payload["components"][0]["components"]) < 5:
                        payload["components"][0]["components"].append(voice_button)
                    else:
                        payload["components"].append({"type": 1, "components": [voice_button]})
            except Exception as _e:
                logger.warning(f"Failed to attach voice button: {_e}")

            session = await self._ensure_session()
            async with session.patch(url, json=payload) as response:
                if response.status == 200:
                    logger.info(
                        f"Successfully published TEAM overview for match {team_report.match_id} "
                        f"(token: {self._mask_token(interaction_token)})"
                    )
                    return True
                elif response.status in (404, 403, 400) and channel_id:
                    settings = get_settings()
                    if settings.discord_bot_token:
                        content = "原交互响应已过期，这是团队概览的备用发送："
                        success = await self._post_channel_message(
                            channel_id, embed.to_dict(), content
                        )
                        return bool(success)
                    return False
                else:
                    error_text = await response.text()
                    raise DiscordWebhookError(
                        f"Discord API error: {response.status} - {error_text}",
                        status_code=response.status,
                    )
        except DiscordWebhookError:
            raise
        except Exception as e:
            logger.error(f"Failed to send team overview webhook: {e}", exc_info=True)
            return False

    async def send_error_notification(
        self,
        application_id: str,
        interaction_token: str,
        error_report: AnalysisErrorReport,
        channel_id: str | None = None,
    ) -> bool:
        """Send error notification to Discord via webhook.

        Delegates error embed rendering to CLI 1's view layer,
        then PATCHes the original response.

        Args:
            application_id: Discord application ID
            interaction_token: Interaction token (15min validity)
            error_report: Structured AnalysisErrorReport Pydantic object
            channel_id: Optional channel ID for fallback delivery

        Returns:
            True if webhook delivery succeeded
        """
        try:
            # Build webhook URL
            url = self._build_webhook_url(application_id, interaction_token)

            # [CRITICAL: View-Layer Decoupling]
            # Delegate to CLI 1's error renderer
            from src.core.views.analysis_view import render_error_embed

            embed = render_error_embed(
                error_message=error_report.error_message,
                match_id=error_report.match_id,
                retry_suggested=error_report.retry_suggested,
            )

            # Prepare PATCH payload
            payload: dict[str, Any] = {
                "content": None,
                "embeds": [embed.to_dict()],
                "allowed_mentions": {"parse": []},
            }

            # Send PATCH request
            session = await self._ensure_session()
            async with session.patch(url, json=payload) as response:
                if response.status == 200:
                    logger.info(
                        f"Successfully sent error notification via webhook "
                        f"(error_type: {error_report.error_type}, token: {self._mask_token(interaction_token)})"
                    )
                    return True
                elif response.status in (404, 403, 400) and channel_id:
                    # Try fallback to channel message
                    settings = get_settings()
                    if settings.discord_bot_token:
                        content = "原交互响应已过期，这是错误通知的备用发送："
                        success = await self._post_channel_message(
                            channel_id, embed.to_dict(), content
                        )
                        if success:
                            logger.info(
                                f"Successfully sent error notification via fallback channel message "
                                f"(error_type: {error_report.error_type})"
                            )
                            return True
                        else:
                            logger.warning(
                                f"Failed to send error notification via fallback "
                                f"(error_type: {error_report.error_type})"
                            )
                # Fall through to existing error handling
                error_text = await response.text()
                logger.error(f"Failed to send error webhook: {response.status} - {error_text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send error webhook: {e}", exc_info=True)
            return False

    def _build_webhook_url(self, application_id: str, interaction_token: str) -> str:
        """Build Discord webhook URL for editing original response.

        Args:
            application_id: Discord application ID
            interaction_token: Interaction token

        Returns:
            Complete webhook URL
        """
        return (
            f"{self.WEBHOOK_BASE_URL}/webhooks/{application_id}/"
            f"{interaction_token}/messages/@original"
        )

    # Legacy method compatibility (deprecated, will be removed in next phase)
    async def send_match_analysis(
        self,
        application_id: str,
        interaction_token: str,
        match_id: str,
        narrative: str,
        score_data: dict[str, Any],
        emotion: str | None = None,
    ) -> bool:
        """[DEPRECATED] Legacy send_match_analysis method.

        This method exists for backward compatibility with existing Celery tasks.
        New code should use publish_match_analysis() with FinalAnalysisReport.

        Will be removed after all Celery tasks migrate to new contract.
        """
        logger.warning(
            "send_match_analysis() is deprecated. "
            "Migrate to publish_match_analysis() with FinalAnalysisReport"
        )

        # Convert legacy data to FinalAnalysisReport format
        # This is a temporary bridge during migration
        try:
            from src.contracts.analysis_results import V1ScoreSummary

            # Extract V1 scores from legacy score_data
            v1_scores = V1ScoreSummary(
                combat_score=score_data.get("combat_score", 0.0),
                economy_score=score_data.get("economy_score", 0.0),
                vision_score=score_data.get("vision_score", 0.0),
                objective_score=score_data.get("objective_score", 0.0),
                teamplay_score=score_data.get("teamplay_score", 0.0),
                overall_score=score_data.get("overall_score", 0.0),
            )

            # Validate emotion tag against FinalAnalysisReport's Literal type
            from typing import Literal

            valid_emotions: tuple[str, ...] = ("激动", "遗憾", "嘲讽", "鼓励", "平淡")
            sentiment_tag: Literal["激动", "遗憾", "嘲讽", "鼓励", "平淡"] = (
                emotion if emotion in valid_emotions else "平淡"  # type: ignore[assignment]
            )

            # Create FinalAnalysisReport from legacy data
            report = FinalAnalysisReport(
                match_id=match_id,
                match_result=score_data.get("match_result", "defeat"),
                summoner_name=score_data.get("summoner_name", "Unknown"),
                champion_name=score_data.get("champion_name", "Unknown"),
                champion_id=score_data.get("champion_id", 0),
                ai_narrative_text=narrative,
                llm_sentiment_tag=sentiment_tag,
                v1_score_summary=v1_scores,
                champion_assets_url=score_data.get("champion_assets_url", ""),
                processing_duration_ms=score_data.get("processing_duration_ms", 0.0),
                algorithm_version=score_data.get("algorithm_version", "v1"),
                tts_audio_url=score_data.get("tts_audio_url"),
                builds_summary_text=score_data.get("builds_summary_text"),
                builds_metadata=score_data.get("builds_metadata"),
            )

            # Delegate to new method
            return await self.publish_match_analysis(application_id, interaction_token, report)

        except Exception as e:
            logger.error(f"Failed to convert legacy data to FinalAnalysisReport: {e}")
            raise DiscordWebhookError(f"Legacy method conversion failed: {e}") from e

    # Legacy error method compatibility (deprecated)
    async def send_error_message(
        self,
        application_id: str,
        interaction_token: str,
        error_type: str,
        user_friendly_message: str,
    ) -> bool:
        """[DEPRECATED] Legacy send_error_message method.

        This method exists for backward compatibility.
        New code should use send_error_notification() with AnalysisErrorReport.
        """
        logger.warning(
            "send_error_message() is deprecated. "
            "Migrate to send_error_notification() with AnalysisErrorReport"
        )

        try:
            error_report = AnalysisErrorReport(
                match_id="unknown",
                error_type=error_type,
                error_message=user_friendly_message,
                retry_suggested=True,
            )

            return await self.send_error_notification(
                application_id, interaction_token, error_report
            )

        except Exception as e:
            logger.error(f"Failed to convert legacy error to AnalysisErrorReport: {e}")
            return False

    async def close(self) -> None:
        """Close HTTP session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Discord webhook adapter session closed")
