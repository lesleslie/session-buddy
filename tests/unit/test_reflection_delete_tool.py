#!/usr/bin/env python3
"""Unit tests for the per-reflection delete path.

Covers three layers:

- ``ReflectionDatabaseAdapter.delete_reflection`` — row removal, idempotency,
  and the derived artifacts that live on the same row (embedding, MinHash
  fingerprint, tags).
- ``tasks_storage.delete_task_metadata`` — cleanup of the SQLite sidecar,
  which lives in a different physical database and therefore cannot be
  reached by the DuckDB delete.
- The MCP ``delete_reflection`` tool surface.

``asyncio_mode = "auto"`` is set in pyproject, so async tests need no
decorator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from session_buddy.adapters.reflection_adapter import (
    ReflectionDatabaseAdapter,
)
from session_buddy.mcp.tools import tasks_storage
from session_buddy.mcp.tools.advanced import fingerprint_tools
from session_buddy.mcp.tools.memory import memory_tools

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


@pytest.fixture
async def adapter(tmp_path: Path) -> AsyncGenerator[ReflectionDatabaseAdapter]:
    """An initialized adapter backed by a temporary DuckDB file."""
    db = ReflectionDatabaseAdapter(
        # NB: collection names are validated against SQL keywords, so this
        # must not contain "DELETE".
        collection_name="test_reflection_rm",
        db_path=str(tmp_path / "delete_test.duckdb"),
    )
    await db.initialize()
    try:
        yield db
    finally:
        await db.aclose()


# ==============================================================================
# Adapter: delete_reflection
# ==============================================================================


class TestDeleteReflection:
    """Behaviour of the adapter-level delete."""

    async def test_deletes_existing_reflection(self, adapter: ReflectionDatabaseAdapter) -> None:
        """A stored reflection is removed and reports success."""
        reflection_id = await adapter.store_reflection(
            "A reflection that should be deletable.",
            tags=["delete-test"],
        )

        assert await adapter.delete_reflection(reflection_id) is True
        assert await adapter.get_reflection_by_id(reflection_id) is None

    async def test_unknown_id_returns_false(self, adapter: ReflectionDatabaseAdapter) -> None:
        """Deleting an unknown ID is a no-op, not an error."""
        assert await adapter.delete_reflection("does-not-exist") is False

    async def test_empty_id_returns_false(self, adapter: ReflectionDatabaseAdapter) -> None:
        """An empty ID short-circuits before touching the database."""
        assert await adapter.delete_reflection("") is False

    async def test_delete_is_idempotent(self, adapter: ReflectionDatabaseAdapter) -> None:
        """The second delete of the same ID reports False."""
        reflection_id = await adapter.store_reflection("Delete me twice.")

        assert await adapter.delete_reflection(reflection_id) is True
        assert await adapter.delete_reflection(reflection_id) is False

    async def test_deleted_reflection_absent_from_search(
        self, adapter: ReflectionDatabaseAdapter
    ) -> None:
        """A deleted reflection no longer comes back from a text search."""
        marker = "zorbulax uniquetoken"
        reflection_id = await adapter.store_reflection(f"Contains {marker} inside.")

        found = await adapter.search_reflections(marker, use_embeddings=False)
        assert any(r["id"] == reflection_id for r in found)

        await adapter.delete_reflection(reflection_id)

        after = await adapter.search_reflections(marker, use_embeddings=False)
        assert not any(r["id"] == reflection_id for r in after)

    async def test_deleted_reflection_absent_from_cached_search(
        self, adapter: ReflectionDatabaseAdapter
    ) -> None:
        """The query cache stores IDs and re-reads rows, so deletes take effect.

        The cache holds result *IDs*; the rows are re-fetched on a hit. A
        deleted reflection therefore drops out of a cached search without any
        cache purge.
        """
        marker = "quixotric cachetoken"
        reflection_id = await adapter.store_reflection(f"Contains {marker} inside.")

        # Prime the cache.
        first = await adapter.search_reflections(
            marker, use_embeddings=False, use_cache=True
        )
        assert any(r["id"] == reflection_id for r in first)

        await adapter.delete_reflection(reflection_id)

        # Second call is a cache hit; the row must no longer be returned.
        second = await adapter.search_reflections(
            marker, use_embeddings=False, use_cache=True
        )
        assert not any(r["id"] == reflection_id for r in second)

    async def test_deleted_fingerprint_frees_the_content(
        self, adapter: ReflectionDatabaseAdapter
    ) -> None:
        """The MinHash fingerprint is removed with the row.

        Duplicate detection reads fingerprints straight off the table, so a
        deleted reflection must not keep blocking a re-store of the same
        content.
        """
        content = "Exactly the same content, stored twice over."
        first_id = await adapter.store_reflection(content, deduplicate=True)

        # Still detected as a duplicate while it exists.
        duplicate_id = await adapter.store_reflection(content, deduplicate=True)
        assert duplicate_id == first_id

        await adapter.delete_reflection(first_id)

        # With the row gone the fingerprint is gone too, so this stores fresh.
        fresh_id = await adapter.store_reflection(content, deduplicate=True)
        assert fresh_id != first_id


# ==============================================================================
# Sidecar: delete_task_metadata
# ==============================================================================


class TestDeleteTaskMetadata:
    """Cleanup of the SQLite task-metadata sidecar."""

    async def test_removes_the_sidecar_row(self) -> None:
        """The sidecar row is deleted once the reflection is gone."""
        engine = tasks_storage.create_metadata_engine()
        tasks_storage.persist_task_metadata(
            engine, "ref-123", {"kind": "task", "uuid_alias": "abc"}
        )
        assert tasks_storage.read_task_metadata(engine, "ref-123") is not None

        assert tasks_storage.delete_task_metadata(engine, "ref-123") is True
        assert tasks_storage.read_task_metadata(engine, "ref-123") is None

    async def test_unknown_id_returns_false(self) -> None:
        """Deleting an absent sidecar row reports False."""
        engine = tasks_storage.create_metadata_engine()
        assert tasks_storage.delete_task_metadata(engine, "nope") is False


# ==============================================================================
# MCP tool surface
# ==============================================================================


class TestDeleteReflectionTool:
    """The MCP-facing ``delete_reflection`` tool."""

    async def test_reports_success(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successful delete reports the reflection id back."""
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection("Delete via the MCP tool.")

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "Deleted reflection" in result
        assert reflection_id in result
        assert await adapter.get_reflection_by_id(reflection_id) is None

    async def test_reports_not_found_for_unknown_id(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unknown ID is reported as not found, not as a failure."""
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)

        result = await memory_tools._delete_reflection_impl("no-such-reflection")

        # Both envelopes carry the id, so assert the not-found envelope
        # specifically -- otherwise an inverted contract still passes.
        assert "No reflection with ID 'no-such-reflection' exists." in result
        assert "Deleted reflection" not in result

    async def test_tool_removes_the_task_metadata_sidecar(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The tool drops the sidecar row, not just the reflection row."""
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection("Backed by a sidecar row.")
        engine = tasks_storage.create_metadata_engine()
        tasks_storage.persist_task_metadata(engine, reflection_id, {"kind": "note"})
        monkeypatch.setattr(tasks_storage, "get_engine", lambda: engine)
        assert tasks_storage.read_task_metadata(engine, reflection_id) is not None

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "Deleted reflection" in result
        assert tasks_storage.read_task_metadata(engine, reflection_id) is None

    async def test_refuses_to_delete_a_task_backed_reflection(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A reflection backing a task is refused -- the task surface owns it."""
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection("A task-backed reflection.")
        engine = tasks_storage.create_metadata_engine()
        tasks_storage.persist_task_metadata(
            engine, reflection_id, {"kind": "task", "owner": "user:alice"}
        )
        monkeypatch.setattr(tasks_storage, "get_engine", lambda: engine)

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "task lifecycle" in result
        assert await adapter.get_reflection_by_id(reflection_id) is not None

    async def test_refusal_does_not_disclose_the_task_owner(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The refusal must not name the task's owner.

        This tool has no caller identity to check visibility against, so
        naming the owner back would hand an unauthorised caller the
        identity of whoever owns the task they just probed for.
        """
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection("A task-backed reflection.")
        engine = tasks_storage.create_metadata_engine()
        tasks_storage.persist_task_metadata(
            engine, reflection_id, {"kind": "task", "owner": "user:alice"}
        )
        monkeypatch.setattr(tasks_storage, "get_engine", lambda: engine)

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "alice" not in result
        assert "user:alice" not in result

    async def test_refuses_to_delete_a_task_tagged_reflection_without_a_sidecar(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The ``"task"`` tag alone is enough to refuse the delete.

        The sidecar engine defaults to in-memory SQLite, so it starts
        empty in every new process. The tag lives in DuckDB and survives
        a restart, so it is the discriminator that still holds when the
        sidecar does not. Without this, every task-backed reflection
        becomes deletable across a restart -- which is exactly when the
        ownership guard is supposed to matter.
        """
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection(
            "A task-tagged reflection.", tags=["task"]
        )
        # No sidecar row at all: the sidecar is empty, as it is in a
        # freshly started process.
        engine = tasks_storage.create_metadata_engine()
        monkeypatch.setattr(tasks_storage, "get_engine", lambda: engine)
        assert tasks_storage.read_task_metadata(engine, reflection_id) is None

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "task lifecycle" in result
        assert await adapter.get_reflection_by_id(reflection_id) is not None

    async def test_deletes_an_untagged_reflection_with_no_sidecar(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The guard must not block ordinary reflections."""
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection("Just a reflection.")
        engine = tasks_storage.create_metadata_engine()
        monkeypatch.setattr(tasks_storage, "get_engine", lambda: engine)

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "Deleted reflection" in result
        assert await adapter.get_reflection_by_id(reflection_id) is None

    async def test_refuses_to_delete_when_the_sidecar_cannot_be_read(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unreadable sidecar fails closed -- "cannot check" is not "not a task".

        The ownership guard is the only thing standing between this tool
        and another owner's private task. If the sidecar cannot be read,
        the guard cannot fire, so proceeding would delete exactly the row
        it exists to protect.
        """
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)
        reflection_id = await adapter.store_reflection("A reflection to protect.")

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("sidecar store is broken")

        monkeypatch.setattr(tasks_storage, "read_task_metadata", _boom)

        result = await memory_tools._delete_reflection_impl(reflection_id)

        assert "refused" in result
        # The reflection must survive: the guard refused, it did not fail
        # open.
        assert await adapter.get_reflection_by_id(reflection_id) is not None

    async def test_rejects_empty_id(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An empty reflection id is a validation error."""
        monkeypatch.setattr(memory_tools, "_reflection_db", adapter)

        result = await memory_tools._delete_reflection_impl("   ")

        assert "reflection_id" in result.lower()

    async def test_tool_is_registered(self) -> None:
        """The tool is exposed by the memory tool registration."""
        registered: list[str] = []

        class _FakeMCP:
            def tool(self, *_args: object, **_kwargs: object):
                def _decorator(fn: object) -> object:
                    registered.append(getattr(fn, "__name__", ""))
                    return fn

                return _decorator

        memory_tools.register_memory_tools(_FakeMCP())

        assert "delete_reflection" in registered


# ==============================================================================
# Sibling path: the deduplication delete
# ==============================================================================


class TestDeduplicationDeletePath:
    """The dedup path is a delete path, so it carries the same guard.

    ``deduplicate_content`` removes duplicate reflections. Without the
    task-ownership gate it would remove a task-backed reflection -- and
    with it another owner's private task -- with no ownership check,
    which is exactly what the gate on the MCP tool exists to prevent.
    """

    async def test_task_backed_reflection_is_not_deleted(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A task-backed reflection survives deduplication."""
        monkeypatch.setattr(tasks_storage, "get_engine", tasks_storage.create_metadata_engine)
        reflection_id = await adapter.store_reflection(
            "A task that happens to be a duplicate.", tags=["task"]
        )

        result = await fingerprint_tools._delete_duplicate_content(
            adapter,
            [{"id": reflection_id, "type": "reflection"}],
            "default",
            0.85,
        )

        assert result["duplicates_removed"] == 0
        assert await adapter.get_reflection_by_id(reflection_id) is not None

    async def test_ordinary_reflection_is_deleted(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The gate must not stop deduplication from doing its job."""
        monkeypatch.setattr(tasks_storage, "get_engine", tasks_storage.create_metadata_engine)
        reflection_id = await adapter.store_reflection("Just a duplicate.")

        result = await fingerprint_tools._delete_duplicate_content(
            adapter,
            [{"id": reflection_id, "type": "reflection"}],
            "default",
            0.85,
        )

        assert result["duplicates_removed"] == 1
        assert await adapter.get_reflection_by_id(reflection_id) is None

    async def test_fails_closed_when_the_sidecar_cannot_be_read(
        self,
        adapter: ReflectionDatabaseAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unreadable sidecar means the row is left alone, not deleted."""
        engine = tasks_storage.create_metadata_engine()
        monkeypatch.setattr(tasks_storage, "get_engine", lambda: engine)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("sidecar store is broken")

        monkeypatch.setattr(tasks_storage, "read_task_metadata", _boom)
        reflection_id = await adapter.store_reflection("A duplicate of unknown status.")

        result = await fingerprint_tools._delete_duplicate_content(
            adapter,
            [{"id": reflection_id, "type": "reflection"}],
            "default",
            0.85,
        )

        assert result["duplicates_removed"] == 0
        assert await adapter.get_reflection_by_id(reflection_id) is not None
