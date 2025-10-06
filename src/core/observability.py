"""Observability framework for Project Chimera.

This module provides the core debugging and monitoring capabilities
through the llm_debug_wrapper decorator and structured logging.
"""

import asyncio
import functools
import json
import re
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

import structlog
from pydantic import BaseModel, ConfigDict, Field
from structlog.contextvars import bind_contextvars, unbind_contextvars

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
        ),
        structlog.processors.dict_tracebacks,
        structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),  # type: ignore[list-item]
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Get logger instance
logger = structlog.get_logger()

# Type variable for generic decorator
F = TypeVar("F", bound=Callable[..., Any])

# Sensitive data redaction pattern
_SENSITIVE_KEY_RE = re.compile(r"(token|key|secret|password|pass|authorization|auth|client_secret)", re.IGNORECASE)


def _mask_scalar(value: Any) -> Any:
    if value is None:
        return None
    s = str(value)
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-3:]}"


def _redact_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: (_mask_scalar(v) if _SENSITIVE_KEY_RE.search(str(k)) else _redact_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(i) for i in obj]
    return obj


def _safe_serialize_kv(key: str, value: Any, max_length: int) -> Any:
    ser = _serialize_value(value, max_length)
    if _SENSITIVE_KEY_RE.search(str(key)):
        return _redact_obj(ser)
    return ser


