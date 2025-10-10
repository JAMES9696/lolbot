#!/usr/bin/env python3
"""Concurrent enqueuer for /team-analyze Celery tasks (V2.1 stress tool).

Design:
- Enqueue N tasks per second for D seconds to measure queue/backlog behavior
- Observe Prometheus/Grafana panels for latency/429/worker saturation

Usage:
  poetry run python scripts/load_test_team_analyze.py \
    --rps 5 --duration 60 --match-id NA1_123 --puuid <puuid> --region na1 --user 123456
"""

from __future__ import annotations

import argparse
import asyncio
import time


from src.tasks.team_tasks import analyze_team_task


async def enqueue(
    rps: int, duration: int, match_id: str, puuid: str, region: str, user: str
) -> None:
    interval = 1.0 / max(rps, 1)
    deadline = time.time() + duration
    i = 0
    while time.time() < deadline:
        analyze_team_task.apply_async(
            kwargs={
                "match_id": match_id,
                "requester_puuid": puuid,
                "region": region,
                "discord_user_id": user,
            }
        )
        i += 1
        await asyncio.sleep(interval)
    print(f"Enqueued {i} tasks in {duration}s at ~{rps} rps")


def main() -> None:
    p = argparse.ArgumentParser(description="Celery enqueuer for team-analyze stress test")
    p.add_argument("--rps", type=int, default=5)
    p.add_argument("--duration", type=int, default=60)
    p.add_argument("--match-id", required=True)
    p.add_argument("--puuid", required=True)
    p.add_argument("--region", default="na1")
    p.add_argument("--user", required=True)
    args = p.parse_args()

    asyncio.run(enqueue(args.rps, args.duration, args.match_id, args.puuid, args.region, args.user))


if __name__ == "__main__":
    main()
