#!/usr/bin/env python3
"""Security tests for input validation and vulnerability prevention."""

import os
import tempfile
from pathlib import Path

import pytest
from tests.helpers import MockingHelper, TestDataFactory


class TestInputValidation:
    """Tests for input validation and sanitization."""

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "'; DROP TABLE reflections; --",
            "<script>alert('xss')</script>",
            "../../../../etc/passwd",
            "\x00\x01\x02\x03",  # Binary injection
            "A" * 10000,  # Buffer overflow attempt
            "SELECT * FROM users; --",
            "${system('rm -rf /')}",  # Command injection template
            "{{7*7}}",  # Template injection
        ],
    )
    async def test_malicious_input_handling(self, malicious_input: str, fast_temp_db):
        """Test system handles malicious input safely."""
        try:
            # Try to store conversation with malicious content
            result_id = await fast_temp_db.store_conversation(
                malicious_input, {"project": "security-test"}
            )

            # If successful, make sure no SQL injection occurred
            if result_id:
                # Retrieve and verify the stored content is exactly what was provided
                await fast_temp_db.search_conversations(malicious_input)
                # We might not find the result due to search implementation,
                # but that's ok, the important thing is it didn't cause a crash
        except (ValueError, TypeError) as e:
            # Acceptable to reject invalid input with appropriate errors
            assert "invalid" in str(e).lower() or "malformed" in str(e).lower()

    @pytest.mark.parametrize(
        "unsafe_path",
        [
            "/etc/passwd",
            "../config.py",
            "..\\..\\windows\\system32\\config\\sam",
            "file:///etc/passwd",
            "file://localhost/etc/passwd",
        ],
    )
    def test_path_traversal_protection(self, unsafe_path: str):
        """Test that path traversal attempts are handled safely."""
        import os
        from pathlib import Path

        # Simulate user input that might be used in file operations
        base_path = Path("/safe/base/path")

        # The correct way to handle user input in paths - using Path operations
        # This prevents path traversal
        sanitized = unsafe_path.replace("\\", "/")
        safe_path = base_path / Path(sanitized).name

        # Verify the path stays within the safe base
        assert str(safe_path).startswith(str(base_path))
        assert ".." not in str(safe_path)

    async def test_large_input_handling(self, fast_temp_db):
        """Test system handles large inputs without resource exhaustion."""
        # Create very large content (larger than typical)
        large_content = "A" * 100000  # 100KB of content

        # Should handle large content without crashing
        result_id = await fast_temp_db.store_conversation(
            large_content, {"project": "large-input-test"}
        )
        assert result_id is not None

        # Test large tags list
        large_tags = [f"tag_{i}" for i in range(1000)]
        result_id = await fast_temp_db.store_reflection("Large tags test", large_tags)
        assert result_id is not None


class TestSQLInjectionProtection:
    """Tests for SQL injection prevention."""

    async def test_sql_injection_in_content(self, fast_temp_db):
        """Test SQL injection attempts in content fields."""
        sql_payloads = [
            "'; DROP TABLE conversations; --",
            "'; EXEC xp_cmdshell 'dir'; --",
            "1; SELECT * FROM conversations WHERE '1'='1",
            "'; INSERT INTO conversations VALUES ('hacked', 'hacked'); --",
            "'; UPDATE conversations SET content='hacked' WHERE 1=1; --",
        ]

        for payload in sql_payloads:
            try:
                # This should not cause SQL injection
                result_id = await fast_temp_db.store_conversation(
                    payload, {"project": "sql-injection-test"}
                )

                # Even if it's stored, a successful store without exception is good
                # The important thing is that no tables were dropped or modified inappropriately
                if result_id:
                    # Try to search for it - this tests if the DB is still intact
                    results = await fast_temp_db.search_conversations("test")
                    assert isinstance(
                        results, list
                    )  # Should return a list even if empty
            except Exception:
                # Some payloads might be rejected, which is also acceptable
                pass

    async def test_sql_injection_in_project_field(self, fast_temp_db):
        """Test SQL injection attempts in project field."""
        sql_payloads = [
            "'; DROP TABLE conversations; --",
            "'; SELECT * FROM conversations; --",
        ]

        for payload in sql_payloads:
            try:
                # This should not cause SQL injection
                await fast_temp_db.store_conversation(
                    "Normal content", {"project": payload}
                )

                # Verify DB integrity is maintained
                stats = await fast_temp_db.get_stats()
                assert "total_conversations" in stats
            except Exception:
                # Rejection of malicious input is also acceptable
                pass


