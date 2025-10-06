"""Redis cache adapter for state management and caching."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from src.config import get_settings
from src.core.ports import CachePort

logger = logging.getLogger(__name__)


class RedisAdapter(CachePort):
    """Redis cache adapter using async redis client."""

    def __init__(self) -> None:
        """Initialize Redis adapter."""
        self.settings = get_settings()
        self._client: Any = None  # aioredis.Redis (untyped library)

    async def connect(self) -> None:
        """Connect to Redis."""
        if self._client:
            logger.warning("Redis client already connected")
            return

        try:
            self._client = await aioredis.from_url(
                self.settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("Redis client connected")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis client disconnected")

    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        KISS: return raw strings as-is to avoid unintended type coercion.
        Only attempt JSON parse when the value clearly looks like a JSON
        object or array (starts with '{' or '['). This prevents numeric
        strings like Discord IDs from being converted to integers.
        """
        if not self._client:
            logger.error("Redis client not connected")
            return None

        try:
            value = await self._client.get(key)
            if value is None:
                return None

            # Avoid coercing numeric strings to int; parse JSON only for
            # obvious JSON payloads (dict/array). DRY with `set()` which
            # serializes dict/list to JSON strings starting with '{'/'['.
            try:
                trimmed = value.lstrip() if isinstance(value, str) else str(value).lstrip()
                if trimmed.startswith("{") or trimmed.startswith("["):
                    return json.loads(value)
            except json.JSONDecodeError:
                pass

            return value
        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache with optional TTL."""
        if not self._client:
            logger.error("Redis client not connected")
            return False

        try:
            # Serialize complex objects as JSON
            if isinstance(value, dict | list):
                value = json.dumps(value)
            elif not isinstance(value, str):
                value = str(value)

            if ttl:
                await self._client.setex(key, ttl, value)
            else:
                await self._client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self._client:
            logger.error("Redis client not connected")
            return False

        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            return False

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        if not self._client:
            return False

        try:
            await self._client.ping()
            return True
        except Exception:
            return False
