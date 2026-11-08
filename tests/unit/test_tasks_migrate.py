"""Tests for the task-metadata backfill.

The task system used to keep task metadata in a SQLite sidecar while the
task body lived in the DuckDB reflection store. The reflection store now
carries the metadata too (``reflections_v2.metadata``); this module
copies the sidecar blobs across so no task loses its fields.

See ``docs/plans/2026-11-07-task-metadata-single-store.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from session_buddy.mcp.tools import tasks_storage


@pytest.fixture
def _engine() -> Any:
    """Yield a fresh in-memory sidecar engine; reset the singleton after."""
    e = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(e)
    try:
        yield e
    finally:
        tasks_storage.set_engine(None)


class _FakeDb:
    """Minimal stand-in for the reflection adapter."""

    def __init__(self, reflections: dict[str, dict[str, Any]]) -> None:
        self.reflections = reflections
        self.updates: list[tuple[str, dict[str, Any]]] = []

    async def get_reflection_by_id(self, reflection_id: str) -> dict[str, Any] | None:
        return self.reflections.get(reflection_id)

    async def update_reflection(
        self,
        reflection_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if reflection_id not in self.reflections:
            return False
        self.updates.append((reflection_id, dict(metadata or {})))
        row = self.reflections[reflection_id]
        row["metadata"] = dict(metadata or {})
        return True


def _seed(engine: Any, reflection_id: str, task_id: str, **extra: Any) -> None:
    tasks_storage.persist_task_metadata(
        engine,
        reflection_id,
        {
            "kind": "task",
            "task_id": task_id,
            "owner": "user:les@example.com",
            "visibility": "private",
            **extra,
        },
    )


@pytest.mark.asyncio
async def test_backfill_copies_sidecar_metadata_into_the_reflection_row(
    _engine: Any,
) -> None:
    """A task whose reflection row has no metadata gets it."""
    from session_buddy.mcp.tools.tasks_migrate import backfill_task_metadata

    _seed(_engine, "ref-1", "t-" + "0" * 32, priority="high")
    db = _FakeDb({"ref-1": {"id": "ref-1", "content": "body", "tags": ["task"]}})

    result = await backfill_task_metadata(_engine, db)

    assert result == {
        "scanned": 1,
        "migrated": 1,
        "skipped": 0,
        "missing_reflection": 0,
    }
    assert db.updates[0][0] == "ref-1"
    assert db.updates[0][1]["kind"] == "task"
    assert db.updates[0][1]["priority"] == "high"


@pytest.mark.asyncio
async def test_backfill_does_not_overwrite_existing_metadata(_engine: Any) -> None:
    """A reflection row that already carries the identity fields is left alone."""
    from session_buddy.mcp.tools.tasks_migrate import backfill_task_metadata

    _seed(_engine, "ref-1", "t-" + "0" * 32, priority="high")
    db = _FakeDb(
        {
            "ref-1": {
                "id": "ref-1",
                "content": "body",
                "tags": ["task"],
                "metadata": {
                    "kind": "task",
                    "owner": "user:les@example.com",
                    "task_id": "t-" + "0" * 32,
                    "priority": "critical",
                },
            }
        }
    )

    result = await backfill_task_metadata(_engine, db)

    assert result["skipped"] == 1
    assert result["migrated"] == 0
    assert db.updates == []
    assert db.reflections["ref-1"]["metadata"]["priority"] == "critical"


@pytest.mark.asyncio
async def test_backfill_counts_reflections_that_no_longer_exist(
    _engine: Any,
) -> None:
    """A sidecar row whose reflection was deleted is counted, not invented."""
    from session_buddy.mcp.tools.tasks_migrate import backfill_task_metadata

    _seed(_engine, "gone", "t-" + "0" * 32)
    db = _FakeDb({})

    result = await backfill_task_metadata(_engine, db)

    assert result["missing_reflection"] == 1
    assert result["migrated"] == 0
    assert db.updates == []


@pytest.mark.asyncio
async def test_backfill_ignores_non_task_rows(_engine: Any) -> None:
    """Only ``kind=task`` rows are task rows."""
    from session_buddy.mcp.tools.tasks_migrate import backfill_task_metadata

    tasks_storage.persist_task_metadata(
        _engine,
        "ordinary",
        {"kind": "note", "owner": "user:les@example.com"},
    )
    db = _FakeDb({"ordinary": {"id": "ordinary", "content": "x", "tags": ["note"]}})

    result = await backfill_task_metadata(_engine, db)

    assert result == {
        "scanned": 0,
        "migrated": 0,
        "skipped": 0,
        "missing_reflection": 0,
    }
    assert db.updates == []


@pytest.mark.asyncio
async def test_backfill_does_not_truncate_at_a_thousand_rows(_engine: Any) -> None:
    """Every task row is migrated — the old ``limit=1000`` silently dropped
    the rest, and the summary looked identical to a complete run."""
    from session_buddy.mcp.tools.tasks_migrate import backfill_task_metadata

    row_count = 1100
    reflections = {}
    for i in range(row_count):
        reflection_id = f"ref-{i:05d}"
        _seed(_engine, reflection_id, "t-" + f"{i:032x}")
        reflections[reflection_id] = {
            "id": reflection_id,
            "content": "body",
            "tags": ["task"],
        }
    db = _FakeDb(reflections)

    result = await backfill_task_metadata(_engine, db)

    assert result["scanned"] == row_count
    assert result["migrated"] == row_count
    assert len(db.updates) == row_count


@pytest.mark.asyncio
async def test_main_backfills_the_configured_sidecar_not_an_in_memory_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main()`` must open the sidecar the server uses.

    ``tasks_storage.get_engine()`` defaults to ``sqlite:///:memory:``; the
    file-backed engine is wired only inside the server's lifespan. A CLI
    that used the default would migrate NOTHING while printing a summary
    indistinguishable from success — and the operator runbook puts a
    sidecar deletion right after it.
    """
    from session_buddy.mcp.tools import tasks_migrate

    sidecar_path = tmp_path / "tasks_metadata.sqlite"
    seed_engine = tasks_storage.create_metadata_engine(sidecar_path)
    _seed(seed_engine, "ref-1", "t-" + "0" * 32)

    monkeypatch.setattr(
        "session_buddy.settings.get_task_metadata_path",
        lambda: sidecar_path,
    )
    db = _FakeDb({"ref-1": {"id": "ref-1", "content": "body", "tags": ["task"]}})

    summary = await tasks_migrate.main(db=db)

    assert summary["migrated"] == 1, summary
    assert db.updates[0][0] == "ref-1"


