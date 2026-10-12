"""Channel session state reader — read-back consumer for S-CHANNEL-DURABLE.

Read-back consumer for the channel session state plan lineage v1.2
(Task 154 — restoration of the consumer deleted in commit 7b5c746a).
Mirrors the producer-side pattern in
``session_buddy/channel/state_writer.py``.

Per Phase 8 Task 7: the entity type moved from ``dhara.schema`` to
a session-buddy-local msgspec.Struct (see
``session_buddy/channel/_models.py``). The producer/consumer pair
shares the local class; round-trip wire compatibility is pinned
in ``tests/unit/channel/test_models.py``.

Phase 5 of the UUID7-only migration plan (2026-10-11) deleted the
dhara substrate-compat shim (``session_buddy._dhara_substrate_compat``)
because the dhara substrate is being retired (per memory rule
``feedback-substrate-compat-shim-rot.md``, confirmed 2026-10-11 in
the Bodai ULID→UUID7 migration). The tool therefore has no backing
store and always returns ``None`` until a replacement substrate is
wired. The tool is retained (not deleted) so the call-site contract
is preserved for downstream MCP clients that expect the method to
exist; behavior is "well-typed no-op".

The tool's key shape ``channel-sessions/{channel_id}/{sender_id}``
(no trailing slash) is the producer-side convention used by
M-APPROVAL-LOG / M-WORKFLOW-OUTCOME in mahavishnu; readers no longer
look the key up but the key shape is documented here so producers
can align if a replacement substrate is wired.
"""

from __future__ import annotations

from typing import Any

import msgspec
from oneiric.core.logging import get_logger

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

        Phase 5 post-state: there is no backing store. The tool
        always returns ``None`` and emits a structured INFO so
        callers can distinguish "no record" from "substrate outage"
        in the post-migration observability stream. A replacement
        substrate will re-introduce the read path; the call-site
        signature is preserved so downstream MCP clients do not
        need to change.

        Args:
            channel_id: Channel identifier (Slack channel ID,
                Signal conversation ID, terminal session ID, etc.).
            sender_id: Actor identifier within the channel.
            token: Optional auth token (handled by ``require_auth``).
        """
        # Phase 5: dhara substrate retired. Read is a well-typed no-op
        # until a replacement substrate is wired. Key construction is
        # kept (commented) so the producer/consumer key shape stays
        # documented; logging gives operators the channel/sender
        # observability that the previous read path provided.
        logger.info(
            "channel_session_state_read_no_substrate",
            extra={
                "channel_id": channel_id,
                "sender_id": sender_id,
                "reason": "no_substrate_wired_post_phase5",
            },
        )
        return None
