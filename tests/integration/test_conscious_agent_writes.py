"""RED test: Conscious Agent write-path instrumentation.

Phase 0c of /Users/les/.claude/plans/zazzy-moseying-pelican.md (lines ~115-122).

The Conscious Agent analyzes access patterns from ``memory_access_log`` to
decide which memories to promote. The plan requires the read path to
write to that table UNCONDITIONALLY (i.e. not gated by any feature flag)
so the analysis loop has data from day one of the rollout.

Three behaviors are pinned here:

1. ``search_conversations`` must write a row to ``memory_access_log``.
2. The write must be unconditional — instrumentation happens even when
   the ``enable_conscious_agent`` feature flag is off. (The flag gates
   only the *background analysis* loop, not the read-path write.)
3. Multi-worker safety: the start-of-process Conscious Agent bootstrap
   must be protected by a fcntl file lock so only one worker per host
   actually starts the background analysis loop.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest


# Note: this module has both async tests (DB-backed) and sync tests
# (lock function). ``asyncio_mode = "auto"`` in ``pyproject.toml``
# runs async tests without an explicit marker, so we deliberately
# do NOT set a module-level ``pytestmark = pytest.mark.asyncio``
# here — that marker would warn on the two sync tests.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_access_rows(db: object) -> int:
    """Return the number of rows in ``memory_access_log``.

    The adapter's DuckDB connection is exposed as ``db.conn``; we read the
    table directly so the assertion does not depend on the adapter
    growing a public accessor.
    """
    row = db.conn.execute("SELECT COUNT(*) FROM memory_access_log").fetchone()  # type: ignore[attr-defined]
    return int(row[0])


def _column_exists(db: object, table: str, column: str) -> bool:
    """Return True if ``table`` has a column named ``column``."""
    rows = db.conn.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_columns() WHERE table_name = ? AND column_name = ?",
        [table, column],
    ).fetchall()
    return len(rows) > 0


# ---------------------------------------------------------------------------
# Test 1 — instrumentation writes to memory_access_log
# ---------------------------------------------------------------------------


async def test_search_writes_to_memory_access_log(
    fast_temp_db: AsyncGenerator,
) -> None:
    """Calling ``search_conversations`` must write a row to ``memory_access_log``."""
    db = fast_temp_db

    # Sanity precondition: log table exists and is empty
    assert _count_access_rows(db) == 0

    # The search query — unique per run so it cannot collide with a cached
    # result from a prior test in the same session.
    query = f"conscious-agent-instrumentation-{uuid.uuid4().hex}"
    await db.search_conversations(query, limit=5)

    # A row was written, and the access_type captures the search action.
    after = _count_access_rows(db)
    assert after == 1, (
        f"Expected exactly 1 row in memory_access_log after one search call, got {after}"
    )

    # The row should record the query text so the Conscious Agent can
    # analyze query patterns. We do not require a memory_id (a search
    # that hits nothing has no memory to point at), but we do require
    # access_type = 'search' and a query_text equal to the input.
    if _column_exists(db, "memory_access_log", "query_text"):
        row = db.conn.execute(  # type: ignore[attr-defined]
            "SELECT access_type, query_text FROM memory_access_log"
        ).fetchone()
        assert row is not None
        access_type, query_text = row[0], row[1]
        assert access_type == "search", f"expected access_type='search', got {access_type!r}"
        assert query_text == query, f"expected query_text={query!r}, got {query_text!r}"


# ---------------------------------------------------------------------------
# Test 2 — instrumentation is UNCONDITIONAL (flag does not gate writes)
# ---------------------------------------------------------------------------


async def test_instrumentation_runs_when_flag_off(
    fast_temp_db: AsyncGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with ``enable_conscious_agent=False``, searches must still log.

    The feature flag gates only the background analysis loop (so we can
    ship the write path to all users before turning the analysis loop
    on). The read path must write unconditionally so the log is populated
    the day the loop turns on.

    The flag lives on :class:`session_buddy.settings.SessionMgmtSettings`,
    not on the adapter's own :class:`ReflectionAdapterSettings`. We
    monkeypatch the global settings singleton so the runtime sees the
    flag as off, then verify the search STILL writes a row.
    """
    db = fast_temp_db

    # Force the global SessionMgmtSettings singleton to report the flag
    # as off. The adapter does not consult this flag today, but we patch
    # it to make the "unconditional" contract observable: if a future
    # change accidentally short-circuits the write on flag=False, this
    # test catches it.
    import session_buddy.settings as _settings_module
    from session_buddy.settings import SessionMgmtSettings

    base = _settings_module._settings or SessionMgmtSettings.load("session-buddy")
    monkeypatch.setattr(base, "enable_conscious_agent", False)
    monkeypatch.setattr(_settings_module, "_settings", base)

    # Sanity check: the flag really is off at the global level.
    from session_buddy.settings import get_settings

    assert get_settings().enable_conscious_agent is False

    query = f"unconditional-instrumentation-{uuid.uuid4().hex}"
    await db.search_conversations(query, limit=5)

    after = _count_access_rows(db)
    assert after == 1, (
        "Instrumentation must be UNCONDITIONAL — a row must be written to "
        f"memory_access_log even when enable_conscious_agent is False (got {after} rows)"
    )


