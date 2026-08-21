"""Re-export shim for ``session_buddy.tools.session_tools``.

Exposes module-level wrappers for the MCP tool closures (``start_session_tool``,
``checkpoint_session_tool``, ``end_session_tool``) so callers and the type
checker can import them from the conventional ``session_buddy.tools.session_tools``
path.

Also re-exports the helper functions, classes, and ``_impl`` closures that
unit tests and tooling may reach for at the same public path. The canonical
implementation lives in ``session_buddy.mcp.tools.session.session_tools``;
this module is a thin facade to keep callers independent from the MCP
package layout.
"""

from __future__ import annotations

import typing as t

from session_buddy.mcp.tools.session.session_tools import (  # noqa: F401
    SessionOutputBuilder,
    SessionSetupResults,
    _add_environment_info_to_output,
    _add_quality_section_to_output,
    _check_environment_variables,
    _check_working_dir_file,
    _checkpoint_impl,
    _collect_git_repos,
    _create_session_shortcuts,
    _end_impl,
    _format_recommendations,
    _format_session_summary,
    _get_client_working_directory,
    _get_most_recent_client_repo,
    _get_session_manager,
    _handle_auto_store_reflection,
    _is_git_repository,
    _pre_compact_sync_impl,
    _setup_uv_dependencies,
    _start_impl,
    _status_impl,
)
from session_buddy.mcp.tools.session.session_tools import (
    register_session_tools as _canonical_register_session_tools,
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


def register_session_tools(mcp_server: t.Any) -> None:
    """Register all session management tools with the MCP server.

    This wrapper exists so that the ``start`` and ``checkpoint`` tool
    closures resolve ``_start_impl`` and ``_checkpoint_impl`` against this
    module's namespace (and therefore honor mocks patched on
    ``session_buddy.tools.session_tools``) rather than the canonical
    module's globals.

    Registration order matters: the canonical registration is invoked
    first so its ``end``/``status``/``health_check``/``server_info``/
    ``ping``/``pre_compact_sync`` tools land in the registry. ``start``
    and ``checkpoint`` are then registered *again* with closures from
    this module so a server that stores functions keyed by name (the
    ``FakeServer`` style fixture in :mod:`tests.unit.test_server_tools`)
    observes the shim-bound versions last.
    """

    _canonical_register_session_tools(mcp_server)

    @mcp_server.tool()
    async def start(working_directory: str | None = None) -> str:
        """Initialize Claude session with comprehensive setup including UV dependencies and automation tools.

        Unpacks the typed envelope from ``_start_impl`` and discards the
        ``conversation_id`` so callers downstream of FastMCP stay on the
        historical single-string contract. A bare string return is also
        accepted so tests can patch ``_start_impl`` with a prose-only
        mock without changing the contract.
        """
        result = await _start_impl(working_directory)
        if isinstance(result, tuple):
            prose, _conversation_id = result
            return prose
        return result

    @mcp_server.tool()
    async def checkpoint(working_directory: str | None = None) -> str:
        """Perform mid-session quality checkpoint with workflow analysis and optimization recommendations."""
        return await _checkpoint_impl(working_directory)


__all__ = [
    "SessionOutputBuilder",
    "SessionSetupResults",
    "checkpoint_session_tool",
    "end_session_tool",
    "register_session_tools",
    "start_session_tool",
]
