"""HTTP client adapter implementing the VoiceBroadcastPort."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from src.config.settings import get_settings
from src.core.ports import VoiceBroadcastPort

logger = logging.getLogger(__name__)


class VoiceBroadcastHttpClient(VoiceBroadcastPort):
    """Invoke the callback server's /broadcast endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        secret: str | None = None,
        session: aiohttp.ClientSession | None = None,
        request_timeout: float = 5.0,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.broadcast_server_url).rstrip("/")
        self._secret = secret or settings.broadcast_webhook_secret
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._session = session
        self._owns_session = session is None

    async def broadcast_to_user(
        self, *, guild_id: int, user_id: int, match_id: str
    ) -> tuple[bool, str]:
        payload: dict[str, Any] = {
            "match_id": match_id,
            "guild_id": guild_id,
            "user_id": user_id,
        }
        headers: dict[str, str] = {}
        if self._secret:
            headers["X-Auth-Token"] = self._secret

        session = await self._ensure_session()
        url = f"{self._base_url}/broadcast"

        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "Broadcast HTTP error status=%s match=%s guild=%s user=%s",
                        resp.status,
                        match_id,
                        guild_id,
                        user_id,
                    )
                    return False, f"http_{resp.status}"

                data = await resp.json()
        except Exception as exc:
            logger.error(
                "Broadcast request failed match=%s guild=%s user=%s error=%s",
                match_id,
                guild_id,
                user_id,
                exc,
            )
            return False, "network_error"

        ok = bool(data.get("ok"))
        message = str(data.get("message") or data.get("error") or "unknown")
        return ok, message

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session
