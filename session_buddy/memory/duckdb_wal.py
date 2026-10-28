"""Recovering a DuckDB instance from a poisoned WAL sidecar.

A DuckDB *fatal* error -- most often a failed checkpoint -- invalidates
the whole database instance, and the invalidation is persisted in the
``.wal`` sidecar next to the database file. Every later open replays the
poison, so the database is dead on arrival and restarting the process
does not clear it: the poison is on disk.

The data file itself is fine. Recovery is to discard the WAL sidecar and
reopen at the last good checkpoint. The writes that were in the WAL but
never checkpointed are lost, which is the right trade for a database
that cannot otherwise be opened at all.

The important detail is *when* to look. A poisoned WAL does not make
``duckdb.connect()`` fail -- the instance is simply invalid on arrival,
and the first write or checkpoint is what reports it. A recovery keyed
on a connect-time exception therefore never fires, and the service stays
broken across restarts. So the instance is probed with a CHECKPOINT
right after connecting, and the sidecar is discarded only when the
failure is one of the known WAL signatures.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

#: Error fragments that mean "the WAL sidecar is the problem, not the
#: data file". A failure that does not match any of these is left alone:
#: discarding the WAL would throw away uncommitted writes for no reason.
WAL_ERROR_SIGNATURES = (
    "replaying WAL",
    "GetDefaultDatabase",
    "has been invalidated because of a previous fatal error",
    "Operation requires a flat or constant vector",
)

__all__ = [
    "WAL_ERROR_SIGNATURES",
    "is_wal_poison",
    "open_healthy_duckdb",
    "purge_wal",
]


def is_wal_poison(error: BaseException) -> bool:
    """True when ``error`` means the WAL sidecar is the problem.

    Args:
        error: The exception raised while opening or using the database.

    Returns:
        True if the failure is one of the known WAL-poison signatures.
    """
    message = str(error)
    return any(signature in message for signature in WAL_ERROR_SIGNATURES)


def purge_wal(db_path: str) -> bool:
    """Delete the ``.wal`` sidecar belonging to ``db_path``.

    Args:
        db_path: Path to the DuckDB database file, or ``":memory:"``.

    Returns:
        True if a sidecar was removed.
    """
    if db_path == ":memory:":
        return False
    wal_file = Path(f"{db_path}.wal")
    if not wal_file.exists():
        return False
    try:
        wal_file.unlink()
    except OSError:
        logger.exception("Could not remove the poisoned DuckDB WAL: %s", wal_file)
        return False
    logger.warning("Discarded a poisoned DuckDB WAL sidecar: %s", wal_file)
    return True


def open_healthy_duckdb(
    db_path: str, *, config: dict[str, Any] | None = None
) -> duckdb.DuckDBPyConnection:
    """Open ``db_path``, recovering from a poisoned WAL sidecar if needed.

    The instance is probed with a CHECKPOINT after connecting, because a
    poisoned WAL leaves the instance invalid on arrival rather than
    refusing the connection. If the probe reports WAL poison, the
    sidecar is discarded and the database is reopened at the last good
    checkpoint.

    Args:
        db_path: Path to the DuckDB database, or ``":memory:"``.
        config: Optional DuckDB configuration.

    Returns:
        A live connection to a healthy instance.

    Raises:
        duckdb.Error: If the database cannot be opened, even after the
            WAL sidecar has been discarded.
    """
    # ``duckdb.connect`` rejects a None config outright, so only pass it
    # when there is one.
    connect_kwargs: dict[str, Any] = {} if config is None else {"config": config}

    try:
        conn = duckdb.connect(db_path, **connect_kwargs)
    except Exception as e:
        if not is_wal_poison(e):
            raise
        logger.warning(
            "DuckDB refused to open %s because of its WAL sidecar (%s); "
            "discarding the WAL and reopening at the last good checkpoint.",
            db_path,
            e,
        )
    else:
        if db_path == ":memory:":
            return conn
        try:
            conn.execute("CHECKPOINT")
            return conn
        except Exception as e:
            if not is_wal_poison(e):
                raise
            logger.warning(
                "DuckDB instance for %s is poisoned by its WAL sidecar (%s); "
                "discarding the WAL and reopening at the last good checkpoint.",
                db_path,
                e,
            )
            with suppress(Exception):
                conn.close()

    purge_wal(db_path)
    return duckdb.connect(db_path, **connect_kwargs)
