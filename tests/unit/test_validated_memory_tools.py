#!/usr/bin/env python3
"""Tests for validated_memory_tools module.

Tests Pydantic parameter validation integration with memory tools,
covering validation success, validation failures, and error handling.

Phase 2: Core Coverage (0% → 60%) - Validated Memory Tools
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStoreReflectionValidated:
    """Test _store_reflection_validated_impl function.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_store_reflection_with_valid_params(self) -> None:
        """Should store reflection with valid parameters."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        # Mock reflection database
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=True)

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test reflection content",
                tags=["test", "async"],
            )

            assert "Reflection stored successfully!" in result
            assert "Test reflection content" in result
            assert "Tags: test, async" in result
            mock_db.store_reflection.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_reflection_with_empty_content_fails_validation(self) -> None:
        """Should reject empty content with validation error."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _store_reflection_validated_impl(
                content="",
                tags=None,
            )

            assert "Parameter validation error" in result
            # Pydantic error message for min_length constraint
            assert "at least 1 character" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_with_invalid_tags_fails_validation(self) -> None:
        """Should reject invalid tag format with validation error."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            # Tags with spaces should fail validation
            result = await _store_reflection_validated_impl(
                content="Valid content",
                tags=["valid-tag", "invalid tag with spaces"],
            )

            assert (
                "Parameter validation error" in result or "validation" in result.lower()
            )

    @pytest.mark.asyncio
    async def test_store_reflection_without_tags(self) -> None:
        """Should store reflection without tags."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=True)

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Reflection stored successfully!" in result
            # Should not mention tags when None provided
            call_kwargs = mock_db.store_reflection.call_args.kwargs
            assert call_kwargs["tags"] == []

    @pytest.mark.asyncio
    async def test_store_reflection_when_tools_not_available(self) -> None:
        """Should return error when reflection tools not available."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Reflection tools not available" in result
            assert "uv sync --extra embeddings" in result

    @pytest.mark.asyncio
    async def test_store_reflection_database_error(self) -> None:
        """Should handle database errors gracefully."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=False)

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Failed to store reflection" in result

    @pytest.mark.asyncio
    async def test_store_reflection_truncates_long_content_in_output(self) -> None:
        """Should truncate long content in success message."""
        from session_buddy.tools.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=True)

        long_content = "x" * 200

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content=long_content,
                tags=None,
            )

            assert "Reflection stored successfully!" in result
            # Should show ellipsis for truncated content
            assert "..." in result
            # Should not show full 200 chars
            assert long_content not in result


