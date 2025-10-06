"""Unit tests for Riot API adapter.

Tests focus on adapter behavior, mocking Cassiopeia responses.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.riot_api import RiotAPIAdapter
from src.contracts import SummonerDTO


class TestRiotAPIAdapter:
    """Test suite for RiotAPIAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create a RiotAPIAdapter instance for testing."""
        with patch("src.adapters.riot_api.settings") as mock_settings:
            mock_settings.riot_api_key = "test_api_key"
            adapter = RiotAPIAdapter()
            return adapter

    @pytest.mark.asyncio
    async def test_get_summoner_by_puuid_success(self, adapter):
        """Test successful summoner retrieval by PUUID."""
        # Mock Cassiopeia Summoner object
        mock_summoner = MagicMock()
        mock_summoner.account_id = "test_account_id"
        mock_summoner.profile_icon.id = 123
        mock_summoner.revision_date.timestamp.return_value = 1609459200
        mock_summoner.id = "test_summoner_id"
        mock_summoner.puuid = "test_puuid"
        mock_summoner.level = 150
        mock_summoner.name = "TestSummoner"

        with (
            patch("src.adapters.riot_api.Summoner"),
            patch("asyncio.to_thread", new=AsyncMock(return_value=mock_summoner)),
        ):
            result = await adapter.get_summoner_by_puuid("test_puuid", "NA")

        assert isinstance(result, SummonerDTO)
        assert result.puuid == "test_puuid"
        assert result.name == "TestSummoner"
        assert result.summoner_level == 150

    @pytest.mark.asyncio
    async def test_get_summoner_by_puuid_error(self, adapter):
        """Test error handling in summoner retrieval."""
        with patch("asyncio.to_thread", side_effect=Exception("API Error")):
            result = await adapter.get_summoner_by_puuid("test_puuid", "NA")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_match_history_success(self, adapter):
        """Test successful match history retrieval."""
        # Mock match objects
        mock_matches = []
        for i in range(5):
            mock_match = MagicMock()
            mock_match.id = f"NA1_{1000000 + i}"
            mock_matches.append(mock_match)

        # Mock summoner and match history
        mock_summoner = MagicMock()
        mock_match_history = MagicMock()
        mock_match_history.__iter__ = MagicMock(return_value=iter(mock_matches))

        with patch("asyncio.to_thread") as mock_to_thread:
            # First call returns summoner, second returns match history
            mock_to_thread.side_effect = [mock_summoner, mock_match_history]

            # Mock the async generator
            async def mock_async_gen(*args):
                for match in mock_matches[:3]:  # Limit to 3
                    yield match

            with patch.object(adapter, "_async_match_generator", mock_async_gen):
                result = await adapter.get_match_history("test_puuid", "NA", count=3)

        assert len(result) == 3
        assert all(match_id.startswith("NA1_") for match_id in result)

    @pytest.mark.asyncio
    async def test_get_match_timeline_success(self, adapter):
        """Test successful timeline retrieval."""
        # Mock timeline object
        mock_timeline = MagicMock()
        mock_timeline.frame_interval = 60000
        mock_timeline.frames = []
        mock_timeline.match.id = "NA1_1000000"
        mock_timeline.match.participants = []

        # Add mock frames
        for i in range(3):
            mock_frame = MagicMock()
            mock_frame.timestamp = i * 60000
            mock_frame.events = []
            mock_timeline.frames.append(mock_frame)

        mock_match = MagicMock()
        mock_match.timeline = mock_timeline

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = [mock_match, mock_timeline]

            result = await adapter.get_match_timeline("NA1_1000000", "NA")

        assert result is not None
        assert "metadata" in result
        assert "info" in result
        assert result["info"]["frameInterval"] == 60000
        assert len(result["info"]["frames"]) == 3

    @pytest.mark.asyncio
    async def test_get_match_timeline_rate_limit(self, adapter):
        """Test rate limit handling for timeline retrieval."""
        from cassiopeia.datastores.riotapi.common import APIError

        with patch("asyncio.to_thread", side_effect=APIError("Rate limited", 429)):
            result = await adapter.get_match_timeline("NA1_1000000", "NA")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_match_details_success(self, adapter):
        """Test successful match details retrieval."""
        # Mock match object
        mock_match = MagicMock()
        mock_match.id = "NA1_1000000"
        mock_match.creation.timestamp.return_value = 1609459200
        mock_match.duration.seconds = 1800
        mock_match.start.timestamp.return_value = 1609459200
        mock_match.mode.value = "CLASSIC"
        mock_match.type.value = "MATCHED_GAME"
        mock_match.version = "11.1.1"
        mock_match.map.id = 11
        mock_match.platform.value = "NA1"
        mock_match.queue = MagicMock()
        mock_match.queue.id = 420

        # Mock participants
        mock_participants = []
        for i in range(10):
            mock_participant = MagicMock()
            mock_participant.summoner.puuid = f"puuid_{i}"
            mock_participant.summoner.id = f"summoner_{i}"
            mock_participant.summoner.name = f"Player{i}"
            mock_participant.team.side.value = 100 if i < 5 else 200
            mock_participant.id = i + 1
            mock_participant.champion.id = 1 + i
            mock_participant.champion.name = f"Champion{i}"
            mock_participant.stats = MagicMock(
                kills=i,
                deaths=i + 1,
                assists=i + 2,
                gold_earned=10000 + i * 1000,
                total_damage_dealt=50000 + i * 5000,
                vision_score=20 + i,
                win=(i < 5),
            )
            mock_participants.append(mock_participant)

        mock_match.participants = mock_participants

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = [
                mock_match,
                None,
            ]  # Load doesn't return anything

            result = await adapter.get_match_details("NA1_1000000", "NA")

        assert result is not None
        assert "metadata" in result
        assert "info" in result
        assert len(result["info"]["participants"]) == 10
        assert result["info"]["gameDuration"] == 1800

    def test_convert_region(self, adapter):
        """Test region conversion to Cassiopeia format."""
        assert adapter._convert_region("na1") == "NA"
        assert adapter._convert_region("euw1") == "EUW"
        assert adapter._convert_region("kr") == "KR"
        assert adapter._convert_region("unknown") == "NA"  # Default

    @pytest.mark.asyncio
    async def test_async_match_generator(self, adapter):
        """Test the async match generator."""
        # Mock match history
        mock_matches = [MagicMock(id=f"match_{i}") for i in range(5)]
        mock_match_history = MagicMock()
        mock_match_history.__iter__ = MagicMock(return_value=iter(mock_matches))

        matches = []
        async for match in adapter._async_match_generator(mock_match_history, 3):
            matches.append(match)

        assert len(matches) == 3
        assert matches[0].id == "match_0"
