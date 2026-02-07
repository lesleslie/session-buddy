#!/usr/bin/env python3
"""MCP tools for schema migration status and control."""

from __future__ import annotations

import typing as t
from typing import TYPE_CHECKING

from session_buddy.memory.migration import (
    create_backup,
    get_migration_status,
    migrate_v1_to_v2,
    needs_migration,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_migration_tools(mcp: FastMCP) -> None:
    @mcp.tool()  # type: ignore[no-untyped-call]
    async def migration_status() -> dict[str, t.Any]:
        """Check migration status and progress."""
        return get_migration_status()

    @mcp.tool()  # type: ignore[no-untyped-call]
    async def trigger_migration(
        create_backup_first: bool = True, dry_run: bool = False
    ) -> dict[str, t.Any]:
        """Manually trigger migration (with preview)."""
        if create_backup_first and not dry_run:
            backup_path = create_backup()
            backup = str(backup_path)
        else:
            backup = None

        result = migrate_v1_to_v2(dry_run=dry_run)
        return {
            "success": result.success,
            "error": result.error,
            "stats": result.stats or {},
            "duration_seconds": result.duration_seconds,
            "backup": backup,
            "migration_needed": needs_migration() if not result.success else False,
        }

    @mcp.tool()  # type: ignore[no-untyped-call]
    async def rollback_migration(backup_path: str) -> dict[str, t.Any]:
        """Restore database from a previous backup file path."""
        from pathlib import Path

        from session_buddy.memory.migration import get_schema_version, restore_backup

        restore_backup(Path(backup_path))
        version = get_schema_version()
        status = get_migration_status()
        return {"restored_version": version, "status": status}
