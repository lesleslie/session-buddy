#!/usr/bin/env python3
"""Migration base classes for skills metrics schema.

Provides protocol-based migration system with:
- Up/down migration support
- Transaction safety
- Rollback capability
- Version tracking
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ============================================================================#
# Migration Protocols
# ============================================================================#


@dataclass
class MigrationVersion:
    """Migration version identifier."""

    version: str  # e.g., "V1__initial_schema"
    description: str
    checksum: str | None = None  # SHA256 of SQL content


class Migration(ABC):
    """Base class for database migrations.

    All migrations must implement up() and down() methods.
    Migrations run in transactions - all-or-nothing execution.
    """

    @property
    @abstractmethod
    def version(self) -> str:
        """Migration version identifier (e.g., 'V1__initial_schema')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of migration."""

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply migration to database.

        Args:
            conn: Database connection (transaction already started)
        """

    @abstractmethod
    def down(self, conn: sqlite3.Connection) -> None:
        """Rollback migration from database.

        Args:
            conn: Database connection (transaction already started)
        """

    def checksum(self) -> str | None:
        """Compute checksum of migration SQL (optional).

        Returns:
            SHA256 hash of migration content, or None
        """
        return None


class SQLMigration(Migration):
    """SQL file-based migration.

    Reads up/down SQL from files in migrations directory.
    """

    def __init__(
        self,
        version: str,
        description: str,
        migration_dir: Path,
    ) -> None:
        """Initialize SQL migration.

        Args:
            version: Migration version identifier
            description: Human-readable description
            migration_dir: Directory containing migration files
        """
        self._version = version
        self._description = description
        self.migration_dir = migration_dir

    @property
    def version(self) -> str:
        return self._version

    @property
    def description(self) -> str:
        return self._description

    def up(self, conn: sqlite3.Connection) -> None:
        """Apply up migration from SQL file."""
        up_file = self.migration_dir / f"{self.version}__up.sql"
        if not up_file.exists():
            raise FileNotFoundError(f"Up migration file not found: {up_file}")

        sql = up_file.read_text()
        conn.executescript(sql)

    def down(self, conn: sqlite3.Connection) -> None:
        """Apply down migration from SQL file."""
        down_file = self.migration_dir / f"{self.version}__down.sql"
        if not down_file.exists():
            raise FileNotFoundError(f"Down migration file not found: {down_file}")

        sql = down_file.read_text()
        conn.executescript(sql)


# ============================================================================#
# Migration Discovery
# ============================================================================#


class MigrationLoader:
    """Discover and load migration files from directory."""

    def __init__(self, migration_dir: Path) -> None:
        """Initialize migration loader.

        Args:
            migration_dir: Directory containing migration files
        """
        self.migration_dir = migration_dir

    def discover_migrations(self) -> list[SQLMigration]:
        """Discover all SQL migrations in directory.

        Returns:
            List of migrations sorted by version

        Raises:
            ValueError: If migration files are malformed
        """
        if not self.migration_dir.exists():
            return []

        migrations: dict[str, SQLMigration] = {}

        # Find all up migration files
        for up_file in sorted(self.migration_dir.glob("*__up.sql")):
            # Extract version from filename (e.g., "V1__initial_schema__up.sql")
            version = up_file.stem.replace("__up", "")

            # Extract description from version (e.g., "V1__initial_schema")
            parts = version.split("__", 1)
            if len(parts) < 2:
                raise ValueError(f"Invalid migration version format: {version}")

            description = parts[1].replace("_", " ").title()

            migrations[version] = SQLMigration(
                version=version,
                description=description,
                migration_dir=self.migration_dir,
            )

        # Return sorted by version
        return sorted(migrations.values(), key=lambda m: m.version)


# ============================================================================#
# Migration Manager
# ============================================================================#


