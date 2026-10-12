"""Tests for ``session_buddy.migrations.runner.runner.MigrationRunner``.

Each test materializes a small bundle of synthetic ``*.sql`` files under a
``tmp_path`` so we exercise the full discovery -> execute -> mark pipeline
without depending on the canonical 2026-10-11 bundle. The runner opens a
real (file-backed) DuckDB so the marker + side-effect surface is observed
end-to-end; tests run serially under their own DB file.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from session_buddy.migrations.runner.context import MigrationContext
from session_buddy.migrations.runner.errors import MigrationStepError
from session_buddy.migrations.runner.runner import MigrationRunner, StepResult


# ---------------------------------------------------------------------------
# Test fixtures.
# ---------------------------------------------------------------------------
def _write_bundle(tmp_path: Path, name: str, body: str) -> Path:
    """Write a single ``name.sql`` script under ``tmp_path/bundle``."""
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    (bundle / name).write_text(body, encoding="utf-8")
    return bundle


def _write_pair(
    tmp_path: Path, forward: str, down: str | None = None
) -> Path:
    """Write a forward ``name.sql`` and, optionally, a paired ``name_down.sql``."""
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    (bundle / forward).write_text(
        "CREATE TABLE __demo (id INTEGER); INSERT INTO __demo VALUES (1);",
        encoding="utf-8",
    )
    if down is not None:
        (bundle / down).write_text(
            "DROP TABLE __demo;",
            encoding="utf-8",
        )
    return bundle


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test DuckDB file path. Runner will open it on each verb."""
    return tmp_path / "test.duckdb"


def _ctx(bundle: Path, db_path: Path, **overrides) -> MigrationContext:
    """Build a :class:`MigrationContext` from the common bundle/db pair."""
    return MigrationContext(
        bundle_dir=bundle,
        db_path=db_path,
        dry_run=overrides.get("dry_run", False),
        from_step=overrides.get("from_step"),
        force=overrides.get("force", False),
        json_output=overrides.get("json_output", False),
    )


# ---------------------------------------------------------------------------
# Forward-execution semantics.
# ---------------------------------------------------------------------------
def test_run_executes_all_scripts_in_order_when_db_is_fresh(
    tmp_path: Path, db_path: Path
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "000_init.sql").write_text(
        "CREATE TABLE t1 (id INTEGER); INSERT INTO t1 VALUES (1), (2);",
        encoding="utf-8",
    )
    (bundle / "001_add.sql").write_text(
        "ALTER TABLE t1 ADD COLUMN name VARCHAR; UPDATE t1 SET name = 'a' WHERE id = 1;",
        encoding="utf-8",
    )

    runner = MigrationRunner(_ctx(bundle, db_path))
    results = runner.run()

    assert [r.step for r in results] == ["000_init", "001_add"]
    assert [r.state for r in results] == ["done", "done"]
    assert results[0].rows_affected >= 2  # 2 inserts
    assert results[1].rows_affected >= 1  # 1 update

    # Side effects landed.
    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute("SELECT COUNT(*) FROM t1").fetchone()
        assert rows[0] == 2
        names = conn.execute("SELECT name FROM t1 ORDER BY id").fetchall()
        # id=1 was set to 'a' by the UPDATE; id=2 stays NULL.
        assert names == [("a",), (None,)]
    finally:
        conn.close()


def test_run_skips_already_done_steps_idempotent(tmp_path: Path, db_path: Path) -> None:
    bundle = _write_pair(tmp_path, "001_first.sql", down="001_first_down.sql")

    first = MigrationRunner(_ctx(bundle, db_path))
    results = first.run()
    assert [r.state for r in results] == ["done"]

    # Second invocation: the step must be marked as done already and skipped.
    second = MigrationRunner(_ctx(bundle, db_path))
    again = second.run()
    assert [r.state for r in again] == ["skipped"]


def test_run_force_false_skips_failed_step(tmp_path: Path, db_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "001_bad.sql").write_text(
        "SELECT * FROM table_that_does_not_exist;",
        encoding="utf-8",
    )

    runner = MigrationRunner(_ctx(bundle, db_path))

    with pytest.raises(MigrationStepError):
        runner.run()

    # Second run without --force: the step is in ``failed`` state and
    # should be skipped (claim returns False) rather than re-attempted.
    second = MigrationRunner(_ctx(bundle, db_path))
    results = second.run()
    assert [r.state for r in results] == ["skipped"]


