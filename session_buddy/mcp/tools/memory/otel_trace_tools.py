"""Trace query tools for Session-Buddy.

Session-Buddy does not keep an OpenTelemetry span store locally. It
*emits* spans to the fleet collector (Akosha owns the collector) and keeps
its own records in the reflection database. This tool queries those local
records through the fleet-wide ``query_local_traces`` **parameter
envelope**, so a caller can issue one call against any server that
exposes the name.

The envelope is shared; the semantics are not. On this server the two
filters map onto the columns the local store actually populates:

* ``task_class`` -> the record's classification (``category`` or
  ``subcategory``)
* ``system_id`` -> the record's ``project`` (the component or repo it came
  from)

The mapping is a property of what this store holds, not a choice: the
conversation writer moves every non-allowlisted metadata key into a
``_redacted`` bucket (``session_buddy/ingesters/redaction.py``), so no
record carries ``system_id`` or an OpenTelemetry ``attributes`` blob as a
first-class field. The bucket itself is not returned -- handing it back
would undo the redaction policy.

The query does not run a similarity search, so it does not depend on the
embedding chain being up. The earlier search-backed implementation did,
and the text path treats an empty query as "matches nothing" -- so the
all-projects query returned an empty list whenever the vector index was
cold.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from session_buddy.utils.error_management import _get_logger

logger = _get_logger()

# A dry run returns the stored metadata instead of the record body, so it
# clamps the limit to keep a wide probe readable. Same clamp as the
# Akosha and Mahavishnu tools.
_DRY_RUN_LIMIT = 20


def _parse_window_bound(value: str) -> datetime | None:
    """Parse an ISO8601 window bound into a UTC-aware datetime.

    A bound with no offset is read as UTC, so a bound is always an
    instant and is compared against the store's timestamps as one. A bound
    with an offset is converted to UTC.

    Note that the store's ``timestamp`` column holds host-local
    wall-clock. DuckDB re-attaches the session time zone when it compares
    that column against a timezone-aware value, so an absolute bound
    still selects the right records -- as long as the reader's time zone
    is the writer's. A *naive* bound is read as UTC, not as the server's
    local clock. A caller that means local time must say so with an
    offset.

    Returns ``None`` when the value does not parse. The caller treats
    that as a rejected request rather than as an absent bound, so a
    malformed bound never silently widens the window.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def query_local_traces(
    task_class: str,
    system_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Query the local record store for a task class.

    Session-Buddy has no local OpenTelemetry span store -- it emits spans
    to the fleet collector and reads its own records back from the
    reflection database. This tool queries those local records through the
    fleet-wide `query_local_traces` envelope:

    * `task_class` matches the record's classification (`category` or
      `subcategory`). The values present are memory categories such as
      "facts" and "context" -- NOT the OpenTelemetry task taxonomy
      ("code", "code_generation", "mcp_tool_call"), which this store
      does not carry. A `task_class` from the OTel taxonomy matches
      nothing here, and that is an accurate answer: this server has no
      traces for it.
    * `system_id` matches the record's `project` -- the basename of the
      directory the writing session ran in. In a plain checkout that is
      the repo name ("mahavishnu"); in a worktree checkout it is the
      worktree directory name, so a filter for the repo name will not
      find records written from a worktree. The match is exact (case
      insensitive). A record written by a consolidated multi-project
      session carries a comma-joined list and is not reachable by any
      single-project filter. A record with no project is excluded by a
      project filter.

    This reads conversation and checkpoint rows (``conversations_v2``).
    Reflections written via `store_reflection` live in a different table
    and are NOT returned -- use `quick_search` or `search_conversations`
    for those.

    The window bounds are absolute ISO8601 timestamps. A bound with no
    offset is read as UTC. A bound that does not parse is rejected: the
    call returns an empty list rather than running an unbounded query.

    Returns a list of records; an empty list means no record matched the
    filter, or the store was unreachable, so an empty result does not
    distinguish "no matches" from "query failed". Set `dry_run` to get the
    stored metadata instead of the record body; that mode clamps `limit`
    to 20 and keeps your `system_id` and `task_class` filters in force.
    Side effect: none; reads the record store only.

    Args:
        task_class: Classification to match, case-insensitively (e.g.
            "facts")
        system_id: Optional project filter -- the basename of the directory
            the writing session ran in. Omit (or pass "" or "*") to search
            every project.
        start_time: Optional ISO8601 start of the query window
        end_time: Optional ISO8601 end of the query window
        limit: Maximum number of records to return (default 100). Clamped
            to 1..1000 by the store query.
        dry_run: When True, return the stored metadata instead of the
            record body, clamped to 20 records. The filters stay in force --
            this flag changes the output shape, not the scope.

    Returns:
        List of records matching the filter criteria.
    """
    # Implements: REQ-MCPTD-003
    if not task_class or not isinstance(task_class, str):
        logger.error("query_local_traces: task_class must be a non-empty string")
        return []

    # A bound that does not parse is a rejected request, not an absent
    # bound. Treating it as absent would drop that side of the window and
    # return MORE records than the caller asked for.
    window_start: datetime | None = None
    window_end: datetime | None = None
    for label, value in (("start_time", start_time), ("end_time", end_time)):
        if value is None:
            continue
        parsed = _parse_window_bound(value)
        if parsed is None:
            logger.error(
                "query_local_traces: %s must be an ISO8601 timestamp, got %r",
                label,
                value,
            )
            return []
        if label == "start_time":
            window_start = parsed
        else:
            window_end = parsed

    try:
        from session_buddy.reflection_tools import (
            get_reflection_database,
        )

        # ``dry_run`` is a *shape* switch, not a scope switch: it returns the
        # stored metadata instead of the record body and clamps the limit
        # so a wide probe stays readable. It deliberately does NOT disable
        # the caller's filters -- a caller-supplied flag that switches off
        # scoping is an escape hatch on a public tool.
        #
        # ``""`` and ``"*`` mean "every project", the same sentinel the
        # Akosha and Mahavishnu tools accept.
        effective_project = None if system_id in (None, "", "*") else system_id
        effective_limit = min(limit, _DRY_RUN_LIMIT) if dry_run else limit

        db = await get_reflection_database()
        if db is None:
            logger.error("query_local_traces: the reflection database is unavailable")
            return []

        rows = await db.query_conversations_by_classification(
            classification=task_class,
            project=effective_project,
            start_time=window_start,
            end_time=window_end,
            limit=effective_limit,
        )

        records: list[dict[str, Any]] = []
        for row in rows:
            timestamp = row.get("timestamp")
            record: dict[str, Any] = {
                "system_id": row.get("project"),
                "conversation_id": row.get("id"),
                "timestamp": (
                    timestamp.astimezone(UTC).isoformat()
                    if isinstance(timestamp, datetime)
                    else str(timestamp or "")
                ),
                "metadata": row.get("metadata") or {},
                "task_class": row.get("classification"),
                "project": row.get("project"),
            }
            if not dry_run:
                record["content"] = row.get("content")
            records.append(record)

        logger.info(
            "query_local_traces: project=%s task_class=%s matched=%d",
            effective_project,
            task_class,
            len(records),
        )
        return records

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
