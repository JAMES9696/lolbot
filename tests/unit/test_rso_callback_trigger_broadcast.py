"""Unit tests for RSOCallbackServer.trigger_broadcast handler.

Test Coverage:
- user_id branch: resolves user's voice channel via play_tts_to_user_channel
- channel_id branch: direct playback via play_tts_in_voice_channel
- queue branch: enqueue when voice_broadcast available
- authorization checks
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.rso_callback import RSOCallbackServer
from src.config.settings import get_settings
from src.adapters.tts_adapter import TTSError


@pytest.fixture
def mock_discord_adapter() -> Any:
    """Create a mock DiscordAdapter with voice methods."""
    adapter = MagicMock()
    adapter.play_tts_to_user_channel = AsyncMock(return_value=True)
    adapter.play_tts_in_voice_channel = AsyncMock(return_value=True)
    adapter.enqueue_tts_playback = AsyncMock(return_value=True)
    adapter.enqueue_tts_playback_bytes = AsyncMock(return_value=True)
    adapter.play_tts_bytes_in_voice_channel = AsyncMock(return_value=True)
    adapter.voice_broadcast = None  # Default: no queue
    return adapter


@pytest.fixture
def callback_server(mock_discord_adapter: Any) -> RSOCallbackServer:
    """Create RSOCallbackServer with mocked dependencies."""
    server = RSOCallbackServer(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
        redis_adapter=MagicMock(),
        discord_adapter=mock_discord_adapter,
    )
    return server


@pytest.mark.asyncio
async def test_trigger_broadcast_user_id_branch(
    callback_server: RSOCallbackServer,
    mock_discord_adapter: Any,
    monkeypatch: Any,
) -> None:
    """Verify trigger_broadcast uses play_tts_to_user_channel when user_id provided."""

    # Mock authorization
    def mock_authorize(request: web.Request) -> bool:
        return True

    monkeypatch.setattr(callback_server, "_authorize_broadcast", mock_authorize)

    # Create test client
    async with TestClient(TestServer(callback_server.app)) as client:
        # POST with user_id (should trigger play_tts_to_user_channel)
        resp = await client.post(
            "/broadcast",
            json={
                "audio_url": "https://cdn.example.com/audio.mp3",
                "guild_id": 123,
                "user_id": 789,  # user_id branch
            },
        )

        # Verify response
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["by_user"] is True

        # Verify play_tts_to_user_channel was called
        mock_discord_adapter.play_tts_to_user_channel.assert_called_once_with(
            guild_id=123,
            user_id=789,
            audio_url="https://cdn.example.com/audio.mp3",
        )

        # Verify other methods were NOT called
        mock_discord_adapter.play_tts_in_voice_channel.assert_not_called()
        mock_discord_adapter.enqueue_tts_playback.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_broadcast_channel_id_branch_direct(
    callback_server: RSOCallbackServer,
    mock_discord_adapter: Any,
    monkeypatch: Any,
) -> None:
    """Verify trigger_broadcast uses direct playback when channel_id provided and no queue."""

    # Mock authorization
    def mock_authorize(request: web.Request) -> bool:
        return True

    monkeypatch.setattr(callback_server, "_authorize_broadcast", mock_authorize)

    # Ensure no queue available
    mock_discord_adapter.voice_broadcast = None

    # Create test client
    async with TestClient(TestServer(callback_server.app)) as client:
        # POST with channel_id (should trigger play_tts_in_voice_channel)
        resp = await client.post(
            "/broadcast",
            json={
                "audio_url": "https://cdn.example.com/audio.mp3",
                "guild_id": 123,
                "voice_channel_id": 456,  # channel_id branch
            },
        )

        # Verify response
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["queued"] is False

        # Verify _play_audio was called (which calls play_tts_in_voice_channel)
        # Note: _play_audio is a private method, so we check the underlying call
        mock_discord_adapter.play_tts_in_voice_channel.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_broadcast_channel_id_branch_queued(
    callback_server: RSOCallbackServer,
    mock_discord_adapter: Any,
    monkeypatch: Any,
) -> None:
    """Verify trigger_broadcast uses queue when channel_id provided and queue available."""

    # Mock authorization
    def mock_authorize(request: web.Request) -> bool:
        return True

    monkeypatch.setattr(callback_server, "_authorize_broadcast", mock_authorize)

    # Enable queue
    mock_discord_adapter.voice_broadcast = MagicMock()

    # Create test client
    async with TestClient(TestServer(callback_server.app)) as client:
        # POST with channel_id (should use queue)
        resp = await client.post(
            "/broadcast",
            json={
                "audio_url": "https://cdn.example.com/audio.mp3",
                "guild_id": 123,
                "voice_channel_id": 456,
            },
        )

        # Verify response
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["queued"] is True

        # Verify enqueue_tts_playback was called
        mock_discord_adapter.enqueue_tts_playback.assert_called_once_with(
            guild_id=123,
            voice_channel_id=456,
            audio_url="https://cdn.example.com/audio.mp3",
        )


@pytest.mark.asyncio
async def test_trigger_broadcast_unauthorized(
    callback_server: RSOCallbackServer,
    monkeypatch: Any,
) -> None:
    """Verify trigger_broadcast rejects unauthorized requests."""

    # Mock authorization to fail
    def mock_authorize(request: web.Request) -> bool:
        return False

    monkeypatch.setattr(callback_server, "_authorize_broadcast", mock_authorize)

    # Create test client
    async with TestClient(TestServer(callback_server.app)) as client:
        # POST without auth
        resp = await client.post(
            "/broadcast",
            json={
                "audio_url": "https://cdn.example.com/audio.mp3",
                "guild_id": 123,
                "voice_channel_id": 456,
            },
        )

        # Verify rejection
        assert resp.status == 401
        text = await resp.text()
        assert text == "unauthorized"


@pytest.mark.asyncio
async def test_trigger_broadcast_user_id_no_adapter(
    callback_server: RSOCallbackServer,
    monkeypatch: Any,
) -> None:
    """Verify trigger_broadcast returns error when user_id provided but no discord_adapter."""

    # Mock authorization
    def mock_authorize(request: web.Request) -> bool:
        return True

    monkeypatch.setattr(callback_server, "_authorize_broadcast", mock_authorize)

    # Remove discord adapter
    callback_server.discord_adapter = None

    # Create test client
    async with TestClient(TestServer(callback_server.app)) as client:
        # POST with user_id but no adapter
        resp = await client.post(
            "/broadcast",
            json={
                "audio_url": "https://cdn.example.com/audio.mp3",
                "guild_id": 123,
                "user_id": 789,
            },
        )

        # Verify error response
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is False
        assert data["error"] == "no_discord_adapter"


@pytest.mark.asyncio
async def test_trigger_broadcast_no_channel_or_user(
    callback_server: RSOCallbackServer,
    monkeypatch: Any,
) -> None:
    """Verify trigger_broadcast returns error when neither channel_id nor user_id provided."""

    # Mock authorization
    def mock_authorize(request: web.Request) -> bool:
        return True

    monkeypatch.setattr(callback_server, "_authorize_broadcast", mock_authorize)

    # Create test client
    async with TestClient(TestServer(callback_server.app)) as client:
        # POST with audio_url but no channel or user
        resp = await client.post(
            "/broadcast",
            json={
                "audio_url": "https://cdn.example.com/audio.mp3",
                "guild_id": 123,
                # Missing both voice_channel_id and user_id
            },
        )

        # Verify error response
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is False
        assert data["error"] == "no_channel_or_user"


@pytest.mark.asyncio
async def test_broadcast_streaming_prefers_tts_summary(
    callback_server: RSOCallbackServer,
    mock_discord_adapter: Any,
    monkeypatch: Any,
) -> None:
    """Ensure streaming mode uses stored tts_summary text."""

    settings = get_settings()
    monkeypatch.setattr(settings, "feature_voice_streaming_enabled", True)

    summary_text = "这是一段精简摘要"
    callback_server.db.get_analysis_result = AsyncMock(
        return_value={
            "llm_narrative": "原始全文",
            "llm_metadata": {"tts_summary": summary_text, "emotion": "激动"},
        }
    )

    captured: dict[str, Any] = {}

    class StubTTS:
        async def synthesize_speech_to_bytes(self, text: str, emotion: str | None) -> bytes:
            captured["text"] = text
            captured["emotion"] = emotion
            return b"STREAM"

        async def synthesize_speech_to_url(self, *_: Any, **__: Any) -> str:
            raise AssertionError("URL fallback should not be invoked when streaming succeeds")

    monkeypatch.setattr("src.api.rso_callback.TTSAdapter", StubTTS)

    callback_server.discord_adapter.voice_broadcast = object()

    ok, msg = await callback_server._broadcast_match_tts(123, 456, "NA1_TEST_MATCH")

    assert ok is True
    assert msg == "stream_enqueued"
    assert captured["text"] == summary_text
    mock_discord_adapter.enqueue_tts_playback_bytes.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_streaming_timeout_fallbacks_to_url(
    callback_server: RSOCallbackServer,
    mock_discord_adapter: Any,
    monkeypatch: Any,
) -> None:
    """Streaming timeout should fall back to URL synthesis and still play audio."""

    settings = get_settings()
    monkeypatch.setattr(settings, "feature_voice_streaming_enabled", True)

    summary_text = "队伍表现摘要"
    callback_server.db.get_analysis_result = AsyncMock(
        return_value={
            "llm_narrative": "完整叙事",
            "llm_metadata": {"tts_summary": summary_text, "emotion": "遗憾"},
        }
    )
    callback_server.db.update_llm_narrative = AsyncMock()

    captured: dict[str, Any] = {}

    class TimeoutTTS:
        async def synthesize_speech_to_bytes(self, text: str, emotion: str | None) -> bytes:
            raise TTSError("provider timeout")

        async def synthesize_speech_to_url(self, text: str, emotion: str | None) -> str:
            captured["text"] = text
            captured["emotion"] = emotion
            return "https://cdn.example.com/fallback.mp3"

    monkeypatch.setattr("src.api.rso_callback.TTSAdapter", TimeoutTTS)

    callback_server.discord_adapter.voice_broadcast = None

    ok, msg = await callback_server._broadcast_match_tts(987, 654, "NA1_TIMEOUT_MATCH")

    assert ok is True
    assert msg == "ok"
    assert captured["text"] == summary_text
    mock_discord_adapter.play_tts_in_voice_channel.assert_awaited_once_with(
        guild_id=987,
        voice_channel_id=654,
        audio_url="https://cdn.example.com/fallback.mp3",
    )
    callback_server.db.update_llm_narrative.assert_awaited_once()
    metadata_arg = callback_server.db.update_llm_narrative.await_args.kwargs["llm_metadata"]
    assert metadata_arg["tts_audio_url"] == "https://cdn.example.com/fallback.mp3"
    assert metadata_arg["tts_summary"] == summary_text
