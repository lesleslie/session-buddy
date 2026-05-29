"""MCP tools for receiving code graphs from Mahavishnu.

This module provides MCP tools that Mahavishnu can call to store
indexed code graphs in Session-Buddy's reflection database.
"""

from __future__ import annotations

import logging
import operator
import typing as t
from datetime import UTC
from typing import TYPE_CHECKING, Any

from session_buddy.utils.database_tools import require_reflection_database

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _get_lock(reflection_db: Any) -> Any:
    """Get lock from reflection database if available."""
    return (
        reflection_db.lock
        if hasattr(reflection_db, "is_temp_db") and reflection_db.is_temp_db
        else None
    )


def _is_valid_symbol_id(symbol_name: str) -> bool:
    import re

    symbol_id_pattern = re.compile(r"^[^|]+(\|\|\|[^|]+){3}[^|]+$")
    return "|||" not in symbol_name or bool(symbol_id_pattern.match(symbol_name))


def _build_node_map(nodes: list[Any]) -> dict[str, dict[str, Any]]:
    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if isinstance(node, dict):
            node_id: str = node.get("id", node.get("name", "")) or ""
            node_map[node_id] = node
        elif isinstance(node, str):
            node_map[node] = {"id": node, "name": node}
    return node_map


def _find_target_node_id(
    symbol_name: str, node_map: dict[str, dict[str, Any]]
) -> str | None:
    bare_name = symbol_name.split("|||")[-1] if "|||" in symbol_name else symbol_name
    for node_id, node_info in node_map.items():
        node_name = node_info.get("name", node_id)
        if node_name in (symbol_name, bare_name):
            return node_id
    return None


