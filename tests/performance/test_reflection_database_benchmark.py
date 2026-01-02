#!/usr/bin/env python3
"""Performance benchmarking tests for ReflectionDatabase operations.

Uses pytest-benchmark to measure and track performance of critical database operations
over time to detect regressions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from session_buddy.reflection_tools import ReflectionDatabase


class TestReflectionDatabasePerformance:
    """Performance benchmarking tests for ReflectionDatabase operations."""

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_store_reflection_performance(self, benchmark):
        """Benchmark reflection storage performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Benchmark storing 100 reflections
                def store_reflections():
                    for i in range(100):
                        content = f"Performance test reflection {i}"
                        db.store_reflection(
                            content, ["performance"], "benchmark-project"
                        )

                benchmark(store_reflections)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_bulk_store_performance(self, benchmark):
        """Benchmark bulk reflection storage performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Benchmark storing 1000 reflections
                def bulk_store():
                    for i in range(1000):
                        content = f"Bulk performance test reflection {i}"
                        db.store_reflection(content, ["bulk"], "benchmark-project")

                benchmark(bulk_store)

            finally:
                db.close()

    @pytest.mark.benchmark(group="search-operations")
    @pytest.mark.asyncio
    async def test_search_performance(self, benchmark):
        """Benchmark search performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Populate database with test data
                for i in range(100):
                    content = f"Search performance test reflection {i}"
                    await db.store_reflection(content, ["search"], "benchmark-project")

                # Benchmark search operation
                def search_operation():
                    db.search_reflections("performance", 10, "benchmark-project")

                benchmark(search_operation)

            finally:
                db.close()

    @pytest.mark.benchmark(group="search-operations")
    @pytest.mark.asyncio
    async def test_complex_search_performance(self, benchmark):
        """Benchmark complex search with tags and filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Populate database with diverse test data
                for i in range(200):
                    content = f"Complex search performance test reflection {i}"
                    tags = ["performance", f"tag_{i % 10}"]
                    await db.store_reflection(content, tags, "benchmark-project")

                # Benchmark complex search operation
                def complex_search():
                    db.search_reflections(
                        "performance",
                        20,
                        "benchmark-project",
                        tags=["performance", "tag_5"],
                    )

                benchmark(complex_search)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_get_stats_performance(self, benchmark):
        """Benchmark statistics retrieval performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Populate database with test data
                for i in range(500):
                    content = f"Stats performance test reflection {i}"
                    await db.store_reflection(content, ["stats"], "benchmark-project")

                # Benchmark stats retrieval
                def get_stats():
                    db.get_stats()

                benchmark(get_stats)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_update_reflection_performance(self, benchmark):
        """Benchmark reflection update performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store a reflection to update
                reflection_id = await db.store_reflection(
                    "Original content", ["original"], "benchmark-project"
                )

                # Benchmark update operation
                def update_reflection():
                    db.update_reflection(reflection_id, "Updated content", ["updated"])

                benchmark(update_reflection)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_delete_reflection_performance(self, benchmark):
        """Benchmark reflection deletion performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store a reflection to delete
                reflection_id = await db.store_reflection(
                    "Content to delete", ["delete"], "benchmark-project"
                )

                # Benchmark delete operation
                def delete_reflection():
                    db.delete_reflection(reflection_id)

                benchmark(delete_reflection)

            finally:
                db.close()

    @pytest.mark.benchmark(group="concurrent-operations")
    @pytest.mark.asyncio
    async def test_concurrent_store_performance(self, benchmark):
        """Benchmark concurrent reflection storage performance."""
        import asyncio

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:

                async def store_reflection(i):
                    content = f"Concurrent performance test reflection {i}"
                    await db.store_reflection(
                        content, ["concurrent"], "benchmark-project"
                    )

                # Benchmark concurrent operations
                async def concurrent_store():
                    tasks = [store_reflection(i) for i in range(50)]
                    await asyncio.gather(*tasks)

                benchmark(concurrent_store)

            finally:
                db.close()

    @pytest.mark.benchmark(group="bulk-operations")
    @pytest.mark.asyncio
    async def test_large_dataset_search_performance(self, benchmark):
        """Benchmark search performance on large datasets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Populate with large dataset
                for i in range(1000):
                    content = f"Large dataset performance test reflection {i}"
                    await db.store_reflection(content, ["large"], "benchmark-project")

                # Benchmark search on large dataset
                def large_search():
                    db.search_reflections("performance", 50, "benchmark-project")

                benchmark(large_search)

            finally:
                db.close()

    @pytest.mark.benchmark(group="memory-usage")
    @pytest.mark.asyncio
    async def test_memory_efficiency(self, benchmark):
        """Benchmark memory efficiency of database operations."""
        import gc

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Force garbage collection before benchmark
                gc.collect()

                # Benchmark memory usage during bulk operations
                def memory_intensive_operations():
                    for i in range(200):
                        content = f"Memory efficiency test reflection {i}"
                        db.store_reflection(content, ["memory"], "benchmark-project")

                    # Perform searches to test memory usage
                    for j in range(10):
                        db.search_reflections("memory", 20, "benchmark-project")

                benchmark(memory_intensive_operations)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_mixed_operations_performance(self, benchmark):
        """Benchmark mixed database operations performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Benchmark mixed operations
                def mixed_operations():
                    # Store operations
                    for i in range(50):
                        content = f"Mixed operations test reflection {i}"
                        db.store_reflection(content, ["mixed"], "benchmark-project")

                    # Search operations
                    for j in range(10):
                        db.search_reflections("mixed", 10, "benchmark-project")

                    # Stats operations
                    for k in range(5):
                        db.get_stats()

                benchmark(mixed_operations)

            finally:
                db.close()

    @pytest.mark.benchmark(group="project-isolation")
    @pytest.mark.asyncio
    async def test_multi_project_performance(self, benchmark):
        """Benchmark performance with multiple projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Populate with data across multiple projects
                for project_num in range(10):
                    project_name = f"project-{project_num}"
                    for i in range(50):
                        content = f"Multi-project test reflection {i}"
                        await db.store_reflection(content, ["multi"], project_name)

                # Benchmark multi-project search
                def multi_project_search():
                    for project_num in range(10):
                        project_name = f"project-{project_num}"
                        db.search_reflections("multi", 10, project_name)

                benchmark(multi_project_search)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_retrieval_performance(self, benchmark):
        """Benchmark reflection retrieval performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Store reflections to retrieve
                reflection_ids = []
                for i in range(100):
                    content = f"Retrieval performance test reflection {i}"
                    reflection_id = await db.store_reflection(
                        content, ["retrieval"], "benchmark-project"
                    )
                    reflection_ids.append(reflection_id)

                # Benchmark retrieval operations
                def retrieve_reflections():
                    for reflection_id in reflection_ids:
                        db.get_reflection(reflection_id)

                benchmark(retrieve_reflections)

            finally:
                db.close()

    @pytest.mark.benchmark(group="database-operations")
    @pytest.mark.asyncio
    async def test_tag_filtering_performance(self, benchmark):
        """Benchmark tag filtering performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = ReflectionDatabase(str(db_path))
            await db.initialize()

            try:
                # Populate with reflections having various tags
                for i in range(200):
                    tags = [f"tag_{i % 20}", "performance"]
                    content = f"Tag filtering performance test reflection {i}"
                    await db.store_reflection(content, tags, "benchmark-project")

                # Benchmark tag filtering
                def tag_filter_search():
                    db.search_reflections(
                        "performance",
                        20,
                        "benchmark-project",
                        tags=["tag_5", "performance"],
                    )

                benchmark(tag_filter_search)

            finally:
                db.close()
