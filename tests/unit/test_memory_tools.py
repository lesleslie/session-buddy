#!/usr/bin/env python3
"""Unit tests for Memory MCP tools.

Tests the MCP tools for storing, searching, and managing reflections and conversation memories.

Phase: Week 1 Day 2 - Quick Win Coverage (84% → 90%+)
"""

from __future__ import annotations

import asyncio
import operator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from session_buddy.mcp.tools.memory.memory_tools import (
    _analyze_project_distribution,
    _analyze_relevance_scores,
    _check_reflection_tools_available,
    _close_db_connection,
    _close_db_object,
    _close_reflection_db_safely,
    _execute_database_tool,
    _execute_simple_database_tool,
    _extract_common_themes,
    _format_concept_search_results,
    _format_file_search_results,
    _format_new_stats,
    _format_old_stats,
    _format_score,
    _format_search_summary,
    _format_stats_new,
    _format_stats_old,
    _format_store_reflection_result,
    _get_reflection_database,
    _quick_search_impl,
    _quick_search_operation,
    _reflection_stats_impl,
    _reflection_stats_operation,
    _reset_reflection_database_impl,
    _search_by_concept_impl,
    _search_by_concept_operation,
    _search_by_file_impl,
    _search_by_file_operation,
    _search_summary_impl,
    _search_summary_operation,
    _store_reflection_impl,
    _store_reflection_operation,
    register_memory_tools,
)


# =============================================================================
# Test Format Score Helper
# =============================================================================


class TestFormatScore:
    """Test _format_score helper function."""

    def test_format_score_standard(self):
        """Should format standard score correctly."""
        result = _format_score(0.8567)
        assert result == "0.86"

    def test_format_score_zero(self):
        """Should format zero score."""
        result = _format_score(0.0)
        assert result == "0.00"

    def test_format_score_perfect(self):
        """Should format perfect score."""
        result = _format_score(1.0)
        assert result == "1.00"

    def test_format_score_low(self):
        """Should format low score."""
        result = _format_score(0.1234)
        assert result == "0.12"

    def test_format_score_high(self):
        """Should format high score near 1."""
        result = _format_score(0.9999)
        assert result == "1.00"


# =============================================================================
# Test Format Stats New (V2 format)
# =============================================================================


class TestFormatStatsNew:
    """Test _format_stats_new and _format_stats_old helper functions."""

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
        assert "150" in result[0]
        assert "75" in result[1]
        assert "onnx-local" in result[2]
        assert "✅ Healthy" in result[3]

    def test_format_stats_new_with_zero_counts(self):
        """Should indicate empty database for zero counts."""
        stats = {
            "conversations_count": 0,
            "reflections_count": 0,
            "embedding_provider": "unknown",
        }

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert "0" in result[0]
        assert "0" in result[1]
        assert "⚠️ Empty" in result[3]

    def test_format_stats_new_with_missing_fields(self):
        """Should handle missing optional fields gracefully."""
        stats = {}

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert "0" in result[0]
        assert "0" in result[1]
        assert "unknown" in result[2]
        assert "⚠️ Empty" in result[3]

    def test_format_stats_new_with_partial_data(self):
        """Should use defaults for missing fields."""
        stats = {
            "conversations_count": 50,
            "embedding_provider": "transformers",
        }

        result = _format_stats_new(stats)

        assert isinstance(result, list)
        assert "50" in result[0]
        assert "0" in result[1]
        assert "transformers" in result[2]
        assert "✅ Healthy" in result[3]

    def test_format_stats_new_health_threshold_one(self):
        """Should show healthy when total count > 0."""
        stats = {
            "conversations_count": 0,
            "reflections_count": 1,
            "embedding_provider": "test",
        }

        result = _format_new_stats(stats)

        assert "✅ Healthy" in result[3]

    def test_format_new_stats_is_alias(self):
        """Should be backward-compatible alias."""
        stats = {"conversations_count": 10, "reflections_count": 5}
        assert _format_new_stats(stats) == _format_stats_new(stats)


