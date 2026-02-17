#!/usr/bin/env python3
"""Simple Phase 2 Activation Script (DuckDB Native).

This script activates Phase 2 auto-discovery using standard DuckDB operations
without requiring the DuckPGQ extension.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb

from session_buddy.reflection.database import ReflectionDatabase


def get_db_path() -> str:
    """Get knowledge graph database path."""
    return str(Path.home() / ".claude" / "data" / "knowledge_graph.duckdb")


def print_section(title: str) -> None:
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def generate_embeddings_sync() -> dict[str, int]:
    """Generate embeddings for entities using reflection system.

    This is a synchronous version that works with standard DuckDB.
    """
    print_section("Step 2: Generating Embeddings")

    db_path = get_db_path()
    conn = duckdb.connect(db_path)

    # Get entities without embeddings
    result = conn.execute(
        """
        SELECT id, name, entity_type
        FROM kg_entities
        WHERE embedding IS NULL
        LIMIT 100
        """
    ).fetchall()

    entities_without = len(result)
    print(f"Entities needing embeddings: {entities_without}")

    if entities_without == 0:
        conn.close()
        return {"generated": 0, "skipped": 0}

    # Initialize reflection database for embeddings
    refl_db = ReflectionDatabase()

    try:
        asyncio.run(refl_db.initialize())
    except RuntimeError as e:
        print(f"⚠️  Could not initialize embedding system: {e}")
        print(
            "   Skipping embedding generation (can discover relationships without them)"
        )
        conn.close()
        return {"generated": 0, "skipped": entities_without}

    generated = 0
    skipped = 0

    for entity_id, name, entity_type in result:
        try:
            # Generate embedding using reflection system
            embedding = refl_db.onnx_session
            if embedding is None:
                skipped += 1
                continue

            # Generate simple embedding from name + type
            text = f"{name} {entity_type}"
            from session_buddy.reflection.embeddings import generate_embedding

            embedding_vector = asyncio.get_event_loop().run_until_complete(
                generate_embedding(text, refl_db.onnx_session, refl_db.tokenizer)
            )

            if embedding_vector is None:
                skipped += 1
                continue

            # Convert to DuckDB format
            embedding_str = f"[{','.join(str(x) for x in embedding_vector)}]"

            # Update entity
            conn.execute(
                """
                UPDATE kg_entities
                SET embedding = CAST($1 AS FLOAT[384])
                WHERE id = $2
                """,
                [embedding_str, entity_id],
            )
            generated += 1

            if generated % 10 == 0:
                print(
                    f"  Progress: {generated}/{entities_without} embeddings generated"
                )

        except Exception as e:
            print(f"  ⚠️  Failed to generate embedding for {name}: {e}")
            skipped += 1
            continue

    conn.close()
    refl_db.close()

    print(f"\n✅ Generated: {generated}")
    print(f"⚠️  Skipped: {skipped}")

    return {"generated": generated, "skipped": skipped}


def discover_relationships_sync(threshold: float = 0.75) -> dict[str, int]:
    """Discover relationships between similar entities.

    This uses DuckDB's cosine similarity on embeddings.
    """
    print_section("Step 3: Discovering Relationships")

    db_path = get_db_path()
    conn = duckdb.connect(db_path)

    # Get stats
    total_entities = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    entities_with_embeddings = conn.execute(
        "SELECT COUNT(*) FROM kg_entities WHERE embedding IS NOT NULL"
    ).fetchone()[0]

    print(f"Total entities: {total_entities}")
    print(f"Entities with embeddings: {entities_with_embeddings}")

    if entities_with_embeddings < 2:
        print("⚠️  Need at least 2 entities with embeddings to discover relationships")
        conn.close()
        return {"created": 0, "skipped": 0}

    # Discover relationships using cosine similarity
    # For each entity with embedding, find similar entities
    result = conn.execute(
        """
        SELECT
            e1.id as from_id,
            e1.name as from_name,
            e1.entity_type as from_type,
            e2.id as to_id,
            e2.name as to_name,
            e2.entity_type as to_type,
            array_cosine_similarity(e1.embedding, e2.embedding) as similarity
        FROM kg_entities e1
        CROSS JOIN kg_entities e2
        WHERE e1.id != e2.id
          AND e1.embedding IS NOT NULL
          AND e2.embedding IS NOT NULL
          AND array_cosine_similarity(e1.embedding, e2.embedding) > $1
        ORDER BY similarity DESC
        LIMIT 500
        """,
        [threshold],
    ).fetchall()

    print(f"Found {len(result)} potential relationships above threshold {threshold}")

    # Create relationships that don't already exist
    created = 0
    skipped = 0

    for from_id, from_name, from_type, to_id, to_name, to_type, similarity in result:
        # Check if relationship already exists
        existing = conn.execute(
            """
            SELECT COUNT(*) FROM kg_relationships
            WHERE from_entity = $1 AND to_entity = $2
            """,
            [from_id, to_id],
        ).fetchone()[0]

        if existing > 0:
            skipped += 1
            continue

        # Infer relationship type
        relation_type = infer_relation_type(from_type, to_type)

        # Create relationship
        try:
            import uuid

            relation_id = str(uuid.uuid4())

            conn.execute(
                """
                INSERT INTO kg_relationships (id, from_entity, to_entity, relation_type, properties, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                [
                    relation_id,
                    from_id,
                    to_id,
                    relation_type,
                    f'{{"similarity": {similarity:.3f}, "auto_discovered": true}}',
                ],
            )
            created += 1

            if created % 10 == 0:
                print(f"  Progress: {created} relationships created")

        except Exception as e:
            print(f"  ⚠️  Failed to create relationship: {e}")
            skipped += 1
            continue

    conn.close()

    print(f"\n✅ Created: {created} relationships")
    print(f"⚠️  Skipped: {skipped} (already exist)")

    return {"created": created, "skipped": skipped}


