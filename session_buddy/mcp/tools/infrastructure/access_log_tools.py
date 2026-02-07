#!/usr/bin/env python3
"""MCP tools for memory access log statistics."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_access_log_tools(mcp: FastMCP) -> None:
    @mcp.tool()  # type: ignore[no-untyped-call]
    async def access_log_stats(
        hours: int = 24,
        top_n: int = 10,
        project: str | None = None,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Return access statistics from memory_access_log.

        Filters by time window and optional project/namespace.
        """
        try:
            import duckdb

            from session_buddy.settings import get_database_path

            db_path = get_database_path()
            cutoff = datetime.now() - timedelta(hours=hours)

            with duckdb.connect(
                db_path, config={"allow_unsigned_extensions": True}
            ) as conn:
                query_config = _build_query_config(cutoff, project, namespace)

                total_accesses = _get_total_accesses(conn, query_config)
                distinct_memories = _get_distinct_memories(conn, query_config)
                by_type = _get_access_type_stats(conn, query_config)
                by_provider = _get_provider_stats(by_type)
                top_memories = _get_top_memories(conn, query_config, top_n)
                recent = _get_recent_accesses(conn, query_config, top_n)

                return {
                    "window_hours": hours,
                    "total_accesses": total_accesses,
                    "distinct_memories": distinct_memories,
                    "by_type": by_type,
                    "by_provider": by_provider,
                    "top_memories": top_memories,
                    "recent": recent,
                    "filters": {"project": project, "namespace": namespace},
                }
        except Exception as e:
            return {
                "error": f"Access log stats unavailable: {e}",
                "hint": "Ensure schema_v2 is enabled and memory_access_log exists.",
            }


def _build_query_config(
    cutoff: datetime, project: str | None, namespace: str | None
) -> dict[str, Any]:
    """Build configuration for queries."""
    where = "l.timestamp >= ?"
    params: list[Any] = [cutoff]
    if project or namespace:
        where += " AND c.id = l.memory_id"
    if project:
        where += " AND c.project = ?"
        params.append(project)
    if namespace:
        where += " AND c.namespace = ?"
        params.append(namespace)

    join_clause = (
        "JOIN conversations_v2 c ON c.id=l.memory_id" if (project or namespace) else ""
    )

    return {"where": where, "params": params, "join_clause": join_clause}


def _get_total_accesses(conn: Any, config: dict[str, Any]) -> int:
    """Get total access count."""
    total_sql = f"SELECT COUNT(*) FROM memory_access_log l {config['join_clause']} WHERE {config['where']}"
    total_result = conn.execute(total_sql, config["params"]).fetchone()
    return int(total_result[0]) if total_result else 0


def _get_distinct_memories(conn: Any, config: dict[str, Any]) -> int:
    """Get distinct memories count."""
    distinct_sql = f"SELECT COUNT(DISTINCT l.memory_id) FROM memory_access_log l {config['join_clause']} WHERE {config['where']}"
    distinct_result = conn.execute(distinct_sql, config["params"]).fetchone()
    return int(distinct_result[0]) if distinct_result else 0


def _get_access_type_stats(conn: Any, config: dict[str, Any]) -> dict[str, int]:
    """Get access type statistics."""
    by_type_sql = f"SELECT l.access_type, COUNT(*) FROM memory_access_log l {config['join_clause']} WHERE {config['where']} GROUP BY l.access_type"
    by_type_rows = conn.execute(by_type_sql, config["params"]).fetchall()
    return {str(r[0] or ""): int(r[1]) for r in by_type_rows}


def _get_provider_stats(by_type: dict[str, int]) -> dict[str, int]:
    """Parse provider usage from access type."""
    by_provider: dict[str, int] = {}
    for k, v in by_type.items():
        if k.startswith("extract:"):
            prov = k.split(":", 1)[1] or "unknown"
            by_provider[prov] = by_provider.get(prov, 0) + v
    return by_provider


def _get_top_memories(
    conn: Any, config: dict[str, Any], top_n: int
) -> list[dict[str, Any]]:
    """Get top accessed memories."""
    top_sql = f"""
        SELECT l.memory_id,
               COUNT(*) AS cnt,
               MAX(l.timestamp) AS last_access,
               c.category,
               c.memory_tier,
               c.importance_score,
               c.project,
               c.namespace
        FROM memory_access_log l
        JOIN conversations_v2 c ON c.id = l.memory_id
        WHERE {config["where"]}
        GROUP BY l.memory_id, c.category, c.memory_tier, c.importance_score, c.project, c.namespace
        ORDER BY cnt DESC, last_access DESC
        LIMIT ?
        """
    top_params = [*config["params"], top_n]
    top_rows = conn.execute(top_sql, top_params).fetchall()
    return [
        {
            "memory_id": str(r[0]),
            "count": int(r[1]),
            "last_access": str(r[2]),
            "category": str(r[3]) if r[3] is not None else None,
            "memory_tier": str(r[4]) if r[4] is not None else None,
            "importance_score": float(r[5]) if r[5] is not None else None,
            "project": str(r[6]) if r[6] is not None else None,
            "namespace": str(r[7]) if r[7] is not None else None,
        }
        for r in top_rows
    ]


def _get_recent_accesses(
    conn: Any, config: dict[str, Any], top_n: int
) -> list[dict[str, Any]]:
    """Get recent access samples."""
    recent_sql = f"""
        SELECT l.memory_id, l.access_type, l.timestamp
        FROM memory_access_log l {config["join_clause"]}
        WHERE {config["where"]}
        ORDER BY l.timestamp DESC
        LIMIT ?
        """
    recent_params = [*config["params"], top_n]
    recent_rows = conn.execute(recent_sql, recent_params).fetchall()
    return [
        {
            "memory_id": str(r[0]),
            "access_type": str(r[1]) if r[1] is not None else None,
            "timestamp": str(r[2]),
        }
        for r in recent_rows
    ]