# =============================================================================
# Test Format Stats Old (Legacy format)
# =============================================================================


class TestFormatStatsOld:
    """Test _format_old_stats helper function for legacy stats format."""

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
                "Activity 6",
            ],
        }

        result = _format_old_stats(stats)

        assert isinstance(result, list)
        assert any("100" in line for line in result)
        assert any("5" in line for line in result)
        assert any("2025-01-01" in line and "2025-01-15" in line for line in result)
        activity_section = [line for line in result if "Activity" in line]
        assert len(activity_section) == 5
        assert any("✅ Healthy" in line for line in result)

    def test_format_old_stats_with_zero_reflections(self):
        """Should show empty database warning for zero reflections."""
        stats = {
            "total_reflections": 0,
            "projects": 0,
        }

        result = _format_old_stats(stats)

        assert any("⚠️ Empty" in line for line in result)

    def test_format_old_stats_with_missing_date_range(self):
        """Should handle missing date_range gracefully."""
        stats = {
            "total_reflections": 50,
            "projects": 3,
        }

        result = _format_old_stats(stats)

        assert any("50" in line for line in result)
        assert not any("Date range" in line for line in result)

    def test_format_old_stats_with_empty_recent_activity(self):
        """Should handle empty recent_activity list."""
        stats = {
            "total_reflections": 25,
            "projects": 2,
            "recent_activity": [],
        }

        result = _format_old_stats(stats)

        assert not any("Recent activity" in line for line in result)

    def test_format_old_stats_with_invalid_date_range_type(self):
        """Should handle non-dict date_range gracefully."""
        stats = {
            "total_reflections": 10,
            "projects": 1,
            "date_range": "invalid",
        }

        result = _format_old_stats(stats)

        assert not any("Date range" in line for line in result)

    def test_format_old_stats_minimal_data(self):
        """Should work with minimal stats (just total_reflections)."""
        stats = {
            "total_reflections": 1,
        }

        result = _format_old_stats(stats)

        assert any("1" in line for line in result)
        assert any("✅ Healthy" in line for line in result)

    def test_format_old_stats_is_alias(self):
        """Should be backward-compatible alias."""
        stats = {"total_reflections": 100, "projects": 5}
        assert _format_old_stats(stats) == _format_stats_old(stats)


# =============================================================================
# Test Check Reflection Tools Available
# =============================================================================


class TestCheckReflectionToolsAvailable:
    """Test _check_reflection_tools_available function."""

    def test_check_with_spec_found(self):
        """Should return True when duckdb is available."""
        mock_spec = MagicMock()
        with patch("importlib.util.find_spec", return_value=mock_spec):
            result = _check_reflection_tools_available()
            assert result is True

    def test_check_with_spec_none(self):
        """Should return False when duckdb is not available."""
        # Reset global state to ensure clean test
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": None},
            clear=False,
        ):
            with patch("importlib.util.find_spec", return_value=None):
                result = _check_reflection_tools_available()
                assert result is False

    def test_check_caches_result(self):
        """Should cache the check result."""
        mock_spec = MagicMock()
        with patch("importlib.util.find_spec", return_value=mock_spec):
            first = _check_reflection_tools_available()
            second = _check_reflection_tools_available()
            assert first == second


# =============================================================================
# Test Get Reflection Database
# =============================================================================


class TestGetReflectionDatabase:
    """Test _get_reflection_database function."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_returns_cached(self):
        """Should return cached database if available."""
        mock_db = MagicMock()
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_db": mock_db},
            clear=False,
        ):
            result = await _get_reflection_database()
            assert result is mock_db

    @pytest.mark.asyncio
    async def test_get_reflection_database_creates_new(self):
        """Should create new database if none cached."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_db": None},
            clear=False,
        ):
            mock_db = MagicMock()
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools.require_reflection_database",
                new=AsyncMock(return_value=mock_db),
            ):
                result = await _get_reflection_database()
                assert result is mock_db


# =============================================================================
# Test Execute Database Tool
# =============================================================================