def infer_relation_type(from_type: str, to_type: str) -> str:
    """Infer relationship type based on entity types."""
    # Simple heuristics
    if from_type == to_type:
        return "related_to"
    elif from_type == "project" and to_type == "library":
        return "uses"
    elif from_type == "project" and to_type == "service":
        return "connects_to"
    elif from_type == "test" and to_type == "project":
        return "tests"
    elif from_type == "library" and to_type == "project":
        return "used_by"
    else:
        return "related_to"


def analyze_connectivity() -> dict[str, Any]:
    """Analyze current graph connectivity."""
    print_section("Step 1: Current Connectivity Analysis")

    db_path = get_db_path()
    conn = duckdb.connect(db_path)

    # Get stats
    entity_count = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    relationship_count = conn.execute(
        "SELECT COUNT(*) FROM kg_relationships"
    ).fetchone()[0]
    entities_with_embeddings = conn.execute(
        "SELECT COUNT(*) FROM kg_entities WHERE embedding IS NOT NULL"
    ).fetchone()[0]

    connectivity = relationship_count / entity_count if entity_count > 0 else 0
    embedding_coverage = (
        entities_with_embeddings / entity_count if entity_count > 0 else 0
    )

    # Isolated entities
    isolated = conn.execute(
        """
        SELECT COUNT(*) FROM kg_entities e
        WHERE NOT EXISTS (
            SELECT 1 FROM kg_relationships r
            WHERE r.from_entity = e.id OR r.to_entity = e.id
        )
        """
    ).fetchone()[0]

    # Entity types
    entity_types = dict(
        conn.execute(
            "SELECT entity_type, COUNT(*) FROM kg_entities GROUP BY entity_type"
        ).fetchall()
    )

    # Relationship types
    relationship_types = dict(
        conn.execute(
            "SELECT relation_type, COUNT(*) FROM kg_relationships GROUP BY relation_type"
        ).fetchall()
    )

    conn.close()

    # Print stats
    print("\n📊 Current State:")
    print(f"  Entities: {entity_count}")
    print(f"  Relationships: {relationship_count}")
    print(f"  Connectivity: {connectivity:.3f} ({connectivity * 100:.1f}%)")
    print(f"  Embedding Coverage: {embedding_coverage:.1%}")
    print(f"  Isolated Entities: {isolated} ({isolated / entity_count * 100:.1f}%)")

    # Health status
    if connectivity >= 0.5:
        health = "🟢 Excellent"
    elif connectivity >= 0.2:
        health = "🟡 Good"
    elif connectivity >= 0.1:
        health = "🟠 Fair"
    else:
        health = "🔴 Poor"

    print(f"\n  Health Status: {health}")

    print("\n📊 Entity Types:")
    for etype, count in sorted(entity_types.items()):
        print(f"  {etype}: {count}")

    print("\n🔗 Relationship Types:")
    for rtype, count in sorted(relationship_types.items(), key=lambda x: -x[1]):
        print(f"  {rtype}: {count}")

    return {
        "total_entities": entity_count,
        "total_relationships": relationship_count,
        "connectivity_ratio": connectivity,
        "embedding_coverage": embedding_coverage,
        "isolated_entities": isolated,
        "entity_types": entity_types,
        "relationship_types": relationship_types,
    }


def main():
    """Run Phase 2 activation workflow."""
    print("\n🚀 Phase 2 Auto-Discovery Activation")
    print("=" * 70)
    print("   Using DuckDB Native (No DuckPGQ Required)")
    print("=" * 70)

    # Step 1: Analyze current state
    stats_before = analyze_connectivity()

    # Step 2: Generate embeddings
    generate_embeddings_sync()

    # Step 3: Discover relationships
    discover_relationships_sync(threshold=0.75)

    # Step 4: Analyze final state
    print_section("Step 4: Final State Analysis")

    stats_after = analyze_connectivity()

    # Calculate improvement
    relationships_before = stats_before["total_relationships"]
    relationships_after = stats_after["total_relationships"]
    relationships_created = relationships_after - relationships_before

    connectivity_before = stats_before["connectivity_ratio"]
    connectivity_after = stats_after["connectivity_ratio"]

    if connectivity_before > 0:
        improvement_x = connectivity_after / connectivity_before
        improvement_pct = (improvement_x - 1) * 100
    else:
        improvement_x = float("inf") if relationships_after > 0 else 1
        improvement_pct = float("inf") if relationships_after > 0 else 0

    print("\n📈 Improvement Summary:")
    print(
        f"  Relationships: {relationships_before} → {relationships_after} (+{relationships_created})"
    )
    print(f"  Connectivity: {connectivity_before:.3f} → {connectivity_after:.3f}")
    if improvement_x != float("inf"):
        print(f"  Improvement: {improvement_x:.1f}x ({improvement_pct:.1f}% increase)")
    else:
        print(f"  Improvement: From 0 to {connectivity_after:.3f} (new relationships!)")

    print_section("✅ Phase 2 Activation Complete")

    # Recommendations
    if connectivity_after < 0.2:
        print("\n💡 Recommendations:")
        print("  1. Lower threshold to discover more relationships:")
        print("     python scripts/activate_phase2_simple.py --threshold 0.70")
        print("  2. Run again to process more entities")
        print("  3. Check embedding coverage - generate more embeddings if needed")
    else:
        print("\n✅ Great! Connectivity target achieved!")


if __name__ == "__main__":
    main()
