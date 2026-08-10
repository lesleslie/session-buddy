"""Integration test: checkpoint_session invokes the cross-repo accountant.

Verifies the wiring end-to-end — after checkpoint_session returns, the DB
must contain at least one cross_repo_work_v2 row tagged with the current
conversation_id. The test creates a sibling repo with one ambient commit
and runs the full checkpoint pipeline.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb
import pytest


def _git_init(p: Path) -> None:
    subprocess.check_call(["git", "init", "--quiet", str(p)])
    subprocess.check_call(["git", "-C", str(p), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(p), "config", "user.name", "T"])


@pytest.mark.integration
async def test_checkpoint_session_invokes_accountant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After checkpoint_session, cross_repo_work_v2 has rows for our conv_id."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)

    sib = tmp_path / "sib"
    sib.mkdir()
    _git_init(sib)
    subprocess.check_call(  # noqa: ASYNC221 — sync setup helper, not an async test body
        ["git", "-C", str(sib), "commit", "--allow-empty", "-m", "x"]
    )

    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(f"ecosystem:\n  sib:\n    path: {sib}\n    role: x\n")
    monkeypatch.setenv("ECOSYSTEM_MANIFEST", str(manifest))

    db = tmp_path / "a.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute(
        "CREATE TABLE session_windows ("
        "id TEXT PRIMARY KEY, "
        "working_directory TEXT NOT NULL, "
        "project TEXT, "
        "started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
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
        "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "UNIQUE (conversation_id, repo_name))"
    )
    conn.close()

    # Mock the connection factory used by the wiring. The wiring does:
    #   adapter = await require_reflection_database()
    #   conn = adapter.conn
    # We need a stable in-process connection that survives both checkpoint
    # steps (initialize_session INSERT into session_windows, and the
    # accountant's INSERT into cross_repo_work_v2). Monkeypatch the
    # helper in utils.database_tools.
    from session_buddy.utils import database_tools

    persistent_conn = duckdb.connect(str(db))
    persistent_conn.execute(
        "INSERT INTO session_windows (id, working_directory) VALUES (?, ?)",
        ["01HXXXXXXXXXXXXXXXXXXXXXXX", str(workdir)],
    )

    class _FakeAdapter:
        @property
        def conn(self):
            return persistent_conn

    async def _fake_require() -> _FakeAdapter:
        return _FakeAdapter()

    monkeypatch.setattr(database_tools, "require_reflection_database", _fake_require)

    from session_buddy.core.session_manager import SessionLifecycleManager

    mgr = SessionLifecycleManager()
    init_envelope = await mgr.initialize_session(working_directory=str(workdir))
    conv_id = init_envelope.get("conversation_id")
    assert conv_id is not None, (
        f"initialize_session returned no conversation_id: {init_envelope}"
    )

    result = await mgr.checkpoint_session(working_directory=str(workdir))

    # Re-use the persistent connection for verification (DuckDB rejects
    # mixed read-only / read-write on the same file path).
    count = persistent_conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        [conv_id],
    ).fetchone()[0]
    assert count >= 1, (
        f"checkpoint didn't write cross_repo_work_v2 rows; got {count}. "
        f"checkpoint result: {result}"
    )

    # G7 contract: cross_repo_work_v2.session_window_start must equal
    # session_windows.started_at for the same conversation_id. Consecutive
    # checkpoints in the same session must share the window so the merge
    # primitive accumulates work. If this fails, the wiring regressed
    # to using a fresh NOW() and broke the load-bearing contract.
    joined = persistent_conn.execute(
        "SELECT crw.session_window_start, sw.started_at "
        "FROM cross_repo_work_v2 crw "
        "JOIN session_windows sw ON crw.conversation_id = sw.id "
        "WHERE crw.conversation_id = ? LIMIT 1",
        [conv_id],
    ).fetchall()
    assert joined, f"no joined row for conv_id={conv_id}"
    crw_start, sw_start = joined[0]
    # DuckDB returns tz-aware datetimes; equality should hold directly.
    # If a tz coercion issue surfaces, fall back to seconds comparison.
    assert crw_start == sw_start, (
        f"G7 violation: crw.session_window_start={crw_start} "
        f"!= session_windows.started_at={sw_start}"
    )
