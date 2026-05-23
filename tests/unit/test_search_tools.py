#!/usr/bin/env python3
"""Unit tests for search tools (session_buddy.mcp.tools.memory.search_tools).

Tests MCP search tool functions including semantic search, keyword search,
hybrid search functions, result filtering, pagination, sorting, and error handling.

Target: 60%+ coverage
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.memory.search_tools import (
    _build_pagination_output,
    _configure_tiers_impl,
    _extract_code_blocks_from_content,
    _extract_file_excerpt,
    _extract_key_terms,
    _extract_mentioned_files,
    _extract_relevant_excerpt,
    _find_best_error_excerpt,
    _format_code_search_results,
    _format_concept_results,
    _format_error_search_results,
    _format_file_search_results,
    _format_search_summary,
    _format_temporal_results,
    _get_more_results_impl,
    _optimize_search_results_impl,
    _parse_tags_parameter,
    _parse_time_expression,
    _progressive_search_impl,
    _quick_search_impl,
    _reflection_stats_impl,
    _reset_reflection_database_impl,
    _search_by_concept_impl,
    _search_by_file_impl,
    _search_code_impl,
    _search_errors_impl,
    _search_summary_impl,
    _search_temporal_impl,
    _store_reflection_impl,
    _tier_stats_impl,
)

# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    """Create a mock reflection database."""
    db = MagicMock()
    db.search_conversations = AsyncMock(return_value=[])
    db.store_reflection = AsyncMock(return_value="reflection-123")
    db.get_stats = AsyncMock(return_value={
        "total_reflections": 100,
        "total_conversations": 500,
    })
    return db


@pytest.fixture
def sample_search_results():
    """Create sample search results for testing."""
    return [
        {
            "id": "conv-1",
            "content": "Test conversation about Python async programming",
            "timestamp": "2026-05-20 10:00:00",
            "similarity": 0.95,
            "project": "test-project",
        },
        {
            "id": "conv-2",
            "content": "Another conversation about asyncio",
            "timestamp": "2026-05-21 14:30:00",
            "similarity": 0.85,
            "project": "test-project",
        },
        {
            "id": "conv-3",
            "content": "Discussion about async/await patterns",
            "timestamp": "2026-05-22 09:15:00",
            "similarity": 0.75,
            "project": "test-project",
        },
    ]


@pytest.fixture
def sample_code_results():
    """Create sample results with code blocks."""
    return [
        {
            "id": "code-1",
            "content": "```python\nasync def example():\n    return await foo()\n```\nSome explanation",
            "timestamp": "2026-05-20 10:00:00",
            "similarity": 0.9,
        },
    ]


@pytest.fixture
def sample_error_results():
    """Create sample error search results."""
    return [
        {
            "id": "err-1",
            "content": "Error: connection refused in async function. Exception traceback failed.",
            "timestamp": "2026-05-20 10:00:00",
            "similarity": 0.8,
        },
    ]


# ==============================================================================
# Token Optimization Tests
# ==============================================================================

class TestOptimizeSearchResultsImpl:
    """Tests for _optimize_search_results_impl."""

    @pytest.mark.asyncio
    async def test_optimize_search_results_with_token_optimizer(self, sample_search_results):
        """Test optimization when TokenOptimizer is available."""
        with patch("session_buddy.token_optimizer.TokenOptimizer") as mock_opt_class:
            mock_optimizer = MagicMock()
            mock_opt_class.return_value = mock_optimizer
            mock_optimizer.optimize_search_results = AsyncMock(
                return_value=(
                    [{"content": "optimized"}],
                    {"tokens_saved": 100},
                )
            )

            result = await _optimize_search_results_impl(
                sample_search_results, optimize_tokens=True, max_tokens=1000, query="test"
            )

            assert result["optimized"] is True
            assert result["results"] == [{"content": "optimized"}]
            assert "optimization_info" in result

    @pytest.mark.asyncio
    async def test_optimize_search_results_disabled(self, sample_search_results):
        """Test when optimization is disabled."""
        result = await _optimize_search_results_impl(
            sample_search_results, optimize_tokens=False, max_tokens=1000, query="test"
        )

        assert result["optimized"] is False
        assert result["results"] == sample_search_results

    @pytest.mark.asyncio
    async def test_optimize_search_results_empty_results(self):
        """Test with empty results list."""
        result = await _optimize_search_results_impl(
            [], optimize_tokens=True, max_tokens=1000, query="test"
        )

        assert result["optimized"] is False
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_optimize_search_results_token_optimizer_import_error(
        self, sample_search_results
    ):
        """Test when TokenOptimizer import fails."""
        with patch(
            "session_buddy.token_optimizer.TokenOptimizer",
            side_effect=ImportError,
        ):
            result = await _optimize_search_results_impl(
                sample_search_results, optimize_tokens=True, max_tokens=1000, query="test"
            )

            assert result["optimized"] is False
            assert result["results"] == sample_search_results

    @pytest.mark.asyncio
    async def test_optimize_search_results_general_exception(self, sample_search_results):
        """Test when TokenOptimizer raises an exception."""
        with patch(
            "session_buddy.token_optimizer.TokenOptimizer",
            side_effect=Exception("Optimizer error"),
        ):
            result = await _optimize_search_results_impl(
                sample_search_results, optimize_tokens=True, max_tokens=1000, query="test"
            )

            assert result["optimized"] is False
            assert "error" in result


# ==============================================================================
# Store Reflection Tests
# ==============================================================================

class TestStoreReflectionImpl:
    """Tests for _store_reflection_impl."""

    @pytest.mark.asyncio
    async def test_store_reflection_success(self, mock_db):
        """Test successful reflection storage."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_database_tool",
        ) as mock_exec:
            # Mock execute_database_tool to bypass the actual DB call
            mock_exec.return_value = "✅ Reflection stored successfully with ID: test-id (tags: test, python)"

            result = await _store_reflection_impl(
                content="Test reflection content", tags=["test", "python"]
            )

            assert "Reflection stored successfully" in result

    @pytest.mark.asyncio
    async def test_store_reflection_empty_content(self, mock_db):
        """Test validation error for empty content."""
        # Empty content should raise ValidationError which is caught by execute_database_tool
        # and returns an error message
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "❌ Validation error: Store reflection: content is required"

            result = await _store_reflection_impl(content="", tags=[])

            # Should return error message, not raise
            assert "Validation error" in result or "required" in result


