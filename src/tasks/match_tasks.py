"""Match data fetching and processing tasks.

Background tasks for asynchronous match data retrieval from Riot API,
including match history, match details, and timeline data.
"""

import asyncio
import logging
from typing import Any

from src.adapters.database import DatabaseAdapter
from src.adapters.riot_api import RiotAPIAdapter
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.tasks.match_tasks.fetch_match_history",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def fetch_match_history(
    self: Any,  # Celery task instance
    puuid: str,
    region: str = "na1",
    count: int = 20,
) -> dict[str, Any]:
    """Fetch match history for a player (background task).

    This task runs asynchronously in a Celery worker, fetching the player's
    recent match IDs from Riot API. It demonstrates the task queue infrastructure.

    Args:
        puuid: Player Universally Unique Identifier
        region: Riot region (default: na1)
        count: Number of matches to fetch (default: 20)

    Returns:
        Dictionary with match_ids list and metadata

    Raises:
        Retry: If API request fails with retryable error
    """
    logger.info(f"[Task {self.request.id}] Fetching match history for {puuid}")

    try:
        # Initialize adapters (in production, use dependency injection)
        riot_api = RiotAPIAdapter()

        # Run async function in event loop
        # Celery workers run sync code, so we need to bridge to async
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            match_ids = loop.run_until_complete(
                riot_api.get_match_history(puuid=puuid, region=region, count=count)
            )

            logger.info(f"[Task {self.request.id}] Successfully fetched {len(match_ids)} match IDs")

            return {
                "success": True,
                "puuid": puuid,
                "region": region,
                "match_ids": match_ids,
                "count": len(match_ids),
                "task_id": self.request.id,
            }

        finally:
            loop.close()

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error fetching match history for {puuid}: {exc}")

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc


@celery_app.task(
    name="src.tasks.match_tasks.fetch_and_store_match",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def fetch_and_store_match(
    self: Any,
    match_id: str,
    region: str = "na1",
) -> dict[str, Any]:
    """Fetch match details and timeline, then store in database.

    This task demonstrates the full workflow of:
    1. Fetching match data from Riot API
    2. Fetching timeline data (expensive operation)
    3. Storing everything in database

    Args:
        match_id: Match ID to fetch
        region: Riot region

    Returns:
        Dictionary with operation result

    Raises:
        Retry: If API request fails with retryable error
    """
    logger.info(f"[Task {self.request.id}] Fetching match data for {match_id}")

    try:
        # Initialize adapters
        riot_api = RiotAPIAdapter()
        database = DatabaseAdapter()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Connect database
            loop.run_until_complete(database.connect())

            # Check if match already exists in cache
            cached_match = loop.run_until_complete(database.get_match_data(match_id))
            if cached_match:
                logger.info(f"[Task {self.request.id}] Match {match_id} already cached")
                return {
                    "success": True,
                    "match_id": match_id,
                    "cached": True,
                    "task_id": self.request.id,
                }

            # Fetch match details
            match_data = loop.run_until_complete(
                riot_api.get_match_details(match_id=match_id, region=region)
            )

            if not match_data:
                logger.warning(f"[Task {self.request.id}] No match data found for {match_id}")
                return {
                    "success": False,
                    "match_id": match_id,
                    "error": "Match not found",
                    "task_id": self.request.id,
                }

            # Fetch timeline data (this is the expensive operation)
            timeline_data = loop.run_until_complete(
                riot_api.get_match_timeline(match_id=match_id, region=region)
            )

            # Store in database
            save_success = loop.run_until_complete(
                database.save_match_data(
                    match_id=match_id,
                    match_data=match_data,
                    timeline_data=timeline_data or {},
                )
            )

            if not save_success:
                logger.error(f"[Task {self.request.id}] Failed to save match {match_id}")
                return {
                    "success": False,
                    "match_id": match_id,
                    "error": "Database save failed",
                    "task_id": self.request.id,
                }

            logger.info(
                f"[Task {self.request.id}] Successfully processed and stored match {match_id}"
            )

            return {
                "success": True,
                "match_id": match_id,
                "cached": False,
                "has_timeline": timeline_data is not None,
                "task_id": self.request.id,
            }

        finally:
            # Cleanup
            loop.run_until_complete(database.disconnect())
            loop.close()

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error processing match {match_id}: {exc}")

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc


@celery_app.task(
    name="src.tasks.match_tasks.batch_fetch_matches",
    bind=True,
)
def batch_fetch_matches(
    self: Any,
    match_ids: list[str],
    region: str = "na1",
) -> dict[str, Any]:
    """Batch fetch multiple matches by creating subtasks.

    This demonstrates task composition - creating child tasks for each match.

    Args:
        match_ids: List of match IDs to fetch
        region: Riot region

    Returns:
        Dictionary with batch operation metadata
    """
    logger.info(f"[Task {self.request.id}] Starting batch fetch for {len(match_ids)} matches")

    # Create subtasks for each match
    from celery import group

    job = group(fetch_and_store_match.s(match_id=match_id, region=region) for match_id in match_ids)

    # Execute all tasks in parallel
    result = job.apply_async()

    logger.info(f"[Task {self.request.id}] Batch job created with {len(match_ids)} subtasks")

    return {
        "success": True,
        "batch_size": len(match_ids),
        "group_id": result.id,
        "task_id": self.request.id,
    }