def test_run_force_true_retries_failed_step(tmp_path: Path, db_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    # Synthesize a script that fails the first time and succeeds the second:
    # the second invocation must overwrite the broken view with a valid one.
    (bundle / "001_flaky.sql").write_text(
        "CREATE VIEW flaky AS SELECT * FROM no_such_table;",
        encoding="utf-8",
    )

    runner_first = MigrationRunner(_ctx(bundle, db_path))
    with pytest.raises(MigrationStepError):
        runner_first.run()

    # Repair the script to a non-failing definition.
    (bundle / "001_flaky.sql").write_text(
        "CREATE TABLE recovered (id INTEGER); INSERT INTO recovered VALUES (1);",
        encoding="utf-8",
    )

    runner_retry = MigrationRunner(_ctx(bundle, db_path, force=True))
    results = runner_retry.run()
    assert [r.state for r in results] == ["done"]

    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute("SELECT COUNT(*) FROM recovered").fetchone()
        assert rows[0] == 1
    finally:
        conn.close()


def test_run_dry_run_does_not_write_marker(tmp_path: Path, db_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "001_step.sql").write_text(
        "CREATE TABLE demo (id INTEGER); INSERT INTO demo VALUES (1);",
        encoding="utf-8",
    )

    runner = MigrationRunner(_ctx(bundle, db_path, dry_run=True))
    results = runner.run()

    # Side effects: the script DID run (dry_run only suppresses the
    # marker write). What's tested is the no-marker-write invariant.
    assert [r.state for r in results] == ["done"]

    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM __uuid7_migration_state WHERE step = '001_step' AND state = 'done'"
        ).fetchone()
        assert rows[0] == 0  # marker never recorded
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Rollback semantics.
# ---------------------------------------------------------------------------
def test_rollback_runs_down_scripts_and_marks_rolled_back(
    tmp_path: Path, db_path: Path
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "001_first.sql").write_text(
        "CREATE TABLE t1 (id INTEGER);",
        encoding="utf-8",
    )
    (bundle / "001_first_down.sql").write_text(
        "DROP TABLE t1;",
        encoding="utf-8",
    )
    (bundle / "002_second.sql").write_text(
        "CREATE TABLE t2 (id INTEGER);",
        encoding="utf-8",
    )
    (bundle / "002_second_down.sql").write_text(
        "DROP TABLE t2;",
        encoding="utf-8",
    )

    runner = MigrationRunner(_ctx(bundle, db_path))
    runner.run()  # both done

    rolled = runner.rollback()
    assert rolled == 2

    status = runner.status()
    states = {row["step"]: row["state"] for row in status}
    assert states == {"001_first": "rolled_back", "002_second": "rolled_back"}


def test_rollback_with_from_step_only_rolls_back_suffix(
    tmp_path: Path, db_path: Path
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "001_first.sql").write_text("CREATE TABLE t1 (id INTEGER);", encoding="utf-8")
    (bundle / "001_first_down.sql").write_text("DROP TABLE t1;", encoding="utf-8")
    (bundle / "002_second.sql").write_text("CREATE TABLE t2 (id INTEGER);", encoding="utf-8")
    (bundle / "002_second_down.sql").write_text("DROP TABLE t2;", encoding="utf-8")

    runner = MigrationRunner(_ctx(bundle, db_path))
    runner.run()

    rolled = runner.rollback(from_step="002_second")
    assert rolled == 1  # only 002

    status = runner.status()
    states = {row["step"]: row["state"] for row in status}
    assert states == {"001_first": "done", "002_second": "rolled_back"}


# ---------------------------------------------------------------------------
# Status / reset_stuck.
# ---------------------------------------------------------------------------
def test_status_returns_right_shape(tmp_path: Path, db_path: Path) -> None:
    bundle = _write_pair(tmp_path, "001_only.sql", down="001_only_down.sql")
    runner = MigrationRunner(_ctx(bundle, db_path))
    runner.run()

    rows = runner.status()
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "step",
        "state",
        "started_at",
        "finished_at",
        "rows_affected",
        "error_message",
    }
    assert row["step"] == "001_only"
    assert row["state"] == "done"
    assert row["error_message"] is None