class TestQuickSearchValidated:
    """Test _quick_search_validated_impl function.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_quick_search_with_valid_params(self) -> None:
        """Should perform quick search with valid parameters."""
        from session_buddy.tools.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Found reflection",
                    "project": "test-project",
                    "score": 0.95,
                    "timestamp": "2025-01-06",
                },
            ]
        )

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _quick_search_validated_impl(
                query="test query",
                min_score=0.7,
                project="test-project",
            )

            assert "Quick search for: 'test query'" in result
            assert "Found reflection" in result
            assert "Project: test-project" in result
            assert "Relevance: 0.95" in result

    @pytest.mark.asyncio
    async def test_quick_search_with_empty_query_fails_validation(self) -> None:
        """Should reject empty query with validation error."""
        from session_buddy.tools.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _quick_search_validated_impl(
                query="",
                min_score=0.7,
                project=None,
            )

            assert "Parameter validation error" in result
            assert "at least 1 character" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_with_invalid_min_score_fails_validation(self) -> None:
        """Should reject invalid min_score with validation error."""
        from session_buddy.tools.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            # Score > 1.0 should fail
            result = await _quick_search_validated_impl(
                query="test",
                min_score=1.5,
                project=None,
            )

            assert (
                "Parameter validation error" in result or "validation" in result.lower()
            )

    @pytest.mark.asyncio
    async def test_quick_search_with_no_results(self) -> None:
        """Should handle no search results gracefully."""
        from session_buddy.tools.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _quick_search_validated_impl(
                query="nonexistent",
                min_score=0.7,
                project=None,
            )

            assert "No results found" in result
            assert "Try adjusting your search terms" in result

    @pytest.mark.asyncio
    async def test_quick_search_when_tools_not_available(self) -> None:
        """Should return error when reflection tools not available."""
        from session_buddy.tools.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=0.7,
                project=None,
            )

            assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_quick_search_truncates_long_content(self) -> None:
        """Should truncate long content in results."""
        from session_buddy.tools.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        long_content = "x" * 200

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": long_content,
                    "project": "test",
                    "score": 0.9,
                    "timestamp": "2025-01-06",
                },
            ]
        )

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=0.7,
                project=None,
            )

            # Should truncate at 150 chars with ellipsis
            assert "..." in result
            assert long_content not in result


class TestSearchByFileValidated:
    """Test _search_by_file_validated_impl function.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_search_by_file_with_valid_path(self) -> None:
        """Should search for file conversations successfully."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Discussed file changes",
                    "project": "test",
                    "score": 0.88,
                    "timestamp": "2025-01-06",
                },
            ]
        )

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_file_validated_impl(
                file_path="src/main.py",
                limit=10,
                project="test",
            )

            assert "Searching conversations about: src/main.py" in result
            assert "Found 1 relevant conversations:" in result
            assert "Discussed file changes" in result

    @pytest.mark.asyncio
    async def test_search_by_file_with_empty_path_fails_validation(self) -> None:
        """Should reject empty file path with validation error."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_file_validated_impl(
                file_path="",
                limit=10,
                project=None,
            )

            assert "Parameter validation error" in result
            assert "at least 1 character" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_with_no_results(self) -> None:
        """Should handle no file conversation results gracefully."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_file_validated_impl(
                file_path="unknown.py",
                limit=10,
                project=None,
            )

            assert "No conversations found about this file" in result
            assert "not have been discussed" in result

    @pytest.mark.asyncio
    async def test_search_by_file_when_tools_not_available(self) -> None:
        """Should return error when reflection tools not available."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _search_by_file_validated_impl(
                file_path="test.py",
                limit=10,
                project=None,
            )

            assert "Reflection tools not available" in result


class TestSearchByConceptValidated:
    """Test _search_by_concept_validated_impl function.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_search_by_concept_with_valid_params(self) -> None:
        """Should search for concept conversations successfully."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Discussion about async patterns in Python",
                    "project": "test",
                    "score": 0.92,
                    "timestamp": "2025-01-06",
                    "files": ["src/async.py", "src/main.py"],
                },
            ]
        )

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_concept_validated_impl(
                concept="async patterns",
                include_files=True,
                limit=10,
                project="test",
            )

            assert "Searching for concept: 'async patterns'" in result
            assert "Found 1 related conversations:" in result
            assert "Discussion about async patterns" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_with_empty_concept_fails_validation(self) -> None:
        """Should reject empty concept with validation error."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_concept_validated_impl(
                concept="",
                include_files=True,
                limit=10,
                project=None,
            )

            assert "Parameter validation error" in result
            assert "at least 1 character" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_concept_with_no_results(self) -> None:
        """Should handle no concept results gracefully."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.tools.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_concept_validated_impl(
                concept="unknown concept",
                include_files=False,
                limit=10,
                project=None,
            )

            assert "No conversations found about this concept" in result
            assert "Try related terms or broader concepts" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_when_tools_not_available(self) -> None:
        """Should return error when reflection tools not available."""
        from session_buddy.tools.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        with patch(
            "session_buddy.tools.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _search_by_concept_validated_impl(
                concept="test",
                include_files=True,
                limit=10,
                project=None,
            )

            assert "Reflection tools not available" in result


