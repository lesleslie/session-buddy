"""Recovering a DuckDB instance from a poisoned WAL sidecar.

A DuckDB *fatal* error -- most often a failed checkpoint -- invalidates
the whole database instance, and the invalidation is persisted in the
``.wal`` sidecar next to the database file. Every later open replays the
poison, so the database is dead on arrival: the connect succeeds and the
first write reports the invalidation. Restarting the process does not
clear it, because the poison is on disk.
"""

from __future__ import annotations

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

    assert len(attempts) == 2, "the helper must retry once after purging the WAL"
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
