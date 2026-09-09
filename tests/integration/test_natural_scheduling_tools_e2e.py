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
import json
from pathlib import Path
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


class TestNaturalSchedulingRoundTrip:
    """Round-trip tests using a REAL ReminderScheduler.

    QA review (2026-09-09) H1: 9 of 12 tools had no round-trip coverage; the
    3 that did used MagicMock stubs. The column-name bugs in
    ``natural_scheduler.py`` went undetected because no test exercised the
    real backing class.

    Each test injects a real ``ReminderScheduler(db_path=":memory:")`` so
    the tool round-trips against the actual SQLite schema. The
    ``create_reminder`` test is the load-bearing one — it would have
    failed before commits ``b90b5fa1`` and ``3db8da67`` aligned SQL queries
    with the actual schema column names.
    """

    @pytest.fixture
    def real_scheduler(self, tmp_path: Path) -> Any:
        """Inject a real ReminderScheduler using a tmp SQLite file for the test.

        SQLite ``:memory:`` databases are connection-scoped — every
        ``sqlite3.connect(":memory:")`` call returns a fresh empty DB,
        so the schema created in ``_init_database()`` would be lost the
        moment the connection is closed. A per-test temp file gives the
        scheduler a stable backing store.

        Cleans up by resetting the module-level singleton on teardown so
        tests don't pollute each other.
        """
        from session_buddy.mcp.tools.infrastructure import (
            natural_scheduling_tools as nst,
        )
        from session_buddy.natural_scheduler import ReminderScheduler

        db_path = str(tmp_path / "scheduler.db")
        rs = ReminderScheduler(db_path=db_path)
        nst._set_scheduler_for_testing(rs)
        yield rs
        nst._set_scheduler_for_testing(None)

    async def test_create_reminder_round_trip(self, real_scheduler: Any) -> None:
        """create_reminder → list_reminders sees it; list_due_reminders doesn't.

        This is the test that would have caught the column-name bugs fixed
        in commits ``b90b5fa1`` and ``3db8da67``. ``create_reminder``
        returns ``{"reminder_id": ..., "title": ...}``; we then verify the
        same row appears in ``list_reminders`` and is NOT in
        ``list_due_reminders`` (since it is 5 minutes out).
        """
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)

        # --- create_reminder ---
        create_out = await mcp.tools["create_reminder"](
            title="real-backing-test",
            time_expression="in 5 minutes",
        )
        create_payload = json.loads(create_out)
        assert "reminder_id" in create_payload, (
            f"create_reminder response missing reminder_id: {create_out}"
        )
        assert create_payload["reminder_id"].startswith("rem_"), (
            f"unexpected reminder_id format: {create_payload['reminder_id']!r}"
        )
        assert create_payload["title"] == "real-backing-test"

        reminder_id = create_payload["reminder_id"]

        # --- list_reminders sees it ---
        list_out = await mcp.tools["list_reminders"]()
        list_payload = json.loads(list_out)
        assert isinstance(list_payload, list)
        ids_in_list = {r["reminder_id"] for r in list_payload}
        assert reminder_id in ids_in_list, (
            f"reminder {reminder_id} not in list_reminders; got {ids_in_list}"
        )

        # --- list_due_reminders does NOT see it (5 minutes out) ---
        due_out = await mcp.tools["list_due_reminders"]()
        due_payload = json.loads(due_out)
        assert isinstance(due_payload, list)
        due_ids = {r["reminder_id"] for r in due_payload}
        assert reminder_id not in due_ids, (
            f"reminder {reminder_id} incorrectly in due list (it's 5 minutes out); "
            f"got {due_ids}"
        )

    async def test_list_reminders_round_trip(self, real_scheduler: Any) -> None:
        """list_reminders returns a JSON array; empty DB returns []."""
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)

        # Empty DB → empty list
        empty_out = await mcp.tools["list_reminders"]()
        empty_payload = json.loads(empty_out)
        assert isinstance(empty_payload, list)
        assert empty_payload == []

        # Add two reminders
        await mcp.tools["create_reminder"](title="t1", time_expression="in 1 hour")
        await mcp.tools["create_reminder"](title="t2", time_expression="in 2 hours")

        # Non-empty
        out = await mcp.tools["list_reminders"]()
        payload = json.loads(out)
        assert isinstance(payload, list)
        assert len(payload) == 2
        # ReminderScheduler stores title in metadata JSON, exposed as `action`
        actions = {r.get("action") for r in payload}
        assert "t1" in actions
        assert "t2" in actions

    async def test_list_due_reminders_round_trip(self, real_scheduler: Any) -> None:
        """list_due_reminders returns a JSON array (empty for fresh scheduler)."""
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)

        out = await mcp.tools["list_due_reminders"]()
        payload = json.loads(out)
        assert isinstance(payload, list)
        assert payload == []

    async def test_execute_reminder_round_trip(self, real_scheduler: Any) -> None:
        """execute_reminder returns a JSON envelope with executed=bool.

        Envelope shape is in flux (parallel agent modifying cancel/execute),
        so assert only the boolean field plus reminder_id presence — NOT
        specific field names like ``{"cancelled": ..., "user_id": ...}``.
        """
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)

        # Create reminder to execute
        create_out = await mcp.tools["create_reminder"](
            title="to execute",
            time_expression="in 5 minutes",
        )
        reminder_id = json.loads(create_out)["reminder_id"]

        # Execute — assert only that the envelope is a JSON object containing
        # the boolean `executed` field and the reminder_id. Envelope shape
        # is in flux (parallel agent modifying cancel/execute), so do NOT
        # assert other field names.
        exec_out = await mcp.tools["execute_reminder"](reminder_id=reminder_id)
        exec_payload = json.loads(exec_out)
        assert isinstance(exec_payload, dict)
        assert reminder_id in exec_out, (
            f"reminder_id {reminder_id} missing from execute output: {exec_out}"
        )
        assert "executed" in exec_payload, (
            f"execute_reminder envelope missing 'executed' field: {exec_payload}"
        )
        assert isinstance(exec_payload["executed"], bool), (
            f"execute_reminder 'executed' is not bool: {exec_payload}"
        )
        assert exec_payload["executed"] is True, (
            f"execute_reminder returned executed=False for an existing reminder: "
            f"{exec_payload}"
        )

    async def test_oversize_title_returns_error_envelope(
        self, real_scheduler: Any
    ) -> None:
        """_check_len rejects oversized title with the ❌ envelope prefix.

        MAX_TITLE_CHARS = 200; sending 300 chars must short-circuit before
        the scheduler is touched.
        """
        from session_buddy.mcp.tools.infrastructure.natural_scheduling_tools import (
            register_natural_scheduling_tools,
        )

        mcp = _FakeMCP()
        register_natural_scheduling_tools(mcp)

        huge = "x" * 300  # > MAX_TITLE_CHARS (200)
        out = await mcp.tools["create_reminder"](
            title=huge,
            time_expression="in 5 minutes",
        )
        assert out.startswith("❌"), (
            f"expected ❌ envelope for oversize title, got: {out[:120]!r}"
        )
        assert "title" in out.lower(), (
            f"error envelope should mention the offending field 'title': {out!r}"
        )
        assert "200" in out, (
            f"error envelope should mention max length 200: {out!r}"
        )
