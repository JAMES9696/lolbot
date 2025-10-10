"""Celery application configuration.

Configures Celery with Redis as broker and result backend,
sets up task autodiscovery, and defines worker configuration.
"""

import logging

from celery import Celery

from src.config.settings import settings
from src.core.observability import configure_stdlib_json_logging

logger = logging.getLogger(__name__)

# Configure structured logging for workers (stdout only; Celery may set logfile)
try:
    configure_stdlib_json_logging(level=settings.app_log_level)
except Exception:
    pass

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
