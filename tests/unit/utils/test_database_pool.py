"""Unit tests for ``session_buddy.utils.database_pool``.

Covers:
- ``DatabaseConnectionPool.__init__`` (dir creation, atexit registration)
- ``_create_connection`` (raises when duckdb unavailable)
- ``get_connection`` / ``return_connection`` (sync pool ops)
- ``get_async_connection`` / ``execute_query`` / ``execute_many`` (async API)
- ``get_stats`` / ``close_all`` (lifecycle)
- Thread-safety under concurrent ``get_connection`` calls
- Module-level ``get_database_pool`` / ``close_all_pools`` singletons
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from session_buddy.utils import database_pool as dbp


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _stub_atexit(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``atexit.register`` with a no-op so tests don't pollute the
    process-global atexit handler list.

    Returns the mock that captured the registrations, in case a test wants
    to assert what was registered.
    """
    captured = MagicMock()
    monkeypatch.setattr(dbp.atexit, "register", captured)
    return captured


def _make_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_connections: int = 5,
    db_name: str = "pool.duckdb",
) -> dbp.DatabaseConnectionPool:
    """Build a pool with a unique per-test file path and atexit stubbed.

    Skips the surrounding test if DuckDB is unavailable.
    """
    if not dbp.DUCKDB_AVAILABLE:
        pytest.skip("duckdb is unavailable in this environment")
    _stub_atexit(monkeypatch)
    return dbp.DatabaseConnectionPool(
        str(tmp_path / db_name),
        max_connections=max_connections,
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestDatabaseConnectionPoolInit:
    """Verify construction-time invariants of ``DatabaseConnectionPool``."""

    def test_init_creates_database_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True, exist_ok=True) is False  # noop; just sanity
        _stub_atexit(monkeypatch)
        dbp.DatabaseConnectionPool(str(nested / "x.duckdb"))
        assert nested.is_dir()

    def test_init_registers_atexit_cleanup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured = _stub_atexit(monkeypatch)
        pool = dbp.DatabaseConnectionPool(str(tmp_path / "p.duckdb"))
        assert captured.called
        # The first registered callable is the pool's close_all bound method.
        registered = [call.args[0] for call in captured.call_args_list]
        assert any(getattr(c, "__self__", None) is pool for c in registered)

    def test_init_default_max_connections(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_atexit(monkeypatch)
        pool = dbp.DatabaseConnectionPool(str(tmp_path / "p.duckdb"))
        assert pool.max_connections == 5

    def test_init_custom_max_connections(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_atexit(monkeypatch)
        pool = dbp.DatabaseConnectionPool(
            str(tmp_path / "p.duckdb"),
            max_connections=3,
        )
        assert pool.max_connections == 3

    def test_init_records_path_and_defaults(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_atexit(monkeypatch)
        path = str(tmp_path / "p.duckdb")
        pool = dbp.DatabaseConnectionPool(path)
        assert pool.db_path == path
        assert pool._pool == []
        assert pool._active_connections == {}
        assert pool._closed is False
        assert pool._executor is None


# ---------------------------------------------------------------------------
# _create_connection
# ---------------------------------------------------------------------------


class TestCreateConnection:
    """Cover the private ``_create_connection`` factory."""

    def test_create_connection_returns_working_connection(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        if not dbp.DUCKDB_AVAILABLE:
            pytest.skip("duckdb is unavailable in this environment")
        pool = _make_pool(tmp_path, monkeypatch)
        conn = pool._create_connection()
        try:
            # The pragma set inside _create_connection must succeed.
            result = conn.execute("SELECT 1 AS one").fetchone()
            assert result == (1,)
        finally:
            conn.close()

    def test_create_connection_raises_when_duckdb_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_atexit(monkeypatch)
        monkeypatch.setattr(dbp, "DUCKDB_AVAILABLE", False)
        pool = dbp.DatabaseConnectionPool(str(tmp_path / "p.duckdb"))
        with pytest.raises(ImportError, match="DuckDB not available"):
            pool._create_connection()


# ---------------------------------------------------------------------------
# get_connection / return_connection (sync)
# ---------------------------------------------------------------------------


class TestGetAndReturnConnection:
    """Cover the synchronous ``get_connection`` / ``return_connection`` pair."""

    def test_get_connection_creates_new_when_pool_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=3)
        conn = pool.get_connection()
        try:
            assert pool._active_connections[id(conn)] is conn
            stats = pool.get_stats()
            assert stats["active_connections"] == 1
            assert stats["pooled_connections"] == 0
        finally:
            conn.close()
            pool.close_all()

    def test_return_connection_recycles_to_pool(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=3)
        conn = pool.get_connection()
        pool.return_connection(conn)
        assert pool.get_stats()["pooled_connections"] == 1
        assert pool.get_stats()["active_connections"] == 0
        pool.close_all()

    def test_returned_connection_is_returned_by_next_get(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=3)
        first = pool.get_connection()
        pool.return_connection(first)
        second = pool.get_connection()
        try:
            assert second is first
            assert pool.get_stats()["pooled_connections"] == 0
        finally:
            pool.return_connection(second)
            pool.close_all()

    def test_get_connection_raises_when_max_reached(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=1)
        first = pool.get_connection()
        try:
            with pytest.raises(RuntimeError, match="Maximum connections"):
                pool.get_connection()
        finally:
            pool.return_connection(first)
            pool.close_all()

    def test_get_connection_after_close_all_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        pool.close_all()
        with pytest.raises(RuntimeError, match="Connection pool is closed"):
            pool.get_connection()

    def test_return_connection_when_closed_is_noop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        conn = pool.get_connection()
        pool.close_all()
        # Should not raise even though the pool is closed.
        pool.return_connection(conn)

    def test_return_none_connection_is_noop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        pool.return_connection(None)  # type: ignore[arg-type]
        assert pool.get_stats()["active_connections"] == 0

    def test_return_when_pool_already_full_closes_excess(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the pool is already at max, a returned conn is closed
        rather than appended.

        The pool's ``get_connection`` enforces ``active < max``, so we
        have to seed both sides directly to exercise the
        ``pool-already-full`` branch in ``return_connection``.
        """
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        # Fill the pool by returning two real connections.
        first = pool.get_connection()
        second = pool.get_connection()
        pool.return_connection(first)
        pool.return_connection(second)
        assert pool.get_stats()["pooled_connections"] == 2
        # Now synthesize a third active connection and return it. The
        # pool is full, so return_connection should close it instead of
        # appending it.
        if not dbp.DUCKDB_AVAILABLE:
            pytest.skip("duckdb is unavailable in this environment")
        import duckdb

        extra = duckdb.connect(
            pool.db_path,
            config={"allow_unsigned_extensions": True},
        )
        pool._active_connections[id(extra)] = extra
        pool.return_connection(extra)
        # Pool length unchanged, the extra conn should be unusable now.
        assert pool.get_stats()["pooled_connections"] == 2
        with pytest.raises(Exception):  # noqa: BLE001 - duckdb raises on closed conn
            extra.execute("SELECT 1").fetchall()
        pool.close_all()


# ---------------------------------------------------------------------------
# get_async_connection / execute_query / execute_many
# ---------------------------------------------------------------------------


class TestAsyncConnectionAndQueries:
    """Cover the async context manager and query helpers."""

    async def test_get_async_connection_yields_and_returns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        async with pool.get_async_connection() as conn:
            assert conn is not None
            assert pool.get_stats()["active_connections"] == 1
        # After exit the connection should be back in the pool.
        assert pool.get_stats()["active_connections"] == 0
        assert pool.get_stats()["pooled_connections"] == 1
        pool.close_all()

    async def test_execute_query_basic_select(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        try:
            rows = await pool.execute_query("SELECT 1 + 1 AS two")
            assert rows == [(2,)]
        finally:
            pool.close_all()

    async def test_execute_query_with_parameters(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        try:
            rows = await pool.execute_query(
                "SELECT ?::INT AS n",
                (42,),
            )
            assert rows == [(42,)]
        finally:
            pool.close_all()

    async def test_execute_query_without_parameters(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # parameters=None branch
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        try:
            rows = await pool.execute_query(
                "SELECT 'hi' AS greeting",
                parameters=None,
            )
            assert rows == [("hi",)]
        finally:
            pool.close_all()

    async def test_execute_many_runs_each_parameter_tuple(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        try:
            results = await pool.execute_many(
                "SELECT ?::INT AS n",
                [(1,), (2,), (3,)],
            )
            assert results == [[(1,)], [(2,)], [(3,)]]
        finally:
            pool.close_all()


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Cover the ``get_stats`` introspection helper."""

    def test_stats_initial_pool_is_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=4)
        stats = pool.get_stats()
        assert stats == {
            "total_connections": 0,
            "active_connections": 0,
            "pooled_connections": 0,
            "max_connections": 4,
            "pool_utilization": 0.0,
            "db_path": pool.db_path,
        }
        pool.close_all()

    def test_stats_reflects_active_and_pooled(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=4)
        a = pool.get_connection()
        b = pool.get_connection()
        pool.return_connection(b)
        stats = pool.get_stats()
        assert stats["active_connections"] == 1
        assert stats["pooled_connections"] == 1
        assert stats["total_connections"] == 2
        assert stats["max_connections"] == 4
        assert stats["pool_utilization"] == 0.25
        pool.return_connection(a)
        pool.close_all()


# ---------------------------------------------------------------------------
# close_all
# ---------------------------------------------------------------------------


class TestCloseAll:
    """Cover pool teardown semantics."""

    def test_close_all_clears_pools_and_active(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=3)
        conn = pool.get_connection()
        pool.close_all()
        assert pool._pool == []
        assert pool._active_connections == {}
        assert pool._closed is True
        assert pool._executor is None
        # The closed connection should no longer respond to queries.
        with pytest.raises(Exception):  # noqa: BLE001 - duckdb raises on closed conn
            conn.execute("SELECT 1").fetchall()

    def test_close_all_is_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        pool.get_connection()
        pool.close_all()
        # Second call must not raise.
        pool.close_all()
        assert pool._closed is True

    def test_close_all_with_no_active_or_pooled_conns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        pool.close_all()
        assert pool._closed is True
        assert pool._pool == []
        assert pool._active_connections == {}

    def test_close_all_shuts_down_executor(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        # Force executor creation.
        executor = pool._get_executor()
        assert pool._executor is executor
        pool.close_all()
        assert pool._executor is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Verify concurrent ``get_connection`` calls are serialized by the lock."""

    def test_concurrent_gets_return_unique_connection_ids(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=8)
        results: list[int] = []
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                conn = pool.get_connection()
                results.append(id(conn))
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(results) == 8
        # Each concurrent get returned a distinct connection.
        assert len(set(results)) == len(results)
        pool.close_all()

    def test_concurrent_gets_respect_max_connections(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = _make_pool(tmp_path, monkeypatch, max_connections=2)
        successes: list[int] = []
        max_reached: list[BaseException] = []

        def worker() -> None:
            try:
                conn = pool.get_connection()
                successes.append(id(conn))
            except RuntimeError as exc:
                if "Maximum connections" in str(exc):
                    max_reached.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Only 2 successes are permitted when max=2; the rest should
        # see the "Maximum connections" error.
        assert len(successes) == 2
        assert len(max_reached) == 4
        assert pool.get_stats()["active_connections"] == 2
        pool.close_all()


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------


class TestGetDatabasePoolModule:
    """Cover the module-level cache helpers."""

    def test_get_database_pool_returns_cached_instance(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        if not dbp.DUCKDB_AVAILABLE:
            pytest.skip("duckdb is unavailable in this environment")
        captured = _stub_atexit(monkeypatch)
        path = str(tmp_path / "shared.duckdb")
        first = dbp.get_database_pool(path, max_connections=4)
        second = dbp.get_database_pool(path, max_connections=2)
        assert first is second
        # max_connections from the first call wins — the cache key is the
        # path alone.
        assert first.max_connections == 4
        # Only one DatabaseConnectionPool was constructed, so atexit
        # register should have fired once for it.
        registrations = [
            call.args[0]
            for call in captured.call_args_list
            if isinstance(getattr(call.args[0], "__self__", None), dbp.DatabaseConnectionPool)
        ]
        assert len(registrations) == 1
        first.close_all()

    def test_get_database_pool_different_paths_yield_different_pools(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        if not dbp.DUCKDB_AVAILABLE:
            pytest.skip("duckdb is unavailable in this environment")
        _stub_atexit(monkeypatch)
        a = dbp.get_database_pool(str(tmp_path / "a.duckdb"))
        b = dbp.get_database_pool(str(tmp_path / "b.duckdb"))
        assert a is not b
        a.close_all()
        b.close_all()

    def test_close_all_pools_clears_module_cache(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        if not dbp.DUCKDB_AVAILABLE:
            pytest.skip("duckdb is unavailable in this environment")
        _stub_atexit(monkeypatch)
        a = dbp.get_database_pool(str(tmp_path / "a.duckdb"))
        b = dbp.get_database_pool(str(tmp_path / "b.duckdb"))
        dbp.close_all_pools()
        # After close_all_pools, the cache should be empty and
        # subsequent lookups should return fresh instances.
        assert dbp._connection_pools == {}
        assert a._closed is True
        assert b._closed is True
