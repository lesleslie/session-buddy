"""Recovering a DuckDB instance from a poisoned WAL sidecar.

A DuckDB *fatal* error -- most often a failed checkpoint -- invalidates
the whole database instance, and the invalidation is persisted in the
``.wal`` sidecar next to the database file. Every later open replays the
poison, so the database is dead on arrival: the connect succeeds and the
first write reports the invalidation. Restarting the process does not
clear it, because the poison is on disk.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from session_buddy.memory import duckdb_open

INVALIDATION = (
    "FATAL Error: Failed: database has been invalidated because of a "
    "previous fatal error. The database must be restarted prior to being "
    "used again."
)

#: Builds a database whose HNSW-indexed row exists only in the WAL.
#:
#: The process exits without closing the connection, which is what an
#: unclean shutdown looks like to the next open: the row was written, but
#: never checkpointed, so it lives in the WAL sidecar. That is the state
#: DuckDB cannot rebuild an HNSW index over.
_WAL_BEARING_HNSW_SCRIPT = """
import os
import sys

import duckdb

conn = duckdb.connect(sys.argv[1])
try:
    conn.execute("LOAD 'vss'")
    conn.execute("SET hnsw_enable_experimental_persistence=true")
except Exception:
    print("VSS_MISSING")
    sys.exit(3)
conn.execute("CREATE TABLE t (id VARCHAR, embedding FLOAT[4096])")
conn.execute(
    "CREATE INDEX idx ON t USING HNSW (embedding) "
    "WITH (metric = 'cosine', M = 16, ef_construction = 200)"
)
real = "[" + ",".join(["0.5"] * 4096) + "]"
conn.execute("INSERT INTO t VALUES ('a', " + real + ")")
print("VSS_OK")
# Leave without checkpointing: os._exit skips the checkpoint-on-close, so
# the WAL sidecar survives with the row in it.
os._exit(0)
"""


def _make_wal_bearing_hnsw_db(db: Path) -> None:
    """Build a database whose HNSW-indexed row lives only in the WAL.

    Skips the test when the ``vss`` extension is not installed -- the
    HNSW index type needs it.
    """
    result = subprocess.run(
        [sys.executable, "-c", _WAL_BEARING_HNSW_SCRIPT, str(db)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 3 or "VSS_MISSING" in result.stdout:
        pytest.skip("the vss extension is not installed")
    assert result.returncode == 0, result.stderr


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> None:
    """The probe memo is process-wide; each test starts from a clean slate."""
    duckdb_open._probed_paths.clear()


def test_is_wal_poison_matches_the_known_signatures() -> None:
    """The signatures that mean "the WAL is the problem" are recognised."""
    assert duckdb_open.is_wal_poison(RuntimeError(INVALIDATION))
    assert duckdb_open.is_wal_poison(RuntimeError("Error: replaying WAL"))
    assert duckdb_open.is_wal_poison(RuntimeError("GetDefaultDatabase failed"))
    assert duckdb_open.is_wal_poison(
        RuntimeError(
            "Failed: create checkpoint because of error: Operation requires "
            "a flat or constant vector but a non-flat/non-constant vector "
            "was encountered"
        )
    )


def test_is_wal_poison_ignores_unrelated_errors() -> None:
    """An unrelated failure must not be mistaken for WAL poison."""
    assert not duckdb_open.is_wal_poison(OSError("No space left on device"))
    assert not duckdb_open.is_wal_poison(RuntimeError("Catalog Error: Table not found"))


def test_purge_wal_removes_the_sidecar(tmp_path: Path) -> None:
    """The sidecar is removed, and only the sidecar."""
    db = tmp_path / "reflection.duckdb"
    db.write_bytes(b"not really a database")
    wal = Path(f"{db}.wal")
    wal.write_bytes(b"poison")

    assert duckdb_open.purge_wal(str(db)) is True
    assert not wal.exists()
    assert db.exists()


def test_purge_wal_is_a_no_op_when_there_is_no_sidecar(tmp_path: Path) -> None:
    """Nothing to purge is not an error."""
    db = tmp_path / "reflection.duckdb"
    db.write_bytes(b"not really a database")

    assert duckdb_open.purge_wal(str(db)) is False
    assert db.exists()


def test_open_healthy_duckdb_discards_a_poisoned_wal_and_reopens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A poisoned WAL must not leave the service permanently broken.

    The connect itself succeeds -- a poisoned WAL leaves the instance
    invalid on arrival rather than refusing the connection -- so the
    probe is what detects it. Recovery discards the sidecar and reopens
    at the last good checkpoint.
    """
    db = tmp_path / "reflection.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (i INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()
    wal = Path(f"{db}.wal")
    wal.write_bytes(b"poison")

    real_connect = duckdb.connect
    attempts: list[str] = []

    def fake_connect(path: str, **kwargs: object) -> object:
        attempts.append(str(path))
        if len(attempts) == 1:
            # First attempt: the probe fails the way a poisoned WAL does.
            poisoned = Mock()

            def execute(sql: str, *args: object, **kw: object) -> None:
                if sql.strip().upper().startswith("CHECKPOINT"):
                    raise RuntimeError(INVALIDATION)

            poisoned.execute.side_effect = execute
            return poisoned
        return real_connect(path, **kwargs)

    monkeypatch.setattr(duckdb_open.duckdb, "connect", fake_connect)

    conn = duckdb_open.open_healthy_duckdb(str(db))

    # Three connects: the probe, the data-preserving flush (which declines
    # here -- the fixture has no HNSW index), and the reopen after the
    # sidecar was purged.
    assert len(attempts) == 3, "the helper must retry after purging the WAL"
    assert not wal.exists(), "the poisoned sidecar must be discarded"
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1


