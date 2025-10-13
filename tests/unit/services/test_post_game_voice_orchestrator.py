"""PostGameVoiceOrchestrator unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.services.match_completion_watcher import MatchCompletedEvent
from src.core.services.post_game_voice_orchestrator import (
    PostGameVoiceOrchestrator,
)


@pytest.mark.asyncio
async def test_orchestrator_broadcasts_to_first_successful_guild() -> None:
    database = AsyncMock()
    database.get_analysis_result = AsyncMock(return_value={"match_id": "NA1_101"})

    guild_resolver = AsyncMock()
    guild_resolver.get_user_guilds = AsyncMock(return_value=[123])

    broadcaster = AsyncMock()
    broadcaster.broadcast_to_user = AsyncMock(return_value=(True, "stream_enqueued"))

    orchestrator = PostGameVoiceOrchestrator(
        database=database,
        guild_resolver=guild_resolver,
        broadcaster=broadcaster,
    )

    event = MatchCompletedEvent(discord_id="789", puuid="PUUID", match_id="NA1_101", region="na1")
    ok, message = await orchestrator.handle_event(event)

    assert ok is True
    assert message == "stream_enqueued"
    broadcaster.broadcast_to_user.assert_awaited_once_with(
        guild_id=123, user_id=789, match_id="NA1_101"
    )


@pytest.mark.asyncio
async def test_orchestrator_uses_event_guild_hint() -> None:
    database = AsyncMock()
    database.get_analysis_result = AsyncMock(return_value=None)

    guild_resolver = AsyncMock()
    broadcaster = AsyncMock()
    broadcaster.broadcast_to_user = AsyncMock(return_value=(True, "ok"))

    orchestrator = PostGameVoiceOrchestrator(
        database=database,
        guild_resolver=guild_resolver,
        broadcaster=broadcaster,
    )

    event = MatchCompletedEvent(
        discord_id="42",
        puuid="PUUID",
        match_id="NA1_200",
        region="na1",
        guild_id=555,
    )
    ok, _ = await orchestrator.handle_event(event)

    assert ok is True
    guild_resolver.get_user_guilds.assert_not_called()
    broadcaster.broadcast_to_user.assert_awaited_once_with(
        guild_id=555, user_id=42, match_id="NA1_200"
    )


@pytest.mark.asyncio
async def test_orchestrator_attempts_multiple_guilds_until_success() -> None:
    database = AsyncMock()
    database.get_analysis_result = AsyncMock(return_value={"match_id": "NA1_300"})

    guild_resolver = AsyncMock()
    guild_resolver.get_user_guilds = AsyncMock(return_value=[111, 222])

    broadcaster = AsyncMock()
    broadcaster.broadcast_to_user = AsyncMock(
        side_effect=[(False, "voice_busy"), (True, "stream_enqueued")]
    )

    orchestrator = PostGameVoiceOrchestrator(
        database=database,
        guild_resolver=guild_resolver,
        broadcaster=broadcaster,
    )

    event = MatchCompletedEvent(discord_id="900", puuid="PUUID", match_id="NA1_300", region="na1")
    ok, message = await orchestrator.handle_event(event)

    assert ok is True
    assert message == "stream_enqueued"
    assert broadcaster.broadcast_to_user.await_count == 2
    broadcaster.broadcast_to_user.assert_awaited_with(guild_id=222, user_id=900, match_id="NA1_300")


@pytest.mark.asyncio
async def test_orchestrator_returns_failure_when_no_guilds() -> None:
    database = AsyncMock()
    database.get_analysis_result = AsyncMock(return_value=None)

    guild_resolver = AsyncMock()
    guild_resolver.get_user_guilds = AsyncMock(return_value=[])

    broadcaster = AsyncMock()

    orchestrator = PostGameVoiceOrchestrator(
        database=database,
        guild_resolver=guild_resolver,
        broadcaster=broadcaster,
    )

    event = MatchCompletedEvent(discord_id="123", puuid="PUUID", match_id="NA1_1", region="na1")
    ok, message = await orchestrator.handle_event(event)

    assert ok is False
    assert message == "no_guild"
    broadcaster.broadcast_to_user.assert_not_called()
