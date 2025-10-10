"""Unit tests for DiscordAdapter voice methods.

Test Coverage:
- enqueue_tts_playback: queue vs direct playback paths
- play_tts_to_user_channel: user voice channel resolution and delegation
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_voice_broadcast_service() -> Any:
    """Create a mock VoiceBroadcastService."""
    service = MagicMock()
    service.enqueue = AsyncMock()
    return service


@pytest.fixture
def mock_discord_bot() -> Any:
    """Create a mock Discord bot with guild/member support."""
    bot = MagicMock()

    # Mock guild
    guild = MagicMock()
    guild.id = 123

    # Mock member with voice state
    member = MagicMock()
    member.id = 789

    # Mock voice channel
    voice_channel = MagicMock()
    voice_channel.id = 456

    # Setup voice state
    voice_state = MagicMock()
    voice_state.channel = voice_channel

    member.voice = voice_state

    # Wire up bot methods
    bot.get_guild.return_value = guild
    bot.fetch_guild = AsyncMock(return_value=guild)
    guild.get_member.return_value = member
    guild.fetch_member = AsyncMock(return_value=member)

    return bot


@pytest.mark.asyncio
async def test_enqueue_tts_playback_with_queue(
    mock_voice_broadcast_service: Any, mock_discord_bot: Any
) -> None:
    """Verify enqueue_tts_playback uses queue when available."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter with voice broadcast service
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot
    adapter.voice_broadcast = mock_voice_broadcast_service

    # Mock enqueue to return True (successful enqueue)
    mock_voice_broadcast_service.enqueue = AsyncMock(return_value=True)

    # Mock the fallback method (should not be called)
    adapter.play_tts_in_voice_channel = AsyncMock()

    # Call enqueue_tts_playback
    result = await adapter.enqueue_tts_playback(
        guild_id=123,
        voice_channel_id=456,
        audio_url="https://cdn.example.com/audio.mp3",
        volume=0.6,
        normalize=True,
        max_seconds=45,
    )

    # Verify queue was used and returned True
    assert result is True
    mock_voice_broadcast_service.enqueue.assert_called_once_with(
        guild_id=123,
        channel_id=456,
        audio_url="https://cdn.example.com/audio.mp3",
        volume=0.6,
        normalize=True,
        max_seconds=45,
    )

    # Verify direct playback was NOT used
    adapter.play_tts_in_voice_channel.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_tts_playback_without_queue_fallback(mock_discord_bot: Any) -> None:
    """Verify enqueue_tts_playback falls back to direct playback when no queue."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter WITHOUT voice broadcast service
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot
    adapter.voice_broadcast = None  # No queue

    # Mock the fallback method
    adapter.play_tts_in_voice_channel = AsyncMock(return_value=True)

    # Call enqueue_tts_playback
    result = await adapter.enqueue_tts_playback(
        guild_id=123,
        voice_channel_id=456,
        audio_url="https://cdn.example.com/fallback.mp3",
        volume=0.4,
        normalize=False,
        max_seconds=None,
    )

    # Verify direct playback was used
    assert result is True
    adapter.play_tts_in_voice_channel.assert_called_once_with(
        guild_id=123,
        voice_channel_id=456,
        audio_url="https://cdn.example.com/fallback.mp3",
        volume=0.4,
        normalize=False,
        max_seconds=None,
    )


@pytest.mark.asyncio
async def test_play_tts_to_user_channel_success(mock_discord_bot: Any) -> None:
    """Verify play_tts_to_user_channel resolves user's channel and delegates playback."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot

    # Mock playback method
    adapter.play_tts_in_voice_channel = AsyncMock(return_value=True)

    # Call play_tts_to_user_channel
    result = await adapter.play_tts_to_user_channel(
        guild_id=123,
        user_id=789,
        audio_url="https://cdn.example.com/user_audio.mp3",
        volume=0.8,
        normalize=True,
        max_seconds=30,
    )

    # Verify success
    assert result is True

    # Verify user/guild lookups
    mock_discord_bot.get_guild.assert_called_once_with(123)
    guild = mock_discord_bot.get_guild.return_value
    guild.get_member.assert_called_once_with(789)

    # Verify playback was delegated with resolved channel_id (456)
    adapter.play_tts_in_voice_channel.assert_called_once_with(
        guild_id=123,
        voice_channel_id=456,  # Resolved from member.voice.channel.id
        audio_url="https://cdn.example.com/user_audio.mp3",
        volume=0.8,
        normalize=True,
        max_seconds=30,
    )


@pytest.mark.asyncio
async def test_play_tts_to_user_channel_user_not_in_voice(mock_discord_bot: Any) -> None:
    """Verify play_tts_to_user_channel returns False when user not in voice channel."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot

    # Mock member without voice state
    guild = mock_discord_bot.get_guild.return_value
    member = guild.get_member.return_value
    member.voice = None  # User not in voice channel

    # Mock playback method (should not be called)
    adapter.play_tts_in_voice_channel = AsyncMock()

    # Call play_tts_to_user_channel
    result = await adapter.play_tts_to_user_channel(
        guild_id=123,
        user_id=789,
        audio_url="https://cdn.example.com/audio.mp3",
    )

    # Verify failure
    assert result is False

    # Verify playback was NOT attempted
    adapter.play_tts_in_voice_channel.assert_not_called()


@pytest.mark.asyncio
async def test_play_tts_to_user_channel_handles_exceptions(mock_discord_bot: Any) -> None:
    """Verify play_tts_to_user_channel gracefully handles exceptions."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot

    # Mock guild lookup to raise exception
    mock_discord_bot.get_guild.side_effect = Exception("Guild not found")

    # Call play_tts_to_user_channel
    result = await adapter.play_tts_to_user_channel(
        guild_id=999,
        user_id=789,
        audio_url="https://cdn.example.com/audio.mp3",
    )

    # Verify graceful failure
    assert result is False


