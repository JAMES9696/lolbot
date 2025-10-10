"""Unit tests for Celery match tasks.

Tests task execution logic using mocked adapters.
These tests verify task behavior without requiring a running Celery worker.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.match_tasks import fetch_match_history


class TestFetchMatchHistory:
    """Test cases for fetch_match_history task."""

    @patch("src.tasks.match_tasks.RiotAPIAdapter")
    @patch("src.tasks.match_tasks.asyncio.new_event_loop")
    def test_fetch_match_history_success(
        self,
        mock_event_loop: MagicMock,
        mock_riot_api_class: MagicMock,
    ) -> None:
        """Test successful match history fetch."""
        # Arrange
        puuid = "test_puuid_123"
        region = "na1"
        count = 5

        # Mock return values
        mock_match_ids = ["NA1_123", "NA1_124", "NA1_125", "NA1_126", "NA1_127"]

        # Setup mock RiotAPIAdapter
        mock_riot_api = MagicMock()
        mock_riot_api.get_match_history = AsyncMock(return_value=mock_match_ids)
        mock_riot_api_class.return_value = mock_riot_api

        # Setup mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = mock_match_ids
        mock_event_loop.return_value = mock_loop

        # Create a mock task instance
        mock_task = MagicMock()
        mock_task.request.id = "test-task-id"
        mock_task.request.retries = 0

        # Act
        result = fetch_match_history(
            mock_task,
            puuid=puuid,
            region=region,
            count=count,
        )

        # Assert
        assert result["success"] is True
        assert result["puuid"] == puuid
        assert result["region"] == region
        assert result["match_ids"] == mock_match_ids
        assert result["count"] == 5
        assert result["task_id"] == "test-task-id"

        # Verify adapter was called correctly
        mock_loop.run_until_complete.assert_called_once()
        mock_loop.close.assert_called_once()

    @patch("src.tasks.match_tasks.RiotAPIAdapter")
    @patch("src.tasks.match_tasks.asyncio.new_event_loop")
    def test_fetch_match_history_with_retry(
        self,
        mock_event_loop: MagicMock,
        mock_riot_api_class: MagicMock,
    ) -> None:
        """Test match history fetch with retry on error."""
        # Arrange
        puuid = "test_puuid_123"

        # Setup mock to raise exception
        mock_riot_api = MagicMock()
        mock_riot_api_class.return_value = mock_riot_api

        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = Exception("API Error")
        mock_event_loop.return_value = mock_loop

        # Create mock task with retry capability
        mock_task = MagicMock()
        mock_task.request.id = "test-task-id"
        mock_task.request.retries = 0
        mock_task.retry.side_effect = Exception("Retry triggered")

        # Act & Assert
        with pytest.raises(Exception, match="Retry triggered"):
            fetch_match_history(
                mock_task,
                puuid=puuid,
            )

        # Verify retry was called
        mock_task.retry.assert_called_once()
        mock_loop.close.assert_called_once()


class TestTaskConfiguration:
    """Test task configuration and metadata."""

    def test_fetch_match_history_task_config(self) -> None:
        """Verify task configuration settings."""
        # Check task name
        assert fetch_match_history.name == "src.tasks.match_tasks.fetch_match_history"

        # Check retry settings
        assert fetch_match_history.max_retries == 3
        assert fetch_match_history.default_retry_delay == 60

    def test_task_binding(self) -> None:
        """Verify task is bound (has access to self/request)."""
        # The bind=True parameter means the task receives self as first argument
        assert fetch_match_history.bind is True


@pytest.mark.integration
class TestTaskIntegration:
    """Integration tests for task execution.

    These tests require a running Celery worker and Redis broker.
    Skip in CI if dependencies are not available.
    """

    @pytest.mark.skip(reason="Requires running Celery worker and Redis")
    def test_task_execution_async(self) -> None:
        """Test actual async task execution."""
        # This would test real task execution in a worker
        result = fetch_match_history.delay(
            puuid="test_puuid",
            region="na1",
            count=5,
        )

        # Wait for result (with timeout)
        task_result = result.get(timeout=10)

        assert task_result["success"] is True
        assert "match_ids" in task_result
