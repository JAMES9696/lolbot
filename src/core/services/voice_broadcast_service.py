import asyncio
import logging
from dataclasses import dataclass
import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.adapters.discord_adapter import DiscordAdapter


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VoiceJob:
    guild_id: int
    channel_id: int
    audio_url: str
    volume: float = 0.5
    normalize: bool = False
    max_seconds: int | None = None
    # Optional in-memory audio payload (mutually exclusive with URL)
    audio_bytes: bytes | None = None


class VoiceBroadcastService:
    """Per‑guild single-lane voice broadcast with FIFO queue.

    KISS: Minimal queue + worker per guild; each item connects, plays, disconnects.
    YAGNI: No persistence or complex state management until required.
    SOLID: Single responsibility (queue + ordering); playback delegated to adapter.
    DRY: Reuse DiscordAdapter.play_tts_in_voice_channel for actual playback.
    """

    def __init__(self, discord_adapter: "DiscordAdapter") -> None:  # type: ignore[name-defined]
        self._adapter = discord_adapter
        self._queues: dict[int, asyncio.Queue[VoiceJob]] = {}
        self._workers: dict[int, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    def _get_queue(self, guild_id: int) -> asyncio.Queue[VoiceJob]:
        q = self._queues.get(guild_id)
        if q is None:
            q = asyncio.Queue()
            self._queues[guild_id] = q
        return q

    async def enqueue(
        self,
        *,
        guild_id: int,
        channel_id: int,
        audio_url: str,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Enqueue a playback job for the guild's single queue.

        Args:
            guild_id: Discord guild (server) ID
            channel_id: Voice channel ID
            audio_url: URL to audio file
            volume: Playback volume (0.0-1.0)
            normalize: Whether to normalize audio
            max_seconds: Maximum playback duration

        Returns:
            True if job was successfully enqueued, False otherwise
        """
        try:
            job = VoiceJob(
                guild_id=guild_id,
                channel_id=channel_id,
                audio_url=audio_url,
                volume=volume,
                normalize=normalize,
                max_seconds=max_seconds,
            )
            q = self._get_queue(guild_id)
            await q.put(job)

            logger.info(
                "voice_job_enqueued",
                extra={
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "audio_url": audio_url[:100],  # Truncate URL for log
                    "queue_size": q.qsize(),
                },
            )

            async with self._lock:
                # Ensure a single worker per guild
                if guild_id not in self._workers or self._workers[guild_id].done():
                    self._workers[guild_id] = asyncio.create_task(self._worker(guild_id))
                    logger.info("voice_worker_started", extra={"guild_id": guild_id})

            return True
        except Exception as exc:
            logger.exception(
                "voice_enqueue_failed",
                extra={
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return False

    async def enqueue_bytes(
        self,
        *,
        guild_id: int,
        channel_id: int,
        audio_bytes: bytes,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Enqueue a playback job with in-memory audio bytes.

        Args:
            guild_id: Discord guild (server) ID
            channel_id: Voice channel ID
            audio_bytes: In-memory audio data
            volume: Playback volume (0.0-1.0)
            normalize: Whether to normalize audio
            max_seconds: Maximum playback duration

        Returns:
            True if job was successfully enqueued, False otherwise
        """
        try:
            job = VoiceJob(
                guild_id=guild_id,
                channel_id=channel_id,
                audio_url="",
                volume=volume,
                normalize=normalize,
                max_seconds=max_seconds,
                audio_bytes=audio_bytes,
            )
            q = self._get_queue(guild_id)
            await q.put(job)

            logger.info(
                "voice_job_bytes_enqueued",
                extra={
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "audio_size_bytes": len(audio_bytes),
                    "queue_size": q.qsize(),
                },
            )

            async with self._lock:
                if guild_id not in self._workers or self._workers[guild_id].done():
                    self._workers[guild_id] = asyncio.create_task(self._worker(guild_id))
                    logger.info("voice_worker_bytes_started", extra={"guild_id": guild_id})

            return True
        except Exception as exc:
            logger.exception(
                "voice_enqueue_bytes_failed",
                extra={
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return False

    async def _worker(self, guild_id: int) -> None:
        q = self._get_queue(guild_id)
        while True:
            try:
                job = await q.get()
            except Exception:
                break
            try:
                logger.info(
                    "Voice job start guild=%s channel=%s url=%s",
                    job.guild_id,
                    job.channel_id,
                    job.audio_url,
                )
                if job.audio_bytes is not None:
                    ok = await self._adapter.play_tts_bytes_in_voice_channel(
                        guild_id=job.guild_id,
                        voice_channel_id=job.channel_id,
                        audio_bytes=job.audio_bytes,
                        volume=job.volume,
                        normalize=job.normalize,
                        max_seconds=job.max_seconds,
                    )
                else:
                    ok = await self._adapter.play_tts_in_voice_channel(
                        guild_id=job.guild_id,
                        voice_channel_id=job.channel_id,
                        audio_url=job.audio_url,
                        volume=job.volume,
                        normalize=job.normalize,
                        max_seconds=job.max_seconds,
                    )
                if not ok:
                    logger.warning("Voice job failed guild=%s url=%s", guild_id, job.audio_url)
                else:
                    logger.info("Voice job done guild=%s url=%s", guild_id, job.audio_url)
            except Exception:
                logger.exception("Voice worker error while playing guild=%s", guild_id)
            finally:
                with contextlib.suppress(Exception):
                    q.task_done()

            # Exit worker when queue drains to keep footprint small
            if q.empty():
                break

        # Cleanup
        async with self._lock:
            self._workers.pop(guild_id, None)
        logger.info("Voice worker exited for guild=%s", guild_id)
