"""Session-Buddy MCP tool: search_code_graph.

Read-through facade over the canonical ``code_graphs`` v2 table. Akosha's
``search_code_patterns`` and Mahavishnu's ``treesitter_*`` shims call this
instead of running their own DuckDB queries.

Spec: docs/superpowers/specs/2026-07-29-session-buddy-extension-design.md
(Q4: code-graph consolidation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


class CodeGraphSearchable(Protocol):
    """Duck-typed contract for objects that can serve ``search_code_graph_nodes``.

    The real ``ReflectionDatabaseAdapter`` exposes this method; tests can pass
    any object that implements the same surface (sync or async callable).
    """

    def search_code_graph_nodes(
        self,
        *,
        query: str,
        project: str,
        limit: int,
    ) -> Any: ...


@dataclass
class CodeGraphHit:
    """A single code-graph search hit."""

    repo_path: str
    symbol: str
    project: str
    call_count: int
    last_seen_at: str


async def search_code_graph(
    query: str,
    project: str,
    limit: int = 50,
    *,
    db: CodeGraphSearchable | None = None,
) -> list[CodeGraphHit]:
    """Search the canonical code graph for symbols matching ``query`` in ``project``.

    Args:
        query: Free-text symbol or pattern to match.
        project: Project scope to search within.
        limit: Maximum number of hits to return (capped at 50 by default).
        db: Optional injected reflection database. When ``None`` (default) the
            canonical reflection database is resolved lazily. Tests inject a
            mock ``db`` with a ``search_code_graph_nodes`` method.

    Returns:
        Up to ``limit`` ``CodeGraphHit`` records sorted by relevance (call-graph
        proximity, then alpha). When the underlying accessor is unavailable or
        returns empty rows, the result is an empty list.
    """
    limit = min(limit, 50)

    resolved_db = db if db is not None else await _resolve_default_db()
    if resolved_db is None:
        return []

    rows: list[dict[str, Any]] = []
    if hasattr(resolved_db, "search_code_graph_nodes"):
        search = resolved_db.search_code_graph_nodes
        rows = await _await_search(search, query=query, project=project, limit=limit)
    else:
        rows = await _search_via_sql(
            resolved_db, query=query, project=project, limit=limit
        )

    return [
        CodeGraphHit(
            repo_path=str(r.get("repo_path", "")),
            symbol=str(r.get("symbol", "")),
            project=str(r.get("project", project)),
            call_count=int(r.get("call_count", 0)),
            last_seen_at=str(r.get("last_seen_at", "")),
        )
        for r in rows
    ]


async def _resolve_default_db() -> ReflectionDatabaseAdapter | None:
    """Resolve the canonical reflection database, returning None if unavailable."""
    try:
        from session_buddy.utils.database_tools import require_reflection_database
    except ImportError:
        return None
    try:
        return await require_reflection_database()
    except RuntimeError, ConnectionError, OSError:
        return None


async def _await_search(
    search: Any, *, query: str, project: str, limit: int
) -> list[dict[str, Any]]:
    """Call ``search_code_graph_nodes`` whether it's sync or async."""
    result = search(query=query, project=project, limit=limit)
    if hasattr(result, "__await__"):
        result = await result
    return list(result) if result else []


async def _search_via_sql(
    db: Any,
    *,
    query: str,
    project: str,
    limit: int,
) -> list[dict[str, Any]]:
    """SQL fallback when the db doesn't expose ``search_code_graph_nodes``.

    Returns dict-shaped rows compatible with the ``CodeGraphHit`` mapping.
    Surfaces a real symbol by parsing ``graph_data.nodes[0].name``; when
    the JSON payload has no nodes (legacy rows that predate the
    ``nodes[]`` convention), ``symbol`` falls back to ``commit_hash`` so
    the row is still representable.
    """
    try:
        import asyncio
        import json

        conn = db if hasattr(db, "execute") else db._get_conn()

        def _query() -> list[Any]:
            like = f"%{query}%"
            sql = (
                "SELECT repo_path, commit_hash, indexed_at, nodes_count, graph_data "
                "FROM code_graphs "
                "WHERE repo_path LIKE ? "
                "ORDER BY indexed_at DESC LIMIT ?"
            )
            result = conn.execute(sql, [like, limit]).fetchall()
            return list(result)

        rows = await asyncio.get_running_loop().run_in_executor(None, _query)
    except RuntimeError, ConnectionError, OSError:
        return []

    hits: list[dict[str, Any]] = []
    for r in rows:
        symbol = ""
        try:
            graph_data = json.loads(r[4]) if len(r) > 4 and r[4] else {}
            nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
            if nodes and isinstance(nodes[0], dict):
                symbol = str(nodes[0].get("name", "") or "")
        except TypeError, ValueError:
            # Malformed graph_data JSON; fall through to commit_hash.
            symbol = ""
        if not symbol:
            symbol = str(r[1])  # commit_hash fallback
        hits.append(
            {
                "repo_path": str(r[0]),
                "symbol": symbol,
                "project": project,
                "call_count": int(r[3]) if len(r) > 3 else 0,
                "last_seen_at": str(r[2]) if len(r) > 2 else "",
            }
        )
    return hits


__all__ = ["CodeGraphHit", "search_code_graph"]
