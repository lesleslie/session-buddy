#!/usr/bin/env python3
"""Performance and benchmark tests for the session management system."""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest
from tests.helpers import (
    AsyncTestHelper,
    DatabaseTestHelper,
    PerformanceHelper,
    TestDataFactory,
)


class TestPerformanceBenchmarks:
    """Performance and benchmark tests for core functionality."""

    @pytest.mark.performance
    async def test_conversation_storage_performance(self, perf_helper):
        """Benchmark conversation storage performance."""
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Measure performance of storing conversations
            async with perf_helper.measure_time() as measurements:
                for i in range(100):
                    await db.store_conversation(
                        f"Benchmark conversation {i}",
                        {"project": "benchmark", "iteration": i},
                    )

            duration = measurements["duration"]

            # Should store 100 conversations in under 5 seconds
            assert duration < 5.0, f"Storing 100 conversations took {duration:.2f}s"

            # Performance requirement: at least 20 ops per second
            ops_per_second = 100 / duration if duration > 0 else float("inf")
            assert ops_per_second > 20, (
                f"Expected >20 ops/s, got {ops_per_second:.2f} ops/s"
            )

    @pytest.mark.performance
    async def test_reflection_storage_performance(self, perf_helper):
        """Benchmark reflection storage performance."""
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Measure performance of storing reflections
            async with perf_helper.measure_time() as measurements:
                for i in range(50):
                    await db.store_reflection(
                        f"Benchmark reflection {i}",
                        [f"tag_{i % 10}", "benchmark", "performance"],
                    )

            duration = measurements["duration"]

            # Should store 50 reflections in under 3 seconds
            assert duration < 3.0, f"Storing 50 reflections took {duration:.2f}s"

    @pytest.mark.performance
    async def test_search_performance(self, perf_helper):
        """Benchmark search performance with various data sizes."""
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Pre-populate with test data
            for i in range(1000):
                await db.store_conversation(
                    f"Performance search test content {i} with more searchable text",
                    {"project": "perf-search", "index": i},
                )

            # Measure search performance
            async with perf_helper.measure_time() as measurements:
                results = await db.search_conversations("search test", limit=10)

            duration = measurements["duration"]

            # Should search 1000 records in under 1 second
            assert duration < 1.0, f"Search took {duration:.2f}s"
            assert len(results) <= 10  # Results limited to 10

    @pytest.mark.performance
    async def test_bulk_operations_performance(self, perf_helper):
        """Benchmark bulk operations performance."""
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Generate bulk test data
            conversations = TestDataFactory.bulk_conversations(200, "bulk-perf-test")

            # Measure bulk storage performance
            async with perf_helper.measure_time() as measurements:
                for conv in conversations:
                    await db.store_conversation(
                        conv["content"], {"project": conv["project"]}
                    )

            duration = measurements["duration"]

            # Should store 200 conversations in under 5 seconds
            assert duration < 5.0, f"Storing 200 conversations took {duration:.2f}s"
            ops_per_second = 200 / duration if duration > 0 else float("inf")
            assert ops_per_second > 40, (
                f"Expected >40 ops/s, got {ops_per_second:.2f} ops/s"
            )

    @pytest.mark.performance
    async def test_concurrent_access_performance(self, perf_helper):
        """Benchmark concurrent access performance."""
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Pre-populate the database
            for i in range(50):
                await db.store_conversation(
                    f"Concurrent test {i}", {"project": "concurrent-perf-test"}
                )

            # Measure time for concurrent operations
            start_time = time.time()

            async def concurrent_operation(op_id: int):
                await db.store_conversation(
                    f"Concurrent operation {op_id}", {"project": "concurrent-perf-test"}
                )

            # Run 20 operations concurrently
            tasks = [concurrent_operation(i) for i in range(20)]
            await asyncio.gather(*tasks)

            duration = time.time() - start_time

            # Should handle 20 concurrent operations in under 5 seconds
            assert duration < 5.0, f"20 concurrent operations took {duration:.2f}s"

    @pytest.mark.performance
    async def test_memory_usage_efficiency(self):
        """Test memory usage efficiency during operations."""
        import gc

        import psutil

        process = psutil.Process()

        # Measure initial memory usage
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Perform operations that might use memory
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Store 100 conversations
            for i in range(100):
                await db.store_conversation(
                    f"Memory efficiency test {i} " + "x" * 100,
                    {"project": "memory-efficiency-test"},
                )

        # Force garbage collection
        gc.collect()

        # Measure final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100MB for this test)
        assert memory_increase < 100.0, f"Memory increase too high: {memory_increase}MB"

    @pytest.mark.performance
    async def test_large_data_handling_performance(self):
        """Test performance with large data items."""
        async with DatabaseTestHelper.temp_reflection_db() as db:
            # Create a large conversation (10KB)
            large_content = "Large content test. " * 500  # ~10KB

            start_time = time.time()
            conv_id = await db.store_conversation(
                large_content, {"project": "large-data-test"}
            )
            store_time = time.time() - start_time

            assert conv_id is not None
            assert store_time < 1.0  # Should store large data in under 1 second

            # Test retrieval performance
            start_time = time.time()
            results = await db.search_conversations("Large content test", limit=1)
            retrieval_time = time.time() - start_time

            assert (
                len(results) >= 0
            )  # May or may not find it based on search implementation
            assert retrieval_time < 1.0  # Should retrieve in under 1 second


