"""Schema regression tests for the v2.1 cross-repo-checkpoint-accounting tables.

Task 2 of the 2026-08-05 cross-repo-checkpoint-accounting plan adds two tables
to the reflection DB schema:

* ``session_windows`` — one row per session window. Holds the 26-char
  Crockford ULID that is the canonical conversation identity (i.e. the
  ``conversation_id`` returned by ``_start_impl``). This table supersedes
  ``conversations_v2.id`` as the session-identity table; ``conversations_v2``
  keeps its Memori-style meaning (one row per memory entry).
* ``cross_repo_work_v2`` — one row per ``(conversation_id, repo_name)`` pair
  with a UNIQUE index enforcing dedup at the storage layer. The
  ``work_entries`` JSON column holds a discriminated union of
  ``(commit_sha|plan_path)`` work-entry fragments merged in by Task 8's
  CrossRepoPusher.

These tests verify the DDL is registered in the canonical
``session_buddy.memory.migration.apply_migrations(conn)`` entry point so
every active schema-init / migration path emits the new tables.

Note: the v2.1 amendment (commit ``e307fc68``) added ``session_windows``
alongside ``cross_repo_work_v2`` — earlier v2.0 drafts only had the latter.
Both must land in this task.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from session_buddy.memory.migration import apply_migrations


def test_cross_repo_work_v2_table_present(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    apply_migrations(conn)
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'cross_repo_work_v2'"
    ).fetchall()
    columns = {r[0] for r in rows}
    expected = {
        "id",
        "conversation_id",
        "repo_name",
        "repo_path",
        "repo_role",
        "session_window_start",
        "session_window_end",
        "work_entries",
        "contributor_sources",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(columns), f"missing columns: {expected - columns}"


def test_cross_repo_work_v2_unique_constraint(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    apply_migrations(conn)
    indexes = conn.execute(
        "SELECT index_name FROM duckdb_indexes() "
        "WHERE table_name = 'cross_repo_work_v2'"
    ).fetchall()
    # Index name is the brief-prescribed ``idx_cross_repo_work_v2_conv_repo``
    # (the ``_conv_`` inflection matches the DDL emitted by
    # ``schema_v2.CROSS_REPO_CHECKPOINT_V2_1_DDL``).  The original brief
    # asserted a ``conversation_id_repo_name`` substring that never existed
    # in the prescribed DDL — this assertion matches the index DuckDB
    # actually creates.
    assert any(r[0] == "idx_cross_repo_work_v2_conv_repo" for r in indexes), (
        f"missing UNIQUE (conversation_id, repo_name) index; got {indexes}"
    )


def test_session_windows_table_present(tmp_path: Path) -> None:
    """v2.1 amendment: session_windows holds conversation identity."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    apply_migrations(conn)
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'session_windows'"
    ).fetchall()
    columns = {r[0] for r in rows}
    expected = {
        "id",
        "working_directory",
        "project",
        "started_at",
        "ended_at",
        "session_metadata",
    }
    assert expected.issubset(columns), f"missing columns: {expected - columns}"
