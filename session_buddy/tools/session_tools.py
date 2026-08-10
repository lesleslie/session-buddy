"""Re-export shim for ``session_buddy.tools.session_tools``.

Exposes module-level wrappers for the MCP tool closures (``start_session_tool``,
``checkpoint_session_tool``, ``end_session_tool``) so callers and the type
checker can import them from the conventional ``session_buddy.tools.session_tools``
path.
"""

from __future__ import annotations

from session_buddy.mcp.tools.session.session_tools import (
    _checkpoint_impl,
    _end_impl,
    _start_impl,
    register_session_tools,
)


async def start_session_tool(
    working_directory: str | None = None,
) -> str:
    """Start a new Claude session, including environment setup and shortcuts.

    Unpacks the typed envelope from ``_start_impl`` and discards the
    ``conversation_id`` so existing callers that only consume prose
    (the FastMCP wrapper, hook scripts, etc.) see no signature change.
    The conversation_id ULID is threaded through to consumers that need
    it via Task 8's CrossRepoPusher path.
    """
    prose, _conversation_id = await _start_impl(working_directory)
    return prose


async def checkpoint_session_tool(
    working_directory: str | None = None,
) -> str:
    """Create a session checkpoint capturing current progress."""
    return await _checkpoint_impl(working_directory)


async def end_session_tool(
    working_directory: str | None = None,
) -> str:
    """End the current session, persisting context and final reflection."""
    return await _end_impl(working_directory)


__all__ = [
    "checkpoint_session_tool",
    "end_session_tool",
    "register_session_tools",
    "start_session_tool",
]
