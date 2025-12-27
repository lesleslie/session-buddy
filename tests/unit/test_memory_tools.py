#!/usr/bin/env python3
"""Unit tests for memory tools.

Tests the MCP tools for storing, searching, and managing reflections and conversation memories.

Phase: Week 1 Day 2 - Quick Win Coverage (84% → 90%+)
"""

from unittest.mock import AsyncMock, patch

import pytest
from session_buddy.tools.memory_tools import (
    _format_new_stats,
    _format_old_stats,
    _format_stats_new,
    _format_stats_old,
    _quick_search_impl,
    _reflection_stats_impl,
    _reset_reflection_database_impl,
    _search_by_concept_impl,
    _search_by_file_impl,
    _search_summary_impl,
    _store_reflection_impl,
)


class TestStoreReflectionImpl:
    """Test store reflection implementation."""

    @pytest.mark.asyncio
    async def test_store_reflection_when_tools_unavailable(self):
        """Test storing reflection when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _store_reflection_impl("Test content")
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_store_reflection_success(self):
        """Test successful reflection storage."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database and its store_reflection method
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="test-id-123")

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _store_reflection_impl("Test content", ["tag1", "tag2"])

            assert "Reflection stored successfully" in result
            assert "Test content" in result
            assert "tag1, tag2" in result
            mock_db.store_reflection.assert_called_once_with(
                "Test content", tags=["tag1", "tag2"]
            )

    @pytest.mark.asyncio
    async def test_store_reflection_failure(self):
        """Test reflection storage failure."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(side_effect=Exception("Database error"))

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _store_reflection_impl("Test content")

            assert "Error storing reflection" in result
            assert "Database error" in result

    @pytest.mark.asyncio
    async def test_store_reflection_without_tags(self):
        """Test storing reflection without tags."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value="test-id-456")

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _store_reflection_impl("Test content without tags")

            assert "Reflection stored successfully" in result
            assert "Test content without tags" in result
            mock_db.store_reflection.assert_called_once_with(
                "Test content without tags", tags=[]
            )


class TestQuickSearchImpl:
    """Test quick search implementation."""

    @pytest.mark.asyncio
    async def test_quick_search_when_tools_unavailable(self):
        """Test quick search when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _quick_search_impl("test query")
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_quick_search_with_results(self):
        """Test quick search with results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database and search results
        mock_db = AsyncMock()
        mock_results = [
            {
                "content": "Test result content",
                "project": "test-project",
                "score": 0.85,
                "timestamp": "2023-01-01T12:00:00Z",
            }
        ]
        mock_db.search_conversations = AsyncMock(return_value=mock_results)

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _quick_search_impl("test query", min_score=0.7)

            assert "Quick search for: 'test query'" in result
            assert "Test result content" in result
            assert "test-project" in result
            assert "0.85" in result
            mock_db.search_conversations.assert_called_once_with(
                query="test query", project=None, limit=1, min_score=0.7
            )

    @pytest.mark.asyncio
    async def test_quick_search_no_results(self):
        """Test quick search with no results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database with no results
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _quick_search_impl("nonexistent query")

            assert "No results found" in result
            assert "nonexistent query" in result

    @pytest.mark.asyncio
    async def test_quick_search_with_exception(self):
        """Test quick search with exception."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _quick_search_impl("test query")

            assert "Search error" in result


class TestSearchSummaryImpl:
    """Test search summary implementation."""

    @pytest.mark.asyncio
    async def test_search_summary_when_tools_unavailable(self):
        """Test search summary when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _search_summary_impl("test query")
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_search_summary_with_results(self):
        """Test search summary with results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database and search results
        mock_db = AsyncMock()
        mock_results = [
            {
                "content": "Result 1 content",
                "project": "project-a",
                "score": 0.9,
                "timestamp": "2023-01-01T12:00:00Z",
            },
            {
                "content": "Result 2 content",
                "project": "project-b",
                "score": 0.8,
                "timestamp": "2023-01-02T12:00:00Z",
            },
            {
                "content": "Result 3 content",
                "project": "project-a",
                "score": 0.75,
                "timestamp": "2023-01-03T12:00:00Z",
            },
        ]
        mock_db.search_conversations = AsyncMock(return_value=mock_results)

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_summary_impl("test query")

            assert "Search Summary for: 'test query'" in result
            assert "Total results: 3" in result
            assert "project-a" in result
            assert "project-b" in result
            mock_db.search_conversations.assert_called_once_with(
                query="test query", project=None, limit=20, min_score=0.7
            )

    @pytest.mark.asyncio
    async def test_search_summary_no_results(self):
        """Test search summary with no results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database with no results
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_summary_impl("nonexistent query")

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_search_summary_with_exception(self):
        """Test search summary with exception."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_summary_impl("test query")

            assert "Search summary error" in result


