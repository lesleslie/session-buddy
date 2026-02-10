#!/usr/bin/env python3
"""Comprehensive database status and data validity checker.

Tests all Session Buddy databases:
1. Reflection database (conversations, reflections, embeddings)
2. Knowledge graph database
3. Crackerjack integration database
4. Interruption manager database
5. Shared analytics database
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    print("❌ DuckDB not available")

try:
    import sqlite3

    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False
    print("❌ SQLite not available")


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_status(name: str, status: bool, details: str = "") -> None:
    """Print a status line."""
    symbol = "✅" if status else "❌"
    print(f"{symbol} {name:<40} {details}")


def test_reflection_database() -> dict[str, Any]:
    """Test the main reflection database."""
    print_section("Reflection Database (~/.claude/data/reflection.duckdb)")

    if not DUCKDB_AVAILABLE:
        print_status("Reflection DB", False, "DuckDB not available")
        return {"status": "unavailable"}

    db_path = Path.home() / ".claude" / "data" / "reflection.duckdb"

    if not db_path.exists():
        print_status("Database file", False, "Not found")
        return {"status": "missing"}

    print_status("Database file", True, f"{db_path.stat().st_size / 1024 / 1024:.1f} MB")

    results: dict[str, Any] = {"status": "ok", "tables": {}, "data_quality": {}}

    try:
        conn = duckdb.connect(str(db_path))

        # Test core tables
        tables = [
            "conversations",
            "reflections",
            "reflection_tags",
            "project_groups",
            "project_dependencies",
            "session_links",
            "access_log_v2",
            "code_graphs",
        ]

        for table in tables:
            try:
                result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                count = result[0] if result else 0
                results["tables"][table] = count
                print_status(f"Table: {table}", True, f"{count:,} rows")

                # Check for data quality issues
                if count > 0:
                    # Check for NULL content in conversations/reflections
                    if table in ["conversations", "reflections"]:
                        null_content = conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE content IS NULL OR content = ''"
                        ).fetchone()[0]
                        if null_content > 0:
                            results["data_quality"][f"{table}_null_content"] = null_content
                            print_status(
                                f"  ⚠️  NULL/empty content", False, f"{null_content:,} rows"
                            )

                    # Check for embeddings
                    if table in ["conversations", "reflections"]:
                        has_embedding = conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE embedding IS NOT NULL"
                        ).fetchone()[0]
                        embedding_pct = (has_embedding / count * 100) if count > 0 else 0
                        results["data_quality"][f"{table}_embeddings"] = {
                            "count": has_embedding,
                            "percentage": embedding_pct,
                        }
                        print_status(
                            f"  📊 Embeddings",
                            embedding_pct > 50,
                            f"{has_embedding:,} ({embedding_pct:.1f}%)",
                        )

                    # Check recent activity
                    if table in ["conversations", "reflections"]:
                        recent = conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE timestamp > NOW() - INTERVAL '7 days'"
                        ).fetchone()[0]
                        results["data_quality"][f"{table}_recent"] = recent
                        print_status(
                            f"  🕐 Recent (7d)", recent > 0, f"{recent:,} new"
                        )

            except Exception as e:
                results["tables"][table] = f"Error: {e}"
                print_status(f"Table: {table}", False, str(e)[:50])

        # Test schema integrity
        print("\n📋 Schema Validation:")

        # Check for required columns
        conv_columns = conn.execute("DESCRIBE conversations").fetchall()
        conv_col_names = {col[0] for col in conv_columns}
        required_conv = {"id", "content", "embedding", "project", "timestamp"}
        missing_conv = required_conv - conv_col_names
        print_status(
            "Conversations schema", len(missing_conv) == 0, f"Missing: {missing_conv}"
        )

        refl_columns = conn.execute("DESCRIBE reflections").fetchall()
        refl_col_names = {col[0] for col in refl_columns}
        required_refl = {"id", "content", "embedding", "project", "tags", "timestamp"}
        missing_refl = required_refl - refl_col_names
        print_status(
            "Reflections schema", len(missing_refl) == 0, f"Missing: {missing_refl}"
        )

        # Check for orphaned records
        print("\n🔗 Data Integrity:")

        # Check for orphaned reflection_tags
        orphaned_tags = conn.execute(
            """
            SELECT COUNT(*) FROM reflection_tags rt
            LEFT JOIN reflections r ON rt.reflection_id = r.id
            WHERE r.id IS NULL
        """
        ).fetchone()[0]
        print_status("Orphaned tags", orphaned_tags == 0, f"{orphaned_tags} orphaned")

        conn.close()

    except Exception as e:
        results["status"] = f"Error: {e}"
        print_status("Database connection", False, str(e)[:60])

    return results


def test_knowledge_graph_database() -> dict[str, Any]:
    """Test the knowledge graph database."""
    print_section("Knowledge Graph Database (~/.claude/data/knowledge_graph.duckdb)")

    if not DUCKDB_AVAILABLE:
        print_status("Knowledge Graph DB", False, "DuckDB not available")
        return {"status": "unavailable"}

    db_path = Path.home() / ".claude" / "data" / "knowledge_graph.duckdb"

    if not db_path.exists():
        print_status("Database file", False, "Not found")
        return {"status": "missing"}

    print_status("Database file", True, f"{db_path.stat().st_size / 1024 / 1024:.1f} MB")

    results: dict[str, Any] = {"status": "ok", "tables": {}, "data_quality": {}}

    try:
        conn = duckdb.connect(str(db_path))

        # List all tables
        tables_query = conn.execute("SHOW TABLES").fetchall()
        tables = [row[0] for row in tables_query]

        print(f"📊 Found {len(tables)} tables: {', '.join(tables)}")

        for table in tables:
            try:
                result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                count = result[0] if result else 0
                results["tables"][table] = count
                print_status(f"Table: {table}", True, f"{count:,} rows")

                # Check for embeddings in kg_entities
                if table == "kg_entities" and count > 0:
                    has_embedding = conn.execute(
                        "SELECT COUNT(*) FROM kg_entities WHERE embedding IS NOT NULL"
                    ).fetchone()[0]
                    embedding_pct = (has_embedding / count * 100) if count > 0 else 0
                    print_status(
                        f"  📊 Entity embeddings",
                        embedding_pct > 50,
                        f"{has_embedding:,} ({embedding_pct:.1f}%)",
                    )

            except Exception as e:
                results["tables"][table] = f"Error: {e}"
                print_status(f"Table: {table}", False, str(e)[:50])

        # Test graph structure
        if "kg_entities" in tables and "kg_relations" in tables:
            print("\n🔗 Graph Structure:")

            entity_count = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
            relation_count = conn.execute("SELECT COUNT(*) FROM kg_relations").fetchone()[0]

            print_status("Entities", entity_count > 0, f"{entity_count:,} entities")
            print_status("Relations", relation_count > 0, f"{relation_count:,} relations")

            if entity_count > 0:
                avg_connections = relation_count / entity_count if entity_count > 0 else 0
                print_status(
                    "Avg connections",
                    avg_connections > 0,
                    f"{avg_connections:.2f} per entity",
                )

            # Check for orphaned relations
            orphaned_relations = conn.execute(
                """
                SELECT COUNT(*) FROM kg_relations kr
                LEFT JOIN kg_entities e1 ON kr.from_entity = e1.id
                LEFT JOIN kg_entities e2 ON kr.to_entity = e2.id
                WHERE e1.id IS NULL OR e2.id IS NULL
            """
            ).fetchone()[0]
            print_status(
                "Orphaned relations", orphaned_relations == 0, f"{orphaned_relations} orphaned"
            )

        conn.close()

    except Exception as e:
        results["status"] = f"Error: {e}"
        print_status("Database connection", False, str(e)[:60])

    return results


def test_crackerjack_database() -> dict[str, Any]:
    """Test the Crackerjack integration database."""
    print_section("Crackerjack Integration Database (~/.claude/data/crackerjack_integration.db)")

    if not SQLITE_AVAILABLE:
        print_status("Crackerjack DB", False, "SQLite not available")
        return {"status": "unavailable"}

    db_path = Path.home() / ".claude" / "data" / "crackerjack_integration.db"

    if not db_path.exists():
        print_status("Database file", False, "Not found")
        return {"status": "missing"}

    print_status("Database file", True, f"{db_path.stat().st_size / 1024 / 1024:.1f} MB")

    results: dict[str, Any] = {"status": "ok", "tables": {}}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        print(f"📊 Found {len(tables)} tables: {', '.join(tables)}")

        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                results["tables"][table] = count
                print_status(f"Table: {table}", True, f"{count:,} rows")

                # Check recent data
                if "timestamp" in table or "created_at" in table or "date" in table:
                    try:
                        cursor.execute(
                            f"SELECT COUNT(*) FROM [{table}] WHERE datetime(timestamp) > datetime('now', '-7 days')"
                        )
                        recent = cursor.fetchone()[0]
                        if recent > 0:
                            print(f"     🕐 Recent (7d): {recent:,} new")
                    except Exception:
                        pass  # Table might not have timestamp column

            except Exception as e:
                results["tables"][table] = f"Error: {e}"
                print_status(f"Table: {table}", False, str(e)[:50])

        conn.close()

    except Exception as e:
        results["status"] = f"Error: {e}"
        print_status("Database connection", False, str(e)[:60])

    return results


def test_interruption_database() -> dict[str, Any]:
    """Test the interruption manager database."""
    print_section("Interruption Manager Database (~/.claude/data/interruption_manager.db)")

    if not SQLITE_AVAILABLE:
        print_status("Interruption DB", False, "SQLite not available")
        return {"status": "unavailable"}

    db_path = Path.home() / ".claude" / "data" / "interruption_manager.db"

    if not db_path.exists():
        print_status("Database file", False, "Not found")
        return {"status": "missing"}

    print_status("Database file", True, f"{db_path.stat().st_size / 1024:.1f} KB")

    results: dict[str, Any] = {"status": "ok", "tables": {}}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        print(f"📊 Found {len(tables)} tables: {', '.join(tables)}")

        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                results["tables"][table] = count
                print_status(f"Table: {table}", True, f"{count:,} rows")

            except Exception as e:
                results["tables"][table] = f"Error: {e}"
                print_status(f"Table: {table}", False, str(e)[:50])

        conn.close()

    except Exception as e:
        results["status"] = f"Error: {e}"
        print_status("Database connection", False, str(e)[:60])

    return results


# Shared analytics database removed - was a phantom database with no production code references
# See investigation report for details
def test_embedding_system() -> dict[str, Any]:
    """Test the embedding system functionality."""
    print_section("Embedding System Test")

    results: dict[str, Any] = {"status": "unknown", "provider": None}

    try:
        from session_buddy.reflection.embeddings import (
            initialize_embedding_system,
        )
        from session_buddy.reflection.database import ONNX_AVAILABLE

        if ONNX_AVAILABLE:
            print_status("ONNX Runtime", True, "Available")

            try:
                session = initialize_embedding_system()
                if session:
                    print_status("Embedding model", True, "Loaded successfully")
                    results["status"] = "ok"
                    results["provider"] = "onnx-runtime"

                    # Test generating an embedding
                    import asyncio

                    async def test_embedding():
                        from session_buddy.reflection.embeddings import generate_embedding

                        test_text = "This is a test of the embedding system."
                        embedding = await generate_embedding(test_text, session, None)

                        if embedding and len(embedding) == 384:
                            return True, len(embedding)
                        return False, None

                    has_embedding, dim = asyncio.run(test_embedding())
                    if has_embedding:
                        print_status("Embedding generation", True, f"{dim} dimensions")
                        results["embedding_dimension"] = dim
                    else:
                        print_status("Embedding generation", False, "Failed")
                else:
                    print_status("Embedding model", False, "Failed to load")
                    results["status"] = "model_load_failed"
            except Exception as e:
                print_status("Embedding model", False, f"Error: {e}")
                results["status"] = f"Error: {e}"
        else:
            print_status("ONNX Runtime", False, "Not available")
            results["status"] = "onnx_unavailable"
            results["provider"] = "text-search-only"

    except ImportError as e:
        print_status("Embedding system", False, f"Import error: {e}")
        results["status"] = f"Import error: {e}"

    return results


def generate_summary_report(all_results: dict[str, Any]) -> None:
    """Generate a final summary report."""
    print_section("SUMMARY REPORT")

    total_dbs = 0
    healthy_dbs = 0
    total_rows = 0
    total_tables = 0

    for db_name, db_data in all_results.items():
        if db_name == "embedding_system":
            continue

        total_dbs += 1

        if db_data.get("status") == "ok":
            healthy_dbs += 1

        for table, count in db_data.get("tables", {}).items():
            if isinstance(count, int):
                total_tables += 1
                total_rows += count

    print(f"📊 Overall Database Health:")
    print(f"   Databases: {healthy_dbs}/{total_dbs} healthy")
    print(f"   Total tables: {total_tables}")
    print(f"   Total records: {total_rows:,}")

    # Embedding system status
    embedding_status = all_results.get("embedding_system", {})
    provider = embedding_status.get("provider", "unknown")
    print(f"\n🤖 Embedding System:")
    print(f"   Provider: {provider}")

    # Recommendations
    print(f"\n💡 Recommendations:")

    reflection_db = all_results.get("reflection_database", {})
    if reflection_db.get("status") == "ok":
        tables = reflection_db.get("tables", {})
        conv_count = tables.get("conversations", 0)
        refl_count = tables.get("reflections", 0)

        if conv_count == 0 and refl_count == 0:
            print("   ⚠️  Reflection DB is empty - start storing conversations/reflections")

        data_quality = reflection_db.get("data_quality", {})
        conv_emb = data_quality.get("conversations_embeddings", {})
        refl_emb = data_quality.get("reflections_embeddings", {})

        conv_pct = conv_emb.get("percentage", 0)
        refl_pct = refl_emb.get("percentage", 0)

        if conv_pct < 50 and conv_count > 0:
            print("   ⚠️  Low embedding coverage on conversations - check ONNX setup")
        if refl_pct < 50 and refl_count > 0:
            print("   ⚠️  Low embedding coverage on reflections - check ONNX setup")

    kg_db = all_results.get("knowledge_graph_database", {})
    if kg_db.get("status") == "ok":
        tables = kg_db.get("tables", {})
        entity_count = tables.get("kg_entities", 0)
        relation_count = tables.get("kg_relations", 0)

        if entity_count == 0:
            print("   ℹ️  Knowledge graph is empty - entities will be created automatically")

    # Export JSON report
    report_path = Path.home() / ".claude" / "data" / "database_status_report.json"
    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n📄 Full report saved to: {report_path}")


def main() -> int:
    """Run all database tests."""
    print("\n🔍 Session Buddy Database Status Checker")
    print("=" * 70)

    all_results: dict[str, Any] = {}

    # Test all databases
    all_results["reflection_database"] = test_reflection_database()
    all_results["knowledge_graph_database"] = test_knowledge_graph_database()
    all_results["crackerjack_database"] = test_crackerjack_database()
    all_results["interruption_database"] = test_interruption_database()
    all_results["embedding_system"] = test_embedding_system()

    # Generate summary
    generate_summary_report(all_results)

    print("\n" + "=" * 70)
    print("✅ Database status check complete!")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
