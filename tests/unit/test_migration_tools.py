"""Tests for mcp.tools.session.migration_tools."""

from __future__ import annotations

import typing as t
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class DummyMCP:
    """Dummy FastMCP for testing tool registration."""

    def __init__(self) -> None:
        self.tools: dict[str, t.Callable[..., t.Any]] = {}

    def tool(
        self,
    ) -> t.Callable[[t.Callable[..., t.Any]], t.Callable[..., t.Any]]:
        def decorator(fn: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class TestRegisterMigrationTools:
    """Tests for register_migration_tools function."""

    def test_register_migration_tools_registers_three_tools(self) -> None:
        """register_migration_tools should register 3 tools."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        mcp = DummyMCP()
        register_migration_tools(mcp)

        assert len(mcp.tools) == 3
        assert "migration_status" in mcp.tools
        assert "trigger_migration" in mcp.tools
        assert "rollback_migration" in mcp.tools


class TestMigrationStatusTool:
    """Tests for the migration_status tool behavior."""

    @pytest.mark.asyncio
    async def test_returns_migration_status(self) -> None:
        """migration_status should return status from get_migration_status."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        mcp = DummyMCP()

        expected_status = {
            "current_version": "v2",
            "migration_history": [],
            "counts": {"v1_conversations": 0, "v2_conversations": 5},
        }

        with patch(
            "session_buddy.mcp.tools.session.migration_tools.get_migration_status",
        ) as mock_status:
            mock_status.return_value = expected_status

            register_migration_tools(mcp)
            result = await mcp.tools["migration_status"]()

            assert result == expected_status
            mock_status.assert_called_once()


class TestTriggerMigrationTool:
    """Tests for the trigger_migration tool behavior."""

    @pytest.mark.asyncio
    async def test_dry_run_returns_preview_without_backup(self) -> None:
        """trigger_migration with dry_run=True should not create backup."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.session.migration_tools.create_backup",
        ) as mock_backup:
            mock_backup.return_value = Path("/fake/backup.duckdb")

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
                    register_migration_tools(mcp)
                    result = await mcp.tools["trigger_migration"](dry_run=True)

                    assert mock_backup.call_count == 0
                    assert result["backup"] is None
                    assert result["success"] is True

    @pytest.mark.asyncio
    async def test_creates_backup_when_not_dry_run(self) -> None:
        """trigger_migration should create backup when dry_run=False."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        backup_path = Path("/fake/backup.duckdb")

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.session.migration_tools.create_backup",
        ) as mock_backup:
            mock_backup.return_value = backup_path

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
                    register_migration_tools(mcp)
                    result = await mcp.tools["trigger_migration"](dry_run=False)

                    mock_backup.assert_called_once()
                    assert result["backup"] == str(backup_path)

    @pytest.mark.asyncio
    async def test_returns_migration_needed_when_failed(self) -> None:
        """trigger_migration should check needs_migration when migration fails."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.session.migration_tools.create_backup",
        ) as mock_backup:
            mock_backup.return_value = Path("/fake/backup.duckdb")

            with patch(
                "session_buddy.mcp.tools.session.migration_tools.migrate_v1_to_v2",
            ) as mock_migrate:
                mock_migrate.return_value.success = False
                mock_migrate.return_value.error = "Test error"
                mock_migrate.return_value.stats = {}
                mock_migrate.return_value.duration_seconds = 0.5

                with patch(
                    "session_buddy.mcp.tools.session.migration_tools.needs_migration",
                    return_value=True,
                ) as mock_needs:
                    register_migration_tools(mcp)
                    result = await mcp.tools["trigger_migration"]()

                    mock_needs.assert_called_once()
                    assert result["migration_needed"] is True

    @pytest.mark.asyncio
    async def test_skips_needs_migration_check_when_successful(self) -> None:
        """trigger_migration should NOT check needs_migration when migration succeeds."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.session.migration_tools.create_backup",
        ) as mock_backup:
            mock_backup.return_value = Path("/fake/backup.duckdb")

            with patch(
                "session_buddy.mcp.tools.session.migration_tools.migrate_v1_to_v2",
            ) as mock_migrate:
                mock_migrate.return_value.success = True
                mock_migrate.return_value.error = None
                mock_migrate.return_value.stats = {"migrated": 3}
                mock_migrate.return_value.duration_seconds = 1.0

                with patch(
                    "session_buddy.mcp.tools.session.migration_tools.needs_migration",
                    return_value=True,
                ) as mock_needs:
                    register_migration_tools(mcp)
                    result = await mcp.tools["trigger_migration"]()

                    mock_needs.assert_not_called()
                    assert result["migration_needed"] is False


class TestRollbackMigrationTool:
    """Tests for the rollback_migration tool behavior."""

    @pytest.mark.asyncio
    async def test_restores_backup_and_returns_status(self) -> None:
        """rollback_migration should restore backup and return version/status."""
        from session_buddy.mcp.tools.session.migration_tools import (
            register_migration_tools,
        )

        backup_path = "/fake/backup.duckdb"
        expected_version = "v1"
        expected_status = {
            "current_version": "v1",
            "migration_history": [],
            "counts": {"v1_conversations": 3, "v2_conversations": 0},
        }

        mcp = DummyMCP()

        with patch(
            "session_buddy.mcp.tools.session.migration_tools.get_migration_status",
            return_value=expected_status,
        ):
            with patch(
                "session_buddy.memory.migration.get_schema_version",
                return_value=expected_version,
            ):
                with patch(
                    "session_buddy.memory.migration.restore_backup"
                ) as mock_restore:
                    register_migration_tools(mcp)
                    result = await mcp.tools["rollback_migration"](backup_path)

        mock_restore.assert_called_once()
        assert result == {
            "restored_version": expected_version,
            "status": expected_status,
        }