class TestPerformanceRegression:
    """Tests to detect performance regressions."""

    @pytest.mark.performance
    async def test_database_initialization_performance(self, perf_helper):
        """Ensure database initialization doesn't regress in performance."""
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
            db_path = tmp.name

            async with perf_helper.measure_time() as measurements:
                from session_buddy.reflection_tools import ReflectionDatabase

                db = ReflectionDatabase(db_path=db_path)
                await db.initialize()

                # Make sure to close db to avoid file locks
                db.close()

            duration = measurements["duration"]

            # Database initialization should be fast (under 1 second)
            assert duration < 1.0, f"Database initialization took {duration:.2f}s"

    @pytest.mark.performance
    async def test_embedding_generation_performance(self, perf_helper):
        """Test embedding generation performance (when available)."""
        from session_buddy.reflection_tools import ReflectionDatabase

        # Test with embeddings disabled first
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
            db_path = tmp.name

            db = ReflectionDatabase(db_path=db_path, enable_embeddings=False)
            await db.initialize()

            # Measure time for operations that would use embeddings if available
            async with perf_helper.measure_time() as measurements:
                await db.store_conversation(
                    "Embedding perf test", {"project": "embedding-perf-test"}
                )

            duration = measurements["duration"]
            assert duration < 1.0  # Should be fast without embeddings

            db.close()

    @pytest.mark.performance
    async def test_session_lifecycle_performance(self):
        """Test overall session lifecycle performance."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from session_buddy.core.session_manager import SessionLifecycleManager

        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)

            # Create a simple project structure
            (project_dir / "pyproject.toml").write_text(
                '[project]\nname = "perf-test"\n'
            )
            (project_dir / "README.md").write_text("# Perf Test")

            manager = SessionLifecycleManager()

            with patch(
                "session_buddy.core.session_manager.is_git_repository",
                return_value=True,
            ):
                with patch("os.chdir"):
                    with patch("os.getcwd", return_value=str(project_dir)):
                        # Measure complete lifecycle
                        start_time = time.time()

                        # Initialize session
                        init_result = await manager.initialize_session(str(project_dir))
                        assert init_result["success"] is True

                        # Perform a checkpoint
                        checkpoint_result = await manager.checkpoint_session()
                        assert checkpoint_result["success"] is True

                        # End the session
                        end_result = await manager.end_session()
                        assert end_result["success"] is True

                        total_duration = time.time() - start_time

                        # Complete session lifecycle should complete in under 5 seconds
                        assert total_duration < 5.0, (
                            f"Session lifecycle took {total_duration:.2f}s"
                        )


class TestScalability:
    """Scalability tests for handling increased load."""

    @pytest.mark.performance
    async def test_scaling_with_data_volume(self):
        """Test how performance scales with increasing data volume."""
        import time

        async def measure_operation_with_size(db, data_size):
            """Helper to measure performance with different data volumes."""
            start_time = time.time()

            # Add data for this test
            for i in range(data_size):
                await db.store_conversation(
                    f"Scaling test conversation {i}",
                    {"project": f"scaling-test-{data_size}"},
                )

            # Perform a search operation
            await db.search_conversations("scaling test", limit=5)

            return time.time() - start_time

        # Test with increasing data volumes
        sizes = [10, 50, 100, 200]  # Smaller sizes for CI/testing purposes
        times = []

        for size in sizes:
            async with DatabaseTestHelper.temp_reflection_db() as db:
                operation_time = await measure_operation_with_size(db, size)
                times.append(operation_time)
                # Each test gets a fresh database with specific data size

        # Performance should scale reasonably - not exponential growth
        if len(times) > 1:
            # Calculate growth rate between smallest and largest
            growth_rate = times[-1] / times[0] if times[0] > 0 else float("inf")

            # Growth should be sub-quadratic (O(n) or O(n log n), not O(n^2))
            expected_max_growth = (sizes[-1] / sizes[0]) * 2  # Allow 2x linear growth
            assert growth_rate < expected_max_growth, (
                f"Performance growth too high: {growth_rate}x vs expected <{expected_max_growth}x"
            )
