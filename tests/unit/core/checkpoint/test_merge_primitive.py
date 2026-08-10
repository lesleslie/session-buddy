from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb

from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import (
    CommitEntry,
    CrossRepoWorkRowCreate,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _row(
    sha: str,
    prov: str = "ambient",
    files_changed_count: int | None = None,
    timestamp: datetime | None = None,
    id_suffix: str = "",
) -> CrossRepoWorkRowCreate:
    now = _now()
    return CrossRepoWorkRowCreate(
        id=f"id_{sha}{id_suffix}",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        repo_name="mahavishnu",
        repo_path="/Users/les/Projects/mahavishnu",
        repo_role="orchestrator",
        session_window_start=now,
        session_window_end=now,
        work_entries=[
            CommitEntry(
                kind="commit",
                sha=sha,
                provenance=prov,
                files_changed_count=files_changed_count,
                timestamp=timestamp,
            )
        ],
        contributor_sources=[prov],
    )


def _make_conn() -> duckdb.DuckDBPyConnection:
    # Mirrors production schema (schema_v2.py): TIMESTAMP WITH TIME ZONE.
    # DuckDB's Python client requires pytz to read tz-aware columns (it's a
    # transitive runtime dependency of session-buddy via duckdb).
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE cross_repo_work_v2 ("
        "id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "repo_name TEXT NOT NULL, repo_path TEXT NOT NULL, repo_role TEXT, "
        "session_window_start TIMESTAMP WITH TIME ZONE NOT NULL, "
        "session_window_end TIMESTAMP WITH TIME ZONE NOT NULL, "
        "work_entries JSON NOT NULL, contributor_sources JSON NOT NULL DEFAULT '[]', "
        "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
        "UNIQUE (conversation_id, repo_name))"
    )
    return conn


def test_merge_first_write_inserts() -> None:
    conn = _make_conn()
    mp = MergePrimitive()
    read, ins, ded = mp.merge(conn, _row("sha1"))
    assert ins == 1 and ded == 0
    assert len(read.work_entries) == 1


def test_merge_dedup_prefers_explicit() -> None:
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient"))
    # different sha; should insert
    mp.merge(conn, _row("sha2", "explicit"))
    # collide sha1 ambient with sha1 explicit → dedup, prefer explicit
    read2, ins2, ded2 = mp.merge(conn, _row("sha1", "explicit"))
    assert ins2 == 0 and ded2 == 1
    assert read2.work_entries[0].provenance == "explicit"
    assert "ambient" in read2.contributor_sources
    assert "explicit" in read2.contributor_sources


def test_merge_collision_preserves_max_files_changed() -> None:
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient", files_changed_count=3))
    read, _, _ = mp.merge(conn, _row("sha1", "explicit", files_changed_count=5, id_suffix="2"))
    assert read.work_entries[0].files_changed_count == 5  # max(3, 5)


def test_merge_contributor_sources_order_preserving() -> None:
    conn = _make_conn()
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1", "ambient"))
    read, _, _ = mp.merge(conn, _row("sha1", "explicit", id_suffix="2"))
    assert read.contributor_sources == ["ambient", "explicit"]


def test_merge_collision_preserves_first_observed_timestamp() -> None:
    conn = _make_conn()
    mp = MergePrimitive()
    older = _now() - timedelta(hours=2)
    newer = _now() - timedelta(hours=1)
    mp.merge(conn, _row("sha1", "ambient", timestamp=older))
    read, _, _ = mp.merge(conn, _row("sha1", "explicit", timestamp=newer, id_suffix="2"))
    # First-observed wins on timestamp
    assert read.work_entries[0].timestamp == older


def test_merge_does_not_open_transaction() -> None:
    """Caller-managed transactions: merge() must NOT BEGIN or COMMIT.

    The caller opens BEGIN TRANSACTION (mirroring how CheckpointCrossRepoAccountant
    and CrossRepoPusher will use this primitive); merge() issues only its INSERT.
    ROLLBACK undoes the merge's INSERT — proving merge() did not auto-commit.
    (DuckDB in-memory is autocommit by default, so the test must explicitly open
    the transaction to make the assertion meaningful.)
    """
    conn = _make_conn()
    conn.execute("BEGIN TRANSACTION")
    mp = MergePrimitive()
    mp.merge(conn, _row("sha1"))
    conn.execute("ROLLBACK")
    rows = conn.execute("SELECT COUNT(*) FROM cross_repo_work_v2").fetchone()[0]
    assert rows == 0
