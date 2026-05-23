#!/usr/bin/env python3
"""Comprehensive tests for validated_memory_tools module.

Tests Pydantic parameter validation integration with memory tools,
covering all public methods, edge cases, and error handling paths.

Phase 2: Core Coverage (0% → 70%+) - Validated Memory Tools
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Test Classes for Each Public Implementation Function
# =============================================================================


class TestStoreReflectionValidatedImpl:
    """Tests for _store_reflection_validated_impl function."""

    @pytest.mark.asyncio
    async def test_store_reflection_valid_content(self) -> None:
        """Should store reflection with valid content and tags."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_123")

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test reflection content",
                tags=["test", "python"],
            )

            assert "Reflection stored successfully!" in result
            assert "ref_123" in result
            mock_db.store_reflection.assert_called_once_with(
                "Test reflection content",
                tags=["test", "python"],
            )

    @pytest.mark.asyncio
    async def test_store_reflection_valid_content_no_tags(self) -> None:
        """Should store reflection when tags is None."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_456")

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Content without tags",
                tags=None,
            )

            assert "Reflection stored successfully!" in result
            mock_db.store_reflection.assert_called_once_with(
                "Content without tags",
                tags=[],
            )

    @pytest.mark.asyncio
    async def test_store_reflection_empty_content_fails_validation(self) -> None:
        """Should return validation error for empty content."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _store_reflection_validated_impl(
                content="",
                tags=None,
            )

            assert "Parameter validation error" in result
            assert "at least 1 character" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_whitespace_content_fails_validation(self) -> None:
        """Should return validation error for whitespace-only content."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _store_reflection_validated_impl(
                content="   ",
                tags=None,
            )

            assert "Parameter validation error" in result

    @pytest.mark.asyncio
    async def test_store_reflection_invalid_tags_format(self) -> None:
        """Should return validation error for invalid tag format."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _store_reflection_validated_impl(
                content="Valid content",
                tags=["invalid tag with spaces"],
            )

            assert "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_tools_not_available(self) -> None:
        """Should return error message when tools not available."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Reflection tools not available" in result
            assert "uv sync --extra embeddings" in result

    @pytest.mark.asyncio
    async def test_store_reflection_database_returns_none(self) -> None:
        """Should handle database returning None as reflection_id."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=None)

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Failed to store reflection" in result

    @pytest.mark.asyncio
    async def test_store_reflection_database_returns_false(self) -> None:
        """Should handle database returning False as reflection_id."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=False)

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Failed to store reflection" in result

    @pytest.mark.asyncio
    async def test_store_reflection_database_connection_fails(self) -> None:
        """Should handle database connection failure."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(side_effect=Exception("Connection lost"))

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Test content",
                tags=None,
            )

            assert "Failed to store reflection" in result
            assert "Connection lost" in result

    @pytest.mark.asyncio
    async def test_store_reflection_long_content_truncated_in_output(self) -> None:
        """Should truncate long content in success message."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_789")

        long_content = "x" * 200

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content=long_content,
                tags=None,
            )

            assert "Reflection stored successfully!" in result
            assert "..." in result
            assert long_content not in result

    @pytest.mark.asyncio
    async def test_store_reflection_multiple_tags(self) -> None:
        """Should handle multiple valid tags."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_multi")

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Content with multiple tags",
                tags=["python", "async", "testing", "tdd"],
            )

            assert "Reflection stored successfully!" in result
            assert "python, async, testing, tdd" in result


