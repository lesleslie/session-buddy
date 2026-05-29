"""OTel trace query tools for Session-Buddy.

This module provides MCP tools for querying OTel traces by system_id and
attribute filters (time range, task_class). Used by the Bodai feedback loop
so Session-Buddy can poll traces from all Bodai components.

Uses ReflectionDatabaseAdapterOneiric search_conversations with attribute-based
filtering in Python. HNSW vector index is NOT used for this query.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from session_buddy.utils.error_management import _get_logger

logger = _get_logger()


def _filter_result_by_system_id(result: dict[str, Any], system_id: str) -> bool:
    """Check if result matches system_id filter. Returns True if filtered out."""
    metadata = result.get("metadata", {})
    result_system_id = result.get("system_id") or metadata.get("system_id")
    return result_system_id is not None and result_system_id != system_id


def _filter_result_by_time_range(
    result: dict[str, Any], start_time: str | None, end_time: str | None
) -> bool:
    """Check if result falls outside time range. Returns True if filtered out."""
    if not start_time and not end_time:
        return False

    ts = result.get("timestamp") or result.get("created_at")
    if not ts:
        return False

    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return False

    # Ensure ts is timezone-aware for comparison
    if isinstance(ts, datetime) and ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    if start_time:
        start_dt = datetime.fromisoformat(start_time)
        if ts < start_dt:
            return True
    if end_time:
        end_dt = datetime.fromisoformat(end_time)
        if ts > end_dt:
            return True
    return False


def _filter_result_by_task_class(
    result: dict[str, Any], task_class: str | None
) -> bool:
    """Check if result matches task_class filter. Returns True if filtered out."""
    if not task_class:
        return False

    metadata = result.get("metadata", {})
    attributes = metadata.get("attributes", {})
    task_classes = attributes.get("task.class") or attributes.get("task_class")

    if isinstance(task_classes, list):
        return task_class not in task_classes
    elif task_classes != task_class:
        return metadata.get("task_class") != task_class  # type: ignore[no-any-return]
    return False


async def query_local_traces(
    system_id: str,
    start_time: str | None = None,
    end_time: str | None = None,
    task_class: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query OTel traces by system_id and optional attribute filters.

    Fetches traces for a given system_id within an optional time range,
    and optionally filtered by task.class attribute. Uses the global
    ReflectionDatabaseAdapterOneiric instance (same as Akosha) for storage.

    Args:
        system_id: Source system identifier (e.g., 'mahavishnu', 'akosha')
        start_time: ISO8601 start time (optional)
        end_time: ISO8601 end time (optional)
        task_class: Task classification tag to filter on (optional)
        limit: Maximum number of traces to return (default 100)

    Returns:
        List of trace records matching the filter criteria
    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (  # type: ignore[attr-defined]
            get_reflection_database,
        )

        db = await get_reflection_database()

        results = await db.search_conversations(
            query=system_id,
            limit=limit,
            threshold=0.0,
        )

        filtered = []
        for result in results:
            metadata = result.get("metadata", {})
            attributes = metadata.get("attributes", {})

            if _filter_result_by_system_id(result, system_id):
                continue
            if _filter_result_by_time_range(result, start_time, end_time):
                continue
            if _filter_result_by_task_class(result, task_class):
                continue

            filtered.append(
                {
                    "conversation_id": result.get("id")
                    or result.get("conversation_id"),
                    "content": result.get("content"),
                    "timestamp": str(
                        result.get("timestamp") or result.get("created_at", "")
                    ),
                    "metadata": metadata,
                    "attributes": attributes,
                }
            )

        logger.info(f"query_local_traces: system={system_id}, matched={len(filtered)}")
        return filtered

    except Exception as e:
        logger.exception(f"Error querying traces: {e}")
        return []


def register_otel_trace_tools(mcp_server: Any) -> None:
    """Register OTel trace query tools with MCP server.

    Args:
        mcp_server: FastMCP server instance

    Example:
        >>> from session_buddy.mcp.server import mcp
        >>> register_otel_trace_tools(mcp)
    """
    mcp_server.tool()(query_local_traces)
    logger.info("Registered OTel trace query tools")


__all__ = [
    "query_local_traces",
    "register_otel_trace_tools",
]