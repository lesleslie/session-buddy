"""Recovering a DuckDB instance from a poisoned WAL sidecar.

A DuckDB *fatal* error -- most often a failed checkpoint -- invalidates
the whole database instance, and the invalidation is persisted in the
``.wal`` sidecar next to the database file. Every later open replays the
poison, so the database is dead on arrival and restarting the process
does not clear it: the poison is on disk.

The data file itself is fine. Recovery comes in two tiers. The first
tier flushes the WAL *without* losing the writes it holds: DuckDB cannot
rebuild an HNSW index over rows that were replayed from the WAL, so the
index -- and only the index -- is dropped, checkpointed around, and
rebuilt from its own ``CREATE INDEX`` statement. The second tier, used
when the first does not apply, discards the WAL sidecar and reopens at
the last good checkpoint. That loses the writes that were in the WAL but
never checkpointed, which is the right trade for a database that cannot
otherwise be opened at all.

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

#: Database paths already probed in this process. The probe costs a
#: checkpoint, and the service opens several connections to the same
#: file.
_probed_paths: set[str] = set()

__all__ = [
    "WAL_ERROR_SIGNATURES",
    "flush_poisoned_wal",
    "is_wal_poison",
    "load_vector_extensions",
    "open_healthy_duckdb",
    "purge_wal",
]


def load_vector_extensions(conn: duckdb.DuckDBPyConnection) -> None:
    """Load the extensions the reflection schema's HNSW indexes need.

    The schema creates ``USING HNSW`` indexes, and the ``vss`` extension
    provides that index type. An extension is bound to a database
    *instance*, not to a file, so a connection that does not load it
    cannot checkpoint the database: DuckDB fails the checkpoint with
    "unknown index type 'HNSW'", and a failed checkpoint invalidates the
    whole instance.

    That makes the load order load-bearing. The extension has to be
    loaded before the first checkpoint, which is before the schema
    initialisation that creates the indexes in the first place.

    Args:
        conn: The connection to prepare.
    """
    with suppress(Exception):
        conn.execute("INSTALL 'vss'")
    with suppress(Exception):
        conn.execute("LOAD 'vss'")
    with suppress(Exception):
        # HNSW indexes can only be persisted to disk with this flag set.
        conn.execute("SET hnsw_enable_experimental_persistence=true")


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


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier so it is safe to use in DDL."""
    return '"' + name.replace('"', '""') + '"'