class TestHelperFunctions:
    """Test helper functions for formatting.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    def test_format_file_search_header(self) -> None:
        """Should format file search header correctly."""
        from session_buddy.tools.validated_memory_tools import (
            _format_file_search_header,
        )

        result = _format_file_search_header("src/main.py")

        assert isinstance(result, list)
        assert "Searching conversations about: src/main.py" in result[0]
        assert "=" * 50 in result[1]

    def test_format_file_search_result(self) -> None:
        """Should format single file search result."""
        from session_buddy.tools.validated_memory_tools import (
            _format_file_search_result,
        )

        result_data = {
            "content": "Test conversation content",
            "project": "test-project",
            "score": 0.95,
            "timestamp": "2025-01-06",
        }

        result = _format_file_search_result(result_data, 1)

        assert isinstance(result, list)
        assert any("Test conversation content" in line for line in result)
        assert any("Project: test-project" in line for line in result)
        assert any("Relevance: 0.95" in line for line in result)

    def test_format_file_search_result_truncates_long_content(self) -> None:
        """Should truncate long content in file search results."""
        from session_buddy.tools.validated_memory_tools import (
            _format_file_search_result,
        )

        long_content = "x" * 250

        result_data = {
            "content": long_content,
            "project": "test",
            "score": 0.9,
            "timestamp": "2025-01-06",
        }

        result = _format_file_search_result(result_data, 1)

        result_text = "\n".join(result)
        # Should truncate at 200 chars with ellipsis
        assert "..." in result_text
        assert long_content not in result_text

    def test_format_file_search_results_with_results(self) -> None:
        """Should format complete file search results."""
        from session_buddy.tools.validated_memory_tools import (
            _format_file_search_results,
        )

        results = [
            {"content": "Result 1", "score": 0.9, "timestamp": "2025-01-06"},
            {"content": "Result 2", "score": 0.8, "timestamp": "2025-01-05"},
        ]

        result = _format_file_search_results(results, "test.py")

        result_text = "\n".join(result)
        assert "Searching conversations about: test.py" in result_text
        assert "Found 2 relevant conversations:" in result_text
        assert "Result 1" in result_text
        assert "Result 2" in result_text

    def test_format_file_search_results_with_no_results(self) -> None:
        """Should format file search with no results."""
        from session_buddy.tools.validated_memory_tools import (
            _format_file_search_results,
        )

        result = _format_file_search_results([], "unknown.py")

        result_text = "\n".join(result)
        assert "No conversations found about this file" in result_text
        assert "not have been discussed" in result_text

    def test_format_validated_concept_result(self) -> None:
        """Should format validated concept result."""
        from session_buddy.tools.validated_memory_tools import (
            _format_validated_concept_result,
        )

        result_data = {
            "content": "Concept discussion content",
            "project": "test",
            "score": 0.88,
            "timestamp": "2025-01-06",
            "files": ["file1.py", "file2.py", "file3.py"],
        }

        result = _format_validated_concept_result(result_data, 1, include_files=True)

        result_text = "\n".join(result)
        assert "Concept discussion content" in result_text
        assert "Project: test" in result_text
        assert "Relevance: 0.88" in result_text
        assert "Files:" in result_text

    def test_format_validated_concept_result_without_files(self) -> None:
        """Should format concept result without including files."""
        from session_buddy.tools.validated_memory_tools import (
            _format_validated_concept_result,
        )

        result_data = {
            "content": "Concept discussion",
            "project": "test",
            "score": 0.88,
            "timestamp": "2025-01-06",
            "files": ["file1.py"],
        }

        result = _format_validated_concept_result(result_data, 1, include_files=False)

        result_text = "\n".join(result)
        assert "Concept discussion" in result_text
        # Should not include files when include_files=False
        assert "Files:" not in result_text


class TestAvailabilityChecking:
    """Test reflection tools availability checking.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    def test_check_reflection_tools_available_when_installed(self) -> None:
        """Should return True when reflection tools are available."""
        # Reset global state
        import session_buddy.tools.validated_memory_tools as module
        from session_buddy.tools.validated_memory_tools import (
            _check_reflection_tools_available,
        )

        module._reflection_tools_available = None

        with patch("importlib.util.find_spec", return_value=MagicMock()):
            result = _check_reflection_tools_available()

            assert result is True

    def test_check_reflection_tools_available_when_not_installed(self) -> None:
        """Should return False when reflection tools not available."""
        # Reset global state
        import session_buddy.tools.validated_memory_tools as module
        from session_buddy.tools.validated_memory_tools import (
            _check_reflection_tools_available,
        )

        module._reflection_tools_available = None

        with patch("importlib.util.find_spec", return_value=None):
            result = _check_reflection_tools_available()

            assert result is False

    def test_check_reflection_tools_available_caches_result(self) -> None:
        """Should cache availability check result."""
        # Reset global state
        import session_buddy.tools.validated_memory_tools as module
        from session_buddy.tools.validated_memory_tools import (
            _check_reflection_tools_available,
        )

        module._reflection_tools_available = None

        # First call - should check
        with patch("importlib.util.find_spec", return_value=MagicMock()) as mock_spec:
            result1 = _check_reflection_tools_available()
            assert mock_spec.call_count == 1

            # Second call - should use cached value
            result2 = _check_reflection_tools_available()
            assert mock_spec.call_count == 1  # Not called again
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_get_reflection_database_when_available(self) -> None:
        """Should get reflection database when available."""
        # Reset global state
        import session_buddy.tools.validated_memory_tools as module
        from session_buddy.tools.validated_memory_tools import (
            _get_reflection_database,
        )

        module._reflection_tools_available = None

        mock_db = AsyncMock()

        with patch(
            "session_buddy.reflection_tools.get_reflection_database",
            return_value=mock_db,
        ):
            result = await _get_reflection_database()

            assert result == mock_db

    @pytest.mark.asyncio
    async def test_get_reflection_database_when_not_available(self) -> None:
        """Should raise ImportError when database not available."""
        # Reset global state
        import session_buddy.tools.validated_memory_tools as module
        from session_buddy.tools.validated_memory_tools import (
            _get_reflection_database,
        )

        module._reflection_tools_available = None

        with patch(
            "session_buddy.reflection_tools.get_reflection_database",
            return_value=None,
        ):
            with pytest.raises(ImportError, match="Reflection tools not available"):
                await _get_reflection_database()

    @pytest.mark.asyncio
    async def test_get_reflection_database_when_previously_failed(self) -> None:
        """Should raise immediately when previously failed."""
        # Set global flag to indicate previous failure
        import session_buddy.tools.validated_memory_tools as module
        from session_buddy.tools.validated_memory_tools import (
            _get_reflection_database,
        )

        module._reflection_tools_available = False

        with pytest.raises(ImportError, match="Reflection tools not available"):
            await _get_reflection_database()