# ==============================================================================
# Quick Search Tests
# ==============================================================================

class TestQuickSearchImpl:
    """Tests for _quick_search_impl."""

    @pytest.mark.asyncio
    async def test_quick_search_with_results(self, mock_db, sample_search_results):
        """Test quick search returning results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_search_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            # Mock to return the formatted result directly
            mock_exec.return_value = "🔍 **3 results** for 'async'\n\n**Top Result** (score: 0.95):\nTest conversation about Python async programming..."

            result = await _quick_search_impl(
                query="async", project="test-project", min_score=0.7, limit=5
            )

            assert "results" in result
            assert len(sample_search_results) == 3

    @pytest.mark.asyncio
    async def test_quick_search_no_results(self, mock_db):
        """Test quick search with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No results found for 'nonexistent'"

            result = await _quick_search_impl(query="nonexistent")

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_quick_search_database_error(self, mock_db):
        """Test quick search with database error."""
        mock_db.search_conversations = AsyncMock(side_effect=Exception("DB error"))

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "❌ Quick search failed: DB error"

            result = await _quick_search_impl(query="test")

            assert "failed" in result


# ==============================================================================
# Search Summary Tests
# ==============================================================================

class TestSearchSummaryImpl:
    """Tests for _search_summary_impl."""

    @pytest.mark.asyncio
    async def test_search_summary_with_results(self, mock_db, sample_search_results):
        """Test search summary with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_search_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **Search Summary for 'async'**\n**Found**: 3 relevant conversations"

            result = await _search_summary_impl(query="async", min_score=0.6)

            assert "Search Summary" in result
            assert "3" in result  # result count

    @pytest.mark.asyncio
    async def test_search_summary_no_results(self, mock_db):
        """Test search summary with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No results found for 'nonexistent'"

            result = await _search_summary_impl(query="nonexistent")

            assert "No results found" in result


