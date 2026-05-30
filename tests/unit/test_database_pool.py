from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import types
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_LOGGING_STUB = types.ModuleType("session_buddy.utils.logging")
_LOGGING_STUB.get_session_logger = lambda: MagicMock()
sys.modules.setdefault("session_buddy.utils.logging", _LOGGING_STUB)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "database_pool.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.database_pool", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
database_pool = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.database_pool", database_pool)
_SPEC.loader.exec_module(database_pool)


class FakeCursor:
    def __init__(self, results: list[tuple[object, ...]]) -> None:
        self._results = results

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._results


class FakeConnection:
    def __init__(self, results: list[tuple[object, ...]] | None = None) -> None:
        self.results = results or [("ok",)]
        self.executions: list[tuple[str, object | None]] = []
        self.closed = False

    def execute(self, query: str, parameters: object | None = None) -> FakeCursor:
        self.executions.append((query, parameters))
        return FakeCursor(self.results)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_duckdb(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.SimpleNamespace()
    fake_module.connect = MagicMock(return_value=FakeConnection())
    monkeypatch.setattr(database_pool, "duckdb", fake_module)
    monkeypatch.setattr(database_pool, "DUCKDB_AVAILABLE", True)


def test_create_connection_raises_when_duckdb_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(database_pool, "DUCKDB_AVAILABLE", False)
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))

    with pytest.raises(ImportError, match="DuckDB not available"):
        pool._create_connection()


