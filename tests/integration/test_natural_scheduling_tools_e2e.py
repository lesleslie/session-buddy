"""End-to-end tests for register_natural_scheduling_tools.

Verifies the function:

1. Runs without error against a mock FastMCP server.
2. Registers at least 5 MCP tools (the brief's target count for the
   natural-scheduling category).
3. Registers the expected tool names so downstream callers can rely
   on them.
4. Optionally exercises a registered tool against a stubbed scheduler
   so the wiring round-trips end-to-end with non-empty results.

Pattern adapted from
:mod:`tests.integration.test_mcp_registration_standard_profile`
(verbatim from lines 68-80 of that file).
"""

from __future__ import annotations

import asyncio
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


class TestRegisterNaturalSchedulingTools:
    def test_register_function_runs_without_error(self) -> None:
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)
        assert mcp.tools, "register_natural_scheduling_tools registered no tools"

    def test_registers_expected_tool_names(self) -> None:
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)
        expected = {
            "create_reminder",
            "list_reminders",
            "list_due_reminders",
            "cancel_reminder",
            "execute_reminder",
            "parse_natural_time",
        }
        assert expected.issubset(mcp.tools), (
            f"missing tools: {expected - set(mcp.tools)}"
        )
        assert len(mcp.tools) >= 5

    def test_registered_tools_are_callable_coroutines(self) -> None:
        """Each registered tool must be an async coroutine function."""
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)
        for name, fn in mcp.tools.items():
            assert callable(fn), f"tool {name!r} is not callable"
            assert asyncio.iscoroutinefunction(fn), (
                f"tool {name!r} is not an async coroutine function"
            )

    async def test_end_to_end_cancel_via_stubbed_scheduler(self) -> None:
        """Round-trip: register, then invoke with a stubbed scheduler."""
        from session_buddy.mcp.tools.infrastructure import (
            natural_scheduling_tools as nst,
        )
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        scheduler = MagicMock()
        scheduler.cancel_reminder = AsyncMock(return_value=True)

        nst._set_scheduler_for_testing(scheduler)
        try:
            mcp = _FakeMCP()
            register_natural_scheduling_tools(mcp)
            out = await mcp.tools["cancel_reminder"]("rem_abc123")
        finally:
            nst._set_scheduler_for_testing(None)

        scheduler.cancel_reminder.assert_awaited_once_with(
            reminder_id="rem_abc123"
        )
        assert "rem_abc123" in out
        assert "true" in out.lower()

    async def test_parse_natural_time_via_stubbed_parser(self) -> None:
        """parse_natural_time uses the parser, not the scheduler."""
        from datetime import datetime, timedelta

        from session_buddy.mcp.tools.infrastructure import (
            natural_scheduling_tools as nst,
        )
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        target = datetime(2026, 9, 10, 15, 0, 0)
        parser = MagicMock()
        parser.parse_time_expression = MagicMock(return_value=target)
        parser.parse_recurrence = MagicMock(return_value=None)

        nst._set_parser_for_testing(parser)
        try:
            mcp = _FakeMCP()
            register_natural_scheduling_tools(mcp)
            out = await mcp.tools["parse_natural_time"]("tomorrow at 3pm")
        finally:
            nst._set_parser_for_testing(None)

        parser.parse_time_expression.assert_called_once_with("tomorrow at 3pm")
        parser.parse_recurrence.assert_called_once_with("tomorrow at 3pm")
        assert "tomorrow at 3pm" in out
        assert "2026-09-10T15:00:00" in out
