"""Celery application configuration.

Configures Celery with Redis as broker and result backend,
sets up task autodiscovery, and defines worker configuration.
"""

import logging

from celery import Celery
from celery.signals import after_task_publish, task_prerun, task_postrun, task_failure

from src.config.settings import settings
from src.core.observability import configure_stdlib_json_logging
import contextlib

logger = logging.getLogger(__name__)

# Configure structured logging for workers (stdout only; Celery may set logfile)
with contextlib.suppress(Exception):
    configure_stdlib_json_logging(level=settings.app_log_level)

# Initialize Celery app
celery_app = Celery(
    "project_chimera",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task execution settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task result settings
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,  # Store additional task metadata
    # Worker settings
    worker_prefetch_multiplier=4,  # Number of tasks to prefetch
    worker_max_tasks_per_child=1000,  # Restart worker after N tasks
    # Task routing
    task_routes={
        "src.tasks.match_tasks.*": {"queue": "matches"},
        # Route analysis/AI heavy tasks to dedicated queue for isolation
        "src.tasks.analysis_tasks.*": {"queue": "ai"},
        "src.tasks.team_tasks.*": {"queue": "ai"},
    },
    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,
    # Rate limiting
    task_default_rate_limit="100/m",  # 100 tasks per minute by default
    # Retry settings
    task_acks_late=True,  # Acknowledge task after execution
    task_reject_on_worker_lost=True,  # Reject task if worker dies
)

# Autodiscover tasks in the tasks package
celery_app.autodiscover_tasks(["src.tasks"], force=True)

logger.info("Celery application configured successfully")

# ----------------------------------------------------------------------------
# Lightweight E2E Trace Hooks (Publish → Receive → Run → Finish/Fail)
# ----------------------------------------------------------------------------
# 目的：给“任务是否真正被 Worker 收到并开始执行”一个最小可视化链路。
# - 不改变路由与业务逻辑；仅输出结构化日志，便于用 rg/fd 快速串联排查。
# - 关键字段：task_id, task_name, routing_key(queue), correlation_id（从 kwargs 提取）。
# - 成本：极低（INFO 级日志），默认开启，后续如需可通过日志级别关闭。


def _extract_kwargs_from_body(body: object) -> dict:
    """Best-effort parse Celery publish body to get kwargs for correlation_id.

    Celery 在 JSON 序列化下，after_task_publish(body=...) 可能是：
      - dict 结构，含有 'kwargs' / 'args'；
      - 元组/列表形式 (args, kwargs, embed)；
    这里做最小健壮解析，失败则返回 {}。
    """
    try:
        if isinstance(body, dict):
            return dict(body.get("kwargs") or {})
        if isinstance(body, list | tuple) and len(body) >= 2 and isinstance(body[1], dict):
            return dict(body[1])
    except Exception:
        pass
    return {}


@after_task_publish.connect
def _on_task_published(
    sender=None, body=None, exchange=None, routing_key=None, headers=None, **kwargs
):
    try:
        task_id = (headers or {}).get("id")
        kws = _extract_kwargs_from_body(body)
        correlation_id = kws.get("correlation_id")
        logger.info(
            "celery_task_published",
            extra={
                "task_id": task_id,
                "task_name": sender,
                "routing_key": routing_key,
                "exchange": exchange,
                "correlation_id": correlation_id,
            },
        )
    except Exception:
        # 避免钩子影响任务发布
        pass


@task_prerun.connect
def _on_task_prerun(task=None, task_id=None, args=None, kwargs=None, **_):
    try:
        correlation_id = (kwargs or {}).get("correlation_id")
        logger.info(
            "celery_task_started",
            extra={
                "task_id": task_id,
                "task_name": getattr(task, "name", None),
                "correlation_id": correlation_id,
            },
        )
    except Exception:
        pass


@task_postrun.connect
def _on_task_postrun(task=None, task_id=None, retval=None, state=None, **_):
    with contextlib.suppress(Exception):
        logger.info(
            "celery_task_finished",
            extra={
                "task_id": task_id,
                "task_name": getattr(task, "name", None),
                "state": state,
            },
        )


@task_failure.connect
def _on_task_failure(
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    sender=None,
    **_,
):
    with contextlib.suppress(Exception):
        logger.error(
            "celery_task_failed",
            extra={
                "task_id": task_id,
                "task_name": getattr(sender, "name", None),
                "error": str(exception) if exception else None,
            },
        )