class TestQuickSearchValidatedImpl:
    """Tests for _quick_search_validated_impl function."""

    @pytest.mark.asyncio
    async def test_quick_search_valid_query(self) -> None:
        """Should perform quick search with valid query."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Found reflection about testing",
                    "project": "test-project",
                    "score": 0.95,
                    "timestamp": "2025-01-06",
                },
            ]
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _quick_search_validated_impl(
                query="testing",
                min_score=0.7,
                project="test-project",
            )

            assert "Quick search for: 'testing'" in result
            assert "Found reflection about testing" in result
            assert "test-project" in result

    @pytest.mark.asyncio
    async def test_quick_search_empty_query_fails_validation(self) -> None:
        """Should return validation error for empty query."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_quick_search_whitespace_query_fails_validation(self) -> None:
        """Should return validation error for whitespace-only query."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _quick_search_validated_impl(
                query="   ",
                min_score=0.7,
                project=None,
            )

            assert "Parameter validation error" in result

    @pytest.mark.asyncio
    async def test_quick_search_min_score_too_high_fails_validation(self) -> None:
        """Should return validation error when min_score > 1.0."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=1.5,
                project=None,
            )

            assert "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_min_score_negative_fails_validation(self) -> None:
        """Should return validation error when min_score < 0.0."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=-0.1,
                project=None,
            )

            assert "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_no_results(self) -> None:
        """Should handle no search results gracefully."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_quick_search_tools_not_available(self) -> None:
        """Should return error when tools not available."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=0.7,
                project=None,
            )

            assert "Reflection tools not available" in result
            assert "uv sync --extra embeddings" in result

    @pytest.mark.asyncio
    async def test_quick_search_database_connection_fails(self) -> None:
        """Should handle database connection failure."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            side_effect=Exception("Database connection lost")
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=0.7,
                project=None,
            )

            assert "Failed to perform quick search" in result
            assert "Database connection lost" in result

    @pytest.mark.asyncio
    async def test_quick_search_result_content_truncated(self) -> None:
        """Should truncate long content in results."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
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
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _quick_search_validated_impl(
                query="test",
                min_score=0.7,
                project=None,
            )

            assert "..." in result
            assert long_content not in result


class TestSearchByFileValidatedImpl:
    """Tests for _search_by_file_validated_impl function."""

    @pytest.mark.asyncio
    async def test_search_by_file_valid_path(self) -> None:
        """Should search by file path successfully."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Discussed src/main.py changes",
                    "project": "test",
                    "score": 0.88,
                    "timestamp": "2025-01-06",
                },
            ]
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
            assert "Discussed src/main.py changes" in result

    @pytest.mark.asyncio
    async def test_search_by_file_empty_path_fails_validation(self) -> None:
        """Should return validation error for empty file path."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_search_by_file_whitespace_path_fails_validation(self) -> None:
        """Should return validation error for whitespace-only path."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_file_validated_impl(
                file_path="   ",
                limit=10,
                project=None,
            )

            assert "Parameter validation error" in result

    @pytest.mark.asyncio
    async def test_search_by_file_limit_zero_fails_validation(self) -> None:
        """Should return validation error when limit is 0."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_file_validated_impl(
                file_path="test.py",
                limit=0,
                project=None,
            )

            assert "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_limit_exceeds_max_fails_validation(self) -> None:
        """Should return validation error when limit exceeds 1000."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_file_validated_impl(
                file_path="test.py",
                limit=1001,
                project=None,
            )

            assert "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_no_results(self) -> None:
        """Should handle no results gracefully."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_search_by_file_tools_not_available(self) -> None:
        """Should return error when tools not available."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _search_by_file_validated_impl(
                file_path="test.py",
                limit=10,
                project=None,
            )

            assert "Reflection tools not available" in result
            assert "uv sync --extra embeddings" in result

    @pytest.mark.asyncio
    async def test_search_by_file_database_connection_fails(self) -> None:
        """Should handle database connection failure."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            side_effect=Exception("Connection lost")
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_file_validated_impl(
                file_path="test.py",
                limit=10,
                project=None,
            )

            assert "Failed to perform file search" in result


class TestSearchByConceptValidatedImpl:
    """Tests for _search_by_concept_validated_impl function."""

    @pytest.mark.asyncio
    async def test_search_by_concept_valid_concept(self) -> None:
        """Should search by concept successfully."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Discussion about async patterns",
                    "project": "test",
                    "score": 0.92,
                    "timestamp": "2025-01-06",
                    "files": ["src/async.py", "src/main.py"],
                },
            ]
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_search_by_concept_empty_concept_fails_validation(self) -> None:
        """Should return validation error for empty concept."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_search_by_concept_whitespace_concept_fails_validation(self) -> None:
        """Should return validation error for whitespace-only concept."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_concept_validated_impl(
                concept="   ",
                include_files=True,
                limit=10,
                project=None,
            )

            assert "Parameter validation error" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_no_results(self) -> None:
        """Should handle no results gracefully."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
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
    async def test_search_by_concept_tools_not_available(self) -> None:
        """Should return error when tools not available."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            result = await _search_by_concept_validated_impl(
                concept="test",
                include_files=True,
                limit=10,
                project=None,
            )

            assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_database_connection_fails(self) -> None:
        """Should handle database connection failure."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            side_effect=Exception("Connection lost")
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_concept_validated_impl(
                concept="test",
                include_files=True,
                limit=10,
                project=None,
            )

            assert "Failed to perform concept search" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_include_files_false(self) -> None:
        """Should not include files when include_files is False."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "content": "Concept discussion",
                    "project": "test",
                    "score": 0.9,
                    "timestamp": "2025-01-06",
                    "files": ["file1.py", "file2.py"],
                },
            ]
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_concept_validated_impl(
                concept="test",
                include_files=False,
                limit=10,
                project=None,
            )

            # Files should not appear in output when include_files=False
            assert "file1.py" not in result


