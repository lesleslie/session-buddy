"""Focused unit tests for the code-graph MCP subscriber facade.

Covers the helper utilities and the registered MCP tools exposed by
``session_buddy.subscribers.code_graph_subscriber``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.subscribers import code_graph_subscriber
from session_buddy.subscribers.code_graph_subscriber import (
    _build_node_map,
    _build_path_str,
    _collect_dependents,
    _find_target_node_id,
    _get_conn,
    _get_lock,
    _is_graph_stale,
    _is_valid_symbol_id,
    _load_latest_code_graph_context,
    _normalize_call_edges,
    _query_code_graph,
    _query_code_graphs_list,
    _traverse_call_chain,
    register_code_graph_tools,
)

pytestmark = pytest.mark.unit


class _RowsResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class _Connection:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.rows = rows or []
        self.sql = ""
        self.params: list[object] = []
        self.executemany_sql: list[str] = []

    def execute(self, sql: str, params: list[object] | None = None) -> _RowsResult:
        self.sql = sql
        self.params = params or []
        return _RowsResult(self.rows)


class _ImmediateLoop:
    async def run_in_executor(self, _executor: object, function: Any) -> Any:
        return function()


class TestModuleSurface:
    """Smoke tests covering module-level imports and the registration entry point."""

    def test_module_exposes_register_function(self) -> None:
        assert callable(register_code_graph_tools)
        assert callable(code_graph_subscriber.register_code_graph_tools)

    def test_register_code_graph_tools_invokes_all_registrars(self) -> None:
        mcp = MagicMock()
        mcp.tool.return_value = lambda fn: fn  # passthrough decorator

        register_code_graph_tools(mcp)

        # Each @mcp.tool() call returns the decorated function, so we expect
        # exactly five registered tools (storage + retrieval + list + call chain
        # + impact analysis).
        assert mcp.tool.call_count == 5


class TestGetLock:
    """``_get_lock`` returns the wrapper's lock when running against the temp db."""

    def test_returns_none_for_non_temp_database(self) -> None:
        reflection_db = SimpleNamespace(is_temp_db=False)
        assert _get_lock(reflection_db) is None

    def test_returns_none_when_is_temp_db_attribute_missing(self) -> None:
        reflection_db = SimpleNamespace()
        assert _get_lock(reflection_db) is None

    def test_returns_lock_for_temp_database(self) -> None:
        sentinel_lock = MagicMock()
        reflection_db = SimpleNamespace(is_temp_db=True, lock=sentinel_lock)
        assert _get_lock(reflection_db) is sentinel_lock


class TestGetConn:
    """``_get_conn`` extracts the underlying connection from the wrapper."""

    def test_returns_underlying_connection(self) -> None:
        sentinel_conn = object()
        reflection_db = SimpleNamespace(_get_conn=lambda: sentinel_conn)
        assert _get_conn(reflection_db) is sentinel_conn


class TestIsValidSymbolId:
    """``_is_valid_symbol_id`` rejects malformed qualified IDs."""

    @pytest.mark.parametrize(
        "symbol",
        [
            "Foo",
            "foo.bar",
            "Foo.bar.baz",
        ],
    )
    def test_accepts_unqualified_and_partial_ids(self, symbol: str) -> None:
        assert _is_valid_symbol_id(symbol) is True

    @pytest.mark.parametrize(
        "symbol",
        [
            "repo|||ns|||kind|||name",
            "a|||b|||c|||d.sub",
            "repo|||main|||module|||Foo.bar",
        ],
    )
    def test_accepts_fully_qualified_ids(self, symbol: str) -> None:
        assert _is_valid_symbol_id(symbol) is True

    def test_rejects_malformed_qualified_ids(self) -> None:
        assert _is_valid_symbol_id("a|||b|||c") is False
        assert _is_valid_symbol_id("a|||b") is False
        assert _is_valid_symbol_id("repo|||ns|||Foo.bar") is False
        # Single-char segments can't backtrack the final `[^|]+$` anchor.
        assert _is_valid_symbol_id("a|||b|||c|||d") is False