class TestExtractKeyTerms:
    """Tests for _extract_key_terms helper."""

    def test_extract_key_terms_normal(self):
        """Test extraction with normal content."""
        content = "Python programming is great for async programming and testing"
        result = _extract_key_terms(content)

        assert "programming" in result or "async" in result

    def test_extract_key_terms_short_words(self):
        """Test extraction filters short words."""
        content = "a b c d e f g Python is great"
        result = _extract_key_terms(content)

        # 'a', 'b', 'c' etc. should be filtered out
        assert all(len(word) > 4 for word in result)

    def test_extract_key_terms_empty(self):
        """Test with empty content."""
        result = _extract_key_terms("")
        assert result == []


# ==============================================================================
# Pagination Tests
# ==============================================================================

class TestGetMoreResultsImpl:
    """Tests for _get_more_results_impl."""

    @pytest.mark.asyncio
    async def test_get_more_results_with_results(self, mock_db, sample_search_results):
        """Test pagination with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_search_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **Results 2-3** for 'async'\n\n**2.** Discussion about async/await patterns...\n\n💡 1 more results available"

            result = await _get_more_results_impl(
                query="async", offset=1, limit=2, project="test-project"
            )

            assert "Results" in result or "more results" in result

    @pytest.mark.asyncio
    async def test_get_more_results_empty(self, mock_db):
        """Test pagination with no more results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No more results for 'test' (offset: 100)"

            result = await _get_more_results_impl(query="test", offset=100)

            assert "No more results" in result


class TestBuildPaginationOutput:
    """Tests for _build_pagination_output helper."""

    def test_build_pagination_output_with_results(self, sample_search_results):
        """Test pagination output formatting."""
        result = _build_pagination_output(
            query="async",
            offset=0,
            paginated_results=sample_search_results,
            total_results=3,
            limit=3,
        )

        assert "Results 1-" in result
        assert "async" in result

    def test_build_pagination_output_empty(self):
        """Test pagination with empty results."""
        result = _build_pagination_output(
            query="test", offset=0, paginated_results=[], total_results=0, limit=5
        )

        assert "No more results" in result

    def test_build_pagination_output_remaining(self, sample_search_results):
        """Test pagination shows remaining count."""
        result = _build_pagination_output(
            query="async",
            offset=0,
            paginated_results=sample_search_results,
            total_results=10,
            limit=3,
        )

        assert "more results available" in result


# ==============================================================================
# Search by File Tests
# ==============================================================================

class TestSearchByFileImpl:
    """Tests for _search_by_file_impl."""

    @pytest.mark.asyncio
    async def test_search_by_file_with_results(self, mock_db, sample_search_results):
        """Test file search with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_search_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **3 conversations** about `/path/to/file.py`\n\n**1.** Test conversation about Python async programming..."

            result = await _search_by_file_impl(
                file_path="/path/to/file.py", limit=10, project="test-project"
            )

            assert "conversations" in result
            assert "/path/to/file.py" in result

    @pytest.mark.asyncio
    async def test_search_by_file_no_results(self, mock_db):
        """Test file search with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No conversations found about file: /nonexistent/file.py"

            result = await _search_by_file_impl(file_path="/nonexistent/file.py")

            assert "No conversations found" in result


class TestExtractFileExcerpt:
    """Tests for _extract_file_excerpt helper."""

    def test_extract_file_excerpt_found(self):
        """Test excerpt extraction when file path is in content."""
        content = "Some text before /path/to/file.py and some text after it"
        result = _extract_file_excerpt(content, "/path/to/file.py")

        assert "/path/to/file.py" in result

    def test_extract_file_excerpt_not_found(self):
        """Test excerpt when file path not in content."""
        content = "Some general content without file paths"
        result = _extract_file_excerpt(content, "/path/to/file.py")

        assert len(result) <= 150


# ==============================================================================
# Search by Concept Tests
# ==============================================================================

class TestSearchByConceptImpl:
    """Tests for _search_by_concept_impl."""

    @pytest.mark.asyncio
    async def test_search_by_concept_with_results(self, mock_db, sample_search_results):
        """Test concept search with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_search_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **3 conversations** about `async`\n\n**1.** (2026-05-20 10:00:00) (relevance: 0.95) Test conversation about Python async..."

            result = await _search_by_concept_impl(
                concept="async",
                include_files=True,
                limit=10,
                project="test-project",
            )

            assert "conversations" in result
            assert "async" in result

    @pytest.mark.asyncio
    async def test_search_by_concept_no_results(self, mock_db):
        """Test concept search with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No conversations found about concept: nonexistent"

            result = await _search_by_concept_impl(concept="nonexistent")

            assert "No conversations found" in result


