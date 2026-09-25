"""Unit tests for the provenance columns on ``reflections_v2``.

Track C (2026-09-25 serverless-tiering plan) adds:

- ``source_session_id`` and ``source_artifact_uri`` columns on
  ``reflections_v2`` (and the legacy ``reflections`` table) so callers
  can answer ``search_by_source_session`` cheaply.
- Auto-extraction in ``store_reflection`` of the ``provenance:<json>``
  tag entries that Track A-ext2 encoded.
- A backfill script that scans ``tags`` for ``provenance:`` entries and
  populates the new columns.
- A new ``search_by_source_session`` MCP tool.

These tests cover the four commits in this track:

1. C1 — schema migration is idempotent (re-init does not error).
2. C2 — store_reflection extracts the ``provenance:<json>`` tags.
3. C3 — backfill populates existing rows from legacy tags.
4. C4 — search_by_source_session returns rows by session id.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from session_buddy.adapters import reflection_adapter_oneiric as reflection_module
from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings


def _settings(tmp_path: Path, name: str = "test.duckdb") -> ReflectionAdapterSettings:
    return ReflectionAdapterSettings(
        database_path=tmp_path / name,
        enable_embeddings=False,
        enable_vss=False,
        enable_hnsw_index=False,
    )


# ============================================================================
# Task C1 — Schema migration
# ============================================================================


class TestProvenanceSchema:
    """C1: provenance columns are present and idempotently added."""

    async def test_columns_present_after_init(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            cols = db.conn.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = ? AND column_name IN ('source_session_id', 'source_artifact_uri')
                """,
                [db._table("reflections")],
            ).fetchall()
            names = {row[0] for row in cols}
        assert "source_session_id" in names
        assert "source_artifact_uri" in names

    async def test_idempotent_reinitialize(self, tmp_path: Path) -> None:
        """Re-opening the same DB does NOT raise — IF NOT EXISTS guard works."""
        settings1 = _settings(tmp_path)
        adapter1 = ReflectionDatabaseAdapterOneiric(settings=settings1)
        async with adapter1:
            pass

        settings2 = _settings(tmp_path)
        adapter2 = ReflectionDatabaseAdapterOneiric(settings=settings2)
        async with adapter2:
            # Second init on existing DB: column already there, ALTER is no-op
            assert adapter2.conn is not None
            cols = adapter2.conn.execute(
                "DESCRIBE " + adapter2._table("reflections")
            ).fetchall()
        col_names = {row[0] for row in cols}
        assert "source_session_id" in col_names
        assert "source_artifact_uri" in col_names


# ============================================================================
# Task C2 — store_reflection auto-extracts provenance from tags
# ============================================================================


class TestStoreReflectionProvenanceExtraction:
    """C2: store_reflection reads provenance from ``provenance:<json>`` tags."""

    async def test_explicit_kwargs_written_to_columns(self, tmp_path: Path) -> None:
        """Passing source_session_id/source_artifact_uri explicitly stores them."""
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            rid = await db.store_reflection(
                content="explicit-provenance reflection",
                tags=["manual"],
                project="test-proj",
                source_session_id="sess-explicit-1",
                source_artifact_uri="pool://test/task/explicit-1",
            )
            row = db.conn.execute(
                f"SELECT id, source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE id = ?",
                [rid],
            ).fetchone()
            assert row is not None
            assert row[1] == "sess-explicit-1"
            assert row[2] == "pool://test/task/explicit-1"

    async def test_extracts_provenance_from_tag(self, tmp_path: Path) -> None:
        """A ``provenance:<json>`` tag is auto-decoded into the new columns."""
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        payload = {
            "source_session_id": "sess-tag-2",
            "source_artifact_uri": "pool://tagged/task/42",
        }
        encoded = f"provenance:{json.dumps(payload, sort_keys=True)}"
        async with adapter as db:
            rid = await db.store_reflection(
                content="tag-extracted reflection",
                tags=["pool-task", "pool:sess-tag-2", encoded],
                project="sess-tag-2",
            )
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE id = ?",
                [rid],
            ).fetchone()
        assert row is not None
        assert row[0] == "sess-tag-2"
        assert row[1] == "pool://tagged/task/42"

    async def test_explicit_kwargs_override_tag(self, tmp_path: Path) -> None:
        """Explicit kwargs take precedence over a (possibly stale) tag."""
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        tag_payload = {"source_session_id": "old", "source_artifact_uri": "old-uri"}
        encoded = f"provenance:{json.dumps(tag_payload, sort_keys=True)}"
        async with adapter as db:
            rid = await db.store_reflection(
                content="override reflection",
                tags=[encoded],
                project="override",
                source_session_id="new",
                source_artifact_uri="new-uri",
            )
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE id = ?",
                [rid],
            ).fetchone()
        assert row is not None
        assert row[0] == "new"
        assert row[1] == "new-uri"

    async def test_malformed_provenance_tag_ignored(self, tmp_path: Path) -> None:
        """A malformed tag does not break the write — columns stay NULL."""
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            rid = await db.store_reflection(
                content="malformed-tag reflection",
                tags=["provenance:this is not json"],
                project="malformed",
            )
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE id = ?",
                [rid],
            ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None

    async def test_non_string_tag_entries_ignored(self, tmp_path: Path) -> None:
        """A tag list that contains non-strings (defensive) does not crash."""
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            rid = await db.store_reflection(
                content="non-string-tag reflection",
                # Mypy/type-checkers would reject this; we bypass via cast.
                tags=["normal", 123, None],  # type: ignore[list-item]
                project="non-string",
            )
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE id = ?",
                [rid],
            ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None


