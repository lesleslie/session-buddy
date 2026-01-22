#!/usr/bin/env python3
"""Benchmark HNSW indexing performance improvements.

Measures vector search performance with HNSW indexes vs linear scan
to validate the 10x improvement target (from ~50-100ms to <5ms).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from statistics import mean, median, stdev

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings


async def benchmark_hnsw_search(
    num_conversations: int = 1000,
    num_searches: int = 100,
    enable_hnsw: bool = True,
) -> dict[str, float]:
    """Benchmark vector search performance.

    Args:
        num_conversations: Number of conversations to insert for testing
        num_searches: Number of search queries to run
        enable_hnsw: Whether HNSW indexing is enabled

    Returns:
        Dictionary with performance metrics (latency in ms)
    """
    # Create temporary database
    db_path = Path(f"/tmp/benchmark_hnsw_{enable_hnsw}.duckdb")
    if db_path.exists():
        db_path.unlink()

    settings = ReflectionAdapterSettings(
        database_path=db_path,
        collection_name="benchmark",
        enable_hnsw_index=enable_hnsw,
        hnsw_m=16,
        hnsw_ef_construction=200,
        hnsw_ef_search=64,
    )

    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
    await adapter.initialize()

    # Insert test conversations with embeddings
    print(f"Inserting {num_conversations} conversations...")
    topics = [
        "Python programming and development",
        "Machine learning algorithms",
        "Web development with JavaScript",
        "Database management systems",
        "Cloud infrastructure",
        "Software testing methodologies",
        "Agile development practices",
        "Container orchestration",
        "API design principles",
        "DevOps automation",
    ]

    for i in range(num_conversations):
        topic = topics[i % len(topics)]
        await adapter.store_conversation(f"{topic} - Example {i}", {"benchmark": True})

    print(f"Inserted {num_conversations} conversations")

    # Benchmark search performance
    print(f"Running {num_searches} searches...")
    latencies_ms = []

    for i in range(num_searches):
        query = topics[i % len(topics)]

        start = time.perf_counter()
        results = await adapter.search_conversations(query, limit=10, threshold=0.0)
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        latencies_ms.append(latency_ms)

    await adapter.aclose()

    # Cleanup
    if db_path.exists():
        db_path.unlink()

    # Calculate statistics
    return {
        "mean_ms": mean(latencies_ms),
        "median_ms": median(latencies_ms),
        "min_ms": min(latencies_ms),
        "max_ms": max(latencies_ms),
        "stdev_ms": stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0,
        "p95_ms": sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
        if latencies_ms
        else 0.0,
        "p99_ms": sorted(latencies_ms)[int(len(latencies_ms) * 0.99)]
        if latencies_ms
        else 0.0,
    }


async def main() -> None:
    """Run comprehensive HNSW performance benchmarks."""
    print("=" * 70)
    print("HNSW Performance Benchmark")
    print("=" * 70)
    print()

    # Test configurations
    test_configs = [
        {
            "name": "Small Dataset (100 conversations)",
            "num_conversations": 100,
            "num_searches": 50,
        },
        {
            "name": "Medium Dataset (1,000 conversations)",
            "num_conversations": 1000,
            "num_searches": 100,
        },
        {
            "name": "Large Dataset (10,000 conversations)",
            "num_conversations": 10000,
            "num_searches": 100,
        },
    ]

    for config in test_configs:
        print(f"\n{'=' * 70}")
        print(f"Test: {config['name']}")
        print(f"{'=' * 70}")

        # Benchmark WITH HNSW
        print("\n🔍 WITH HNSW Indexing:")
        hnsw_metrics = await benchmark_hnsw_search(
            num_conversations=config["num_conversations"],
            num_searches=config["num_searches"],
            enable_hnsw=True,
        )

        print(f"  Mean latency:   {hnsw_metrics['mean_ms']:.3f} ms")
        print(f"  Median latency: {hnsw_metrics['median_ms']:.3f} ms")
        print(f"  Min latency:    {hnsw_metrics['min_ms']:.3f} ms")
        print(f"  Max latency:    {hnsw_metrics['max_ms']:.3f} ms")
        print(f"  Std deviation:  {hnsw_metrics['stdev_ms']:.3f} ms")
        print(f"  P95 latency:    {hnsw_metrics['p95_ms']:.3f} ms")
        print(f"  P99 latency:    {hnsw_metrics['p99_ms']:.3f} ms")

        # Benchmark WITHOUT HNSW (fallback)
        print("\n🔍 WITHOUT HNSW (Linear Scan):")
        no_hnsw_metrics = await benchmark_hnsw_search(
            num_conversations=config["num_conversations"],
            num_searches=config["num_searches"],
            enable_hnsw=False,
        )

        print(f"  Mean latency:   {no_hnsw_metrics['mean_ms']:.3f} ms")
        print(f"  Median latency: {no_hnsw_metrics['median_ms']:.3f} ms")
        print(f"  Min latency:    {no_hnsw_metrics['min_ms']:.3f} ms")
        print(f"  Max latency:    {no_hnsw_metrics['max_ms']:.3f} ms")
        print(f"  Std deviation:  {no_hnsw_metrics['stdev_ms']:.3f} ms")
        print(f"  P95 latency:    {no_hnsw_metrics['p95_ms']:.3f} ms")
        print(f"  P99 latency:    {no_hnsw_metrics['p99_ms']:.3f} ms")

        # Calculate improvement
        improvement = no_hnsw_metrics["mean_ms"] / hnsw_metrics["mean_ms"]
        print(f"\n📊 Performance Improvement: {improvement:.2f}x faster")
        print(f"   Target: <5ms, Actual: {hnsw_metrics['mean_ms']:.3f} ms")

        if hnsw_metrics["mean_ms"] < 5.0:
            print("   ✅ MEETS <5ms target!")
        else:
            print("   ⚠️  Above <5ms target")

    print("\n" + "=" * 70)
    print("Benchmark Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