@pytest.mark.asyncio
async def test_handle_voice_play_interaction_success(mock_discord_bot: Any) -> None:
    """Verify _handle_voice_play_interaction handles successful playback."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot

    # Mock settings with default values
    from unittest.mock import patch

    with patch("src.adapters.discord_adapter.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.voice_volume_default = 0.5
        settings.voice_normalize_default = False
        settings.voice_max_seconds_default = 90
        mock_get_settings.return_value = settings
        adapter.settings = settings

        # Mock DB response with tts_audio_url
        adapter.db.get_analysis_result = AsyncMock(
            return_value={
                "llm_metadata": {"tts_audio_url": "https://cdn.example.com/audio.mp3"},
                "llm_narrative": "Test narrative",
            }
        )

        # Mock play_tts_to_user_channel
        adapter.play_tts_to_user_channel = AsyncMock(return_value=True)

        # Mock interaction
        interaction = MagicMock()
        interaction.user.id = 789
        interaction.guild.id = 123
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        # Call handler
        custom_id = "chimera:voice:play:NA1_12345"
        await adapter._handle_voice_play_interaction(interaction, custom_id)

        # Verify interaction was acknowledged
        interaction.response.defer.assert_called_once_with(ephemeral=True)

        # Verify DB was queried
        adapter.db.get_analysis_result.assert_called_once_with("NA1_12345")

        # Verify play_tts_to_user_channel was called with correct parameters
        adapter.play_tts_to_user_channel.assert_called_once_with(
            guild_id=123,
            user_id=789,
            audio_url="https://cdn.example.com/audio.mp3",
            volume=0.5,
            normalize=False,
            max_seconds=90,
        )

        # Verify success response
        interaction.followup.send.assert_called_once()
        call_args = interaction.followup.send.call_args
        assert "✅" in call_args.args[0]
        assert call_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_handle_voice_play_interaction_synthesize_on_missing_audio(
    mock_discord_bot: Any,
) -> None:
    """Verify _handle_voice_play_interaction synthesizes TTS when audio_url missing."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot

    # Mock settings
    from unittest.mock import patch

    with patch("src.adapters.discord_adapter.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.voice_volume_default = 0.5
        settings.voice_normalize_default = False
        settings.voice_max_seconds_default = 90
        mock_get_settings.return_value = settings
        adapter.settings = settings

        # Mock DB response WITHOUT tts_audio_url
        adapter.db.get_analysis_result = AsyncMock(
            return_value={
                "llm_metadata": {"emotion": "激动"},
                "llm_narrative": "Test narrative for synthesis",
            }
        )
        adapter.db.update_llm_narrative = AsyncMock()

        # Mock TTS synthesis
        with patch("src.adapters.tts_adapter.TTSAdapter") as MockTTS:
            mock_tts = MockTTS.return_value
            mock_tts.synthesize_speech_to_url = AsyncMock(
                return_value="https://cdn.example.com/synthesized.mp3"
            )

            # Mock play_tts_to_user_channel
            adapter.play_tts_to_user_channel = AsyncMock(return_value=True)

            # Mock interaction
            interaction = MagicMock()
            interaction.user.id = 789
            interaction.guild.id = 123
            interaction.response.defer = AsyncMock()
            interaction.followup.send = AsyncMock()

            # Call handler
            custom_id = "chimera:voice:play:NA1_12345"
            await adapter._handle_voice_play_interaction(interaction, custom_id)

            # Verify TTS was synthesized
            mock_tts.synthesize_speech_to_url.assert_called_once_with(
                "Test narrative for synthesis", "激动"
            )

            # Verify DB was updated with new audio_url
            adapter.db.update_llm_narrative.assert_called_once()
            update_call = adapter.db.update_llm_narrative.call_args
            assert update_call.kwargs["match_id"] == "NA1_12345"
            assert (
                update_call.kwargs["llm_metadata"]["tts_audio_url"]
                == "https://cdn.example.com/synthesized.mp3"
            )

            # Verify playback was attempted
            adapter.play_tts_to_user_channel.assert_called_once()


@pytest.mark.asyncio
async def test_handle_voice_play_interaction_user_not_in_voice(mock_discord_bot: Any) -> None:
    """Verify _handle_voice_play_interaction handles user not in voice channel."""
    from src.adapters.discord_adapter import DiscordAdapter

    # Create adapter
    adapter = DiscordAdapter(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
    )
    adapter.bot = mock_discord_bot

    # Mock settings
    from unittest.mock import patch

    with patch("src.adapters.discord_adapter.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.voice_volume_default = 0.5
        settings.voice_normalize_default = False
        settings.voice_max_seconds_default = 90
        mock_get_settings.return_value = settings
        adapter.settings = settings

        # Mock DB response
        adapter.db.get_analysis_result = AsyncMock(
            return_value={
                "llm_metadata": {"tts_audio_url": "https://cdn.example.com/audio.mp3"},
                "llm_narrative": "Test narrative",
            }
        )

        # Mock play_tts_to_user_channel returning False (user not in voice)
        adapter.play_tts_to_user_channel = AsyncMock(return_value=False)

        # Mock interaction
        interaction = MagicMock()
        interaction.user.id = 789
        interaction.guild.id = 123
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        # Call handler
        custom_id = "chimera:voice:play:NA1_12345"
        await adapter._handle_voice_play_interaction(interaction, custom_id)

        # Verify warning response
        interaction.followup.send.assert_called_once()
        call_args = interaction.followup.send.call_args
        assert "⚠️" in call_args.args[0]
        assert "不在任何语音频道" in call_args.args[0]
        assert call_args.kwargs["ephemeral"] is True
