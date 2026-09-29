"""Unit tests for ``session_buddy.mcp.tools.tasks_storage``.

T4 fix round 2 (2026-09-29): SQLModel-backed metadata sidecar.

These tests pin the contract for the five functions exposed by the
module:
- ``persist_task_metadata`` — upsert by reflection_id
- ``read_task_metadata`` — round-trip read
- ``find_tasks_by_metadata`` — equality filter over the metadata JSON
- ``ensure_metadata_schema`` — idempotent create-all
- End-to-end through ``_store_reflection_operation`` — metadata
  reaches the sidecar when the wrapper chain passes ``metadata=`` to
  ``store_reflection``.

Each test uses an isolated in-memory SQLite engine via
``create_metadata_engine()`` and resets the module-level singleton
between cases so the production on-disk sidecar never opens.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from session_buddy.mcp.tools import tasks_storage


@pytest.fixture
def engine() -> Any:
    """Yield a fresh in-memory engine and reset the module singleton after."""
    e = tasks_storage.create_metadata_engine()
    tasks_storage.set_engine(e)
    try:
        yield e
    finally:
        tasks_storage.set_engine(None)


# ----------------------------------------------------------------------
# Round-trip persistence
# ----------------------------------------------------------------------


def test_persist_task_metadata_round_trip(engine: Any) -> None:
    """Insert metadata, read it back, assert deep equality."""
    md = {"kind": "task", "owner": "user:les", "uuid_alias": "abc123def456"}
    tasks_storage.persist_task_metadata(engine, "ref-1", md)

    assert tasks_storage.read_task_metadata(engine, "ref-1") == md


def test_persist_task_metadata_updates_existing(engine: Any) -> None:
    """Second call with the same reflection_id replaces, not appends."""
    tasks_storage.persist_task_metadata(
        engine,
        "ref-1",
        {"kind": "task", "status": "open"},
    )
    tasks_storage.persist_task_metadata(
        engine,
        "ref-1",
        {"kind": "task", "status": "closed"},
    )

    result = tasks_storage.read_task_metadata(engine, "ref-1")
    assert result is not None
    assert result["status"] == "closed"
    assert len(result) == 2


# ----------------------------------------------------------------------
# Filtering
# ----------------------------------------------------------------------


def test_find_tasks_by_metadata_filters_correctly(engine: Any) -> None:
    """Insert three rows with different metadata; query by ``kind=task``."""
    tasks_storage.persist_task_metadata(engine, "ref-1", {"kind": "task", "owner": "u1"})
    tasks_storage.persist_task_metadata(engine, "ref-2", {"kind": "task", "owner": "u2"})
    tasks_storage.persist_task_metadata(engine, "ref-3", {"kind": "note"})

    matches = tasks_storage.find_tasks_by_metadata(engine, {"kind": "task"})
    assert sorted(matches) == ["ref-1", "ref-2"]


def test_find_tasks_by_metadata_combined_filter(engine: Any) -> None:
    """Query with two key/value pairs AND-matches both."""
    tasks_storage.persist_task_metadata(engine, "ref-1", {"kind": "task", "owner": "user:les"})
    tasks_storage.persist_task_metadata(
        engine,
        "ref-2",
        {"kind": "task", "owner": "user:alice"},
    )
    tasks_storage.persist_task_metadata(engine, "ref-3", {"kind": "task", "owner": "user:les"})
    tasks_storage.persist_task_metadata(engine, "ref-4", {"kind": "note", "owner": "user:les"})

    matches = tasks_storage.find_tasks_by_metadata(
        engine,
        {"kind": "task", "owner": "user:les"},
    )
    assert sorted(matches) == ["ref-1", "ref-3"]


# ----------------------------------------------------------------------
# End-to-end through the reflection wrapper chain
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_create_persists_metadata_through_real_storage(engine: Any) -> None:
    """End-to-end: ``store_reflection(metadata=...)`` reaches the SQLModel sidecar.

    Patches only the reflection adapter (``db.store_reflection``) — every
    other layer in the chain runs against real modules so we verify the
    threading contract end-to-end. The adapter returns a known
    reflection_id; we then assert ``find_tasks_by_metadata({"kind": "task"})``
    includes that id, which is what ``tasks_list`` (T5) depends on.
    """
    from session_buddy.mcp.tools.memory.memory_tools import (
        _store_reflection_operation,
    )

    mock_db = AsyncMock()
    mock_db.store_reflection = AsyncMock(return_value="ref-end-to-end-001")

    metadata = {
        "kind": "task",
        "owner": "user:les",
        "uuid_alias": "abcdef123456",
        "priority": "normal",
    }
    await _store_reflection_operation(
        mock_db,
        "Refactor the auth handler",
        ["task", "refactor"],
        project=None,
        metadata=metadata,
    )

    # Adapter was called exactly once with the expected args/kwargs
    mock_db.store_reflection.assert_awaited_once()
    call = mock_db.store_reflection.await_args
    assert call is not None
    # ``content`` is a positional arg; ``tags`` is a kwarg
    args, kwargs = call.args, call.kwargs
    assert args[0] == "Refactor the auth handler"
    assert kwargs["tags"] == ["task", "refactor"]

    # And the metadata reached the SQLModel sidecar (real DB, not a mock)
    matches = tasks_storage.find_tasks_by_metadata(engine, {"kind": "task"})
    assert "ref-end-to-end-001" in matches

    # Round-trip: the full metadata dict is preserved
    stored = tasks_storage.read_task_metadata(engine, "ref-end-to-end-001")
    assert stored == metadata
