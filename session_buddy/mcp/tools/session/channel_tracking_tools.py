"""Channel session tracking MCP tools.

Provides ``track_channel_session`` and ``get_channel_sessions`` for
multi-channel session lifecycle tracking (Slack, Signal, terminal, etc.).

Event Flow:
    1. Channel message received → nanobot skill emits ChannelSessionEvent
    2. track_channel_session MCP tool receives event → validates, stores
    3. Returns ChannelSessionResult with session_id
    4. Idle timeout expires → skill emits channel_session_end
    5. track_channel_session records session end, purges entry

Storage:
    Phase 1 uses an in-memory store (``_ChannelSessionStore``).  Entries are
    keyed by ``(channel_type, channel_id, sender_id, session_scope)`` and
    expire when a ``channel_session_end`` event is received.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from session_buddy.mcp.auth import require_auth
from session_buddy.mcp.event_models import ChannelSessionEvent, ChannelSessionResult

if TYPE_CHECKING:
    from fastmcp import FastMCP

_VALID_EVENT_TYPES = frozenset(
    {"channel_session_start", "channel_session_end", "channel_heartbeat"}
)
_VALID_SCOPES = frozenset({"conversation", "thread", "day"})

logger = logging.getLogger(__name__)


class DharaChannelPublisher:
    """Fire-and-forget publisher for channel session events to Dhara time-series.

    Uses Dhara's MCP HTTP transport (``POST /tools/call``) with the
    ``record_time_series`` tool. All errors are swallowed so a Dhara outage
    never blocks channel tracking.

    Args:
        dhara_url: Base URL of the Dhara MCP server (e.g. ``http://localhost:8683``).
    """

    def __init__(self, dhara_url: str) -> None:
        import httpx

        self.dhara_url = dhara_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=5.0)

    async def publish(
        self,
        metric_type: str,
        entity_id: str,
        record: dict[str, Any],
    ) -> None:
        """Record a time-series entry in Dhara. Errors are silently dropped."""
        try:
            await self._client.post(
                f"{self.dhara_url}/tools/call",
                json={
                    "name": "record_time_series",
                    "arguments": {
                        "metric_type": metric_type,
                        "entity_id": entity_id,
                        "record": record,
                    },
                },
            )
        except Exception as exc:
            logger.debug("Dhara channel publish failed (non-fatal): %s", exc)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> DharaChannelPublisher:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


class _ChannelSessionStore:
    """Lightweight in-memory store for active channel sessions."""

    def __init__(self) -> None:
        # key: (channel_type, channel_id, sender_id, session_scope, thread_id or "")
        self._active: dict[tuple[str, ...], dict[str, Any]] = {}

    def _key(self, event: ChannelSessionEvent) -> tuple[str, ...]:
        return (
            event.channel_type,
            event.channel_id,
            event.sender_id,
            event.session_scope,
            event.thread_id or "",
        )

    def start(self, event: ChannelSessionEvent) -> str:
        """Record a session start; return the assigned session_id."""
        key = self._key(event)
        existing = self._active.get(key)
        if existing:
            return existing["session_id"]
        session_id = f"chan_{uuid.uuid4().hex[:12]}"
        self._active[key] = {
            "session_id": session_id,
            "channel_type": event.channel_type,
            "channel_id": event.channel_id,
            "sender_id": event.sender_id,
            "session_scope": event.session_scope,
            "thread_id": event.thread_id,
            "component_name": event.component_name,
            "workspace": event.workspace,
            "platform": event.platform,
            "started_at": event.timestamp,
            "last_seen": event.timestamp,
            "message_count": event.message_count,
        }
        return session_id

    def heartbeat(self, event: ChannelSessionEvent) -> str | None:
        """Update last_seen; return session_id or None if no active session."""
        key = self._key(event)
        record = self._active.get(key)
        if record is None:
            return None
        record["last_seen"] = event.timestamp
        record["message_count"] = record.get("message_count", 0) + event.message_count
        return record["session_id"]

    def end(self, event: ChannelSessionEvent) -> str | None:
        """Remove the active session; return session_id or None if not found."""
        key = self._key(event)
        record = self._active.pop(key, None)
        return record["session_id"] if record else None

    def query(
        self,
        channel_type: str | None = None,
        channel_id: str | None = None,
        sender_id: str | None = None,
        session_scope: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return active sessions matching the given filters."""
        results = []
        for record in self._active.values():
            if channel_type and record["channel_type"] != channel_type:
                continue
            if channel_id and record["channel_id"] != channel_id:
                continue
            if sender_id and record["sender_id"] != sender_id:
                continue
            if session_scope and record["session_scope"] != session_scope:
                continue
            results.append(record)
            if len(results) >= limit:
                break
        return results


# Module-level singleton shared across all tool invocations
_store = _ChannelSessionStore()


def _make_dhara_publisher() -> DharaChannelPublisher | None:
    """Return a DharaChannelPublisher if SESSION_BUDDY_DHARA_URL is set, else None."""
    url = os.environ.get("SESSION_BUDDY_DHARA_URL", "").strip()
    if not url:
        return None
    return DharaChannelPublisher(dhara_url=url)


def register_channel_tracking_tools(
    mcp_server: FastMCP,
    dhara_publisher: DharaChannelPublisher | None = None,
) -> None:
    """Register channel session tracking tools with the MCP server.

    Registers:
    - track_channel_session: Record channel session start / end / heartbeat
    - get_channel_sessions: Query active channel sessions

    Args:
        mcp_server: FastMCP server instance
        dhara_publisher: Optional Dhara publisher for fire-and-forget
            time-series recording of channel events.  When ``None``
            (default) no Dhara publishing occurs.
    """

    @mcp_server.tool()
    @require_auth()
    async def track_channel_session(
        event_id: str,
        event_type: str,
        channel_type: str,
        channel_id: str,
        sender_id: str,
        timestamp: str,
        event_version: str = "2.0",
        session_scope: str = "conversation",
        thread_id: str | None = None,
        component_name: str = "nanobot",
        workspace: str | None = None,
        platform: str | None = None,
        message_preview: str | None = None,
        message_count: int = 1,
        metadata: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Track a channel session event (start / heartbeat / end).

        Accepts events from any nanobot channel (Slack, Signal, terminal, etc.)
        and maintains active session state.  Delegates storage to the
        module-level ``_ChannelSessionStore``.
        """
        if event_type not in _VALID_EVENT_TYPES:
            return ChannelSessionResult(
                event_id=event_id,
                status="error",
                error=f"Invalid event_type {event_type!r}. Must be one of {sorted(_VALID_EVENT_TYPES)}",
            ).model_dump()
        if session_scope not in _VALID_SCOPES:
            return ChannelSessionResult(
                event_id=event_id,
                status="error",
                error=f"Invalid session_scope {session_scope!r}. Must be one of {sorted(_VALID_SCOPES)}",
            ).model_dump()

        try:
            event = ChannelSessionEvent(
                event_version=event_version,
                event_id=event_id,
                event_type=event_type,
                channel_type=channel_type,
                channel_id=channel_id,
                sender_id=sender_id,
                session_scope=session_scope,
                thread_id=thread_id,
                component_name=component_name,
                timestamp=timestamp,
                workspace=workspace,
                platform=platform,
                message_preview=message_preview[:200] if message_preview else None,
                message_count=message_count,
                metadata=metadata or {},
            )

            if event_type == "channel_session_start":
                session_id = _store.start(event)
                status = "tracked"
            elif event_type == "channel_heartbeat":
                session_id = _store.heartbeat(event)
                status = "heartbeat" if session_id else "tracked"
                if session_id is None:
                    session_id = _store.start(event)
                    status = "tracked"
            else:  # channel_session_end
                session_id = _store.end(event)
                status = "ended" if session_id else "not_found"

            # Phase 2: fire-and-forget Dhara time-series publish
            if dhara_publisher is not None and session_id is not None:
                asyncio.create_task(
                    dhara_publisher.publish(
                        "session_buddy.channel_event",
                        session_id,
                        {
                            "event_type": event_type,
                            "channel_type": channel_type,
                            "channel_id": channel_id,
                            "sender_id": sender_id,
                            "timestamp": timestamp,
                            "status": status,
                        },
                    ),
                    name=f"dhara_publish_{session_id}",
                )

            logger.info(
                "channel_session event=%s channel=%s/%s sender=%s session=%s status=%s",
                event_type,
                channel_type,
                channel_id,
                sender_id,
                session_id,
                status,
            )
            return ChannelSessionResult(
                session_id=session_id,
                event_id=event_id,
                status=status,
            ).model_dump()

        except Exception as exc:
            logger.exception("channel_session tracking failed: %s", exc)
            return ChannelSessionResult(
                event_id=event_id,
                status="error",
                error=str(exc),
            ).model_dump()

    @mcp_server.tool()
    @require_auth()
    async def get_channel_sessions(
        channel_type: str | None = None,
        channel_id: str | None = None,
        sender_id: str | None = None,
        session_scope: str | None = None,
        limit: int = 20,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Query active channel sessions, optionally filtered by channel/sender/scope.

        All parameters are optional.  Omit to retrieve all active sessions.
        """
        if limit < 1 or limit > 200:
            return {"status": "error", "error": "limit must be between 1 and 200"}
        if session_scope is not None and session_scope not in _VALID_SCOPES:
            return {
                "status": "error",
                "error": f"Invalid session_scope {session_scope!r}. Must be one of {sorted(_VALID_SCOPES)}",
            }

        try:
            results = _store.query(
                channel_type=channel_type,
                channel_id=channel_id,
                sender_id=sender_id,
                session_scope=session_scope,
                limit=limit,
            )
            return {
                "status": "success",
                "count": len(results),
                "sessions": results,
                "queried_at": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:
            logger.exception("get_channel_sessions failed: %s", exc)
            return {"status": "error", "error": str(exc)}
