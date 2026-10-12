"""Migration marker store for the UUID7 consolidation.

Each migration step is recorded in a single-row ``__uuid7_migration_state``
table inside DuckDB. The state machine is::

    absent  ──claim──▶  running  ──mark_done──▶  done
       │                   │
       │                   ├──mark_failed──▶  failed  ──mark_rolled_back──▶  rolled_back
       │                   │                                          │
       │                   │            claim (no force)          │
       │                   └──────────────────────────────────────┴──▶ running (force)

The table is created lazily by :meth:`MarkerStore.ensure_schema`; the rest of
the API assumes the schema is in place.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb


class StaleRunningError(RuntimeError):
    """Raised when ``claim`` is invoked for a step that is already ``running``."""


class MarkerStore:
    """Thin wrapper around ``__uuid7_migration_state`` in DuckDB."""

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def ensure_schema(self) -> None:
        """Create the marker table if it does not already exist."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS __uuid7_migration_state (
                step VARCHAR PRIMARY KEY,
                state VARCHAR NOT NULL CHECK (
                    state IN ('pending','running','done','failed','rolled_back')
                ),
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                rows_affected BIGINT,
                error_message VARCHAR
            )
            """
        )

    def claim(self, step: str, force: bool = False) -> bool:
        """Transition ``step`` to ``running`` and return ``True``.

        Returns ``False`` when the step is already ``done`` (idempotent skip)
        or when it is ``failed`` and ``force=False``. Raises
        :class:`StaleRunningError` when the step is ``running`` so the caller
        can recover via :meth:`reset_stuck` followed by a forced claim.
        """
        row = self._conn.execute(
            "SELECT state, started_at FROM __uuid7_migration_state WHERE step = ?",
            [step],
        ).fetchone()

        if row is None:
            self._conn.execute(
                """
                INSERT INTO __uuid7_migration_state (step, state, started_at)
                VALUES (?, 'running', ?)
                """,
                [step, datetime.now(UTC)],
            )
            return True

        state = row[0]

        if state == "done":
            return False

        if state == "failed":
            if not force:
                return False
            self._transition_to_running(step)
            return True

        if state in ("pending", "rolled_back"):
            self._transition_to_running(step)
            return True

        if state == "running":
            raise StaleRunningError(
                f"step {step!r} is already running (started_at={row[1]}); "
                "call reset_stuck() then retry with force=True"
            )

        raise RuntimeError(f"unknown migration state {state!r} for step {step!r}")

    def mark_done(self, step: str, rows_affected: int) -> None:
        """Persist terminal success for ``step``."""
        self._conn.execute(
            """
            UPDATE __uuid7_migration_state
            SET state = 'done',
                finished_at = ?,
                rows_affected = ?,
                error_message = NULL
            WHERE step = ?
            """,
            [datetime.now(UTC), rows_affected, step],
        )

    def mark_failed(self, step: str, error: str) -> None:
        """Persist terminal failure for ``step``."""
        self._conn.execute(
            """
            UPDATE __uuid7_migration_state
            SET state = 'failed',
                finished_at = ?,
                error_message = ?,
                rows_affected = NULL
            WHERE step = ?
            """,
            [datetime.now(UTC), error, step],
        )

    def mark_rolled_back(self, step: str) -> None:
        """Persist that the operator reverted ``step``'s effects."""
        self._conn.execute(
            """
            UPDATE __uuid7_migration_state
            SET state = 'rolled_back',
                finished_at = ?,
                error_message = NULL,
                rows_affected = NULL
            WHERE step = ?
            """,
            [datetime.now(UTC), step],
        )

    def status(self) -> list[dict]:
        """Return every step row, sorted by step name."""
        rows = self._conn.execute(
            """
            SELECT step, state, started_at, finished_at, rows_affected, error_message
            FROM __uuid7_migration_state
            ORDER BY step
            """
        ).fetchall()
        return [
            {
                "step": row[0],
                "state": row[1],
                "started_at": row[2],
                "finished_at": row[3],
                "rows_affected": row[4],
                "error_message": row[5],
            }
            for row in rows
        ]

    def reset_stuck(self, stuck_threshold_seconds: int = 3600) -> int:
        """Move ``running`` rows older than the threshold into ``failed``.

        Returns the number of rows moved. Use this to recover from crashed
        ``runners`` that left rows in ``running``; follow up with ``claim(step,
        force=True)`` to retry.
        """
        now = datetime.now(UTC)
        threshold = now - timedelta(seconds=stuck_threshold_seconds)
        result = self._conn.execute(
            """
            UPDATE __uuid7_migration_state
            SET state = 'failed',
                finished_at = ?,
                error_message = 'reset by reset_stuck: exceeded stuck threshold'
            WHERE state = 'running' AND started_at < ?
            RETURNING step
            """,
            [now, threshold],
        ).fetchall()
        return len(result)

    def _transition_to_running(self, step: str) -> None:
        self._conn.execute(
            """
            UPDATE __uuid7_migration_state
            SET state = 'running',
                started_at = ?,
                finished_at = NULL,
                rows_affected = NULL,
                error_message = NULL
            WHERE step = ?
            """,
            [datetime.now(UTC), step],
        )
