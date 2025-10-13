#!/usr/bin/env python3
"""
Minimal Celery routing/worker-queue trace (no task execution).

Purpose (中文/English):
- 快速判断“任务会被路由到哪个队列、当前是否有 worker 订阅该队列”。
- Quickly verify: route(queue) for a task name, and whether any worker is
  subscribed to that queue at runtime.

Usage:
  poetry run python scripts/trace_queue_routing.py \
    --task src.tasks.analysis_tasks.analyze_match_task

Notes:
- 不发送/执行任务（无副作用）。
- 需要 Celery broker 可达且至少 1 个 worker 在线（用于读取 active_queues）。
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from src.tasks.celery_app import celery_app


def resolve_queue_for_task(task_name: str) -> str | None:
    """Return target queue for task according to Celery routes, or None.

    Celery supports callable/regex routes; here we only handle dict mapping
    as configured in this project (see src/tasks/celery_app.py::task_routes).
    """
    routes: dict[str, dict[str, Any]] = getattr(celery_app.conf, "task_routes", {}) or {}
    for pattern, route in routes.items():
        if _task_matches(task_name, pattern):
            return str(route.get("queue")) if route else None
    return None


def _task_matches(task_name: str, pattern: str) -> bool:
    if pattern.endswith(".*"):
        return task_name.startswith(pattern[:-2])
    return task_name == pattern


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="Fully-qualified Celery task name")
    args = parser.parse_args()

    task_name = args.task
    route_queue = resolve_queue_for_task(task_name)

    # Inspect workers
    try:
        inspector = celery_app.control.inspect(timeout=6.0)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Failed to reach Celery control API: {exc}",
                },
                ensure_ascii=False,
            )
        )
        return 2

    stats = (inspector.stats() or {}) if inspector else {}
    active_queues = (inspector.active_queues() or {}) if inspector else {}

    # Compute whether any worker subscribes to the route_queue
    has_target_queue = None
    if route_queue:
        has_target_queue = False
        for _worker, queues in (active_queues or {}).items():
            names = {q.get("name") for q in (queues or [])}
            if route_queue in names:
                has_target_queue = True
                break

    print(
        json.dumps(
            {
                "ok": True,
                "task": task_name,
                "route_queue": route_queue,
                "workers": {
                    "count": len(stats or {}),
                    "active_queues": active_queues,
                },
                "route_queue_subscribed": has_target_queue,
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
