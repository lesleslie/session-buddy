"""Unit tests for session_buddy.mcp.tools.session.migration_tools.

Lifts coverage on ``migration_tools`` by re-hitting the registration shape
and every branch of ``trigger_migration`` / ``rollback_migration`` from the
``tests/unit/mcp/tools/session/`` directory. Mirrors the patterns in
``tests/unit/test_migration_tools.py`` but lives in the scoped test dir.
"""

from __future__ import annotations

import typing as t
from pathlib import Path
from unittest.mock import patch

import pytest


class _DummyMCP:
    """Minimal stand-in for FastMCP — captures decorated tool callables."""

    def __init__(self) -> None:
        self.tools: dict[str, t.Callable[..., t.Any]] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _make_server_and_tools() -> tuple[_DummyMCP, dict[str, t.Any]]:
    """Build a fresh server, run registration, return the captured tools."""
    from session_buddy.mcp.tools.session.migration_tools import (
        register_migration_tools,
    )

    mcp = _DummyMCP()
    register_migration_tools(mcp)
    return mcp, mcp.tools


# ---------------------------------------------------------------------------
# Registration smoke tests
# ---------------------------------------------------------------------------


def test_register_registers_three_tools() -> None:
    """``register_migration_tools`` exposes exactly three tools."""
    _mcp, tools = _make_server_and_tools()
    assert set(tools) == {"migration_status", "trigger_migration", "rollback_migration"}


def test_tools_are_coroutines() -> None:
    """All three tools are coroutine functions."""
    import inspect

    _mcp, tools = _make_server_and_tools()
    for name in tools:
        assert inspect.iscoroutinefunction(tools[name])


# ---------------------------------------------------------------------------
# migration_status tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_status_returns_status_dict() -> None:
    """``migration_status`` returns the value of ``get_migration_status()``."""
    from session_buddy.mcp.tools.session.migration_tools import (
        register_migration_tools,
    )

    expected = {
        "current_version": "v2",
        "migration_history": [],
        "counts": {"v1_conversations": 0, "v2_conversations": 5},
    }

    with patch(
        "session_buddy.mcp.tools.session.migration_tools.get_migration_status",
        return_value=expected,
    ) as mock_status:
        _mcp, tools = _make_server_and_tools()
        result = await tools["migration_status"]()

    assert result == expected
    mock_status.assert_called_once()


# ---------------------------------------------------------------------------
# trigger_migration tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_migration_dry_run_skips_backup() -> None:
    """``dry_run=True`` suppresses backup creation regardless of the flag."""
    from session_buddy.mcp.tools.session.migration_tools import (
        register_migration_tools,
    )

    with patch(
        "session_buddy.mcp.tools.session.migration_tools.create_backup",
    ) as mock_backup:
        with patch(
            "session_buddy.mcp.tools.session.migration_tools.migrate_v1_to_v2",
        ) as mock_migrate:
            mock_migrate.return_value.success = True
            mock_migrate.return_value.error = None
            mock_migrate.return_value.stats = {"preview": True}
            mock_migrate.return_value.duration_seconds = 0.1

            with patch(
                "session_buddy.mcp.tools.session.migration_tools.needs_migration",
                return_value=True,
            ):
                _mcp, tools = _make_server_and_tools()
                result = await tools["trigger_migration"](
                    create_backup_first=True,
                    dry_run=True,
                )

    assert mock_backup.call_count == 0
    assert result["backup"] is None
    assert result["success"] is True
    assert result["stats"] == {"preview": True}
    assert result["duration_seconds"] == 0.1
    # Successful migration — needs_migration should NOT be called
    assert result["migration_needed"] is False