# ============================================================================
# Task C3 — Backfill populates existing rows
# ============================================================================


class TestBackfillProvenance:
    """C3: the backfill script populates columns from legacy tag encodings.

    These tests simulate pre-Track-C legacy data by inserting rows
    directly via the ``reflections_v2`` table (bypassing
    ``store_reflection``, which would auto-extract provenance post-C2).
    That mirrors the migration scenario: existing rows have
    ``provenance:<json>`` tags and NULL provenance columns.
    """

    @staticmethod
    def _insert_legacy_row(
        db: reflection_module.ReflectionDatabaseAdapterOneiric,
        *,
        content: str,
        tags: list[str],
        project: str | None,
    ) -> None:
        """Insert a reflection row directly via duckdb, simulating pre-Track-C data.

        Bypasses ``store_reflection`` so the provenance columns stay NULL.
        This is exactly what the existing pool-encoded rows look like
        before the backfill runs.
        """
        from ulid import ULID

        rid = str(ULID())
        db.conn.execute(
            f"""
            INSERT INTO {db._table("reflections")}
                (id, content, tags, project, namespace, category,
                 importance_score, memory_tier, timestamp, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'default', 'context', 0.5, 'long_term',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [rid, content, tags, project],
        )

    async def test_backfill_finds_tag_encoded_rows(self, tmp_path: Path) -> None:
        """Insert rows with provenance: tags, run backfill, verify columns."""
        from scripts.backfill_reflection_provenance import backfill

        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        payload = {
            "source_session_id": "prefill-sess",
            "source_artifact_uri": "pool://prefill/task/1",
        }
        encoded = f"provenance:{json.dumps(payload, sort_keys=True)}"
        async with adapter as db:
            self._insert_legacy_row(
                db,
                content="backfill target",
                tags=["pool-task", encoded],
                project="prefill-sess",
            )
        updated, skipped = backfill(tmp_path / "test.duckdb", dry_run=False)
        assert updated == 1
        assert skipped == 0
        # Re-open the adapter and read the column back.
        async with adapter as db:
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE project = 'prefill-sess'"
            ).fetchone()
        assert row is not None
        assert row[0] == "prefill-sess"
        assert row[1] == "pool://prefill/task/1"

    async def test_backfill_dry_run_does_not_mutate(self, tmp_path: Path) -> None:
        """dry_run=True returns the planned count but leaves columns NULL."""
        from scripts.backfill_reflection_provenance import backfill

        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        payload = {
            "source_session_id": "dryrun-sess",
            "source_artifact_uri": "pool://dryrun/task/9",
        }
        encoded = f"provenance:{json.dumps(payload, sort_keys=True)}"
        async with adapter as db:
            self._insert_legacy_row(
                db,
                content="dry-run target",
                tags=[encoded],
                project="dryrun-sess",
            )
        updated, _skipped = backfill(tmp_path / "test.duckdb", dry_run=True)
        assert updated == 1
        async with adapter as db:
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE project = 'dryrun-sess'"
            ).fetchone()
        assert row[0] is None
        assert row[1] is None

    async def test_backfill_idempotent(self, tmp_path: Path) -> None:
        """Running backfill twice produces the same final state — no overwrite."""
        from scripts.backfill_reflection_provenance import backfill

        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        payload = {
            "source_session_id": "idem-sess",
            "source_artifact_uri": "pool://idem/task/3",
        }
        encoded = f"provenance:{json.dumps(payload, sort_keys=True)}"
        async with adapter as db:
            self._insert_legacy_row(
                db,
                content="idempotent target",
                tags=[encoded],
                project="idem-sess",
            )
        u1, s1 = backfill(tmp_path / "test.duckdb", dry_run=False)
        u2, s2 = backfill(tmp_path / "test.duckdb", dry_run=False)
        # First run: 1 update, 0 skipped. Second run: the WHERE clause
        # already filtered out the populated row, so the loop sees
        # nothing — both counters stay at 0. The columns are unchanged.
        assert u1 == 1 and s1 == 0
        assert u2 == 0 and s2 == 0
        # Verify the columns are still populated from the first run.
        async with adapter as db:
            row = db.conn.execute(
                f"SELECT source_session_id, source_artifact_uri FROM {db._table('reflections')} WHERE project = 'idem-sess'"
            ).fetchone()
        assert row is not None
        assert row[0] == "idem-sess"
        assert row[1] == "pool://idem/task/3"

    async def test_backfill_skips_rows_without_provenance(self, tmp_path: Path) -> None:
        """Rows without a provenance: tag are skipped."""
        from scripts.backfill_reflection_provenance import backfill

        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            self._insert_legacy_row(
                db,
                content="no-provenance row",
                tags=["plain", "tags"],
                project="no-provenance",
            )
        updated, skipped = backfill(tmp_path / "test.duckdb", dry_run=False)
        assert updated == 0
        assert skipped == 1


# ============================================================================
# Task C4 — search_by_source_session
# ============================================================================


class TestSearchBySourceSession:
    """C4: search_by_source_session returns rows matching source_session_id."""

    async def test_returns_matching_rows(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            await db.store_reflection(
                content="matching row",
                tags=["manual"],
                project="sess-a",
                source_session_id="sess-a",
                source_artifact_uri="pool://sess-a/task/1",
            )
            await db.store_reflection(
                content="non-matching row",
                tags=["manual"],
                project="sess-b",
                source_session_id="sess-b",
                source_artifact_uri="pool://sess-b/task/1",
            )
            results = await db.search_by_source_session("sess-a")
        assert len(results) == 1
        assert results[0]["content"] == "matching row"
        assert results[0]["source_session_id"] == "sess-a"
        assert results[0]["source_artifact_uri"] == "pool://sess-a/task/1"

    async def test_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            await db.store_reflection(
                content="only-row",
                tags=["manual"],
                project="sess-only",
                source_session_id="sess-only",
                source_artifact_uri="pool://sess-only/task/1",
            )
            results = await db.search_by_source_session("nope")
        assert results == []

    async def test_limit_is_respected(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            for i in range(5):
                await db.store_reflection(
                    content=f"row-{i}",
                    tags=["manual"],
                    project="sess-many",
                    source_session_id="sess-many",
                    source_artifact_uri=f"pool://sess-many/task/{i}",
                )
            results = await db.search_by_source_session("sess-many", limit=2)
        assert len(results) == 2

    async def test_search_by_source_session_mcp_tool(self, tmp_path: Path) -> None:
        """The MCP wrapper exposes ``search_by_source_session``."""
        from session_buddy.mcp.tools.memory import memory_tools

        settings = _settings(tmp_path)
        adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
        async with adapter as db:
            await db.store_reflection(
                content="mcp-tool target",
                tags=["manual"],
                project="sess-mcp",
                source_session_id="sess-mcp",
                source_artifact_uri="pool://sess-mcp/task/1",
            )

            # Monkeypatch the module-level ``_get_reflection_database`` to
            # return our in-memory adapter so the MCP wrapper hits it.
            async def _fake_get() -> ReflectionDatabaseAdapterOneiric:
                return db

            original_get = memory_tools._get_reflection_database
            memory_tools._get_reflection_database = _fake_get  # type: ignore[assignment]
            try:
                # Direct call to the impl helper bypasses the tool-registration
                # closure (which lives inside _register_core_memory_tools and
                # is hard to invoke in isolation).
                output = await memory_tools._search_by_source_session_impl(
                    session_id="sess-mcp", limit=10
                )
            finally:
                memory_tools._get_reflection_database = original_get  # type: ignore[assignment]
        assert "mcp-tool target" in output
        assert "sess-mcp" in output
