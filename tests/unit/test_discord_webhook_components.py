"""Unit tests for Discord webhook message components (buttons).

Test Coverage:
- Feedback buttons attachment when feature_feedback_enabled
- Voice play button attachment when feature_voice_enabled
- Component limit enforcement (max 5 buttons per row)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.discord_webhook import DiscordWebhookAdapter
from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary


@pytest.fixture
def sample_analysis_report() -> FinalAnalysisReport:
    """Create a sample FinalAnalysisReport for testing."""
    return FinalAnalysisReport(
        match_id="NA1_12345",
        match_result="victory",
        summoner_name="TestPlayer#NA1",
        champion_name="Yasuo",
        champion_id=157,
        ai_narrative_text="Great performance!",
        llm_sentiment_tag="激动",
        v1_score_summary=V1ScoreSummary(
            combat_score=8.5,
            economy_score=7.0,
            vision_score=6.5,
            objective_score=9.0,
            teamplay_score=8.0,
            growth_score=7.5,
            tankiness_score=6.0,
            damage_composition_score=8.0,
            survivability_score=7.0,
            cc_contribution_score=6.5,
            overall_score=7.8,
        ),
        champion_assets_url="https://cdn.example.com/yasuo.png",
        processing_duration_ms=1234.5,
        algorithm_version="v1",
        tts_audio_url="https://cdn.example.com/audio.mp3",
    )


@pytest.mark.asyncio
async def test_publish_match_analysis_includes_voice_button(
    sample_analysis_report: FinalAnalysisReport,
) -> None:
    """Verify voice play button is included when feature_voice_enabled=True."""
    adapter = DiscordWebhookAdapter()

    # Mock settings with both features enabled
    with patch("src.adapters.discord_webhook.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.feature_feedback_enabled = True
        settings.feature_voice_enabled = True
        mock_get_settings.return_value = settings

        # Mock render_analysis_embed
        with patch("src.core.views.analysis_view.render_analysis_embed") as mock_render:
            mock_embed = MagicMock()
            mock_embed.to_dict.return_value = {"title": "Analysis Result"}
            mock_render.return_value = mock_embed

            # Mock HTTP session
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_session = MagicMock()
            mock_session.patch.return_value = mock_response
            mock_session.closed = False
            adapter._session = mock_session

            # Call publish_match_analysis
            result = await adapter.publish_match_analysis(
                application_id="test_app_id",
                interaction_token="test_token",
                analysis_report=sample_analysis_report,
            )

            assert result is True

            # Extract the payload sent to Discord
            call_args = mock_session.patch.call_args
            payload = call_args.kwargs["json"]

            # Verify components exist
            assert "components" in payload
            assert len(payload["components"]) == 1

            # Verify action row has 4 buttons (3 feedback + 1 voice)
            action_row = payload["components"][0]
            assert action_row["type"] == 1  # Action Row
            assert len(action_row["components"]) == 4

            # Extract button custom_ids
            button_ids = [btn["custom_id"] for btn in action_row["components"]]

            # Verify feedback buttons
            assert f"chimera:fb:up:{sample_analysis_report.match_id}" in button_ids
            assert f"chimera:fb:down:{sample_analysis_report.match_id}" in button_ids
            assert f"chimera:fb:star:{sample_analysis_report.match_id}" in button_ids

            # Verify voice button
            voice_buttons = [cid for cid in button_ids if cid.startswith("chimera:voice:play:")]
            assert len(voice_buttons) == 1
            voice_button_id = voice_buttons[0]
            parts = voice_button_id.split(":")
            assert parts[3] == sample_analysis_report.match_id
            assert len(parts) == 5  # includes issued_at timestamp

            # Verify voice button properties
            voice_button = next(
                btn for btn in action_row["components"] if btn["custom_id"] == voice_button_id
            )
            assert voice_button["type"] == 2  # Button
            assert voice_button["style"] == 1  # Primary
            assert voice_button["label"] == "播报到我所在频道"
            assert voice_button["emoji"]["name"] == "🔊"


@pytest.mark.asyncio
async def test_publish_match_analysis_no_voice_button_when_disabled(
    sample_analysis_report: FinalAnalysisReport,
) -> None:
    """Verify voice button is NOT included when feature_voice_enabled=False."""
    adapter = DiscordWebhookAdapter()

    # Mock settings with feedback enabled but voice disabled
    with patch("src.adapters.discord_webhook.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.feature_feedback_enabled = True
        settings.feature_voice_enabled = False  # Voice disabled
        mock_get_settings.return_value = settings

        # Mock render_analysis_embed
        with patch("src.core.views.analysis_view.render_analysis_embed") as mock_render:
            mock_embed = MagicMock()
            mock_embed.to_dict.return_value = {"title": "Analysis Result"}
            mock_render.return_value = mock_embed

            # Mock HTTP session
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_session = MagicMock()
            mock_session.patch.return_value = mock_response
            mock_session.closed = False
            adapter._session = mock_session

            # Call publish_match_analysis
            result = await adapter.publish_match_analysis(
                application_id="test_app_id",
                interaction_token="test_token",
                analysis_report=sample_analysis_report,
            )

            assert result is True

            # Extract the payload
            call_args = mock_session.patch.call_args
            payload = call_args.kwargs["json"]

            # Verify components exist
            assert "components" in payload

            # Verify action row has only 3 buttons (feedback only)
            action_row = payload["components"][0]
            assert len(action_row["components"]) == 3

            # Extract button custom_ids
            button_ids = [btn["custom_id"] for btn in action_row["components"]]

            # Verify NO voice button
            assert not any("voice:play" in btn_id for btn_id in button_ids)


@pytest.mark.asyncio
async def test_publish_match_analysis_respects_5_button_limit(
    sample_analysis_report: FinalAnalysisReport,
) -> None:
    """Verify component array never exceeds 5 buttons (Discord limit)."""
    adapter = DiscordWebhookAdapter()

    # Mock settings
    with patch("src.adapters.discord_webhook.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.feature_feedback_enabled = True
        settings.feature_voice_enabled = True
        mock_get_settings.return_value = settings

        # Mock render_analysis_embed
        with patch("src.core.views.analysis_view.render_analysis_embed") as mock_render:
            mock_embed = MagicMock()
            mock_embed.to_dict.return_value = {"title": "Analysis Result"}
            mock_render.return_value = mock_embed

            # Mock HTTP session
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_session = MagicMock()
            mock_session.patch.return_value = mock_response
            mock_session.closed = False
            adapter._session = mock_session

            # Call publish_match_analysis
            await adapter.publish_match_analysis(
                application_id="test_app_id",
                interaction_token="test_token",
                analysis_report=sample_analysis_report,
            )

            # Extract the payload
            call_args = mock_session.patch.call_args
            payload = call_args.kwargs["json"]

            # Verify button count never exceeds 5
            action_row = payload["components"][0]
            assert len(action_row["components"]) <= 5


@pytest.mark.asyncio
async def test_publish_match_analysis_components_optional_on_failure(
    sample_analysis_report: FinalAnalysisReport,
) -> None:
    """Verify component attachment failure doesn't prevent webhook success."""
    adapter = DiscordWebhookAdapter()

    # Mock settings to cause component build failure
    with patch("src.adapters.discord_webhook.get_settings") as mock_get_settings:
        # Make get_settings raise an exception during component building
        mock_get_settings.side_effect = [
            MagicMock(
                feature_feedback_enabled=True, feature_voice_enabled=True
            ),  # First call (payload build)
            Exception("Settings error"),  # Second call (component build - will be caught)
        ]

        # Mock render_analysis_embed
        with patch("src.core.views.analysis_view.render_analysis_embed") as mock_render:
            mock_embed = MagicMock()
            mock_embed.to_dict.return_value = {"title": "Analysis Result"}
            mock_render.return_value = mock_embed

            # Mock HTTP session
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_session = MagicMock()
            mock_session.patch.return_value = mock_response
            mock_session.closed = False
            adapter._session = mock_session

            # This should still succeed despite component error
            # Note: The actual implementation catches exceptions in component building
            # and logs a warning but continues with webhook delivery
            result = await adapter.publish_match_analysis(
                application_id="test_app_id",
                interaction_token="test_token",
                analysis_report=sample_analysis_report,
            )

            # Webhook should still succeed
            assert result is True
