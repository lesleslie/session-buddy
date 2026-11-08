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


def _filter_result_by_system_id(result: dict[str, Any], system_id: str | None) -> bool:
    """Check if result matches system_id filter. Returns True if filtered out.

    ``None``, ``""`` and ``"*"`` all mean "do not filter by system" — the
    same sentinel the Akosha and Mahavishnu trace tools accept.
    """
    if not system_id or system_id == "*":
        return False
    metadata = result.get("metadata", {})
    result_system_id = result.get("system_id") or metadata.get("system_id")
    return result_system_id is not None and result_system_id != system_id


def _parse_window_bound(value: str) -> datetime | None:
    """Parse an ISO8601 window bound into a UTC-aware datetime.

    A bound with no offset is read as UTC, matching how the trace store
    writes timestamps; a bound with an offset is converted to UTC. Returns
    ``None`` when the value does not parse, so the caller treats the bound
    as absent instead of raising.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
        ts = _parse_window_bound(ts)
        if ts is None:
            return False
    elif isinstance(ts, datetime):
        # Ensure ts is timezone-aware, and in UTC, for comparison
        ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    else:
        return False

    if start_time:
        start_dt = _parse_window_bound(start_time)
        if start_dt is not None and ts < start_dt:
            return True
    if end_time:
        end_dt = _parse_window_bound(end_time)
        if end_dt is not None and ts > end_dt:
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
    task_class: str,
    system_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Query OTel traces for a task class from the session trace store.

    Fetches traces for a given task_class within an optional absolute ISO8601
    time range, and optionally filtered by source system. Uses the global
    ReflectionDatabaseAdapterOneiric instance (same as Akosha) for storage.
    Do NOT use to fetch one trace by id — use `get_otel_trace` on Mahavishnu
    for that. Returns a list of trace records; an empty list means no trace
    matched the filter, or the store was unreachable, so an empty result does
    not distinguish "no matches" from "query failed". Set `dry_run` to get
    the raw stored metadata instead of the full record; that mode clamps
    `limit` to 20, omits the bulky `content` blob, and keeps your `system_id`
    and `task_class` filters in force. Side effect: none; reads the trace
    store only.

    Args:
        task_class: Task classification tag to filter on (e.g. "code_generation")
        system_id: Optional source system identifier (e.g., 'mahavishnu'); omit
            (or pass "" or "*") to search every system
        start_time: Optional ISO8601 start of the query window
        end_time: Optional ISO8601 end of the query window
        limit: Maximum number of traces to return (default 100)
        dry_run: When True, return the raw stored metadata instead of the
            full record, clamped to 20 records. The filters stay in force --
            this flag changes the output shape, not the scope.

    Returns:
        List of trace records matching the filter criteria
    """
    # Implements: REQ-MCPTD-003
    if not task_class or not isinstance(task_class, str):
        logger.error("query_local_traces: task_class must be a non-empty string")
        return []

    try:
        from session_buddy.reflection_tools import (
            get_reflection_database,
        )

        # ``dry_run`` is a *shape* switch, not a scope switch: it returns the
        # raw stored metadata instead of the full record and clamps the limit
        # so a wide probe stays readable. It deliberately does NOT disable the
        # caller's filters -- a caller-supplied flag that switches off scoping
        # is an escape hatch on a public tool.
        #
        # ``""`` and ``"*`` mean "every system", the same sentinel the
        # Akosha and Mahavishnu tools accept.
        effective_system_id = None if system_id in (None, "", "*") else system_id
        effective_task_class = task_class
        effective_limit = min(limit, 20) if dry_run else limit

        db = await get_reflection_database()

        results = await db.search_conversations(  # ty: ignore[unresolved-attribute]
            query=effective_system_id or "",
            limit=effective_limit,
            threshold=0.0,
        )

        filtered = []
        for result in results:
            metadata = result.get("metadata", {})
            attributes = metadata.get("attributes", {})

            if _filter_result_by_system_id(result, effective_system_id):
                continue
            if _filter_result_by_time_range(result, start_time, end_time):
                continue
            if _filter_result_by_task_class(result, effective_task_class):
                continue

            record: dict[str, Any] = {
                "conversation_id": result.get("id") or result.get("conversation_id"),
                "timestamp": str(
                    result.get("timestamp") or result.get("created_at", "")
                ),
                "metadata": metadata,
                "attributes": attributes,
            }
            if not dry_run:
                record["content"] = result.get("content")
            filtered.append(record)

        logger.info(
            "query_local_traces: system=%s task_class=%s matched=%d",
            effective_system_id,
            effective_task_class,
            len(filtered),
        )
        return filtered

    except Exception:
        logger.exception("Error querying traces")
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
