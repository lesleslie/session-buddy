"""Focused coverage tests for the code-graph MCP facade."""

from __future__ import annotations

import asyncio
import builtins
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools import code_graph
from session_buddy.mcp.tools.code_graph import CodeGraphHit, search_code_graph

pytestmark = pytest.mark.unit


class _RowsResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class _Connection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.sql = ""
        self.params: list[object] = []

    def execute(self, sql: str, params: list[object]) -> _RowsResult:
        self.sql = sql
        self.params = params
        return _RowsResult(self.rows)


class _WrappedDatabase:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def _get_conn(self) -> _Connection:
        return self.connection


class _ImmediateLoop:
    async def run_in_executor(self, _executor: object, function: Any) -> Any:
        return function()


def test_public_exports_are_importable() -> None:
    assert CodeGraphHit is not None
    assert search_code_graph is not None
    assert code_graph.__all__ == ["CodeGraphHit", "search_code_graph"]


async def test_search_code_graph_maps_sync_rows_and_caps_limit() -> None:
    search = MagicMock(
        return_value=[
            {
                "repo_path": "/repo",
                "symbol": "target",
                "project": "explicit-project",
                "call_count": "4",
                "last_seen_at": "2026-08-03T12:00:00Z",
            },
            {},
        ]
    )
    db = SimpleNamespace(search_code_graph_nodes=search)

    hits = await search_code_graph("target", "fallback-project", limit=500, db=db)

    search.assert_called_once_with(query="target", project="fallback-project", limit=50)
    assert hits == [
        CodeGraphHit(
            repo_path="/repo",
            symbol="target",
            project="explicit-project",
            call_count=4,
            last_seen_at="2026-08-03T12:00:00Z",
        ),
        CodeGraphHit(
            repo_path="",
            symbol="",
            project="fallback-project",
            call_count=0,
            last_seen_at="",
        ),
    ]


async def test_search_code_graph_awaits_async_accessor_with_empty_result() -> None:
    search = AsyncMock(return_value=None)
    db = SimpleNamespace(search_code_graph_nodes=search)

    assert await search_code_graph("missing", "project", limit=2, db=db) == []
    search.assert_awaited_once_with(query="missing", project="project", limit=2)


async def test_search_code_graph_returns_empty_when_default_db_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = AsyncMock(return_value=None)
    monkeypatch.setattr(code_graph, "_resolve_default_db", resolver)

    assert await search_code_graph("target", "project") == []
    resolver.assert_awaited_once_with()


async def test_search_code_graph_uses_resolved_default_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search = MagicMock(return_value=[])
    db = SimpleNamespace(search_code_graph_nodes=search)
    monkeypatch.setattr(code_graph, "_resolve_default_db", AsyncMock(return_value=db))

    assert await search_code_graph("target", "project", limit=3) == []
    search.assert_called_once_with(query="target", project="project", limit=3)


async def test_search_code_graph_propagates_accessor_errors() -> None:
    search = MagicMock(side_effect=ValueError("bad query"))
    db = SimpleNamespace(search_code_graph_nodes=search)

    with pytest.raises(ValueError, match="bad query"):
        await search_code_graph("target", "project", db=db)


async def test_resolve_default_db_returns_required_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    expected = object()
    resolver = AsyncMock(return_value=expected)

    # Force-import the canonical module so it lives in sys.modules under
    # its fully-qualified name. Without this, the prior test files'
    # sys.modules stub-leak (and the conftest's per-test
    # ``_purge_session_buddy_stubs``) can leave the package's
    # ``database_tools`` attribute pointing at a module object that is
    # NOT the one in ``sys.modules``. In that state,
    # ``code_graph._resolve_default_db`` re-imports a fresh module from
    # disk and patches applied via either the string-form
    # ``monkeypatch.setattr`` or the ``database_tools`` local form land on
    # the stale reference, so the production function calls the real
    # ``require_reflection_database`` and returns a live adapter instead of
    # the mock.
    if "session_buddy.utils.database_tools" not in sys.modules:
        import importlib
        importlib.import_module("session_buddy.utils.database_tools")

    # Use the canonical sys.modules reference so the patch lands on the
    # same module object that ``code_graph._resolve_default_db`` will
    # import. A naive ``from session_buddy.utils import database_tools``
    # can return a *different* module object than
    # ``sys.modules['session_buddy.utils.database_tools']`` when prior
    # tests pollute the namespace (see the long-form explanation above),
    # so the local-form ``monkeypatch.setattr(database_tools, ...)`` is
    # racy. The string-form ``monkeypatch.setattr("...")`` is also racy
    # because ``_pytest.monkeypatch.resolve()`` walks the dotted path via
    # ``getattr`` and can miss the cached attribute under pytest's per-
    # test stub-purge dance (raising AttributeError before the patch
    # lands).
    db_tools_module = sys.modules["session_buddy.utils.database_tools"]
    monkeypatch.setattr(db_tools_module, "require_reflection_database", resolver)

    assert await code_graph._resolve_default_db() is expected
    resolver.assert_awaited_once_with()


@pytest.mark.parametrize("error_type", [RuntimeError, ConnectionError, OSError])
async def test_resolve_default_db_handles_runtime_failures(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    from session_buddy.utils import database_tools

    monkeypatch.setattr(
        database_tools,
        "require_reflection_database",
        AsyncMock(side_effect=error_type("unavailable")),
    )

    assert await code_graph._resolve_default_db() is None


async def test_resolve_default_db_handles_missing_database_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def missing_database_tools(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "session_buddy.utils.database_tools":
            raise ImportError("database tools unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_database_tools)

    assert await code_graph._resolve_default_db() is None


async def test_sql_fallback_maps_supported_and_legacy_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _ImmediateLoop())
    rows = [
        (
            "/repo/named",
            "named-hash",
            "2026-08-03T12:00:00Z",
            7,
            json.dumps({"nodes": [{"name": "real_symbol"}]}),
        ),
        ("/repo/missing-name", "missing-hash", "timestamp", 8, '{"nodes": [{}]}'),
        ("/repo/list", "list-hash", "timestamp", 9, "[]"),
        ("/repo/non-dict", "non-dict-hash", "timestamp", 10, '{"nodes": ["x"]}'),
        ("/repo/malformed", "malformed-hash", "timestamp", 11, "not-json"),
        ("/repo/no-json", "no-json-hash", "timestamp", 12, None),
        ("/repo/short", "short-hash"),
    ]
    connection = _Connection(rows)

    hits = await search_code_graph("repo", "project", limit=7, db=connection)

    assert connection.params == ["%repo%", 7]
    assert "FROM code_graphs" in connection.sql
    assert [hit.symbol for hit in hits] == [
        "real_symbol",
        "missing-hash",
        "list-hash",
        "non-dict-hash",
        "malformed-hash",
        "no-json-hash",
        "short-hash",
    ]
    assert hits[0].call_count == 7
    assert hits[-1].call_count == 0
    assert hits[-1].last_seen_at == ""
    assert all(hit.project == "project" for hit in hits)


async def test_sql_fallback_uses_wrapped_connection() -> None:
    connection = _Connection([])

    rows = await code_graph._search_via_sql(
        _WrappedDatabase(connection), query="needle", project="project", limit=4
    )

    assert rows == []
    assert connection.params == ["%needle%", 4]


@pytest.mark.parametrize("error_type", [RuntimeError, ConnectionError, OSError])
async def test_sql_fallback_handles_database_failures(error_type: type[Exception]) -> None:
    connection = _Connection([])
    connection.execute = MagicMock(side_effect=error_type("query failed"))

    assert await search_code_graph("target", "project", db=connection) == []
