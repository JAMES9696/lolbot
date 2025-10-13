"""Celery-backed async task service implementation.

Implements the IAsyncTaskService port to push analysis tasks and read
task status via Celery. This keeps Discord adapter decoupled from the
task queue implementation.
"""

from __future__ import annotations

from typing import Any

from src.core.ports.task_port import IAsyncTaskService
from src.tasks.celery_app import celery_app
from datetime import UTC


class TaskQueueError(Exception):
    """Raised when task queue operations fail."""

    pass


class CeleryTaskService(IAsyncTaskService):
    """Celery implementation of the async task service port."""

    def __init__(self) -> None:
        self._app = celery_app

    async def push_analysis_task(self, task_name: str, payload: dict[str, Any]) -> str:
        """Push match analysis task to Celery.

        Args:
            task_name: Fully-qualified Celery task name
            payload: Task kwargs (unpacked as keyword arguments)

        Returns:
            Celery task ID
        """
        try:
            self._ensure_workers_available()
            # Pass payload as keyword arguments (unpacked)
            # Both analyze_match_task and analyze_team_task use kwargs signature
            async_result = self._app.send_task(task_name, kwargs=payload)
            try:
                # 结构化埋点：确认已进入 Broker（与 after_task_publish 联动）
                # 这里不去强推 queue，保持由 task_routes 决定；仅记录可观测信息。
                from datetime import datetime

                ts = datetime.now(UTC).isoformat()
                # 使用标准 logging（由全局 JSON 配置接管）
                import logging

                logging.getLogger(__name__).info(
                    "celery_task_enqueued",
                    extra={
                        "task_id": async_result.id,
                        "task_name": task_name,
                        "correlation_id": payload.get("correlation_id"),
                        "timestamp": ts,
                    },
                )
            except Exception:
                # 埋点失败不影响主流程
                pass
            return async_result.id
        except Exception as e:  # pragma: no cover - defensive
            raise TaskQueueError(f"Failed to enqueue task {task_name}: {e}") from e

    async def get_task_status(self, task_id: str) -> str:
        """Get Celery task status by ID."""
        try:
            result = self._app.AsyncResult(task_id)
            return str(result.status)
        except Exception as e:  # pragma: no cover - defensive
            raise TaskQueueError(f"Failed to query task {task_id}: {e}") from e

    def _ensure_workers_available(self) -> None:
        """Best-effort check to ensure at least one worker is online before enqueueing."""
        try:
            inspector = self._app.control.inspect(timeout=6.0)
        except Exception as exc:  # pragma: no cover - defensive
            raise TaskQueueError(f"Failed to reach Celery control API: {exc}") from exc

        if not inspector:
            raise TaskQueueError("Celery inspector returned no data (workers unreachable)")

        try:
            stats = inspector.stats() or {}
        except Exception:  # pragma: no cover - defensive
            stats = {}

        if not stats:
            raise TaskQueueError("No active Celery workers reporting stats")
