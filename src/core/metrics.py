"""
Prometheus metrics utilities (process-safe, optional dependency).

KISS: Import `prometheus_client` if available; otherwise no-op stubs keep
runtime stable. Metrics exposure is optional and controlled by code paths.

DRY: Centralize metric definitions and helpers here to avoid scattered
instrumentation across modules.
"""

from __future__ import annotations

from typing import Any

from src.config.settings import get_settings

try:  # Optional dependency
    from prometheus_client import (
        CollectorRegistry,
        CONTENT_TYPE_LATEST,
        Counter,
        generate_latest,
        Gauge,
        Histogram,
    )

    _PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover - keep runtime safe without dependency
    CollectorRegistry = object  # type: ignore
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"  # type: ignore

    class _Noop:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return self

        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass

        def set(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, *args: Any, **kwargs: Any) -> _Noop:
            return self

    Counter = _Noop  # type: ignore
    Gauge = _Noop  # type: ignore
    Histogram = _Noop  # type: ignore
    _PROMETHEUS_AVAILABLE = False

# Global registry
_registry = CollectorRegistry() if _PROMETHEUS_AVAILABLE else None

# ============================================================================
# Counters
# ============================================================================

chimera_analyze_requests_total = Counter(  # type: ignore[call-arg]
    "chimera_analyze_requests_total",
    "Total analysis requests by status and mode",
    labelnames=("status", "mode"),
    registry=_registry,
)

chimera_llm_tokens_total = Counter(  # type: ignore[call-arg]
    "chimera_llm_tokens_total",
    "LLM token usage by type, model, and mode",
    labelnames=("type", "model", "mode"),
    registry=_registry,
)

chimera_llm_cost_usd_total_by_mode = Counter(  # type: ignore[call-arg]
    "chimera_llm_cost_usd_total_by_mode",
    "Accumulated LLM API cost in USD by game mode",
    labelnames=("model", "game_mode"),
    registry=_registry,
)

chimera_json_validation_errors_total_by_mode = Counter(  # type: ignore[call-arg]
    "chimera_json_validation_errors_total_by_mode",
    "JSON validation failures by schema, error type, json mode and game mode",
    labelnames=("schema", "error", "mode", "game_mode"),
    registry=_registry,
)

chimera_external_api_errors_total = Counter(  # type: ignore[call-arg]
    "chimera_external_api_errors_total",
    "External API errors by service and error type",
    labelnames=("service", "error_type"),
    registry=_registry,
)

# ============================================================================
# Gauges (dynamic)
# ============================================================================

chimera_celery_queue_length = Gauge(  # type: ignore[call-arg]
    "chimera_celery_queue_length",
    "Celery queue length by queue name",
    labelnames=("queue",),
    registry=_registry,
)

# ============================================================================
# Histograms
# ============================================================================

chimera_request_duration_seconds = Histogram(  # type: ignore[call-arg]
    "chimera_request_duration_seconds",
    "Request duration in seconds by endpoint and status",
    labelnames=("endpoint", "status"),
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=_registry,
)


# ============================================================================
# Helper Functions
# ============================================================================


def mark_request_outcome(endpoint: str, status: str) -> None:
    """Mark request outcome for observability.

    Args:
        endpoint: Endpoint name (e.g., 'team_analyze', 'analyze_match')
        status: Status ('success' or 'failed')
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        chimera_analyze_requests_total.labels(status=status, mode=endpoint).inc()  # type: ignore
    except Exception:
        pass


def observe_request_latency(endpoint: str, duration_seconds: float) -> None:
    """Observe request latency.

    Args:
        endpoint: Endpoint name
        duration_seconds: Request duration in seconds
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        chimera_request_duration_seconds.labels(endpoint=endpoint, status="success").observe(  # type: ignore
            duration_seconds
        )
    except Exception:
        pass


def mark_llm(status: str, model: str, mode: str = "default") -> None:
    """Mark LLM request outcome.

    Args:
        status: 'success' or 'error'
        model: Model name (e.g., 'gemini-pro')
        mode: Game mode (e.g., 'sr', 'aram', 'arena', 'default')
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        chimera_llm_tokens_total.labels(type=status, model=model, mode=mode).inc()  # type: ignore
    except Exception:
        pass


def mark_riot_429() -> None:
    """Mark Riot API rate limit hit."""
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        chimera_external_api_errors_total.labels(service="riot", error_type="429").inc()  # type: ignore
    except Exception:
        pass


def mark_json_validation_error(schema: str, error_type: str) -> None:
    """Mark JSON validation error.

    Args:
        schema: Schema name (e.g., 'v2_team_analysis')
        error_type: Error type (e.g., 'validation_error', 'json_parse_error')
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        chimera_json_validation_errors_total_by_mode.labels(  # type: ignore
            schema=schema, error=error_type, mode="unknown", game_mode="unknown"
        ).inc()
    except Exception:
        pass


def mark_json_validation_error_by_mode(
    schema: str, error_type: str, game_mode: str
) -> None:
    """Mark JSON validation error with game mode.

    Args:
        schema: Schema name
        error_type: Error type
        game_mode: Game mode label
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        chimera_json_validation_errors_total_by_mode.labels(  # type: ignore
            schema=schema, error=error_type, mode=game_mode, game_mode=game_mode
        ).inc()
    except Exception:
        pass


def observe_analyze_e2e(total_ms: float | None, stages_ms: dict[str, float | None]) -> None:
    """Record end-to-end and per-stage durations.

    KISS: accept milliseconds from existing code, convert internally.

    Args:
        total_ms: Total duration in milliseconds
        stages_ms: Dict of stage name -> duration in milliseconds
    """
    # Currently just a placeholder - can extend with histograms per stage if needed
    pass


async def update_dynamic_gauges() -> None:
    """Update dynamic gauges (e.g., queue lengths).

    KISS: Pull metrics on demand to avoid background schedulers.
    """
    if not _PROMETHEUS_AVAILABLE:
        return

    try:
        from src.adapters.redis_adapter import RedisAdapter

        settings = get_settings()
        redis = RedisAdapter(redis_url=settings.redis_url)
        await redis.connect()

        # Get queue lengths
        try:
            queue_length = await redis.client.llen("celery")  # type: ignore
            chimera_celery_queue_length.labels(queue="celery").set(queue_length)  # type: ignore
        except Exception:
            pass

        await redis.disconnect()
    except Exception:
        pass


def render_latest() -> tuple[bytes, str]:
    """Render latest metrics for Prometheus scraping.

    Returns:
        Tuple of (payload bytes, content_type string)
    """
    if not _PROMETHEUS_AVAILABLE or _registry is None:
        return (b"# Prometheus metrics not available\n", "text/plain; charset=utf-8")

    try:
        payload = generate_latest(_registry)  # type: ignore
        return (payload, CONTENT_TYPE_LATEST)  # type: ignore
    except Exception:
        return (b"# Error generating metrics\n", "text/plain; charset=utf-8")
