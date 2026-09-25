#!/usr/bin/env python3
"""One-shot backfill: set project='legacy' on reflections with project=NULL.

Background: 234 pre-2026-09-25 reflections had ``project IS NULL`` because the
project column was added 2026-09-25 (Commit 1, ``aa96771a``) but the
backfill was deferred. This script runs the one-shot UPDATE so the
``📁 Projects:`` count in ``reflection_stats`` reflects legacy reflections.

Usage:
    python scripts/backfill_reflection_project.py [--dry-run]

The script is idempotent — running it twice produces the same result.

The default project value is ``"legacy"`` (chosen as a sentinel so operators
can distinguish pre-project-field reflections from new ones). To backfill
with a different value, edit the ``DEFAULT_PROJECT`` constant below.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings

DEFAULT_PROJECT = "legacy"


async def backfill_one_db(db_path: Path, default_project: str) -> int:
    """Backfill ``project=NULL`` rows in one DB file. Returns count updated."""
    settings = ReflectionAdapterSettings(database_path=db_path)
    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
    async with adapter as db:
        # Count before
        cursor = db.conn.execute(
            "SELECT COUNT(*) FROM reflections_v2 WHERE project IS NULL"
        )
        before_nulls = cursor.fetchone()[0]

        if before_nulls == 0:
            return 0

        # Update
        db.conn.execute(
            "UPDATE reflections_v2 SET project = ? WHERE project IS NULL",
            [default_project],
        )
        return before_nulls


def discover_db_paths(data_dir: Path) -> list[Path]:
    """Find all DuckDB files under ``data_dir`` (the canonical store)."""
    if not data_dir.exists():
        return []
    return sorted(data_dir.rglob("*.duckdb"))


async def main(dry_run: bool) -> int:
    from session_buddy.di.config import SessionPaths

    paths = SessionPaths.from_home()
    db_paths = discover_db_paths(paths.data_dir)

    if not db_paths:
        print(f"No DuckDB files found under {paths.data_dir}")
        return 0

    print(f"Found {len(db_paths)} DuckDB file(s) under {paths.data_dir}")
    if dry_run:
        for db_path in db_paths:
            print(f"  [dry-run] would backfill: {db_path}")
        return 0

    total = 0
    for db_path in db_paths:
        updated = await backfill_one_db(db_path, DEFAULT_PROJECT)
        if updated:
            print(f"  backfilled {updated} row(s) in {db_path}")
            total += updated
    print(f"Done. Total rows backfilled: {total}")
    return total


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List DB files that would be backfilled without modifying them.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.dry_run))
    sys.exit(0 if exit_code is not None else 0)


if __name__ == "__main__":
    cli()