# =============================================================================
# Test Classes for Helper Functions
# =============================================================================


class TestFormatHelpers:
    """Tests for formatting helper functions."""

    def test_format_result_item_basic(self) -> None:
        """Should format basic result item."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_result_item,
        )

        result_data = {
            "content": "Test conversation content",
            "project": "test-project",
            "score": 0.95,
            "timestamp": "2025-01-06",
        }

        lines = _format_result_item(result_data, 1)

        assert isinstance(lines, list)
        assert any("Test conversation content" in line for line in lines)
        assert any("test-project" in line for line in lines)
        assert any("0.95" in line for line in lines)
        assert any("2025-01-06" in line for line in lines)

    def test_format_result_item_missing_optional_fields(self) -> None:
        """Should format result item with missing optional fields."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_result_item,
        )

        result_data = {"content": "Minimal content"}

        lines = _format_result_item(result_data, 1)

        assert isinstance(lines, list)
        assert any("Minimal content" in line for line in lines)
        # Should only have the content line since other fields are missing
        assert len(lines) == 1

    def test_format_result_item_truncates_long_content(self) -> None:
        """Should truncate content over 200 characters."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_result_item,
        )

        long_content = "x" * 250
        result_data = {
            "content": long_content,
            "project": "test",
        }

        lines = _format_result_item(result_data, 1)
        result_text = "\n".join(lines)

        assert "..." in result_text
        assert long_content not in result_text

    def test_format_search_results_with_results(self) -> None:
        """Should format search results with results."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_search_results,
        )

        results = [
            {"content": "Result 1", "score": 0.9, "timestamp": "2025-01-06"},
            {"content": "Result 2", "score": 0.8, "timestamp": "2025-01-05"},
        ]

        lines = _format_search_results(results)
        result_text = "\n".join(lines)

        assert "Found 2 relevant conversations:" in result_text
        assert "Result 1" in result_text
        assert "Result 2" in result_text

    def test_format_search_results_empty(self) -> None:
        """Should format empty search results."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_search_results,
        )

        lines = _format_search_results([])
        result_text = "\n".join(lines)

        assert "No conversations found about this file" in result_text
        assert "not have been discussed" in result_text

    def test_format_concept_results_with_results_and_files(self) -> None:
        """Should format concept results including files."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_concept_results,
        )

        results = [
            {
                "content": "Concept discussion",
                "project": "test",
                "score": 0.9,
                "timestamp": "2025-01-06",
                "files": ["file1.py", "file2.py", "file3.py"],
            },
        ]

        lines = _format_concept_results(results, include_files=True)
        result_text = "\n".join(lines)

        assert "Found 1 related conversations:" in result_text
        assert "file1.py" in result_text

    def test_format_concept_results_with_results_no_files(self) -> None:
        """Should format concept results without files when include_files=False."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_concept_results,
        )

        results = [
            {
                "content": "Concept discussion",
                "project": "test",
                "score": 0.9,
                "timestamp": "2025-01-06",
                "files": ["file1.py"],
            },
        ]

        lines = _format_concept_results(results, include_files=False)
        result_text = "\n".join(lines)

        assert "file1.py" not in result_text

    def test_format_concept_results_empty(self) -> None:
        """Should format empty concept results."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_concept_results,
        )

        lines = _format_concept_results([], include_files=True)
        result_text = "\n".join(lines)

        assert "No conversations found about this concept" in result_text
        assert "Try related terms" in result_text


