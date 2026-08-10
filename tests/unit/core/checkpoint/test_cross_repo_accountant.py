from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller
from session_buddy.core.checkpoint.cross_repo_accountant import (
    CheckpointCrossRepoAccountant,
    CrossRepoCaptureSummary,
)
from session_buddy.core.checkpoint.merge_primitive import MergePrimitive
from session_buddy.memory.cross_repo_work import (
    CrossRepoWorkRowRead,
)


def _git_init(p: Path) -> None:
    subprocess.check_call(["git", "init", "--quiet", str(p)])
    subprocess.check_call(["git", "-C", str(p), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(p), "config", "user.name", "T"])


def _commit(p: Path, msg: str) -> str:
    subprocess.check_call(["git", "-C", str(p), "commit", "--allow-empty", "-m", msg])
    return subprocess.check_output(["git", "-C", str(p), "rev-parse", "HEAD"]).decode().strip()


def _setup_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Mirrors production schema (schema_v2.py): TIMESTAMP WITH TIME ZONE."""
    conn = duckdb.connect(str(tmp_path / "a.duckdb"))
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


def _explode_multi_merge(
    *args: object, **kwargs: object
) -> tuple[list[CrossRepoWorkRowRead], int, int]:
    raise RuntimeError("simulated multi_merge failure for G6 rollback test")


@pytest.mark.asyncio
async def test_capture_multi_repo_writes_per_repo_rows(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sib_a = tmp_path / "a"
    sib_a.mkdir()
    _git_init(sib_a)
    sib_b = tmp_path / "b"
    sib_b.mkdir()
    _git_init(sib_b)
    _commit(sib_a, "feat(a)")
    _commit(sib_b, "feat(b)")
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(
        f"ecosystem:\n  a:\n    path: {sib_a}\n    role: x\n  b:\n    path: {sib_b}\n    role: x\n"
    )
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest_path=manifest),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary: CrossRepoCaptureSummary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=UTC) - timedelta(hours=1),
        session_window_end=datetime.now(tz=UTC) + timedelta(hours=1),
    )
    assert summary.repos_captured == 2
    assert summary.ambient_failures == []
    # Verify TWO rows written, not one
    count = conn.execute(
        "SELECT COUNT(*) FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()[0]
    assert count == 2


@pytest.mark.asyncio
async def test_capture_never_raises_on_ambient_failure(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest_path=tmp_path / "missing.yaml"),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )
    summary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=UTC),
        session_window_end=datetime.now(tz=UTC),
    )
    assert summary.repos_captured == 0
    assert summary.entries_inserted == 0


@pytest.mark.asyncio
async def test_capture_never_raises_when_rollback_itself_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G6 contract: if multi_merge raises AND the ROLLBACK raises (e.g.
    broken connection, autocommit surprise), ``capture()`` MUST still
    return a CrossRepoCaptureSummary rather than propagating. Exercises
    the C-Q1 fix that wraps ROLLBACK in its own try/except."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sib_a = tmp_path / "a"
    sib_a.mkdir()
    _git_init(sib_a)
    _commit(sib_a, "feat(a)")
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(
        f"ecosystem:\n  a:\n    path: {sib_a}\n    role: x\n"
    )
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest_path=manifest),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )

    class _FlakyConn:
        """Wraps DuckDBPyConnection; raises on ROLLBACK only.
        Delegates everything else to the real connection."""

        def __init__(self, real: duckdb.DuckDBPyConnection) -> None:
            self._real = real

        def execute(self, sql: str, *args: object, **kwargs: object) -> object:
            if isinstance(sql, str) and "ROLLBACK" in sql.upper():
                raise RuntimeError("simulated rollback failure (broken connection)")
            return self._real.execute(sql, *args, **kwargs)

    flaky_conn = _FlakyConn(conn)
    # Force multi_merge to raise so the merge except-branch is exercised.
    monkeypatch.setattr(accountant._merge, "multi_merge", _explode_multi_merge)
    # Swap the real conn for a flaky one whose ROLLBACK always raises.
    monkeypatch.setattr(accountant, "_conn", flaky_conn)

    # The test PASSES if capture() returns a summary instead of raising.
    summary: CrossRepoCaptureSummary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=UTC),
        session_window_end=datetime.now(tz=UTC),
    )
    assert isinstance(summary, CrossRepoCaptureSummary)
    assert summary.repos_captured == 0
    assert summary.entries_inserted == 0


@pytest.mark.asyncio
async def test_capture_never_raises_on_manifest_read_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G6 contract: manifest.read_text() raising FileNotFoundError /
    PermissionError / IsADirectoryError (TOCTOU between exists() and
    read_text()) MUST NOT propagate. Exercises the C-Q2 fix that
    broadens the YAML load handler to catch OSError."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sib_a = tmp_path / "a"
    sib_a.mkdir()
    _git_init(sib_a)
    _commit(sib_a, "feat(a)")
    manifest = tmp_path / "ecosystem.yaml"
    manifest.write_text(
        f"ecosystem:\n  a:\n    path: {sib_a}\n    role: x\n"
    )
    conn = _setup_db(tmp_path)
    accountant = CheckpointCrossRepoAccountant(
        ambient_puller=AmbientPuller(manifest_path=manifest),
        merge_primitive=MergePrimitive(),
        conn=conn,
    )

    class _ExplodingPath:
        """Minimal Path-like stand-in whose read_text raises OSError.
        exists() returns True so the accountant enters the read branch."""

        def __init__(self, real_name: str) -> None:
            self.name = real_name

        def exists(self) -> bool:
            return True

        def read_text(self, *args: object, **kwargs: object) -> str:
            raise PermissionError("simulated read_text permission error")

    # Patch the accountant module's view of resolve_manifest_path only
    # (the puller still uses its original to load repos successfully).
    import session_buddy.core.checkpoint.cross_repo_accountant as _ca

    monkeypatch.setattr(
        _ca, "resolve_manifest_path",
        lambda _p: _ExplodingPath("ecosystem.yaml"),
    )

    # Should still return a summary rather than propagate.
    summary: CrossRepoCaptureSummary = await accountant.capture(
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=UTC),
        session_window_end=datetime.now(tz=UTC),
    )
    assert isinstance(summary, CrossRepoCaptureSummary)
    assert summary.repos_captured == 1
    assert summary.entries_inserted >= 1
    # Row written, repo_path defaulted to "" (ecosystem couldn't be parsed)
    row = conn.execute(
        "SELECT repo_path FROM cross_repo_work_v2 WHERE conversation_id = ?",
        ["01HXXXXXXXXXXXXXXXXXXXXXXX"],
    ).fetchone()
    assert row is not None
    assert row[0] == ""
