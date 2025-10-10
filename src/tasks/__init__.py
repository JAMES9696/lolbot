"""Celery task definitions for background job processing.

This module contains all asynchronous tasks that run in background workers,
including match data fetching, AI analysis, and TTS generation.
"""

from src.tasks.celery_app import celery_app

# Import task modules to ensure registration
from src.tasks import analysis_tasks, match_tasks, team_tasks  # noqa: F401

__all__ = ["celery_app"]