def _hnsw_index_definitions(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    """Return ``(index_name, create_statement)`` for every HNSW index.

    The statement is the index's own ``CREATE INDEX`` text, which is what
    the flush re-runs to rebuild the index.
    """
    try:
        rows = conn.execute(
            "SELECT index_name, sql FROM duckdb_indexes() WHERE sql ILIKE ?",
            ["%USING HNSW%"],
        ).fetchall()
    except Exception:
        logger.exception("Could not list the HNSW indexes of the database")
        return []
    return [(str(name), str(sql)) for name, sql in rows if name and sql]


def _recreate_indexes(
    conn: duckdb.DuckDBPyConnection, definitions: list[tuple[str, str]]
) -> bool:
    """Rebuild the HNSW indexes that were dropped for the flush.

    Returns:
        True when every index was rebuilt.
    """
    rebuilt = True
    for index_name, statement in definitions:
        try:
            conn.execute(statement)
        except Exception:
            logger.exception("Could not rebuild the HNSW index %s", index_name)
            rebuilt = False
    return rebuilt


def flush_poisoned_wal(
    db_path: str, *, config: dict[str, Any] | None = None
) -> duckdb.DuckDBPyConnection | None:
    """Flush a poisoned WAL *without* losing the writes it holds.

    DuckDB cannot reconstruct an HNSW index over rows that were replayed
    from the WAL, so the checkpoint that would persist them fails and the
    instance is invalidated. The index is the only thing that cannot be
    rebuilt -- the data itself is fine. Dropping the index, checkpointing,
    and recreating the index from its own ``CREATE INDEX`` statement
    flushes the WAL *and* keeps every un-checkpointed write.

    Returns:
        A live connection with the WAL flushed, or ``None`` when the
        recovery does not apply (no HNSW index, or the flush failed).
    """
    connect_kwargs: dict[str, Any] = {} if config is None else {"config": config}
    try:
        conn = duckdb.connect(db_path, **connect_kwargs)
    except Exception:
        logger.exception("Could not reopen %s to flush its WAL", db_path)
        return None

    try:
        load_vector_extensions(conn)
        definitions = _hnsw_index_definitions(conn)
        if not definitions:
            # The poison is not an HNSW index, so this recovery cannot
            # help; the caller falls back to discarding the WAL.
            conn.close()
            return None
        for index_name, _ in definitions:
            conn.execute(f"DROP INDEX IF EXISTS {_quote_identifier(index_name)}")
        try:
            conn.execute("CHECKPOINT")
        except Exception:
            # The flush failed. Put the indexes back before giving up, so
            # the database is not left without them.
            _recreate_indexes(conn, definitions)
            raise
    except Exception:
        logger.exception("Could not flush the poisoned WAL of %s", db_path)
        with suppress(Exception):
            conn.close()
        return None

    if _recreate_indexes(conn, definitions):
        logger.warning(
            "Flushed the poisoned DuckDB WAL of %s without losing its writes.", db_path
        )
    else:
        # The data is flushed either way. A missing index costs recall,
        # not rows, so this is worth shouting about -- but it is not a
        # reason to fail the open.
        logger.error(
            "The WAL of %s was flushed, but some HNSW indexes could not be "
            "rebuilt. Vector search over those tables will be degraded until "
            "they are recreated.",
            db_path,
        )
    return conn


def open_healthy_duckdb(
    db_path: str, *, config: dict[str, Any] | None = None
) -> duckdb.DuckDBPyConnection:
    """Open ``db_path``, recovering from a poisoned WAL sidecar if needed.

    The instance is probed with a CHECKPOINT after connecting, because a
    poisoned WAL leaves the instance invalid on arrival rather than
    refusing the connection. If the probe reports WAL poison, the
    sidecar is discarded and the database is reopened at the last good
    checkpoint.

    The probe runs once per database path per process. The service opens
    several connections to the same file, and a checkpoint is not free on
    a large database; one probe is enough to catch a poisoned sidecar,
    because the sidecar lives on disk and every connection replays it.

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
        load_vector_extensions(conn)
        if db_path == ":memory:" or db_path in _probed_paths:
            return conn
        _probed_paths.add(db_path)
        try:
            conn.execute("CHECKPOINT")
            return conn
        except Exception as e:
            if "unknown index type" in str(e):
                # The extension that owns an index type is not loaded, so
                # the checkpoint cannot run. That is not WAL poison and
                # discarding the sidecar would throw away uncommitted
                # writes for nothing. The instance still works for reads.
                logger.warning(
                    "Could not checkpoint %s: %s. The instance is still "
                    "usable for reads; writes that need a checkpoint will fail.",
                    db_path,
                    e,
                )
                return conn
            if not is_wal_poison(e):
                raise
            logger.warning(
                "DuckDB instance for %s is poisoned by its WAL sidecar (%s); "
                "recovering the WAL without discarding its writes.",
                db_path,
                e,
            )
            with suppress(Exception):
                conn.close()

    # The WAL holds writes that were never checkpointed. Flushing it keeps
    # them; discarding the sidecar throws them away. Flush first, and only
    # discard when the flush does not apply.
    flushed = flush_poisoned_wal(db_path, config=config)
    if flushed is not None:
        return flushed

    purge_wal(db_path)
    conn = duckdb.connect(db_path, **connect_kwargs)
    load_vector_extensions(conn)
    return conn
