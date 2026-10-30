"""Unit tests for the task system's sidecar persistence round trip.

The task surface keeps its state in two places: the reflection row
(DuckDB) and a metadata sidecar (SQLite). ``_persist_task_update``
writes the sidecar blob and ``_build_task`` reads it back. These tests
pin the fields that must survive that round trip.

They exist because the fields were *not* surviving it. ``tasks_complete``
computed ``completed_at`` / ``completed_by`` / ``result_notes``, returned
them to the caller, and then dropped them on the floor: the write helper
persisted only ``priority`` / ``effort`` / ``visibility`` / ``due_at`` /
``parent_task_id`` / ``updated_at`` / ``history``, and the read side
hardcoded ``completed_at=None``, ``completed_by=None``,
``result_notes=None``, ``metadata={}``. A task read back after being
completed reported ``completed_by=None`` -- the audit trail the spec
documents was empty.

``status`` was the exception: it is mirrored into the reflection's
``status:<value>`` tag, so it survived even though the blob never held
it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from session_buddy.mcp.tools import tasks_tools
from session_buddy.mcp.tools.tasks_models import FieldDiff, Task

_NOW = datetime(2026, 10, 30, 7, 0, tzinfo=UTC)
_REFLECTION_ID = "01a18ba0cb6b733284ad653e64911e46"
_TASK_ID = "t-" + "0" * 32


def _reflection(tags: list[str] | None = None) -> dict[str, Any]:
    """A minimal reflection row as ``_build_task`` expects to read it.

    ``status`` / ``priority`` / ``effort`` live in the reflection's
    ``<field>:<value>`` tags, not in the sidecar blob, so the tags are a
    parameter: a faithful round trip has to carry them forward.
    """
    return {
        "id": _REFLECTION_ID,
        "content": "a task",
        "tags": list(tags) if tags is not None else ["task", "status:open"],
    }


def _base_blob(**extra: Any) -> dict[str, Any]:
    """A sidecar blob as ``tasks_create`` writes it."""
    blob: dict[str, Any] = {
        "kind": "task",
        "owner": "user:les@example.com",
        "task_id": _TASK_ID,
        "uuid_alias": "000000000000",
        "priority": "normal",
        "effort": None,
        "due_at": None,
        "parent_task_id": None,
        "workflow_id": None,
        "created_at": _NOW.isoformat(),
        "metadata": {},
    }
    blob.update(extra)
    return blob


def _task(**overrides: Any) -> Task:
    """Build a Task with sensible defaults for the fields under test."""
    fields: dict[str, Any] = {
        "id": _TASK_ID,
        "content": "a task",
        "owner": "user:les@example.com",
        "visibility": "private",
        "status": "open",
        "priority": "normal",
        "effort": None,
        "tags": ["task", "status:open"],
        "parent_task_id": None,
        "workflow_id": None,
        "due_at": None,
        "created_at": _NOW,
        "updated_at": _NOW,
        "created_by": "user:les@example.com",
        "completed_at": None,
        "completed_by": None,
        "result_notes": None,
        "metadata": {},
    }
    fields.update(overrides)
    return Task(**fields)


async def _persist(
    task: Task,
    blob: dict[str, Any],
    diffs: list[FieldDiff] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Run ``_persist_task_update`` and return what it wrote.

    Returns ``(blob, tags)``: the sidecar blob and the synced tag list
    the reflection row is updated with. Both are part of the task's
    persisted state, so a faithful round trip carries both forward.
    """
    written: dict[str, Any] = {}
    tags: list[str] = []

    def _capture(_engine, _reflection_id, metadata):
        written.update(metadata)

    async def _capture_reflection(**kwargs):
        tags.extend(kwargs.get("tags") or [])

    with (
        patch.object(tasks_tools.tasks_storage, "persist_task_metadata", _capture),
        patch.object(tasks_tools, "_update_reflection", _capture_reflection),
    ):
        await tasks_tools._persist_task_update(
            reflection_id=_REFLECTION_ID,
            task=task,
            sidecar_meta=blob,
            diff_events=diffs or [],
            actor="user:les@example.com",
        )
    return written, tags


@pytest.mark.unit
async def test_completion_fields_survive_the_round_trip() -> None:
    """The completion audit trail must survive persistence.

    ``tasks_complete`` sets these three fields and returns them to the
    caller; without the write and the read they are returned-then-lost.
    """
    blob = _base_blob()
    completed = _task(
        status="done",
        completed_at=_NOW,
        completed_by="user:les@example.com",
        result_notes="shipped",
    )
    status_diff = FieldDiff(field="status", before="open", after="done")

    written, tags = await _persist(completed, blob, diffs=[status_diff])
    assert written["completed_at"] == _NOW.isoformat()
    assert written["completed_by"] == "user:les@example.com"
    assert written["result_notes"] == "shipped"
    # The status prefix is synced onto the reflection's tags.
    assert "status:done" in tags

    # Read it back the way tasks_get / tasks_update do.
    rebuilt = tasks_tools._build_task(_reflection(tags), written)
    assert rebuilt is not None
    assert rebuilt.completed_at == _NOW
    assert rebuilt.completed_by == "user:les@example.com"
    assert rebuilt.result_notes == "shipped"
    assert rebuilt.status == "done"