def test_module_loads_with_duckdb_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_duckdb = types.SimpleNamespace(connect=lambda *args, **kwargs: FakeConnection())
    monkeypatch.setitem(sys.modules, "duckdb", fake_duckdb)

    module_path = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "database_pool.py"
    spec = importlib.util.spec_from_file_location("session_buddy.utils.database_pool_duckdb", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.DUCKDB_AVAILABLE is True


def test_create_connection_sets_pragmas(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = pool._create_connection()

    assert isinstance(conn, FakeConnection)
    assert database_pool.duckdb.connect.called
    assert conn.executions == [
        ("PRAGMA threads=4", None),
        ("PRAGMA memory_limit='1GB'", None),
        ("PRAGMA temp_directory='/tmp'", None),
    ]


def test_create_connection_logs_and_reraises_on_error(
    fake_duckdb: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    logger = MagicMock()
    logger.exception = MagicMock()
    monkeypatch.setattr(database_pool, "_get_logger", lambda: logger)
    monkeypatch.setattr(database_pool.duckdb, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        pool._create_connection()

    logger.exception.assert_called_once_with("Failed to create database connection: boom")


def test_get_logger_falls_back_when_session_logger_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        database_pool,
        "get_session_logger",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    database_pool._logger = None

    logger = database_pool._get_logger()

    assert logger.name == database_pool.__name__


def test_get_connection_reuses_pooled_connection(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    pooled = FakeConnection()
    pool._pool.append(pooled)

    conn = pool.get_connection()

    assert conn is pooled
    assert pooled in pool._active_connections.values()


def test_get_connection_creates_new_connection(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))

    conn = pool.get_connection()

    assert isinstance(conn, FakeConnection)
    assert conn in pool._active_connections.values()


def test_get_connection_raises_when_max_connections_reached(
    fake_duckdb: None,
    tmp_path: Path,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"), max_connections=1)
    pool._active_connections[1] = FakeConnection()

    with pytest.raises(RuntimeError, match="Maximum connections"):
        pool.get_connection()


def test_get_connection_raises_when_pool_closed(
    fake_duckdb: None,
    tmp_path: Path,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    pool._closed = True

    with pytest.raises(RuntimeError, match="Connection pool is closed"):
        pool.get_connection()


def test_return_connection_recycles_and_closes_excess(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"), max_connections=1)
    conn = FakeConnection()
    pool._active_connections[id(conn)] = conn

    pool.return_connection(conn)

    assert conn in pool._pool
    assert id(conn) not in pool._active_connections


def test_return_connection_ignores_closed_pool_and_none(
    fake_duckdb: None,
    tmp_path: Path,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    pool._closed = True

    pool.return_connection(None)
    pool.return_connection(FakeConnection())

    assert pool._pool == []


def test_return_connection_closes_when_pool_full(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"), max_connections=1)
    conn1 = FakeConnection()
    conn2 = FakeConnection()
    pool._pool.append(conn1)
    pool._active_connections[id(conn2)] = conn2

    pool.return_connection(conn2)

    assert conn2.closed is True
    assert conn2 not in pool._pool


def test_return_connection_logs_excess_close_error(
    fake_duckdb: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"), max_connections=1)
    conn = FakeConnection()
    pool._active_connections[id(conn)] = conn
    pool._pool.append(FakeConnection())
    logger = MagicMock()
    logger.warning = MagicMock()
    monkeypatch.setattr(database_pool, "_get_logger", lambda: logger)

    def boom_close() -> None:
        raise RuntimeError("close boom")

    conn.close = boom_close  # type: ignore[method-assign]

    pool.return_connection(conn)

    assert logger.warning.called


@pytest.mark.asyncio
async def test_get_async_connection_returns_and_recycles(
    fake_duckdb: None,
    tmp_path: Path,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = FakeConnection()
    pool._create_connection = lambda: conn  # type: ignore[method-assign]

    async with pool.get_async_connection() as acquired:
        assert acquired is conn

    assert conn in pool._pool


@pytest.mark.asyncio
async def test_get_async_connection_logs_and_reraises(
    fake_duckdb: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    logger = MagicMock()
    logger.exception = MagicMock()
    monkeypatch.setattr(database_pool, "_get_logger", lambda: logger)

    async def boom() -> None:
        async with pool.get_async_connection():
            raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await boom()

    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_execute_query_uses_parameters(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = FakeConnection(results=[(1,), (2,)])
    pool._create_connection = lambda: conn  # type: ignore[method-assign]

    result = await pool.execute_query("SELECT * FROM t WHERE id = ?", (5,))

    assert result == [(1,), (2,)]
    assert conn.executions[-1] == ("SELECT * FROM t WHERE id = ?", (5,))


@pytest.mark.asyncio
async def test_execute_query_logs_errors(
    fake_duckdb: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = FakeConnection()
    pool._create_connection = lambda: conn  # type: ignore[method-assign]
    logger = MagicMock()
    logger.exception = MagicMock()
    monkeypatch.setattr(database_pool, "_get_logger", lambda: logger)

    def boom_execute(query: str, parameters: object | None = None) -> FakeCursor:
        raise RuntimeError("query boom")

    conn.execute = boom_execute  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="query boom"):
        await pool.execute_query("SELECT 1")

    assert logger.exception.call_count == 2
    assert logger.exception.call_args_list[0].args[0] == "Query execution failed: query boom"
    assert logger.exception.call_args_list[1].args[0] == "Database connection error: query boom"


@pytest.mark.asyncio
async def test_execute_query_without_parameters(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = FakeConnection(results=[("row",)])
    pool._create_connection = lambda: conn  # type: ignore[method-assign]

    result = await pool.execute_query("SELECT 1")

    assert result == [("row",)]
    assert conn.executions[-1] == ("SELECT 1", None)


@pytest.mark.asyncio
async def test_execute_many(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = FakeConnection(results=[("ok",)])
    pool._create_connection = lambda: conn  # type: ignore[method-assign]

    result = await pool.execute_many("INSERT INTO t VALUES (?)", [(1,), (2,)])

    assert result == [[("ok",)], [("ok",)]]
    assert conn.executions == [
        ("INSERT INTO t VALUES (?)", (1,)),
        ("INSERT INTO t VALUES (?)", (2,)),
    ]


@pytest.mark.asyncio
async def test_execute_many_logs_errors(
    fake_duckdb: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    conn = FakeConnection()
    pool._create_connection = lambda: conn  # type: ignore[method-assign]
    logger = MagicMock()
    logger.exception = MagicMock()
    monkeypatch.setattr(database_pool, "_get_logger", lambda: logger)

    def boom_execute(query: str, parameters: object | None = None) -> FakeCursor:
        if parameters == (2,):
            raise RuntimeError("batch boom")
        return FakeCursor([("ok",)])

    conn.execute = boom_execute  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="batch boom"):
        await pool.execute_many("INSERT INTO t VALUES (?)", [(1,), (2,)])

    assert logger.exception.call_count == 2
    assert logger.exception.call_args_list[0].args[0] == "Batch query execution error: batch boom"
    assert logger.exception.call_args_list[1].args[0] == "Database connection error: batch boom"


def test_get_stats_and_close_all(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"), max_connections=3)
    conn1 = FakeConnection()
    conn2 = FakeConnection()
    pool._pool.append(conn1)
    pool._active_connections[id(conn2)] = conn2

    stats = pool.get_stats()

    assert stats == {
        "total_connections": 2,
        "active_connections": 1,
        "pooled_connections": 1,
        "max_connections": 3,
        "pool_utilization": pytest.approx(1 / 3),
        "db_path": str(tmp_path / "db.duckdb"),
    }

    pool.close_all()

    assert pool._closed is True
    assert conn1.closed is True
    assert conn2.closed is True
    assert pool._pool == []
    assert pool._active_connections == {}


def test_close_all_logs_errors_and_shuts_down_executor(
    fake_duckdb: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"), max_connections=3)
    pooled = FakeConnection()
    active = FakeConnection()
    pool._pool.append(pooled)
    pool._active_connections[id(active)] = active
    pool._executor = ThreadPoolExecutor(max_workers=1)
    logger = MagicMock()
    logger.warning = MagicMock()
    logger.info = MagicMock()
    monkeypatch.setattr(database_pool, "_get_logger", lambda: logger)

    def boom_close() -> None:
        raise RuntimeError("close boom")

    pooled.close = boom_close  # type: ignore[method-assign]
    active.close = boom_close  # type: ignore[method-assign]

    pool.close_all()

    assert logger.warning.call_count == 2
    assert logger.info.call_count == 1
    assert pool._executor is None


def test_close_all_is_idempotent(fake_duckdb: None, tmp_path: Path) -> None:
    pool = database_pool.DatabaseConnectionPool(str(tmp_path / "db.duckdb"))
    pool.close_all()

    # Second call should be a no-op
    pool.close_all()

    assert pool._closed is True


def test_get_database_pool_reuses_instance(fake_duckdb: None, tmp_path: Path) -> None:
    path = str(tmp_path / "db.duckdb")
    pool1 = database_pool.get_database_pool(path, max_connections=2)
    pool2 = database_pool.get_database_pool(path, max_connections=5)

    assert pool1 is pool2


def test_close_all_pools_clears_registry(fake_duckdb: None, tmp_path: Path) -> None:
    path = str(tmp_path / "db.duckdb")
    pool = database_pool.get_database_pool(path, max_connections=2)
    pool._pool.append(FakeConnection())

    database_pool.close_all_pools()

    assert database_pool._connection_pools == {}