class MigrationManager:
    """Manage database schema migrations.

    Features:
    - Discover and apply migrations
    - Track migration history
    - Support rollback
    - Dry-run mode for validation
    """

    def __init__(
        self,
        db_path: Path,
        migration_dir: Path,
    ) -> None:
        """Initialize migration manager.

        Args:
            db_path: Path to SQLite database
            migration_dir: Directory containing migration files
        """
        self.db_path = db_path
        self.migration_dir = migration_dir
        self.loader = MigrationLoader(migration_dir)

    # -----------------------------------------------------------------------#
    # Public API
    # -----------------------------------------------------------------------#

    def get_status(self) -> dict[str, object]:
        """Get migration status.

        Returns:
            Dictionary with:
            - current_version: Currently applied version
            - pending_migrations: List of pending migrations
            - applied_migrations: List of applied migrations
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            # Ensure migrations table exists
            self._ensure_migrations_table(conn)

            # Get applied migrations
            cursor = conn.execute(
                """
                SELECT version, applied_at, description
                FROM skill_migrations
                ORDER BY applied_at ASC
                """
            )
            applied = [dict(row) for row in cursor.fetchall()]

            # Get all available migrations
            all_migrations = self.loader.discover_migrations()

            # Find pending migrations
            applied_versions = {row["version"] for row in applied}
            pending = [
                {"version": m.version, "description": m.description}
                for m in all_migrations
                if m.version not in applied_versions
            ]

            # Current version is most recently applied
            current_version = applied[-1]["version"] if applied else None

            return {
                "current_version": current_version,
                "applied_migrations": applied,
                "pending_migrations": pending,
                "total_applied": len(applied),
                "total_pending": len(pending),
            }
        finally:
            conn.close()

    def migrate(
        self,
        target_version: str | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        """Apply pending migrations.

        Args:
            target_version: Specific version to migrate to (default: latest)
            dry_run: If True, don't actually apply migrations

        Returns:
            List of applied migration versions

        Raises:
            MigrationError: If migration fails
        """
        conn = sqlite3.connect(self.db_path)

        try:
            # Ensure migrations table exists
            self._ensure_migrations_table(conn)

            # Get all available migrations
            all_migrations = self.loader.discover_migrations()

            if not all_migrations:
                return []

            # Get applied migrations
            applied = self._get_applied_versions(conn)

            # Determine which migrations to apply
            to_apply = [m for m in all_migrations if m.version not in applied]

            # Filter by target version if specified
            if target_version:
                to_apply = [m for m in to_apply if m.version <= target_version]

            if not to_apply:
                return []

            # Apply migrations
            applied_versions: list[str] = []

            for migration in to_apply:
                if dry_run:
                    applied_versions.append(migration.version)
                    continue

                # Run in transaction
                with conn:
                    # Apply migration
                    migration.up(conn)

                    # Record migration (use OR IGNORE to handle migrations that self-record)
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO skill_migrations (version, applied_at, description, applied_by)
                        VALUES (?, datetime('now'), ?, 'session-buddy')
                        """,
                        (migration.version, migration.description),
                    )

                    applied_versions.append(migration.version)

            return applied_versions

        except Exception as e:
            conn.rollback()
            raise MigrationError(f"Migration failed: {e}") from e
        finally:
            conn.close()

    def rollback(
        self,
        steps: int = 1,
        dry_run: bool = False,
    ) -> list[str]:
        """Rollback migrations.

        Args:
            steps: Number of migrations to rollback (default: 1)
            dry_run: If True, don't actually rollback

        Returns:
            List of rolled back migration versions

        Raises:
            MigrationError: If rollback fails
        """
        conn = sqlite3.connect(self.db_path)

        try:
            # Get applied migrations (most recent first)
            cursor = conn.execute(
                """
                SELECT version
                FROM skill_migrations
                ORDER BY applied_at DESC
                """
            )
            applied = [row[0] for row in cursor.fetchall()]

            if not applied:
                return []

            # Determine which migrations to rollback
            to_rollback = applied[:steps]

            # Get all migrations for down scripts
            all_migrations = self.loader.discover_migrations()
            migrations_by_version = {m.version: m for m in all_migrations}

            rolled_back: list[str] = []

            for version in to_rollback:
                migration = migrations_by_version.get(version)

                if not migration:
                    raise MigrationError(f"Migration not found: {version}")

                if dry_run:
                    rolled_back.append(version)
                    continue

                # Run in transaction
                with conn:
                    # Remove migration record FIRST (before down migration drops table)
                    conn.execute(
                        "DELETE FROM skill_migrations WHERE version = ?",
                        (version,),
                    )

                    # Rollback migration (may drop skill_migrations table)
                    migration.down(conn)

                    rolled_back.append(version)

            return rolled_back

        except Exception as e:
            conn.rollback()
            raise MigrationError(f"Rollback failed: {e}") from e
        finally:
            conn.close()

    def validate(self) -> list[str]:
        """Validate migration state.

        Checks:
        - All migration files have corresponding records
        - No duplicate migrations
        - Checksums match (if available)

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        conn = sqlite3.connect(self.db_path)

        try:
            # Ensure migrations table exists
            self._ensure_migrations_table(conn)

            # Get applied migrations
            applied = self._get_applied_versions(conn)

            # Check for duplicates
            cursor = conn.execute(
                """
                SELECT version, COUNT(*) as count
                FROM skill_migrations
                GROUP BY version
                HAVING count > 1
                """
            )
            duplicates = cursor.fetchall()
            if duplicates:
                errors.extend(
                    f"Duplicate migration {row[0]} applied {row[1]} times"
                    for row in duplicates
                )

            # Check that all applied migrations still exist
            all_migrations = self.loader.discover_migrations()
            available_versions = {m.version for m in all_migrations}

            for version in applied:
                if version not in available_versions:
                    errors.append(
                        f"Applied migration {version} not found in migration directory"
                    )

            return errors

        finally:
            conn.close()

    # -----------------------------------------------------------------------#
    # Private Helpers
    # -----------------------------------------------------------------------#

    def _ensure_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Create migrations table if it doesn't exist."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT,
                rollback_sql TEXT,
                checksum TEXT,
                applied_by TEXT DEFAULT 'session-buddy',
                success BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )

    def _get_applied_versions(self, conn: sqlite3.Connection) -> set[str]:
        """Get set of applied migration versions."""
        cursor = conn.execute(
            "SELECT version FROM skill_migrations ORDER BY applied_at ASC"
        )
        return {row[0] for row in cursor.fetchall()}


# ============================================================================#
# Exceptions
# ============================================================================#


class MigrationError(Exception):
    """Error during migration execution."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause
