"""Tests for analysis task event loop handling and payload compatibility."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock


def _fake_loop() -> MagicMock:
    loop = MagicMock()
    loop.is_closed.return_value = False

    async def _shutdown_asyncgens() -> None:
        return None

    loop.shutdown_asyncgens = MagicMock(side_effect=_shutdown_asyncgens)
    loop.close = MagicMock()

    def _run_until_complete(coro: Any) -> Any:
        return asyncio.run(coro)

    loop.run_until_complete.side_effect = _run_until_complete
    return loop


def test_analyze_match_task_uses_dedicated_event_loop(monkeypatch) -> None:
    """Each invocation should spin up a private event loop and tear it down cleanly."""
    from src.tasks import analysis_tasks

    fake_loop = _fake_loop()
    set_calls: list[Any] = []

    def fake_set_event_loop(loop: Any) -> None:
        set_calls.append(loop)

    monkeypatch.setattr(
        analysis_tasks.asyncio, "get_event_loop", MagicMock(side_effect=RuntimeError("no loop"))
    )
    monkeypatch.setattr(analysis_tasks.asyncio, "new_event_loop", MagicMock(return_value=fake_loop))
    monkeypatch.setattr(analysis_tasks.asyncio, "set_event_loop", fake_set_event_loop)

    async def fake_run_workflow(_self: MagicMock, _payload: Any, _start: float) -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr(analysis_tasks, "_run_analysis_workflow", fake_run_workflow)

    result = analysis_tasks.analyze_match_task.run(
        application_id="app",
        interaction_token="token",
        channel_id="channel",
        discord_user_id="user",
        puuid="puuid",
        match_id="MATCH_123",
        region="na1",
        match_index=2,
        correlation_id="cid",
    )

    assert result == {"status": "ok"}
    assert len(fake_loop.run_until_complete.call_args_list) == 2
    first_call_arg = fake_loop.run_until_complete.call_args_list[0].args[0]
    second_call_arg = fake_loop.run_until_complete.call_args_list[1].args[0]
    assert asyncio.iscoroutine(first_call_arg)
    assert asyncio.iscoroutine(second_call_arg)
    fake_loop.shutdown_asyncgens.assert_called_once()
    fake_loop.close.assert_called_once()
    assert set_calls == [fake_loop, None]


def test_analyze_match_task_accepts_legacy_payload_dict(monkeypatch) -> None:
    """Legacy Celery callers passing a single dict arg should still be supported."""
    from src.tasks import analysis_tasks
    from src.contracts.tasks import AnalysisTaskPayload

    fake_loop = _fake_loop()
    monkeypatch.setattr(
        analysis_tasks.asyncio, "get_event_loop", MagicMock(side_effect=RuntimeError("no loop"))
    )
    monkeypatch.setattr(analysis_tasks.asyncio, "new_event_loop", MagicMock(return_value=fake_loop))
    monkeypatch.setattr(analysis_tasks.asyncio, "set_event_loop", lambda _loop: None)

    captured_payload: list[AnalysisTaskPayload] = []

    async def fake_run_workflow(
        _self: MagicMock, payload: AnalysisTaskPayload, _start: float
    ) -> dict[str, str]:
        captured_payload.append(payload)
        return {"status": "ok"}

    monkeypatch.setattr(analysis_tasks, "_run_analysis_workflow", fake_run_workflow)

    raw_payload = {
        "application_id": "app",
        "interaction_token": "token",
        "channel_id": "channel",
        "discord_user_id": "user",
        "puuid": "puuid",
        "match_id": "MATCH_456",
        "region": "na1",
        "match_index": 3,
        "correlation_id": "legacy",
    }

    result = analysis_tasks.analyze_match_task.run(raw_payload)

    assert result == {"status": "ok"}
    assert captured_payload, "Expected payload to be passed into workflow"
    payload = captured_payload[0]
    assert isinstance(payload, AnalysisTaskPayload)
    assert payload.match_id == raw_payload["match_id"]
    assert payload.application_id == raw_payload["application_id"]