class TestBuildNodeMap:
    """``_build_node_map`` collapses node lists into a name-keyed dict."""

    def test_builds_map_from_dict_nodes(self) -> None:
        nodes = [
            {"id": "n1", "name": "alpha"},
            {"id": "n2", "name": "beta"},
        ]

        node_map = _build_node_map(nodes)

        assert node_map == {
            "n1": {"id": "n1", "name": "alpha"},
            "n2": {"id": "n2", "name": "beta"},
        }

    def test_falls_back_to_name_when_id_missing(self) -> None:
        nodes = [{"name": "alpha"}, {"id": "explicit-id"}]

        node_map = _build_node_map(nodes)

        assert node_map == {
            "alpha": {"name": "alpha"},
            "explicit-id": {"id": "explicit-id"},
        }

    def test_builds_map_from_string_nodes(self) -> None:
        nodes = ["alpha", "beta"]

        node_map = _build_node_map(nodes)

        assert node_map == {
            "alpha": {"id": "alpha", "name": "alpha"},
            "beta": {"id": "beta", "name": "beta"},
        }

    def test_empty_input_yields_empty_map(self) -> None:
        assert _build_node_map([]) == {}


class TestFindTargetNodeId:
    """``_find_target_node_id`` resolves a symbol name to its node id."""

    def test_returns_id_for_exact_name_match(self) -> None:
        node_map = {"n1": {"id": "n1", "name": "alpha"}, "n2": {"id": "n2", "name": "beta"}}

        assert _find_target_node_id("alpha", node_map) == "n1"

    def test_strips_qualifier_prefix_before_lookup(self) -> None:
        node_map = {"n1": {"id": "n1", "name": "alpha"}}

        assert _find_target_node_id("repo|||ns|||kind|||alpha", node_map) == "n1"

    def test_returns_none_when_symbol_missing(self) -> None:
        node_map = {"n1": {"id": "n1", "name": "alpha"}}
        assert _find_target_node_id("gamma", node_map) is None


class TestNormalizeCallEdges:
    """``_normalize_call_edges`` accepts both dict and tuple edge encodings."""

    def test_normalizes_dict_edges_with_default_relation(self) -> None:
        edges = [
            {"source": "a", "target": "b"},
            {"from": "c", "to": "d", "type": "imports"},
        ]

        assert _normalize_call_edges(edges) == [
            ("a", "b", "calls"),
            ("c", "d", "imports"),
        ]

    def test_normalizes_tuple_edges(self) -> None:
        edges = [("a", "b"), ("c", "d", "imports")]

        assert _normalize_call_edges(edges) == [
            ("a", "b", "calls"),
            ("c", "d", "imports"),
        ]

    def test_skips_unparseable_edges(self) -> None:
        edges = [None, 42, "raw-string", {"source": "x", "target": "y"}]
        assert _normalize_call_edges(edges) == [("x", "y", "calls")]


class TestTraverseCallChain:
    """``_traverse_call_chain`` walks callers/callees up to ``max_depth``."""

    def test_finds_callers_in_caller_direction(self) -> None:
        node_map = {
            "a": {"id": "a", "name": "a"},
            "b": {"id": "b", "name": "b"},
            "c": {"id": "c", "name": "c"},
        }
        call_edges = [("a", "b", "calls"), ("c", "b", "calls")]

        chains, total, truncated = _traverse_call_chain(
            target_node_id="b",
            direction="callers",
            max_depth=3,
            node_map=node_map,
            call_edges=call_edges,
            edge_filter=None,
        )

        assert total == 2
        assert truncated is False
        assert {chain["symbol"] for chain in chains} == {"a", "c"}
        assert all(chain["direction"] == "caller" for chain in chains)

    def test_finds_callees_in_callee_direction(self) -> None:
        node_map = {
            "a": {"id": "a", "name": "a"},
            "b": {"id": "b", "name": "b"},
            "c": {"id": "c", "name": "c"},
        }
        call_edges = [("a", "b", "calls"), ("a", "c", "calls")]

        chains, total, truncated = _traverse_call_chain(
            target_node_id="a",
            direction="callees",
            max_depth=3,
            node_map=node_map,
            call_edges=call_edges,
            edge_filter=None,
        )

        assert total == 2
        assert truncated is False
        assert {chain["symbol"] for chain in chains} == {"b", "c"}
        assert all(chain["direction"] == "callee" for chain in chains)

    def test_respects_edge_filter(self) -> None:
        node_map = {
            "a": {"id": "a", "name": "a"},
            "b": {"id": "b", "name": "b"},
        }
        call_edges = [
            ("a", "b", "calls"),
            ("a", "b", "imports"),
        ]

        chains, _, _ = _traverse_call_chain(
            target_node_id="b",
            direction="callers",
            max_depth=3,
            node_map=node_map,
            call_edges=call_edges,
            edge_filter=["calls"],
        )

        assert len(chains) == 1
        assert chains[0]["edge_type"] == "calls"