class TestSearchByFileImpl:
    """Test search by file implementation."""

    @pytest.mark.asyncio
    async def test_search_by_file_when_tools_unavailable(self):
        """Test search by file when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _search_by_file_impl("test_file.py")
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_search_by_file_with_results(self):
        """Test search by file with results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database and search results
        mock_db = AsyncMock()
        mock_results = [
            {
                "content": "Discussion about test_file.py implementation",
                "project": "test-project",
                "score": 0.85,
                "timestamp": "2023-01-01T12:00:00Z",
            }
        ]
        mock_db.search_conversations = AsyncMock(return_value=mock_results)

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_by_file_impl("test_file.py", limit=5)

            assert "Searching conversations about: test_file.py" in result
            assert "Found 1 relevant conversations" in result
            assert "test_file.py" in result
            mock_db.search_conversations.assert_called_once_with(
                query="test_file.py", project=None, limit=5
            )

    @pytest.mark.asyncio
    async def test_search_by_file_no_results(self):
        """Test search by file with no results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database with no results
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_by_file_impl("nonexistent.py")

            assert "No conversations found about this file" in result

    @pytest.mark.asyncio
    async def test_search_by_file_with_exception(self):
        """Test search by file with exception."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_by_file_impl("test_file.py")

            assert "File search error" in result


class TestSearchByConceptImpl:
    """Test search by concept implementation."""

    @pytest.mark.asyncio
    async def test_search_by_concept_when_tools_unavailable(self):
        """Test search by concept when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _search_by_concept_impl("authentication")
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_with_results(self):
        """Test search by concept with results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database and search results
        mock_db = AsyncMock()
        mock_results = [
            {
                "content": "Discussion about authentication patterns",
                "project": "auth-service",
                "score": 0.9,
                "timestamp": "2023-01-01T12:00:00Z",
            }
        ]
        mock_db.search_conversations = AsyncMock(return_value=mock_results)

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_by_concept_impl("authentication", limit=5)

            assert "Searching for concept: 'authentication'" in result
            assert "Found 1 related conversations" in result
            assert "authentication" in result
            mock_db.search_conversations.assert_called_once_with(
                query="authentication", project=None, limit=5
            )

    @pytest.mark.asyncio
    async def test_search_by_concept_no_results(self):
        """Test search by concept with no results."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database with no results
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_by_concept_impl("nonexistent_concept")

            assert "No conversations found about this concept" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_with_exception(self):
        """Test search by concept with exception."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _search_by_concept_impl("authentication")

            assert "Concept search error" in result


class TestReflectionStatsImpl:
    """Test reflection stats implementation."""

    @pytest.mark.asyncio
    async def test_reflection_stats_when_tools_unavailable(self):
        """Test reflection stats when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _reflection_stats_impl()
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_reflection_stats_success(self):
        """Test successful reflection stats retrieval."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database and stats
        mock_db = AsyncMock()
        # Use the format from the actual get_stats() method in reflection_tools.py
        mock_stats = {
            "conversations_count": 42,
            "reflections_count": 35,
            "embedding_provider": "onnx-runtime",
            "embedding_dimension": 384,
            "database_path": "/tmp/test.db",
        }
        mock_db.get_stats = AsyncMock(return_value=mock_stats)

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _reflection_stats_impl()

            assert "Reflection Database Statistics" in result
            assert "conversations" in result.lower() or "reflections" in result.lower()
            mock_db.get_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_reflection_stats_with_exception(self):
        """Test reflection stats with exception."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(side_effect=Exception("Stats error"))

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _reflection_stats_impl()

            assert "Stats error" in result or "error" in result.lower()


class TestResetReflectionDatabaseImpl:
    """Test reset reflection database implementation."""

    @pytest.mark.asyncio
    async def test_reset_reflection_database_when_tools_unavailable(self):
        """Test reset reflection database when tools are unavailable."""
        # Set the global state to False
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = False

        result = await _reset_reflection_database_impl()
        assert "Reflection tools not available" in result

    @pytest.mark.asyncio
    async def test_reset_reflection_database_success(self):
        """Test successful reflection database reset."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database connection
        mock_db = AsyncMock()
        mock_db.conn = AsyncMock()
        mock_db.conn.close = AsyncMock()

        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            # Set up the global database instance
            from session_buddy.tools import memory_tools

            memory_tools._reflection_db = mock_db

            result = await _reset_reflection_database_impl()

            assert "Reflection database connection reset" in result
            assert "New connection established successfully" in result
            # Verify the old connection was closed
            mock_db.conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_reflection_database_with_exception(self):
        """Test reflection database reset with exception."""
        # Set the global state to True
        from session_buddy.tools import memory_tools

        memory_tools._reflection_tools_available = True

        # Mock the database to raise an exception
        with patch(
            "session_buddy.tools.memory_tools._get_reflection_database",
            side_effect=Exception("Reset error"),
        ):
            result = await _reset_reflection_database_impl()

            assert "Reset error" in result


