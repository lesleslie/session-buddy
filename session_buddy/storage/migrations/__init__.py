#!/usr/bin/env python3
"""Skills metrics schema migrations.

This package provides database schema migration support for the skills metrics
storage system using Dhruva (SQLite-based ACID storage).

Usage:
    >>> from session_buddy.storage.migrations import MigrationManager
    >>> manager = MigrationManager(
    ...     db_path=Path("skills.db"),
    ...     migration_dir=Path("session_buddy/storage/migrations")
    ... )
    >>> status = manager.get_status()
    >>> print(f"Pending: {status['total_pending']}")
    >>> applied = manager.migrate()
    >>> print(f"Applied: {applied}")
"""

from __future__ import annotations

from pathlib import Path

# Re-export key classes for convenience
from .base import (
    Migration,
    MigrationError,
    MigrationLoader,
    MigrationManager,
    MigrationVersion,
    SQLMigration,
)

__all__ = [
    "Migration",
    "MigrationError",
    "MigrationLoader",
    "MigrationManager",
    "MigrationVersion",
    "SQLMigration",
    "get_migration_manager",
]


def get_migration_manager(
    db_path: Path | None = None,
    migration_dir: Path | None = None,
) -> MigrationManager:
    """Get or create migration manager for skills metrics.

    Args:
        db_path: Path to SQLite database file. Defaults to
            `.session-buddy/skills.db` in current directory.
        migration_dir: Path to migration files. Defaults to
            `session_buddy/storage/migrations/`.

    Returns:
        Configured MigrationManager instance

    Example:
        >>> manager = get_migration_manager()
        >>> status = manager.get_status()
        >>> if status["total_pending"] > 0:
        ...     manager.migrate()
    """
    if db_path is None:
        db_path = Path.cwd() / ".session-buddy" / "skills.db"

    if migration_dir is None:
        # Default to this package's directory
        migration_dir = Path(__file__).parent

    return MigrationManager(
        db_path=db_path,
        migration_dir=migration_dir,
    )
