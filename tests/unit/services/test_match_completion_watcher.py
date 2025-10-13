"""MatchCompletionWatcher unit tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.services.match_completion_watcher import (
    MatchCompletedEvent,
    MatchCompletionWatcher,
)


class _InMemoryCache:
    """Minimal async cache stub used for watcher tests."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:  # noqa: ARG002
        self._store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        self._store.pop(key, None)
        return True


def _binding(
    *,
    discord_id: str = "123",
    puuid: str = "PUUID",
    region: str = "na1",
    summoner_name: str = "Tester#NA1",
) -> dict[str, Any]:
    return {
        "discord_id": discord_id,
        "puuid": puuid,
        "region": region,
        "summoner_name": summoner_name,
    }


@pytest.mark.asyncio
async def test_first_poll_primes_cache_without_emitting_events() -> None:
    database = AsyncMock()
    database.list_user_bindings = AsyncMock(return_value=[_binding()])

    riot_api = AsyncMock()
    riot_api.get_match_history = AsyncMock(return_value=["NA1_100", "NA1_099"])

    cache = _InMemoryCache()
    watcher = MatchCompletionWatcher(database=database, riot_api=riot_api, cache=cache)

    events = await watcher.poll_new_matches()

    assert events == []
    assert await cache.get("match_watcher:last:123:PUUID") == "NA1_100"
    riot_api.get_match_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_detects_new_match_and_updates_cache() -> None:
    database = AsyncMock()
    database.list_user_bindings = AsyncMock(return_value=[_binding()])

    riot_api = AsyncMock()
    riot_api.get_match_history = AsyncMock(return_value=["NA1_101", "NA1_100"])

    cache = _InMemoryCache()
    await cache.set("match_watcher:last:123:PUUID", "NA1_100")

    watcher = MatchCompletionWatcher(database=database, riot_api=riot_api, cache=cache)

    events = await watcher.poll_new_matches()

    assert events == [
        MatchCompletedEvent(discord_id="123", puuid="PUUID", match_id="NA1_101", region="na1")
    ]
    assert await cache.get("match_watcher:last:123:PUUID") == "NA1_101"


@pytest.mark.asyncio
async def test_skips_binding_when_riot_api_errors(caplog: pytest.LogCaptureFixture) -> None:
    database = AsyncMock()
    database.list_user_bindings = AsyncMock(return_value=[_binding()])

    riot_api = AsyncMock()
    riot_api.get_match_history = AsyncMock(side_effect=RuntimeError("riot down"))

    cache = _InMemoryCache()
    watcher = MatchCompletionWatcher(database=database, riot_api=riot_api, cache=cache)

    events = await watcher.poll_new_matches()

    assert events == []
    assert "riot down" in caplog.text


@pytest.mark.asyncio
async def test_ignores_bindings_without_puuid() -> None:
    database = AsyncMock()
    incomplete: Mapping[str, Any] = {"discord_id": "999", "region": "na1"}
    database.list_user_bindings = AsyncMock(return_value=[incomplete])

    riot_api = AsyncMock()
    cache = _InMemoryCache()

    watcher = MatchCompletionWatcher(database=database, riot_api=riot_api, cache=cache)
    events = await watcher.poll_new_matches()

    assert events == []
    riot_api.get_match_history.assert_not_called()