class TestValidationExamples:
    """Test validation examples class.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    @pytest.mark.asyncio
    async def test_example_valid_calls_structure(self) -> None:
        """Should have example_valid_calls method."""
        from session_buddy.tools.validated_memory_tools import ValidationExamples

        assert hasattr(ValidationExamples, "example_valid_calls")
        assert callable(ValidationExamples.example_valid_calls)

    @pytest.mark.asyncio
    async def test_example_validation_errors_structure(self) -> None:
        """Should have example_validation_errors method."""
        from session_buddy.tools.validated_memory_tools import ValidationExamples

        assert hasattr(ValidationExamples, "example_validation_errors")
        assert callable(ValidationExamples.example_validation_errors)


class TestMigrationGuide:
    """Test migration guide class.

    Phase 2: Core Coverage - validated_memory_tools.py (0% → 60%)
    """

    def test_migration_guide_has_before_method(self) -> None:
        """Should have before_migration method."""
        from session_buddy.tools.validated_memory_tools import MigrationGuide

        assert hasattr(MigrationGuide, "before_migration")
        assert callable(MigrationGuide.before_migration)

    def test_migration_guide_has_after_method(self) -> None:
        """Should have after_migration method."""
        from session_buddy.tools.validated_memory_tools import MigrationGuide

        assert hasattr(MigrationGuide, "after_migration")
        assert callable(MigrationGuide.after_migration)
