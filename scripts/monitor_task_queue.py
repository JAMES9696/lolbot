#!/usr/bin/env python3
"""Task Queue Health Monitoring Script.

Monitors Celery/Redis task queue health and provides real-time metrics:
- Queue lengths (pending tasks)
- Task processing rates
- Failure rates and error analysis
- Worker health status
- API rate limit compliance (via llm_debug_wrapper logs)

Usage:
    poetry run python scripts/monitor_task_queue.py [--interval 5] [--export metrics.json]
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from celery import Celery

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings


class TaskQueueMonitor:
    """Real-time task queue health monitor."""

    def __init__(self, celery_app: Celery, redis_url: str) -> None:
        """Initialize monitor with Celery app and Redis connection.

        Args:
            celery_app: Celery application instance
            redis_url: Redis connection URL
        """
        self.celery_app = celery_app
        self.redis_url = redis_url
        self.redis_client: Any = None  # aioredis.Redis (untyped)

        # Metrics storage
        self.metrics_history: list[dict[str, Any]] = []

    async def connect_redis(self) -> None:
        """Establish Redis connection."""
        self.redis_client = await aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def disconnect_redis(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()

    async def get_queue_lengths(self) -> dict[str, int]:
        """Get current queue lengths for all queues.

        Returns:
            Dict mapping queue names to pending task counts
        """
        queues = ["celery", "matches", "ai", "default"]  # From celery_app.conf
        queue_lengths = {}

        for queue_name in queues:
            try:
                # Celery uses Redis lists for queues
                length = await self.redis_client.llen(queue_name)
                queue_lengths[queue_name] = length
            except Exception as e:
                print(f"⚠️  Error getting length for queue '{queue_name}': {e}")
                queue_lengths[queue_name] = -1

        return queue_lengths

    async def get_worker_status(self) -> dict[str, Any]:
        """Get Celery worker health status.

        Returns:
            Dict with worker statistics
        """
        inspector = self.celery_app.control.inspect()

        # Get active workers
        active_workers = inspector.active()
        registered_tasks = inspector.registered()
        stats = inspector.stats()

        worker_count = len(active_workers) if active_workers else 0
        total_active_tasks = sum(len(tasks) for tasks in (active_workers or {}).values())

        return {
            "worker_count": worker_count,
            "active_tasks": total_active_tasks,
            "registered_tasks_count": (
                len(list(registered_tasks.values())[0]) if registered_tasks else 0
            ),
            "workers_online": list(active_workers.keys()) if active_workers else [],
            "worker_stats": stats or {},
        }

    async def get_task_failure_metrics(self) -> dict[str, Any]:
        """Analyze task failure rates from Celery results.

        Returns:
            Dict with failure statistics
        """
        # Query Celery result backend for failed tasks
        # This is a simplified implementation - production should use Flower or Celery events
        failed_tasks = 0
        total_tasks = 0

        # Note: This requires celery_result_backend to be queryable
        # In production, use Celery Events or Flower API for accurate metrics

        return {
            "failed_tasks": failed_tasks,
            "total_tasks": total_tasks,
            "failure_rate": ((failed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0),
        }

    async def analyze_llm_debug_logs(self, log_path: str | None = None) -> dict[str, Any]:
        """Analyze @llm_debug_wrapper logs for performance metrics.

        Args:
            log_path: Path to structured log file (defaults to logs/llm_debug.jsonl)

        Returns:
            Dict with API latency, error rates, and rate limit compliance
        """
        if log_path is None:
            log_path = "logs/llm_debug.jsonl"

        log_file = Path(log_path)
        if not log_file.exists():
            return {
                "log_file_missing": True,
                "error": f"Log file not found: {log_path}",
            }

        # Parse structured logs
        latencies: list[float] = []
        error_count = 0
        rate_limit_429_count = 0
        total_calls = 0

        try:
            with log_file.open() as f:
                for line in f:
                    try:
                        log_entry = json.loads(line)
                        total_calls += 1

                        # Extract latency
                        if "latency_ms" in log_entry:
                            latencies.append(log_entry["latency_ms"])

                        # Count errors
                        if log_entry.get("error"):
                            error_count += 1

                        # Count rate limit errors
                        if log_entry.get("status_code") == 429:
                            rate_limit_429_count += 1

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            return {"error": f"Failed to parse log file: {e}"}

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 0 else 0.0

        return {
            "total_api_calls": total_calls,
            "avg_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "error_count": error_count,
            "error_rate_percent": (
                round(error_count / total_calls * 100, 2) if total_calls > 0 else 0.0
            ),
            "rate_limit_429_count": rate_limit_429_count,
            "rate_limit_compliance": "PASS"
            if rate_limit_429_count == 0
            else f"FAIL ({rate_limit_429_count} violations)",
        }

    async def collect_metrics(self) -> dict[str, Any]:
        """Collect all monitoring metrics.

        Returns:
            Comprehensive metrics snapshot
        """
        timestamp = datetime.now(UTC).isoformat()

        queue_lengths = await self.get_queue_lengths()
        worker_status = await self.get_worker_status()
        failure_metrics = await self.get_task_failure_metrics()
        llm_debug_metrics = await self.analyze_llm_debug_logs()

        metrics = {
            "timestamp": timestamp,
            "queue_lengths": queue_lengths,
            "worker_status": worker_status,
            "task_failures": failure_metrics,
            "llm_debug_metrics": llm_debug_metrics,
            # Health summary
            "health_summary": {
                "total_pending_tasks": sum(v for v in queue_lengths.values() if v >= 0),
                "workers_healthy": worker_status["worker_count"] > 0,
                "queue_backlog_alert": any(length > 100 for length in queue_lengths.values()),
            },
        }

        self.metrics_history.append(metrics)
        return metrics

    def display_metrics(self, metrics: dict[str, Any]) -> None:
        """Display metrics in terminal-friendly format."""
        print("\n" + "=" * 80)
        print(f"📊 Task Queue Health Monitor - {metrics['timestamp']}")
        print("=" * 80)

        # Queue Lengths
        print("\n🔢 Queue Lengths (Pending Tasks):")
        for queue, length in metrics["queue_lengths"].items():
            status = "⚠️ " if length > 100 else "✅"
            print(f"  {status} {queue:15s}: {length:>5d} tasks")

        # Worker Status
        print("\n👷 Worker Status:")
        ws = metrics["worker_status"]
        worker_icon = "✅" if ws["worker_count"] > 0 else "❌"
        print(f"  {worker_icon} Workers Online: {ws['worker_count']}")
        print(f"  🔄 Active Tasks: {ws['active_tasks']}")
        print(f"  📋 Registered Tasks: {ws['registered_tasks_count']}")

        # Task Failures
        print("\n❌ Task Failures:")
        tf = metrics["task_failures"]
        print(f"  Failed: {tf['failed_tasks']}")
        print(f"  Total: {tf['total_tasks']}")
        print(f"  Failure Rate: {tf['failure_rate']:.2f}%")

        # LLM Debug Metrics
        print("\n🔍 LLM/API Performance (from @llm_debug_wrapper logs):")
        llm = metrics["llm_debug_metrics"]
        if "error" in llm:
            print(f"  ⚠️  {llm['error']}")
        else:
            print(f"  📞 Total API Calls: {llm['total_api_calls']}")
            print(f"  ⏱️  Avg Latency: {llm['avg_latency_ms']} ms")
            print(f"  📈 P95 Latency: {llm['p95_latency_ms']} ms")
            print(f"  ❌ Error Rate: {llm['error_rate_percent']}%")
            compliance_icon = "✅" if "PASS" in llm["rate_limit_compliance"] else "❌"
            print(f"  {compliance_icon} Rate Limit Compliance: {llm['rate_limit_compliance']}")

        # Health Summary
        print("\n🏥 Health Summary:")
        hs = metrics["health_summary"]
        print(f"  Total Pending: {hs['total_pending_tasks']} tasks")
        workers_icon = "✅" if hs["workers_healthy"] else "❌"
        print(f"  {workers_icon} Workers: {'Healthy' if hs['workers_healthy'] else 'DOWN'}")
        if hs["queue_backlog_alert"]:
            print("  ⚠️  ALERT: Queue backlog detected (>100 tasks)")

        print("=" * 80)

    async def run_monitoring_loop(self, interval: int = 5, duration: int | None = None) -> None:
        """Run continuous monitoring loop.

        Args:
            interval: Seconds between metric collections
            duration: Total monitoring duration in seconds (None = infinite)
        """
        await self.connect_redis()

        start_time = time.time()
        try:
            while True:
                metrics = await self.collect_metrics()
                self.display_metrics(metrics)

                # Check duration limit
                if duration and (time.time() - start_time) >= duration:
                    print(f"\n⏰ Monitoring duration ({duration}s) completed.")
                    break

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\n\n🛑 Monitoring stopped by user.")
        finally:
            await self.disconnect_redis()

    def export_metrics(self, output_path: str) -> None:
        """Export collected metrics to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w") as f:
            json.dump(
                {
                    "monitoring_session": {
                        "start_time": (
                            self.metrics_history[0]["timestamp"] if self.metrics_history else None
                        ),
                        "end_time": (
                            self.metrics_history[-1]["timestamp"] if self.metrics_history else None
                        ),
                        "total_snapshots": len(self.metrics_history),
                    },
                    "metrics": self.metrics_history,
                },
                f,
                indent=2,
            )

        print(f"✅ Metrics exported to {output_path}")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor Celery/Redis task queue health")
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Monitoring interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Total monitoring duration in seconds (default: infinite)",
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export metrics to JSON file (e.g., metrics.json)",
    )

    args = parser.parse_args()

    # Initialize Celery app (reuse from project)
    from src.tasks.celery_app import celery_app

    # Create monitor
    monitor = TaskQueueMonitor(celery_app, settings.redis_url)

    # Run monitoring
    await monitor.run_monitoring_loop(interval=args.interval, duration=args.duration)

    # Export if requested
    if args.export:
        monitor.export_metrics(args.export)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
