from typing import Any

import structlog
import pytest

from src.core.observability import llm_debug_wrapper, set_correlation_id, clear_correlation_id


@pytest.mark.asyncio
async def test_llm_debug_wrapper_includes_correlation_id() -> None:
    """Ensure correlation_id bound via contextvars appears in structured logs.

    This validates that our logging pipeline merges contextvars (e.g., correlation_id)
    into the event dict, so we can reconstruct end-to-end traces by ID.
    """
    events: list[dict[str, Any]] = []

    # Configure a temporary processor to capture event dicts
    # Note: capture_logs only captures structlog logs
    processor = structlog.processors.JSONRenderer()

    # Use structlog's testing helper to capture logs
    from structlog.testing import capture_logs

    # Bind correlation id to the context
    cid = "test-cid-1234"
    set_correlation_id(cid)

    @llm_debug_wrapper(capture_result=False, capture_args=False, log_level="INFO")
    async def _foo() -> str:
        return "ok"

    try:
        with capture_logs() as cap:
            await _foo()
            # Also emit a manual log to ensure context is merged
            logger = structlog.get_logger()
            logger.info("manual_log")
            events.extend(cap)
    finally:
        clear_correlation_id()

    # At least one of the structured events must carry the correlation_id
    assert any(
        e.get("correlation_id") == cid for e in events
    ), f"Expected correlation_id '{cid}' in structured logs, got: {events}"