class TestExecuteDatabaseTool:
    """Test _execute_database_tool helper function."""

    @pytest.mark.asyncio
    async def test_execute_with_validation_error(self):
        """Should handle ValidationError."""

        async def op(db):
            return "result"

        def formatter(r):
            return f"formatted: {r}"

        with patch(
            "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
            new=AsyncMock(),
        ):
            mock_db = AsyncMock()
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools.require_reflection_database",
                return_value=mock_db,
            ):
                from session_buddy.utils.error_management import ValidationError

                validator = MagicMock(side_effect=ValidationError("bad input"))
                result = await _execute_database_tool(op, formatter, "TestOp", validator)
                assert "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_with_database_unavailable(self):
        """Should handle DatabaseUnavailableError."""
        from session_buddy.utils.error_management import DatabaseUnavailableError

        async def op(db):
            return "result"

        def formatter(r):
            return f"formatted: {r}"

        mock_db = MagicMock()
        with patch(
            "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
            side_effect=DatabaseUnavailableError("not available"),
        ):
            result = await _execute_database_tool(op, formatter, "TestOp")
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_with_generic_exception(self):
        """Should handle generic exceptions."""
        from session_buddy.utils.error_management import DatabaseUnavailableError

        async def op(db):
            raise Exception("generic error")

        def formatter(r):
            return f"formatted: {r}"

        mock_db = AsyncMock()
        with patch(
            "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _execute_database_tool(op, formatter, "TestOp")
            assert "generic error" in result.lower()


# =============================================================================
# Test Execute Simple Database Tool
# =============================================================================


class TestExecuteSimpleDatabaseTool:
    """Test _execute_simple_database_tool helper function."""

    @pytest.mark.asyncio
    async def test_execute_simple_success(self):
        """Should execute simple operation successfully."""

        async def op(db):
            return "success message"

        mock_db = MagicMock()
        with patch(
            "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
            return_value=mock_db,
        ):
            result = await _execute_simple_database_tool(op, "SimpleOp")
            assert result == "success message"

    @pytest.mark.asyncio
    async def test_execute_simple_database_unavailable(self):
        """Should handle DatabaseUnavailableError."""
        from session_buddy.utils.error_management import DatabaseUnavailableError

        async def op(db):
            return "result"

        with patch(
            "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
            side_effect=DatabaseUnavailableError("DB down"),
        ):
            result = await _execute_simple_database_tool(op, "SimpleOp")
            assert "down" in result.lower()


# =============================================================================
# Test Store Reflection
# =============================================================================


class TestStoreReflectionImpl:
    """Test _store_reflection_impl function."""

    @pytest.mark.asyncio
    async def test_store_reflection_when_tools_unavailable(self):
        """Should return unavailable message when duckdb not installed."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _store_reflection_impl("Test content")
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_success(self):
        """Should store reflection successfully."""
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=True)

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _store_reflection_impl("Test content", ["tag1", "tag2"])
                assert "stored" in result.lower() or "success" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_failure(self):
        """Should handle storage failure."""
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(side_effect=Exception("DB error"))

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _store_reflection_impl("Test content")
                assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_without_tags(self):
        """Should store reflection without tags."""
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=True)

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _store_reflection_impl("No tags content")
                assert "stored" in result.lower() or "success" in result.lower()


# =============================================================================
# Test Quick Search
# =============================================================================


class TestQuickSearchImpl:
    """Test _quick_search_impl function."""

    @pytest.mark.asyncio
    async def test_quick_search_when_tools_unavailable(self):
        """Should return unavailable message."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _quick_search_impl("test query")
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_with_results(self):
        """Should return search results."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(
            return_value=[
                {
                    "content": "Test result",
                    "project": "test-project",
                    "score": 0.85,
                    "timestamp": "2023-01-01T12:00:00Z",
                }
            ]
        )

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _quick_search_impl("test query", min_score=0.7)
                assert "test query" in result.lower()
                assert "test result" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_no_results(self):
        """Should return no results message."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _quick_search_impl("nonexistent")
                assert "no results" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_with_exception(self):
        """Should handle exceptions."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _quick_search_impl("test query")
                assert "error" in result.lower()


# =============================================================================
# Test Search Summary
# =============================================================================


class TestSearchSummaryImpl:
    """Test _search_summary_impl function."""

    @pytest.mark.asyncio
    async def test_search_summary_when_tools_unavailable(self):
        """Should return unavailable message."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _search_summary_impl("test query")
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_search_summary_with_results(self):
        """Should return search summary with results."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(
            return_value=[
                {
                    "content": "Result 1",
                    "project": "project-a",
                    "score": 0.9,
                    "timestamp": "2023-01-01T12:00:00Z",
                },
                {
                    "content": "Result 2",
                    "project": "project-b",
                    "score": 0.8,
                    "timestamp": "2023-01-02T12:00:00Z",
                },
            ]
        )

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_summary_impl("test query")
                assert "summary" in result.lower() or "test query" in result.lower()

    @pytest.mark.asyncio
    async def test_search_summary_no_results(self):
        """Should return no results message."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_summary_impl("nonexistent")
                assert "no results" in result.lower()

    @pytest.mark.asyncio
    async def test_search_summary_with_exception(self):
        """Should handle exceptions."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_summary_impl("test query")
                assert "error" in result.lower()


# =============================================================================
# Test Search By File
# =============================================================================


class TestSearchByFileImpl:
    """Test _search_by_file_impl function."""

    @pytest.mark.asyncio
    async def test_search_by_file_when_tools_unavailable(self):
        """Should return unavailable message."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _search_by_file_impl("test_file.py")
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_with_results(self):
        """Should return search results."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(
            return_value=[
                {
                    "content": "Discussion about test_file.py",
                    "project": "test-project",
                    "score": 0.85,
                    "timestamp": "2023-01-01T12:00:00Z",
                }
            ]
        )

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_file_impl("test_file.py", limit=5)
                assert "test_file.py" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_no_results(self):
        """Should return no results message."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_file_impl("nonexistent.py")
                assert "no conversations" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_file_with_exception(self):
        """Should handle exceptions."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_file_impl("test_file.py")
                assert "error" in result.lower()


# =============================================================================
# Test Search By Concept
# =============================================================================


class TestSearchByConceptImpl:
    """Test _search_by_concept_impl function."""

    @pytest.mark.asyncio
    async def test_search_by_concept_when_tools_unavailable(self):
        """Should return unavailable message."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _search_by_concept_impl("authentication")
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_concept_with_results(self):
        """Should return search results."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(
            return_value=[
                {
                    "content": "Discussion about authentication",
                    "project": "auth-service",
                    "score": 0.9,
                    "timestamp": "2023-01-01T12:00:00Z",
                }
            ]
        )

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_concept_impl("authentication", limit=5)
                assert "authentication" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_concept_no_results(self):
        """Should return no results message."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_concept_impl("nonexistent_concept")
                assert "no conversations" in result.lower()

    @pytest.mark.asyncio
    async def test_search_by_concept_with_exception(self):
        """Should handle exceptions."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(side_effect=Exception("Search error"))

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_concept_impl("authentication")
                assert "error" in result.lower()


# =============================================================================
# Test Reflection Stats
# =============================================================================


class TestReflectionStatsImpl:
    """Test _reflection_stats_impl function."""

    @pytest.mark.asyncio
    async def test_reflection_stats_when_tools_unavailable(self):
        """Should return unavailable message."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _reflection_stats_impl()
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_reflection_stats_success(self):
        """Should return statistics."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(
            return_value={
                "conversations_count": 42,
                "reflections_count": 35,
                "embedding_provider": "onnx-runtime",
            }
        )

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _reflection_stats_impl()
                assert "statistics" in result.lower() or "stats" in result.lower()

    @pytest.mark.asyncio
    async def test_reflection_stats_with_exception(self):
        """Should handle exceptions."""
        mock_db = AsyncMock()
        mock_db.get_stats = AsyncMock(side_effect=Exception("Stats error"))

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _reflection_stats_impl()
                assert "error" in result.lower()


# =============================================================================
# Test Reset Reflection Database
# =============================================================================


class TestResetReflectionDatabaseImpl:
    """Test _reset_reflection_database_impl function."""

    @pytest.mark.asyncio
    async def test_reset_when_tools_unavailable(self):
        """Should return unavailable message."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": False},
            clear=False,
        ):
            result = await _reset_reflection_database_impl()
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_reset_success(self):
        """Should reset database successfully."""
        mock_db = MagicMock()
        mock_db.conn = MagicMock()
        mock_db.conn.close = MagicMock()
        mock_db.aclose = AsyncMock()

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            mock_new_db = MagicMock()
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_new_db,
            ):
                result = await _reset_reflection_database_impl()
                assert "reset" in result.lower() or "connection" in result.lower()

    @pytest.mark.asyncio
    async def test_reset_with_exception(self):
        """Should handle exceptions during reset."""
        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": None},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                side_effect=Exception("Reset error"),
            ):
                result = await _reset_reflection_database_impl()
                assert "error" in result.lower()


