#!/usr/bin/env python3
"""ULID Migration Runner for Session-Buddy.

Uses direct DuckDB connections for ULID backfill.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import duckdb
except ImportError:
    print("❌ DuckDB not installed. Install with: pip install duckdb")
    sys.exit(1)

from session_buddy.core.ulid_generator import generate_ulid


def get_db_path():
    """Get Session-Buddy database path."""
    db_dir = Path.home() / ".cache" / "session-buddy"
    return db_dir / "session_buddy.db"


def backfill_conversations(conn):
    """Backfill ULIDs for existing conversations."""
    result = conn.execute(
        "SELECT id FROM conversations WHERE conversation_ulid IS NULL"
    ).fetchall()

    for (conversation_id,) in result:
        ulid = generate_ulid()
        conn.execute(
            "UPDATE conversations SET conversation_ulid = ?, conversation_ulid_generated_at = NOW() WHERE id = ?",
            [ulid, conversation_id]
        )

    conn.commit()
    return len(result)


def backfill_reflections(conn):
    """Backfill ULIDs for existing reflections."""
    result = conn.execute(
        "SELECT id FROM reflections WHERE reflection_ulid IS NULL"
    ).fetchall()

    for (reflection_id,) in result:
        ulid = generate_ulid()
        conn.execute(
            "UPDATE reflections SET reflection_ulid = ?, reflection_ulid_generated_at = NOW() WHERE id = ?",
            [ulid, reflection_id]
        )

    conn.commit()
    return len(result)


def backfill_code_graphs(conn):
    """Backfill ULIDs for existing code graphs."""
    result = conn.execute(
        "SELECT id FROM code_graphs WHERE code_graph_ulid IS NULL"
    ).fetchall()

    for (graph_id,) in result:
        ulid = generate_ulid()
        conn.execute(
            "UPDATE code_graphs SET code_graph_ulid = ?, code_graph_ulid_generated_at = NOW() WHERE id = ?",
            [ulid, graph_id]
        )

    conn.commit()
    return len(result)


def run_migration():
    """Run ULID migration for Session-Buddy."""

    print("=" * 60)
    print("Session-Buddy ULID Migration")
    print("=" * 60)
    print()
    print("📊 Phase 1: Expanding Schema")
    print("   (Skipping - SQL migration already applied)")
    print()
    print("📊 Phase 2: Backfilling ULIDs")
    print("   Generating ULIDs for existing records...")

    db_path = get_db_path()

    if not db_path.exists():
        print(f"   ⚠️  Database not found at {db_path}")
        print("   No migration needed - database doesn't exist yet")
        return

    # Connect to database
    conn = duckdb.connect(str(db_path))

    try:
        # Backfill all tables
        conversations_count = backfill_conversations(conn)
        print(f"   ✅ Conversations backfilled: {conversations_count} records")

        reflections_count = backfill_reflections(conn)
        print(f"   ✅ Reflections backfilled: {reflections_count} records")

        graphs_count = backfill_code_graphs(conn)
        print(f"   ✅ Code graphs backfilled: {graphs_count} records")

        total = conversations_count + reflections_count + graphs_count

        print()
        print("🎉 Migration Complete!")
        print(f"   Total records migrated: {total} records across 3 tables")
        print()
        print("⏭️  Next Steps:")
        print("   1. Application code updated to use ULID for new records")
        print("   2. Verification period: 14 days (keep both IDs active)")
        print("   3. After verification, can switch to ULID as primary identifier")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
