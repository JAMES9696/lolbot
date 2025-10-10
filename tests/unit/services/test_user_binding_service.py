"""Unit tests for UserBindingService.

Tests the service layer business logic without touching external dependencies.
Uses mocks for DatabasePort and RSOPort.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.contracts.user_binding import (
    BindingStatus,
    RiotAccount,
)
from src.core.services.user_binding_service import UserBindingService


@pytest.fixture
def mock_database() -> Mock:
    """Create mock DatabasePort."""
    return Mock()


@pytest.fixture
def mock_rso() -> Mock:
    """Create mock RSOPort."""
    return Mock()


@pytest.fixture
def service(mock_database: Mock, mock_rso: Mock) -> UserBindingService:
    """Create UserBindingService with mocked dependencies."""
    return UserBindingService(database=mock_database, rso_adapter=mock_rso)


class TestInitiateBinding:
    """Test cases for initiate_binding method."""

    @pytest.mark.asyncio
    async def test_initiate_binding_new_user(
        self,
        service: UserBindingService,
        mock_database: Mock,
        mock_rso: Mock,
    ) -> None:
        """Test initiating binding for a new user."""
        # Arrange
        discord_id = "123456789012345678"
        region = "na1"
        auth_url = "https://auth.riotgames.com/authorize?client_id=..."
        state_token = "random_state_token"

        mock_database.get_user_binding = AsyncMock(return_value=None)
        mock_rso.generate_auth_url = AsyncMock(return_value=(auth_url, state_token))
        mock_rso.store_state = AsyncMock(return_value=True)

        # Act
        response = await service.initiate_binding(discord_id, region)

        # Assert
        assert response.success is True
        assert response.auth_url == auth_url
        assert "authenticate with Riot Games" in response.message
        mock_database.get_user_binding.assert_awaited_once_with(discord_id)
        mock_rso.generate_auth_url.assert_awaited_once_with(discord_id, region)
        mock_rso.store_state.assert_awaited_once_with(state_token, discord_id, ttl=600)

    @pytest.mark.asyncio
    async def test_initiate_binding_existing_user(
        self,
        service: UserBindingService,
        mock_database: Mock,
    ) -> None:
        """Test initiating binding when user already has a binding."""
        # Arrange
        discord_id = "123456789012345678"
        # PUUID must be exactly 78 characters
        valid_puuid = "a" * 78
        existing_binding = {
            "discord_id": discord_id,
            "puuid": valid_puuid,
            "summoner_name": "ExistingUser",  # Max 16 chars
            "region": "na1",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        mock_database.get_user_binding = AsyncMock(return_value=existing_binding)

        # Act
        response = await service.initiate_binding(discord_id)

        # Assert
        assert response.success is False
        assert "already bound" in response.message
        assert response.binding is not None
        assert response.binding.puuid == valid_puuid


class TestCompleteBinding:
    """Test cases for complete_binding method."""

    @pytest.mark.asyncio
    async def test_complete_binding_success(
        self,
        service: UserBindingService,
        mock_database: Mock,
        mock_rso: Mock,
    ) -> None:
        """Test successful binding completion."""
        # Arrange
        code = "auth_code_from_riot"
        state = "state_token"
        discord_id = "123456789012345678"
        # PUUID must be exactly 78 characters
        valid_puuid = "b" * 78

        riot_account = RiotAccount(
            puuid=valid_puuid,
            game_name="TestPlayer",
            tag_line="NA1",
            summoner_id="summoner_id",
            account_id="account_id",
            profile_icon_id=123,
            summoner_level=150,
        )

        mock_rso.validate_state = AsyncMock(return_value=discord_id)
        mock_rso.exchange_code = AsyncMock(return_value=riot_account)
        mock_database.save_user_binding = AsyncMock(return_value=True)

        # Act
        response = await service.complete_binding(code, state)

        # Assert
        assert response.success is True
        assert response.binding is not None
        assert response.binding.puuid == riot_account.puuid
        assert response.binding.discord_id == discord_id
        assert "TestPlayer#NA1" in response.message

        mock_rso.validate_state.assert_awaited_once_with(state)
        mock_rso.exchange_code.assert_awaited_once_with(code)
        mock_database.save_user_binding.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_binding_invalid_state(
        self,
        service: UserBindingService,
        mock_rso: Mock,
    ) -> None:
        """Test binding completion with invalid state token."""
        # Arrange
        code = "auth_code"
        state = "invalid_state"

        mock_rso.validate_state = AsyncMock(return_value=None)

        # Act
        response = await service.complete_binding(code, state)

        # Assert
        assert response.success is False
        assert "Invalid or expired" in response.message
        assert response.error == "Invalid state token"

    @pytest.mark.asyncio
    async def test_complete_binding_exchange_failed(
        self,
        service: UserBindingService,
        mock_rso: Mock,
    ) -> None:
        """Test binding completion when code exchange fails."""
        # Arrange
        code = "auth_code"
        state = "valid_state"
        discord_id = "123456789012345678"

        mock_rso.validate_state = AsyncMock(return_value=discord_id)
        mock_rso.exchange_code = AsyncMock(return_value=None)

        # Act
        response = await service.complete_binding(code, state)

        # Assert
        assert response.success is False
        assert "Failed to retrieve Riot account" in response.message
        assert response.error == "Code exchange failed"

    @pytest.mark.asyncio
    async def test_complete_binding_database_save_failed(
        self,
        service: UserBindingService,
        mock_database: Mock,
        mock_rso: Mock,
    ) -> None:
        """Test binding completion when database save fails."""
        # Arrange
        code = "auth_code"
        state = "valid_state"
        discord_id = "123456789012345678"

        riot_account = RiotAccount(
            puuid="test_puuid",
            game_name="TestPlayer",
            tag_line="NA1",
        )

        mock_rso.validate_state = AsyncMock(return_value=discord_id)
        mock_rso.exchange_code = AsyncMock(return_value=riot_account)
        mock_database.save_user_binding = AsyncMock(return_value=False)

        # Act
        response = await service.complete_binding(code, state)

        # Assert
        assert response.success is False
        assert "Failed to save account binding" in response.message


class TestGetBinding:
    """Test cases for get_binding method."""

    @pytest.mark.asyncio
    async def test_get_binding_exists(
        self,
        service: UserBindingService,
        mock_database: Mock,
    ) -> None:
        """Test getting existing binding."""
        # Arrange
        discord_id = "123456789012345678"
        valid_puuid = "c" * 78
        binding_data = {
            "discord_id": discord_id,
            "puuid": valid_puuid,
            "summoner_name": "TestPlayer",  # Max 16 chars
            "region": "na1",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        mock_database.get_user_binding = AsyncMock(return_value=binding_data)

        # Act
        binding = await service.get_binding(discord_id)

        # Assert
        assert binding is not None
        assert binding.discord_id == discord_id
        assert binding.puuid == valid_puuid
        assert binding.status == BindingStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_get_binding_not_exists(
        self,
        service: UserBindingService,
        mock_database: Mock,
    ) -> None:
        """Test getting non-existent binding."""
        # Arrange
        discord_id = "123456789012345678"
        mock_database.get_user_binding = AsyncMock(return_value=None)

        # Act
        binding = await service.get_binding(discord_id)

        # Assert
        assert binding is None


class TestValidateBinding:
    """Test cases for validate_binding method."""

    @pytest.mark.asyncio
    async def test_validate_binding_valid(
        self,
        service: UserBindingService,
        mock_database: Mock,
    ) -> None:
        """Test validating a valid binding."""
        # Arrange
        discord_id = "123456789012345678"
        valid_puuid = "d" * 78
        binding_data = {
            "discord_id": discord_id,
            "puuid": valid_puuid,
            "summoner_name": "TestPlayer",
            "region": "na1",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        mock_database.get_user_binding = AsyncMock(return_value=binding_data)

        # Act
        is_valid, puuid = await service.validate_binding(discord_id)

        # Assert
        assert is_valid is True
        assert puuid == valid_puuid

    @pytest.mark.asyncio
    async def test_validate_binding_invalid(
        self,
        service: UserBindingService,
        mock_database: Mock,
    ) -> None:
        """Test validating an invalid binding."""
        # Arrange
        discord_id = "123456789012345678"
        mock_database.get_user_binding = AsyncMock(return_value=None)

        # Act
        is_valid, puuid = await service.validate_binding(discord_id)

        # Assert
        assert is_valid is False
        assert puuid is None
