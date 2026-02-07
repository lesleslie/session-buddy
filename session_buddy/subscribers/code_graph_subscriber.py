"""MCP tools for receiving code graphs from Mahavishnu.

This module provides MCP tools that Mahavishnu can call to store
indexed code graphs in Session-Buddy's reflection database.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from session_buddy.utils.database_tools import require_reflection_database

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

logger = logging.getLogger(__name__)


def _get_lock(reflection_db: Any) -> Any:
    """Get lock from reflection database if available."""
    return reflection_db.lock if hasattr(reflection_db, "is_temp_db") and reflection_db.is_temp_db else None


def _register_code_graph_storage_tool(mcp: Any) -> None:
    """Register code graph storage tool."""

    @mcp.tool()  # type: ignore[misc]
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


def _query_code_graph(conn: Any, repo_path: str, commit_hash: str) -> dict[str, Any] | None:
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


def _query_code_graphs_list(conn: Any, repo_path: str | None, limit: int) -> list[dict[str, Any]]:
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

    @mcp.tool()  # type: ignore[misc]
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
            conn = reflection_db if hasattr(reflection_db, "execute") else typing.cast(Any, reflection_db)._get_conn()  # type: ignore[union-attr]

            import asyncio

            def _query() -> list[dict[str, Any]]:
                return _query_code_graph(conn, repo_path, commit_hash)

            lock = _get_lock(reflection_db)
            if lock:
                with lock:
                    graph_record = _query()  # type: ignore[no-untyped-call]
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

    @mcp.tool()  # type: ignore[misc]
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
            conn = reflection_db if hasattr(reflection_db, "execute") else typing.cast(Any, reflection_db)._get_conn()  # type: ignore[union-attr]

            import asyncio

            def _query() -> list[dict[str, Any]]:
                return _query_code_graphs_list(conn, repo_path, limit)

            lock = _get_lock(reflection_db)
            if lock:
                with lock:
                    graphs = _query()  # type: ignore[no-untyped-call]
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


def register_code_graph_tools(mcp: Any) -> None:
    """Register code graph storage tools with MCP server.

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
