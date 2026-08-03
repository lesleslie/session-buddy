"""Session-Buddy ``commands.checkpoint`` wrapper.

Adapts the session-tools checkpoint flow to the plugin/hook-facing
``(project_path, agent_idx)`` signature expected by the
``2026-07-29-session-buddy-extension`` design. Layered over the
existing MCP-tool wrapper so concurrent and sequential coalescing
both apply:

- Concurrent identical requests collapse inside
  ``session_buddy.mcp.tools.session.session_tools._single_flight_checkpoint``.
- Sequential hook retries within ``ttl_seconds`` (default 5s) collapse
  here via :class:`~session_buddy.hooks.HookSingleFlight`.

Public surface:
    ``async def checkpoint(*, project_path: str, agent_idx: int = 0) -> str``

Returns:
    ``str`` — the formatted checkpoint output from the underlying
    MCP tool, or the literal ``"coalesced"`` marker when this call
    was suppressed by the time-based gate.

Environment:
    ``SESSION_BUDDY_HOOK_SINGLE_FLIGHT=false`` disables the
    time-based gate; ``checkpoint`` then forwards every call
    straight to the underlying tool.
"""

from __future__ import annotations

import os

from session_buddy.hooks import HookSingleFlight
from session_buddy.mcp.tools.session.session_tools import _checkpoint_impl

_FLIGHT = HookSingleFlight(ttl_seconds=5.0)
_GATE_ENABLED = os.environ.get(
    "SESSION_BUDDY_HOOK_SINGLE_FLIGHT",
    "true",
).lower() not in {"false", "0", "no", "off"}


async def checkpoint(
    *,
    project_path: str,
    agent_idx: int = 0,
) -> str:
    """Run the checkpoint tool with single-flight protection.

    Parameters
    ----------
    project_path:
        Absolute path of the project being checkpointed. Used as the
        dedup key so distinct projects never coalesce.
    agent_idx:
        Index of the agent within the project. Defaults to ``0``
        because the existing MCP-layer signature carries no agent
        index. Multi-agent projects must pass a stable, distinct
        value per agent.

    Returns
    -------
    str
        The formatted checkpoint result, or ``"coalesced"`` if this
        call was suppressed by the time-based gate.
    """
    key = (project_path, agent_idx)
    last_result: list[str] = []

    async def body() -> None:
        last_result.append(await _checkpoint_impl(working_directory=project_path))

    if not _GATE_ENABLED:
        await body()
        return last_result[0]

    ran = await _FLIGHT(key, body)
    if not ran:
        return "coalesced"
    return last_result[0]
