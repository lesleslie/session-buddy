#!/usr/bin/env python3
"""Quick fixes for database issues found during status check.

Run this script to fix:
1. Missing embedding system symbolic link
2. Missing database tables (access_log_v2, code_graphs)
3. Missing project column in reflections table
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def fix_embedding_symlink() -> bool:
    """Create symbolic link for ONNX model to fix embedding system."""
    print("\n🔧 Fixing Embedding System Symlink...")

    # Find the actual model location
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    xenova_dir = cache_dir / "models--Xenova--all-MiniLM-L6-v2"

    if not xenova_dir.exists():
        print(f"❌ Model directory not found: {xenova_dir}")
        return False

    # Find the snapshot directory
    snapshots = list(xenova_dir.glob("snapshots/*/onnx/model.onnx"))
    if not snapshots:
        print("❌ ONNX model file not found in Xenova directory")
        return False

    model_path = snapshots[0]
    print(f"✅ Found model at: {model_path}")

    # Create symbolic link
    link_path = cache_dir / "model.onnx"

    # Remove existing link if it exists (and is broken)
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
        print("🗑️  Removed existing symlink")

    # Create new symlink
    try:
        os.symlink(model_path, link_path)
        print(f"✅ Created symlink: {link_path} -> {model_path}")
        return True
    except OSError as e:
        print(f"❌ Failed to create symlink: {e}")
        return False


def fix_database_schema() -> bool:
    """Add missing tables and columns to reflection database."""
    print("\n🔧 Fixing Database Schema...")

    try:
        import duckdb

        db_path = Path.home() / ".claude" / "data" / "reflection.duckdb"

        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            return False

        conn = duckdb.connect(str(db_path))

        # Check existing tables
        existing_tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        print(f"📊 Existing tables: {existing_tables}")

        # access_log_v2 was removed by the UUID7 consolidation migration
        # (2026_10_11_uuid7_consolidation/006_drop_vestigial.sql). It is
        # vestigial: superseded by memory_access_log (rebuilt with UUID7 PKs
        # by 007). The previous b-step patch tried to gate the recreate on a
        # __uuid7_migration_done marker, but the marker is only created when
        # the 2026_10_11 bundle runs -- and a fresh DB has no marker yet, so
        # the gate was dormant and the table came back. The semantic fix is
        # simpler: don't recreate it. Period. The migration drops it; the
        # startup script doesn't bring it back. If a downstream consumer
        # still expects access_log_v2, that consumer needs to migrate to
        # memory_access_log too.
        print("⏭️  access_log_v2 intentionally not recreated (vestigial; dropped by 006)")

        if "code_graphs" not in existing_tables:
            print("🔨 Creating code_graphs table...")
            conn.execute(
                """
                CREATE TABLE code_graphs (
                    id VARCHAR PRIMARY KEY,
                    repo_path TEXT NOT NULL,
                    commit_hash TEXT NOT NULL,
                    indexed_at TIMESTAMP NOT NULL,
                    nodes_count INTEGER NOT NULL,
                    graph_data JSON NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    metadata JSON
                )
            """
            )
            print("✅ Created code_graphs table")
        else:
            print("✅ code_graphs table already exists")

        # Check for missing project column in reflections
        print("\n🔨 Checking reflections table schema...")
        refl_columns = conn.execute("DESCRIBE reflections").fetchall()
        refl_col_names = {col[0] for col in refl_columns}

        if "project" not in refl_col_names:
            print("🔨 Adding missing 'project' column to reflections table...")
            conn.execute("ALTER TABLE reflections ADD COLUMN project VARCHAR")
            print("✅ Added project column to reflections table")
        else:
            print("✅ project column already exists in reflections table")

        conn.close()
        return True

    except ImportError:
        print("❌ DuckDB not available")
        return False
    except Exception as e:
        print(f"❌ Schema fix failed: {e}")
        return False


def test_embedding_system() -> bool:
    """Test if embedding system works after fixes."""
    print("\n🧪 Testing Embedding System...")

    try:
        import asyncio

        from session_buddy.reflection.embeddings import (
            initialize_embedding_system,
        )

        async def test():
            session = initialize_embedding_system()
            if session is None:
                print("⚠️  ONNX session not initialized (may be using fallback)")
                return False

            print("✅ ONNX session initialized")

            # Try generating an embedding
            from session_buddy.reflection.embeddings import generate_embedding

            test_embedding = await generate_embedding(
                "Test embedding after fix", session, None
            )

            if test_embedding and len(test_embedding) == 384:
                print(
                    f"✅ Successfully generated {len(test_embedding)}-dimensional embedding"
                )
                return True
            else:
                print("❌ Failed to generate embedding")
                return False

        return asyncio.run(test())

    except Exception as e:
        print(f"❌ Embedding test failed: {e}")
        return False


def main() -> int:
    """Run all fixes."""
    print("=" * 70)
    print("🔧 Session Buddy Database Fixes")
    print("=" * 70)

    results = {
        "embedding_symlink": fix_embedding_symlink(),
        "database_schema": fix_database_schema(),
        "embedding_test": test_embedding_system(),
    }

    print("\n" + "=" * 70)
    print("📋 Fix Results Summary")
    print("=" * 70)

    for name, success in results.items():
        status = "✅" if success else "❌"
        print(
            f"{status} {name.replace('_', ' ').title():.<50} {'Success' if success else 'Failed'}"
        )

    all_success = all(results.values())

    print("\n" + "=" * 70)
    if all_success:
        print("✅ All fixes applied successfully!")
        print("\n💡 Next steps:")
        print(
            "   1. Test storing a reflection: python -m session_buddy.mcp.tools.memory"
        )
        print("   2. Run status check again: python scripts/test_database_status.py")
    else:
        print("⚠️  Some fixes failed. Check output above for details.")
    print("=" * 70)

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
