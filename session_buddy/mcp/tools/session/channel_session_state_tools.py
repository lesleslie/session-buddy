"""Channel session state reader — read-back consumer for S-CHANNEL-DURABLE.

Read-back consumer for the channel session state plan lineage v1.2
(Task 154 — restoration of the consumer deleted in commit 7b5c746a).
Mirrors the producer-side pattern in
``session_buddy/channel/state_writer.py`` and uses the same
``_dhara_substrate_compat`` helpers so the call-time
``getattr(dhara, "get", None)`` gate short-circuits cleanly when
the substrate is unbound (G6 contract — read failures must not
crash the MCP layer).

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

from oneiric.core.logging import get_logger

from session_buddy._dhara_substrate_compat import (
    dhara_calltime,
    stamp_dhara_attr,
)

logger = get_logger(__name__)


# Substrate-compat stamp (mirrors producer at
# ``session_buddy/channel/state_writer.py:79``). The installed
# Bodai dhara distribution ships without a persistence backend
# wired, so ``dhara.get`` is typically absent. We stamp it as
# ``None`` at import time so the call-time getattr gate can
# short-circuit without raising. Tests inject a synthetic ``get``
# by stamping the live ``dhara`` module attribute via
# ``monkeypatch.setattr``.
stamp_dhara_attr("get")  # pragma: no cover - substrate introspection


def _load_schema_registry() -> tuple[Any, Any] | None:
    """Lazy-load the dhara schema registry (``from_dict``/``to_dict``).

    Imports ``dhara.schema`` at call time so this module loads
    cleanly on session-buddy's pinned dhara version (which does not
    yet ship ``dhara.schema``). When the schema package is absent
    we return ``None`` and the tool short-circuits to a WARNING
    log + ``None`` result — mirroring the G6 contract that read
    failures must not crash the MCP consumer path.
    """
    try:
        from dhara.schema import from_dict, to_dict
    except ImportError:
        return None
    return from_dict, to_dict


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
        dict (the same form produced by ``to_dict``), or ``None``
        when the record is missing, the substrate is unbound, or
        the substrate raises (G6 contract).

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

        # Lazy-load the schema registry. On session-buddy's pinned
        # dhara version the ``dhara.schema`` subpackage is absent —
        # the consumer must not crash in that environment, so we
        # log + return None (G6 contract: read failures must not
        # propagate into the calling MCP client).
        registry = _load_schema_registry()
        if registry is None:
            logger.warning(
                "channel_session_state_read_skipped",
                extra={
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "reason": "dhara.schema_unavailable",
                },
            )
            return None

        from_dict, to_dict = registry

        # Reconstruct via the schema registry so the returned dict
        # carries the validated shape (and any default normalization
        # the registry applies). Mirrors the producer's
        # ``validate("channel_session_state", payload)`` symmetry:
        # write-validate / read-reconstruct.
        struct = from_dict("channel_session_state", payload)
        return to_dict(struct)
