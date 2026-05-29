"""Tests for rewriting_tools MCP module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.advanced.rewriting_tools import (
    _calculate_rewrite_health,
    _categorize_cache_hit_rate,
    _categorize_llm_reliability,
    _categorize_latency,
    _format_error_response,
    query_rewrite_stats,
    rewrite_query,
)


class TestFormatErrorResponse:
    """Tests for _format_error_response helper."""

    def test_formats_basic_error(self):
        """Test basic error message formatting."""
        result = _format_error_response("Something went wrong")

        parsed = json.loads(result)
        assert parsed["success"] is False
        assert parsed["error"] == "Something went wrong"

    def test_formats_empty_error(self):
        """Test empty error message."""
        result = _format_error_response("")

        parsed = json.loads(result)
        assert parsed["success"] is False
        assert parsed["error"] == ""

    def test_formats_json_valid(self):
        """Test that output is valid JSON."""
        result = _format_error_response("Test error")

        # Should not raise
        parsed = json.loads(result)
        assert "success" in parsed
        assert "error" in parsed


class TestCategorizeCacheHitRate:
    """Tests for _categorize_cache_hit_rate helper."""

    @pytest.mark.parametrize(
        "rate,expected",
        [
            (0.71, "Excellent"),
            (1.0, "Excellent"),
            (0.7, "Good"),
            (0.51, "Good"),
            (0.5, "Needs warming"),
            (0.0, "Needs warming"),
            (0.25, "Needs warming"),
        ],
    )
    def test_returns_expected_category(self, rate, expected):
        """Test cache hit rate categorization across boundaries."""
        result = _categorize_cache_hit_rate(rate)
        assert result == expected

    def test_boundary_70_percent(self):
        """Test boundary at 0.70 - exactly 70% is Good."""
        assert _categorize_cache_hit_rate(0.70) == "Good"

    def test_boundary_50_percent(self):
        """Test boundary at 0.50 - exactly 50% is Needs warming."""
        assert _categorize_cache_hit_rate(0.50) == "Needs warming"


class TestCategorizeLlmReliability:
    """Tests for _categorize_llm_reliability helper."""

    @pytest.mark.parametrize(
        "failures,expected",
        [
            (0, "Good"),
            (1, "Some failures"),
            (5, "Some failures"),
            (9, "Some failures"),
            (10, "High failure rate"),
            (100, "High failure rate"),
        ],
    )
    def test_returns_expected_category(self, failures, expected):
        """Test LLM reliability categorization across boundaries."""
        result = _categorize_llm_reliability(failures)
        assert result == expected

    def test_boundary_at_zero(self):
        """Test boundary at exactly 0 failures."""
        assert _categorize_llm_reliability(0) == "Good"

    def test_boundary_at_ten(self):
        """Test boundary at exactly 10 failures."""
        assert _categorize_llm_reliability(10) == "High failure rate"


class TestCategorizeLatency:
    """Tests for _categorize_latency helper."""

    @pytest.mark.parametrize(
        "latency_ms,expected",
        [
            (50, "Excellent"),
            (99, "Excellent"),
            (100, "Good"),
            (150, "Good"),
            (199, "Good"),
            (200, "Slow"),
            (500, "Slow"),
            (1000, "Slow"),
        ],
    )
    def test_returns_expected_category(self, latency_ms, expected):
        """Test latency categorization across boundaries."""
        result = _categorize_latency(latency_ms)
        assert result == expected

    def test_boundary_100ms(self):
        """Test boundary at exactly 100ms."""
        assert _categorize_latency(100) == "Good"

    def test_boundary_200ms(self):
        """Test boundary at exactly 200ms."""
        assert _categorize_latency(200) == "Slow"


class TestCalculateRewriteHealth:
    """Tests for _calculate_rewrite_health helper."""

    def test_with_zero_rewrites(self):
        """Test health calculation when no rewrites have occurred."""
        stats = {
            "total_rewrites": 0,
            "cache_hit_rate": 0.0,
            "llm_failures": 0,
            "avg_latency_ms": 0.0,
        }

        result = _calculate_rewrite_health(stats)

        assert result["total_rewrites"] == 0
        assert result["cache_hit_rate_category"] == "Needs warming"
        assert result["llm_reliability"] == "Good"
        assert result["avg_latency_category"] == "Excellent"

    def test_with_excellent_cache_and_reliability(self):
        """Test health with high cache hit rate and no failures."""
        stats = {
            "total_rewrites": 100,
            "cache_hit_rate": 0.85,
            "llm_failures": 0,
            "avg_latency_ms": 50.0,
        }

        result = _calculate_rewrite_health(stats)

        assert result["total_rewrites"] == 100
        assert result["cache_hit_rate_category"] == "Excellent"
        assert result["llm_reliability"] == "Good"
        assert result["avg_latency_category"] == "Excellent"

    def test_with_degraded_metrics(self):
        """Test health with poor cache hit rate and many failures."""
        stats = {
            "total_rewrites": 500,
            "cache_hit_rate": 0.3,
            "llm_failures": 25,
            "avg_latency_ms": 350.0,
        }

        result = _calculate_rewrite_health(stats)

        assert result["total_rewrites"] == 500
        assert result["cache_hit_rate_category"] == "Needs warming"
        assert result["llm_reliability"] == "High failure rate"
        assert result["avg_latency_category"] == "Slow"

    def test_with_moderate_conditions(self):
        """Test health with moderate cache and some failures."""
        stats = {
            "total_rewrites": 200,
            "cache_hit_rate": 0.6,
            "llm_failures": 7,
            "avg_latency_ms": 180.0,
        }

        result = _calculate_rewrite_health(stats)

        assert result["total_rewrites"] == 200
        assert result["cache_hit_rate_category"] == "Good"
        assert result["llm_reliability"] == "Some failures"
        assert result["avg_latency_category"] == "Good"


class TestRewriteQuery:
    """Tests for rewrite_query function."""

    @pytest.fixture
    def mock_rewriter_result(self):
        """Create a mock RewriteResult."""
        result = MagicMock()
        result.original_query = "what did I learn"
        result.rewritten_query = "what did I learn about session-buddy"
        result.was_rewritten = True
        result.confidence = 0.85
        result.llm_provider = "minimax"
        result.latency_ms = 150.0
        result.context_used = {"project": "test"}
        result.cache_hit = False
        return result

    @pytest.fixture
    def mock_context(self):
        """Create a mock FastMCP Context."""
        ctx = MagicMock()
        ctx.session_id = "test-session-123"
        return ctx

    @pytest.mark.asyncio
    async def test_rewrite_query_success(self, mock_context, mock_rewriter_result):
        """Test successful query rewrite."""
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_query = AsyncMock(return_value=mock_rewriter_result)

        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_rewriter

            result = await rewrite_query(mock_context, "what did I learn")

        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["result"]["original_query"] == "what did I learn"
        assert parsed["result"]["was_rewritten"] is True
        assert parsed["result"]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_rewrite_query_no_rewriter(self, mock_context):
        """Test rewrite_query when no rewriter is available."""
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.original_query = "test"
        mock_result.rewritten_query = "test"
        mock_result.was_rewritten = False
        mock_result.confidence = 1.0
        mock_result.llm_provider = None
        mock_result.latency_ms = 0
        mock_result.context_used = {}
        mock_result.cache_hit = False
        mock_instance.rewrite_query = AsyncMock(return_value=mock_result)

        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = None

            with patch("session_buddy.mcp.tools.advanced.rewriting_tools.QueryRewriter", return_value=mock_instance):
                result = await rewrite_query(mock_context, "test query")

        parsed = json.loads(result)
        assert parsed["success"] is True

    @pytest.mark.asyncio
    async def test_rewrite_query_with_project_filter(self, mock_context):
        """Test rewrite_query with project filter."""
        mock_result = MagicMock()
        mock_result.original_query = "test"
        mock_result.rewritten_query = "test"
        mock_result.was_rewritten = False
        mock_result.confidence = 1.0
        mock_result.llm_provider = None
        mock_result.latency_ms = 0
        mock_result.context_used = {}
        mock_result.cache_hit = True

        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_query = AsyncMock(return_value=mock_result)

        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_rewriter

            result = await rewrite_query(mock_context, "test", project="my-project")

        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["result"]["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_rewrite_query_force_rewrite(self, mock_context):
        """Test rewrite_query with force_rewrite=True."""
        mock_result = MagicMock()
        mock_result.original_query = "test"
        mock_result.rewritten_query = "test"
        mock_result.was_rewritten = True
        mock_result.confidence = 0.9
        mock_result.llm_provider = "minimax"
        mock_result.latency_ms = 100.0
        mock_result.context_used = {}
        mock_result.cache_hit = False

        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_query = AsyncMock(return_value=mock_result)

        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_rewriter

            result = await rewrite_query(mock_context, "test", force_rewrite=True)

        parsed = json.loads(result)
        assert parsed["success"] is True

    @pytest.mark.asyncio
    async def test_rewrite_query_exception(self, mock_context):
        """Test rewrite_query handles exceptions."""
        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.side_effect = Exception("Database error")

            result = await rewrite_query(mock_context, "test query")

        parsed = json.loads(result)
        assert parsed["success"] is False
        assert "Query rewriting failed" in parsed["error"]

    @pytest.mark.asyncio
    async def test_rewrite_query_interpretation_clear_query(self, mock_context):
        """Test interpretation for non-rewritten clear query."""
        mock_result = MagicMock()
        mock_result.original_query = "list all projects"
        mock_result.rewritten_query = "list all projects"
        mock_result.was_rewritten = False
        mock_result.confidence = 0.95
        mock_result.llm_provider = None
        mock_result.latency_ms = 0
        mock_result.context_used = {}
        mock_result.cache_hit = True

        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_query = AsyncMock(return_value=mock_result)

        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_rewriter

            result = await rewrite_query(mock_context, "list all projects")

        parsed = json.loads(result)
        assert parsed["interpretation"]["query_type"] == "clear"
        assert parsed["interpretation"]["rewriting_quality"] == "high"
        assert parsed["interpretation"]["cache_efficiency"] == "cache hit"

    @pytest.mark.asyncio
    async def test_rewrite_query_interpretation_ambiguous_query(self, mock_context):
        """Test interpretation for rewritten ambiguous query."""
        mock_result = MagicMock()
        mock_result.original_query = "what did I learn"
        mock_result.rewritten_query = "what did I learn about session-buddy"
        mock_result.was_rewritten = True
        mock_result.confidence = 0.6
        mock_result.llm_provider = "minimax"
        mock_result.latency_ms = 200.0
        mock_result.context_used = {}
        mock_result.cache_hit = False

        mock_rewriter = MagicMock()
        mock_rewriter.rewrite_query = AsyncMock(return_value=mock_result)

        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = mock_rewriter

            result = await rewrite_query(mock_context, "what did I learn")

        parsed = json.loads(result)
        assert parsed["interpretation"]["query_type"] == "ambiguous"
        assert parsed["interpretation"]["rewriting_quality"] == "medium"
        assert parsed["interpretation"]["cache_efficiency"] == "new rewrite"


class TestQueryRewriteStats:
    """Tests for query_rewrite_stats function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock FastMCP Context."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_stats_success(self, mock_context):
        """Test successful stats retrieval."""
        with patch("session_buddy.di.depends") as mock_depends:
            mock_rewriter = MagicMock()
            mock_depends.get_sync.return_value = mock_rewriter

            mock_rewriter.get_stats.return_value = {
                "total_rewrites": 150,
                "cache_hit_rate": 0.75,
                "llm_failures": 3,
                "avg_latency_ms": 120.0,
            }

            result = await query_rewrite_stats(mock_context)

        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["stats"]["total_rewrites"] == 150
        assert parsed["health"]["cache_hit_rate_category"] == "Excellent"
        assert parsed["health"]["llm_reliability"] == "Some failures"
        assert parsed["health"]["avg_latency_category"] == "Good"

    @pytest.mark.asyncio
    async def test_stats_no_rewriter(self, mock_context):
        """Test stats when rewriter not initialized."""
        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.return_value = None

            result = await query_rewrite_stats(mock_context)

        parsed = json.loads(result)
        assert parsed["success"] is False
        assert "not initialized" in parsed["error"]

    @pytest.mark.asyncio
    async def test_stats_exception(self, mock_context):
        """Test stats handles exceptions."""
        with patch("session_buddy.di.depends") as mock_depends:
            mock_depends.get_sync.side_effect = Exception("Connection failed")

            result = await query_rewrite_stats(mock_context)

        parsed = json.loads(result)
        assert parsed["success"] is False
        assert "Failed to retrieve" in parsed["error"]

    @pytest.mark.asyncio
    async def test_stats_health_calculation(self, mock_context):
        """Test that health is calculated correctly from stats."""
        with patch("session_buddy.di.depends") as mock_depends:
            mock_rewriter = MagicMock()
            mock_depends.get_sync.return_value = mock_rewriter

            mock_rewriter.get_stats.return_value = {
                "total_rewrites": 300,
                "cache_hit_rate": 0.45,
                "llm_failures": 0,
                "avg_latency_ms": 80.0,
            }

            result = await query_rewrite_stats(mock_context)

        parsed = json.loads(result)
        assert parsed["health"]["total_rewrites"] == 300
        assert parsed["health"]["cache_hit_rate_category"] == "Needs warming"
        assert parsed["health"]["llm_reliability"] == "Good"
        assert parsed["health"]["avg_latency_category"] == "Excellent"

    @pytest.mark.asyncio
    async def test_stats_with_high_failure_rate(self, mock_context):
        """Test stats with high LLM failure rate."""
        with patch("session_buddy.di.depends") as mock_depends:
            mock_rewriter = MagicMock()
            mock_depends.get_sync.return_value = mock_rewriter

            mock_rewriter.get_stats.return_value = {
                "total_rewrites": 1000,
                "cache_hit_rate": 0.9,
                "llm_failures": 50,
                "avg_latency_ms": 300.0,
            }

            result = await query_rewrite_stats(mock_context)

        parsed = json.loads(result)
        assert parsed["health"]["llm_reliability"] == "High failure rate"
        assert parsed["health"]["avg_latency_category"] == "Slow"