def test_open_healthy_duckdb_keeps_the_wal_for_unrelated_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure that is not WAL poison must not destroy the sidecar."""
    db = tmp_path / "reflection.duckdb"
    db.write_bytes(b"not really a database")
    wal = Path(f"{db}.wal")
    wal.write_bytes(b"precious")

    def fake_connect(path: str, **kwargs: object) -> object:
        failing = Mock()

        def execute(sql: str, *args: object, **kw: object) -> None:
            raise OSError("No space left on device")

        failing.execute.side_effect = execute
        return failing

    monkeypatch.setattr(duckdb_open.duckdb, "connect", fake_connect)

    with pytest.raises(OSError, match="No space left"):
        duckdb_open.open_healthy_duckdb(str(db))

    assert wal.exists(), "an unrelated failure must not discard the WAL"


def test_open_healthy_duckdb_loads_the_vector_extension_before_probing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The extension that owns the HNSW index type must be loaded first.

    A checkpoint cannot bind an index whose extension is not loaded, and
    a failed checkpoint invalidates the whole instance -- so the load has
    to happen before the probe, not after the schema initialisation that
    creates the indexes in the first place.
    """
    db = tmp_path / "reflection.duckdb"
    db.write_bytes(b"not really a database")
    calls: list[str] = []

    recording = Mock()

    def execute(sql: str, *args: object, **kw: object) -> None:
        calls.append(sql.strip().split()[0].upper())

    recording.execute.side_effect = execute

    monkeypatch.setattr(duckdb_open.duckdb, "connect", Mock(return_value=recording))

    duckdb_open.open_healthy_duckdb(str(db))

    assert "LOAD" in calls, "the vector extension must be loaded"
    assert calls.index("LOAD") < calls.index("CHECKPOINT"), (
        f"the extension must be loaded before the checkpoint; calls were {calls}"
    )


def test_open_healthy_duckdb_keeps_the_wal_when_an_index_type_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing extension is not WAL poison, so the sidecar survives."""
    db = tmp_path / "reflection.duckdb"
    db.write_bytes(b"not really a database")
    wal = Path(f"{db}.wal")
    wal.write_bytes(b"precious")

    def fake_connect(path: str, **kwargs: object) -> object:
        failing = Mock()

        def execute(sql: str, *args: object, **kw: object) -> None:
            msg = (
                'Cannot bind index "default_conversations", unknown index '
                "type 'HNSW'. You need to load the extension that provides "
                "this index type."
            )
            raise RuntimeError(msg)

        failing.execute.side_effect = execute
        return failing

    monkeypatch.setattr(duckdb_open.duckdb, "connect", fake_connect)

    conn = duckdb_open.open_healthy_duckdb(str(db))

    assert conn is not None
    assert wal.exists(), "a missing extension must not discard the WAL"


def test_open_healthy_duckdb_probes_each_path_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe costs a checkpoint, so it runs once per path per process.

    The service opens several connections to the same file, and the
    sidecar is on disk -- every connection replays it, so one probe
    catches the poison for all of them.
    """
    db = tmp_path / "reflection.duckdb"
    db.write_bytes(b"not really a database")
    calls: list[str] = []

    recording = Mock()

    def execute(sql: str, *args: object, **kw: object) -> None:
        calls.append(sql.strip().split()[0].upper())

    recording.execute.side_effect = execute

    monkeypatch.setattr(duckdb_open.duckdb, "connect", Mock(return_value=recording))

    duckdb_open.open_healthy_duckdb(str(db))
    duckdb_open.open_healthy_duckdb(str(db))
    duckdb_open.open_healthy_duckdb(str(db))

    assert calls.count("CHECKPOINT") == 1, (
        f"the probe must run once per path; calls were {calls}"
    )


