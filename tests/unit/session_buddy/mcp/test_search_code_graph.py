"""Unit tests for Session-Buddy code-graph read-through facade.

Task 6 of the 2026-07-29 Session-Buddy extension plan (Q4: code-graph
consolidation). The ``search_code_graph`` MCP tool is a read-through
facade over the canonical ``code_graphs`` v2 table.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def _hit(
    repo_path: str = "/path/to/repo",
    symbol: str = "func_alpha",
    project: str = "myproj",
    call_count: int = 3,
    last_seen_at: str = "2026-07-29T12:00:00Z",
) -> dict[str, Any]:
    """Build a code_graphs-shaped row for use in fixture data."""
    return {
        "repo_path": repo_path,
        "symbol": symbol,
        "project": project,
        "call_count": call_count,
        "last_seen_at": last_seen_at,
    }


def test_search_code_graph_returns_dataclass_list() -> None:
    """search_code_graph converts SQL rows to CodeGraphHit dataclasses."""
    import asyncio

    from session_buddy.mcp.tools.code_graph import (
        CodeGraphHit,
        search_code_graph,
    )

    db = AsyncMock()
    db.search_code_graph_nodes = AsyncMock(
        return_value=[
            _hit(symbol="func_alpha"),
            _hit(symbol="func_beta"),
        ]
    )

    hits = asyncio.run(search_code_graph(query="func", project="myproj", db=db))

    assert len(hits) == 2
    assert all(isinstance(h, CodeGraphHit) for h in hits)
    assert hits[0].symbol == "func_alpha"
    assert hits[1].symbol == "func_beta"
    assert hits[0].repo_path == "/path/to/repo"
    assert hits[0].project == "myproj"
    assert hits[0].call_count == 3


def test_search_code_graph_respects_limit() -> None:
    """search_code_graph forwards limit to the underlying query."""
    import asyncio

    from session_buddy.mcp.tools.code_graph import search_code_graph

    db = AsyncMock()
    db.search_code_graph_nodes = AsyncMock(return_value=[])

    asyncio.run(search_code_graph(query="func", project="myproj", limit=50, db=db))

    db.search_code_graph_nodes.assert_awaited_once()
    await_args = db.search_code_graph_nodes.await_args
    assert await_args is not None
    call_kwargs = await_args.kwargs
    assert call_kwargs["limit"] == 50
    assert call_kwargs["query"] == "func"
    assert call_kwargs["project"] == "myproj"


def test_search_code_graph_caps_default_limit_at_50() -> None:
    """search_code_graph defaults to limit=50."""
    import asyncio

    from session_buddy.mcp.tools.code_graph import search_code_graph

    db = AsyncMock()
    db.search_code_graph_nodes = AsyncMock(return_value=[])

    asyncio.run(search_code_graph(query="anything", project="myproj", db=db))

    await_args = db.search_code_graph_nodes.await_args
    assert await_args is not None
    call_kwargs = await_args.kwargs
    assert call_kwargs["limit"] == 50


def test_search_code_graph_caps_oversized_limit_at_50() -> None:
    """search_code_graph caps an oversized limit at 50."""
    import asyncio

    from session_buddy.mcp.tools.code_graph import search_code_graph

    db = AsyncMock()
    db.search_code_graph_nodes = AsyncMock(return_value=[])

    asyncio.run(search_code_graph(query="anything", project="myproj", limit=500, db=db))

    await_args = db.search_code_graph_nodes.await_args
    assert await_args is not None
    call_kwargs = await_args.kwargs
    assert call_kwargs["limit"] == 50


def test_search_code_graph_returns_up_to_50_hits_against_real_db() -> None:
    """When 60 rows exist, search_code_graph returns at most 50."""
    import asyncio
    import tempfile
    from pathlib import Path

    import duckdb

    from session_buddy.mcp.tools.code_graph import search_code_graph
    from session_buddy.reflection.schema import initialize_schema

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "code_graph.duckdb"
        conn = duckdb.connect(str(db_path))
        try:
            initialize_schema(conn)
            for i in range(60):
                conn.execute(
                    """
                    INSERT INTO code_graphs
                    (id, repo_path, commit_hash, indexed_at, nodes_count, graph_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        f"repo:commit_{i}",
                        "repo",
                        f"commit_{i}",
                        "2026-07-29T12:00:00Z",
                        100,
                        "{}",
                    ],
                )
        finally:
            conn.close()

        class _FakeDB:
            def __init__(self, path: Path) -> None:
                self._path = path

            def _get_conn(self) -> Any:
                return duckdb.connect(str(self._path))

            @property
            def lock(self) -> Any:
                return None

            async def search_code_graph_nodes(
                self, *, query: str, project: str, limit: int = 50
            ) -> list[dict[str, Any]]:
                conn = duckdb.connect(str(self._path))
                rows = conn.execute(
                    """
                    SELECT repo_path, commit_hash, indexed_at, nodes_count
                    FROM code_graphs
                    LIMIT ?
                    """,
                    [limit],
                ).fetchall()
                return [
                    {
                        "repo_path": r[0],
                        "symbol": r[1],
                        "project": project,
                        "call_count": r[3],
                        "last_seen_at": str(r[2]),
                    }
                    for r in rows
                ]

        fake_db = _FakeDB(db_path)
        hits = asyncio.run(
            search_code_graph(query="commit", project="myproj", db=fake_db)
        )
        assert len(hits) <= 50
        assert all(h.project == "myproj" for h in hits)


