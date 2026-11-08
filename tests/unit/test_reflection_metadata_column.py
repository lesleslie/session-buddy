"""The reflection store can carry a metadata document.

``reflections_v2`` already has a nullable ``metadata JSON`` column
(``session_buddy/memory/schema_v2.py``), but the adapter never wrote it.
Task metadata therefore had to live in a separate SQLite sidecar
(``session_buddy/mcp/tools/tasks_storage.py``), splitting a task's identity
from its payload across two databases with no transaction between them.

See ``docs/plans/2026-11-07-task-metadata-single-store.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings


@pytest.fixture
async def reflection_db(tmp_path: Path) -> Any:
    """A real adapter on a throwaway DuckDB file, embeddings disabled."""
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "metadata_column.duckdb",
        enable_embeddings=False,
    )
    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()
    try:
        yield adapter
    finally:
        adapter.close()


@pytest.fixture
async def embedding_reflection_db(tmp_path: Path) -> Any:
    """A real adapter whose embedding path is stubbed, so the INSERT that
    carries an embedding vector is exercised too.

    ``store_reflection`` has TWO INSERT statements -- one for rows with an
    embedding, one without. A change that updates only one of them is the
    classic half-done change, so both are covered.
    """
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "metadata_column_embedding.duckdb",
        enable_embeddings=True,
    )
    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)

    async def _fake_embedding(text: str) -> list[float]:
        return [0.0] * 768

    adapter._generate_embedding = _fake_embedding  # ty: ignore[invalid-assignment]
    await adapter.initialize()
    try:
        yield adapter
    finally:
        adapter.close()


async def test_store_reflection_round_trips_metadata(reflection_db: Any) -> None:
    """A metadata dict survives the write/read round trip."""
    reflection_id = await reflection_db.store_reflection(
        content="hello",
        tags=["task"],
        metadata={"kind": "task", "owner": "user:les"},
    )

    row = await reflection_db.get_reflection_by_id(reflection_id)
    assert row is not None
    assert row["metadata"] == {"kind": "task", "owner": "user:les"}


async def test_store_reflection_without_metadata_writes_null(
    reflection_db: Any,
) -> None:
    """Most reflections in the fleet have no metadata; the column stays NULL."""
    reflection_id = await reflection_db.store_reflection(
        content="plain reflection",
        tags=["note"],
    )

    row = await reflection_db.get_reflection_by_id(reflection_id)
    assert row is not None
    assert row["metadata"] == {}


async def test_store_reflection_round_trips_metadata_with_embedding(
    embedding_reflection_db: Any,
) -> None:
    """The INSERT that carries an embedding vector also carries metadata."""
    reflection_id = await embedding_reflection_db.store_reflection(
        content="hello with embedding",
        tags=["task"],
        metadata={"kind": "task"},
    )

    row = await embedding_reflection_db.get_reflection_by_id(reflection_id)
    assert row is not None
    assert row["metadata"] == {"kind": "task"}


async def test_update_reflection_replaces_metadata(reflection_db: Any) -> None:
    """``update_reflection`` can replace the stored metadata document."""
    reflection_id = await reflection_db.store_reflection(
        content="hello",
        metadata={"a": 1},
    )

    assert (
        await reflection_db.update_reflection(reflection_id, metadata={"b": 2}) is True
    )

    row = await reflection_db.get_reflection_by_id(reflection_id)
    assert row is not None
    assert row["metadata"] == {"b": 2}


async def test_update_reflection_without_metadata_leaves_it_alone(
    reflection_db: Any,
) -> None:
    """``update_reflection(content=...)`` must not blank the metadata column."""
    reflection_id = await reflection_db.store_reflection(
        content="hello",
        metadata={"kind": "task"},
    )

    assert (
        await reflection_db.update_reflection(reflection_id, content="new body") is True
    )

    row = await reflection_db.get_reflection_by_id(reflection_id)
    assert row is not None
    assert row["metadata"] == {"kind": "task"}


async def test_store_reflection_rejects_unserialisable_metadata(
    reflection_db: Any,
) -> None:
    """A metadata value that is not JSON-serialisable is an error, not a
    silently malformed document."""
    with pytest.raises((TypeError, ValueError)) as excinfo:
        await reflection_db.store_reflection(
            content="hello",
            metadata={"bad": object()},
        )
    # Assert the failure is about the VALUE, not about the keyword being
    # unknown -- otherwise this test passes for the wrong reason on a
    # version of the adapter that has no ``metadata`` parameter at all.
    assert "serializable" in str(excinfo.value).lower()