# =============================================================================
# Test Close DB Helpers
# =============================================================================


class TestCloseDBConnection:
    """Test _close_db_connection function."""

    @pytest.mark.asyncio
    async def test_close_with_sync_close(self):
        """Should handle sync close method."""
        mock_conn = MagicMock()
        mock_conn.close = MagicMock()

        await _close_db_connection(mock_conn)
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_async_close(self):
        """Should handle async close method."""
        mock_conn = MagicMock()
        mock_close = AsyncMock()
        mock_conn.close = mock_close

        await _close_db_connection(mock_conn)
        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_close_method(self):
        """Should handle missing close method."""
        mock_conn = MagicMock()
        del mock_conn.close

        await _close_db_connection(mock_conn)


class TestCloseDBObject:
    """Test _close_db_object function."""

    @pytest.mark.asyncio
    async def test_close_with_async_aclose(self):
        """Should prefer aclose if available."""
        mock_db = MagicMock()
        mock_aclose = AsyncMock()
        mock_db.aclose = mock_aclose

        await _close_db_object(mock_db)
        mock_aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_sync_close(self):
        """Should fallback to sync close."""
        mock_db = MagicMock()
        mock_close = MagicMock()
        mock_db.aclose = None
        mock_db.close = mock_close

        await _close_db_object(mock_db)
        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_methods(self):
        """Should handle missing close methods."""
        mock_db = MagicMock()

        await _close_db_object(mock_db)