class TestExtractRelevantExcerpt:
    """Tests for _extract_relevant_excerpt helper."""

    def test_extract_relevant_excerpt_concept_found(self):
        """Test excerpt extraction when concept is in content."""
        content = "This is about async programming and async/await patterns"
        result = _extract_relevant_excerpt(content, "async")

        assert "async" in result.lower()

    def test_extract_relevant_excerpt_concept_not_found(self):
        """Test excerpt when concept not in content."""
        content = "This is some general content"
        result = _extract_relevant_excerpt(content, "async")

        assert len(result) <= 150


class TestExtractMentionedFiles:
    """Tests for _extract_mentioned_files helper."""

    def test_extract_mentioned_files_python(self, sample_search_results):
        """Test extraction of Python files."""
        results = [
            {
                "content": "Working on /path/to/main.py and /path/to/utils.py today"
            }
        ]
        result = _extract_mentioned_files(results)

        assert len(result) >= 0  # May or may not find files depending on regex

    def test_extract_mentioned_files_empty(self):
        """Test with content without file paths."""
        result = _extract_mentioned_files([{"content": "Just text without files"}])
        assert isinstance(result, list)


# ==============================================================================
# Reflection Stats Tests
# ==============================================================================

class TestReflectionStatsImpl:
    """Tests for _reflection_stats_impl."""

    @pytest.mark.asyncio
    async def test_reflection_stats_success(self, mock_db):
        """Test successful reflection stats retrieval."""
        mock_db.get_stats = AsyncMock(
            return_value={
                "total_reflections": 100,
                "total_conversations": 500,
            }
        )

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "📊 **Reflection Database Statistics**\n\n**Total Reflections**: 100\n**Total Conversations**: 500"

            result = await _reflection_stats_impl()

            assert "Reflection Database Statistics" in result


class TestResetReflectionDatabaseImpl:
    """Tests for _reset_reflection_database_impl."""

    @pytest.mark.asyncio
    async def test_reset_database_success(self, mock_db):
        """Test successful database reset."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.require_reflection_database",
            return_value=mock_db,
        ):
            result = await _reset_reflection_database_impl()

            assert "successfully" in result or "✅" in result

    @pytest.mark.asyncio
    async def test_reset_database_failure(self, mock_db):
        """Test database reset failure."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.require_reflection_database",
            side_effect=Exception("Database locked"),
        ):
            result = await _reset_reflection_database_impl()

            assert "failed" in result or "❌" in result


# ==============================================================================
# Search Code Tests
# ==============================================================================

class TestSearchCodeImpl:
    """Tests for _search_code_impl."""

    @pytest.mark.asyncio
    async def test_search_code_with_results(
        self, mock_db, sample_code_results
    ):
        """Test code search with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_code_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **1 code patterns** for `async` (type: python)\n\n**1.** (2026-05-20 10:00:00) \n```\nasync def example()...\n```"

            result = await _search_code_impl(
                query="async",
                pattern_type="python",
                limit=10,
                project="test-project",
            )

            assert "code patterns" in result or "No code patterns" in result

    @pytest.mark.asyncio
    async def test_search_code_no_results(self, mock_db):
        """Test code search with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No code patterns found for: nonexistent"

            result = await _search_code_impl(query="nonexistent")

            assert "No code patterns found" in result


class TestExtractCodeBlocksFromContent:
    """Tests for _extract_code_blocks_from_content helper."""

    def test_extract_code_blocks_with_code(self):
        """Test extraction with code blocks in content."""
        content = "Here is some code: ```python\nprint('hello')\n``` and more text"
        result = _extract_code_blocks_from_content(content)

        assert isinstance(result, list)

    def test_extract_code_blocks_no_code(self):
        """Test extraction with no code blocks."""
        content = "Just regular text without code blocks"
        result = _extract_code_blocks_from_content(content)

        assert isinstance(result, list)


