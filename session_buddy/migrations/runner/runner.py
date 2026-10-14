"""MigrationRunner — orchestrates forward / status / rollback for the
UUID7 consolidation bundle.

The runner is the single owner of the DuckDB connection lifecycle for the
``migrate`` CLI subcommand group. ``run`` opens a read-write connection,
registers ``ulid_to_uuid7`` as a Python-backed DuckDB UDF (side_effects=False,
since the function is pure), ensures the marker schema is in place, then
walks the lexicographically-discovered forward scripts in order. Each step
is funneled through the :class:`MarkerStore` claim / done / failed state
machine; errors are wrapped in :class:`MigrationStepError` so the CLI can
emit structured output.

``status`` and ``reset_stuck`` delegate to the marker store directly.
``rollback`` walks down-scripts in reverse order, marking each step as
``rolled_back`` as it goes.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import duckdb
import duckdb.sqltypes  # imported for side effects on duckdb namespace
from oneiric.core.logging import get_logger

from session_buddy.migrations.runner.context import MigrationContext
from session_buddy.migrations.runner.discovery import ScriptDiscovery
from session_buddy.migrations.runner.errors import MigrationStepError
from session_buddy.migrations.runner.marker import MarkerStore
from session_buddy.migrations.udf import ulid_to_uuid7

logger = get_logger(__name__)


@dataclass
class StepResult:
    """Outcome of a single forward step.

    Attributes:
        step: The script name (e.g. ``003_consolidate_reflections``).
        state: Terminal state — ``done``, ``failed``, ``skipped``, or
            ``rolled_back``. ``skipped`` is used when the step is
            already-done (idempotent skip) or when ``from_step`` excludes
            it.
        rows_affected: For ``done`` steps, the total row-count touched by
            the script (sum of the DuckDB ``Count`` pseudo-column across
            every DML statement). For ``skipped`` / ``failed`` steps it
            is 0.
        duration_ms: Wall-clock duration of the step in milliseconds
            (rounded to int).
        error: Populated only on ``state == "failed"``. Holds the
            human-readable error message; the full exception lives on
            :class:`MigrationStepError.cause`.
    """

    step: str
    state: str
    rows_affected: int
    duration_ms: int
    error: str | None = None


_STEP_ID_RE = re.compile(r"^(\d{3})_")


def _step_id_from_stem(stem: str) -> str:
    """Extract the 3-digit step ID from a forward-script stem.

    Canonical bundle: ``001_consolidate_conversations`` -> ``001``. The
    regex catches ``000`` and any other 3-digit numeric prefix; for
    non-numeric stems (synthetic test bundles) the full stem is returned
    as the step identifier.
    """
    match = _STEP_ID_RE.match(stem)
    return match.group(1) if match else stem


def _extract_rows_affected(result: Any) -> int:
    """Return the row-count touched by a DuckDB DML/SELECT statement.

    DuckDB exposes a synthetic ``Count`` pseudo-column on DDL/DML
    results; a single-row ``[(N,)]`` payload is the conventional retrieval
    path. For SELECTs the runner walks ``fetchall`` and counts rows.

    Returns 0 when the result is empty, ``None`` (DuckDB returns
    ``None`` for comment-only statements that hit no DDL/DML path),
    or otherwise unreachable.
    """
    if result is None:
        return 0
    if result.description is None:
        return 0
    if len(result.description) == 1 and result.description[0][0] == "Count":
        row = result.fetchone()
        return int(row[0]) if row else 0
    rows = result.fetchall()
    return len(rows)


def _strip_sql_comments(sql: str) -> str:
    """Remove ``-- ...`` line comments before semicolon-splitting.

    The canonical bundle's script headers embed semicolons inside multi-line
    ``-- comment`` prose (e.g. ``-- Marker handling: the
    ``__uuid7_migration_done`` marker table is the ...``). A naive
    ``script_sql.split(';')`` would split on those embedded semicolons,
    producing fragments like ``-- Marker handling: the
    ``__uuid7_migration_done`` marker table is the`` that are not valid
    SQL on their own. Stripping comments first preserves the original
    statement boundaries.
    """
    lines = []
    for line in sql.splitlines():
        # Strip trailing ``-- ...`` only when it appears outside a string
        # literal. The canonical bundle does not embed ``--`` inside a
        # string literal, so a flat ``split('--', 1)`` is safe.
        stripped = line.split("--", 1)[0]
        lines.append(stripped)
    return "\n".join(lines)


def _execute_script(conn: duckdb.DuckDBPyConnection, script_sql: str) -> int:
    """Execute a single SQL script, summing rows touched across statements.

    The script has its ``--`` line comments stripped (so semicolons in
    comment prose do not fragment the SQL), then is split on remaining
    semicolons. Each statement is executed independently so a failure
    on statement N is attributed to that statement; the row-count is the
    sum of ``Count`` pseudo-column reads across DML statements and the
    row count of any final SELECT.

    Returns:
        Total rows touched by the script.
    """
    stripped_sql = _strip_sql_comments(script_sql)
    statements = [s.strip() for s in stripped_sql.split(";") if s.strip()]
    total = 0
    for stmt in statements:
        result = conn.execute(stmt)
        total += _extract_rows_affected(result)
    return total


class MigrationRunner:
    """Drives the UUID7 consolidation bundle end-to-end.

    The runner opens its own DuckDB connection per public method so each
    CLI invocation sees a clean transaction scope; this also means
    concurrent ``run`` / ``status`` calls are safe (DuckDB file-level
    write lock blocks the second writer until the first finishes).
    """

    def __init__(self, ctx: MigrationContext) -> None:
        self._ctx = ctx
        self._discovery = ScriptDiscovery(ctx.bundle_dir)
        self._marker: MarkerStore | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle.
    # ------------------------------------------------------------------
    def _open(self) -> duckdb.DuckDBPyConnection:
        """Open a read-write connection and register the UDFs on it.

        Two UDFs are registered per-connection (DuckDB UDFs are not
        persisted across sessions):

        * ``ulid_to_uuid7(ulid_text)`` — deterministic converter used by 007
          to translate legacy ULIDs into canonical UUID7 hex. Pure
          (``side_effects=False``).
        * ``uuid7()`` — non-deterministic helper used by 003 to absorb
          ``default_reflections`` rows that need a fresh UUID7 (their
          legacy ids are non-PK-shaped). Returns a 32-char lowercase hex
          UUID7 from ``uuid.uuid7().hex``.

        The ``uuid7()`` UDF does NOT have ``side_effects=False`` because
        it relies on the system clock + OS RNG. DuckDB will not cache
        repeated calls with the same args (which is what we want — every
        absorbed row needs a distinct id).
        """
        conn = duckdb.connect(str(self._ctx.db_path))
        try:
            # ``side_effects=False`` documents the purity. ``return_type`` is
            # pinned to VARCHAR per the ulid_to_uuid7 contract.
            conn.create_function(
                "ulid_to_uuid7",
                ulid_to_uuid7,
                return_type=duckdb.sqltypes.VARCHAR,
                side_effects=False,
            )
        except duckdb.Error as exc:
            # Restricted context (e.g. read-only DB, sandboxed connection):
            # log and continue. The forward scripts that depend on the UDF
            # (003, 007) will fail loudly at execution time if they
            # actually need it; the ``status`` / ``reset-stuck`` /
            # non-UDF rollback paths do not.
            logger.warning("could not register ulid_to_uuid7 UDF: %s", exc)
        try:
            # Zero-arg UUID7 generator for ``default_reflections`` absorb
            # (default_reflections rows get fresh UUID7s, not derived
            # from their legacy ids). ``side_effects=True`` is REQUIRED:
            # the default is False, which lets DuckDB cache the function
            # result and reuse it for every row of a vectorized SELECT,
            # causing every absorbed row to share the same UUID7 PK and
            # fail the PK uniqueness constraint.
            conn.create_function(
                "uuid7",
                lambda: uuid.uuid7().hex,
                return_type=duckdb.sqltypes.VARCHAR,
                side_effects=True,
            )
        except duckdb.Error as exc:
            logger.warning("could not register uuid7 UDF: %s", exc)
        self._marker = MarkerStore(conn)
        self._marker.ensure_schema()
        return conn

    # ------------------------------------------------------------------
    # Public API.
    # ------------------------------------------------------------------
    def run(self) -> list[StepResult]:
        """Apply every discovered script in lex order.

        Returns:
            One :class:`StepResult` per discovered script. ``done`` means
            the script ran and committed; ``skipped`` means the marker
            store already recorded the step as ``done`` (or the step is
            before ``from_step``); ``failed`` means the script raised.

        Raises:
            MigrationStepError: When a script raises during execution.
                The marker is left in the ``failed`` state; retry with
                ``force=True``.
            StaleRunningError: Re-raised from the marker store when a
                step is currently ``running``. Caller must invoke
                :meth:`reset_stuck` followed by ``run(force=True)``.
        """
        if self._ctx.dry_run:
            logger.info(
                "dry_run: opening %s to count discoverable steps", self._ctx.db_path
            )

        scripts = self._discovery.discover_scripts()
        results: list[StepResult] = []

        # ``from_step`` filtering: scripts whose stem < ``from_step`` are
        # skipped silently; ``from_step`` itself and later scripts run.
        from_step: str | None = self._ctx.from_step
        from_step_idx: int | None = None
        if from_step is not None:
            for idx, path in enumerate(scripts):
                if path.stem == from_step:
                    from_step_idx = idx
                    break
            if from_step_idx is None:
                logger.warning(
                    "from_step %r did not match any discovered script; "
                    "running all steps",
                    from_step,
                )
                from_step_idx = 0

        conn = self._open()
        assert self._marker is not None  # _open() always sets _marker
        marker = self._marker
        try:
            for idx, script_path in enumerate(scripts):
                step_name = script_path.stem
                if from_step_idx is not None and idx < from_step_idx:
                    results.append(
                        StepResult(
                            step=step_name,
                            state="skipped",
                            rows_affected=0,
                            duration_ms=0,
                        )
                    )
                    continue

                claim_result = marker.claim(step_name, force=self._ctx.force)
                if not claim_result:
                    logger.info(
                        "step %r already done or (without force) failed; skipping",
                        step_name,
                    )
                    results.append(
                        StepResult(
                            step=step_name,
                            state="skipped",
                            rows_affected=0,
                            duration_ms=0,
                        )
                    )
                    continue

                sql_text = script_path.read_text(encoding="utf-8")
                started = time.monotonic()
                if self._ctx.dry_run:
                    logger.info(
                        "dry_run: would execute step %r (%d bytes)",
                        step_name,
                        len(sql_text),
                    )
                    rows_affected = 0
                else:
                    try:
                        rows_affected = _execute_script(conn, sql_text)
                    except Exception as exc:
                        duration_ms = int((time.monotonic() - started) * 1000)
                        err_msg = f"{type(exc).__name__}: {exc}"
                        try:
                            marker.mark_failed(step_name, err_msg)
                        except Exception:
                            logger.exception(
                                "failed to persist failed state for %r",
                                step_name,
                            )
                        results.append(
                            StepResult(
                                step=step_name,
                                state="failed",
                                rows_affected=0,
                                duration_ms=duration_ms,
                                error=err_msg,
                            )
                        )
                        raise MigrationStepError(step_name, exc) from exc

                duration_ms = int((time.monotonic() - started) * 1000)
                if not self._ctx.dry_run:
                    marker.mark_done(step_name, rows_affected)
                results.append(
                    StepResult(
                        step=step_name,
                        state="done",
                        rows_affected=rows_affected,
                        duration_ms=duration_ms,
                    )
                )
                step_id = _step_id_from_stem(step_name)
                logger.info(
                    "migration.%s.rows_affected: %d",
                    step_id,
                    rows_affected,
                )
                logger.info(
                    "step %r done (%d rows, %d ms)",
                    step_name,
                    rows_affected,
                    duration_ms,
                )
        finally:
            conn.close()

        return results

    def status(self) -> list[dict]:
        """Return the migration marker table as a list of dicts.

        Delegates directly to :meth:`MarkerStore.status`. Opens a
        read-write connection (``duckdb.connect`` defaults to RW even when
        only reads happen) so the same call works against any DB file
        that has the marker schema.
        """
        conn = self._open()
        assert self._marker is not None  # _open() always sets _marker
        marker = self._marker
        try:
            return marker.status()
        finally:
            conn.close()

    def rollback(self, from_step: str | None = None) -> int:
        """Run the matching ``*_down.sql`` for every done step, in reverse.

        Args:
            from_step: Optional stop-bound — only the suffix starting at
                ``from_step`` is rolled back. ``from_step`` itself is also
                rolled back. ``None`` rolls back every reversible step
                whose ``NNN_*_down.sql`` exists in the bundle.

        Returns:
            Number of steps successfully rolled back.

        Notes:
            The ``discover_down_scripts`` helper only returns
            ``NNN_*_down.sql`` for step IDs ``001``..``007``; ``000_`` and
            ``008+`` are intentionally irreversible in this bundle.
        """
        down_scripts = self._discovery.discover_down_scripts()
        if from_step is not None:
            from_idx: int | None = None
            for idx, path in enumerate(down_scripts):
                if path.stem.split("_down")[0] == from_step:
                    from_idx = idx
                    break
            if from_idx is None:
                logger.warning(
                    "from_step %r did not match any reversible step; "
                    "rolling back nothing",
                    from_step,
                )
                return 0
            down_scripts = down_scripts[from_idx:]

        # Reverse so the most recent change reverts first.
        ordered = list(reversed(down_scripts))
        conn = self._open()
        assert self._marker is not None  # _open() always sets _marker
        marker = self._marker
        try:
            rolled = 0
            for down_path in ordered:
                step_name = down_path.stem.split("_down")[0]
                sql_text = down_path.read_text(encoding="utf-8")
                if self._ctx.dry_run:
                    logger.info("dry_run: would roll back step %r", step_name)
                    continue
                try:
                    _execute_script(conn, sql_text)
                except Exception as exc:
                    logger.exception("failed to roll back step %r", step_name)
                    raise MigrationStepError(step_name, exc) from exc
                marker.mark_rolled_back(step_name)
                rolled += 1
                logger.info("rolled back step %r", step_name)
            return rolled
        finally:
            conn.close()

    def reset_stuck(self) -> int:
        """Delegate to :meth:`MarkerStore.reset_stuck` and close.

        Returns:
            Number of rows moved from ``running`` to ``failed`` by the
            stuck-threshold sweep.
        """
        conn = self._open()
        assert self._marker is not None  # _open() always sets _marker
        marker = self._marker
        try:
            return marker.reset_stuck()
        finally:
            conn.close()


__all__ = ["MigrationRunner", "StepResult"]