class TestFormatFileSearchHelpers:
    """Tests for file search formatting helper functions."""

    def test_format_file_search_header(self) -> None:
        """Should format file search header."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_file_search_header,
        )

        lines = _format_file_search_header("src/main.py")

        assert isinstance(lines, list)
        assert "Searching conversations about: src/main.py" in lines[0]
        assert "=" * 50 in lines[1]

    def test_format_file_search_result_with_all_fields(self) -> None:
        """Should format file search result with all fields."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_file_search_result,
        )

        result_data = {
            "content": "File discussion content",
            "timestamp": "2025-01-06",
            "project": "test-project",
            "score": 0.88,
        }

        lines = _format_file_search_result(result_data, 1)
        result_text = "\n".join(lines)

        assert "File discussion content" in result_text
        assert "2025-01-06" in result_text
        assert "test-project" in result_text
        assert "0.88" in result_text

    def test_format_file_search_result_missing_fields(self) -> None:
        """Should format file search result with missing fields."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_file_search_result,
        )

        result_data = {"content": "Minimal content"}

        lines = _format_file_search_result(result_data, 1)
        result_text = "\n".join(lines)

        assert "Minimal content" in result_text

    def test_format_file_search_result_truncates_long_content(self) -> None:
        """Should truncate content over 200 characters."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_file_search_result,
        )

        long_content = "x" * 250
        result_data = {"content": long_content}

        lines = _format_file_search_result(result_data, 1)
        result_text = "\n".join(lines)

        assert "..." in result_text
        assert long_content not in result_text

    def test_format_file_search_results_with_multiple_results(self) -> None:
        """Should format multiple file search results."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_file_search_results,
        )

        results = [
            {
                "content": "Result 1",
                "score": 0.9,
                "timestamp": "2025-01-06",
            },
            {
                "content": "Result 2",
                "score": 0.8,
                "timestamp": "2025-01-05",
            },
        ]

        lines = _format_file_search_results(results, "test.py")
        result_text = "\n".join(lines)

        assert "Searching conversations about: test.py" in result_text
        assert "Found 2 relevant conversations:" in result_text
        assert "Result 1" in result_text
        assert "Result 2" in result_text

    def test_format_file_search_results_empty(self) -> None:
        """Should format empty file search results."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_file_search_results,
        )

        lines = _format_file_search_results([], "unknown.py")
        result_text = "\n".join(lines)

        assert "No conversations found about this file" in result_text
        assert "not have been discussed" in result_text