@pytest.mark.unit
async def test_an_update_does_not_blank_a_recorded_completion() -> None:
    """A later update must not erase a completion recorded earlier.

    The completion fields are written only when set, and the blob the
    write helper starts from is a copy of what was read -- so an update
    to a completed task keeps its completion.
    """
    blob = _base_blob(
        completed_at=_NOW.isoformat(),
        completed_by="user:les@example.com",
        result_notes="shipped",
    )
    # A task built from that blob: the completion is present.
    task = tasks_tools._build_task(_reflection(), blob)
    assert task is not None
    assert task.completed_by == "user:les@example.com"

    # An update that touches something else must not drop it.
    task.content = "a task, revised"
    written, _tags = await _persist(task, blob)
    assert written["completed_by"] == "user:les@example.com"
    assert written["result_notes"] == "shipped"


@pytest.mark.unit
async def test_caller_metadata_survives_the_round_trip() -> None:
    """``UpdateTaskRequest.metadata`` is part of the task contract.

    It was accepted by the request model and then dropped: neither the
    write helper persisted it nor the read side recovered it.
    """
    blob = _base_blob()
    task = _task(metadata={"uuid_alias": "abc123", "workflow_id": "wf-42"})

    written, _tags = await _persist(task, blob)
    assert written["metadata"] == {"uuid_alias": "abc123", "workflow_id": "wf-42"}

    rebuilt = tasks_tools._build_task(_reflection(), written)
    assert rebuilt is not None
    assert rebuilt.metadata == {"uuid_alias": "abc123", "workflow_id": "wf-42"}


@pytest.mark.unit
async def test_workflow_id_cannot_be_spoofed_through_caller_metadata() -> None:
    """Caller metadata must never become the server-set ``workflow_id``.

    ``workflow_id`` is server-set by the handoff flow only (spec §Authz
    Model). ``UpdateTaskRequest.metadata`` is caller-supplied, so
    promoting ``metadata["workflow_id"]`` into the first-class field
    would let any caller claim a task is bound to a workflow it never
    dispatched -- and the orphan sweeper and the handoff gate both read
    that field.

    The caller's metadata is still persisted (it is the caller's own
    data); it is simply never treated as authoritative for a
    server-set field.
    """
    blob = _base_blob(metadata={"workflow_id": "wf-attacker-chosen"})

    task = tasks_tools._build_task(_reflection(), blob)
    assert task is not None
    assert task.workflow_id is None, (
        "caller metadata must not populate the server-set workflow_id"
    )

    written, _tags = await _persist(task, blob)
    assert written.get("workflow_id") is None, (
        "persisting must not write a workflow_id derived from caller metadata"
    )
    # The caller's own metadata is still there, under its own key.
    assert written["metadata"] == {"workflow_id": "wf-attacker-chosen"}


@pytest.mark.unit
async def test_caller_metadata_cannot_forge_a_server_set_field() -> None:
    """Caller metadata is stored under its own key, never merged.

    ``find_tasks_by_metadata`` filters on the blob's TOP-LEVEL keys
    (``kind``, ``owner``, ...). Merging the caller's dict into the top
    level would let a caller forge ``kind="task"`` on a reflection that
    is not one.
    """
    blob = _base_blob()
    task = _task(metadata={"kind": "task", "owner": "user:someone-else"})

    written, _tags = await _persist(task, blob)
    assert written["kind"] == "task"  # the create-time value, untouched
    assert written["owner"] == "user:les@example.com"  # the server-set owner
    # The caller's dict is nested, so it cannot act as a top-level key.
    assert written["metadata"] == {"kind": "task", "owner": "user:someone-else"}
    assert written["owner"] != "user:someone-else"


@pytest.mark.unit
async def test_updated_at_is_read_back_not_replaced_by_created_at() -> None:
    """``updated_at`` must reflect the last write.

    The read side hardcoded ``updated_at=created_at``, so every task
    looked untouched even after it had been updated.
    """
    later = _NOW.replace(hour=9)
    blob = _base_blob(updated_at=later.isoformat())

    task = tasks_tools._build_task(_reflection(), blob)
    assert task is not None
    assert task.updated_at == later
    assert task.created_at == _NOW


@pytest.mark.unit
async def test_a_task_with_no_history_still_builds() -> None:
    """The regression guard: a blob without the new keys still builds."""
    task = tasks_tools._build_task(_reflection(), _base_blob())
    assert task is not None
    assert task.completed_at is None
    assert task.completed_by is None
    assert task.result_notes is None
    assert task.metadata == {}
    assert task.workflow_id is None


@pytest.mark.unit
async def test_the_diff_history_records_a_completion() -> None:
    """The completion shows up in the history timeline.

    ``tasks_history`` renders the sidecar's ``history`` list, so the
    field-diff entry for the completion has to be written too.
    """
    blob = _base_blob()
    completed = _task(
        status="done", completed_at=_NOW, completed_by="user:les@example.com"
    )

    diff = FieldDiff(field="status", before="open", after="done")
    written, _tags = await _persist(completed, blob, diffs=[diff])

    history = written["history"]
    assert history, "the diff must be recorded in the history timeline"
    assert history[-1]["field"] == "status"
    assert history[-1]["after"] == "done"
    assert history[-1]["actor"] == "user:les@example.com"
