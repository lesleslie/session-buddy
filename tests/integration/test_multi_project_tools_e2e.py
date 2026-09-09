"""End-to-end tests for register_multi_project_tools.

Verifies the function:

1. Runs without error against a mock FastMCP server.
2. Registers at least 5 MCP tools (the brief's target count for the
   multi-project category).
3. Registers the expected tool names so downstream callers can rely
   on them.
4. Optionally exercises a registered tool against a stubbed
   coordinator so the wiring round-trips end-to-end with non-empty
   results.

Pattern adapted from
:mod:`tests.integration.test_mcp_registration_standard_profile`
(verbatim from lines 68-80 of that file).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeMCP:
    """FastMCP stand-in recording tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class TestRegisterMultiProjectTools:
    def test_register_function_runs_without_error(self) -> None:
        """The registration call itself must not raise."""
        from session_buddy.mcp.tools.collaboration.multi_project_tools import (
            register_multi_project_tools,
        )

        mcp = _FakeMCP()
        register_multi_project_tools(mcp)
        assert mcp.tools, "register_multi_project_tools registered no tools"

    def test_registers_expected_tool_names(self) -> None:
        from session_buddy.mcp.tools.collaboration.multi_project_tools import (
            register_multi_project_tools,
        )

        mcp = _FakeMCP()
        register_multi_project_tools(mcp)
        expected = {
            "create_project_group",
            "add_project_dependency",
            "link_sessions",
            "list_project_groups",
            "get_project_dependencies",
            "find_related_conversations",
        }
        assert expected.issubset(mcp.tools), (
            f"missing tools: {expected - set(mcp.tools)}"
        )
        assert len(mcp.tools) >= 5

    def test_registered_tools_are_callable_coroutines(self) -> None:
        """Each registered tool must be an async coroutine function."""
        from session_buddy.mcp.tools.collaboration.multi_project_tools import (
            register_multi_project_tools,
        )

        mcp = _FakeMCP()
        register_multi_project_tools(mcp)
        for name, fn in mcp.tools.items():
            assert callable(fn), f"tool {name!r} is not callable"
            assert asyncio_iscoroutinefunction(fn), (
                f"tool {name!r} is not an async coroutine function"
            )

    async def test_end_to_end_against_stubbed_coordinator(self) -> None:
        """Round-trip: register, then invoke with a stubbed coordinator."""
        from session_buddy.mcp.tools.collaboration import multi_project_tools as mpt
        from session_buddy.mcp.tools.collaboration.multi_project_tools import (
            register_multi_project_tools,
        )

        coordinator = MagicMock()
        coordinator.create_project_group = AsyncMock(
            return_value=MagicMock(
                model_dump_json=MagicMock(return_value='{"id":"grp-1"}'),
            )
        )

        mpt._set_coordinator_for_testing(coordinator)
        try:
            mcp = _FakeMCP()
            register_multi_project_tools(mcp)
            out = await mcp.tools["create_project_group"](
                name="g1",
                projects=["p1"],
                description="",
            )
        finally:
            mpt._set_coordinator_for_testing(None)

        coordinator.create_project_group.assert_awaited_once()
        kwargs = coordinator.create_project_group.await_args.kwargs
        assert kwargs["name"] == "g1"
        assert kwargs["projects"] == ["p1"]
        assert "grp-1" in out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def asyncio_iscoroutinefunction(fn: Any) -> bool:
    """Return True if ``fn`` is an async coroutine function.

    Wraps :func:`asyncio.iscoroutinefunction` with a portable import
    so the test module can be collected even when ``asyncio_mode`` is
    not yet applied.
    """
    import asyncio

    return asyncio.iscoroutinefunction(fn)
