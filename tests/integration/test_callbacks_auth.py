from typing import Any

import pytest
from aiohttp import web

from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_alerts_auth_unauthorized(monkeypatch) -> None:
    # Arrange app
    from src.api.rso_callback import RSOCallbackServer
    from src.config.settings import get_settings

    settings = get_settings()
    # Ensure secrets exist
    settings.alert_webhook_secret = "secret-token"
    settings.alerts_discord_webhook = "http://127.0.0.1:9/nowhere"  # won't be hit due to 401

    server = RSOCallbackServer(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
        redis_adapter=MagicMock(),
        discord_adapter=None,
    )

    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        # Act: no header/query token → 401
        import aiohttp

        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"http://127.0.0.1:{port}/alerts", json={"status": "firing", "alerts": []}
            ) as resp:
                assert resp.status == 401
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_alerts_auth_bearer_ok(monkeypatch) -> None:
    # Arrange app
    from src.api.rso_callback import RSOCallbackServer
    from src.config.settings import get_settings

    settings = get_settings()
    settings.alert_webhook_secret = "secret-token"
    settings.alerts_discord_webhook = "http://localhost/nowhere"

    # Spin up a stub webhook receiver (for success path)
    from aiohttp import web as _web

    webhook_app = _web.Application()

    async def _ok_handler(request):
        return _web.Response(text="ok")

    webhook_app.router.add_post("/ok", _ok_handler)
    webhook_runner = _web.AppRunner(webhook_app)
    await webhook_runner.setup()
    webhook_site = _web.TCPSite(webhook_runner, "127.0.0.1", 0)
    await webhook_site.start()
    webhook_port = webhook_site._server.sockets[0].getsockname()[1]

    server = RSOCallbackServer(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
        redis_adapter=MagicMock(),
        discord_adapter=None,
    )

    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        import aiohttp

        async with aiohttp.ClientSession() as s:
            headers = {"Authorization": "Bearer secret-token"}
            # Route Discord webhook to local stub to avoid outbound
            settings.alerts_discord_webhook = f"http://127.0.0.1:{webhook_port}/ok"
            async with s.post(
                f"http://127.0.0.1:{port}/alerts",
                headers=headers,
                json={"status": "firing", "alerts": []},
            ) as resp:
                assert resp.status == 200
    finally:
        await runner.cleanup()
        await webhook_runner.cleanup()


@pytest.mark.asyncio
async def test_broadcast_auth_x_header(monkeypatch) -> None:
    from src.api.rso_callback import RSOCallbackServer
    from src.config.settings import get_settings

    settings = get_settings()
    settings.broadcast_webhook_secret = "b-token"

    # Stub discord adapter to accept playback
    class _DiscordStub:
        voice_broadcast = None

        async def play_tts_in_voice_channel(
            self, *, guild_id: int, voice_channel_id: int, audio_url: str, **_: Any
        ) -> bool:
            return True

    server = RSOCallbackServer(
        rso_adapter=MagicMock(),
        db_adapter=MagicMock(),
        redis_adapter=MagicMock(),
        discord_adapter=_DiscordStub(),
    )

    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        import aiohttp

        async with aiohttp.ClientSession() as s:
            # 401 when token missing
            async with s.post(f"http://127.0.0.1:{port}/broadcast", json={}) as resp:
                assert resp.status == 401

            # 200 when X-Auth-Token and payload are valid
            headers = {"X-Auth-Token": "b-token"}
            payload = {
                "audio_url": "https://cdn.example.com/a.mp3",
                "guild_id": 1,
                "voice_channel_id": 2,
            }
            async with s.post(
                f"http://127.0.0.1:{port}/broadcast", headers=headers, json=payload
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data.get("ok") is True
    finally:
        await runner.cleanup()
