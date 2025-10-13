#!/usr/bin/env python3
"""
Database migration helper for 蔚-上城人.

CAUTION: This script performs destructive operations.

Usage examples:
  # Purge only incomplete/legacy rows (safe-ish)
  python scripts/db_migrate_purge_or_truncate.py --mode purge --yes

  # Truncate the entire match_analytics table (destructive)
  python scripts/db_migrate_purge_or_truncate.py --mode truncate --yes

Env:
  DATABASE_URL is read via src.config.settings.Settings (.env supported)
"""

import argparse
import asyncio

import asyncpg

from src.config.settings import get_settings


async def purge_incomplete(conn: asyncpg.Connection) -> int:
    """Delete obviously incomplete legacy rows (NULL or empty key fields)."""
    # NOTE: Keep criteria conservative to avoid accidental data loss.
    # Rows with NULL score_data are unusable under current model.
    sql = """
    DELETE FROM match_analytics
    WHERE score_data IS NULL
       OR status IS NULL
       OR algorithm_version IS NULL
       OR processing_duration_ms IS NULL
    RETURNING 1;
    """
    rows = await conn.fetch(sql)
    return len(rows)


async def truncate_all(conn: asyncpg.Connection) -> None:
    await conn.execute("TRUNCATE TABLE match_analytics;")


async def main(mode: str, yes: bool) -> None:
    if not yes:
        raise SystemExit("Refusing to run without --yes confirmation.")

    settings = get_settings()
    url = settings.database_url
    pool: asyncpg.Pool | None = None
    try:
        pool = await asyncpg.create_pool(dsn=url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            if mode == "purge":
                deleted = await purge_incomplete(conn)
                print(f"purge_incomplete: deleted={deleted}")
            elif mode == "truncate":
                await truncate_all(conn)
                print("truncate: match_analytics truncated")
            else:
                raise SystemExit(f"Unknown mode: {mode}")
    finally:
        if pool:
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["purge", "truncate"], default="purge")
    ap.add_argument("--yes", action="store_true", help="confirm destructive action")
    args = ap.parse_args()
    asyncio.run(main(args.mode, args.yes))
