"""Port interface for async task queue operations.

This port abstracts the task queue implementation (Celery/RQ) from
the application core, following hexagonal architecture principles.
"""

from abc import ABC, abstractmethod
from typing import Any


class IAsyncTaskService(ABC):
    """Port interface for asynchronous task queue service.

    This abstraction allows CLI 1 (Frontend) to push tasks to the queue
    without knowing the concrete implementation (Celery worker details).
    """

    @abstractmethod
    async def push_analysis_task(self, task_name: str, payload: dict[str, Any]) -> str:
        """Push match analysis task to async queue.

        Args:
            task_name: Celery task identifier (e.g., 'tasks.analyze_match')
            payload: Serialized task payload (from Pydantic model)

        Returns:
            Task ID for tracking (Celery task UUID)

        Raises:
            TaskQueueError: If task push fails
        """
        pass

    @abstractmethod
    async def get_task_status(self, task_id: str) -> str:
        """Query task execution status.

        Args:
            task_id: Celery task UUID

        Returns:
            Status string: 'PENDING', 'STARTED', 'SUCCESS', 'FAILURE'
        """
        pass
