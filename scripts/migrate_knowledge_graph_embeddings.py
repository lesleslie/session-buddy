#!/usr/bin/env python3
"""Migration script to add embeddings to knowledge graph entities.

This script:
1. Adds the 'embedding' column to kg_entities table
2. Generates embeddings for all existing entities
3. Updates entities with their embeddings

Usage:
    python scripts/migrate_knowledge_graph_embeddings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Add embeddings to knowledge graph entities"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without making changes",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="~/.claude/data/knowledge_graph.duckdb",
        help="Path to knowledge graph database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for embedding generation",
    )
    return parser.parse_args()


async def add_embedding_column(conn: Any, dry_run: bool = False) -> bool:
    """Add embedding column to kg_entities table.

    Args:
        conn: DuckDB connection
        dry_run: If True, simulate without making changes

    Returns:
        True if column was added or already exists

    """
    # Check if column exists
    result = conn.execute(
        "SELECT COUNT(*) FROM pragma_table_info('kg_entities') WHERE name = 'embedding'"
    ).fetchone()

    column_exists = result[0] > 0 if result else False

    if column_exists:
        print("✅ Embedding column already exists")
        return True

    if dry_run:
        print("[DRY RUN] Would add embedding column to kg_entities")
        return True

    try:
        conn.execute("ALTER TABLE kg_entities ADD COLUMN embedding FLOAT[384]")
        print("✅ Added embedding column to kg_entities")
        return True
    except Exception as e:
        print(f"❌ Failed to add embedding column: {e}")
        return False


async def generate_embedding_for_entity(entity: dict[str, Any]) -> list[float] | None:
    """Generate embedding for a single entity.

    Args:
        entity: Entity dictionary with name and observations

    Returns:
        Embedding vector or None if generation failed

    """
    try:
        from session_buddy.reflection.embeddings import generate_embedding

        # Combine name and observations for embedding text
        text_parts = [entity["name"]]

        # Add observations if available
        observations = entity.get("observations", [])
        if observations:
            text_parts.extend(observations)

        text = " ".join(text_parts)

        # Generate embedding
        embedding = await generate_embedding(text)

        return embedding
    except Exception as e:
        print(f"⚠️  Failed to generate embedding for {entity['name']}: {e}")
        return None


async def migrate_embeddings(
    db_path: str, dry_run: bool = False, batch_size: int = 50
) -> dict[str, int]:
    """Migrate embeddings for all entities.

    Args:
        db_path: Path to DuckDB database
        dry_run: If True, simulate without making changes
        batch_size: Batch size for processing

    Returns:
        Statistics about migration

    """
    import duckdb

    print(f"📊 Connecting to database: {db_path}")

    if dry_run:
        print("[DRY RUN] Simulating migration (no changes will be made)")

    conn = duckdb.connect(db_path)

    # Add embedding column
    print("\n=== Step 1: Add Embedding Column ===")
    if not await add_embedding_column(conn, dry_run):
        return {"error": "Failed to add embedding column"}

    # Get entities without embeddings
    print("\n=== Step 2: Find Entities Needing Embeddings ===")
    result = conn.execute(
        """
        SELECT id, name, entity_type, observations
        FROM kg_entities
        WHERE embedding IS NULL
        ORDER BY created_at DESC
        """
    ).fetchall()

    entities = [
        {
            "id": row[0],
            "name": row[1],
            "entity_type": row[2],
            "observations": row[3] if row[3] else [],
        }
        for row in result
    ]

    total = len(entities)
    print(f"📊 Found {total} entities without embeddings")

    if total == 0:
        print("✅ All entities already have embeddings")
        return {"total": total, "processed": 0, "success": 0, "failed": 0}

    # Initialize embedding system
    print("\n=== Step 3: Initialize Embedding System ===")
    try:
        from session_buddy.reflection.embeddings import initialize_embedding_system

        embedding_session = initialize_embedding_system()

        if embedding_session is None:
            # Try to continue anyway - may use transformers fallback
            print("⚠️  ONNX session not available, trying transformers fallback")

        print("✅ Embedding system initialized")
    except Exception as e:
        print(f"❌ Failed to initialize embedding system: {e}")
        return {"error": f"Failed to initialize embedding system: {e}"}

    # Process in batches
    print(f"\n=== Step 4: Generate Embeddings (batch size={batch_size}) ===")

    success_count = 0
    failed_count = 0
    processed_count = 0

    for i in range(0, total, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(
            f"\nBatch {batch_num}/{total_batches} (entities {i + 1}-{min(i + batch_size, total)})"
        )

        for entity in batch:
            processed_count += 1

            # Generate embedding
            embedding = await generate_embedding_for_entity(entity)

            if embedding is None:
                failed_count += 1
                continue

            # Update database
            if not dry_run:
                try:
                    conn.execute(
                        """
                        UPDATE kg_entities
                        SET embedding = ?
                        WHERE id = ?
                        """,
                        (embedding, entity["id"]),
                    )
                    success_count += 1
                except Exception as e:
                    print(f"  ❌ Failed to update {entity['name']}: {e}")
                    failed_count += 1
            else:
                success_count += 1

            # Progress indicator
            if processed_count % 10 == 0:
                print(
                    f"  Progress: {processed_count}/{total} ({processed_count * 100 // total}%)"
                )

    # Summary
    print("\n=== Migration Summary ===")
    print(f"📊 Total entities: {total}")
    print(f"✅ Successfully processed: {success_count}")
    print(f"❌ Failed: {failed_count}")

    # Verify results
    if not dry_run:
        print("\n=== Verification ===")
        result = conn.execute(
            "SELECT COUNT(*) FROM kg_entities WHERE embedding IS NOT NULL"
        ).fetchone()
        with_embeddings = result[0] if result else 0
        print(f"📊 Entities with embeddings: {with_embeddings}/{total}")

    conn.close()

    return {
        "total": total,
        "processed": processed_count,
        "success": success_count,
        "failed": failed_count,
    }


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    print("=" * 60)
    print("Knowledge Graph Embedding Migration")
    print("=" * 60)

    # Expand path
    db_path = str(Path(args.db_path).expanduser())

    # Run migration
    stats = await migrate_embeddings(
        db_path=db_path,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )

    if "error" in stats:
        print(f"\n❌ Migration failed: {stats['error']}")
        return 1

    print("\n✅ Migration complete!")
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