# ============================================================================
# The data-preserving flush
# ============================================================================


def test_open_healthy_duckdb_keeps_the_writes_a_poisoned_wal_holds(
    tmp_path: Path,
) -> None:
    """The un-checkpointed writes must survive the recovery.

    DuckDB cannot rebuild an HNSW index over rows that were replayed from
    the WAL, so the probe's checkpoint fails and the instance is
    invalidated. The index is the only thing that cannot be rebuilt -- the
    data is fine. Discarding the WAL therefore throws away writes that
    were perfectly good; dropping the index, checkpointing, and recreating
    the index keeps them.
    """
    db = tmp_path / "reflection.duckdb"
    _make_wal_bearing_hnsw_db(db)
    wal = Path(f"{db}.wal")
    assert wal.exists(), "the fixture must leave a WAL behind"

    conn = duckdb_open.open_healthy_duckdb(str(db))

    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1, (
        "the row that lived only in the WAL must survive the recovery"
    )
    indexes = conn.execute(
        "SELECT index_name, sql FROM duckdb_indexes() WHERE sql ILIKE '%USING HNSW%'"
    ).fetchall()
    assert indexes, "the HNSW index must be rebuilt"
    # The rebuild has to keep the index's tuning: an HNSW index rebuilt
    # with the default M and ef_construction is a different index.
    assert "metric = 'cosine'" in indexes[0][1]
    assert "M = 16" in indexes[0][1]
    assert "ef_construction = 200" in indexes[0][1]
    conn.close()


def test_flush_poisoned_wal_declines_when_there_is_no_hnsw_index(
    tmp_path: Path,
) -> None:
    """Without an HNSW index there is nothing to drop, so the flush declines.

    The caller then falls back to discarding the sidecar, which is the
    right trade for a poison this recovery cannot explain.
    """
    db = tmp_path / "reflection.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE TABLE t (i INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.close()

    assert duckdb_open.flush_poisoned_wal(str(db)) is None


# ============================================================================
# The recovery never executes text read out of the database
# ============================================================================


def _create_hnsw_db(db: Path, table_sql: str, index_sql: str) -> None:
    """Create a database with one HNSW index and a table to protect."""
    conn = duckdb.connect(str(db))
    conn.execute("LOAD 'vss'")
    conn.execute("SET hnsw_enable_experimental_persistence=true")
    conn.execute(table_sql)
    conn.execute("CREATE TABLE marker (x INTEGER)")
    conn.execute(index_sql)
    conn.close()


def test_flush_poisoned_wal_refuses_an_index_with_a_hostile_name(
    tmp_path: Path,
) -> None:
    """A name the recovery cannot vouch for means it declines, not escapes.

    The catalog's SQL text is read to find the index and its options,
    but it is never executed: the statement is composed from validated
    identifiers and options. A name that is not a plain identifier
    cannot be composed, so the recovery declines -- and the schema is
    left untouched rather than rebuilt from unvetted text.
    """
    db = tmp_path / "reflection.duckdb"
    _create_hnsw_db(
        db,
        "CREATE TABLE t (id VARCHAR, embedding FLOAT[4096])",
        'CREATE INDEX "evil; DROP TABLE marker; --" ON t USING HNSW (embedding)',
    )

    assert duckdb_open.flush_poisoned_wal(str(db)) is None

    conn = duckdb.connect(str(db))
    # The marker table still exists: nothing was dropped, so nothing ran.
    assert conn.execute("SELECT count(*) FROM marker").fetchone()[0] == 0
    assert (
        conn.execute(
            "SELECT count(*) FROM duckdb_indexes() WHERE sql ILIKE '%USING HNSW%'"
        ).fetchone()[0]
        == 1
    ), "the index must be left in place"
    conn.close()


def test_flush_poisoned_wal_refuses_an_index_with_a_hostile_column(
    tmp_path: Path,
) -> None:
    """The same rule applies to the indexed column."""
    db = tmp_path / "reflection.duckdb"
    _create_hnsw_db(
        db,
        'CREATE TABLE t (id VARCHAR, "embedding; DROP TABLE marker" FLOAT[4096])',
        'CREATE INDEX evil_idx ON t USING HNSW ("embedding; DROP TABLE marker")',
    )

    assert duckdb_open.flush_poisoned_wal(str(db)) is None

    conn = duckdb.connect(str(db))
    assert conn.execute("SELECT count(*) FROM marker").fetchone()[0] == 0
    conn.close()