class TestCloseReflectionDBSafely:
    """Test _close_reflection_db_safely function."""

    @pytest.mark.asyncio
    async def test_close_with_conn_and_aclose(self):
        """Should close both connection and db object."""
        mock_db = MagicMock()
        mock_db.conn = MagicMock()
        mock_db.conn.close = MagicMock()
        mock_db.aclose = AsyncMock()

        await _close_reflection_db_safely(mock_db)
        mock_db.conn.close.assert_called_once()
        mock_db.aclose.assert_called_once()


# =============================================================================
# Test Analyze Helpers
# =============================================================================


class TestAnalyzeProjectDistribution:
    """Test _analyze_project_distribution function."""

    @pytest.mark.asyncio
    async def test_analyze_with_results(self):
        """Should analyze project distribution."""
        results = [
            {"project": "proj-a", "content": "test 1"},
            {"project": "proj-b", "content": "test 2"},
            {"project": "proj-a", "content": "test 3"},
        ]
        result = await _analyze_project_distribution(results)
        assert result == {"proj-a": 2, "proj-b": 1}

    @pytest.mark.asyncio
    async def test_analyze_with_missing_project(self):
        """Should handle missing project field."""
        results = [
            {"content": "test 1"},
            {"project": "proj-a", "content": "test 2"},
        ]
        result = await _analyze_project_distribution(results)
        assert result == {"Unknown": 1, "proj-a": 1}


