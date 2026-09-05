"""Tests for session_buddy.mcp.tools.infrastructure.access_log_tools.

Covers the MCP tools for memory access log statistics:
- ``register_access_log_tools`` registers the ``access_log_stats`` tool.
- ``access_log_stats`` returns the structured payload with all fields.
- All query helpers (``_build_query_config``, ``_get_total_accesses``,
  ``_get_distinct_memories``, ``_get_access_type_stats``,
  ``_get_provider_stats``, ``_get_top_memories``,
  ``_get_recent_accesses``) work correctly.
- Error path: when duckdb is unavailable, the tool returns a structured
  error dict instead of raising.
"""

from __future__ import annotations

import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from session_buddy.mcp.tools.infrastructure import access_log_tools as mod
from session_buddy.mcp.tools.infrastructure.access_log_tools import (
    _build_query_config,
    _get_access_type_stats,
    _get_distinct_memories,
    _get_provider_stats,
    _get_recent_accesses,
    _get_top_memories,
    _get_total_accesses,
    register_access_log_tools,
)


# ---------------------------------------------------------------------------
# FakeMCP
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Captures @mcp.tool() registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *, name: str | None = None, description: str | None = None):
        def decorator(fn: Any) -> Any:
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


def _as_async(coro_factory: Any) -> Any:
    """Run an async callable (or lambda wrapping one) and return its result."""
    import asyncio

    async def run() -> Any:
        coro = coro_factory
        # If it's a callable that returns a coroutine, invoke it.
        if callable(coro) and not asyncio.iscoroutine(coro):
            coro = coro()
        return await coro

    return asyncio.run(run())


# ---------------------------------------------------------------------------
# Fake duckdb + connection
# ---------------------------------------------------------------------------


def _make_conn(rows_by_query: dict[str, list[Any]]) -> MagicMock:
    """Build a connection mock that returns different results per query."""
    conn = MagicMock()

    def execute(sql: str, params: Any = None) -> MagicMock:
        result = MagicMock()
        # Use the first non-comment, non-whitespace keyword as a key.
        # The actual keys we test against are simple and distinguishable.
        if "COUNT(DISTINCT l.memory_id)" in sql:
            result.fetchone.return_value = rows_by_query.get("distinct", (5,))
        elif "GROUP BY l.access_type" in sql:
            result.fetchall.return_value = rows_by_query.get("by_type", [])
        elif "SELECT COUNT(*) FROM memory_access_log" in sql:
            result.fetchone.return_value = rows_by_query.get("total", (10,))
        elif "MAX(l.timestamp)" in sql:
            # Top memories — each row maps to a dict.
            result.fetchall.return_value = rows_by_query.get("top", [])
        elif "ORDER BY l.timestamp DESC" in sql and "JOIN" not in sql:
            result.fetchall.return_value = rows_by_query.get("recent", [])
        else:
            result.fetchone.return_value = None
            result.fetchall.return_value = []
        return result

    conn.execute.side_effect = execute
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    return conn


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestRegisterAccessLogTools:
    def test_registers_tool(self) -> None:
        mcp = _FakeMCP()
        register_access_log_tools(mcp)
        assert "access_log_stats" in mcp.tools

    def test_returns_none(self) -> None:
        mcp = _FakeMCP()
        assert register_access_log_tools(mcp) is None


# ---------------------------------------------------------------------------
# _build_query_config
# ---------------------------------------------------------------------------


class TestBuildQueryConfig:
    def test_no_filters(self) -> None:
        cfg = _build_query_config(datetime(2026, 1, 1), None, None)
        assert cfg["where"] == "l.timestamp >= ?"
        assert cfg["params"] == [datetime(2026, 1, 1)]
        assert cfg["join_clause"] == ""

    def test_project_only(self) -> None:
        cfg = _build_query_config(datetime(2026, 1, 1), "myproj", None)
        assert "AND c.id = l.memory_id" in cfg["where"]
        assert "AND c.project = ?" in cfg["where"]
        assert cfg["params"] == [datetime(2026, 1, 1), "myproj"]
        assert "JOIN conversations_v2 c ON c.id=l.memory_id" == cfg["join_clause"]

    def test_namespace_only(self) -> None:
        cfg = _build_query_config(datetime(2026, 1, 1), None, "ns1")
        assert "AND c.namespace = ?" in cfg["where"]
        assert cfg["params"] == [datetime(2026, 1, 1), "ns1"]

    def test_project_and_namespace(self) -> None:
        cfg = _build_query_config(datetime(2026, 1, 1), "p", "n")
        assert "AND c.project = ?" in cfg["where"]
        assert "AND c.namespace = ?" in cfg["where"]
        assert cfg["params"] == [datetime(2026, 1, 1), "p", "n"]


# ---------------------------------------------------------------------------
# _get_total_accesses
# ---------------------------------------------------------------------------


