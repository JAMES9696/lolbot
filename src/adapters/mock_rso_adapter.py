"""Mock RSO OAuth adapter for testing without Production API Key.

This adapter simulates the RSO OAuth flow using pre-configured test accounts,
allowing end-to-end testing of the /bind command without requiring actual
Riot OAuth credentials.
"""

import logging
from uuid import uuid4

from src.contracts.user_binding import RiotAccount
from src.core.rso_port import RSOPort

logger = logging.getLogger(__name__)


class MockRSOAdapter(RSOPort):
    """Mock RSO adapter for development testing.

    Simulates RSO OAuth flow with pre-configured test accounts.
    """

    def __init__(self, redis_client=None) -> None:
        """Initialize mock RSO adapter.

        Args:
            redis_client: Optional Redis client (required for state validation)
        """
        self.redis = redis_client

        # Pre-configured test accounts (can be extended)
        # Note: PUUID must be exactly 78 characters (Riot standard)
        self.test_accounts = {
            "test_code_1": RiotAccount(
                puuid="0" * 78,  # Mock PUUID (78 chars)
                game_name="FujiShanXia",  # Max 16 chars, no spaces
                tag_line="NA1",
            ),
            "test_code_2": RiotAccount(
                puuid="1" * 78,  # Mock PUUID (78 chars)
                game_name="TestPlayer",
                tag_line="NA1",
            ),
            "test_code_3": RiotAccount(
                puuid="2" * 78,  # Mock PUUID (78 chars)
                game_name="DemoSummoner",
                tag_line="KR",
            ),
        }

        logger.info("MockRSOAdapter initialized with %d test accounts", len(self.test_accounts))

    async def generate_auth_url(self, discord_id: str, region: str = "na1") -> tuple[str, str]:
        """Generate mock authorization URL.

        Returns a mock URL that simulates the OAuth flow. In development,
        you can manually trigger the callback with a test code.

        Args:
            discord_id: Discord user ID
            region: Riot region (unused in mock)

        Returns:
            Tuple of (auth_url, state_token)
        """
        # Generate state token
        state = uuid4().hex

        # Store state in Redis for validation (same as real adapter)
        if self.redis:
            await self.store_state(state, discord_id, ttl=600)

        # Generate mock auth URL with instructions
        mock_url = (
            f"http://localhost:3000/mock-oauth?"
            f"state={state}&"
            f"discord_id={discord_id}&"
            f"region={region}"
        )

        logger.info(
            "Generated mock auth URL for Discord user %s",
            discord_id,
            extra={"state": state, "region": region},
        )

        return mock_url, state

    async def exchange_code(self, code: str) -> RiotAccount | None:
        """Exchange mock authorization code for test account info.

        Args:
            code: Mock authorization code (e.g., "test_code_1")

        Returns:
            Mock RiotAccount if code is valid, None otherwise
        """
        # Check if code matches a test account
        if code in self.test_accounts:
            account = self.test_accounts[code]
            logger.info(
                "Mock code exchange successful: %s#%s",
                account.game_name,
                account.tag_line,
                extra={"code": code, "puuid": account.puuid},
            )
            return account

        # If not a pre-defined code, generate a dynamic mock account
        if code.startswith("test_"):
            # Generate 78-char PUUID using UUID
            mock_puuid = (uuid4().hex + uuid4().hex + uuid4().hex)[:78]
            account = RiotAccount(
                puuid=mock_puuid,
                game_name=f"TestUser{code[-3:]}",
                tag_line="NA1",
            )
            logger.info(
                "Generated dynamic mock account: %s#%s",
                account.game_name,
                account.tag_line,
                extra={"code": code},
            )
            return account

        logger.warning("Invalid mock code: %s", code)
        return None

    async def validate_state(self, state: str) -> str | None:
        """Validate state token and return Discord ID.

        Same implementation as real adapter (uses Redis).

        Args:
            state: State token to validate

        Returns:
            Discord ID if valid, None otherwise
        """
        if not self.redis:
            logger.warning("No Redis client, skipping state validation in mock")
            return None

        try:
            # Retrieve Discord ID from Redis
            key = f"rso:state:{state}"
            discord_id = await self.redis.get(key)

            if discord_id:
                # Delete state after use (one-time token)
                await self.redis.delete(key)
                logger.info("Valid mock state token for Discord ID %s", discord_id)
                return discord_id

            logger.warning("Invalid or expired mock state token: %s", state)
            return None

        except Exception as e:
            logger.error("Error validating mock state: %s", e)
            return None

    async def store_state(self, state: str, discord_id: str, ttl: int = 600) -> bool:
        """Store state token in Redis.

        Same implementation as real adapter.

        Args:
            state: State token
            discord_id: Discord user ID
            ttl: Time-to-live in seconds

        Returns:
            True if stored successfully, False otherwise
        """
        if not self.redis:
            logger.warning("No Redis client, cannot store mock state")
            return False

        try:
            key = f"rso:state:{state}"
            await self.redis.set(key, discord_id, ttl=ttl)
            logger.debug("Stored mock state token for Discord ID %s", discord_id)
            return True
        except Exception as e:
            logger.error("Error storing mock state: %s", e)
            return False

    def add_test_account(self, code: str, account: RiotAccount) -> None:
        """Add a custom test account for testing.

        Args:
            code: Mock authorization code
            account: RiotAccount to associate with the code
        """
        self.test_accounts[code] = account
        logger.info(
            "Added test account: %s#%s with code %s", account.game_name, account.tag_line, code
        )

    def list_test_accounts(self) -> dict[str, RiotAccount]:
        """Get all available test accounts.

        Returns:
            Dictionary mapping codes to RiotAccounts
        """
        return self.test_accounts.copy()
