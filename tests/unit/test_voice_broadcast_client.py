"""VoiceBroadcastHttpClient unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.voice_broadcast_client import VoiceBroadcastHttpClient


@pytest.mark.asyncio
async def test_broadcast_success() -> None:
    # Use MagicMock for session (not AsyncMock) to prevent coroutine wrapping
    session = MagicMock()
    session.closed = False  # Prevent _ensure_session from recreating session

    # Mock response as async context manager (pattern from test_discord_webhook_components.py)
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={"ok": True, "message": "stream_enqueued"})
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock()
    session.post.return_value = response

    with patch("src.adapters.voice_broadcast_client.get_settings") as mock_settings:
        settings = MagicMock()
        settings.broadcast_server_url = "http://localhost:3000"
        settings.broadcast_webhook_secret = "secret"
        mock_settings.return_value = settings

        client = VoiceBroadcastHttpClient(session=session)
    ok, message = await client.broadcast_to_user(guild_id=123, user_id=456, match_id="NA1_1")

    assert ok is True
    assert message == "stream_enqueued"
    # MagicMock uses assert_called_once (not assert_awaited_once which is for AsyncMock)
    session.post.assert_called_once()
    call = session.post.call_args_list[0]
    args, kwargs = call
    assert args[0] == "http://localhost:3000/broadcast"
    assert kwargs["json"] == {"match_id": "NA1_1", "guild_id": 123, "user_id": 456}
    assert kwargs["headers"]["X-Auth-Token"] == "secret"


@pytest.mark.asyncio
async def test_broadcast_handles_http_error() -> None:
    # Use MagicMock for session (not AsyncMock) to prevent coroutine wrapping
    session = MagicMock()
    session.closed = False  # Prevent _ensure_session from recreating session

    # Mock response as async context manager
    response = MagicMock()
    response.status = 500
    response.json = AsyncMock(return_value={"ok": False, "error": "oops"})
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock()
    session.post.return_value = response

    with patch("src.adapters.voice_broadcast_client.get_settings") as mock_settings:
        settings = MagicMock()
        settings.broadcast_server_url = "http://localhost:3000"
        settings.broadcast_webhook_secret = None
        mock_settings.return_value = settings

        client = VoiceBroadcastHttpClient(session=session)
        ok, message = await client.broadcast_to_user(guild_id=1, user_id=2, match_id="NA1_2")

    assert ok is False
    assert message == "http_500"


@pytest.mark.asyncio
async def test_broadcast_handles_network_failure() -> None:
    # Use MagicMock for session (not AsyncMock) to prevent coroutine wrapping
    session = MagicMock()
    session.closed = False  # Prevent _ensure_session from recreating session
    session.post.side_effect = RuntimeError("network down")

    with patch("src.adapters.voice_broadcast_client.get_settings") as mock_settings:
        settings = MagicMock()
        settings.broadcast_server_url = "http://localhost:3000"
        settings.broadcast_webhook_secret = None
        mock_settings.return_value = settings

        client = VoiceBroadcastHttpClient(session=session)
        ok, message = await client.broadcast_to_user(guild_id=1, user_id=2, match_id="NA1_3")

    assert ok is False
    assert message == "network_error"
