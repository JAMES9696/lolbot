from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.api.rso_callback import RSOCallbackServer
from src.contracts.user_binding import RiotAccount


class _FakeRSO:
    def list_test_accounts(self):
        return {
            "test_code_1": RiotAccount(puuid="0" * 78, game_name="FujiShanXia", tag_line="NA1"),
            "test_code_2": RiotAccount(puuid="1" * 78, game_name="TestPlayer", tag_line="NA1"),
            "test_code_3": RiotAccount(puuid="2" * 78, game_name="DemoSummoner", tag_line="KR"),
        }


class _FakeDB:
    pass


class _FakeRedis:
    pass


@pytest.mark.asyncio
async def test_mock_oauth_page_renders():
    server = RSOCallbackServer(_FakeRSO(), _FakeDB(), _FakeRedis())
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.get(
            "/mock-oauth", params={"state": "abc", "discord_id": "u1", "region": "na1"}
        )
        assert resp.status == 200
        text = await resp.text()
        assert "Mock OAuth" in text
        # quick-pick links contain /callback
        assert "/callback?state=abc&code=" in text
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mock_oauth_redirects_with_code():
    server = RSOCallbackServer(_FakeRSO(), _FakeDB(), _FakeRedis())
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.get(
            "/mock-oauth", params={"state": "xyz", "code": "test_code_1"}, allow_redirects=False
        )
        assert resp.status in (301, 302, 303, 307, 308)
        loc = resp.headers.get("Location")
        assert loc == "/callback?state=xyz&code=test_code_1"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mock_oauth_missing_state_400():
    server = RSOCallbackServer(_FakeRSO(), _FakeDB(), _FakeRedis())
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.get("/mock-oauth")
        assert resp.status == 400
    finally:
        await client.close()