class FunctionTrace(BaseModel):
    """Model for function execution trace data."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    function_name: str = Field(description="Fully qualified function name")
    module: str = Field(description="Module where function is defined")
    execution_id: str = Field(description="Unique execution ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float | None = Field(default=None, description="Execution duration in milliseconds")

    # Input/Output
    args: list[Any] = Field(default_factory=list, description="Positional arguments")
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Keyword arguments")
    result: Any | None = Field(default=None, description="Function return value")

    # Error handling
    is_success: bool = Field(default=True, description="Whether execution succeeded")
    error_type: str | None = Field(default=None, description="Exception class name if failed")
    error_message: str | None = Field(default=None, description="Exception message if failed")
    error_traceback: str | None = Field(default=None, description="Full traceback if failed")

    # Metadata
    is_async: bool = Field(default=False, description="Whether function is async")
    correlation_id: str | None = Field(default=None, description="Correlation ID for tracing")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


def _serialize_value(value: Any, max_length: int = 1000) -> Any:
    """Safely serialize a value for logging.

    Args:
        value: Value to serialize
        max_length: Maximum string length for truncation

    Returns:
        Serializable representation of the value
    """
    try:
        # Handle Pydantic models
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json", exclude_unset=True)

        # Handle other complex objects
        json_str = json.dumps(value, default=str)
        if len(json_str) > max_length:
            return json_str[:max_length] + "..."
        return json.loads(json_str)  # Parse back to keep consistent types

    except (TypeError, ValueError):
        # Fallback to string representation
        str_repr = str(value)
        if len(str_repr) > max_length:
            return str_repr[:max_length] + "..."
        return str_repr


def llm_debug_wrapper(
    *,
    capture_result: bool = True,
    capture_args: bool = True,
    max_arg_length: int = 1000,
    log_level: str = "INFO",
    add_metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """Decorator for comprehensive function tracing and debugging.

    This decorator provides:
    - Input parameter logging
    - Return value capture
    - Execution time measurement
    - Exception capture with full traceback
    - Structured JSON logging output
    - Support for both sync and async functions

    Args:
        capture_result: Whether to capture and log the return value
        capture_args: Whether to capture and log input arguments
        max_arg_length: Maximum length for serialized arguments
        log_level: Log level for successful executions
        add_metadata: Additional metadata to include in logs

    Returns:
        Decorated function with observability features

    Example:
        >>> @llm_debug_wrapper(capture_result=True)
        ... async def fetch_match_data(match_id: str) -> dict:
        ...     return {"match_id": match_id, "data": "..."}
    """

    def decorator(func: F) -> F:
        # Determine if function is async
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Async version of the wrapper."""
            # Generate execution ID
            execution_id = f"{func.__module__}.{func.__name__}_{int(time.time() * 1000000)}"

            # Prepare trace object
            trace = FunctionTrace(
                function_name=f"{func.__module__}.{func.__name__}",
                module=func.__module__,
                execution_id=execution_id,
                is_async=True,
                metadata=add_metadata or {},
            )

            # Capture arguments if enabled
            if capture_args:
                trace.args = [_serialize_value(arg, max_arg_length) for arg in args]
                trace.kwargs = {k: _safe_serialize_kv(k, v, max_arg_length) for k, v in kwargs.items()}

            # Bind context variables for correlation
            bind_contextvars(execution_id=execution_id)

            # Log function entry
            await logger.alog(
                log_level.lower(),
                f"Executing async function: {trace.function_name}",
                execution_id=execution_id,
                args=trace.args if capture_args else None,
                kwargs=trace.kwargs if capture_args else None,
            )

            start_time = time.perf_counter()

            try:
                # Execute the actual function
                result = await func(*args, **kwargs)

                # Calculate duration
                trace.duration_ms = (time.perf_counter() - start_time) * 1000
                trace.is_success = True

                # Capture result if enabled
                if capture_result:
                    trace.result = _redact_obj(_serialize_value(result, max_arg_length))

                # Log success
                await logger.alog(
                    log_level.lower(),
                    f"Successfully executed: {trace.function_name}",
                    execution_id=execution_id,
                    duration_ms=trace.duration_ms,
                    result=trace.result if capture_result else None,
                )

            except Exception as e:
                # Calculate duration even on failure
                trace.duration_ms = (time.perf_counter() - start_time) * 1000
                trace.is_success = False
                trace.error_type = type(e).__name__
                trace.error_message = str(e)
                trace.error_traceback = traceback.format_exc()

                # Log error with full context
                await logger.aerror(
                    "Error in function",
                    function_name=trace.function_name,
                    execution_id=execution_id,
                    duration_ms=trace.duration_ms,
                    error_type=trace.error_type,
                    error_message=trace.error_message,
                    traceback=trace.error_traceback,
                    args=trace.args if capture_args else None,
                    kwargs=trace.kwargs if capture_args else None,
                )

                # Re-raise the exception
                raise

            finally:
                # Clear context variables
                unbind_contextvars("execution_id")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Sync version of the wrapper."""
            # Generate execution ID
            execution_id = f"{func.__module__}.{func.__name__}_{int(time.time() * 1000000)}"

            # Prepare trace object
            trace = FunctionTrace(
                function_name=f"{func.__module__}.{func.__name__}",
                module=func.__module__,
                execution_id=execution_id,
                is_async=False,
                metadata=add_metadata or {},
            )

            # Capture arguments if enabled
            if capture_args:
                trace.args = [_serialize_value(arg, max_arg_length) for arg in args]
                trace.kwargs = {k: _safe_serialize_kv(k, v, max_arg_length) for k, v in kwargs.items()}

            # Bind context variables for correlation
            bind_contextvars(execution_id=execution_id)

            # Log function entry
            logger.log(
                log_level.lower(),
                f"Executing function: {trace.function_name}",
                execution_id=execution_id,
                args=trace.args if capture_args else None,
                kwargs=trace.kwargs if capture_args else None,
            )

            start_time = time.perf_counter()

            try:
                # Execute the actual function
                result = func(*args, **kwargs)

                # Calculate duration
                trace.duration_ms = (time.perf_counter() - start_time) * 1000
                trace.is_success = True

                # Capture result if enabled
                if capture_result:
                    trace.result = _redact_obj(_serialize_value(result, max_arg_length))

                # Log success
                logger.log(
                    log_level.lower(),
                    f"Successfully executed: {trace.function_name}",
                    execution_id=execution_id,
                    duration_ms=trace.duration_ms,
                    result=trace.result if capture_result else None,
                )

                return result

            except Exception as e:
                # Calculate duration even on failure
                trace.duration_ms = (time.perf_counter() - start_time) * 1000
                trace.is_success = False
                trace.error_type = type(e).__name__
                trace.error_message = str(e)
                trace.error_traceback = traceback.format_exc()

                # Log error with full context
                logger.error(
                    f"Error in function: {trace.function_name}",
                    execution_id=execution_id,
                    duration_ms=trace.duration_ms,
                    error_type=trace.error_type,
                    error_message=trace.error_message,
                    traceback=trace.error_traceback,
                    args=trace.args if capture_args else None,
                    kwargs=trace.kwargs if capture_args else None,
                )

                # Re-raise the exception
                raise

            finally:
                # Clear context variables
                unbind_contextvars("execution_id")

        # Return appropriate wrapper based on function type
        if is_async:
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    return decorator


# Convenience decorators with common configurations
def trace_critical(func: F) -> F:
    """Decorator for critical path functions with full tracing."""
    return llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
    )(func)


def trace_performance(func: F) -> F:
    """Decorator focused on performance monitoring."""
    return llm_debug_wrapper(
        capture_result=False,
        capture_args=False,
        log_level="DEBUG",
    )(func)


def trace_adapter(func: F) -> F:
    """Decorator specifically for adapter layer functions."""
    return llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"layer": "adapter"},
    )(func)