class TestCollectDependents:
    """``_collect_dependents`` records both direct and transitive callers."""

    def test_collects_direct_and_indirect_callers(self) -> None:
        node_map = {
            "target": {"id": "target", "name": "target", "file": "target.py"},
            "caller_a": {"id": "caller_a", "name": "caller_a", "file": "a.py"},
            "caller_b": {"id": "caller_b", "name": "caller_b", "file": "b.py"},
        }
        edges = [
            {"source": "caller_a", "target": "target"},
            {"source": "caller_b", "target": "target"},
        ]

        direct, indirect, files = _collect_dependents(
            target_node_id="target",
            max_depth=3,
            include_indirect=True,
            node_map=node_map,
            edges=edges,
        )

        assert {d["symbol"] for d in direct} == {"caller_a", "caller_b"}
        assert indirect == []
        assert files == {"target.py", "a.py", "b.py"}

    def test_excludes_indirect_when_disabled(self) -> None:
        node_map = {
            "target": {"id": "target", "name": "target"},
            "caller_a": {"id": "caller_a", "name": "caller_a"},
            "caller_b": {"id": "caller_b", "name": "caller_b"},
        }
        edges = [
            {"source": "caller_a", "target": "target"},
            {"source": "caller_b", "target": "caller_a"},
        ]

        direct, indirect, _ = _collect_dependents(
            target_node_id="target",
            max_depth=3,
            include_indirect=False,
            node_map=node_map,
            edges=edges,
        )

        assert {d["symbol"] for d in direct} == {"caller_a"}
        assert indirect == []


class TestBuildPathStr:
    """``_build_path_str`` formats an arrow between two node names."""

    def test_builds_path_from_dict_inputs(self) -> None:
        node_map = {"b": {"id": "b", "name": "beta"}}
        path = _build_path_str({"id": "a", "name": "alpha"}, "b", node_map)
        assert path == "alpha -> beta"

    def test_builds_path_from_string_input(self) -> None:
        node_map = {"b": {"id": "b", "name": "beta"}}
        path = _build_path_str("alpha", "b", node_map)
        assert path == "alpha -> beta"

    def test_falls_back_to_str_repr_when_name_missing(self) -> None:
        node_map = {"b": {"id": "b"}}
        path = _build_path_str({"id": "a"}, "b", node_map)
        # When ``from_info`` has no ``name`` key, the function falls back
        # to ``str(from_info)`` — i.e. the dict's repr.
        assert path == "{'id': 'a'} -> b"


class TestIsGraphStale:
    """``_is_graph_stale`` flags graphs older than 24 hours."""

    def test_returns_false_for_none_indexed_at(self) -> None:
        stale, last_seen = _is_graph_stale(None)
        assert stale is False
        assert last_seen is None

    def test_returns_false_for_empty_indexed_at(self) -> None:
        stale, last_seen = _is_graph_stale("")
        assert stale is False
        assert last_seen is None

    def test_returns_false_for_invalid_timestamp(self) -> None:
        stale, last_seen = _is_graph_stale("not-a-timestamp")
        assert stale is False
        assert last_seen is None

    def test_returns_false_for_recent_timestamp(self) -> None:
        from datetime import UTC, datetime, timedelta

        recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        stale, last_seen = _is_graph_stale(recent)
        assert stale is False
        assert last_seen is None

    def test_returns_true_for_old_timestamp(self) -> None:
        from datetime import UTC, datetime, timedelta

        old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        stale, last_seen = _is_graph_stale(old)
        assert stale is True
        assert last_seen == old


