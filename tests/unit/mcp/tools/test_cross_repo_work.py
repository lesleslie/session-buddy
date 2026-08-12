"""Unit tests for the ``store_cross_repo_work`` MCP tool handler.

Plan Task 8: conversation_id validation, multi-repo atomicity,
server-side path resolution from ecosystem.yaml.

TDD discipline: 3 tests covering rejection paths, atomic rollback, and
partial status when one repo in a batch is unknown.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.mcp.tools.cross_repo_work import (
    RepoWorkEntry,
    StoreCrossRepoWorkRequest,
    store_cross_repo_work,
)
from session_buddy.memory.cross_repo_work import CommitEntry


def _setup(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Mirrors production schema (schema_v2.py): TIMESTAMP WITH TIME ZONE.
    Conversation identity table is session_windows (v2.1 amendment)."""
    conn = duckdb.connect(str(tmp_path / "m.duckdb"))
    conn.execute(
        "CREATE TABLE session_windows ("
        "id TEXT PRIMARY KEY, "
        "working_directory TEXT NOT NULL, "
        "project TEXT, "
        "started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
        "ended_at TIMESTAMP WITH TIME ZONE, "
        "session_metadata JSON NOT NULL DEFAULT '{}')"
    )
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
    conn.execute(
        "INSERT INTO session_windows (id, working_directory) VALUES (?, ?)",
        ["01HXXXXXXXXXXXXXXXXXXXXXXX", "/tmp"],
    )
    return conn


def _write_manifest(tmp_path: Path, repos: list[dict[str, str]]) -> Path:
    p = tmp_path / "ecosystem.yaml"
    p.write_text(yaml.safe_dump({
        "ecosystem": {r["name"]: {"path": r["path"], "role": r["role"]} for r in repos}
    }))
    return p


@pytest.mark.asyncio
async def test_rejects_unknown_conversation_id(tmp_path: Path) -> None:
    """G7 validation per spec. Validates against session_windows (v2.1)."""
    conn = _setup(tmp_path)
    manifest = _write_manifest(tmp_path, [{"name": "mahavishnu", "path": "/m", "role": "x"}])
    bad_req = StoreCrossRepoWorkRequest(
        conversation_id="01HNOTEXISTXXXXXXXXXXXXXXX",
        repos=[RepoWorkEntry(repo_name="mahavishnu",
                              work_entries=[CommitEntry(kind="commit", sha="a", provenance="explicit")])],
    )
    result = await store_cross_repo_work(
        request=bad_req, merge_primitive=MergePrimitive(),
        conn=conn, ecosystem_path=manifest,
    )
    assert result.status == "failed"
    assert result.error_code == "session_not_found"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_rejects_unknown_repo_with_partial_status(tmp_path: Path) -> None:
    """Spec §Error handling: unknown repo → rejected. When mixed with
    valid repos, status is 'partial'."""
    conn = _setup(tmp_path)
    manifest = _write_manifest(tmp_path, [{"name": "mahavishnu", "path": "/m", "role": "x"}])
    request = StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[
            RepoWorkEntry(repo_name="mahavishnu",
                          work_entries=[CommitEntry(kind="commit", sha="a", provenance="explicit")]),
            RepoWorkEntry(repo_name="unknown_repo",
                          work_entries=[CommitEntry(kind="commit", sha="b", provenance="explicit")]),
        ],
    )
    result = await store_cross_repo_work(
        request=request, merge_primitive=MergePrimitive(),
        conn=conn, ecosystem_path=manifest,
    )
    assert result.status == "partial"
    statuses = {s.repo_name: s.status for s in result.per_repo}
    assert statuses["mahavishnu"] == "stored"
    assert statuses["unknown_repo"] == "rejected"


@pytest.mark.asyncio
async def test_multi_repo_atomic_rollback(tmp_path: Path) -> None:
    """If any repo's merge fails, the whole call rolls back.

    NOTE: The brief's original test sent two RepoWorkEntry instances with
    the same repo_name and expected a UNIQUE-constraint failure. That
    expectation is faulty — the merge primitive uses
    ``ON CONFLICT (conversation_id, repo_name) DO UPDATE`` which absorbs
    duplicates instead of raising. To trigger the rollback path we
    inject a synthetic failure on the second row's _read_dedup_write
    (simulating storage_locked, schema drift, write_conflict, etc.).
    """
    conn = _setup(tmp_path)
    manifest = _write_manifest(tmp_path, [
        {"name": "a", "path": "/a", "role": "x"},
        {"name": "b", "path": "/b", "role": "x"},
    ])
    request = StoreCrossRepoWorkRequest(
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        repos=[
            RepoWorkEntry(repo_name="a",
                          work_entries=[CommitEntry(kind="commit", sha="a1", provenance="explicit")]),
            RepoWorkEntry(repo_name="b",
                          work_entries=[CommitEntry(kind="commit", sha="b1", provenance="explicit")]),
        ],
    )

    mp = MergePrimitive()
    original_read_dedup_write = mp._read_dedup_write
    call_count = {"n": 0}

    def _failing_read_dedup_write(c, incoming):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated storage failure")
        return original_read_dedup_write(c, incoming)

    mp._read_dedup_write = _failing_read_dedup_write  # type: ignore[method-assign]

    result = await store_cross_repo_work(
        request=request, merge_primitive=mp,
        conn=conn, ecosystem_path=manifest,
    )
    assert result.status == "failed"
    count = conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()[0]
    assert count == 0  # atomic rollback — neither row landed
