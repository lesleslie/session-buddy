"""Atomic storage primitive for the task -> workflow link.

``Task.workflow_id`` is written by exactly one operation — the link. The
link-once invariant ("a task binds to exactly one workflow") is a
read-check-then-write, which is not atomic: two concurrent linkers can
both observe an unlinked task and both write, and the second write wins
silently. That is not hypothetical here — the handoff's step 3 and the
orphan sweeper's recovery are two independent attempts at the same
link, and the sweeper exists precisely to retry a link that failed.

This module performs the check and the write as ONE conditional
``UPDATE``::

    UPDATE reflections
       SET metadata = json_patch(COALESCE(metadata, '{}'), :patch)
     WHERE id = :id
       AND (json_extract(metadata, '$.workflow_id') IS NULL
            OR json_extract(metadata, '$.workflow_id') = :workflow_id)

The ``WHERE`` clause *is* the invariant: the row is written only when the
task is unlinked or already bound to THIS workflow id. A conflicting
link matches zero rows, and the caller reports that rather than
overwriting the first link.

``json_patch`` is RFC 7386 merge-patch, so the write touches only the
keys carried in the patch and leaves the rest of the blob alone. A
concurrent update to the task's priority or status is therefore not
clobbered by the link.

This module lives beside ``tasks_storage`` rather than inside it because
``tasks_storage`` is shared with the reflection-delete work; keeping the
link primitive in its own module keeps the two changes independent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, inspect, or_, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from session_buddy.mcp.tools.tasks_storage import (
    ReflectionMetadata,
    ensure_metadata_schema,
)

#: The link was written by this call.
LINK_OUTCOME_LINKED = "linked"

#: The task is already bound to a DIFFERENT workflow. The write was
#: refused; the existing binding stands.
LINK_OUTCOME_ALREADY_LINKED = "already_linked"

#: There is no sidecar row for this reflection — the task does not
#: exist (or its metadata was deleted).
LINK_OUTCOME_NOT_FOUND = "not_found"


def link_task_workflow(
    engine: Engine,
    reflection_id: str,
    workflow_id: str,
    *,
    linked_at: str,
    linked_by: str,
    updated_at: str,
    history: list[dict[str, Any]],
) -> str:
    """Bind ``reflection_id``'s task to ``workflow_id``, atomically.

    Args:
        engine: The task-metadata sidecar engine.
        reflection_id: The task's reflection id.
        workflow_id: The workflow id to bind.
        linked_at: ISO-8601 timestamp of the link.
        linked_by: The caller identity that made the link.
        updated_at: ISO-8601 timestamp for the task's ``updated_at``.
        history: The task's FULL history list — the stored list is
            replaced by this one, so it must include the entries already
            on the task. (Merge-patch replaces arrays rather than
            appending to them; a concurrent history entry can be lost.
            The link-once invariant is what the atomicity protects, and
            the history is a diagnostic timeline, not a ledger.)

    Returns:
        ``LINK_OUTCOME_LINKED`` when the row was written,
        ``LINK_OUTCOME_ALREADY_LINKED`` when the task is bound to a
        different workflow and the write was refused, or
        ``LINK_OUTCOME_NOT_FOUND`` when there is no such task row.
    """
    ensure_metadata_schema(engine)
    patch = json.dumps(
        {
            "workflow_id": workflow_id,
            "workflow_linked_at": linked_at,
            "workflow_linked_by": linked_by,
            "updated_at": updated_at,
            "history": history,
        },
    )
    # ``inspect(...).local_table`` rather than ``ReflectionMetadata.__table__``:
    # the declarative ``__table__`` attribute is injected by the metaclass at
    # runtime, so a static checker cannot see it on the class.
    table = inspect(ReflectionMetadata).local_table
    # The column's KEY is "metadata" (the ORM attribute is ``metadata_json``,
    # renamed for the DB via ``sa_column_kwargs``). Index it rather than
    # using ``table.c.metadata`` — on a ``ColumnCollection``, ``.metadata``
    # resolves to the Table's MetaData object, not the column.
    metadata_col = table.c["metadata"]
    with Session(engine) as session:
        # ``exec`` (not ``execute``) for the UPDATE: SQLModel's ``exec`` has a
        # dedicated ``UpdateBase`` overload that returns a ``CursorResult``,
        # which is the type that carries ``rowcount``. ``Session.execute`` is
        # deprecated in SQLModel and widens to a plain ``Result``.
        result = session.exec(
            update(table)
            .where(table.c.id == reflection_id)
            .where(
                or_(
                    func.json_extract(metadata_col, "$.workflow_id").is_(None),
                    func.json_extract(metadata_col, "$.workflow_id") == workflow_id,
                ),
            )
            .values(
                {
                    metadata_col: func.json_patch(
                        func.coalesce(metadata_col, "{}"),
                        patch,
                    ),
                    table.c.updated_at: datetime.now(tz=UTC),
                },
            ),
        )
        session.commit()
        affected = result.rowcount or 0

    if affected:
        return LINK_OUTCOME_LINKED

    # Zero rows: either there is no such task, or it is bound to a
    # different workflow. Distinguish them so the caller can answer
    # "not found" rather than "already linked" for a task that never
    # existed.
    with Session(engine) as session:
        # ``select`` is SQLModel's, not SQLAlchemy's: SQLModel's returns a
        # ``SelectOfScalar``, so ``exec(...).first()`` yields the ORM instance
        # itself. SQLAlchemy's ``select`` returns a Row-producing ``Select``,
        # and the value below would be a ``Row`` rather than the row's model.
        existing: ReflectionMetadata | None = session.exec(
            select(ReflectionMetadata).where(ReflectionMetadata.id == reflection_id),
        ).first()
    if existing is None:
        return LINK_OUTCOME_NOT_FOUND
    return LINK_OUTCOME_ALREADY_LINKED