def _load_latest_code_graph_context(
    conn: Any, repo_path: str | None
) -> dict[str, Any] | None:
    if repo_path:
        row = conn.execute(
            """
            SELECT graph_data, indexed_at, nodes_count
            FROM code_graphs
            WHERE repo_path = ?
            ORDER BY indexed_at DESC
            LIMIT 1
            """,
            [repo_path],
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT graph_data, indexed_at, nodes_count, repo_path
            FROM code_graphs
            ORDER BY indexed_at DESC
            LIMIT 1
            """,
        ).fetchone()

    if not row:
        return None

    import json

    return {
        "graph_data": json.loads(row[0]) if row[0] else {},
        "indexed_at": row[1],
        "repo_path": row[3] if len(row) > 3 else repo_path,
    }


def _is_graph_stale(indexed_at: str | None) -> tuple[bool, str | None]:
    if not indexed_at:
        return False, None

    from datetime import datetime

    try:
        indexed_dt = datetime.fromisoformat(indexed_at)
        age_hours = (datetime.now(UTC) - indexed_dt).total_seconds() / 3600
        stale = age_hours > 24
        return stale, indexed_at if stale else None
    except (ValueError, TypeError):
        return False, None


def _normalize_call_edges(edges: list[Any]) -> list[tuple[str, str, str]]:
    call_edges: list[tuple[str, str, str]] = []
    for edge in edges:
        if isinstance(edge, dict):
            source: str = edge.get("source", edge.get("from", ""))  # type: ignore[assignment]
            target: str = edge.get("target", edge.get("to", ""))  # type: ignore[assignment]
            edge_type: str = edge.get("type", edge.get("relation", "calls"))  # type: ignore[assignment]
            call_edges.append((source, target, edge_type))
        elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
            edge_type = edge[2] if len(edge) > 2 else "calls"
            call_edges.append((edge[0], edge[1], edge_type))
    return call_edges


def _traverse_call_chain(
    *,
    target_node_id: str,
    direction: str,
    max_depth: int,
    node_map: dict[str, dict[str, Any]],
    call_edges: list[tuple[str, str, str]],
    edge_filter: list[str] | None,
) -> tuple[list[dict[str, Any]], int, bool]:
    if edge_filter:
        call_edges = [edge for edge in call_edges if edge[2] in edge_filter]

    visited: set[str] = {target_node_id}
    queue: list[tuple[str, int]] = [(target_node_id, 0)]
    result_chains: list[dict[str, Any]] = []
    total_nodes = 0
    truncated = False

    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        for source, target, edge_type in call_edges:
            if (
                direction in ("callers", "both")
                and target == current
                and source not in visited
            ):
                visited.add(source)
                total_nodes += 1
                queue.append((source, depth + 1))
                source_info = node_map.get(source, {"id": source, "name": source})
                result_chains.append(
                    {
                        "symbol": source_info.get("name", source),
                        "direction": "caller",
                        "depth": depth + 1,
                        "edge_type": edge_type,
                        "path": _build_path_str(source_info, current, node_map),
                    }
                )

            if (
                direction in ("callees", "both")
                and source == current
                and target not in visited
            ):
                visited.add(target)
                total_nodes += 1
                queue.append((target, depth + 1))
                target_info = node_map.get(target, {"id": target, "name": target})
                result_chains.append(
                    {
                        "symbol": target_info.get("name", target),
                        "direction": "callee",
                        "depth": depth + 1,
                        "edge_type": edge_type,
                        "path": _build_path_str(target_info, target, node_map),
                    }
                )

        if total_nodes > 500:
            truncated = True
            break

    return result_chains, total_nodes, truncated


def _collect_dependents(
    *,
    target_node_id: str,
    max_depth: int,
    include_indirect: bool,
    node_map: dict[str, dict[str, Any]],
    edges: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    callers_of: dict[str, list[str]] = {}
    for edge in edges:
        if isinstance(edge, dict):
            source: str = edge.get("source", edge.get("from", ""))  # type: ignore[assignment]
            target: str = edge.get("target", edge.get("to", ""))  # type: ignore[assignment]
        elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
            source, target = str(edge[0]), str(edge[1])
        else:
            continue
        callers_of.setdefault(target, []).append(source)

    visited: set[str] = {target_node_id}
    queue: list[tuple[str, int]] = [(target_node_id, 0)]
    direct_dependents: list[dict[str, Any]] = []
    indirect_dependents: list[dict[str, Any]] = []
    affected_files: set[str] = set()

    target_info = node_map.get(target_node_id, {})
    if isinstance(target_info, dict):
        target_file = target_info.get("file", target_info.get("path", ""))
        if target_file:
            affected_files.add(target_file)

    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        for caller_id in callers_of.get(current, []):
            if caller_id in visited:
                continue
            visited.add(caller_id)

            caller_info = node_map.get(caller_id, {"id": caller_id, "name": caller_id})
            caller_name = (
                caller_info.get("name", caller_id)
                if isinstance(caller_info, dict)
                else caller_id
            )
            caller_file = (
                caller_info.get("file", caller_info.get("path", ""))
                if isinstance(caller_info, dict)
                else ""
            )
            if caller_file:
                affected_files.add(caller_file)

            entry = {
                "symbol": caller_name,
                "node_id": caller_id,
                "depth": depth + 1,
                "file": caller_file,
            }

            if depth == 0:
                direct_dependents.append(entry)
            elif include_indirect:
                indirect_dependents.append(entry)

            if include_indirect:
                queue.append((caller_id, depth + 1))

    return direct_dependents, indirect_dependents, affected_files


def _register_code_graph_storage_tool(mcp: Any) -> None:
    """Register code graph storage tool."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def store_code_graph_from_mahavishnu(
        repo_path: str,
        commit_hash: str,
        indexed_at: str,
        nodes_count: int,
        graph_data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Store a code graph indexed by Mahavishnu.

        This tool is called by Mahavishnu after successfully indexing
        a repository to store the code graph in Session-Buddy's
        reflection database for later pattern analysis by Akosha.

        Args:
            repo_path: Path to the repository that was indexed
            commit_hash: Git commit hash for this code graph
            indexed_at: ISO timestamp when indexing was completed
            nodes_count: Number of nodes in the code graph
            graph_data: Complete code graph data (nodes, edges, etc.)
            metadata: Optional metadata dictionary

        Returns:
            Dict with status, graph_id, and message

        Example:
            >>> result = await store_code_graph_from_mahavishnu(
            ...     repo_path="/path/to/repo",
            ...     commit_hash="abc123",
            ...     indexed_at="2025-02-03T12:00:00Z",
            ...     nodes_count=1234,
            ...     graph_data={"nodes": [...], "edges": [...]}
            ... )
            >>> print(result["graph_id"])
            /path/to/repo:abc123
        """
        from session_buddy.reflection.storage import store_code_graph

        try:
            reflection_db = await require_reflection_database()
            graph_id = await store_code_graph(
                db=reflection_db,
                repo_path=repo_path,
                commit_hash=commit_hash,
                indexed_at=indexed_at,
                nodes_count=nodes_count,
                graph_data=graph_data,
                metadata=metadata,
                lock=_get_lock(reflection_db),
            )

            logger.info(
                f"Stored code graph from Mahavishnu: {repo_path} @ {commit_hash[:8]} "
                f"({nodes_count} nodes)"
            )

            return {
                "status": "success",
                "graph_id": graph_id,
                "message": f"Code graph stored for {repo_path} @ {commit_hash[:8]}",
            }

        except Exception as e:
            logger.error(f"Failed to store code graph from Mahavishnu: {e}")
            return {
                "status": "error",
                "graph_id": "",
                "message": f"Failed to store code graph: {e}",
            }


def _query_code_graph(
    conn: Any, repo_path: str, commit_hash: str
) -> dict[str, Any] | None:
    """Query code graph from database.

    Args:
        conn: Database connection
        repo_path: Repository path
        commit_hash: Git commit hash

    Returns:
        Code graph dict or None if not found
    """
    result = conn.execute(
        """
        SELECT id, repo_path, commit_hash, indexed_at, nodes_count, graph_data, metadata
        FROM code_graphs
        WHERE repo_path = ? AND commit_hash = ?
        """,
        [repo_path, commit_hash],
    ).fetchone()

    if not result:
        return None

    import json

    return {
        "id": result[0],
        "repo_path": result[1],
        "commit_hash": result[2],
        "indexed_at": result[3],
        "nodes_count": result[4],
        "graph_data": json.loads(result[5]) if result[5] else {},
        "metadata": json.loads(result[6]) if result[6] else {},
    }


def _query_code_graphs_list(
    conn: Any, repo_path: str | None, limit: int
) -> list[dict[str, Any]]:
    """Query code graphs list from database.

    Args:
        conn: Database connection
        repo_path: Optional repository path filter
        limit: Maximum number of results

    Returns:
        List of code graph dicts
    """
    if repo_path:
        result = conn.execute(
            """
            SELECT id, repo_path, commit_hash, indexed_at, nodes_count
            FROM code_graphs
            WHERE repo_path = ?
            ORDER BY indexed_at DESC
            LIMIT ?
            """,
            [repo_path, limit],
        ).fetchall()
    else:
        result = conn.execute(
            """
            SELECT id, repo_path, commit_hash, indexed_at, nodes_count
            FROM code_graphs
            ORDER BY indexed_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

    return [
        {
            "id": row[0],
            "repo_path": row[1],
            "commit_hash": row[2],
            "indexed_at": row[3],
            "nodes_count": row[4],
        }
        for row in result
    ]


def _register_code_graph_retrieval_tool(mcp: Any) -> None:
    """Register code graph retrieval tool."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def get_code_graph(
        repo_path: str,
        commit_hash: str,
    ) -> dict[str, Any]:
        """Retrieve a code graph from the reflection database.

        Args:
            repo_path: Path to the repository
            commit_hash: Git commit hash

        Returns:
            Dict with code graph data or error message

        Example:
            >>> graph = await get_code_graph(
            ...     repo_path="/path/to/repo",
            ...     commit_hash="abc123"
            ... )
            >>> print(graph["nodes_count"])
            1234
        """
        try:
            reflection_db = await require_reflection_database()
            conn = (
                reflection_db
                if hasattr(reflection_db, "execute")
                else t.cast(Any, reflection_db)._get_conn()
            )

            import asyncio

            def _query() -> dict[str, Any] | None:
                return _query_code_graph(conn, repo_path, commit_hash)

            lock = _get_lock(reflection_db)
            if lock:
                with lock:
                    graph_record = _query()
            else:
                loop = asyncio.get_event_loop()
                graph_record = await loop.run_in_executor(None, _query)

            if not graph_record:
                return {
                    "status": "not_found",
                    "message": f"No code graph found for {repo_path} @ {commit_hash[:8]}",
                }

            return {
                "status": "success",
                **graph_record,
            }

        except Exception as e:
            logger.error(f"Failed to retrieve code graph: {e}")
            return {
                "status": "error",
                "message": f"Failed to retrieve code graph: {e}",
            }


def _register_code_graph_list_tool(mcp: Any) -> None:
    """Register code graph listing tool."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def list_code_graphs(
        repo_path: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List code graphs in the reflection database.

        Args:
            repo_path: Optional filter by repository path
            limit: Maximum number of results

        Returns:
            Dict with list of code graphs

        Example:
            >>> result = await list_code_graphs(repo_path="/path/to/repo")
            >>> print(f"Found {result['count']} code graphs")
        """
        try:
            reflection_db = await require_reflection_database()
            conn = (
                reflection_db
                if hasattr(reflection_db, "execute")
                else t.cast(Any, reflection_db)._get_conn()
            )

            import asyncio

            def _query() -> list[dict[str, Any]]:
                return _query_code_graphs_list(conn, repo_path, limit)

            lock = _get_lock(reflection_db)
            if lock:
                with lock:
                    graphs = _query()
            else:
                loop = asyncio.get_event_loop()
                graphs = await loop.run_in_executor(None, _query)

            return {
                "status": "success",
                "count": len(graphs),
                "code_graphs": graphs,
            }

        except Exception as e:
            logger.error(f"Failed to list code graphs: {e}")
            return {
                "status": "error",
                "message": f"Failed to list code graphs: {e}",
                "count": 0,
                "code_graphs": [],
            }


def _register_code_call_chain_tool(mcp: Any) -> None:
    """Register the code_call_chain query tool."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def code_call_chain(
        symbol_name: str,
        direction: str = "both",
        max_depth: int = 5,
        repo_path: str | None = None,
        edge_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resolve transitive callers/callees of a symbol in the code graph.

        Traverses the stored code graph to find who calls a symbol (callers)
        and what the symbol calls (callees), up to *max_depth* hops.

        Args:
            symbol_name: Qualified symbol ID or bare name (use repo_path to disambiguate)
            direction: "callers", "callees", or "both"
            max_depth: Maximum traversal depth (1-10, default 5)
            repo_path: Disambiguate bare symbol_name
            edge_filter: Filter by edge types (e.g. ["calls", "imports"])

        Returns:
            Dict with root_symbol, chains, total_nodes, truncated, and staleness info.
        """
        max_depth = min(max_depth, 10)

        if not _is_valid_symbol_id(symbol_name):
            return {
                "error": "Invalid symbol ID format",
                "detail": symbol_name,
            }

        try:
            reflection_db = await require_reflection_database()
            conn = (
                reflection_db
                if hasattr(reflection_db, "execute")
                else _get_conn(reflection_db)
            )

            context = _load_latest_code_graph_context(conn, repo_path)
            if context is None:
                return {
                    "root_symbol": symbol_name,
                    "chains": [],
                    "total_nodes": 0,
                    "truncated": False,
                    "stale": False,
                    "message": "No code graphs found in database",
                }

            graph_data = context["graph_data"]
            indexed_at = context["indexed_at"]
            graph_repo_path = context["repo_path"]
            node_map = _build_node_map(graph_data.get("nodes", []))
            target_node_id = _find_target_node_id(symbol_name, node_map)

            if not target_node_id:
                return {
                    "root_symbol": symbol_name,
                    "chains": [],
                    "total_nodes": 0,
                    "truncated": False,
                    "stale": False,
                    "message": f"Symbol '{symbol_name}' not found in code graph "
                    f"for {graph_repo_path}",
                }

            result_chains, total_nodes, truncated = _traverse_call_chain(
                target_node_id=target_node_id,
                direction=direction,
                max_depth=max_depth,
                node_map=node_map,
                call_edges=_normalize_call_edges(graph_data.get("edges", [])),
                edge_filter=edge_filter,
            )
            stale, last_indexed_at = _is_graph_stale(indexed_at)

            return {
                "root_symbol": symbol_name,
                "root_node_id": target_node_id,
                "repo_path": graph_repo_path,
                "chains": result_chains,
                "total_nodes": total_nodes,
                "truncated": truncated,
                "stale": stale,
                "last_indexed_at": last_indexed_at,
            }

        except Exception as e:
            logger.error(f"Failed to resolve call chain for '{symbol_name}': {e}")
            return {
                "root_symbol": symbol_name,
                "chains": [],
                "total_nodes": 0,
                "truncated": False,
                "stale": False,
                "error": str(e),
            }


def _register_code_impact_analysis_tool(mcp: Any) -> None:
    """Register the code_impact_analysis query tool."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def code_impact_analysis(
        symbol_name: str,
        repo_path: str | None = None,
        include_indirect: bool = True,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Analyze the impact of changing a symbol -- what depends on it?

        Walks the code graph in the caller direction to enumerate all symbols
        that directly or transitively depend on *symbol_name*.

        Args:
            symbol_name: Qualified symbol ID or bare name (use repo_path to disambiguate)
            repo_path: Disambiguate bare symbol_name
            include_indirect: Include transitive dependents
            max_depth: Maximum traversal depth (1-10, default 5)

        Returns:
            Dict with direct_dependents, indirect_dependents, affected_files,
            risk_level, blast_radius, and staleness info.
        """
        max_depth = min(max_depth, 10)

        if not _is_valid_symbol_id(symbol_name):
            return {
                "error": "Invalid symbol ID format",
                "detail": symbol_name,
            }

        try:
            reflection_db = await require_reflection_database()
            conn = (
                reflection_db
                if hasattr(reflection_db, "execute")
                else _get_conn(reflection_db)
            )

            context = _load_latest_code_graph_context(conn, repo_path)
            if context is None:
                return {
                    "target": symbol_name,
                    "direct_dependents": [],
                    "indirect_dependents": [],
                    "affected_files": [],
                    "risk_level": "low",
                    "blast_radius": 0,
                    "stale": False,
                    "message": "No code graphs found in database",
                }

            graph_data = context["graph_data"]
            indexed_at = context["indexed_at"]
            graph_repo_path = context["repo_path"]
            node_map = _build_node_map(graph_data.get("nodes", []))
            target_node_id = _find_target_node_id(symbol_name, node_map)

            if not target_node_id:
                return {
                    "target": symbol_name,
                    "direct_dependents": [],
                    "indirect_dependents": [],
                    "affected_files": [],
                    "risk_level": "low",
                    "blast_radius": 0,
                    "stale": False,
                    "message": f"Symbol '{symbol_name}' not found in code graph "
                    f"for {graph_repo_path}",
                }

            direct_dependents, indirect_dependents, affected_files = (
                _collect_dependents(
                    target_node_id=target_node_id,
                    max_depth=max_depth,
                    include_indirect=include_indirect,
                    node_map=node_map,
                    edges=graph_data.get("edges", []),
                )
            )

            blast_radius = len(direct_dependents) + len(indirect_dependents)
            if blast_radius == 0:
                risk_level = "low"
            elif blast_radius <= 5:
                risk_level = "medium"
            elif blast_radius <= 20:
                risk_level = "high"
            else:
                risk_level = "critical"

            stale, last_indexed_at = _is_graph_stale(indexed_at)

            return {
                "target": symbol_name,
                "target_node_id": target_node_id,
                "repo_path": graph_repo_path,
                "direct_dependents": direct_dependents,
                "indirect_dependents": indirect_dependents,
                "affected_files": sorted(affected_files),
                "risk_level": risk_level,
                "blast_radius": blast_radius,
                "stale": stale,
                "last_indexed_at": last_indexed_at,
            }

        except Exception as e:
            logger.error(f"Failed to analyze impact for '{symbol_name}': {e}")
            return {
                "target": symbol_name,
                "direct_dependents": [],
                "indirect_dependents": [],
                "affected_files": [],
                "risk_level": "low",
                "blast_radius": 0,
                "stale": False,
                "error": str(e),
            }


def _get_conn(reflection_db: Any) -> Any:
    """Get the underlying connection from a reflection database wrapper."""
    import typing as t

    return t.cast(Any, reflection_db)._get_conn()


def _build_path_str(
    from_info: dict[str, Any] | str,
    to_id: str,
    node_map: dict[str, dict[str, Any]],
) -> str:
    """Build a human-readable path string for a chain entry."""
    from_name = (
        from_info.get("name", str(from_info))
        if isinstance(from_info, dict)
        else str(from_info)
    )
    to_info = node_map.get(to_id, {"name": to_id})
    to_name = to_info.get("name", to_id) if isinstance(to_info, dict) else str(to_info)
    return f"{from_name} -> {to_name}"


def register_code_graph_tools(mcp: Any) -> None:
    """Register code graph storage and query tools with MCP server.

    Args:
        mcp: FastMCP server instance

    Example:
        >>> from fastmcp import FastMCP
        >>>
        >>> mcp = FastMCP("session-buddy")
        >>> register_code_graph_tools(mcp)
    """
    _register_code_graph_storage_tool(mcp)
    _register_code_graph_retrieval_tool(mcp)
    _register_code_graph_list_tool(mcp)
    _register_code_call_chain_tool(mcp)
    _register_code_impact_analysis_tool(mcp)