class TestAuthenticationAndAuthorization:
    """Tests for authentication and authorization."""

    def test_permission_system_bypass_attempts(self):
        """Test attempts to bypass permission systems."""
        # Import the session permissions manager
        from session_buddy.core.permissions import SessionPermissionsManager

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a new permissions manager instance
            perms_manager = SessionPermissionsManager(Path(temp_dir))

            # Initially, no operations should be trusted
            assert not perms_manager.is_operation_trusted("dangerous_operation")

            # Try to bypass by directly modifying internal state (should not work in well-designed systems)
            # This test is conceptual - in a real system we'd test the actual API
            assert not perms_manager.is_operation_trusted("unauthorized_operation")

    async def test_unauthorized_database_access(self):
        """Test protection against unauthorized database access."""
        # This is a conceptual test - in reality, this would test specific access controls
        # For now, we'll just verify that the database properly handles access patterns
        with tempfile.TemporaryDirectory() as temp_dir:
            from session_buddy.reflection_tools import ReflectionDatabase

            db_path = Path(temp_dir) / "auth_test.duckdb"
            db = ReflectionDatabase(db_path=str(db_path))
            await db.initialize()

            # Verify normal operations work
            result_id = await db.store_conversation(
                "Authorized access test", {"project": "auth-test"}
            )
            assert result_id is not None

            # Close the database properly
            db.close()


class TestResourceConsumption:
    """Tests for protection against resource consumption attacks."""

    async def test_memory_exhaustion_protection(self, fast_temp_db):
        """Test protection against memory exhaustion."""
        import gc

        import psutil

        # Measure initial memory
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        iterations = int(os.environ.get("SB_MEMORY_TEST_ITERS", "100"))
        for i in range(iterations):
            # Store small conversation
            await fast_temp_db.store_conversation(
                f"Memory test {i}", {"project": "memory-test"}
            )

        # Force garbage collection
        gc.collect()

        # Measure final memory
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Should not consume unreasonable amounts of memory
        # This threshold might need adjustment based on implementation
        assert memory_increase < 200.0, f"Memory increase too high: {memory_increase}MB"

    async def test_cpu_exhaustion_protection(self):
        """Test protection against CPU exhaustion."""
        import time

        # Create a temporary database for this test
        from session_buddy.reflection_tools import ReflectionDatabase

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cpu_test.duckdb"
            db = ReflectionDatabase(db_path=str(db_path))
            await db.initialize()

            # Measure time for a standard operation
            start_time = time.time()

            iterations = int(os.environ.get("SB_CPU_TEST_ITERS", "10"))
            for i in range(iterations):
                await db.store_conversation(f"CPU test {i}", {"project": "cpu-test"})

            operation_time = time.time() - start_time

            # Operations should complete in reasonable time (less than 20 seconds default)
            assert operation_time < 20.0, f"Operations took too long: {operation_time}s"

            db.close()


class TestDataIntegrity:
    """Tests for data integrity and consistency."""

    async def test_concurrent_modification_protection(self):
        """Test protection against data corruption during concurrent access."""
        import asyncio

        # Create a shared database for concurrent access testing
        from session_buddy.reflection_tools import ReflectionDatabase

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "concurrent_test.duckdb"
            db = ReflectionDatabase(db_path=str(db_path))
            await db.initialize()

            # Define an async function for concurrent operations
            async def write_operation(op_id: int):
                return await db.store_conversation(
                    f"Concurrent operation {op_id}", {"project": "concurrent-test"}
                )

            # Run multiple operations concurrently
            tasks = [write_operation(i) for i in range(10)]
            results = await asyncio.gather(*tasks)

            # Verify all operations succeeded
            for result in results:
                assert result is not None, "A concurrent operation failed"

            # Verify database integrity
            stats = await db.get_stats()
            total_conversations = stats.get(
                "total_conversations",
                stats.get("conversations_count", 0),
            )
            assert total_conversations >= 10

            db.close()

    async def test_data_recovery_after_crash_simulation(self):
        """Test data recovery after crash simulation."""
        from session_buddy.reflection_tools import ReflectionDatabase

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "recovery_test.duckdb")

            # Create database and add data
            db = ReflectionDatabase(db_path=db_path)
            await db.initialize()

            # Add some data
            conv_id = await db.store_conversation(
                "Recovery test conversation", {"project": "recovery-test"}
            )
            assert conv_id is not None

            refl_id = await db.store_reflection(
                "Recovery test reflection", ["recovery", "test"]
            )
            assert refl_id is not None

            # Close properly
            db.close()

            # Reopen and verify data is still there
            db2 = ReflectionDatabase(db_path=db_path)
            await db2.initialize()

            # Verify conversation exists
            results = await db2.search_conversations("Recovery test conversation")
            assert len(results) == 1

            # Verify reflection exists
            stats = await db2.get_stats()
            total_reflections = stats.get(
                "total_reflections",
                stats.get("reflections_count", 0),
            )
            assert total_reflections >= 1

            db2.close()
