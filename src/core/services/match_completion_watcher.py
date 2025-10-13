"""Detect newly completed matches for bound Discord users."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from collections.abc import Iterable

from src.core.ports import CachePort, DatabasePort, RiotAPIPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchCompletedEvent:
    """Represents a freshly finished match for a bound Discord user."""

    discord_id: str
    puuid: str
    match_id: str
    region: str
    guild_id: int | None = None


class MatchCompletionWatcher:
    """Poll Riot match history and emit events for matches not yet processed.

    The watcher maintains a lightweight last-seen cache keyed by Discord user
    and PUUID so downstream orchestrators can trigger analysis + voice flows
    only once per game.
    """

    def __init__(
        self,
        *,
        database: DatabasePort,
        riot_api: RiotAPIPort,
        cache: CachePort | None,
        max_history: int = 1,
        cache_ttl_seconds: int = 60 * 60 * 24,
        cache_prefix: str = "match_watcher:last",
    ) -> None:
        self._database = database
        self._riot_api = riot_api
        self._cache = cache
        self._max_history = max(1, max_history)
        self._cache_ttl = cache_ttl_seconds
        self._cache_prefix = cache_prefix
        self._local_state: dict[str, str] = {}

    async def poll_new_matches(self) -> list[MatchCompletedEvent]:
        """Fetch bindings, detect new matches, and return emitted events."""
        try:
            bindings = await self._database.list_user_bindings()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to list user bindings: %s", exc)
            return []

        events: list[MatchCompletedEvent] = []
        for binding in _normalize_bindings(bindings):
            key = self._cache_key(binding.discord_id, binding.puuid)
            last_seen = await self._cache_get(key)

            try:
                match_ids = await self._riot_api.get_match_history(
                    binding.puuid, binding.region, count=self._max_history
                )
            except Exception as exc:
                logger.warning("match_history_fetch_failed for %s: %s", binding.puuid, exc)
                continue

            if not match_ids:
                continue

            latest_match_id = str(match_ids[0])
            if not latest_match_id:
                continue

            if last_seen is None:
                await self._cache_set(key, latest_match_id)
                continue

            if latest_match_id == last_seen:
                continue

            events.append(
                MatchCompletedEvent(
                    discord_id=binding.discord_id,
                    puuid=binding.puuid,
                    match_id=latest_match_id,
                    region=binding.region,
                    guild_id=binding.guild_id,
                )
            )
            await self._cache_set(key, latest_match_id)

        return events

    def _cache_key(self, discord_id: str, puuid: str) -> str:
        return f"{self._cache_prefix}:{discord_id}:{puuid}"

    async def _cache_get(self, key: str) -> str | None:
        if self._cache:
            try:
                value = await self._cache.get(key)
                if isinstance(value, str) and value:
                    self._local_state[key] = value
                    return value
            except Exception:
                logger.debug("Cache get failed for key=%s", key, exc_info=True)
        return self._local_state.get(key)

    async def _cache_set(self, key: str, value: str) -> None:
        self._local_state[key] = value
        if self._cache:
            try:
                await self._cache.set(key, value, ttl=self._cache_ttl)
            except Exception:
                logger.debug("Cache set failed for key=%s", key, exc_info=True)


@dataclass(frozen=True)
class _Binding:
    discord_id: str
    puuid: str
    region: str
    guild_id: int | None


def _normalize_bindings(rows: Iterable[dict[str, Any]]) -> list[_Binding]:
    bindings: list[_Binding] = []
    for row in rows:
        discord_id = str(row.get("discord_id") or "").strip()
        puuid = str(row.get("puuid") or "").strip()
        region = str(row.get("region") or "na1").strip().lower()

        if not discord_id or not puuid:
            continue

        guild_raw = row.get("guild_id")
        try:
            guild_id = int(guild_raw) if guild_raw is not None else None
        except (TypeError, ValueError):
            guild_id = None

        bindings.append(
            _Binding(
                discord_id=discord_id,
                puuid=puuid,
                region=region,
                guild_id=guild_id,
            )
        )
    return bindings
