#!/usr/bin/env python3
"""Migrate skills metrics from JSON to Dhruva storage.

This script migrates existing skills metrics data from the crackerjack JSON
format to the new Dhruva SQLite database with ACID guarantees.

Features:
- Discovery of JSON metrics files
- Incremental migration (skip already-imported)
- Validation and rollback on failure
- Backup support
- Dry-run mode for testing

Usage:
    # Migrate with backup
    python -m session_buddy.scripts.migrate_json_to_dhruva migrate

    # Dry-run (no changes)
    python -m session_buddy.scripts.migrate_json_to_dhruva migrate --dry-run

    # Validate migration
    python -m session_buddy.scripts.migrate_json_to_dhruva validate

    # Show migration status
    python -m session_buddy.scripts.migrate_json_to_dhruva status
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class JSONInvocation:
    """Invocation record from JSON file."""

    skill_name: str
    invoked_at: str
    session_id: str = "migrated"
    workflow_path: str | None = None
    completed: bool = False
    duration_seconds: float | None = None
    user_query: str | None = None
    alternatives_considered: list[str] = field(default_factory=list)
    selection_rank: int | None = None
    follow_up_actions: list[str] = field(default_factory=list)
    error_type: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> JSONInvocation:
        """Create from JSON dictionary."""
        return cls(
            skill_name=data["skill_name"],
            invoked_at=data["invoked_at"],
            session_id=data.get("session_id", "migrated"),
            workflow_path=data.get("workflow_path"),
            completed=data.get("completed", False),
            duration_seconds=data.get("duration_seconds"),
            user_query=data.get("user_query"),
            alternatives_considered=data.get("alternatives_considered", []),
            selection_rank=data.get("selection_rank"),
            follow_up_actions=data.get("follow_up_actions", []),
            error_type=data.get("error_type"),
        )


@dataclass
class MigrationStats:
    """Statistics from migration operation."""

    total_found: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def __add__(self, other: MigrationStats) -> MigrationStats:
        """Combine two stats objects."""
        return MigrationStats(
            total_found=self.total_found + other.total_found,
            imported=self.imported + other.imported,
            skipped=self.skipped + other.skipped,
            failed=self.failed + other.failed,
            errors=self.errors + other.errors,
        )


# ============================================================================
# Migration Engine
# ============================================================================


class JSONToDhruvaMigrator:
    """Migrate skills metrics from JSON to Dhruva storage."""

    def __init__(
        self,
        db_path: Path,
        json_dir: Path,
        backup_dir: Path | None = None,
    ) -> None:
        """Initialize migrator.

        Args:
            db_path: Path to SQLite database
            json_dir: Directory containing JSON metrics files
            backup_dir: Optional directory for database backups
        """
        self.db_path = db_path
        self.json_dir = json_dir
        self.backup_dir = backup_dir or json_dir / ".migrate_backups"

    # -----------------------------------------------------------------------#
    # Discovery
    # -----------------------------------------------------------------------#

    def discover_json_files(self) -> list[Path]:
        """Discover all JSON metrics files.

        Returns:
            List of JSON file paths
        """
        if not self.json_dir.exists():
            return []

        # Common JSON metrics file locations
        patterns = [
            "skill_metrics.json",
            ".session-buddy/skill_metrics.json",
            "metrics/skill_metrics.json",
        ]

        found: list[Path] = []

        # Check exact patterns
        for pattern in patterns:
            path = self.json_dir / pattern
            if path.exists():
                found.append(path)

        # Search recursively
        found.extend(self.json_dir.rglob("skill_metrics.json"))

        # Deduplicate
        return sorted(set(found))

    # -----------------------------------------------------------------------#
    # Migration
    # -----------------------------------------------------------------------#

    def migrate(
        self,
        dry_run: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> MigrationStats:
        """Migrate all discovered JSON files.

        Args:
            dry_run: If True, don't actually import data
            progress_callback: Optional callback for progress updates

        Returns:
            Migration statistics
        """
        json_files = self.discover_json_files()

        if not json_files:
            print("No JSON metrics files found.")
            return MigrationStats()

        total_stats = MigrationStats()
        total_files = len(json_files)

        for i, json_file in enumerate(json_files, 1):
            if progress_callback:
                progress_callback(i, total_files)

            print(f"\n[{i}/{total_files}] Migrating {json_file.name}")

            try:
                file_stats = self.migrate_file(json_file, dry_run=dry_run)
                total_stats += file_stats

                print(f"  ✓ Found: {file_stats.total_found}")
                print(f"  ✓ Imported: {file_stats.imported}")
                if file_stats.skipped > 0:
                    print(f"  ⊙ Skipped: {file_stats.skipped} (already imported)")
                if file_stats.failed > 0:
                    print(f"  ✗ Failed: {file_stats.failed}")

            except Exception as e:
                print(f"  ✗ Error: {e}")
                total_stats.failed += 1
                total_stats.errors.append(f"{json_file}: {e}")

        return total_stats

    def migrate_file(
        self,
        json_file: Path,
        dry_run: bool = False,
    ) -> MigrationStats:
        """Migrate a single JSON file.

        Args:
            json_file: Path to JSON metrics file
            dry_run: If True, don't actually import data

        Returns:
            Migration statistics for this file
        """
        # Load JSON data
        try:
            data = json.loads(json_file.read_text())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        # Validate structure
        if "invocations" not in data:
            raise ValueError("Missing 'invocations' key in JSON")

        stats = MigrationStats(total_found=len(data["invocations"]))

        # Create backup if not dry-run
        if not dry_run:
            self._create_backup()

        # Import in transaction
        conn = sqlite3.connect(self.db_path)

        try:
            # Ensure schema exists (apply V1 migration if needed)
            if not dry_run:
                self._ensure_schema(conn)

            for inv_data in data.get("invocations", []):
                try:
                    # Parse invocation
                    invocation = JSONInvocation.from_dict(inv_data)

                    if dry_run:
                        stats.imported += 1
                        continue

                    # Check if already imported
                    cursor = conn.execute(
                        """
                        SELECT id FROM skill_invocation
                        WHERE invoked_at = ? AND skill_name = ?
                        """,
                        (invocation.invoked_at, invocation.skill_name),
                    )

                    if cursor.fetchone() is not None:
                        stats.skipped += 1
                        continue

                    # Import invocation
                    self._import_invocation(conn, invocation)
                    stats.imported += 1

                except Exception as e:
                    stats.failed += 1
                    stats.errors.append(
                        f"{invocation.skill_name}@{invocation.invoked_at}: {e}"
                    )

            # Commit transaction
            if not dry_run:
                conn.commit()

            return stats

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _import_invocation(
        self,
        conn: sqlite3.Connection,
        invocation: JSONInvocation,
    ) -> None:
        """Import a single invocation to database.

        Args:
            conn: Database connection
            invocation: Invocation to import
        """
        # Convert lists to JSON
        alternatives_json = (
            json.dumps(invocation.alternatives_considered)
            if invocation.alternatives_considered
            else None
        )
        actions_json = (
            json.dumps(invocation.follow_up_actions)
            if invocation.follow_up_actions
            else None
        )

        # Insert invocation (trigger updates metrics automatically)
        conn.execute(
            """
            INSERT INTO skill_invocation (
                skill_name, invoked_at, session_id, workflow_path,
                completed, duration_seconds,
                user_query, alternatives_considered, selection_rank,
                follow_up_actions, error_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invocation.skill_name,
                invocation.invoked_at,
                invocation.session_id,
                invocation.workflow_path,
                1 if invocation.completed else 0,
                invocation.duration_seconds,
                invocation.user_query,
                alternatives_json,
                invocation.selection_rank,
                actions_json,
                invocation.error_type,
            ),
        )

    # -----------------------------------------------------------------------#
    # Validation
    # -----------------------------------------------------------------------#

    def validate_migration(self) -> list[str]:
        """Validate migration state.

        Checks:
        - All invocations have valid skill_name
        - All session_ids exist
        - No duplicate (invoked_at, skill_name) pairs
        - Metrics are consistent with invocations

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        if not self.db_path.exists():
            return ["Database does not exist"]

        conn = sqlite3.connect(self.db_path)

        try:
            # Check for duplicates
            cursor = conn.execute(
                """
                SELECT invoked_at, skill_name, COUNT(*) as count
                FROM skill_invocation
                GROUP BY invoked_at, skill_name
                HAVING count > 1
                """
            )
            duplicates = cursor.fetchall()
            if duplicates:
                errors.extend(
                    f"Duplicate invocation {row[0]}@{row[1]} ({row[2]} copies)"
                    for row in duplicates
                )

            # Check orphaned session_skills
            cursor = conn.execute(
                """
                SELECT ss.session_id, ss.skill_name
                FROM session_skills ss
                LEFT JOIN skill_invocation si
                    ON ss.session_id = si.session_id
                    AND ss.skill_name = si.skill_name
                WHERE si.id IS NULL
                """
            )
            orphaned = cursor.fetchall()
            if orphaned:
                errors.extend(
                    f"Orphaned session_skills entry: {row[0]}@{row[1]}"
                    for row in orphaned
                )

            # Verify metrics consistency
            cursor = conn.execute(
                """
                SELECT sm.skill_name,
                    sm.total_invocations as metrics_count,
                    (SELECT COUNT(*) FROM skill_invocation WHERE skill_name = sm.skill_name) as actual_count
                FROM skill_metrics sm
                WHERE sm.total_invocations != (
                    SELECT COUNT(*) FROM skill_invocation WHERE skill_name = sm.skill_name
                )
                """
            )
            inconsistent = cursor.fetchall()
            if inconsistent:
                errors.extend(
                    f"Inconsistent metrics for {row[0]}: metrics={row[1]}, actual={row[2]}"
                    for row in inconsistent
                )

            return errors

        finally:
            conn.close()

    # -----------------------------------------------------------------------#
    # Schema Management
    # -----------------------------------------------------------------------#

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Ensure database schema exists.

        Applies V1 migration if skill_invocation table doesn't exist.

        Args:
            conn: Database connection
        """
        # Check if schema exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_invocation'"
        )

        if cursor.fetchone() is not None:
            # Schema already exists
            return

        # Apply V1 migration directly
        # Use absolute path from this file's location
        # Script is in scripts/, go up to root, then into session_buddy/storage/migrations
        script_dir = Path(__file__).parent
        migration_dir = script_dir.parent / "session_buddy" / "storage" / "migrations"
        up_migration = migration_dir / "V1__initial_schema__up.sql"

        if not up_migration.exists():
            raise FileNotFoundError(f"Migration file not found: {up_migration}")

        # Read and execute migration SQL
        sql = up_migration.read_text()
        conn.executescript(sql)

    # -----------------------------------------------------------------------#
    # Backup
    # -----------------------------------------------------------------------#

    def _create_backup(self) -> Path:
        """Create backup of database.

        Returns:
            Path to backup file
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"skills_backup_{timestamp}.db"

        if self.db_path.exists():
            shutil.copy2(self.db_path, backup_path)

        return backup_path

    # -----------------------------------------------------------------------#
    # Status
    # -----------------------------------------------------------------------#

    def get_status(self) -> dict[str, object]:
        """Get migration status.

        Returns:
            Dictionary with status information
        """
        json_files = self.discover_json_files()

        # Check database status
        db_exists = self.db_path.exists()
        db_invocations = 0

        if db_exists:
            try:
                conn = sqlite3.connect(self.db_path)
                try:
                    cursor = conn.execute("SELECT COUNT(*) FROM skill_invocation")
                    db_invocations = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    # Table doesn't exist yet
                    db_invocations = 0
                finally:
                    conn.close()
            except Exception:
                # Database exists but can't be read
                db_invocations = 0

        # Count JSON invocations
        json_invocations = 0
        for json_file in json_files:
            try:
                data = json.loads(json_file.read_text())
                json_invocations += len(data.get("invocations", []))
            except Exception:
                pass

        return {
            "json_files_found": len(json_files),
            "json_invocations": json_invocations,
            "db_exists": db_exists,
            "db_invocations": db_invocations,
            "migrated": db_invocations > 0,
            "json_files": [str(f) for f in json_files],
        }


# ============================================================================
# CLI
# ============================================================================#


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run migration."""
    migrator = JSONToDhruvaMigrator(
        db_path=args.db_path,
        json_dir=args.json_dir,
        backup_dir=args.backup_dir,
    )

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    def progress_callback(current: int, total: int) -> None:
        print(f"Progress: {current}/{total} files")

    stats = migrator.migrate(dry_run=args.dry_run, progress_callback=progress_callback)

    # Print summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Total found:     {stats.total_found}")
    print(f"Imported:       {stats.imported}")
    print(f"Skipped:        {stats.skipped}")
    print(f"Failed:         {stats.failed}")

    if stats.errors:
        print(f"\nErrors: {len(stats.errors)}")
        for error in stats.errors[:5]:
            print(f"  ✗ {error}")
        if len(stats.errors) > 5:
            print(f"  ... and {len(stats.errors) - 5} more")

    if stats.failed > 0:
        return 1

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show migration status."""
    migrator = JSONToDhruvaMigrator(
        db_path=args.db_path,
        json_dir=args.json_dir,
    )

    status = migrator.get_status()

    print("=" * 60)
    print("JSON to Dhruva Migration Status")
    print("=" * 60)
    print(f"\nDatabase: {args.db_path}")
    print(f"Search Directory: {args.json_dir}")
    print(f"\nJSON Files Found: {status['json_files_found']}")
    print(f"JSON Invocations: {status['json_invocations']}")
    print(f"\nDatabase Exists: {status['db_exists']}")
    print(f"Database Invocations: {status['db_invocations']}")
    print(f"Migrated: {status['migrated']}")

    if status["json_files"]:
        print("\nJSON Files:")
        for f in status["json_files"]:
            print(f"  • {f}")

    print("\n" + "=" * 60)

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate migration."""
    migrator = JSONToDhruvaMigrator(
        db_path=args.db_path,
        json_dir=args.json_dir,
    )

    errors = migrator.validate_migration()

    if not errors:
        print("✓ Migration state is valid")
        return 0

    print("Migration validation errors:", file=sys.stderr)
    for error in errors:
        print(f"  ✗ {error}", file=sys.stderr)

    return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate skills metrics from JSON to Dhruva",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show status
  %(prog)s status

  # Migrate with backup
  %(prog)s migrate

  # Dry-run migration
  %(prog)s migrate --dry-run

  # Validate migration
  %(prog)s validate
        """,
    )

    # Global options
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path.cwd() / ".session-buddy" / "skills.db",
        help="Path to SQLite database (default: .session-buddy/skills.db)",
    )
    parser.add_argument(
        "--json-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to search for JSON files (default: current directory)",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for database backups (default: .migrate_backups/)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate JSON data to Dhruva",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    # status command
    subparsers.add_parser(
        "status",
        help="Show migration status",
    )

    # validate command
    subparsers.add_parser(
        "validate",
        help="Validate migration state",
    )

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Dispatch to command handler
    commands = {
        "migrate": cmd_migrate,
        "status": cmd_status,
        "validate": cmd_validate,
    }

    handler = commands[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
