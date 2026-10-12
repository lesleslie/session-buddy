"""Tests for ``session_buddy.migrations.runner.marker.MarkerStore``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from session_buddy.migrations.runner.marker import MarkerStore, StaleRunningError


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    """Fresh in-memory DuckDB connection per test."""
    return duckdb.connect(":memory:")


@pytest.fixture
def store(conn: duckdb.DuckDBPyConnection) -> MarkerStore:
    s = MarkerStore(conn)
    s.ensure_schema()
    return s


def test_ensure_schema_idempotent(conn: duckdb.DuckDBPyConnection) -> None:
    s = MarkerStore(conn)
    s.ensure_schema()
    # second call must not raise
    s.ensure_schema()
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = '__uuid7_migration_state'"
    ).fetchall()
    assert len(rows) == 1


def test_claim_new_step_returns_true(store: MarkerStore) -> None:
    assert store.claim("step1") is True


def test_claim_done_step_returns_false(store: MarkerStore) -> None:
    store.claim("step1")
    store.mark_done("step1", 100)
    assert store.claim("step1") is False


def test_claim_failed_step_without_force_returns_false(store: MarkerStore) -> None:
    store.claim("step1")
    store.mark_failed("step1", "boom")
    assert store.claim("step1") is False


def test_claim_failed_step_with_force_returns_true(store: MarkerStore) -> None:
    store.claim("step1")
    store.mark_failed("step1", "boom")
    assert store.claim("step1", force=True) is True


def test_claim_running_step_raises_stale_running_error(store: MarkerStore) -> None:
    store.claim("step1")
    with pytest.raises(StaleRunningError):
        store.claim("step1")


def test_claim_running_step_raises_with_force_too(store: MarkerStore) -> None:
    """force=True only bypasses the failed-state guard, not the running-state guard."""
    store.claim("step1")
    with pytest.raises(StaleRunningError):
        store.claim("step1", force=True)


def test_mark_done_persists_state(store: MarkerStore) -> None:
    store.claim("step1")
    store.mark_done("step1", 42)
    status = store.status()
    assert len(status) == 1
    row = status[0]
    assert row["step"] == "step1"
    assert row["state"] == "done"
    assert row["rows_affected"] == 42
    assert row["finished_at"] is not None
    assert row["error_message"] is None


def test_mark_failed_persists_state(store: MarkerStore) -> None:
    store.claim("step1")
    store.mark_failed("step1", "kaboom")
    status = store.status()
    assert len(status) == 1
    row = status[0]
    assert row["state"] == "failed"
    assert row["error_message"] == "kaboom"
    assert row["finished_at"] is not None


def test_mark_rolled_back_persists_state(store: MarkerStore) -> None:
    store.claim("step1")
    store.mark_failed("step1", "boom")
    store.mark_rolled_back("step1")
    status = store.status()
    assert len(status) == 1
    row = status[0]
    assert row["state"] == "rolled_back"
    assert row["error_message"] is None
    assert row["finished_at"] is not None


def test_status_returns_all_rows_sorted_by_step(store: MarkerStore) -> None:
    store.claim("step2")
    store.claim("step1")
    store.mark_done("step1", 10)
    status = store.status()
    assert [row["step"] for row in status] == ["step1", "step2"]
    states = {row["step"]: row["state"] for row in status}
    assert states == {"step1": "done", "step2": "running"}


def test_status_empty_when_no_steps(store: MarkerStore) -> None:
    assert store.status() == []


def test_reset_stuck_moves_stale_running_to_failed(
    conn: duckdb.DuckDBPyConnection, store: MarkerStore
) -> None:
    store.claim("step1")
    # Backdate started_at to 2 hours ago — well beyond the 1h default.
    two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
    conn.execute(
        "UPDATE __uuid7_migration_state SET started_at = ? WHERE step = ?",
        [two_hours_ago, "step1"],
    )

    moved = store.reset_stuck(stuck_threshold_seconds=3600)

    assert moved == 1
    status = store.status()
    assert len(status) == 1
    assert status[0]["state"] == "failed"
    assert status[0]["finished_at"] is not None
    assert status[0]["error_message"] is not None


def test_reset_stuck_does_not_touch_fresh_running(
    conn: duckdb.DuckDBPyConnection, store: MarkerStore
) -> None:
    store.claim("step1")
    # Backdate started_at to 10 seconds ago — well within the 1h threshold.
    ten_seconds_ago = datetime.now(UTC) - timedelta(seconds=10)
    conn.execute(
        "UPDATE __uuid7_migration_state SET started_at = ? WHERE step = ?",
        [ten_seconds_ago, "step1"],
    )

    moved = store.reset_stuck(stuck_threshold_seconds=3600)

    assert moved == 0
    status = store.status()
    assert len(status) == 1
    assert status[0]["state"] == "running"


def test_reset_stuck_only_targets_running_state(
    conn: duckdb.DuckDBPyConnection, store: MarkerStore
) -> None:
    """done/failed/rolled_back rows must never be moved, no matter how old."""
    # step1: done, very old
    store.claim("step1")
    store.mark_done("step1", 5)
    old = datetime.now(UTC) - timedelta(days=10)
    conn.execute(
        "UPDATE __uuid7_migration_state SET started_at = ? WHERE step = ?",
        [old, "step1"],
    )

    # step2: failed, very old
    store.claim("step2")
    store.mark_failed("step2", "old failure")
    conn.execute(
        "UPDATE __uuid7_migration_state SET started_at = ? WHERE step = ?",
        [old, "step2"],
    )

    # step3: rolled_back, very old
    store.claim("step3")
    store.mark_rolled_back("step3")
    conn.execute(
        "UPDATE __uuid7_migration_state SET started_at = ? WHERE step = ?",
        [old, "step3"],
    )

    moved = store.reset_stuck(stuck_threshold_seconds=60)

    assert moved == 0
    states = {row["step"]: row["state"] for row in store.status()}
    assert states == {"step1": "done", "step2": "failed", "step3": "rolled_back"}