class TestLoadLatestCodeGraphContext:
    """``_load_latest_code_graph_context`` queries the latest stored graph."""

    def test_returns_none_when_no_row(self) -> None:
        conn = _Connection(rows=[])

        assert _load_latest_code_graph_context(conn, "/repo") is None

    def test_loads_graph_data_with_repo_path(self) -> None:
        graph = {"nodes": [{"id": "a"}], "edges": []}
        row = (json.dumps(graph), "2026-09-04T12:00:00Z", 1)
        conn = _Connection(rows=[row])

        context = _load_latest_code_graph_context(conn, "/repo")

        assert context is not None
        assert context["graph_data"] == graph
        assert context["indexed_at"] == "2026-09-04T12:00:00Z"
        assert context["repo_path"] == "/repo"

    def test_loads_graph_data_without_repo_path(self) -> None:
        graph = {"nodes": [{"id": "a"}]}
        row = (json.dumps(graph), "2026-09-04T12:00:00Z", 1, "/repo/from-row")
        conn = _Connection(rows=[row])

        context = _load_latest_code_graph_context(conn, None)

        assert context is not None
        assert context["graph_data"] == graph
        assert context["repo_path"] == "/repo/from-row"


class TestQueryCodeGraph:
    """``_query_code_graph`` returns a parsed dict or None."""

    def test_returns_none_when_no_row(self) -> None:
        conn = _Connection(rows=[])
        assert _query_code_graph(conn, "/repo", "hash") is None

    def test_returns_parsed_record(self) -> None:
        graph = {"nodes": [{"name": "x"}]}
        metadata = {"source": "mahavishnu"}
        row = (1, "/repo", "hash", "2026-09-04T12:00:00Z", 5, json.dumps(graph), json.dumps(metadata))
        conn = _Connection(rows=[row])

        result = _query_code_graph(conn, "/repo", "hash")

        assert result == {
            "id": 1,
            "repo_path": "/repo",
            "commit_hash": "hash",
            "indexed_at": "2026-09-04T12:00:00Z",
            "nodes_count": 5,
            "graph_data": graph,
            "metadata": metadata,
        }


class TestQueryCodeGraphsList:
    """``_query_code_graphs_list`` returns summary rows."""

    def test_returns_empty_list_when_no_rows(self) -> None:
        conn = _Connection(rows=[])
        assert _query_code_graphs_list(conn, "/repo", 10) == []

    def test_maps_rows_to_summaries(self) -> None:
        rows = [
            ("id1", "/repo", "hash1", "2026-09-04T12:00:00Z", 5),
            ("id2", "/repo", "hash2", "2026-09-03T12:00:00Z", 10),
        ]
        conn = _Connection(rows=rows)

        result = _query_code_graphs_list(conn, "/repo", 10)

        assert result == [
            {
                "id": "id1",
                "repo_path": "/repo",
                "commit_hash": "hash1",
                "indexed_at": "2026-09-04T12:00:00Z",
                "nodes_count": 5,
            },
            {
                "id": "id2",
                "repo_path": "/repo",
                "commit_hash": "hash2",
                "indexed_at": "2026-09-03T12:00:00Z",
                "nodes_count": 10,
            },
        ]