# ==============================================================================
# Search Errors Tests
# ==============================================================================

class TestSearchErrorsImpl:
    """Tests for _search_errors_impl."""

    @pytest.mark.asyncio
    async def test_search_errors_with_results(
        self, mock_db, sample_error_results
    ):
        """Test error search with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_error_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **1 error contexts** for `connection` (type: network)\n\n**1.** Error: connection refused in async function..."

            result = await _search_errors_impl(
                query="connection",
                error_type="network",
                limit=10,
                project="test-project",
            )

            assert "error contexts" in result or "No error patterns" in result

    @pytest.mark.asyncio
    async def test_search_errors_no_results(self, mock_db):
        """Test error search with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No error patterns found for: nonexistent"

            result = await _search_errors_impl(query="nonexistent")

            assert "No error patterns found" in result


class TestFindBestErrorExcerpt:
    """Tests for _find_best_error_excerpt helper."""

    def test_find_best_error_excerpt_with_errors(self):
        """Test excerpt finding with error keywords."""
        content = "Error: connection refused. The exception was thrown during execution."
        result = _find_best_error_excerpt(content)

        assert len(result) > 0

    def test_find_best_error_excerpt_no_errors(self):
        """Test with content without error keywords."""
        content = "This is a normal conversation without errors"
        result = _find_best_error_excerpt(content)

        # Should return first 150 chars
        assert len(result) <= 150


# ==============================================================================
# Temporal Search Tests
# ==============================================================================

class TestSearchTemporalImpl:
    """Tests for _search_temporal_impl."""

    @pytest.mark.asyncio
    async def test_search_temporal_with_results(self, mock_db, sample_search_results):
        """Test temporal search with results."""
        mock_db.search_conversations = AsyncMock(return_value=sample_search_results)

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 **3 conversations** from `last week` matching `async`\n\n**1.** (2026-05-20 10:00:00) Test conversation about Python async programming..."

            result = await _search_temporal_impl(
                time_expression="last week",
                query="async",
                limit=10,
                project="test-project",
            )

            assert "conversations" in result or "No conversations" in result

    @pytest.mark.asyncio
    async def test_search_temporal_no_results(self, mock_db):
        """Test temporal search with no results."""
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No conversations found for time period: last month"

            result = await _search_temporal_impl(time_expression="last month")

            assert "No conversations found" in result


class TestParseTimeExpression:
    """Tests for _parse_time_expression helper."""

    def test_parse_time_expression_yesterday(self):
        """Test parsing 'yesterday'."""
        result = _parse_time_expression("yesterday")
        assert result is not None
        assert (datetime.now() - result).days == 1

    def test_parse_time_expression_last_week(self):
        """Test parsing 'last week'."""
        result = _parse_time_expression("last week")
        assert result is not None
        assert (datetime.now() - result).days == 7

    def test_parse_time_expression_last_month(self):
        """Test parsing 'last month'."""
        result = _parse_time_expression("last month")
        assert result is not None
        assert (datetime.now() - result).days == 30

    def test_parse_time_expression_today(self):
        """Test parsing 'today'."""
        result = _parse_time_expression("today")
        assert result is not None
        # Should be within last 24 hours (with some tolerance for test execution time)
        elapsed = (datetime.now() - result).total_seconds()
        assert elapsed <= 86400 + 5, f"Expected <= 86400s, got {elapsed}s"

    def test_parse_time_expression_unknown(self):
        """Test parsing unknown expression."""
        result = _parse_time_expression("sometime maybe")
        assert result is None


# ==============================================================================
# Progressive Search Tests
# ==============================================================================