def test_reset_stuck_moves_stuck_rows_to_failed(tmp_path: Path, db_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    bundle = _write_pair(tmp_path, "001_only.sql", down="001_only_down.sql")

    # First run, then manually backdate the started_at to simulate a crash.
    runner = MigrationRunner(_ctx(bundle, db_path))
    runner.run()
    conn = duckdb.connect(str(db_path))
    try:
        old = datetime.now(UTC) - timedelta(hours=2)
        conn.execute(
            "UPDATE __uuid7_migration_state SET started_at = ?, state = 'running' WHERE step = '001_only'",
            [old],
        )
    finally:
        conn.close()

    moved = runner.reset_stuck()
    assert moved == 1

    status = runner.status()
    assert status[0]["state"] == "failed"


# ---------------------------------------------------------------------------
# Script-error path.
# ---------------------------------------------------------------------------
def test_script_syntax_error_marks_failed_and_raises(
    tmp_path: Path, db_path: Path
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "001_broken.sql").write_text(
        "THIS IS NOT VALID SQL; SELECT * FROM;",
        encoding="utf-8",
    )

    runner = MigrationRunner(_ctx(bundle, db_path))
    with pytest.raises(MigrationStepError) as excinfo:
        runner.run()

    err = excinfo.value
    assert err.step == "001_broken"
    assert err.cause is not None

    # Marker store recorded the failure.
    status = runner.status()
    assert len(status) == 1
    assert status[0]["step"] == "001_broken"
    assert status[0]["state"] == "failed"
    assert status[0]["error_message"] is not None


# ---------------------------------------------------------------------------
# from_step filter.
# ---------------------------------------------------------------------------
def test_run_from_step_skips_earlier_scripts(tmp_path: Path, db_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "000_init.sql").write_text(
        "CREATE TABLE init_t (id INTEGER); INSERT INTO init_t VALUES (1);",
        encoding="utf-8",
    )
    (bundle / "001_step_one.sql").write_text(
        "CREATE TABLE one_t (id INTEGER);",
        encoding="utf-8",
    )
    (bundle / "002_step_two.sql").write_text(
        "CREATE TABLE two_t (id INTEGER);",
        encoding="utf-8",
    )

    runner = MigrationRunner(_ctx(bundle, db_path, from_step="001_step_one"))
    results = runner.run()

    assert [r.state for r in results] == ["skipped", "done", "done"]

    conn = duckdb.connect(str(db_path))
    try:
        marker_steps = {
            r[0]
            for r in conn.execute(
                "SELECT step FROM __uuid7_migration_state"
            ).fetchall()
        }
        assert marker_steps == {"001_step_one", "002_step_two"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# StepResult dataclass shape.
# ---------------------------------------------------------------------------
def test_step_result_dataclass_fields() -> None:
    """The :class:`StepResult` dataclass exposes the documented fields."""
    r = StepResult(
        step="001_first",
        state="done",
        rows_affected=5,
        duration_ms=12,
    )
    assert r.step == "001_first"
    assert r.state == "done"
    assert r.rows_affected == 5
    assert r.duration_ms == 12
    assert r.error is None

    r_failed = StepResult(
        step="002_second",
        state="failed",
        rows_affected=0,
        duration_ms=4,
        error="CatalogException: Table not found",
    )
    assert r_failed.error == "CatalogException: Table not found"


# Smoke-test JSON support helpers: just make sure json.dumps accepts the
# returned shapes.
def test_status_json_serializable(tmp_path: Path, db_path: Path) -> None:
    bundle = _write_pair(tmp_path, "001_only.sql", down="001_only_down.sql")
    runner = MigrationRunner(_ctx(bundle, db_path))
    runner.run()

    rows = runner.status()
    payload = json.dumps(rows, default=str)
    parsed = json.loads(payload)
    assert parsed[0]["step"] == "001_only"