@pytest.mark.asyncio
async def test_backfill_merges_into_a_partial_document_instead_of_skipping_it(
    _engine: Any,
) -> None:
    """A non-empty document WITHOUT the identity fields is completed.

    The backfill skipped any row whose document was non-empty, which is
    the wrong test: a document that carries only, say, a workflow link
    has no ``owner`` / ``task_id`` / ``kind``, and skipping it leaves the
    task without its identity for good. Once the sidecar is retired that
    task is unreadable. The backfill must MERGE the sidecar blob into a
    document that lacks the identity fields.
    """
    from session_buddy.mcp.tools.tasks_migrate import backfill_task_metadata

    _seed(_engine, "ref-1", "t-" + "0" * 32, priority="high")
    db = _FakeDb(
        {
            "ref-1": {
                "id": "ref-1",
                "content": "body",
                "tags": ["task"],
                # Non-empty, but no identity fields.
                "metadata": {"workflow_id": "wf_1"},
            }
        }
    )

    result = await backfill_task_metadata(_engine, db)

    assert result["migrated"] == 1, result
    assert result["skipped"] == 0, result
    migrated = db.reflections["ref-1"]["metadata"]
    assert migrated["kind"] == "task"
    assert migrated["owner"] == "user:les@example.com"
    assert migrated["task_id"] == "t-" + "0" * 32
    # The existing document's own field is preserved, not overwritten.
    assert migrated["workflow_id"] == "wf_1", migrated
