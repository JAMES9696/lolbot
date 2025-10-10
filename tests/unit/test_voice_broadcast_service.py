"""Unit tests for VoiceBroadcastService.

Test Coverage:
- FIFO queue ordering per guild
- Parameter passthrough (volume, normalize, max_seconds)
- Single-lane worker per guild
- Worker exit when queue drains
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.services.voice_broadcast_service import VoiceBroadcastService, VoiceJob


@pytest.fixture
def mock_discord_adapter() -> Any:
    """Create a mock DiscordAdapter with async playback method."""
    adapter = MagicMock()
    adapter.play_tts_in_voice_channel = AsyncMock(return_value=True)
    return adapter


@pytest.mark.asyncio
async def test_fifo_ordering_and_parameter_passthrough(mock_discord_adapter: Any) -> None:
    """Verify jobs are executed in FIFO order with correct parameters."""
    service = VoiceBroadcastService(mock_discord_adapter)

    # Enqueue multiple jobs with different parameters
    await service.enqueue(
        guild_id=123,
        channel_id=456,
        audio_url="https://cdn.example.com/audio1.mp3",
        volume=0.3,
        normalize=True,
        max_seconds=30,
    )
    await service.enqueue(
        guild_id=123,
        channel_id=456,
        audio_url="https://cdn.example.com/audio2.mp3",
        volume=0.7,
        normalize=False,
        max_seconds=None,
    )
    await service.enqueue(
        guild_id=123,
        channel_id=789,
        audio_url="https://cdn.example.com/audio3.mp3",
        volume=0.5,
        normalize=True,
        max_seconds=60,
    )

    # Wait for worker to process all jobs
    await asyncio.sleep(0.2)

    # Verify all jobs were called in FIFO order with correct parameters
    assert mock_discord_adapter.play_tts_in_voice_channel.call_count == 3

    # Check first call
    first_call = mock_discord_adapter.play_tts_in_voice_channel.call_args_list[0]
    assert first_call.kwargs["guild_id"] == 123
    assert first_call.kwargs["voice_channel_id"] == 456
    assert first_call.kwargs["audio_url"] == "https://cdn.example.com/audio1.mp3"
    assert first_call.kwargs["volume"] == 0.3
    assert first_call.kwargs["normalize"] is True
    assert first_call.kwargs["max_seconds"] == 30

    # Check second call
    second_call = mock_discord_adapter.play_tts_in_voice_channel.call_args_list[1]
    assert second_call.kwargs["guild_id"] == 123
    assert second_call.kwargs["voice_channel_id"] == 456
    assert second_call.kwargs["audio_url"] == "https://cdn.example.com/audio2.mp3"
    assert second_call.kwargs["volume"] == 0.7
    assert second_call.kwargs["normalize"] is False
    assert second_call.kwargs["max_seconds"] is None

    # Check third call
    third_call = mock_discord_adapter.play_tts_in_voice_channel.call_args_list[2]
    assert third_call.kwargs["guild_id"] == 123
    assert third_call.kwargs["voice_channel_id"] == 789
    assert third_call.kwargs["audio_url"] == "https://cdn.example.com/audio3.mp3"
    assert third_call.kwargs["volume"] == 0.5
    assert third_call.kwargs["normalize"] is True
    assert third_call.kwargs["max_seconds"] == 60


@pytest.mark.asyncio
async def test_single_worker_per_guild(mock_discord_adapter: Any) -> None:
    """Verify only one worker is active per guild at a time."""

    # Slow down playback to keep workers alive longer for inspection
    async def slow_playback(*args: Any, **kwargs: Any) -> bool:
        await asyncio.sleep(0.1)
        return True

    mock_discord_adapter.play_tts_in_voice_channel = AsyncMock(side_effect=slow_playback)

    service = VoiceBroadcastService(mock_discord_adapter)

    # Enqueue jobs for different guilds
    await service.enqueue(guild_id=111, channel_id=456, audio_url="https://cdn.example.com/g1a.mp3")
    await service.enqueue(guild_id=111, channel_id=456, audio_url="https://cdn.example.com/g1b.mp3")
    await service.enqueue(guild_id=222, channel_id=789, audio_url="https://cdn.example.com/g2a.mp3")

    # Give workers time to start
    await asyncio.sleep(0.05)

    # Verify two workers (one per guild)
    assert len(service._workers) == 2
    assert 111 in service._workers
    assert 222 in service._workers

    # Wait for completion
    await asyncio.sleep(0.4)

    # Verify all jobs were processed
    assert mock_discord_adapter.play_tts_in_voice_channel.call_count == 3


@pytest.mark.asyncio
async def test_worker_exits_when_queue_drains(mock_discord_adapter: Any) -> None:
    """Verify worker exits when queue becomes empty (YAGNI: no persistent workers)."""

    # Slow down playback to allow inspection during execution
    async def slow_playback(*args: Any, **kwargs: Any) -> bool:
        await asyncio.sleep(0.1)
        return True

    mock_discord_adapter.play_tts_in_voice_channel = AsyncMock(side_effect=slow_playback)

    service = VoiceBroadcastService(mock_discord_adapter)

    # Enqueue a single job
    await service.enqueue(
        guild_id=123, channel_id=456, audio_url="https://cdn.example.com/single.mp3"
    )

    # Worker should be active (check immediately after enqueue)
    await asyncio.sleep(0.02)
    assert 123 in service._workers
    assert not service._workers[123].done()

    # Wait for job to complete and worker to exit
    await asyncio.sleep(0.2)

    # Worker should have exited and been removed
    assert 123 not in service._workers or service._workers[123].done()


@pytest.mark.asyncio
async def test_playback_failure_does_not_block_queue(mock_discord_adapter: Any) -> None:
    """Verify queue continues processing even if one job fails."""
    # First call fails, second succeeds
    mock_discord_adapter.play_tts_in_voice_channel = AsyncMock(side_effect=[False, True])

    service = VoiceBroadcastService(mock_discord_adapter)

    await service.enqueue(
        guild_id=123, channel_id=456, audio_url="https://cdn.example.com/fail.mp3"
    )
    await service.enqueue(guild_id=123, channel_id=456, audio_url="https://cdn.example.com/ok.mp3")

    # Wait for both jobs to process
    await asyncio.sleep(0.2)

    # Both jobs should have been attempted
    assert mock_discord_adapter.play_tts_in_voice_channel.call_count == 2


@pytest.mark.asyncio
async def test_voice_job_dataclass_defaults() -> None:
    """Verify VoiceJob dataclass has correct default values."""
    job = VoiceJob(guild_id=123, channel_id=456, audio_url="https://example.com/audio.mp3")

    assert job.guild_id == 123
    assert job.channel_id == 456
    assert job.audio_url == "https://example.com/audio.mp3"
    assert job.volume == 0.5  # Default
    assert job.normalize is False  # Default
    assert job.max_seconds is None  # Default
