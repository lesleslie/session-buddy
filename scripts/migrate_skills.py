#!/usr/bin/env python3
"""Migration CLI for skills metrics schema.

Provides command-line interface for database schema migrations.
Supports applying migrations, rollback, status checking, and validation.

Usage:
    python -m session_buddy.storage.migrations.migrate status
    python -m session_buddy.storage.migrations.migrate migrate
    python -m session_buddy.storage.migrations.migrate rollback
    python -m session_buddy.storage.migrations.migrate validate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from session_buddy.storage.migrations import (
    MigrationError,
    get_migration_manager,
)


def cmd_status(args: argparse.Namespace) -> int:
    """Show migration status."""
    manager = get_migration_manager(
        db_path=args.db_path,
        migration_dir=args.migration_dir,
    )

    status = manager.get_status()

    print("=" * 60)
    print("Skills Metrics Migration Status")
    print("=" * 60)
    print(f"\nDatabase: {args.db_path}")
    print(f"Migration Directory: {args.migration_dir}")
    print(f"\nCurrent Version: {status['current_version'] or 'None (empty database)'}")
    print(f"Applied Migrations: {status['total_applied']}")
    print(f"Pending Migrations: {status['total_pending']}")

    if status["applied_migrations"]:
        print("\nApplied Migrations:")
        for migration in status["applied_migrations"]:
            print(f"  ✓ {migration['version']}: {migration['description']}")
            print(f"    Applied at: {migration['applied_at']}")

    if status["pending_migrations"]:
        print("\nPending Migrations:")
        for migration in status["pending_migrations"]:
            print(f"  ⏳ {migration['version']}: {migration['description']}")

    print("\n" + "=" * 60)

    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Apply pending migrations."""
    manager = get_migration_manager(
        db_path=args.db_path,
        migration_dir=args.migration_dir,
    )

    try:
        if args.dry_run:
            print("DRY RUN MODE - No changes will be made\n")

        applied = manager.migrate(
            target_version=args.target,
            dry_run=args.dry_run,
        )

        if not applied:
            print("No pending migrations to apply.")
            return 0

        print(f"Applying {len(applied)} migration(s)...")
        for version in applied:
            action = "[WOULD APPLY]" if args.dry_run else "[APPLYING]"
            print(f"  {action} {version}")

        if args.dry_run:
            print("\nDry run complete - no changes made.")
        else:
            print("\nMigration complete!")

        return 0

    except MigrationError as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        return 1


def cmd_rollback(args: argparse.Namespace) -> int:
    """Rollback migrations."""
    manager = get_migration_manager(
        db_path=args.db_path,
        migration_dir=args.migration_dir,
    )

    try:
        if args.dry_run:
            print("DRY RUN MODE - No changes will be made\n")

        rolled_back = manager.rollback(
            steps=args.steps,
            dry_run=args.dry_run,
        )

        if not rolled_back:
            print("No migrations to rollback.")
            return 0

        print(f"Rolling back {len(rolled_back)} migration(s)...")
        for version in rolled_back:
            action = "[WOULD ROLLBACK]" if args.dry_run else "[ROLLING BACK]"
            print(f"  {action} {version}")

        if args.dry_run:
            print("\nDry run complete - no changes made.")
        else:
            print("\nRollback complete!")

        return 0

    except MigrationError as e:
        print(f"Rollback failed: {e}", file=sys.stderr)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate migration state."""
    manager = get_migration_manager(
        db_path=args.db_path,
        migration_dir=args.migration_dir,
    )

    errors = manager.validate()

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
        description="Skills Metrics Schema Migration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show migration status
  %(prog)s status

  # Apply all pending migrations
  %(prog)s migrate

  # Apply specific version
  %(prog)s migrate --target V1__initial_schema

  # Dry-run migration (no changes)
  %(prog)s migrate --dry-run

  # Rollback last migration
  %(prog)s rollback

  # Rollback 3 migrations
  %(prog)s rollback --steps 3

  # Validate migration state
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
        "--migration-dir",
        type=Path,
        default=Path(__file__).parent.parent / "storage" / "migrations",
        help="Path to migration directory",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # status command
    subparsers.add_parser(
        "status",
        help="Show migration status",
    )

    # migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply pending migrations",
    )
    migrate_parser.add_argument(
        "--target",
        help="Target version (default: latest)",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    # rollback command
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Rollback migrations",
    )
    rollback_parser.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Number of migrations to rollback (default: 1)",
    )
    rollback_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
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
        "status": cmd_status,
        "migrate": cmd_migrate,
        "rollback": cmd_rollback,
        "validate": cmd_validate,
    }

    handler = commands[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
