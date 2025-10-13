"""Unit tests for CeleryTaskService."""

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_push_analysis_task_uses_kwargs(monkeypatch) -> None:
    """Verify push_analysis_task forwards payload as kwargs."""
    from src.core.services.celery_task_service import CeleryTaskService
    from src.tasks import celery_app

    async_result = MagicMock()
    async_result.id = "task-id"

    send_task_mock = MagicMock(return_value=async_result)
    monkeypatch.setattr(celery_app, "send_task", send_task_mock)
    inspect_mock = MagicMock()
    inspect_mock.stats.return_value = {"worker@localhost": {"pid": 12345}}
    monkeypatch.setattr(celery_app.control, "inspect", MagicMock(return_value=inspect_mock))

    service = CeleryTaskService()
    payload = {
        "application_id": "app",
        "interaction_token": "token",
        "channel_id": "channel",
    }

    task_id = await service.push_analysis_task(
        "src.tasks.analysis_tasks.analyze_match_task", payload
    )

    assert task_id == "task-id"
    send_task_mock.assert_called_once_with(
        "src.tasks.analysis_tasks.analyze_match_task", kwargs=payload
    )


@pytest.mark.asyncio
async def test_push_analysis_task_errors_when_no_workers(monkeypatch) -> None:
    """当无活跃Celery worker时，应抛出 TaskQueueError 并阻止排队。"""
    from src.core.services.celery_task_service import CeleryTaskService, TaskQueueError
    from src.tasks import celery_app

    send_task_mock = MagicMock()
    monkeypatch.setattr(celery_app, "send_task", send_task_mock)
    monkeypatch.setattr(celery_app.control, "inspect", MagicMock(return_value=None))

    service = CeleryTaskService()

    with pytest.raises(TaskQueueError):
        await service.push_analysis_task(
            "src.tasks.analysis_tasks.analyze_match_task",
            {"application_id": "app", "interaction_token": "token"},
        )

    send_task_mock.assert_not_called()
