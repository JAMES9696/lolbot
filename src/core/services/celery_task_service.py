"""Celery-backed async task service implementation.

Implements the IAsyncTaskService port to push analysis tasks and read
task status via Celery. This keeps Discord adapter decoupled from the
task queue implementation.
"""

from __future__ import annotations

from typing import Any

from src.core.ports.task_port import IAsyncTaskService
from src.tasks.celery_app import celery_app


class TaskQueueError(Exception):
    """Raised when task queue operations fail."""

    pass


class CeleryTaskService(IAsyncTaskService):
    """Celery implementation of the async task service port."""

    async def push_analysis_task(self, task_name: str, payload: dict[str, Any]) -> str:
        """Push match analysis task to Celery.

        Args:
            task_name: Fully-qualified Celery task name
            payload: Task kwargs (unpacked as keyword arguments)

        Returns:
            Celery task ID
        """
        try:
            # Pass payload as keyword arguments (unpacked)
            # Both analyze_match_task and analyze_team_task use kwargs signature
            async_result = celery_app.send_task(task_name, kwargs=payload)
            return async_result.id
        except Exception as e:  # pragma: no cover - defensive
            raise TaskQueueError(f"Failed to enqueue task {task_name}: {e}") from e

    async def get_task_status(self, task_id: str) -> str:
        """Get Celery task status by ID."""
        try:
            result = celery_app.AsyncResult(task_id)
            return str(result.status)
        except Exception as e:  # pragma: no cover - defensive
            raise TaskQueueError(f"Failed to query task {task_id}: {e}") from e