@pytest.mark.asyncio
async def test_trigger_migration_creates_backup_when_not_dry_run() -> None:
    """``create_backup_first=True`` + ``dry_run=False`` triggers backup."""
    with patch(
        "session_buddy.mcp.tools.session.migration_tools.create_backup",
        return_value=Path("/tmp/backup.duckdb"),
    ) as mock_backup:
        with patch(
            "session_buddy.mcp.tools.session.migration_tools.migrate_v1_to_v2",
        ) as mock_migrate:
            mock_migrate.return_value.success = True
            mock_migrate.return_value.error = None
            mock_migrate.return_value.stats = {"migrated": 3}
            mock_migrate.return_value.duration_seconds = 1.5

            with patch(
                "session_buddy.mcp.tools.session.migration_tools.needs_migration",
                return_value=False,
            ):
                _mcp, tools = _make_server_and_tools()
                result = await tools["trigger_migration"]()

    mock_backup.assert_called_once()
    assert result["backup"] == "/tmp/backup.duckdb"
    assert result["success"] is True
    assert result["stats"] == {"migrated": 3}
    assert result["duration_seconds"] == 1.5
    # Successful migration — needs_migration should NOT be called
    assert result["migration_needed"] is False


@pytest.mark.asyncio
async def test_trigger_migration_default_no_backup_when_create_backup_first_false() -> None:
    """``create_backup_first=False`` skips backup even when dry_run is False."""
    with patch(
        "session_buddy.mcp.tools.session.migration_tools.create_backup",
    ) as mock_backup:
        with patch(
            "session_buddy.mcp.tools.session.migration_tools.migrate_v1_to_v2",
        ) as mock_migrate:
            mock_migrate.return_value.success = True
            mock_migrate.return_value.error = None
            mock_migrate.return_value.stats = {}
            mock_migrate.return_value.duration_seconds = 0.0

            _mcp, tools = _make_server_and_tools()
            result = await tools["trigger_migration"](create_backup_first=False)

    assert mock_backup.call_count == 0
    assert result["backup"] is None
    assert result["success"] is True


@pytest.mark.asyncio
async def test_trigger_migration_failure_returns_needs_migration() -> None:
    """Failure path re-evaluates ``needs_migration()`` and surfaces error."""
    with patch(
        "session_buddy.mcp.tools.session.migration_tools.create_backup",
        return_value=Path("/tmp/backup.duckdb"),
    ):
        with patch(
            "session_buddy.mcp.tools.session.migration_tools.migrate_v1_to_v2",
        ) as mock_migrate:
            mock_migrate.return_value.success = False
            mock_migrate.return_value.error = "boom"
            mock_migrate.return_value.stats = {}
            mock_migrate.return_value.duration_seconds = 0.5

            with patch(
                "session_buddy.mcp.tools.session.migration_tools.needs_migration",
                return_value=True,
            ) as mock_needs:
                _mcp, tools = _make_server_and_tools()
                result = await tools["trigger_migration"]()

    mock_needs.assert_called_once()
    assert result["success"] is False
    assert result["error"] == "boom"
    assert result["migration_needed"] is True


# ---------------------------------------------------------------------------
# rollback_migration tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_migration_returns_version_and_status() -> None:
    """``rollback_migration`` restores the backup and returns version + status."""
    from session_buddy.mcp.tools.session.migration_tools import (
        register_migration_tools,
    )

    expected_status = {
        "current_version": "v1",
        "migration_history": [],
        "counts": {"v1_conversations": 3, "v2_conversations": 0},
    }

    with patch(
        "session_buddy.mcp.tools.session.migration_tools.get_migration_status",
        return_value=expected_status,
    ):
        with patch(
            "session_buddy.memory.migration.get_schema_version",
            return_value="v1",
        ):
            with patch(
                "session_buddy.memory.migration.restore_backup"
            ) as mock_restore:
                _mcp, tools = _make_server_and_tools()
                result = await tools["rollback_migration"](
                    backup_path="/tmp/backup.duckdb"
                )

    mock_restore.assert_called_once()
    call_args = mock_restore.call_args.args
    assert isinstance(call_args[0], Path)
    assert str(call_args[0]) == "/tmp/backup.duckdb"
    assert result == {
        "restored_version": "v1",
        "status": expected_status,
    }