class TestGetTotalAccesses:
    def test_returns_int(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (7,)
        assert _get_total_accesses(conn, {"where": "x", "params": [], "join_clause": ""}) == 7

    def test_handles_none_result(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        assert _get_total_accesses(conn, {"where": "x", "params": [], "join_clause": ""}) == 0


# ---------------------------------------------------------------------------
# _get_distinct_memories
# ---------------------------------------------------------------------------


class TestGetDistinctMemories:
    def test_returns_int(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (3,)
        assert _get_distinct_memories(conn, {"where": "x", "params": [], "join_clause": ""}) == 3

    def test_handles_none_result(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        assert _get_distinct_memories(conn, {"where": "x", "params": [], "join_clause": ""}) == 0


# ---------------------------------------------------------------------------
# _get_access_type_stats
# ---------------------------------------------------------------------------


class TestGetAccessTypeStats:
    def test_returns_dict(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            ("read", 4),
            ("write", 6),
        ]
        result = _get_access_type_stats(conn, {"where": "x", "params": [], "join_clause": ""})
        assert result == {"read": 4, "write": 6}

    def test_empty_rows(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        result = _get_access_type_stats(conn, {"where": "x", "params": [], "join_clause": ""})
        assert result == {}

    def test_handles_none_access_type(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [(None, 2)]
        result = _get_access_type_stats(conn, {"where": "x", "params": [], "join_clause": ""})
        # None becomes "" via the str(r[0] or "") coercion.
        assert result == {"": 2}


# ---------------------------------------------------------------------------
# _get_provider_stats
# ---------------------------------------------------------------------------


class TestGetProviderStats:
    def test_extract_provider_counts(self) -> None:
        by_type = {"extract:anthropic": 3, "extract:openai": 5, "read": 7}
        result = _get_provider_stats(by_type)
        assert result == {"anthropic": 3, "openai": 5}

    def test_empty_input(self) -> None:
        assert _get_provider_stats({}) == {}

    def test_non_extract_keys_ignored(self) -> None:
        assert _get_provider_stats({"read": 1, "write": 2, "list": 3}) == {}

    def test_provider_after_colon_empty_becomes_unknown(self) -> None:
        # Key "extract:" → split gives "extract" and "" → "" or "unknown" → "unknown"
        by_type = {"extract:": 1}
        assert _get_provider_stats(by_type) == {"unknown": 1}

    def test_aggregates_same_provider(self) -> None:
        # Keys must start with "extract:" to be aggregated. Use distinct
        # access_type names that share the same provider:
        by_type = {"extract:anthropic": 1, "extract:anthropic:foo": 2}
        # First splits to "anthropic"; second splits to "anthropic:foo".
        # They aggregate to "anthropic" + "anthropic:foo" — verify both are tracked.
        result = _get_provider_stats(by_type)
        assert result == {"anthropic": 1, "anthropic:foo": 2}


# ---------------------------------------------------------------------------
# _get_top_memories
# ---------------------------------------------------------------------------


class TestGetTopMemories:
    def test_empty_rows(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        assert _get_top_memories(conn, {"where": "x", "params": [], "join_clause": ""}, 5) == []

    def test_full_row(self) -> None:
        row = ("mem1", 10, "2026-09-04T12:00:00", "cat", "tier1", 0.9, "proj", "ns")
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [row]
        result = _get_top_memories(conn, {"where": "x", "params": [], "join_clause": ""}, 5)
        assert result == [
            {
                "memory_id": "mem1",
                "count": 10,
                "last_access": "2026-09-04T12:00:00",
                "category": "cat",
                "memory_tier": "tier1",
                "importance_score": 0.9,
                "project": "proj",
                "namespace": "ns",
            }
        ]

    def test_row_with_nullable_fields(self) -> None:
        row = ("mem1", 10, "2026-09-04T12:00:00", None, None, None, None, None)
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [row]
        result = _get_top_memories(conn, {"where": "x", "params": [], "join_clause": ""}, 5)
        assert result[0]["category"] is None
        assert result[0]["memory_tier"] is None
        assert result[0]["importance_score"] is None
        assert result[0]["project"] is None
        assert result[0]["namespace"] is None


# ---------------------------------------------------------------------------
# _get_recent_accesses
# ---------------------------------------------------------------------------


class TestGetRecentAccesses:
    def test_empty(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        assert _get_recent_accesses(conn, {"where": "x", "params": [], "join_clause": ""}, 5) == []

    def test_full_row(self) -> None:
        row = ("mem1", "read", "2026-09-04T12:00:00")
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [row]
        result = _get_recent_accesses(conn, {"where": "x", "params": [], "join_clause": ""}, 5)
        assert result == [
            {
                "memory_id": "mem1",
                "access_type": "read",
                "timestamp": "2026-09-04T12:00:00",
            }
        ]

    def test_row_with_none_access_type(self) -> None:
        row = ("mem1", None, "2026-09-04T12:00:00")
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [row]
        result = _get_recent_accesses(conn, {"where": "x", "params": [], "join_clause": ""}, 5)
        assert result[0]["access_type"] is None


# ---------------------------------------------------------------------------
# access_log_stats — happy path
# ---------------------------------------------------------------------------


class TestAccessLogStatsHappyPath:
    def test_returns_full_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mcp = _FakeMCP()
        register_access_log_tools(mcp)
        tool_fn = mcp.tools["access_log_stats"]

        # Stub duckdb and get_database_path.
        fake_duckdb = ModuleType("duckdb")

        def fake_connect(path: str, config: dict | None = None):
            return _make_conn(
                {
                    "total": (15,),
                    "distinct": (8,),
                    "by_type": [
                        ("read", 5),
                        ("extract:anthropic", 7),
                        ("extract:openai", 3),
                    ],
                    "top": [
                        ("mem1", 4, "2026-09-04T12:00:00", "cat", "tier1", 0.9, "p", "ns"),
                    ],
                    "recent": [
                        ("mem1", "read", "2026-09-04T12:00:00"),
                    ],
                }
            )

        fake_duckdb.connect = fake_connect
        monkeypatch.setitem(sys.modules, "duckdb", fake_duckdb)
        import session_buddy.settings as _settings_module
        monkeypatch.setattr(
            _settings_module,
            "get_database_path",
            lambda: "/tmp/db.duckdb",
        )

        result = _as_async(tool_fn)

        assert result["window_hours"] == 24
        assert result["total_accesses"] == 15
        assert result["distinct_memories"] == 8
        assert result["by_type"] == {
            "read": 5,
            "extract:anthropic": 7,
            "extract:openai": 3,
        }
        assert result["by_provider"] == {"anthropic": 7, "openai": 3}
        assert len(result["top_memories"]) == 1
        assert len(result["recent"]) == 1
        assert result["filters"] == {"project": None, "namespace": None}


class TestAccessLogStatsArguments:
    def test_passes_filters_to_query_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mcp = _FakeMCP()
        register_access_log_tools(mcp)
        tool_fn = mcp.tools["access_log_stats"]

        captured_params: list[Any] = []

        def fake_connect(path: str, config: dict | None = None):
            conn = MagicMock()

            def execute(sql: str, params: Any = None):
                captured_params.append(params)
                result = MagicMock()
                if "COUNT(DISTINCT" in sql:
                    result.fetchone.return_value = (0,)
                elif "GROUP BY l.access_type" in sql:
                    result.fetchall.return_value = []
                elif "COUNT(*) FROM memory_access_log" in sql:
                    result.fetchone.return_value = (0,)
                elif "MAX(l.timestamp)" in sql:
                    result.fetchall.return_value = []
                else:
                    result.fetchall.return_value = []
                return result

            conn.execute.side_effect = execute
            conn.__enter__.return_value = conn
            conn.__exit__.return_value = False
            return conn

        fake_duckdb = ModuleType("duckdb")
        fake_duckdb.connect = fake_connect
        monkeypatch.setitem(sys.modules, "duckdb", fake_duckdb)
        import session_buddy.settings as _settings_module
        monkeypatch.setattr(
            _settings_module,
            "get_database_path",
            lambda: "/tmp/db.duckdb",
        )

        result = _as_async(
            lambda: tool_fn(hours=48, top_n=5, project="p1", namespace="n1")
        )

        assert result["window_hours"] == 48
        assert result["filters"] == {"project": "p1", "namespace": "n1"}
        # At least one captured params should contain project/namespace.
        joined = [p for params in captured_params for p in (params or [])]
        assert "p1" in joined
        assert "n1" in joined


class TestAccessLogStatsErrorPath:
    def test_returns_error_dict_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mcp = _FakeMCP()
        register_access_log_tools(mcp)
        tool_fn = mcp.tools["access_log_stats"]

        # Force duckdb import to raise.
        fake_duckdb = ModuleType("duckdb")

        def boom(path: str, config: dict | None = None):
            raise RuntimeError("duckdb exploded")

        fake_duckdb.connect = boom
        monkeypatch.setitem(sys.modules, "duckdb", fake_duckdb)
        import session_buddy.settings as _settings_module
        monkeypatch.setattr(
            _settings_module,
            "get_database_path",
            lambda: "/tmp/db.duckdb",
        )

        result = _as_async(tool_fn)

        assert "error" in result
        assert "duckdb exploded" in result["error"]
        assert "hint" in result

    def test_no_duckdb_module_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Remove duckdb from sys.modules to force ImportError inside the function.
        monkeypatch.delitem(sys.modules, "duckdb", raising=False)

        mcp = _FakeMCP()
        register_access_log_tools(mcp)
        tool_fn = mcp.tools["access_log_stats"]

        # Patch the import inside the function: insert a fake that raises on import.
        def fake_import(name: str, *args: Any, **kwargs: Any):
            if name == "duckdb":
                raise ImportError("no duckdb")
            return original_import(name, *args, **kwargs)

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
        monkeypatch.setattr("builtins.__import__", fake_import)

        result = _as_async(tool_fn)

        assert "error" in result
        assert "no duckdb" in result["error"]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_module_has_register_function(self) -> None:
        assert hasattr(mod, "register_access_log_tools")
        assert callable(mod.register_access_log_tools)

    def test_helpers_are_callable(self) -> None:
        for fn in (
            _build_query_config,
            _get_total_accesses,
            _get_distinct_memories,
            _get_access_type_stats,
            _get_provider_stats,
            _get_top_memories,
            _get_recent_accesses,
        ):
            assert callable(fn)
