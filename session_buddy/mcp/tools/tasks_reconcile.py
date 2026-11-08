"""Reconciliation helpers for the task-metadata / reflection-store split.

Task metadata lives in the SQLModel sidecar (``tasks_metadata.sqlite``) and
task content lives in the DuckDB reflection store (``reflections_v2``). The
split is scaffolding from commit ``0f90abd4`` (T4 fix round 2, 2026-09-29),
not an architectural decision -- see
``docs/plans/2026-11-07-task-metadata-single-store.md``.

While the split exists, the two stores can disagree. The dangerous
direction is: the sidecar row resolves a task, but the backing reflection
row is not readable by the live connection. Every read path then answers
"no such task", which is indistinguishable from a deletion.

Proven on 2026-11-07: two tasks went invisible between 11:06 and 11:15
while both stores still held their rows, because a DuckDB WAL-poison
recovery dropped them from the live connection's view.

These helpers enumerate the divergence so an operator can see it and act on
it. They are read-only.
"""

from __future__ import annotations

import logging
import typing as t
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


async def find_unreadable_task_reflections(engine: Engine) -> list[str]:
    """Return the reflection ids of tasks whose backing row is unreadable.

    A task row is "unreadable" when the sidecar resolves it as a task but
    the reflection store cannot return its row. That is a durability fault
    in one of the two stores, not a filter -- the task still exists in the
    sidecar and may still exist in the reflection store's on-disk state.

    The returned ids are sorted, so two runs over the same state produce
    the same output.

    Args:
        engine: The sidecar engine to read task rows from. Callers pass
            ``tasks_storage.get_engine()`` in production; tests inject an
            in-memory engine.

    Returns:
        The reflection ids whose reflection row could not be read, sorted.
    """
    # Lazy imports: the task tools import the storage module, and the
    # reflection reader is a private helper of that module. Importing
    # inside the function keeps the dependency acyclic and keeps the
    # import cost off the module-import path.
    from session_buddy.mcp.tools import tasks_storage
    from session_buddy.mcp.tools.tasks_tools import _read_reflection

    candidate_ids = tasks_storage.find_tasks_by_metadata(
        engine=engine,
        metadata_filter={"kind": "task"},
        limit=1000,
    )

    unreadable: list[str] = [
        reflection_id
        for reflection_id in candidate_ids
        if await _read_reflection(reflection_id) is None
    ]
    return sorted(unreadable)


async def find_task_metadata_drift(engine: Engine) -> list[dict[str, t.Any]]:
    """Return the tasks whose two stores disagree about their metadata.

    A task is in drift when the sidecar blob and the reflection row's
    ``metadata`` document hold different values for the same key. During
    the transition (after the backfill, before the sidecar is retired)
    this is expected to be empty; a non-empty result means one of the
    two stores was written without the other.

    Rows whose reflection is unreadable are skipped — they are reported
    by :func:`find_unreadable_task_reflections`, which is the stronger
    signal.

    Args:
        engine: The sidecar engine to read task rows from.

    Returns:
        One entry per drifting task:
        ``{"reflection_id": str, "task_id": str | None, "fields": list[str]}``
        where ``fields`` lists the top-level keys whose values differ.
    """
    from session_buddy.mcp.tools import tasks_storage
    from session_buddy.mcp.tools.tasks_tools import _read_reflection

    candidate_ids = tasks_storage.find_tasks_by_metadata(
        engine=engine,
        metadata_filter={"kind": "task"},
        limit=1000,
    )

    drift: list[dict[str, t.Any]] = []
    for reflection_id in candidate_ids:
        sidecar = (
            tasks_storage.read_task_metadata(
                engine=engine,
                reflection_id=reflection_id,
            )
            or {}
        )
        reflection = await _read_reflection(reflection_id)
        if reflection is None:
            continue
        reflection_meta = reflection.get("metadata")
        if not isinstance(reflection_meta, dict):
            continue
        # Comparing with ``.get`` on both sides means a key that is absent
        # on one side and None on the other is NOT reported as drift.
        fields = sorted(
            key
            for key in set(sidecar) | set(reflection_meta)
            if sidecar.get(key) != reflection_meta.get(key)
        )
        if fields:
            drift.append(
                {
                    "reflection_id": reflection_id,
                    "task_id": sidecar.get("task_id") or reflection_meta.get("task_id"),
                    "fields": fields,
                }
            )
    return drift


__all__ = ["find_task_metadata_drift", "find_unreadable_task_reflections"]
