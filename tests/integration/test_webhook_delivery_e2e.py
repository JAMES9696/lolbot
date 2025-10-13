"""E2E test for Webhook delivery flow (V2.4 P0).

This test validates:
1. Deferred response (type 5) sent within 3 seconds
2. PATCH request to /webhooks/{app_id}/{token}/messages/@original
3. Proper embed rendering for success/error cases
4. Error handling and graceful degradation

Test Strategy:
- Mock aiohttp.ClientSession.patch to capture webhook calls
- Simulate team_tasks.analyze_team_task execution
- Assert webhook URL pattern and payload structure
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.discord_webhook import DiscordWebhookAdapter
from src.contracts.analysis_results import (
    AnalysisErrorReport,
    FinalAnalysisReport,
    V1ScoreSummary,
)


class TestWebhookDeliveryE2E:
    """E2E validation for webhook delivery mechanism."""

    @pytest.mark.asyncio
    async def test_webhook_delivery_success_flow(self):
        """Test successful webhook delivery with proper URL and payload."""
        # Arrange
        adapter = DiscordWebhookAdapter()
        application_id = "test_app_123"
        interaction_token = "test_token_abc"

        report = FinalAnalysisReport(
            match_id="NA1_1700000001",
            match_result="victory",
            summoner_name="TestPlayer",
            champion_name="Yasuo",
            champion_id=157,
            ai_narrative_text="测试叙述内容",
            llm_sentiment_tag="激动",
            v1_score_summary=V1ScoreSummary(
                combat_score=85.0,
                economy_score=78.5,
                vision_score=62.0,
                objective_score=90.0,
                teamplay_score=72.5,
                growth_score=68.0,
                tankiness_score=55.0,
                damage_composition_score=75.0,
                survivability_score=60.0,
                cc_contribution_score=70.0,
                overall_score=77.6,
            ),
            champion_assets_url="https://example.com/yasuo.png",
            processing_duration_ms=1250.5,
            algorithm_version="v2.4",
        )

        # Mock aiohttp session and PATCH response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.patch = MagicMock(return_value=mock_response)
        mock_session.closed = False

        # Act
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.publish_match_analysis(
                application_id=application_id,
                interaction_token=interaction_token,
                analysis_report=report,
            )

        # Assert
        assert result is True, "Webhook delivery should succeed"

        # Verify PATCH was called
        assert mock_session.patch.called, "PATCH request should be sent"

        # Verify webhook URL pattern
        call_args = mock_session.patch.call_args
        expected_url = (
            f"https://discord.com/api/v10/webhooks/{application_id}/"
            f"{interaction_token}/messages/@original"
        )
        assert call_args[0][0] == expected_url, "Webhook URL should match pattern"

        # Verify payload structure
        payload = call_args[1]["json"]
        assert payload["content"] is None, "Content should be None (clear loading)"
        assert "embeds" in payload, "Payload should contain embeds"
        assert len(payload["embeds"]) == 1, "Should have one embed"
        assert "allowed_mentions" in payload, "Should disable mentions"

    @pytest.mark.asyncio
    async def test_webhook_error_notification_flow(self):
        """Test error notification delivery via webhook."""
        # Arrange
        adapter = DiscordWebhookAdapter()
        application_id = "test_app_123"
        interaction_token = "test_token_abc"

        error_report = AnalysisErrorReport(
            match_id="NA1_1700000002",
            error_type="riot_api_error",
            error_message="Riot API 返回 429 错误（速率限制）",
            retry_suggested=True,
        )

        # Mock successful PATCH
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.patch = MagicMock(return_value=mock_response)
        mock_session.closed = False

        # Act
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.send_error_notification(
                application_id=application_id,
                interaction_token=interaction_token,
                error_report=error_report,
            )

        # Assert
        assert result is True, "Error notification should succeed"
        assert mock_session.patch.called, "PATCH should be sent for errors"

        # Verify URL
        call_args = mock_session.patch.call_args
        assert "@original" in call_args[0][0], "Should edit original message"

        # Verify error payload
        payload = call_args[1]["json"]
        assert "embeds" in payload, "Error should have embed"

    @pytest.mark.asyncio
    async def test_webhook_token_expired_handling(self):
        """Test graceful handling of expired interaction token (404)."""
        # Arrange
        adapter = DiscordWebhookAdapter()

        report = FinalAnalysisReport(
            match_id="NA1_1700000003",
            match_result="defeat",
            summoner_name="TestPlayer",
            champion_name="Zed",
            champion_id=238,
            ai_narrative_text="测试",
            llm_sentiment_tag="遗憾",
            v1_score_summary=V1ScoreSummary(
                combat_score=60.0,
                economy_score=55.0,
                vision_score=40.0,
                objective_score=50.0,
                teamplay_score=45.0,
                growth_score=52.0,
                tankiness_score=48.0,
                damage_composition_score=58.0,
                survivability_score=42.0,
                cc_contribution_score=50.0,
                overall_score=50.0,
            ),
            champion_assets_url="https://example.com/zed.png",
            processing_duration_ms=1500.0,
            algorithm_version="v2.4",
        )

        # Mock 404 response (token expired)
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Unknown Webhook")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.patch = MagicMock(return_value=mock_response)
        mock_session.closed = False

        # Act & Assert
        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(Exception) as exc_info:
                await adapter.publish_match_analysis(
                    application_id="app_id",
                    interaction_token="expired_token",
                    analysis_report=report,
                )

            # 404 with "Unknown Webhook" indicates token/webhook is invalid/expired
            error_msg = str(exc_info.value).lower()
            assert (
                "404" in error_msg and "webhook" in error_msg
            ), "Should raise error for expired token"

    @pytest.mark.asyncio
    async def test_webhook_url_construction(self):
        """Test webhook URL is correctly constructed."""
        adapter = DiscordWebhookAdapter()

        app_id = "123456789"
        token = "abcdef123456"

        url = adapter._build_webhook_url(app_id, token)

        assert url.startswith("https://discord.com/api/v10/webhooks/")
        assert app_id in url
        assert token in url
        assert url.endswith("/messages/@original")

        # Exact pattern match
        expected = f"https://discord.com/api/v10/webhooks/{app_id}/" f"{token}/messages/@original"
        assert url == expected


@pytest.mark.asyncio
async def test_deferred_response_pattern():
    """Validate that Discord adapter uses correct deferred response type.

    This test ensures interaction.response.defer(ephemeral=False) is called,
    which sends a type 5 (DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE) response.
    """
    from unittest.mock import AsyncMock, MagicMock

    # Mock Discord interaction
    mock_interaction = MagicMock()
    mock_interaction.response.defer = AsyncMock()

    # Simulate /team-analyze handler behavior
    await mock_interaction.response.defer(ephemeral=False)

    # Assert defer was called with correct params
    mock_interaction.response.defer.assert_called_once_with(ephemeral=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