class TestStoreCodeGraphTool:
    """Tests for the registered ``store_code_graph_from_mahavishnu`` tool."""

    async def test_store_success(self) -> None:
        reflection_db = MagicMock()
        reflection_db.is_temp_db = False
        reflection_db.lock = None

        captured: dict[str, Any] = {}

        async def fake_store_code_graph(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "/repo:abc123"

        with (
            patch.object(
                code_graph_subscriber,
                "require_reflection_database",
                AsyncMock(return_value=reflection_db),
                create=True,
            ),
            patch(
                "session_buddy.reflection.storage.store_code_graph",
                AsyncMock(side_effect=fake_store_code_graph),
            ),
        ):
            result = await _invoke_store(
                repo_path="/repo",
                commit_hash="abc123",
                indexed_at="2026-09-04T12:00:00Z",
                nodes_count=42,
                graph_data={"nodes": [], "edges": []},
            )

        assert result["status"] == "success"
        assert result["graph_id"] == "/repo:abc123"
        assert captured["repo_path"] == "/repo"
        assert captured["commit_hash"] == "abc123"
        assert captured["nodes_count"] == 42
        assert captured["lock"] is None

    async def test_store_swallows_exception(self) -> None:
        with patch(
            "session_buddy.reflection.storage.store_code_graph",
            AsyncMock(side_effect=RuntimeError("db unavailable")),
        ):
            result = await _invoke_store(
                repo_path="/repo",
                commit_hash="abc",
                indexed_at="2026-09-04T12:00:00Z",
                nodes_count=0,
                graph_data={},
            )

        assert result["status"] == "error"
        assert "db unavailable" in result["message"]
        assert result["graph_id"] == ""


class TestGetCodeGraphTool:
    """Tests for the registered ``get_code_graph`` retrieval tool."""

    async def test_returns_not_found_when_missing(self) -> None:
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([]))
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_get_code_graph("/repo", "abc")

        assert result["status"] == "not_found"

    async def test_returns_record_on_success(self) -> None:
        graph = {"nodes": []}
        row = (
            "id1",
            "/repo",
            "abc",
            "2026-09-04T12:00:00Z",
            0,
            json.dumps(graph),
            json.dumps({}),
        )
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([row]))

        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_get_code_graph("/repo", "abc")

        assert result["status"] == "success"
        assert result["commit_hash"] == "abc"
        assert result["graph_data"] == graph

    async def test_swallows_exception(self) -> None:
        reflection_db = SimpleNamespace(_get_conn=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_get_code_graph("/repo", "abc")

        assert result["status"] == "error"
        assert "boom" in result["message"]


class TestListCodeGraphsTool:
    """Tests for the registered ``list_code_graphs`` tool."""

    async def test_returns_mapped_rows(self) -> None:
        rows = [
            ("id1", "/repo", "hash1", "2026-09-04T12:00:00Z", 5),
        ]
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection(rows))

        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_list_code_graphs(repo_path="/repo", limit=10)

        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["code_graphs"][0]["commit_hash"] == "hash1"

    async def test_swallows_exception(self) -> None:
        def boom() -> Any:
            raise RuntimeError("list failed")

        reflection_db = SimpleNamespace(_get_conn=boom)
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_list_code_graphs()

        assert result["status"] == "error"
        assert result["count"] == 0
        assert result["code_graphs"] == []


class TestCodeCallChainTool:
    """Tests for the registered ``code_call_chain`` query tool."""

    async def test_rejects_invalid_symbol_id(self) -> None:
        result = await _invoke_code_call_chain("a|||b|||c")
        assert result["error"] == "Invalid symbol ID format"

    async def test_returns_empty_when_no_graphs_indexed(self) -> None:
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([]))
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_call_chain("Foo.bar")

        assert result["chains"] == []
        assert result["message"] == "No code graphs found in database"

    async def test_resolves_callers_for_known_symbol(self) -> None:
        graph = {
            "nodes": [{"id": "n1", "name": "alpha"}, {"id": "n2", "name": "beta"}],
            "edges": [{"source": "n1", "target": "n2", "type": "calls"}],
        }
        row = (json.dumps(graph), "2026-09-04T12:00:00Z", 2, "/repo")
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([row]))

        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_call_chain("beta", direction="callers")

        assert result["root_symbol"] == "beta"
        assert result["total_nodes"] == 1
        assert result["chains"][0]["symbol"] == "alpha"

    async def test_returns_not_found_for_unknown_symbol(self) -> None:
        graph = {"nodes": [{"id": "n1", "name": "alpha"}], "edges": []}
        row = (json.dumps(graph), "2026-09-04T12:00:00Z", 1, "/repo")
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([row]))

        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_call_chain("missing")

        assert "not found" in result["message"]
        assert result["chains"] == []

    async def test_swallows_exception(self) -> None:
        def boom() -> Any:
            raise RuntimeError("query failed")

        reflection_db = SimpleNamespace(_get_conn=boom)
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_call_chain("Foo.bar")

        assert result["error"] == "query failed"
        assert result["chains"] == []


