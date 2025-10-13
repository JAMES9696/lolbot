"""Coordinate post-game analysis broadcast flow."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from src.core.ports import (
    DatabasePort,
    GuildResolverPort,
    VoiceBroadcastPort,
)
from src.core.services.match_completion_watcher import MatchCompletedEvent

logger = logging.getLogger(__name__)


class PostGameVoiceOrchestrator:
    """Ensure a completed match is narrated into Discord voice channels."""

    def __init__(
        self,
        *,
        database: DatabasePort,
        guild_resolver: GuildResolverPort,
        broadcaster: VoiceBroadcastPort,
    ) -> None:
        self._database = database
        self._guild_resolver = guild_resolver
        self._broadcaster = broadcaster

    async def handle_event(self, event: MatchCompletedEvent) -> tuple[bool, str]:
        """Trigger voice narration for the supplied match completion event."""
        try:
            user_id = int(event.discord_id)
        except (TypeError, ValueError):
            logger.warning("Invalid discord_id on match event: %s", event.discord_id)
            return False, "invalid_discord_id"

        guild_candidates = await self._determine_guild_candidates(event, user_id)
        if not guild_candidates:
            logger.info("No guild candidates for user=%s match=%s", user_id, event.match_id)
            return False, "no_guild"

        # Optional telemetry: check whether analysis exists before broadcasting.
        analysis_record = await self._database.get_analysis_result(event.match_id)
        if not analysis_record:
            logger.debug(
                "Analysis record missing for match=%s; broadcast will rely on lazy synthesis",
                event.match_id,
            )

        last_status = "broadcast_failed"
        for guild_id in guild_candidates:
            ok, status = await self._broadcaster.broadcast_to_user(
                guild_id=guild_id, user_id=user_id, match_id=event.match_id
            )
            if ok:
                logger.info(
                    "Post-game broadcast succeeded match=%s guild=%s user=%s",
                    event.match_id,
                    guild_id,
                    user_id,
                )
                return True, status

            logger.warning(
                "Post-game broadcast attempt failed match=%s guild=%s user=%s status=%s",
                event.match_id,
                guild_id,
                user_id,
                status,
            )
            last_status = status

        return False, last_status

    async def _determine_guild_candidates(
        self, event: MatchCompletedEvent, user_id: int
    ) -> list[int]:
        if event.guild_id is not None:
            return [event.guild_id]

        try:
            guilds = await self._guild_resolver.get_user_guilds(user_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to resolve guilds for user=%s: %s", user_id, exc, exc_info=True)
            return []

        return _deduplicate_guilds(guilds)


def _deduplicate_guilds(guild_ids: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for gid in guild_ids:
        if gid in seen:
            continue
        seen.add(gid)
        ordered.append(gid)
    return ordered