class TestFormatTopResultHelper:
    """Tests for _format_top_result helper function."""

    def test_format_top_result_with_all_fields(self) -> None:
        """Should format top result with all fields."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_top_result,
        )

        result = {
            "content": "Top result content",
            "project": "test-project",
            "score": 0.95,
            "timestamp": "2025-01-06",
        }

        lines = _format_top_result(result)

        result_text = "\n".join(lines)
        assert "Top result content" in result_text
        assert "test-project" in result_text
        assert "0.95" in result_text

    def test_format_top_result_missing_optional_fields(self) -> None:
        """Should format top result with missing optional fields."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_top_result,
        )

        result = {"content": "Minimal content"}

        lines = _format_top_result(result)

        assert isinstance(lines, list)
        assert any("Minimal content" in line for line in lines)


class TestFormatReflectionResultHelper:
    """Tests for _format_reflection_result helper function."""

    def test_format_reflection_result_with_tags(self) -> None:
        """Should format reflection result with tags."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_reflection_result,
        )

        result = {
            "id": "ref_123",
            "content": "Reflection content here",
            "tags": ["python", "async"],
            "timestamp": "2025-01-06T10:00:00",
        }

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._get_logger"
        ) as mock_logger:
            result_text = _format_reflection_result(result)

            assert "Reflection stored successfully!" in result_text
            assert "ref_123" in result_text
            assert "python, async" in result_text
            mock_logger().info.assert_called_once()

    def test_format_reflection_result_without_tags(self) -> None:
        """Should format reflection result without tags."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_reflection_result,
        )

        result = {
            "id": "ref_456",
            "content": "Reflection content here",
            "tags": [],
            "timestamp": "2025-01-06T10:00:00",
        }

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._get_logger"
        ) as mock_logger:
            result_text = _format_reflection_result(result)

            assert "ref_456" in result_text
            assert "Tags:" not in result_text


class TestFormatConceptResultHelper:
    """Tests for _format_validated_concept_result helper function."""

    def test_format_validated_concept_result_with_files(self) -> None:
        """Should format concept result including files."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_validated_concept_result,
        )

        result = {
            "content": "Concept content",
            "timestamp": "2025-01-06",
            "project": "test",
            "score": 0.88,
            "files": ["file1.py", "file2.py", "file3.py", "file4.py", "file5.py", "file6.py"],
        }

        lines = _format_validated_concept_result(result, 1, include_files=True)
        result_text = "\n".join(lines)

        assert "Concept content" in result_text
        assert "file1.py" in result_text
        # Should limit to 5 files
        assert "file6.py" not in result_text

    def test_format_validated_concept_result_without_files(self) -> None:
        """Should format concept result excluding files."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _format_validated_concept_result,
        )

        result = {
            "content": "Concept content",
            "files": ["file1.py"],
        }

        lines = _format_validated_concept_result(result, 1, include_files=False)
        result_text = "\n".join(lines)

        assert "file1.py" not in result_text


# =============================================================================
# Test Classes for Validation Functions
# =============================================================================