class TestAnalyzeRelevanceScores:
    """Test _analyze_relevance_scores function."""

    @pytest.mark.asyncio
    async def test_analyze_with_scores(self):
        """Should calculate average score."""
        results = [
            {"score": 0.9, "content": "test 1"},
            {"score": 0.8, "content": "test 2"},
            {"score": 0.7, "content": "test 3"},
        ]
        avg, scores = await _analyze_relevance_scores(results)
        assert avg == pytest.approx(0.8)
        assert scores == [0.9, 0.8, 0.7]

    @pytest.mark.asyncio
    async def test_analyze_with_missing_scores(self):
        """Should handle missing scores."""
        results = [
            {"content": "test 1"},
            {"score": None, "content": "test 2"},
        ]
        avg, scores = await _analyze_relevance_scores(results)
        assert avg == 0.0
        assert scores == []

    @pytest.mark.asyncio
    async def test_analyze_with_empty_results(self):
        """Should handle empty results."""
        avg, scores = await _analyze_relevance_scores([])
        assert avg == 0.0
        assert scores == []


class TestExtractCommonThemes:
    """Test _extract_common_themes function."""

    @pytest.mark.asyncio
    async def test_extract_with_common_words(self):
        """Should extract common themes."""
        results = [
            {"content": "python programming language is great"},
            {"content": "python syntax is clean"},
            {"content": "programming requires practice"},
        ]
        themes = await _extract_common_themes(results)
        assert len(themes) <= 5
        # Should include 'python' as high frequency
        word_freq = dict(themes)
        assert "python" in word_freq

    @pytest.mark.asyncio
    async def test_extract_filters_short_words(self):
        """Should filter short words."""
        results = [
            {"content": "the cat sat on mat"},
        ]
        themes = await _extract_common_themes(results)
        themes_words = [w for w, _ in themes]
        assert "the" not in themes_words
        assert "cat" not in themes_words

    @pytest.mark.asyncio
    async def test_extract_with_empty_results(self):
        """Should handle empty results."""
        themes = await _extract_common_themes([])
        assert themes == []


# =============================================================================
# Test Format Result Helpers
# =============================================================================


class TestFormatFileSearchResults:
    """Test _format_file_search_results function."""

    @pytest.mark.asyncio
    async def test_format_with_results(self):
        """Should format file search results."""
        results = [
            {
                "content": "Discussion about file",
                "project": "test-project",
                "score": 0.85,
                "timestamp": "2023-01-01",
            }
        ]
        result = await _format_file_search_results("test.py", results)
        assert "test.py" in result
        assert "test-project" in result

    @pytest.mark.asyncio
    async def test_format_with_no_results(self):
        """Should format empty results."""
        result = await _format_file_search_results("test.py", [])
        assert "no conversations" in result.lower()


class TestFormatConceptSearchResults:
    """Test _format_concept_search_results function."""

    @pytest.mark.asyncio
    async def test_format_with_results_and_files(self):
        """Should format concept search results with files."""
        results = [
            {
                "content": "Discussion about auth",
                "project": "auth-service",
                "score": 0.9,
                "timestamp": "2023-01-01",
                "files": ["auth.py", "login.py", "oauth.py"],
            }
        ]
        result = await _format_concept_search_results("authentication", results, True)
        assert "authentication" in result
        assert "auth-service" in result

    @pytest.mark.asyncio
    async def test_format_with_no_results(self):
        """Should format empty results."""
        result = await _format_concept_search_results("auth", [], True)
        assert "no conversations" in result.lower()


class TestFormatSearchSummary:
    """Test _format_search_summary function."""

    @pytest.mark.asyncio
    async def test_format_with_results(self):
        """Should format search summary."""
        results = [
            {
                "content": "Result 1",
                "project": "proj-a",
                "score": 0.9,
                "timestamp": "2023-01-01",
            },
            {
                "content": "Result 2",
                "project": "proj-b",
                "score": 0.8,
                "timestamp": "2023-01-02",
            },
        ]
        result = await _format_search_summary("test query", results)
        assert "test query" in result
        assert "Total results" in result

    @pytest.mark.asyncio
    async def test_format_with_no_results(self):
        """Should format empty results."""
        result = await _format_search_summary("test", [])
        assert "no results" in result.lower()


