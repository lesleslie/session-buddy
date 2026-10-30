#!/usr/bin/env python3
"""Quick script to add embedding column to knowledge graph.

This script:
1. Adds the 'embedding' column to kg_entities table
2. Verifies the column was added

Usage:
    python scripts/add_kg_embedding_column.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from session_buddy.paths import data_dir


def main() -> int:
    """Add embedding column to knowledge graph."""
    import duckdb

    db_path = data_dir() / "knowledge_graph.duckdb"

    print(f"📊 Connecting to database: {db_path}")

    conn = duckdb.connect(str(db_path))

    # Check if column exists
    result = conn.execute(
        "SELECT COUNT(*) FROM pragma_table_info('kg_entities') WHERE name = 'embedding'"
    ).fetchone()

    column_exists = result[0] > 0 if result else False

    if column_exists:
        print("✅ Embedding column already exists")
        return 0

    # Add column
    try:
        conn.execute("ALTER TABLE kg_entities ADD COLUMN embedding FLOAT[384]")
        print("✅ Added embedding column to kg_entities")

        # Verify
        result = conn.execute(
            "SELECT COUNT(*) FROM pragma_table_info('kg_entities') WHERE name = 'embedding'"
        ).fetchone()
        if result and result[0] > 0:
            print("✅ Verified: embedding column exists")
        else:
            print("❌ Verification failed")
            return 1

        return 0
    except Exception as e:
        print(f"❌ Failed to add embedding column: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