class TestValidateReflectionParams:
    """Tests for _validate_reflection_params function."""

    def test_validate_reflection_params_valid(self) -> None:
        """Should return validated params for valid input."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _validate_reflection_params,
        )

        result = _validate_reflection_params(
            content="Valid content",
            tags=["test"],
        )

        assert not isinstance(result, str)
        assert result.content == "Valid content"
        assert result.tags == ["test"]

    def test_validate_reflection_params_empty_content(self) -> None:
        """Should return error string for empty content."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _validate_reflection_params,
        )

        result = _validate_reflection_params(content="", tags=None)

        assert isinstance(result, str)
        assert "Parameter validation error" in result

    def test_validate_reflection_params_invalid_tags(self) -> None:
        """Should return error string for invalid tags."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _validate_reflection_params,
        )

        result = _validate_reflection_params(
            content="Valid content",
            tags=["invalid tag with spaces"],
        )

        assert isinstance(result, str)
        assert "validation" in result.lower()


# =============================================================================
# Test Classes for Database Resolution Functions
# =============================================================================


class TestReflectionToolsAvailability:
    """Tests for _check_reflection_tools_available function."""

    def test_check_reflection_tools_available_when_installed(self) -> None:
        """Should return True when reflection tools are installed."""
        import session_buddy.mcp.tools.memory.validated_memory_tools as module

        module._reflection_tools_available = None

        with patch(
            "importlib.util.find_spec",
            return_value=MagicMock(),
        ):
            result = module._check_reflection_tools_available()
            assert result is True

    def test_check_reflection_tools_available_when_not_installed(self) -> None:
        """Should return False when reflection tools not installed."""
        import session_buddy.mcp.tools.memory.validated_memory_tools as module

        module._reflection_tools_available = None

        with patch(
            "importlib.util.find_spec",
            return_value=None,
        ):
            result = module._check_reflection_tools_available()
            assert result is False

    def test_check_reflection_tools_available_uses_cache(self) -> None:
        """Should use cached result on subsequent calls."""
        import session_buddy.mcp.tools.memory.validated_memory_tools as module

        module._reflection_tools_available = True

        with patch(
            "importlib.util.find_spec"
        ) as mock_spec:
            result = module._check_reflection_tools_available()
            assert result is True
            mock_spec.assert_not_called()

    def test_check_reflection_tools_available_handles_exception(self) -> None:
        """Should return False when exception occurs during check."""
        import session_buddy.mcp.tools.memory.validated_memory_tools as module

        module._reflection_tools_available = None

        with patch(
            "importlib.util.find_spec",
            side_effect=Exception("Test exception"),
        ):
            result = module._check_reflection_tools_available()
            assert result is False


class TestResolveReflectionDatabase:
    """Tests for resolve_reflection_database function."""

    @pytest.mark.asyncio
    async def test_resolve_from_di_container(self) -> None:
        """Should resolve database from DI container."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            resolve_reflection_database,
        )

        mock_db = MagicMock()
        mock_depends = MagicMock()
        mock_depends.get_sync.return_value = mock_db

        with patch(
            "session_buddy.di.container.depends",
            mock_depends,
        ):
            result = await resolve_reflection_database()

            assert result == mock_db

    @pytest.mark.asyncio
    async def test_resolve_from_fallback_function(self) -> None:
        """Should resolve database from fallback function."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            resolve_reflection_database,
        )

        mock_db = AsyncMock()

        mock_depends = MagicMock()
        mock_depends.get_sync.side_effect = Exception("DI not available")

        with patch(
            "session_buddy.di.container.depends",
            mock_depends,
        ):
            with patch(
                "session_buddy.reflection_tools.get_reflection_database",
                return_value=mock_db,
            ):
                result = await resolve_reflection_database()

                assert result == mock_db

    @pytest.mark.asyncio
    async def test_resolve_returns_none_when_unavailable(self) -> None:
        """Should return None when database is unavailable."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            resolve_reflection_database,
        )

        mock_depends = MagicMock()
        mock_depends.get_sync.side_effect = Exception("DI not available")

        with patch(
            "session_buddy.di.container.depends",
            mock_depends,
        ):
            with patch(
                "session_buddy.reflection_tools.get_reflection_database",
                side_effect=Exception("DB not available"),
            ):
                result = await resolve_reflection_database()

                assert result is None