# =============================================================================
# Test Format Store Reflection Result
# =============================================================================


class TestFormatStoreReflectionResult:
    """Test _format_store_reflection_result function."""

    def test_format_with_success(self):
        """Should format successful storage."""
        result = {
            "success": True,
            "content": "Test content",
            "tags": ["tag1"],
            "timestamp": "2023-01-01 12:00:00",
        }
        formatted = _format_store_reflection_result(result)
        assert "stored" in formatted.lower() or "test content" in formatted.lower()

    def test_format_with_failure(self):
        """Should format failed storage."""
        result = {
            "success": False,
            "content": "Test content",
            "tags": [],
            "timestamp": "2023-01-01 12:00:00",
        }
        formatted = _format_store_reflection_result(result)
        # When success is False, format_reflection_result returns operation_failed
        assert "failed" in formatted.lower() or "error" in formatted.lower()


# =============================================================================
# Test Memory Tool Registration
# =============================================================================


class TestRegisterMemoryTools:
    """Test register_memory_tools function."""

    def test_register_calls_tool_decorator(self):
        """Should register all memory tools."""
        mock_server = MagicMock()

        register_memory_tools(mock_server)

        # Should have 7 tool decorators: store_reflection, quick_search,
        # search_summary, search_by_file, search_by_concept, reflection_stats,
        # reset_reflection_database
        assert mock_server.tool.call_count >= 7


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_store_reflection_empty_content(self):
        """Should handle empty content."""
        from session_buddy.utils.error_management import ValidationError

        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(
            side_effect=ValidationError("content required")
        )

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _store_reflection_impl("")
                assert "validation" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_store_reflection_none_tags(self):
        """Should handle None tags."""
        mock_db = AsyncMock()
        mock_db.store_reflection = AsyncMock(return_value=True)

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _store_reflection_impl("Content", None)
                assert "stored" in result.lower() or "success" in result.lower()

    @pytest.mark.asyncio
    async def test_quick_search_with_custom_min_score(self):
        """Should pass custom min_score to database."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                await _quick_search_impl("query", min_score=0.5)
                mock_db.search_conversations.assert_called_once()
                call_kwargs = mock_db.search_conversations.call_args[1]
                assert call_kwargs["min_score"] == 0.5

    @pytest.mark.asyncio
    async def test_search_summary_with_custom_min_score(self):
        """Should pass custom min_score to database."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                await _search_summary_impl("query", min_score=0.3)
                mock_db.search_conversations.assert_called_once()
                call_kwargs = mock_db.search_conversations.call_args[1]
                assert call_kwargs["min_score"] == 0.3

    @pytest.mark.asyncio
    async def test_search_by_file_with_different_limit(self):
        """Should respect custom limit."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                await _search_by_file_impl("test.py", limit=15)
                mock_db.search_conversations.assert_called_once()
                call_kwargs = mock_db.search_conversations.call_args[1]
                assert call_kwargs["limit"] == 15

    @pytest.mark.asyncio
    async def test_search_by_concept_with_files_disabled(self):
        """Should handle include_files=False."""
        mock_db = AsyncMock()
        mock_db.search_conversations = AsyncMock(return_value=[])

        with patch.dict(
            "session_buddy.mcp.tools.memory.memory_tools.__dict__",
            {"_reflection_tools_available": True, "_reflection_db": mock_db},
            clear=False,
        ):
            with patch(
                "session_buddy.mcp.tools.memory.memory_tools._get_reflection_database",
                return_value=mock_db,
            ):
                result = await _search_by_concept_impl(
                    "auth", include_files=False, limit=10
                )
                assert "no conversations" in result.lower()