# ---------------------------------------------------------------------------
# Test 3 — multi-worker lock: only one process wins
# ---------------------------------------------------------------------------


def test_multi_worker_only_one_starts_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent calls to ``_start_conscious_agent_with_lock`` -> one True, one False.

    We point the lockfile at a temp directory (instead of ``/tmp``) so the
    test does not race with a real Session-Buddy instance running locally,
    and so the lockfile is cleaned up automatically by pytest's tmp_path
    teardown.
    """
    # Import the function under test — it must exist by name. The import
    # will fail (NameError or ImportError) until the implementation lands.
    from session_buddy.memory.conscious_agent import _start_conscious_agent_with_lock

    lock_path = tmp_path / "test-conscious-agent.lock"

    # Stub ``tempfile.gettempdir`` so the function picks up our tmp_path
    # rather than the real /tmp. (Implementation note: the function builds
    # the lock path as ``Path(tempfile.gettempdir()) / "session-buddy-conscious-agent.lock"``.)
    monkeypatch.setattr(
        "tempfile.gettempdir", lambda: str(tmp_path)
    )

    # Build two fake settings objects with enable_conscious_agent=True so
    # the function actually attempts to acquire the lock. Use SimpleNamespace
    # to avoid coupling the test to the SessionMgmtSettings constructor.
    from types import SimpleNamespace

    settings = SimpleNamespace(enable_conscious_agent=True)

    # First call wins the lock and returns True.
    first = _start_conscious_agent_with_lock(settings)

    # Second call (simulating a second worker that just spawned) is
    # blocked by the fcntl lock and must return False.
    second = _start_conscious_agent_with_lock(settings)

    assert first is True, "First call should win the lock and return True"
    assert second is False, "Second call should be blocked by the lock and return False"

    # The PID of the winning call should be recorded in the lockfile so
    # operators can diagnose which worker owns the agent. The function
    # writes the lockfile at ``<tempdir>/session-buddy-conscious-agent.lock``
    # — we redirected ``tempfile.gettempdir`` to ``tmp_path`` above, so
    # the lockfile lives inside the test's tmp dir.
    lock_path = tmp_path / "session-buddy-conscious-agent.lock"
    assert lock_path.exists(), f"lockfile should exist at {lock_path}"
    pid_text = lock_path.read_text().strip()
    assert pid_text == str(os.getpid()), (
        f"lockfile should record winner pid {os.getpid()}, got {pid_text!r}"
    )


# ---------------------------------------------------------------------------
# Test 3b — disabled flag short-circuits before any filesystem work
# ---------------------------------------------------------------------------


def test_lock_function_short_circuits_when_flag_off(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the flag is off, the function returns False without touching the lockfile."""
    from session_buddy.memory.conscious_agent import _start_conscious_agent_with_lock

    monkeypatch.setattr(
        "tempfile.gettempdir", lambda: str(tmp_path)
    )

    from types import SimpleNamespace

    settings = SimpleNamespace(enable_conscious_agent=False)

    result = _start_conscious_agent_with_lock(settings)

    assert result is False, "Disabled flag should short-circuit to False"
    # No lockfile should have been created
    lock_path = tmp_path / "session-buddy-conscious-agent.lock"
    assert not lock_path.exists(), (
        f"Disabled flag should not create a lockfile at {lock_path}"
    )
