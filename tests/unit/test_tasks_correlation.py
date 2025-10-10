import types
from typing import Any

import pytest

from src.contracts.tasks import AnalysisTaskPayload


@pytest.mark.asyncio
async def test_worker_prefers_payload_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: record calls to set_correlation_id
    recorded: list[str] = []

    def _fake_set_correlation_id(cid: str) -> None:  # type: ignore[no-redef]
        recorded.append(cid)

    # Patch set_correlation_id in the analysis_tasks module namespace
    import src.tasks.analysis_tasks as mod

    monkeypatch.setattr(mod, "set_correlation_id", _fake_set_correlation_id, raising=True)

    # Short-circuit network by making fetch return None so the function exits early
    async def _fake_fetch(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(mod, "_fetch_timeline_with_observability", _fake_fetch, raising=True)

    # Minimal self with required attributes accessed before early return
    class _S:
        riot_adapter = object()
        db_adapter = types.SimpleNamespace(connect=lambda: None, disconnect=lambda: None)

    # Use a fixed correlation id
    cid = "discord:12345:67890"
    payload = AnalysisTaskPayload(
        application_id="a",
        interaction_token="t",
        channel_id="c",
        discord_user_id="u",
        puuid="p",
        match_id="NA1_1",
        region="americas",
        match_index=1,
        correlation_id=cid,
    )

    # Act
    await mod._run_analysis_workflow(_S(), payload, 0.0)

    # Assert
    assert recorded and recorded[0] == cid