def test_search_code_graph_handles_empty_results() -> None:
    """search_code_graph returns empty list when no rows match."""
    import asyncio

    from session_buddy.mcp.tools.code_graph import search_code_graph

    db = AsyncMock()
    db.search_code_graph_nodes = AsyncMock(return_value=[])

    hits = asyncio.run(search_code_graph(query="missing", project="myproj", db=db))

    assert hits == []


def test_search_via_sql_extracts_real_symbol_from_graph_data() -> None:
    """The SQL fallback must surface a real symbol (from nodes[0].name) rather
    than reusing commit_hash.

    Test setup: ``repo_path`` and ``commit_hash`` are identical strings, but
    ``graph_data`` carries a node with a real name. The old code mapped
    ``commit_hash`` -> ``symbol`` so today's symbol == repo_path; the fix
    extracts ``nodes[0].name`` so symbol != repo_path.
    """
    import asyncio
    import tempfile
    from pathlib import Path

    import duckdb

    from session_buddy.mcp.tools.code_graph import _search_via_sql
    from session_buddy.reflection.schema import initialize_schema

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "code_graph.duckdb"
        conn = duckdb.connect(str(db_path))
        try:
            initialize_schema(conn)
            conn.execute(
                """
                INSERT INTO code_graphs
                (id, repo_path, commit_hash, indexed_at, nodes_count, graph_data)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    "repo:abc123",
                    "repo",  # repo_path
                    "repo",  # commit_hash -- same as repo_path
                    "2026-07-29T12:00:00Z",
                    1,
                    '{"nodes": [{"id": "n1", "name": "func_alpha"}]}',
                ],
            )
        finally:
            conn.close()

        class _DBWithoutMethod:
            def __init__(self, path: Path) -> None:
                self._path = path

            def _get_conn(self) -> Any:
                return duckdb.connect(str(self._path))

        rows = asyncio.run(
            _search_via_sql(
                _DBWithoutMethod(db_path), query="repo", project="proj", limit=10
            )
        )

        assert len(rows) == 1
        assert rows[0]["repo_path"] == "repo"
        assert rows[0]["symbol"] != rows[0]["repo_path"]  # fails today
        assert rows[0]["symbol"] == "func_alpha"


def test_search_via_sql_falls_back_to_commit_hash_when_nodes_empty() -> None:
    """When ``graph_data`` has no nodes, ``symbol`` falls back to ``commit_hash``.

    The fallback keeps the surface usable for legacy rows that predate the
    nodes[] convention; it is still distinguishable from a real symbol
    only because the upstream callers should normally exercise the
    ``search_code_graph_nodes`` adapter path first.
    """
    import asyncio
    import tempfile
    from pathlib import Path

    import duckdb

    from session_buddy.mcp.tools.code_graph import _search_via_sql
    from session_buddy.reflection.schema import initialize_schema

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "code_graph.duckdb"
        conn = duckdb.connect(str(db_path))
        try:
            initialize_schema(conn)
            conn.execute(
                """
                INSERT INTO code_graphs
                (id, repo_path, commit_hash, indexed_at, nodes_count, graph_data)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    "repo:abc123",
                    "myrepo",
                    "deadbeef",
                    "2026-07-29T12:00:00Z",
                    0,
                    '{"nodes": []}',
                ],
            )
        finally:
            conn.close()

        class _DBWithoutMethod:
            def __init__(self, path: Path) -> None:
                self._path = path

            def _get_conn(self) -> Any:
                return duckdb.connect(str(self._path))

        rows = asyncio.run(
            _search_via_sql(
                _DBWithoutMethod(db_path), query="myrepo", project="proj", limit=10
            )
        )

        assert len(rows) == 1
        assert rows[0]["symbol"] == "deadbeef"
