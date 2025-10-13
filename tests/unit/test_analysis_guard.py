import asyncio

import pytest

from src.tasks.analysis_tasks import match_execution_guard, _reset_match_guard_state_for_tests


@pytest.mark.asyncio
async def test_match_guard_serializes_same_match() -> None:
    _reset_match_guard_state_for_tests()
    order: list[str] = []

    async def worker(label: str) -> None:
        async with match_execution_guard("NA1_12345"):
            order.append(f"{label}-enter")
            await asyncio.sleep(0.05)
        order.append(f"{label}-exit")

    await asyncio.gather(worker("first"), worker("second"))

    assert order[:2] == ["first-enter", "first-exit"]
    assert order[2:] == ["second-enter", "second-exit"]


@pytest.mark.asyncio
async def test_match_guard_allows_different_matches_parallel() -> None:
    _reset_match_guard_state_for_tests()
    order: list[str] = []

    async def worker(match_id: str) -> None:
        async with match_execution_guard(match_id):
            order.append(match_id)
            await asyncio.sleep(0)

    await asyncio.gather(worker("NA1_A"), worker("NA1_B"))
    assert set(order) == {"NA1_A", "NA1_B"}
