"""Migration script for knowledge graph database to ACB adapter.

This script migrates data from the original KnowledgeGraphDatabase to the new
KnowledgeGraphDatabaseAdapter that uses ACB configuration.

Usage:
    # Dry run (preview changes without modifying data)
    python scripts/migrate_graph_database.py --dry-run

    # Create backup before migration
    python scripts/migrate_graph_database.py --backup

    # Verbose output
    python scripts/migrate_graph_database.py --verbose

    # Combination
    python scripts/migrate_graph_database.py --backup --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from session_buddy.paths import data_dir


def get_data_dir() -> Path:
    """Get the data directory path."""
    return data_dir()


def get_old_db_path() -> Path:
    """Get path to old knowledge graph database."""
    return get_data_dir() / "knowledge_graph.duckdb"


def get_new_db_path() -> Path:
    """Get path for new ACB-managed database."""
    return get_data_dir() / "knowledge_graph_acb.duckdb"


def get_backup_path() -> Path:
    """Get timestamped backup path."""
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    return get_data_dir() / f"knowledge_graph_backup_{timestamp}.duckdb"


async def migrate_graph_database(
    *,
    dry_run: bool = False,
    backup: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    """Migrate knowledge graph data from old schema to new ACB adapter.

    Args:
        dry_run: If True, preview changes without modifying data
        backup: If True, create backup before migration
        verbose: If True, print detailed progress information

    Returns:
        Dictionary with migration statistics

    Raises:
        FileNotFoundError: If old database doesn't exist
        RuntimeError: If migration fails

    """
    old_db_path = get_old_db_path()

    # Check if old database exists
    if not old_db_path.exists():
        msg = f"Old database not found at {old_db_path}"
        raise FileNotFoundError(msg)

    if verbose:
        _print_migration_config(old_db_path, dry_run, backup)

    # Create backup if requested
    if backup and not dry_run:
        await _create_backup_graph(old_db_path, verbose)

    # Read data from old database
    entities, relationships = await _read_old_graph_data(old_db_path, verbose)

    # If dry run, just report what would be migrated
    if dry_run:
        return await _handle_dry_run_graph(entities, relationships)

    # Write to new database using adapter
    await _migrate_to_new_database(entities, relationships, verbose)

    # Validate migration
    await _validate_graph_migration(entities, relationships, verbose)

    if verbose:
        pass

    return {
        "entities_migrated": len(entities),
        "relationships_migrated": len(relationships),
        "total_records": len(entities) + len(relationships),
    }


def _print_migration_config(old_db_path, dry_run: bool, backup: bool) -> None:
    """Print migration configuration."""
    get_new_db_path()


async def _create_backup_graph(old_db_path, verbose: bool) -> None:
    """Create backup of old database if requested."""
    backup_path = get_backup_path()
    if verbose:
        pass
    shutil.copy2(old_db_path, backup_path)
    if verbose:
        pass


async def _read_old_graph_data(old_db_path, verbose: bool):
    """Read entities and relationships from old database."""
    import duckdb

    if verbose:
        pass

    old_conn = duckdb.connect(str(old_db_path), read_only=True)

    try:
        # Get table list
        tables_result = old_conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('kg_entities', 'kg_relationships')
        """,
        ).fetchall()
        tables = [row[0] for row in tables_result]

        if verbose:
            pass

        # Read entities
        entities = []
        if "kg_entities" in tables:
            entities = await _read_entities(old_conn, verbose)

        # Read relationships
        relationships = []
        if "kg_relationships" in tables:
            relationships = await _read_relationships(old_conn, verbose)

        if verbose:
            pass

        return entities, relationships
    finally:
        old_conn.close()


async def _read_entities(old_conn, verbose: bool):
    """Read entities from old database."""
    entity_result = old_conn.execute("SELECT * FROM kg_entities").fetchall()
    entities = [
        {
            "id": row[0],
            "name": row[1],
            "entity_type": row[2],
            "observations": list(row[3]) if row[3] else [],
            "properties": row[4] or {},
            "created_at": row[5],
            "updated_at": row[6],
            "metadata": row[7] or {},
        }
        for row in entity_result
    ]

    if verbose:
        pass
    return entities


async def _read_relationships(old_conn, verbose: bool):
    """Read relationships from old database."""
    rel_result = old_conn.execute("SELECT * FROM kg_relationships").fetchall()
    return [
        {
            "id": row[0],
            "from_entity": row[1],
            "to_entity": row[2],
            "relation_type": row[3],
            "properties": row[4] or {},
            "created_at": row[5],
            "updated_at": row[6],
            "metadata": row[7] or {},
        }
        for row in rel_result
    ]


async def _handle_dry_run_graph(entities, relationships):
    """Handle dry run scenario."""
    return {"entities": len(entities), "relationships": len(relationships)}


async def _migrate_to_new_database(entities, relationships, verbose: bool) -> None:
    """Write data to the new database using the adapter."""
    from session_buddy.adapters.knowledge_graph_adapter import (
        KnowledgeGraphDatabaseAdapter,
    )

    new_db_path = get_new_db_path()

    if verbose:
        pass

    async with KnowledgeGraphDatabaseAdapter(db_path=new_db_path) as new_db:
        # Migrate entities (preserve IDs and timestamps)
        if verbose:
            pass

        for entity in entities:
            # Direct insert to preserve IDs and timestamps
            conn = new_db._get_conn()
            conn.execute(
                """
                INSERT INTO kg_entities
                (id, name, entity_type, observations, properties, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity["id"],
                    entity["name"],
                    entity["entity_type"],
                    entity["observations"],
                    entity["properties"],
                    entity["created_at"],
                    entity["updated_at"],
                    entity["metadata"],
                ),
            )

        if verbose:
            pass

        # Migrate relationships (preserve IDs and timestamps)
        if verbose:
            pass

        for rel in relationships:
            conn = new_db._get_conn()
            conn.execute(
                """
                INSERT INTO kg_relationships
                (id, from_entity, to_entity, relation_type, properties, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel["id"],
                    rel["from_entity"],
                    rel["to_entity"],
                    rel["relation_type"],
                    rel["properties"],
                    rel["created_at"],
                    rel["updated_at"],
                    rel["metadata"],
                ),
            )

        if verbose:
            pass


async def _validate_graph_migration(entities, relationships, verbose: bool) -> None:
    """Validate the graph migration."""
    from session_buddy.adapters.knowledge_graph_adapter import (
        KnowledgeGraphDatabaseAdapter,
    )

    new_db_path = get_new_db_path()

    # Validate migration
    if verbose:
        pass

    async with KnowledgeGraphDatabaseAdapter(db_path=new_db_path) as new_db:
        stats = await new_db.get_stats()

        # Compare counts
        entities_match = stats["total_entities"] == len(entities)
        relationships_match = stats["total_relationships"] == len(relationships)

        if verbose:
            pass

        if not (entities_match and relationships_match):
            msg = "Migration validation failed - record counts don't match"
            raise RuntimeError(msg)


def main() -> None:
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate knowledge graph database to ACB adapter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview migration without making changes
  python scripts/migrate_graph_database.py --dry-run

  # Migrate with backup
  python scripts/migrate_graph_database.py --backup --verbose

  # Just migrate (no backup)
  python scripts/migrate_graph_database.py
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying data",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before migration",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed progress information",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            migrate_graph_database(
                dry_run=args.dry_run,
                backup=args.backup,
                verbose=args.verbose,
            ),
        )

        if not args.dry_run and args.backup:
            pass

    except FileNotFoundError:
        sys.exit(0)  # Not an error, just nothing to migrate

    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
