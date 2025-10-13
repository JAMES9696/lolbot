"""Unit tests for database adapter.

Tests focus on adapter behavior with mocked asyncpg operations.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from src.adapters.database import DatabaseAdapter


class TestDatabaseAdapter:
    """Test suite for DatabaseAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create a DatabaseAdapter instance for testing."""
        return DatabaseAdapter()

    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        pool.close = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        """Test successful database connection."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with (
            patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)) as mock_create,
            patch("src.adapters.database.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql://test"
            mock_settings.database_pool_size = 20
            mock_settings.database_pool_timeout = 30

            await adapter.connect()

            mock_create.assert_called_once()
            assert adapter._pool == mock_pool

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, adapter, mock_pool):
        """Test connecting when pool already exists."""
        adapter._pool = mock_pool

        with patch("asyncpg.create_pool") as mock_create:
            await adapter.connect()
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_error(self, adapter):
        """Test database connection error handling."""
        with (
            patch("asyncpg.create_pool", side_effect=Exception("Connection failed")),
            pytest.raises(Exception, match="Connection failed"),
        ):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter, mock_pool):
        """Test database disconnection."""
        adapter._pool = mock_pool

        await adapter.disconnect()

        mock_pool.close.assert_called_once()
        assert adapter._pool is None

    @pytest.mark.asyncio
    async def test_save_user_binding_success(self, adapter, mock_pool):
        """Test successful user binding save."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.save_user_binding("discord_123", "puuid_456", "TestSummoner")

        assert result is True
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_user_binding_duplicate_puuid(self, adapter, mock_pool):
        """Test handling duplicate PUUID binding."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = asyncpg.UniqueViolationError("duplicate key")
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.save_user_binding("discord_123", "puuid_456", "TestSummoner")

        assert result is False

    @pytest.mark.asyncio
    async def test_save_user_binding_no_pool(self, adapter):
        """Test saving user binding without pool."""
        result = await adapter.save_user_binding("discord_123", "puuid_456", "TestSummoner")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_binding_found(self, adapter, mock_pool):
        """Test retrieving existing user binding."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()

        mock_row = {
            "discord_id": "discord_123",
            "puuid": "puuid_456",
            "summoner_name": "TestSummoner",
            "summoner_id": "summoner_789",
            "region": "na1",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        mock_conn.fetchrow.return_value = mock_row
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.get_user_binding("discord_123")

        assert result == mock_row
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_binding_not_found(self, adapter, mock_pool):
        """Test retrieving non-existent user binding."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.get_user_binding("discord_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_user_bindings_returns_rows(self, adapter, mock_pool):
        """List all user bindings ordered by latest update."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_rows = [
            {
                "discord_id": "123",
                "puuid": "puuid_123",
                "summoner_name": "Tester#NA1",
                "region": "na1",
                "updated_at": datetime.now(UTC),
            }
        ]
        mock_conn.fetch.return_value = mock_rows

        rows = await adapter.list_user_bindings()

        assert rows == mock_rows
        mock_conn.fetch.assert_called_once()
        executed_sql = mock_conn.fetch.call_args.args[0]
        assert "FROM user_bindings" in executed_sql
        assert "ORDER BY updated_at DESC" in executed_sql

    @pytest.mark.asyncio
    async def test_list_user_bindings_without_pool(self, adapter):
        """Return empty list when connection pool is unavailable."""
        rows = await adapter.list_user_bindings()
        assert rows == []

    @pytest.mark.asyncio
    async def test_save_match_data_success(self, adapter, mock_pool):
        """Test successful match data save."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        # Mock transaction() method to return a proper async context manager
        # Use contextlib.asynccontextmanager to create a real async context manager
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_transaction_cm():
            yield None

        mock_conn.transaction = MagicMock(return_value=mock_transaction_cm())
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        match_data = {
            "metadata": {
                "matchId": "NA1_1000000",
                "participants": ["puuid1", "puuid2"],
            },
            "info": {
                "gameCreation": 1609459200000,
                "gameDuration": 1800,
                "platformId": "NA1",
                "participants": [
                    {
                        "puuid": "puuid1",
                        "championId": 1,
                        "teamId": 100,
                        "win": True,
                        "kills": 5,
                        "deaths": 2,
                        "assists": 10,
                    },
                    {
                        "puuid": "puuid2",
                        "championId": 2,
                        "teamId": 200,
                        "win": False,
                        "kills": 3,
                        "deaths": 5,
                        "assists": 7,
                    },
                ],
            },
        }

        timeline_data = {
            "metadata": {"matchId": "NA1_1000000"},
            "info": {"frames": [], "frameInterval": 60000},
        }

        result = await adapter.save_match_data("NA1_1000000", match_data, timeline_data)

        assert result is True
        # Should have 3 executes: 1 for match_data, 2 for participants
        assert mock_conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_save_match_data_error(self, adapter, mock_pool):
        """Test match data save error handling."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_conn.transaction.side_effect = Exception("Transaction failed")
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.save_match_data("NA1_1000000", {}, {})

        assert result is False

    @pytest.mark.asyncio
    async def test_get_match_data_found(self, adapter, mock_pool):
        """Test retrieving existing match data."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()

        mock_row = {
            "match_data": {"info": {"gameId": "NA1_1000000"}},
            "timeline_data": {"info": {"frames": []}},
            "analysis_data": {"score": 95},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        mock_conn.fetchrow.return_value = mock_row
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.get_match_data("NA1_1000000")

        assert result is not None
        assert result["match_data"]["info"]["gameId"] == "NA1_1000000"

    @pytest.mark.asyncio
    async def test_get_recent_matches_for_user(self, adapter, mock_pool):
        """Test retrieving recent matches for a user."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()

        mock_rows = [
            {
                "match_id": f"NA1_{1000000 + i}",
                "match_data": {"info": {"gameId": f"NA1_{1000000 + i}"}},
                "game_creation": 1609459200000 + i * 3600000,
                "champion_id": i + 1,
                "win": i % 2 == 0,
                "kills": i + 3,
                "deaths": i + 1,
                "assists": i + 5,
            }
            for i in range(5)
        ]
        mock_conn.fetch.return_value = mock_rows
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.get_recent_matches_for_user("puuid_123", limit=5)

        assert len(result) == 5
        assert all("match_id" in match for match in result)

    @pytest.mark.asyncio
    async def test_update_match_analysis_success(self, adapter, mock_pool):
        """Test updating match with analysis data."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        analysis_data = {
            "performance_scores": {"puuid1": 85.5, "puuid2": 72.3},
            "key_moments": ["First Blood", "Baron Steal"],
        }

        result = await adapter.update_match_analysis("NA1_1000000", analysis_data)

        assert result is True
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter, mock_pool):
        """Test successful health check."""
        adapter._pool = mock_pool
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_no_pool(self, adapter):
        """Test health check without pool."""
        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, adapter, mock_pool):
        """Test health check with connection error."""
        adapter._pool = mock_pool
        mock_pool.acquire.side_effect = Exception("Connection error")

        result = await adapter.health_check()

        assert result is False