class TestCodeImpactAnalysisTool:
    """Tests for the registered ``code_impact_analysis`` tool."""

    async def test_rejects_invalid_symbol_id(self) -> None:
        result = await _invoke_code_impact_analysis("a|||b|||c")
        assert result["error"] == "Invalid symbol ID format"

    async def test_returns_low_risk_with_no_dependents(self) -> None:
        graph = {"nodes": [{"id": "n1", "name": "alpha"}], "edges": []}
        row = (json.dumps(graph), "2026-09-04T12:00:00Z", 1, "/repo")
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([row]))

        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_impact_analysis("alpha")

        assert result["risk_level"] == "low"
        assert result["blast_radius"] == 0
        assert result["direct_dependents"] == []

    async def test_returns_critical_risk_for_many_dependents(self) -> None:
        nodes = [{"id": "target", "name": "target"}] + [
            {"id": f"n{i}", "name": f"name_{i}"} for i in range(24)
        ]
        edges = [{"source": f"n{i}", "target": "target"} for i in range(24)]
        graph = {"nodes": nodes, "edges": edges}
        row = (json.dumps(graph), "2026-09-04T12:00:00Z", 25, "/repo")
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([row]))

        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_impact_analysis(
                "target", include_indirect=False, max_depth=5
            )

        assert result["risk_level"] == "critical"
        assert result["blast_radius"] == 24

    async def test_returns_no_graphs_message_when_empty(self) -> None:
        reflection_db = SimpleNamespace(_get_conn=lambda: _Connection([]))
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_impact_analysis("Foo.bar")

        assert result["message"] == "No code graphs found in database"
        assert result["blast_radius"] == 0

    async def test_swallows_exception(self) -> None:
        def boom() -> Any:
            raise RuntimeError("impact failed")

        reflection_db = SimpleNamespace(_get_conn=boom)
        with patch.object(
            code_graph_subscriber,
            "require_reflection_database",
            AsyncMock(return_value=reflection_db),
            create=True,
        ):
            result = await _invoke_code_impact_analysis("Foo.bar")

        assert result["error"] == "impact failed"
        assert result["blast_radius"] == 0


# ---------------------------------------------------------------------------
# Helpers: re-invoke the @mcp.tool()-decorated functions
# ---------------------------------------------------------------------------


async def _invoke_store(**kwargs: Any) -> dict[str, Any]:
    mcp = MagicMock()
    registered: dict[str, Any] = {}

    def _capture_tool() -> Any:
        def decorator(fn: Any) -> Any:
            registered["fn"] = fn
            return fn

        return decorator

    mcp.tool = _capture_tool

    code_graph_subscriber._register_code_graph_storage_tool(mcp)
    return await registered["fn"](**kwargs)


async def _invoke_get_code_graph(repo_path: str, commit_hash: str) -> dict[str, Any]:
    mcp = MagicMock()
    registered: dict[str, Any] = {}

    def _capture_tool() -> Any:
        def decorator(fn: Any) -> Any:
            registered["fn"] = fn
            return fn

        return decorator

    mcp.tool = _capture_tool

    code_graph_subscriber._register_code_graph_retrieval_tool(mcp)
    return await registered["fn"](repo_path=repo_path, commit_hash=commit_hash)


async def _invoke_list_code_graphs(
    repo_path: str | None = None, limit: int = 100
) -> dict[str, Any]:
    mcp = MagicMock()
    registered: dict[str, Any] = {}

    def _capture_tool() -> Any:
        def decorator(fn: Any) -> Any:
            registered["fn"] = fn
            return fn

        return decorator

    mcp.tool = _capture_tool

    code_graph_subscriber._register_code_graph_list_tool(mcp)
    return await registered["fn"](repo_path=repo_path, limit=limit)


async def _invoke_code_call_chain(
    symbol_name: str,
    direction: str = "both",
    max_depth: int = 5,
    repo_path: str | None = None,
    edge_filter: list[str] | None = None,
) -> dict[str, Any]:
    mcp = MagicMock()
    registered: dict[str, Any] = {}

    def _capture_tool() -> Any:
        def decorator(fn: Any) -> Any:
            registered["fn"] = fn
            return fn

        return decorator

    mcp.tool = _capture_tool

    code_graph_subscriber._register_code_call_chain_tool(mcp)
    return await registered["fn"](
        symbol_name=symbol_name,
        direction=direction,
        max_depth=max_depth,
        repo_path=repo_path,
        edge_filter=edge_filter,
    )


async def _invoke_code_impact_analysis(
    symbol_name: str,
    repo_path: str | None = None,
    include_indirect: bool = True,
    max_depth: int = 5,
) -> dict[str, Any]:
    mcp = MagicMock()
    registered: dict[str, Any] = {}

    def _capture_tool() -> Any:
        def decorator(fn: Any) -> Any:
            registered["fn"] = fn
            return fn

        return decorator

    mcp.tool = _capture_tool

    code_graph_subscriber._register_code_impact_analysis_tool(mcp)
    return await registered["fn"](
        symbol_name=symbol_name,
        repo_path=repo_path,
        include_indirect=include_indirect,
        max_depth=max_depth,
    )
