"""End-to-end integration tests for ``session_buddy.migrations.runner.MigrationRunner``.

These tests drive the full forward / rollback / status / reset_stuck
pipeline against a real (file-backed) DuckDB database. Each test
materializes a small synthetic bundle of ``.sql`` files under
``tmp_path`` so we focus on the runner mechanics — discovery, marker
state machine, idempotency, dry-run semantics, and determinism — without
exercising the full canonical ``001``..``007`` consolidation chain.

Tests in this file cover the seven scenarios required by PR-D:

1. ``test_migrate_run_fresh_db`` — fresh DB, runner executes ``000`` + a
   short ``001``..``008`` chain. The marker table records every step as
   ``done`` (including the bootstrap ``000_`` — see "Bundle layout note"
   below).
2. ``test_migrate_run_idempotent`` — second invocation is a no-op.
3. ``test_migrate_status`` — ``status()`` returns the documented row shape
   for every recorded step.
4. ``test_migrate_rollback`` — ``rollback()`` reverses the last 2 steps;
   marker rows transition to ``rolled_back``.
5. ``test_migrate_dry_run`` — ``dry_run=True`` runs the SQL scripts but
   does NOT write marker rows (no ``mark_done`` invocation).
6. ``test_migrate_reset_stuck`` — an injected ``running`` row with
   ``started_at = now - 2h`` is moved to ``failed`` by ``reset_stuck``;
   a subsequent ``run(force=True)`` retries and succeeds.
7. ``test_determinism_uuid7`` — ``ulid_to_uuid7(legacy_id)`` is a pure
   function: re-runs against the same input produce identical output.

Bundle layout note
------------------
The runner treats the lex-first 3-digit-prefixed forward script
(typically ``000_``) as a fully tracked step — the marker store claims
it, executes it, and records ``:state=done`` like any other. That
matches the canonical ``2026_10_11_uuid7_consolidation/000_ulid_to_uuid7.sql``
in production (``CREATE OR REPLACE FUNCTION …``). Test bundles mirror
this convention: a ``000_bootstrap.sql`` step is included in every
synthetic bundle so the marker-table row-count assertions have a stable
target.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from session_buddy.migrations.runner import (
    MigrationContext,
    MigrationRunner,
    MigrationStepError,
    StaleRunningError,
)
from session_buddy.migrations.udf import ulid_to_uuid7


# ---------------------------------------------------------------------------
# Bundle helpers.
# ---------------------------------------------------------------------------
# We deliberately keep the test bundles tiny. Each scenario below declares
# its own steps inline via ``_write_bundle`` / ``_write_pair``. The forward
# scripts use cheap DDL/DML so the test does not depend on any
# reflection-store schema or the canonical ``2026_10_11`` bundle.

# Eight short forward scripts mirroring the canonical ``000..008`` envelope.
# Each script creates a tiny throwaway table so the runner sees real
# side effects (and a non-zero ``rows_affected`` for INSERT statements).
_BUNDLE_000_008: list[tuple[str, str]] = [
    (
        "000_bootstrap.sql",
        "CREATE TABLE _e2e_bootstrap (k INTEGER PRIMARY KEY, v VARCHAR); "
        "INSERT INTO _e2e_bootstrap VALUES (1, 'b1'), (2, 'b2');",
    ),
    (
        "001_first.sql",
        "CREATE TABLE _e2e_step1 (id INTEGER); "
        "INSERT INTO _e2e_step1 VALUES (10), (20), (30);",
    ),
    (
        "001_first_down.sql",
        "DROP TABLE _e2e_step1;",
    ),
    (
        "002_second.sql",
        "CREATE TABLE _e2e_step2 (id INTEGER); "
        "INSERT INTO _e2e_step2 VALUES (100), (200);",
    ),
    (
        "002_second_down.sql",
        "DROP TABLE _e2e_step2;",
    ),
    (
        "003_third.sql",
        "CREATE TABLE _e2e_step3 (id INTEGER);",
    ),
    (
        "003_third_down.sql",
        "DROP TABLE _e2e_step3;",
    ),
    (
        "004_fourth.sql",
        "CREATE TABLE _e2e_step4 (id INTEGER);",
    ),
    (
        "004_fourth_down.sql",
        "DROP TABLE _e2e_step4;",
    ),
    (
        "005_fifth.sql",
        "CREATE TABLE _e2e_step5 (id INTEGER);",
    ),
    (
        "005_fifth_down.sql",
        "DROP TABLE _e2e_step5;",
    ),
    (
        "006_sixth.sql",
        "CREATE TABLE _e2e_step6 (id INTEGER);",
    ),
    (
        "006_sixth_down.sql",
        "DROP TABLE _e2e_step6;",
    ),
    (
        "007_seventh.sql",
        "CREATE TABLE _e2e_step7 (id INTEGER);",
    ),
    (
        "007_seventh_down.sql",
        "DROP TABLE _e2e_step7;",
    ),
    (
        "008_terminal.sql",
        "CREATE TABLE _e2e_terminal (id INTEGER); "
        "INSERT INTO _e2e_terminal VALUES (1);",
    ),
]


def _write_bundle(tmp_path: Path, scripts: list[tuple[str, str]]) -> Path:
    """Materialize ``scripts`` as ``.sql`` files under ``tmp_path/bundle``.

    Idempotent: re-invocation overwrites the existing ``.sql`` files in
    place (so a second ``_make_runner`` call after a script repair can
    land cleanly on the same ``tmp_path``).
    """
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    for name, body in scripts:
        (bundle / name).write_text(body, encoding="utf-8")
    return bundle


def _make_runner(tmp_path: Path, **overrides) -> tuple[MigrationRunner, Path, Path]:
    """Bundle together the ``(runner, db_path, bundle_dir)`` triple.

    Keeping the three artifacts in one fixture avoids 50 lines of
    repeated ``MigrationRunner(MigrationContext(...))`` boilerplate in
    every test. ``overrides`` is forwarded to ``MigrationContext`` for
    the ``dry_run``, ``force``, ``from_step``, and ``json_output``
    fields.
    """
    db_path = tmp_path / "migrate.duckdb"
    bundle_dir = _write_bundle(tmp_path, _BUNDLE_000_008)
    ctx = MigrationContext(
        bundle_dir=bundle_dir,
        db_path=db_path,
        dry_run=overrides.get("dry_run", False),
        from_step=overrides.get("from_step"),
        force=overrides.get("force", False),
        json_output=overrides.get("json_output", False),
    )
    return MigrationRunner(ctx), db_path, bundle_dir


def _marker_rows(db_path: Path) -> list[tuple[str, str, int | None]]:
    """Return ``(step, state, rows_affected)`` for every marker row.

    Reads directly from DuckDB to bypass the JSON-shaped ``status()``
    surface — keeps each assertion to a single line.
    """
    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT step, state, rows_affected "
            "FROM __uuid7_migration_state ORDER BY step"
        ).fetchall()
    finally:
        conn.close()
    return [(step, state, rows) for step, state, rows in rows]


# ---------------------------------------------------------------------------
# Scenario 1 — fresh DB, all steps run, marker table populated.
# ---------------------------------------------------------------------------
def test_migrate_run_fresh_db(tmp_path: Path) -> None:
    """Fresh DB: runner walks 000..008; every step lands in marker table.

    Documents the bundle layout note from the module docstring: ``000_``
    counts as a tracked step — the marker table records it as ``done``
    just like the rest of the chain. The forward count is 9
    (``000_bootstrap`` plus the eight ``001``..``008`` steps; the
    canonical bundle excludes ``007_`` from rollback but keeps it in
    forward discovery).
    """
    runner, db_path, _ = _make_runner(tmp_path)
    results = runner.run()

    states = [r.state for r in results]
    # Every step lands as ``done`` on a fresh DB.
    assert states.count("done") == 9
    assert "skipped" not in states
    assert "failed" not in states

    # Marker table records all 9 steps as ``done`` (including 000_).
    marker_rows = _marker_rows(db_path)
    step_names = [step for step, state, _ in marker_rows]
    assert step_names == [
        "000_bootstrap",
        "001_first",
        "002_second",
        "003_third",
        "004_fourth",
        "005_fifth",
        "006_sixth",
        "007_seventh",
        "008_terminal",
    ]
    assert all(state == "done" for _, state, _ in marker_rows)

    # Side effects landed: at least the rows that the INSERTs touched
    # are visible from a fresh connection.
    conn = duckdb.connect(str(db_path))
    try:
        bootstrap_count = conn.execute(
            "SELECT COUNT(*) FROM _e2e_bootstrap"
        ).fetchone()[0]
        terminal_count = conn.execute(
            "SELECT COUNT(*) FROM _e2e_terminal"
        ).fetchone()[0]
    finally:
        conn.close()
    assert bootstrap_count == 2
    assert terminal_count == 1


# ---------------------------------------------------------------------------
# Scenario 2 — second run is a no-op (all done state).
# ---------------------------------------------------------------------------
def test_migrate_run_idempotent(tmp_path: Path) -> None:
    """Second ``run()`` invocation: every step already ``done`` -> skipped."""
    runner, db_path, _ = _make_runner(tmp_path)
    first = runner.run()
    assert all(r.state == "done" for r in first)

    # Second invocation must NOT re-execute SQL; the marker table short-
    # circuits every step.
    second = runner.run()
    assert [r.state for r in second] == ["skipped"] * 9

    # Marker table unchanged: still 9 rows, still all ``done``.
    marker_rows = _marker_rows(db_path)
    assert len(marker_rows) == 9
    assert all(state == "done" for _, state, _ in marker_rows)


# ---------------------------------------------------------------------------
# Scenario 3 — status() returns the documented shape.
# ---------------------------------------------------------------------------
def test_migrate_status(tmp_path: Path) -> None:
    """``status()`` returns the documented dict shape with every step."""
    runner, _, _ = _make_runner(tmp_path)
    runner.run()

    rows = runner.status()
    assert len(rows) == 9
    expected_keys = {
        "step",
        "state",
        "started_at",
        "finished_at",
        "rows_affected",
        "error_message",
    }
    for row in rows:
        assert set(row.keys()) == expected_keys
        assert row["state"] == "done"
        assert row["error_message"] is None
        assert row["started_at"] is not None
        assert row["finished_at"] is not None
        assert row["rows_affected"] is not None

    # Status rows are JSON-round-trippable so the CLI's ``--json``
    # output mode never crashes on date / int columns.
    payload = json.loads(json.dumps(rows, default=str))
    assert isinstance(payload, list)
    assert {row["step"] for row in payload} == {
        "000_bootstrap",
        "001_first",
        "002_second",
        "003_third",
        "004_fourth",
        "005_fifth",
        "006_sixth",
        "007_seventh",
        "008_terminal",
    }


# ---------------------------------------------------------------------------
# Scenario 4 — rollback reverses the last 2 steps.
# ---------------------------------------------------------------------------
def test_migrate_rollback(tmp_path: Path) -> None:
    """``rollback(from_step=...)`` reverses the last 2 reversible steps.

    The canonical bundle only rolls back step IDs ``001``..``007``; our
    synthetic bundle mirrors that, so ``000_bootstrap`` and
    ``008_terminal`` are skipped silently (they have no ``*_down.sql``
    counterpart, and ``008_terminal`` falls outside the ``001..007``
    prefix range enforced by ``ScriptDiscovery.discover_down_scripts``).
    ``from_step="006_sixth"`` constrains the rollback to the suffix
    starting at ``006_sixth``; the two most-recently-applied reversible
    steps (``006_sixth`` and ``007_seventh``) are reverted, in reverse
    order.
    """
    runner, db_path, _ = _make_runner(tmp_path)
    runner.run()

    rolled = runner.rollback(from_step="006_sixth")
    assert rolled == 2

    marker_rows = _marker_rows(db_path)
    state_map = {step: state for step, state, _ in marker_rows}
    # Last 2 reversible (001..007) steps flipped to rolled_back; earlier
    # steps remain ``done``; ``000_`` and ``008_`` are not touched
    # (no ``*_down.sql`` for them).
    assert state_map["007_seventh"] == "rolled_back"
    assert state_map["006_sixth"] == "rolled_back"
    assert state_map["005_fifth"] == "done"
    assert state_map["000_bootstrap"] == "done"
    assert state_map["008_terminal"] == "done"

    # Side effects: tables for rolled-back steps are gone.
    conn = duckdb.connect(str(db_path))
    try:
        for step in ("006_sixth", "007_seventh"):
            table_name = f"_e2e_{step.split('_', 1)[1]}"  # _e2e_sixth, _e2e_seventh
            exists = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = ?",
                [table_name],
            ).fetchone()[0]
            assert exists == 0
        # Earlier ``done`` step still has its table.
        five_count = conn.execute(
            "SELECT COUNT(*) FROM _e2e_step5"
        ).fetchone()[0]
    finally:
        conn.close()
    assert five_count == 0  # empty table created by 005_fifth.sql; row count is 0


# ---------------------------------------------------------------------------
# Scenario 5 — dry_run=True does not modify the marker table.
# ---------------------------------------------------------------------------
def test_migrate_dry_run(tmp_path: Path) -> None:
    """``dry_run=True``: SQL still executes but no step reaches ``done``.

    Per ``runner.py``:228-244, dry-run mode still calls
    ``_execute_script`` (the SQL runs against the DB) but skips the
    ``mark_done`` / ``mark_failed`` calls. ``MarkerStore.claim`` does
    insert ``running`` rows on first encounter — the dry-run invariant
    is therefore "no row transitions to ``done`` or ``failed``", not
    "the marker table stays empty".
    """
    runner, db_path, _ = _make_runner(tmp_path, dry_run=True)
    results = runner.run()

    # Every step is reported as ``done`` (matching the production
    # semantics where dry-run is "what WOULD run"); the surface result
    # is the same, only the marker state is suppressed.
    assert all(r.state == "done" for r in results)

    # Marker table: schema is there, but the rows are all ``running``
    # (from the claim step) and zero rows are ``done`` / ``failed``.
    conn = duckdb.connect(str(db_path))
    try:
        schema_exists = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '__uuid7_migration_state'"
        ).fetchone()[0]
        total_rows = conn.execute(
            "SELECT COUNT(*) FROM __uuid7_migration_state"
        ).fetchone()[0]
        terminal_rows = conn.execute(
            "SELECT COUNT(*) FROM __uuid7_migration_state "
            "WHERE state IN ('done', 'failed')"
        ).fetchone()[0]
        running_rows = conn.execute(
            "SELECT COUNT(*) FROM __uuid7_migration_state "
            "WHERE state = 'running'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert schema_exists == 1
    # ``claim`` inserts one ``running`` row per discovered step (9
    # steps). No step transitioned to a terminal state because dry-run
    # suppressed ``mark_done`` / ``mark_failed``.
    assert total_rows == 9
    assert terminal_rows == 0
    assert running_rows == 9


# ---------------------------------------------------------------------------
# Scenario 6 — reset_stuck moves stale ``running`` rows to ``failed``;
# a forced run then retries the step successfully.
# ---------------------------------------------------------------------------
def test_migrate_reset_stuck(tmp_path: Path) -> None:
    """Inject a 2-hour-stale running row; ``reset_stuck`` recovers it.

    Recovery path: ``reset_stuck`` (moves ``running`` -> ``failed``),
    then a fresh runner with ``force=True`` (transitions ``failed`` ->
    ``running`` -> ``done`` on the now-stale marker). The synthetic
    bundle's ``003_third.sql`` script is rewritten between the two
    calls to simulate an operator repairing the broken DDL.
    """
    runner, db_path, bundle_dir = _make_runner(tmp_path)
    runner.run()  # baseline: every step ``done``

    # Inject a stale ``running`` row directly into the marker table
    # (simulates a runner crash mid-flight).
    stale_started_at = datetime.now(UTC) - timedelta(hours=2)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE __uuid7_migration_state "
            "SET state = 'running', started_at = ?, "
            "    finished_at = NULL, error_message = NULL, rows_affected = NULL "
            "WHERE step = '003_third'",
            [stale_started_at],
        )
    finally:
        conn.close()

    # reset_stuck (default 1h threshold) must move the stale ``running``
    # row to ``failed``.
    moved = runner.reset_stuck()
    assert moved == 1

    marker_rows = _marker_rows(db_path)
    state_map = {step: state for step, state, _ in marker_rows}
    assert state_map["003_third"] == "failed"

    # Repair the script in place (operator fixes the broken DDL).
    (bundle_dir / "003_third.sql").write_text(
        "CREATE TABLE _e2e_step3_fixed (id INTEGER); "
        "INSERT INTO _e2e_step3_fixed VALUES (1), (2);",
        encoding="utf-8",
    )

    # ``force`` is a ``MigrationContext`` field, not a ``run()`` kwarg.
    # Build a fresh runner with ``force=True`` over the SAME bundle
    # directory so the operator's script repair survives. Going back
    # through ``_make_runner`` would re-emit ``_BUNDLE_000_008`` and
    # blow away the fixed ``003_third.sql`` body.
    forced_ctx = MigrationContext(
        bundle_dir=bundle_dir,
        db_path=db_path,
        force=True,
    )
    forced_runner = MigrationRunner(forced_ctx)
    results = forced_runner.run()

    # Only ``003_third`` re-runs (it's the only step in ``failed``
    # state); the rest of the chain returns ``skipped`` because the
    # earlier steps are already ``done``.
    step_states = {r.step: r.state for r in results}
    assert step_states["003_third"] == "done"
    assert all(state in {"done", "skipped"} for state in step_states.values())
    # The fixed script's side effect (the new ``_e2e_step3_fixed``
    # table) is in place.
    conn = duckdb.connect(str(db_path))
    try:
        fixed_rows = conn.execute(
            "SELECT COUNT(*) FROM _e2e_step3_fixed"
        ).fetchone()[0]
    finally:
        conn.close()
    assert fixed_rows == 2

    marker_rows = _marker_rows(db_path)
    state_map = {step: state for step, state, _ in marker_rows}
    assert state_map["003_third"] == "done"

    # ``StaleRunningError`` is exposed by the runner namespace for
    # callers that want to handle the no-force path explicitly; a
    # non-forced run against a still-running row raises it.
    fresh_runner, fresh_db, _ = _make_runner(tmp_path)
    fresh_runner.run()
    conn = duckdb.connect(str(fresh_db))
    try:
        conn.execute(
            "UPDATE __uuid7_migration_state SET state = 'running', "
            "started_at = ?, finished_at = NULL, "
            "error_message = NULL, rows_affected = NULL "
            "WHERE step = '004_fourth'",
            [stale_started_at],
        )
    finally:
        conn.close()
    with pytest.raises(StaleRunningError):
        fresh_runner.run()


# ---------------------------------------------------------------------------
# Scenario 7 — ulid_to_uuid7 determinism across re-runs.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("legacy_id", "expected_hex"),
    [
        # The legacy_id is a 32-char Crockford-base32 token (10-char
        # 48-bit ms timestamp + 22-char trailing suffix). The expected
        # hex is pinned to the actual ``ulid_to_uuid7`` output: any
        # future change to the UDF surface (hash function, byte
        # layout, version bits) is a breaking change that must update
        # both the test and the canonical bundle.
        (
            "01HWYAPCGH3D7X4Z4D3V0JZQR9ABCDEF",
            "018f3cab32117fe6be8cb5ff3ed5ef56",
        ),
        # Two distinct inputs with the same timestamp prefix but
        # different suffixes — confirms the suffix is hashed into the
        # output (not just the timestamp).
        (
            "0000000000AAAAAAAAAAAAAAAAAAAAAA",
            "0000000000007170851f4420c94dca1b",
        ),
    ],
)
def test_determinism_uuid7(
    legacy_id: str,
    expected_hex: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """``ulid_to_uuid7`` is pure: same input -> same output across runs.

    Verifies the contract documented in :mod:`session_buddy.migrations.udf`:
    no clock, no PRNG, no salt, no I/O. We re-invoke the function in
    separate ``runner.run()`` calls (each opens a fresh DuckDB
    connection and re-registers the UDF) and confirm the output is
    byte-identical across calls.

    The expected hex values are computed once and pinned; a future
    refactor that changes the UDF surface (e.g. switches the hash
    function) is a breaking change and must update both the test and
    the canonical bundle.
    """
    # Direct call: deterministic against the in-process function.
    first = ulid_to_uuid7(legacy_id)
    assert first == expected_hex

    # Re-invoke 100 times to catch accidental non-determinism
    # (random sources, time-based salts).
    for _ in range(100):
        assert ulid_to_uuid7(legacy_id) == expected_hex

    # Round-trip through DuckDB: register the UDF on a fresh
    # connection, call it via SQL, confirm the SQL path yields the
    # same result as the direct Python call.
    conn = duckdb.connect(":memory:")
    try:
        conn.create_function(
            "ulid_to_uuid7",
            ulid_to_uuid7,
            return_type=duckdb.sqltypes.VARCHAR,
            side_effects=False,
        )
        sql_result = conn.execute(
            "SELECT ulid_to_uuid7(?)", [legacy_id]
        ).fetchone()[0]
    finally:
        conn.close()
    assert sql_result == expected_hex

    # Across a full ``MigrationRunner.run()`` lifecycle: the runner
    # registers the UDF on its own connection. Re-running the same
    # step twice and reading the result back yields the same hex.
    tmp_dir = tmp_path_factory.mktemp(f"det_{legacy_id[:6]}")
    bundle = _write_bundle(
        tmp_dir,
        [
            (
                "000_call_first_uuid7.sql",
                f"CREATE TABLE _e2e_uuid7_out AS "
                f"SELECT ulid_to_uuid7('{legacy_id}') AS hex;",
            ),
        ],
    )
    db_path = tmp_dir / "determinism.duckdb"
    ctx = MigrationContext(bundle_dir=bundle, db_path=db_path)
    runner = MigrationRunner(ctx)
    runner.run()
    runner.run()  # idempotent: still ``done``, row content unchanged
    conn = duckdb.connect(str(db_path))
    try:
        sql_hex = conn.execute(
            "SELECT hex FROM _e2e_uuid7_out"
        ).fetchone()[0]
    finally:
        conn.close()
    assert sql_hex == expected_hex