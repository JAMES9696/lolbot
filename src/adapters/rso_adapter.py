"""RSO (Riot Sign-On) OAuth adapter implementation.

Observability:
- All critical RSO steps are wrapped with `llm_debug_wrapper` to emit
  structured logs for production monitoring:
  1) Auth URL generation (+state token issuance)
  2) Code -> token exchange
  3) `accounts/me` fetch (PUUID retrieval)
  4) State storage/validation in Redis
"""
# mypy: disable-error-code="call-arg,no-any-return"

import logging
from typing import Any
from uuid import uuid4

import aiohttp

from src.config.settings import get_settings
from src.core.observability import llm_debug_wrapper
from src.contracts.user_binding import RiotAccount
from src.core.rso_port import RSOPort

logger = logging.getLogger(__name__)


class RSOAdapter(RSOPort):
    """RSO OAuth adapter using Riot's official OAuth flow."""

    def __init__(self, redis_client: Any = None) -> None:
        """Initialize RSO adapter.

        Args:
            redis_client: Optional Redis client for state storage (CachePort)
        """
        self.settings = get_settings()
        self.redis = redis_client
        self.client_id = self.settings.security_rso_client_id
        self.client_secret = self.settings.security_rso_client_secret
        self.redirect_uri = self.settings.security_rso_redirect_uri

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"flow": "rso_oauth", "step": "generate_auth_url"},
    )
    async def generate_auth_url(self, discord_id: str, region: str = "na1") -> tuple[str, str]:
        """Generate RSO authorization URL with state token.

        Notes:
            - Riot RSO requires exact `redirect_uri` match (scheme/host/port/path)
            - Scopes must include at least: `openid offline_access` (optionally `cpid`)
            - All parameters must be URL-encoded
        """
        # Basic config validation to avoid "Invalid Request" at auth endpoint
        if not self.client_id:
            raise ValueError("RSO OAuth misconfigured: SECURITY_RSO_CLIENT_ID is missing")
        if not self.redirect_uri:
            raise ValueError("RSO OAuth misconfigured: SECURITY_RSO_REDIRECT_URI is missing")

        # Generate secure state token
        state = uuid4().hex

        # Store state in Redis for validation (10 min TTL)
        if self.redis:
            await self.store_state(state, discord_id, ttl=600)

        # Build OAuth URL using safe encoding
        from urllib.parse import urlencode

        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                # Include offline_access for refresh tokens; add cpid for LoL platform id
                "scope": "openid offline_access cpid",
                "state": state,
                # Prompt ensures explicit consent when needed
                "prompt": "consent",
            }
        )
        auth_url = f"https://auth.riotgames.com/authorize?{query}"

        logger.info("Generated RSO auth URL", extra={"discord_id": discord_id})
        return auth_url, state

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"flow": "rso_oauth", "step": "exchange_code"},
    )
    async def exchange_code(self, code: str) -> RiotAccount | None:
        """Exchange authorization code for access token and user info."""
        if not self.client_id or not self.client_secret:
            logger.error("RSO client credentials not configured")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Exchange code for access token
                token_url = "https://auth.riotgames.com/token"
                token_data = {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                }

                auth = aiohttp.BasicAuth(self.client_id, self.client_secret)

                async with session.post(token_url, data=token_data, auth=auth) as resp:
                    if resp.status != 200:
                        logger.error(f"Token exchange failed: {resp.status}")
                        return None

                    token_response = await resp.json()
                    access_token = token_response.get("access_token")

                if not access_token:
                    logger.error("No access token in response")
                    return None

                # Step 2: Get user account info
                account_url = "https://americas.api.riotgames.com/riot/account/v1/accounts/me"
                headers = {"Authorization": f"Bearer {access_token}"}

                async with session.get(account_url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.error(f"Account fetch failed: {resp.status}")
                        return None

                    account_data = await resp.json()

                # Convert to RiotAccount contract
                riot_account = RiotAccount(
                    puuid=account_data["puuid"],
                    game_name=account_data["gameName"],
                    tag_line=account_data["tagLine"],
                )

                logger.info(
                    f"Successfully exchanged code for account: {riot_account.game_name}#{riot_account.tag_line}"
                )
                return riot_account

        except Exception as e:
            logger.error(f"Error during code exchange: {e}", exc_info=True)
            return None

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"flow": "rso_oauth", "step": "validate_state"},
    )
    async def validate_state(self, state: str) -> str | None:
        """Validate state token and return Discord ID."""
        if not self.redis:
            logger.warning("No Redis client, skipping state validation")
            return None

        try:
            # Retrieve Discord ID from Redis
            key = f"rso:state:{state}"
            discord_id = await self.redis.get(key)

            if discord_id:
                # Delete state after use (one-time token)
                await self.redis.delete(key)
                logger.info(f"Valid state token for Discord ID {discord_id}")
                return discord_id

            logger.warning(f"Invalid or expired state token: {state}")
            return None

        except Exception as e:
            logger.error(f"Error validating state: {e}")
            return None

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"flow": "rso_oauth", "step": "store_state"},
    )
    async def store_state(self, state: str, discord_id: str, ttl: int = 600) -> bool:
        """Store state token in Redis."""
        if not self.redis:
            logger.warning("No Redis client, cannot store state")
            return False

        try:
            key = f"rso:state:{state}"
            await self.redis.set(key, discord_id, ttl=ttl)
            logger.debug(f"Stored state token for Discord ID {discord_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing state: {e}")
            return False
