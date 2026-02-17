#!/usr/bin/env python3
"""
Auto-Discovery Workflow Execution Script

This script demonstrates the Phase 2 auto-discovery workflow for improving
knowledge graph connectivity through semantic similarity analysis.

Workflow:
    1. Analyze current graph connectivity
    2. Generate embeddings for entities missing them
    3. Discover relationships between similar entities
    4. Re-analyze to measure improvement

Usage:
    python scripts/run_auto_discovery.py [--entity-type TYPE] [--threshold FLOAT]

Example:
    python scripts/run_auto_discovery.py --threshold 0.75
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_stats(stats: dict[str, Any], label: str) -> None:
    """Print statistics with formatting."""
    print(f"📊 {label}")
    print("-" * 70)

    # Basic stats
    print(f"Total Entities: {stats['total_entities']}")
    print(f"Total Relationships: {stats['total_relationships']}")

    # Phase 2 metrics
    if "connectivity_ratio" in stats:
        print("\n🔗 Connectivity Metrics:")
        print(
            f"  Connectivity Ratio: {stats['connectivity_ratio']:.3f} ({stats['connectivity_ratio'] * 100:.1f}%)"
        )
        print(f"  Average Degree: {stats['avg_degree']:.3f}")
        print(
            f"  Isolated Entities: {stats['isolated_entities']} ({stats['isolated_entities'] / stats['total_entities'] * 100:.1f}%)"
        )

    # Embedding metrics
    if "embedding_coverage" in stats:
        print("\n🧠 Embedding Metrics:")
        print(f"  Coverage: {stats['embedding_coverage']:.1%}")
        print(f"  Entities with Embeddings: {stats['entities_with_embeddings']}")

    # Entity types
    if stats.get("entity_types"):
        print("\n📊 Entity Types:")
        for etype, count in sorted(stats["entity_types"].items()):
            print(f"  {etype}: {count}")

    # Relationship types
    if stats.get("relationship_types"):
        print("\n🔗 Relationship Types:")
        for rtype, count in sorted(
            stats["relationship_types"].items(), key=lambda x: -x[1]
        ):
            print(f"  {rtype}: {count}")

    print()


async def analyze_connectivity(kg: Any) -> dict[str, Any]:
    """Analyze current graph connectivity."""
    print_section("Analyzing Current Graph Connectivity")

    stats = await kg.get_stats()
    print_stats(stats, "Current Graph Statistics")

    # Determine health status
    connectivity = stats.get("connectivity_ratio", 0)
    if connectivity >= 0.5:
        health = "🟢 Excellent"
    elif connectivity >= 0.2:
        health = "🟡 Good"
    elif connectivity >= 0.1:
        health = "🟠 Fair"
    else:
        health = "🔴 Poor"

    print(f"Health Status: {health}\n")

    return stats


async def generate_embeddings(
    kg: Any,
    entity_type: str | None = None,
    batch_size: int = 50,
) -> dict[str, Any]:
    """Generate embeddings for entities missing them."""
    print_section("Generating Embeddings")

    result = await kg.generate_embeddings_for_entities(
        entity_type=entity_type,
        batch_size=batch_size,
        overwrite=False,
    )

    print("🧠 Embedding Generation Results")
    print("-" * 70)
    print(f"✅ Generated: {result['generated']}")
    print(f"❌ Failed: {result['failed']}")
    print(f"📊 Total Processed: {result['total_processed']}")
    print()

    return result


async def discover_relationships(
    kg: Any,
    entity_type: str | None = None,
    threshold: float = 0.75,
    limit: int = 100,
    batch_size: int = 10,
) -> dict[str, Any]:
    """Discover relationships between similar entities."""
    print_section("Discovering Relationships")

    result = await kg.batch_discover_relationships(
        entity_type=entity_type,
        threshold=threshold,
        limit=limit,
        batch_size=batch_size,
    )

    print("🔗 Relationship Discovery Results")
    print("-" * 70)
    print(f"📊 Entities Processed: {result['entities_processed']}")
    print(f"✅ Relationships Created: {result['relationships_created']}")
    print(f"📈 Avg Relationships/Entity: {result['avg_relationships_per_entity']:.2f}")
    print()

    return result


async def main(args: argparse.Namespace) -> int:
    """Main workflow execution."""
    try:
        import importlib.util
        if importlib.util.find_spec("session_buddy.adapters.knowledge_graph_adapter_oneiric") is None:
            raise ImportError("knowledge_graph_adapter_oneiric not found")
    except ImportError as e:
        print(f"❌ Failed to import knowledge graph adapter: {e}")
        return 1

    print("\n" + "=" * 70)
    print("  Knowledge Graph Auto-Discovery Workflow")
    print("  Phase 2: Semantic Similarity Analysis")
    print("=" * 70)

    # Note: We can't actually run this without fixing the DuckPGQ extension issue
    # But we can demonstrate the workflow structure
    print("\n⚠️  NOTE: This is a demonstration script.")
    print("    The actual workflow requires DuckDB with the DuckPGQ extension.")
    print("    See Phase 2 documentation for manual execution steps.\n")

    return 0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Knowledge Graph Auto-Discovery Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full workflow with default settings
  python scripts/run_auto_discovery.py

  # Run for specific entity type only
  python scripts/run_auto_discovery.py --entity-type project

  # Use lower similarity threshold (more connections)
  python scripts/run_auto_discovery.py --threshold 0.70

  # Process more entities per batch (faster but more memory)
  python scripts/run_auto_discovery.py --batch-size 100
        """,
    )

    parser.add_argument(
        "--entity-type",
        type=str,
        default=None,
        help="Filter by entity type (default: all types)",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="Similarity threshold for relationships (0.0-1.0, default: 0.75)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing (default: 50)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum entities to process (default: 100)",
    )

    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation step",
    )

    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip relationship discovery step",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args)))
