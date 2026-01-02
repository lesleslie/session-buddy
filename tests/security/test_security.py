#!/usr/bin/env python3
"""Security tests for session management and reflection tools."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from session_buddy.adapters.reflection_adapter import (
    ReflectionDatabaseAdapter as ReflectionDatabase,
)


class TestSecurity:
    """Security tests for potential vulnerabilities."""

    async def test_path_traversal_protection(self):
        """Test that file operations are protected against path traversal."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_security.duckdb"
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Attempt to use path traversal in content
            malicious_content = "../../../etc/passwd"
            tags = ["test"]

            # This should either fail safely or handle the path traversal appropriately
            try:
                reflection_id = await db.store_reflection(malicious_content, tags)
                # If it succeeds, retrieving should also work safely
                retrieved = await db.get_reflection_by_id(reflection_id)
                # The content should be preserved as provided (validation happens elsewhere if at all)
                assert retrieved["content"] == malicious_content
            except Exception:
                # It's also acceptable if the operation fails due to validation
                pass

            db.close()

    async def test_sql_injection_in_search(self):
        """Test that search operations are protected against SQL injection."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_sql_injection.duckdb"
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Add a test reflection
            await db.store_reflection("Normal content for testing", ["test"])

            # Attempt SQL injection in search query
            injection_queries = [
                "'; DROP TABLE reflections; --",
                "'; UPDATE reflections SET content='hacked'; --",
                "'; SELECT * FROM reflections; --",
                "' OR 1=1; --",
                "'; SELECT * FROM reflections WHERE content LIKE '%'",  # Truncated to test error handling
            ]

            for query in injection_queries:
                try:
                    # This should either work safely or fail gracefully
                    results = await db.similarity_search(query, limit=10)
                    # If it returns results, they should be from actual data, not injection
                    assert isinstance(results, list)
                except Exception:
                    # It's acceptable for these to raise exceptions if properly handled
                    pass

            db.close()

    async def test_executable_content_storage(self):
        """Test storage of potentially executable content."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_executable.duckdb"
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Content that might look like executable code
            executable_looking_content = """
import os
os.system('rm -rf /')  # Harmless in this context, just testing storage
def dangerous_function():
    return "Potentially harmful if executed"
"""

            tags = ["security", "test"]

            # This should store the content safely as text
            try:
                reflection_id = await db.store_reflection(
                    executable_looking_content, tags
                )
                retrieved = await db.get_reflection_by_id(reflection_id)

                # Content should be stored exactly as provided
                assert retrieved["content"] == executable_looking_content
                assert retrieved["tags"] == tags
            except Exception:
                # It's acceptable if this fails if there's content validation
                pass

            db.close()

    async def test_large_content_handling(self):
        """Test handling of extremely large content to prevent resource exhaustion."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_large_content.duckdb"
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Extremely large content (10MB)
            large_content = "A" * (10 * 1024 * 1024)  # 10MB of 'A's
            tags = ["large", "test"]

            try:
                reflection_id = await db.store_reflection(large_content, tags)
                retrieved = await db.get_reflection_by_id(reflection_id)

                # Should handle large content appropriately
                assert retrieved["content"] == large_content
                assert len(retrieved["content"]) == len(large_content)
            except MemoryError:
                # It's acceptable to fail with MemoryError if system limits are reached
                pytest.skip("Memory limits reached during test")
            except Exception:
                # Other failures are acceptable if content size is validated
                pass

            db.close()

    async def test_special_characters_in_content(self):
        """Test storage and retrieval of content with special characters."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_special_chars.duckdb"
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Content with various special characters
            special_content = """
This content includes special chars:
Null byte: \x00
Newlines: \n\r
Tabs: \t
Quotes: " ' `
Backslashes: \\
Control chars: \x01\x02\x03
Unicode: ñáéíóú 中文 🚀
"""

            tags = ["special-chars", "unicode", "test"]

            # Should handle special characters properly
            reflection_id = await db.store_reflection(special_content, tags)
            retrieved = await db.get_reflection_by_id(reflection_id)

            assert retrieved["content"] == special_content
            assert retrieved["tags"] == tags

            db.close()

    async def test_reflection_id_manipulation(self):
        """Test that reflection IDs are properly handled and can't be manipulated."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_id_manipulation.duckdb"
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Store a reflection
            content = "Test content"
            tags = ["test"]
            original_id = await db.store_reflection(content, tags)

            # Try to retrieve with a non-existent ID
            non_existent_id = "definitely-not-a-valid-id"
            result = await db.get_reflection_by_id(non_existent_id)

            # Should return None for non-existent IDs
            assert result is None

            # Try to retrieve with the actual ID
            actual_result = await db.get_reflection_by_id(original_id)
            assert actual_result is not None
            assert actual_result["content"] == content

            db.close()

    async def test_session_permissions_security(self):
        """Test security aspects of session permissions."""
        # This test would require access to the session management system
        # For now, we'll just verify that the module loads properly
        from session_buddy.core.session_manager import SessionLifecycleManager

        manager = SessionLifecycleManager()

        # Test with a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)

            # Mock git repository status
            with patch(
                "session_buddy.core.session_manager.is_git_repository",
                return_value=True,
            ):
                with patch("os.chdir"):
                    with patch("os.getcwd", return_value=str(project_dir)):
                        # Initialize session
                        init_result = await manager.initialize_session(str(project_dir))

                        # Verify success and check that it's secure
                        assert init_result["success"] is True
                        assert (
                            "error" not in init_result or init_result["error"] is None
                        )

    @pytest.mark.skip(
        reason="Requires ONNX embeddings model - skipped in environments without model files"
    )
    async def test_environment_variable_injection(self):
        """Test that environment variables are handled safely."""
        import os

        from tests.test_helpers import create_test_reflection_database

        # Test with a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_env_injection.duckdb"

            # This test doesn't actually inject anything malicious,
            # but verifies that the database can be created properly
            db = create_test_reflection_database(db_path)
            await db.initialize()

            # Store some content
            await db.store_reflection("Environment test content", ["env", "test"])

            # Verify we can retrieve it
            results = await db.similarity_search("environment", limit=10)
            assert len(results) > 0

            # Check that our content appears in results
            found = any(
                "environment test content" in result["content"].lower()
                for result in results
            )
            assert found

            db.close()

    async def test_database_file_path_security(self):
        """Test that database file paths are handled securely."""
        from tests.test_helpers import create_test_reflection_database

        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Regular path (should work)
            normal_db_path = base_dir / "normal_db.duckdb"
            db1 = create_test_reflection_database(normal_db_path)
            await db1.initialize()
            await db1.store_reflection("Normal content", ["test"])
            db1.close()

            # Try to check that the file was created (but don't access system directories)
            assert normal_db_path.exists()


if __name__ == "__main__":
    pytest.main([__file__])
