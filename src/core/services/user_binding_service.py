"""User binding service implementing business logic for Discord-Riot account binding.

This service orchestrates the binding process using DatabasePort and RSOPort,
providing a clean interface for the application layer.
"""

# mypy: disable-error-code="call-arg"

import logging
from datetime import UTC, datetime

from src.contracts.user_binding import (
    BindingResponse,
    BindingStatus,
    UserBinding,
)
from src.core.ports import DatabasePort, RSOPort

logger = logging.getLogger(__name__)


class UserBindingService:
    """Service for managing Discord-Riot account bindings.

    Implements the business logic for:
    - Initiating RSO OAuth flow
    - Processing OAuth callbacks
    - Storing and retrieving bindings
    - Validating binding status
    """

    def __init__(self, database: DatabasePort, rso_adapter: RSOPort) -> None:
        """Initialize service with required dependencies.

        Args:
            database: Database adapter for persistence
            rso_adapter: RSO OAuth adapter for authentication
        """
        self.database = database
        self.rso_adapter = rso_adapter
        logger.info("UserBindingService initialized")

    async def initiate_binding(self, discord_id: str, region: str = "na1") -> BindingResponse:
        """Initiate binding process by generating RSO OAuth URL.

        Args:
            discord_id: Discord user ID
            region: Preferred Riot region

        Returns:
            BindingResponse with auth URL or error
        """
        try:
            # Check if user is already bound
            existing_binding = await self.database.get_user_binding(discord_id)
            if existing_binding:
                logger.info(f"User {discord_id} already has binding to {existing_binding['puuid']}")
                return BindingResponse(
                    success=False,
                    message="Account already bound. Use /unbind first to change accounts.",
                    binding=UserBinding(
                        discord_id=discord_id,
                        puuid=existing_binding["puuid"],
                        summoner_name=existing_binding["summoner_name"],
                        region=existing_binding["region"],
                        status=BindingStatus.VERIFIED,
                        created_at=existing_binding["created_at"],
                        updated_at=existing_binding["updated_at"],
                    ),
                )

            # Generate OAuth URL
            auth_url, state_token = await self.rso_adapter.generate_auth_url(discord_id, region)

            # Store state token for validation
            await self.rso_adapter.store_state(state_token, discord_id, ttl=600)

            logger.info(f"Generated auth URL for Discord user {discord_id}")
            return BindingResponse(
                success=True,
                message="Click the link to authenticate with Riot Games",
                auth_url=auth_url,
            )

        except Exception as e:
            logger.error(f"Error initiating binding for {discord_id}: {e}")
            return BindingResponse(
                success=False,
                message="Failed to initiate binding process",
                error=str(e),
            )

    async def complete_binding(self, code: str, state: str) -> BindingResponse:
        """Complete binding process using OAuth callback.

        Args:
            code: OAuth authorization code from Riot
            state: State token for CSRF validation

        Returns:
            BindingResponse with binding result
        """
        try:
            # Validate state token and get Discord ID
            discord_id = await self.rso_adapter.validate_state(state)
            if not discord_id:
                logger.warning(f"Invalid state token: {state}")
                return BindingResponse(
                    success=False,
                    message="Invalid or expired authentication session",
                    error="Invalid state token",
                )

            # Exchange code for Riot account info
            riot_account = await self.rso_adapter.exchange_code(code)
            if not riot_account:
                logger.error(f"Failed to exchange code for Discord user {discord_id}")
                return BindingResponse(
                    success=False,
                    message="Failed to retrieve Riot account information",
                    error="Code exchange failed",
                )

            # Save binding to database
            success = await self.database.save_user_binding(
                discord_id=discord_id,
                puuid=riot_account.puuid,
                summoner_name=f"{riot_account.game_name}#{riot_account.tag_line}",
            )

            if not success:
                logger.error(f"Failed to save binding for {discord_id}")
                return BindingResponse(
                    success=False,
                    message="Failed to save account binding",
                    error="Database save failed",
                )

            # Create response with binding data
            binding = UserBinding(
                discord_id=discord_id,
                puuid=riot_account.puuid,
                summoner_name=f"{riot_account.game_name}#{riot_account.tag_line}",
                region="na1",  # Default for now
                status=BindingStatus.VERIFIED,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            logger.info(
                f"Successfully bound Discord user {discord_id} to Riot account "
                f"{riot_account.game_name}#{riot_account.tag_line}"
            )

            return BindingResponse(
                success=True,
                message=f"Successfully bound to {riot_account.game_name}#{riot_account.tag_line}",
                binding=binding,
            )

        except Exception as e:
            logger.error(f"Error completing binding: {e}")
            return BindingResponse(
                success=False,
                message="An unexpected error occurred during binding",
                error=str(e),
            )

    async def get_binding(self, discord_id: str) -> UserBinding | None:
        """Get user binding by Discord ID.

        Args:
            discord_id: Discord user ID

        Returns:
            UserBinding if found, None otherwise
        """
        try:
            binding_data = await self.database.get_user_binding(discord_id)
            if not binding_data:
                return None

            return UserBinding(
                discord_id=binding_data["discord_id"],
                puuid=binding_data["puuid"],
                summoner_name=binding_data["summoner_name"],
                region=binding_data["region"],
                status=BindingStatus.VERIFIED,
                created_at=binding_data["created_at"],
                updated_at=binding_data["updated_at"],
            )

        except Exception as e:
            logger.error(f"Error fetching binding for {discord_id}: {e}")
            return None

    async def unbind(self, discord_id: str) -> BindingResponse:
        """Remove binding for a Discord user.

        Note: This is a placeholder. Full implementation would require
        a delete method in DatabasePort.

        Args:
            discord_id: Discord user ID

        Returns:
            BindingResponse with result
        """
        logger.warning(f"Unbind not fully implemented for {discord_id}")
        return BindingResponse(
            success=False,
            message="Unbind functionality not yet implemented",
            error="Not implemented",
        )

    async def validate_binding(self, discord_id: str) -> tuple[bool, str | None]:
        """Validate that a Discord user has a valid binding.

        Args:
            discord_id: Discord user ID

        Returns:
            Tuple of (is_valid, puuid or None)
        """
        binding = await self.get_binding(discord_id)
        if not binding or not binding.puuid:
            return False, None

        return True, binding.puuid
