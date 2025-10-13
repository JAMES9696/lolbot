"""Unit tests for Riot API adapter.

Tests focus on adapter behavior, mocking Cassiopeia responses.
"""

import asyncio
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
        """Test successful match history retrieval via direct HTTP API."""
        # Mock HTTP response with match IDs
        mock_match_ids = [f"NA1_{1000000 + i}" for i in range(3)]

        # Mock aiohttp session and response
        session = MagicMock()
        session.closed = False

        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(return_value=mock_match_ids)
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock()
        session.get.return_value = response

        adapter._session = session
        adapter._session_loop = asyncio.get_running_loop()

        result = await adapter.get_match_history("test_puuid", "NA", count=3)

        assert len(result) == 3
        assert all(match_id.startswith("NA1_") for match_id in result)
        session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_match_timeline_success(self, adapter):
        """Test successful timeline retrieval via direct HTTP API."""
        # Mock HTTP timeline response
        mock_timeline_data = {
            "metadata": {"dataVersion": "2", "matchId": "NA1_1000000", "participants": []},
            "info": {
                "frameInterval": 60000,
                "frames": [
                    {"timestamp": i * 60000, "participantFrames": {}, "events": []}
                    for i in range(3)
                ],
            },
        }

        # Mock aiohttp session and responses
        session = MagicMock()
        session.closed = False

        # Timeline response
        timeline_response = MagicMock()
        timeline_response.status = 200
        timeline_response.json = AsyncMock(return_value=mock_timeline_data)
        timeline_response.__aenter__ = AsyncMock(return_value=timeline_response)
        timeline_response.__aexit__ = AsyncMock()

        # Match details response (called internally by get_match_timeline)
        match_response = MagicMock()
        match_response.status = 200
        match_response.json = AsyncMock(
            return_value={
                "metadata": {"matchId": "NA1_1000000"},
                "info": {"gameId": 1000000, "participants": []},
            }
        )
        match_response.__aenter__ = AsyncMock(return_value=match_response)
        match_response.__aexit__ = AsyncMock()

        # session.get returns timeline first, then match details
        session.get.side_effect = [timeline_response, match_response]

        adapter._session = session
        adapter._session_loop = asyncio.get_running_loop()

        result = await adapter.get_match_timeline("NA1_1000000", "NA")

        assert result is not None
        assert "metadata" in result
        assert "info" in result
        assert result["info"]["frame_interval"] == 60000
        assert len(result["info"]["frames"]) == 3

    @pytest.mark.asyncio
    async def test_get_match_timeline_404_not_found(self, adapter):
        """Test timeline retrieval returns None for 404 (replaces rate limit test)."""
        # Mock 404 response
        session = MagicMock()
        session.closed = False

        response = MagicMock()
        response.status = 404
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock()
        session.get.return_value = response

        adapter._session = session
        adapter._session_loop = asyncio.get_running_loop()

        result = await adapter.get_match_timeline("NA1_1000000", "NA")

        # Should return None for 404 (match not found)
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
    async def test_get_match_history_handles_errors(self, adapter):
        """Test match history error handling (replaces obsolete _async_match_generator test)."""
        # Mock session with 500 error response
        session = MagicMock()
        session.closed = False

        response = MagicMock()
        response.status = 500
        response.text = AsyncMock(return_value="Internal Server Error")
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock()
        session.get.return_value = response

        adapter._session = session
        adapter._session_loop = asyncio.get_running_loop()

        # Should return empty list on error, not raise
        result = await adapter.get_match_history("test_puuid", "NA", count=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_session_recreated_across_event_loops(self, adapter, monkeypatch):
        """Ensure _ensure_session refreshes aiohttp session when loop changes."""
        import aiohttp

        class DummySession:
            def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
                self._loop = loop
                self.closed = False

            async def close(self) -> None:
                self.closed = True

        created_sessions: list[DummySession] = []

        def _fake_client_session(*_args, **_kwargs):
            session = DummySession(asyncio.get_running_loop())
            created_sessions.append(session)
            return session

        monkeypatch.setattr(aiohttp, "ClientSession", _fake_client_session)

        # First ensure creates a session bound to current loop
        session1 = await adapter._ensure_session()
        loop1 = asyncio.get_running_loop()
        assert adapter._session_loop is loop1
        assert session1 in created_sessions

        # Same loop reuse should not recreate session
        session_same = await adapter._ensure_session()
        assert session_same is session1

        # Simulate loop switch by mutating stored loop marker
        adapter._session_loop = object()  # type: ignore[attr-defined]
        session2 = await adapter._ensure_session()
        assert session2 is not session1
        assert session1.closed

        # Closed session should be replaced on next call if marked closed already
        session2.closed = True  # type: ignore[attr-defined]
        session3 = await adapter._ensure_session()
        assert session3 is not session2
        assert session2.closed
        assert adapter._session_loop is asyncio.get_running_loop()

        await adapter.close()
