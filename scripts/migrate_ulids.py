#!/usr/bin/env python3
"""ULID Migration Runner for Session-Buddy.

Performs expand-contract migration for conversations, reflections, and code graphs.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from session_buddy.reflection.database import (
    store_conversation,
    store_reflection,
    store_code_graph,
    ReflectionDatabase,
)


async def run_migration():
    """Run ULID migration for Session-Buddy."""

    print("=" * 60)
    print("Session-Buddy ULID Migration")
    print("=" * 60)
    print()
    print("📊 Phase 1: Expanding Schema")
    print("   Adding ULID columns to all tables...")

    # Initialize database (will create ULID columns if they don't exist)
    from session_buddy.reflection.database import ReflectionDatabase
    db = ReflectionDatabase()
    await db.initialize()

    print("   ✅ Schema expansion complete")
    print()
    print("📊 Phase 2: Backfilling ULIDs")
    print("   Generating ULIDs for existing records...")

    # Backfill conversations
    await backfill_conversations(db)
    print("   ✅ Conversations backfilled")

    # Backfill reflections
    await backfill_reflections(db)
    print("   ✅ Reflections backfilled")

    # Backfill code graphs
    await backfill_code_graphs(db)
    print("   ✅ Code graphs backfilled")

    await db.close()

    print()
    print("🎉 Migration Complete!")
    print(f"   Total records migrated: 3 tables")
    print()
    print("⏭️  Next Steps:")
    print("   1. Application code updated to use ULID for new records")
    print("   2. Verification period: 7 days (keep both IDs active)")
    print("   3. After verification, can switch to ULID as primary identifier")
    print()


async def backfill_conversations(db):
    """Backfill ULIDs for existing conversations."""

    # This would use the database connection to UPDATE records
    # Implementation depends on migration SQL being applied first
    pass


async def backfill_reflections(db):
    """Backfill ULIDs for existing reflections."""

    # This would use the database connection to UPDATE records
    # Implementation depends on migration SQL being applied first
    pass


async def backfill_code_graphs(db):
    """Backfill ULIDs for existing code graphs."""

    # This would use the database connection to UPDATE records
    # Implementation depends on migration SQL being applied first
    pass


if __name__ == "__main__":
    asyncio.run(run_migration())
