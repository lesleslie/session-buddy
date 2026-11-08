"""Backfill task metadata from the sidecar into the reflection store.

Task metadata used to live only in the SQLModel sidecar
(``tasks_metadata.sqlite``) while the task body lived in the DuckDB
reflection store (``reflections_v2``). The reflection store now carries
the metadata too — in the ``metadata`` column that already existed and
that the adapter never wrote.

This module copies the sidecar blobs across so no task loses its fields.
It is a one-shot migration: it never deletes a sidecar row, and it never
overwrites a reflection row that already has metadata.

Run it with::

    python -m session_buddy.mcp.tools.tasks_migrate

See ``docs/plans/2026-11-07-task-metadata-single-store.md``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import typing as t
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

#: The fields that make a metadata document a TASK's identity. A
#: document without them is partial — it may hold a link or a note, but
#: not enough for the task to be read back.
_IDENTITY_FIELDS = ("kind", "owner", "task_id")


def _has_identity_fields(document: dict[str, t.Any]) -> bool:
    """True when the document carries the task's identity fields."""
    return all(document.get(field) is not None for field in _IDENTITY_FIELDS)


async def backfill_task_metadata(engine: Engine, db: t.Any) -> dict[str, int]:
    """Copy every task's sidecar metadata into its reflection row.

    A reflection row that already carries the task's IDENTITY fields
    (``kind``, ``owner``, ``task_id``) is left alone — the backfill must
    never clobber fresher data. A row whose document is PARTIAL (no
    identity fields — a link mirror, a document written before the
    column existed) is COMPLETED by merging the sidecar blob into it:
    skipping it would leave the task without its identity for good,
    because the sidecar is deleted right after this runs.

    A sidecar row whose reflection no longer exists is counted, not
    resurrected.

    Every task row is scanned. The scan is NOT capped: a cap silently
    drops the tail, and the summary of a truncated run is
    indistinguishable from the summary of a complete one — which for a
    migration is the worst possible failure mode, because the operator
    runbook deletes the sidecar right after this runs.

    Args:
        engine: The sidecar engine to read task rows from.
        db: The reflection adapter (anything with
            ``get_reflection_by_id`` and ``update_reflection``).

    Returns:
        ``{"scanned": int, "migrated": int, "skipped": int,
        "missing_reflection": int}``.
    """
    from session_buddy.mcp.tools import tasks_storage

    candidate_ids = tasks_storage.find_tasks_by_metadata(
        engine=engine,
        metadata_filter={"kind": "task"},
        limit=None,
    )

    migrated = 0
    skipped = 0
    missing = 0

    for reflection_id in candidate_ids:
        sidecar = (
            tasks_storage.read_task_metadata(
                engine=engine,
                reflection_id=reflection_id,
            )
            or {}
        )
        reflection = await db.get_reflection_by_id(reflection_id)
        if reflection is None:
            missing += 1
            continue
        existing = reflection.get("metadata")
        if isinstance(existing, dict) and _has_identity_fields(existing):
            skipped += 1
            continue
        # Merge, so a partial document keeps its own fields and gains the
        # identity fields the sidecar holds. The EXISTING document wins per
        # key: it is the authoritative store and may already be fresher
        # than the sidecar.
        merged = dict(sidecar)
        if isinstance(existing, dict):
            merged.update(existing)
        updated = await db.update_reflection(reflection_id, metadata=merged)
        if updated:
            migrated += 1
        else:
            missing += 1

    return {
        "scanned": len(candidate_ids),
        "migrated": migrated,
        "skipped": skipped,
        "missing_reflection": missing,
    }


async def main(engine: Engine | None = None, db: t.Any = None) -> dict[str, int]:
    """Backfill the live task rows and print a JSON summary.

    The sidecar engine is opened from the CONFIGURED path, not from
    ``tasks_storage.get_engine()`` — that helper defaults to
    ``sqlite:///:memory:`` and the file-backed engine is wired only
    inside the server's lifespan. A CLI that used the default would
    migrate nothing while printing a summary that looks like success.

    Args:
        engine: Override the sidecar engine (tests).
        db: Override the reflection adapter (tests).

    Returns:
        The backfill summary.
    """
    from session_buddy.mcp.tools import tasks_storage

    if engine is None:
        from session_buddy.settings import get_task_metadata_path

        engine = tasks_storage.create_metadata_engine(get_task_metadata_path())
    if db is None:
        from session_buddy.reflection_tools import get_reflection_database

        db = await get_reflection_database()
    summary = await backfill_task_metadata(engine, db)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    asyncio.run(main())


__all__ = ["backfill_task_metadata", "main"]
