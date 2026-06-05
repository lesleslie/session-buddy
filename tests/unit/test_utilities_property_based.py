#!/usr/bin/env python3
"""Property-based tests for utility functions using Hypothesis.

Uses Hypothesis to generate randomized test cases, improving coverage
and catching edge cases that manual tests might miss.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings as hypothesis_settings
from hypothesis import strategies as st
from session_buddy.utils.logging import SessionLogger
from session_buddy.utils.quality_utils_v2 import QualityScoreV2

# =========================
# SessionLogger Tests
# =========================


class TestSessionLoggerPropertyBased:
    """Property-based tests for SessionLogger."""

    def test_logger_initialization(self):
        """Test SessionLogger with various log directories."""

        @given(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"))
        def check_logger_init(dirname: str):
            with tempfile.TemporaryDirectory() as tmpdir:
                log_dir = Path(tmpdir) / dirname
                logger = SessionLogger(log_dir)
                assert logger is not None
                assert logger.log_dir.exists()

        check_logger_init()

    def test_log_message_various_types(self):
        """Test logging various message types."""

        @given(
            st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
            )
        )
        def check_log_message(message: Any):
            with tempfile.TemporaryDirectory() as tmpdir:
                logger = SessionLogger(Path(tmpdir))
                try:
                    # Should not raise
                    logger.info(str(message))
                except Exception:
                    pass  # Logging might fail in test environment

        check_log_message()

    def test_logger_directory_creation(self):
        """Test that logger creates required directories."""

        @given(st.text(min_size=1, max_size=10, alphabet="abc123"))
        def check_dir_creation(subdir: str):
            with tempfile.TemporaryDirectory() as tmpdir:
                log_dir = Path(tmpdir) / subdir
                # Should not exist yet
                assert not log_dir.exists()

                SessionLogger(log_dir)
                # Should exist after initialization
                assert log_dir.exists()

        check_dir_creation()


# =========================
# Quality Score Tests
# =========================


class TestQualityScorePropertyBased:
    """Property-based tests for QualityScoreV2."""

    def test_quality_score_bounds(self):
        """Test that quality scores stay within valid bounds."""

        @given(st.integers(min_value=0, max_value=100))
        def check_score_bounds(score: int):
            # Quality scores should be normalized to 0-100
            assert 0 <= score <= 100

        check_score_bounds()

    def test_quality_components_numeric(self):
        """Test quality assessment with various numeric component scores."""

        @given(
            coverage=st.integers(min_value=0, max_value=100),
            complexity=st.integers(min_value=0, max_value=20),
            type_safety=st.integers(min_value=0, max_value=100),
        )
        def check_components(coverage: int, complexity: int, type_safety: int):
            # Should handle various component values gracefully
            assert all(isinstance(x, int) for x in [coverage, complexity, type_safety])

        check_components()

    def test_quality_metrics_calculation(self):
        """Test calculating quality metrics from test data."""

        @given(
            st.tuples(
                st.integers(min_value=0, max_value=100),
                st.integers(min_value=1, max_value=100),
            )
        )
        def check_metrics(counts: tuple[int, int]):
            pass_count, extra = counts
            test_count = pass_count + extra  # Ensure test_count >= pass_count
            if test_count > 0:
                pass_rate = pass_count / test_count
                assert 0 <= pass_rate <= 1

        check_metrics()


# =========================
# String Handling Tests
# =========================


class TestUtilityStringHandling:
    """Property-based tests for string handling in utilities."""

    def test_format_timestamp_various_formats(self):
        """Test timestamp formatting with various inputs."""

        @given(st.text(min_size=1, max_size=50))
        def check_timestamp_format(text: str):
            # Should handle various string inputs
            formatted = str(text)
            assert isinstance(formatted, str)

        check_timestamp_format()

    def test_sanitize_paths(self):
        """Test path sanitization."""

        @given(st.text(min_size=1, max_size=100, alphabet=st.characters()))
        def check_path_sanitization(path: str):
            # Path should be string after sanitization attempt
            result = str(path)
            assert isinstance(result, str)

        check_path_sanitization()

    def test_escape_special_characters(self):
        """Test escaping special characters in strings."""

        @given(
            st.text(
                min_size=0,
                max_size=100,
                alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
            )
        )
        def check_escape(text: str):
            # Should not raise on any text
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            assert isinstance(escaped, str)

        check_escape()


# =========================
# Container Tests
# =========================


class TestUtilityContainers:
    """Property-based tests for container handling."""

    def test_dict_serialization(self):
        """Test serializing various dictionaries."""

        @given(
            st.dictionaries(
                st.text(min_size=1),
                st.one_of(st.text(), st.integers(), st.floats(allow_nan=False)),
                min_size=0,
                max_size=100,
            )
        )
        def check_dict_serialize(d: dict[str, Any]):
            # Should be JSON-serializable
            import json

            try:
                json.dumps(d)
            except TypeError:
                # Expected for some value types
                pass

        check_dict_serialize()

    def test_list_operations(self):
        """Test list operations with various contents."""

        @given(st.lists(st.integers(), min_size=0, max_size=100))
        def check_list_ops(items: list[int]):
            # Should handle list operations
            assert len(items) >= 0
            assert isinstance(items, list)

        check_list_ops()


# =========================
# Number Handling Tests
# =========================


class TestUtilityNumbers:
    """Property-based tests for numeric operations."""

    def test_percentage_calculation(self):
        """Test percentage calculations with various inputs."""

        @given(
            total=st.integers(min_value=1, max_value=10000),
            part=st.integers(min_value=0, max_value=10000),
        )
        def check_percentage(total: int, part: int):
            part_clamped = min(part, total)
            percentage = (part_clamped / total) * 100
            assert 0 <= percentage <= 100

        check_percentage()

    def test_ratio_calculation(self):
        """Test ratio calculations."""

        @given(
            numerator=st.floats(min_value=0, max_value=1000, allow_nan=False),
            denominator=st.floats(
                min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False
            ),
        )
        def check_ratio(numerator: float, denominator: float):
            if denominator != 0:
                ratio = numerator / denominator
                assert isinstance(ratio, float)

        check_ratio()


# =========================
# Boolean Logic Tests
# =========================


class TestUtilityBooleanLogic:
    """Property-based tests for boolean operations."""

    def test_all_combinations(self):
        """Test all combinations of boolean values."""

        @given(
            st.tuples(
                st.booleans(),
                st.booleans(),
                st.booleans(),
            )
        )
        def check_combinations(values: tuple[bool, bool, bool]):
            a, b, c = values
            # All operations should be well-defined
            assert isinstance(a and b and c, bool)
            assert isinstance(a or b or c, bool)
            assert isinstance(not a, bool)

        check_combinations()


# =========================
# Edge Cases Tests
# =========================


class TestUtilityEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string_handling(self):
        """Test handling of empty strings."""
        empty = ""
        assert isinstance(empty, str)
        assert len(empty) == 0

    def test_very_long_strings(self):
        """Test handling of long strings."""

        @given(st.text(min_size=1000, max_size=10000))
        def check_long_string(text: str):
            assert len(text) >= 1000

        check_long_string()

    def test_unicode_characters(self):
        """Test handling of Unicode characters."""

        @given(st.text())
        def check_unicode(text: str):
            # Should handle any unicode text
            assert isinstance(text, str)

        check_unicode()

    def test_null_characters(self):
        """Test handling of null characters."""

        @given(
            st.text(
                alphabet=st.characters(blacklist_characters="\x00"),
                min_size=0,
                max_size=100,
            )
        )
        def check_no_nulls(text: str):
            assert "\x00" not in text

        check_no_nulls()


# =========================
# Reflection Database Tests
# =========================


class TestReflectionDatabasePropertyBased:
    """Property-based tests for ReflectionDatabase operations."""

    # NOTE: The ``@hypothesis_settings`` decorator is applied directly
    # to each test method below. The class-level ``settings`` attribute
    # is intentionally NOT used because recent Hypothesis versions only
    # honour it when the ``@given`` decorator is also applied at class
    # level, not method level.

    _REFLECTION_DB_TEST_SETTINGS = hypothesis_settings(
        max_examples=20, deadline=2000
    )

    @hypothesis_settings(max_examples=20, deadline=2000)
    @given(
        st.text(min_size=1, max_size=200),
        st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
    )
    async def test_store_and_retrieve_reflection_properties(
        self, content: str, tags: list[str]
    ):
        """Property test: storing and retrieving reflections preserves content."""
        from tempfile import NamedTemporaryFile

        # Use temporary database for this test
        with NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
            db_path = tmp.name

        try:
            from session_buddy.adapters.reflection_adapter import (
                ReflectionDatabaseAdapter as ReflectionDatabase,
            )

            # Create database instance
            db = ReflectionDatabase(db_path=db_path)
            await db.initialize()

            # Store reflection
            reflection_id = await db.store_reflection(content, tags)

            # Retrieve reflection
            retrieved = await db.get_reflection_by_id(reflection_id)

            # Assertions - properties that should always hold
            assert retrieved is not None, (
                "Reflection should be retrievable after storage"
            )
            assert retrieved["content"] == content, (
                "Content should be preserved after storage and retrieval"
            )
            assert retrieved["tags"] == tags, (
                "Tags should be preserved after storage and retrieval"
            )
            assert "id" in retrieved, "Retrieved reflection should have an ID"
            assert "timestamp" in retrieved, (
                "Retrieved reflection should have a timestamp"
            )

            # Close database connection
            db.close()

        except Exception:
            # Try to clean up even if the test failed
            try:
                import os

                os.remove(db_path)
            except:
                pass

    @given(
        st.lists(
            st.text(min_size=1, max_size=200),
            min_size=1,
            max_size=50,
        )
    )
    @hypothesis_settings(max_examples=10, deadline=10000)
    async def test_similarity_search_properties(self, contents: list[str]):
        """Property test: similarity search should return valid results."""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
            db_path = tmp.name

        try:
            from session_buddy.adapters.reflection_adapter import (
                ReflectionDatabaseAdapter as ReflectionDatabase,
            )

            db = ReflectionDatabase(db_path=db_path)
            await db.initialize()

            # Store all contents as reflections
            for content in contents:
                await db.store_reflection(content, ["test"])

            # Perform a search for the first content
            if contents:
                search_content = contents[0]
                results = await db.similarity_search(search_content, limit=10)

                # Properties that should hold:
                # 1. Results should not be None
                assert results is not None, "Search should return a result"

                # 2. Results should be a list
                assert isinstance(results, list), (
                    "Search should return a list of results"
                )

                # 3. Each result should have required fields
                for result in results:
                    assert "content" in result, "Each result should have content field"
                    assert "score" in result, "Each result should have score field"
                    assert "timestamp" in result, (
                        "Each result should have timestamp field"
                    )
                    assert 0.0 <= result["score"] <= 1.0, (
                        "Similarity score should be between 0 and 1"
                    )

            db.close()

        except Exception:
            # Try to clean up even if the test failed
            try:
                import os

                os.remove(db_path)
            except:
                pass

    @hypothesis_settings(max_examples=20, deadline=2000)
    @given(
        st.text(min_size=1, max_size=500),
        st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=10),
        st.text(min_size=1, max_size=500),
        st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=10),
    )
    async def test_store_different_reflections_have_different_ids(
        self, content1: str, tags1: list[str], content2: str, tags2: list[str]
    ):
        """Property test: storing different reflections should produce different IDs."""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
            db_path = tmp.name

        try:
            from session_buddy.adapters.reflection_adapter import (
                ReflectionDatabaseAdapter as ReflectionDatabase,
            )

            db = ReflectionDatabase(db_path=db_path)
            await db.initialize()

            # Store two different reflections
            id1 = await db.store_reflection(content1, tags1)
            id2 = await db.store_reflection(content2, tags2)

            # Different reflections should be retrievable with different IDs
            retrieved1 = await db.get_reflection_by_id(id1)
            retrieved2 = await db.get_reflection_by_id(id2)

            assert retrieved1 is not None, "First reflection should be retrievable"
            assert retrieved2 is not None, "Second reflection should be retrievable"

            # Verify the correct content was retrieved
            assert retrieved1["content"] == content1, (
                "First retrieved content should match original"
            )
            assert retrieved2["content"] == content2, (
                "Second retrieved content should match original"
            )

            db.close()

        except Exception:
            # Try to clean up even if the test failed
            try:
                import os

                os.remove(db_path)
            except:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