class TestFormatNewStats:
    """Test _format_stats_new helper function for V2 stats format.

    Phase: Week 1 Day 2 - Quick Win Coverage (84% → 90%)
    """

    def test_format_stats_new_with_complete_data(self):
        """Should format complete stats with all fields."""
        stats = {
            "conversations_count": 150,
            "reflections_count": 75,
            "embedding_provider": "onnx-local",
        }

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert len(result) == 4
        assert "150" in result[0]  # conversations_count
        assert "75" in result[1]  # reflections_count
        assert "onnx-local" in result[2]  # embedding_provider
        assert "✅ Healthy" in result[3]  # Database health (has data)

    def test_format_stats_new_with_zero_counts(self):
        """Should indicate empty database for zero counts."""
        stats = {
            "conversations_count": 0,
            "reflections_count": 0,
            "embedding_provider": "unknown",
        }

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert "0" in result[0]  # conversations_count
        assert "0" in result[1]  # reflections_count
        assert "⚠️ Empty" in result[3]  # Database health warning

    def test_format_stats_new_with_missing_fields(self):
        """Should handle missing optional fields gracefully."""
        stats = {}  # Empty dict

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert "0" in result[0]  # Default conversations_count
        assert "0" in result[1]  # Default reflections_count
        assert "unknown" in result[2]  # Default embedding_provider
        assert "⚠️ Empty" in result[3]  # Empty database

    def test_format_stats_new_with_partial_data(self):
        """Should use defaults for missing fields."""
        stats = {
            "conversations_count": 50,
            # reflections_count missing
            "embedding_provider": "transformers",
        }

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert "50" in result[0]  # conversations_count present
        assert "0" in result[1]  # reflections_count default
        assert "transformers" in result[2]
        assert "✅ Healthy" in result[3]  # Has some data (50 > 0)

    def test_format_stats_new_health_threshold(self):
        """Should show healthy when total count > 0."""
        stats = {
            "conversations_count": 0,
            "reflections_count": 1,  # Just one reflection
            "embedding_provider": "test",
        }

        result = _format_new_stats(stats)

        assert "✅ Healthy" in result[3]  # Total = 1, healthy


class TestFormatOldStats:
    """Test _format_old_stats helper function for legacy stats format.

    Phase: Week 1 Day 2 - Quick Win Coverage (84% → 90%)
    """

    def test_format_old_stats_with_complete_data(self):
        """Should format complete old-style stats."""
        stats = {
            "total_reflections": 100,
            "projects": 5,
            "date_range": {
                "start": "2025-01-01",
                "end": "2025-01-15",
            },
            "recent_activity": [
                "Activity 1",
                "Activity 2",
                "Activity 3",
                "Activity 4",
                "Activity 5",
                "Activity 6",  # Should be truncated to 5
            ],
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        # Check total reflections
        assert any("100" in line for line in result)
        # Check projects count
        assert any("5" in line for line in result)
        # Check date range formatted
        assert any("2025-01-01" in line and "2025-01-15" in line for line in result)
        # Check recent activity (max 5 items)
        activity_section = [line for line in result if "Activity" in line]
        assert len(activity_section) == 5  # Limited to 5 items
        # Check healthy status
        assert any("✅ Healthy" in line for line in result)

    def test_format_old_stats_with_zero_reflections(self):
        """Should show empty database warning for zero reflections."""
        stats = {
            "total_reflections": 0,
            "projects": 0,
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        assert any("0" in line for line in result)
        assert any("⚠️ Empty" in line for line in result)

    def test_format_old_stats_with_missing_date_range(self):
        """Should handle missing date_range gracefully."""
        stats = {
            "total_reflections": 50,
            "projects": 3,
            # date_range missing
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        assert any("50" in line for line in result)
        assert any("3" in line for line in result)
        # Should not crash, just skip date range
        assert not any("Date range" in line for line in result)

    def test_format_old_stats_with_empty_recent_activity(self):
        """Should handle empty recent_activity list."""
        stats = {
            "total_reflections": 25,
            "projects": 2,
            "recent_activity": [],
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        # Should not include recent activity section
        assert not any("Recent activity" in line for line in result)

    def test_format_old_stats_with_invalid_date_range_type(self):
        """Should handle non-dict date_range gracefully."""
        stats = {
            "total_reflections": 10,
            "projects": 1,
            "date_range": "invalid",  # Not a dict
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        # Should not crash, just skip invalid date range
        assert not any("Date range" in line for line in result)

    def test_format_old_stats_minimal_data(self):
        """Should work with minimal stats (just total_reflections)."""
        stats = {
            "total_reflections": 1,
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        assert len(result) >= 3  # At least total, projects, health
        assert any("1" in line for line in result)
        assert any("0" in line for line in result)  # Default projects = 0
        assert any("✅ Healthy" in line for line in result)  # 1 reflection = healthy

    def test_format_old_stats_health_threshold(self):
        """Should show healthy when total_reflections > 0."""
        stats = {
            "total_reflections": 1,
            "projects": 1,
        }

        result = _format_old_stats(stats)

        assert any("✅ Healthy" in line for line in result)