class TestGetReflectionDatabaseAsync:
    """Tests for _get_reflection_database_async function."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_async_success(self) -> None:
        """Should return database when successful."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _get_reflection_database_async,
        )

        mock_db = AsyncMock()

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools.resolve_reflection_database",
                return_value=mock_db,
            ),
        ):
            result = await _get_reflection_database_async()
            assert result == mock_db

    @pytest.mark.asyncio
    async def test_get_reflection_database_async_not_available(self) -> None:
        """Should raise ImportError when tools not available."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _get_reflection_database_async,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=False,
        ):
            with pytest.raises(ImportError, match="Reflection tools not available"):
                await _get_reflection_database_async()

    @pytest.mark.asyncio
    async def test_get_reflection_database_async_resolve_returns_none(self) -> None:
        """Should raise ImportError when resolve returns None."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _get_reflection_database_async,
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools.resolve_reflection_database",
                return_value=None,
            ),
        ):
            with pytest.raises(ImportError, match="Reflection tools not available"):
                await _get_reflection_database_async()

    @pytest.mark.asyncio
    async def test_get_reflection_database_async_handles_exception(self) -> None:
        """Should raise ImportError when exception occurs."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _get_reflection_database_async,
        )

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools.resolve_reflection_database",
                side_effect=Exception("Unexpected error"),
            ),
        ):
            with pytest.raises(ImportError, match="Reflection tools not available"):
                await _get_reflection_database_async()


# =============================================================================
# Test Classes for Placeholder Classes
# =============================================================================


class TestValidationExamples:
    """Tests for ValidationExamples class."""

    def test_example_valid_calls(self) -> None:
        """Should return valid call examples."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            ValidationExamples,
        )

        examples = ValidationExamples().example_valid_calls()

        assert isinstance(examples, list)
        assert len(examples) > 0
        assert "query" in examples[0]

    def test_example_validation_errors(self) -> None:
        """Should return validation error examples."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            ValidationExamples,
        )

        examples = ValidationExamples().example_validation_errors()

        assert isinstance(examples, list)
        assert len(examples) > 0
        assert "field" in examples[0]
        assert "error" in examples[0]


class TestMigrationGuide:
    """Tests for MigrationGuide class."""

    def test_before_migration(self) -> None:
        """Should return before migration instructions."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            MigrationGuide,
        )

        result = MigrationGuide.before_migration()

        assert isinstance(result, str)
        assert "backup" in result.lower()

    def test_after_migration(self) -> None:
        """Should return after migration instructions."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            MigrationGuide,
        )

        result = MigrationGuide.after_migration()

        assert isinstance(result, str)
        assert "verify" in result.lower()


# =============================================================================
# Test Classes for Execute and Register Functions
# =============================================================================


class TestExecuteStoreReflection:
    """Tests for _execute_store_reflection function."""

    @pytest.mark.asyncio
    async def test_execute_store_reflection_success(self) -> None:
        """Should execute store reflection successfully."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _execute_store_reflection,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_new")

        params = MagicMock()
        params.content = "Test content"
        params.tags = ["test"]

        result = await _execute_store_reflection(params, mock_db)

        assert result["success"] is True
        assert result["id"] == "ref_new"
        assert result["content"] == "Test content"
        assert result["tags"] == ["test"]
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_execute_store_reflection_with_none_tags(self) -> None:
        """Should handle None tags by converting to empty list."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _execute_store_reflection,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_none")

        params = MagicMock()
        params.content = "Test content"
        params.tags = None

        result = await _execute_store_reflection(params, mock_db)

        assert result["success"] is True
        assert result["tags"] == []

    @pytest.mark.asyncio
    async def test_execute_store_reflection_returns_false_id(self) -> None:
        """Should return success=False when store_reflection returns False."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _execute_store_reflection,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=False)

        params = MagicMock()
        params.content = "Test content"
        params.tags = []

        result = await _execute_store_reflection(params, mock_db)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_store_reflection_returns_none_id(self) -> None:
        """Should return success=False when store_reflection returns None."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _execute_store_reflection,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=None)

        params = MagicMock()
        params.content = "Test content"
        params.tags = []

        result = await _execute_store_reflection(params, mock_db)

        assert result["success"] is False


class TestRegisterValidatedMemoryTools:
    """Tests for register_validated_memory_tools function."""

    def test_register_validated_memory_tools(self) -> None:
        """Should register all validated memory tools."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            register_validated_memory_tools,
        )

        mock_server = MagicMock()

        register_validated_memory_tools(mock_server)

        # Verify that tool decorator was called 4 times (one for each tool)
        assert mock_server.tool.call_count == 4

    def test_register_does_not_raise(self) -> None:
        """Should not raise any exceptions during registration."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            register_validated_memory_tools,
        )

        mock_server = MagicMock()

        # Should not raise
        register_validated_memory_tools(mock_server)


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_store_reflection_special_characters_in_content(self) -> None:
        """Should handle special characters in content."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_special")

        special_content = "Content with émojis 🎉 and unicode ñ and symbols @#$%"

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content=special_content,
                tags=None,
            )

            assert "Reflection stored successfully!" in result

    @pytest.mark.asyncio
    async def test_store_reflection_very_long_tags_list(self) -> None:
        """Should handle long list of tags."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _store_reflection_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="ref_tags")

        many_tags = [f"tag{i}" for i in range(20)]

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _store_reflection_validated_impl(
                content="Content with many tags",
                tags=many_tags,
            )

            assert "Reflection stored successfully!" in result

    @pytest.mark.asyncio
    async def test_quick_search_with_extremal_scores(self) -> None:
        """Should handle min_score at boundaries 0.0 and 1.0."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _quick_search_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            # Test min_score = 0.0
            result = await _quick_search_validated_impl(
                query="test",
                min_score=0.0,
                project=None,
            )

            assert "validation" not in result.lower() or "validation error" not in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_special_path_characters(self) -> None:
        """Should handle special characters in file paths."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_file_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        special_paths = [
            "path/with spaces/main.py",
            "path/with-dashes/file.py",
            "path/with_underscores/test.py",
        ]

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            for path in special_paths:
                result = await _search_by_file_validated_impl(
                    file_path=path,
                    limit=10,
                    project=None,
                )

                # Should not have validation errors for these paths
                # (only "path with spaces" might fail depending on validation)
                if " " not in path:
                    assert "Parameter validation error" not in result

    @pytest.mark.asyncio
    async def test_search_by_concept_max_length_concept(self) -> None:
        """Should handle concept at max length boundary."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        # Concept at exactly max length (200)
        max_concept = "a" * 200

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
                return_value=True,
            ),
        ):
            result = await _search_by_concept_validated_impl(
                concept=max_concept,
                include_files=True,
                limit=10,
                project=None,
            )

            assert "validation" not in result.lower() or "validation error" not in result

    @pytest.mark.asyncio
    async def test_search_by_concept_exceeds_max_length_fails(self) -> None:
        """Should fail validation when concept exceeds max length."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _search_by_concept_validated_impl,
        )

        mock_db = AsyncMock()
        mock_db.search_reflections = AsyncMock(return_value=[])

        # Concept exceeds max length (200)
        long_concept = "a" * 201

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._check_reflection_tools_available",
            return_value=True,
        ):
            result = await _search_by_concept_validated_impl(
                concept=long_concept,
                include_files=True,
                limit=10,
                project=None,
            )

            assert "validation" in result.lower()


class TestGetReflectionDatabaseSync:
    """Tests for _get_reflection_database function (sync wrapper)."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_sync_wrapper(self) -> None:
        """Should wrap async function correctly."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _get_reflection_database,
        )

        mock_db = AsyncMock()

        with (
            patch(
                "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
                return_value=mock_db,
            ),
        ):
            result = await _get_reflection_database()
            assert result == mock_db

    @pytest.mark.asyncio
    async def test_get_reflection_database_sync_raises_import_error(self) -> None:
        """Should propagate ImportError from async wrapper."""
        from session_buddy.mcp.tools.memory.validated_memory_tools import (
            _get_reflection_database,
        )

        with patch(
            "session_buddy.mcp.tools.memory.validated_memory_tools._get_reflection_database_async",
            side_effect=ImportError("Reflection tools not available"),
        ):
            with pytest.raises(ImportError, match="Reflection tools not available"):
                await _get_reflection_database()