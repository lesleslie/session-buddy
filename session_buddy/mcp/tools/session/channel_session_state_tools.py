"""Channel session state reader — read-back consumer for S-CHANNEL-DURABLE.

Read-back consumer for the channel session state plan lineage v1.2
(Task 154 — restoration of the consumer deleted in commit 7b5c746a).
Mirrors the producer-side pattern in
``session_buddy/channel/state_writer.py`` and uses the same
``_dhara_substrate_compat`` helpers so the call-time
``dhara_calltime("get")`` gate short-circuits cleanly when the
substrate is unbound (G6 contract — read failures must not crash
the MCP layer).

Per Phase 8 Task 7: the entity type moved from ``dhara.schema`` to
a session-buddy-local msgspec.Struct (see
``session_buddy/channel/_models.py``). The producer/consumer pair
now shares the local class; round-trip wire compatibility is pinned
in ``tests/unit/channel/test_models.py``.

Substrate failures are swallowed (G6 contract): a persistence
backend outage MUST NOT crash the MCP consumer path, which would
cascade into the calling nanobot. The tool returns ``None`` on
any failure and emits a structured WARNING so operators can
observe the failure in Dhara/Akosha traces.

The tool's key shape ``channel-sessions/{channel_id}/{sender_id}``
(no trailing slash) is pinned by the producer test at
``tests/integration/channel/test_durable_restart.py::test_channel_session_state_producer_emits_correct_key``
and matches the dhara substrate convention used by
M-APPROVAL-LOG / M-WORKFLOW-OUTCOME in mahavishnu.
"""

from __future__ import annotations

from typing import Any

import msgspec
from oneiric.core.logging import get_logger

from session_buddy._dhara_substrate_compat import dhara_calltime
from session_buddy.channel._models import ChannelSessionState

logger = get_logger(__name__)


def register_channel_session_state_tools(mcp_server: Any) -> None:
    """Register channel session state tools with the MCP server.

    Registers:
    - channel_session_get_state_tool: Read back a persisted
      ``ChannelSessionState`` from the dhara substrate, returning
      the struct as a dict (or ``None`` when the record is missing
      or the substrate is unavailable).

    Args:
        mcp_server: FastMCP server instance.
    """
    # Late import: ``require_auth`` lives in ``session_buddy.mcp.auth``,
    # which itself imports from ``session_buddy.mcp``. Importing at
    # module level would create a circular dependency because this
    # module is imported by ``session_buddy.mcp.tools.__init__``.
    from session_buddy.mcp.auth import require_auth

    @mcp_server.tool()
    @require_auth()
    async def channel_session_get_state_tool(
        channel_id: str,
        sender_id: str,
        token: str | None = None,
    ) -> dict[str, Any] | None:
        """Read back the persisted state for a (channel, sender) pair.

        Returns the validated ``ChannelSessionState`` struct as a
        dict (the same form ``msgspec.to_builtins`` would produce),
        or ``None`` when the record is missing or the substrate is
        unavailable (G6 contract).

        Args:
            channel_id: Channel identifier (Slack channel ID,
                Signal conversation ID, terminal session ID, etc.).
            sender_id: Actor identifier within the channel.
            token: Optional auth token (handled by ``require_auth``).
        """
        key = f"channel-sessions/{channel_id}/{sender_id}"

        # Substrate-compat gate: only read when dhara.get is exposed.
        get: Any = dhara_calltime("get")
        if get is None:
            logger.warning(
                "channel_session_state_read_skipped",
                extra={
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "reason": "dhara.get_unbound",
                },
            )
            return None

        try:
            payload = get(key)
        except Exception as exc:  # noqa: BLE001 — G6 contract: read
            # failures must not crash the MCP consumer path. The
            # structured warning lets operators observe the failure
            # in Dhara/Akosha traces without the call propagating
            # into the calling MCP client.
            logger.warning(
                "channel_session_state_read_failed",
                extra={
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "exception_type": type(exc).__name__,
                },
            )
            return None

        if payload is None:
            return None

        # Convert back to the local msgspec.Struct, then serialize to a JSON-compatible dict.
        struct = msgspec.convert(payload, ChannelSessionState)
        return msgspec.to_builtins(struct)