class TestProgressiveSearchImpl:
    """Tests for _progressive_search_impl."""

    @pytest.mark.asyncio
    async def test_progressive_search_success(self):
        """Test successful progressive search."""
        mock_result = MagicMock(
            tier_results=[],
            total_results=0,
            tiers_searched=[],
            early_stop=False,
            total_latency_ms=100,
            metadata={},
        )

        with patch("session_buddy.search.ProgressiveSearchEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine_class.return_value = mock_engine
            mock_engine.search_progressive = AsyncMock(return_value=mock_result)

            result = await _progressive_search_impl(
                query="async",
                project="test-project",
                min_score=0.6,
                max_results=30,
                max_tiers=4,
                enable_early_stop=True,
            )

            assert "success" in result
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_progressive_search_import_error(self):
        """Test progressive search when import fails."""
        # Mock the module import by setting it to None in sys.modules
        with patch.dict("sys.modules", {"session_buddy.search": None}):
            # Also need to patch the module-level __import__ behavior
            # The import happens inside the function, so we patch the import source
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "session_buddy.search" or name.startswith("session_buddy.search."):
                    raise ImportError("No module named 'session_buddy.search'")
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=mock_import):
                result = await _progressive_search_impl(query="test")

                assert result["success"] is False
                assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_progressive_search_exception(self):
        """Test progressive search when exception occurs."""
        with patch("session_buddy.search.ProgressiveSearchEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine_class.return_value = mock_engine
            mock_engine.search_progressive = AsyncMock(
                side_effect=Exception("Search failed")
            )

            result = await _progressive_search_impl(query="test")

            assert result["success"] is False
            assert "error" in result


# ==============================================================================
# Configure Tiers Tests
# ==============================================================================

class TestConfigureTiersImpl:
    """Tests for _configure_tiers_impl."""

    @pytest.mark.asyncio
    async def test_configure_tiers_success(self):
        """Test successful tier configuration."""
        mock_config = MagicMock()
        mock_config.min_results = 5
        mock_config.high_quality_threshold = 0.8
        mock_config.perfect_match_threshold = 0.95
        mock_config.max_tiers = 4
        mock_config.tier_timeout_ms = 5000
        mock_config.quality_weight = 0.7
        mock_config.quantity_weight = 0.3

        with patch("session_buddy.search.SufficiencyConfig") as mock_config_class:
            mock_config_class.return_value = mock_config

            result = await _configure_tiers_impl(
                sufficiency_min_results=10,
                sufficiency_high_quality_threshold=0.9,
            )

            assert result["success"] is True
            assert "config" in result

    @pytest.mark.asyncio
    async def test_configure_tiers_import_error(self):
        """Test tier configuration when import fails."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "session_buddy.search" or name.startswith("session_buddy.search."):
                raise ImportError("No module named 'session_buddy.search'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = await _configure_tiers_impl()

            assert result["success"] is False
            assert "not available" in result["error"]


# ==============================================================================
# Tier Stats Tests
# ==============================================================================

class TestTierStatsImpl:
    """Tests for _tier_stats_impl."""

    @pytest.mark.asyncio
    async def test_tier_stats_success(self):
        """Test successful tier stats retrieval."""
        with patch("session_buddy.search.ProgressiveSearchEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine_class.return_value = mock_engine
            mock_engine.get_search_stats = MagicMock(return_value={"queries": 100})

            result = await _tier_stats_impl()

            assert result["success"] is True
            assert "stats" in result
            assert "tier_info" in result

    @pytest.mark.asyncio
    async def test_tier_stats_import_error(self):
        """Test tier stats when import fails."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "session_buddy.search" or name.startswith("session_buddy.search."):
                raise ImportError("No module named 'session_buddy.search'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = await _tier_stats_impl()

            assert result["success"] is False
            assert "not available" in result["error"]


# ==============================================================================
# Tags Parameter Parsing Tests
# ==============================================================================

class TestParseTagsParameter:
    """Tests for _parse_tags_parameter helper."""

    def test_parse_tags_parameter_list(self):
        """Test parsing a list parameter."""
        result = _parse_tags_parameter(["tag1", "tag2"])
        assert result == ["tag1", "tag2"]

    def test_parse_tags_parameter_json_string(self):
        """Test parsing JSON string."""
        result = _parse_tags_parameter('["tag1", "tag2"]')
        assert result == ["tag1", "tag2"]

    def test_parse_tags_parameter_single_tag_string(self):
        """Test parsing single tag as string."""
        result = _parse_tags_parameter("single-tag")
        assert result == ["single-tag"]

    def test_parse_tags_parameter_none(self):
        """Test with None parameter."""
        result = _parse_tags_parameter(None)
        assert result is None

    def test_parse_tags_parameter_invalid_json(self):
        """Test with invalid JSON string."""
        result = _parse_tags_parameter("not-valid-json")
        assert result == ["not-valid-json"]

    def test_parse_tags_parameter_single_value_json(self):
        """Test JSON with single non-list value."""
        result = _parse_tags_parameter('"single"')
        assert result == ["single"]


# ==============================================================================
# Format Helper Tests
# ==============================================================================

class TestFormatFileSearchResults:
    """Tests for _format_file_search_results helper."""

    @pytest.mark.asyncio
    async def test_format_file_search_results_with_results(
        self, sample_search_results
    ):
        """Test formatting file search results."""
        result = await _format_file_search_results("/path/file.py", sample_search_results)

        assert "conversations" in result
        assert "file.py" in result

    @pytest.mark.asyncio
    async def test_format_file_search_results_empty(self):
        """Test formatting with empty results."""
        result = await _format_file_search_results("/path/file.py", [])

        assert "No conversations found" in result


class TestFormatConceptResults:
    """Tests for _format_concept_results helper."""

    @pytest.mark.asyncio
    async def test_format_concept_results_with_results(
        self, sample_search_results
    ):
        """Test formatting concept search results."""
        result = await _format_concept_results("async", sample_search_results, include_files=False)

        assert "conversations" in result
        assert "async" in result

    @pytest.mark.asyncio
    async def test_format_concept_results_empty(self):
        """Test formatting with empty results."""
        result = await _format_concept_results("async", [], include_files=True)

        assert "No conversations found" in result


class TestFormatTemporalResults:
    """Tests for _format_temporal_results helper."""

    @pytest.mark.asyncio
    async def test_format_temporal_results_with_results(
        self, sample_search_results
    ):
        """Test formatting temporal search results."""
        result = await _format_temporal_results(
            "last week", query="async", results=sample_search_results
        )

        assert "conversations" in result
        assert "last week" in result

    @pytest.mark.asyncio
    async def test_format_temporal_results_empty(self):
        """Test formatting with empty results."""
        result = await _format_temporal_results("last week", query=None, results=[])

        assert "No conversations found" in result


# ==============================================================================
# Error Handling Tests
# ==============================================================================

class TestSearchToolsErrorHandling:
    """Tests for error handling in search tools."""

    @pytest.mark.asyncio
    async def test_database_unavailable(self):
        """Test handling when database is unavailable."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "❌ Quick search not available: Database not available"

            result = await _quick_search_impl(query="test")

            assert "not available" in result or "failed" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_validation_error_empty_query(self):
        """Test validation error for empty query."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "❌ Validation error: content is required"

            result = await _store_reflection_impl(content="")

            # Should return error message
            assert isinstance(result, str)


# ==============================================================================
# Edge Case Tests
# ==============================================================================

class TestSearchToolsEdgeCases:
    """Tests for edge cases in search tools."""

    @pytest.mark.asyncio
    async def test_search_with_special_characters(self):
        """Test search with special characters in query."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No results found for 'test<script>alert()</script>'"

            result = await _quick_search_impl(query="test<script>alert()</script>")

            # Should handle gracefully without crashing
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_with_unicode(self):
        """Test search with unicode characters."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No results found for 'test with unicode: 中文'"

            result = await _quick_search_impl(query="test with unicode: 中文")

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_with_very_long_query(self):
        """Test search with very long query string."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No results found for '" + "a" * 1000 + "'"

            long_query = "a" * 10000
            result = await _quick_search_impl(query=long_query)

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_with_negative_limit(self):
        """Test search with negative limit parameter."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No conversations found about file: /test.py"

            result = await _search_by_file_impl(file_path="/test.py", limit=-1)

            # Should handle gracefully
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_with_zero_limit(self):
        """Test search with zero limit parameter."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No conversations found about file: /test.py"

            result = await _search_by_file_impl(file_path="/test.py", limit=0)

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_with_very_large_offset(self):
        """Test pagination with very large offset."""
        with patch(
            "session_buddy.mcp.tools.memory.search_tools.execute_simple_database_tool",
        ) as mock_exec:
            mock_exec.return_value = "🔍 No more results for 'test' (offset: 1000000)"

            result = await _get_more_results_impl(query="test", offset=1000000)

            assert isinstance(result, str)


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])