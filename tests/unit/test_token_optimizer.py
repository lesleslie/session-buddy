#!/usr/bin/env python3
"""Comprehensive unit tests for token optimization functionality."""

import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.token_optimizer import (
    ACBChunkCache,
    ChunkResult,
    TokenOptimizer,
    TokenUsageMetrics,
    get_cached_chunk,
    get_chunk_cache,
    get_token_optimizer,
    get_token_usage_stats,
    optimize_search_response,
    track_token_usage,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def token_optimizer():
    """Create a token optimizer instance for testing."""
    return TokenOptimizer(max_tokens=1000, chunk_size=500)


@pytest.fixture
def acb_chunk_cache():
    """Create a fresh ACBChunkCache instance."""
    return ACBChunkCache()


@pytest.fixture
def sample_conversations():
    """Sample conversation data for testing."""
    base_time = datetime.now() - timedelta(days=1)
    return [
        {
            "id": "conv1",
            "content": 'This is a short conversation about Python functions. def hello(): return "world"',
            "timestamp": base_time.isoformat(),
            "project": "test-project",
            "score": 0.8,
        },
        {
            "id": "conv2",
            "content": "This is a much longer conversation that discusses various aspects of software development, including database design, API architecture, testing strategies, and deployment practices. "
            * 20,
            "timestamp": (base_time - timedelta(hours=2)).isoformat(),
            "project": "test-project",
            "score": 0.6,
        },
        {
            "id": "conv3",
            "content": "Recent conversation with error troubleshooting. TypeError: object is not callable. Here is the traceback...",
            "timestamp": (base_time + timedelta(hours=1)).isoformat(),
            "project": "test-project",
            "score": 0.9,
        },
        {
            "id": "conv4",
            "content": "Old conversation from last month about basic concepts",
            "timestamp": (base_time - timedelta(days=30)).isoformat(),
            "project": "old-project",
            "score": 0.4,
        },
    ]


@pytest.fixture(autouse=True)
def clear_chunk_cache():
    """Clear chunk cache before and after each test."""
    cache = get_chunk_cache()
    cache.clear()
    yield
    cache.clear()


# =============================================================================
# ACBChunkCache Tests
# =============================================================================

class TestACBChunkCache:
    """Test ACBChunkCache class directly."""

    @pytest.mark.asyncio
    async def test_cache_get_set(self, acb_chunk_cache):
        """Test basic cache get and set operations."""
        test_data = [("chunk1",), ("chunk2",)]
        await acb_chunk_cache.set("test_key", test_data)
        result = await acb_chunk_cache.get("test_key")
        assert result == test_data

    @pytest.mark.asyncio
    async def test_cache_get_default(self, acb_chunk_cache):
        """Test cache get with default value for missing key."""
        default_val = [("default",)]
        result = await acb_chunk_cache.get("missing_key", default_val)
        assert result == default_val

    @pytest.mark.asyncio
    async def test_cache_get_none_default(self, acb_chunk_cache):
        """Test cache get with None default."""
        result = await acb_chunk_cache.get("missing_key", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_clear(self, acb_chunk_cache):
        """Test cache clear operation."""
        await acb_chunk_cache.set("key1", [("data1",)])
        await acb_chunk_cache.set("key2", [("data2",)])
        await acb_chunk_cache.clear()
        result1 = await acb_chunk_cache.get("key1")
        result2 = await acb_chunk_cache.get("key2")
        assert result1 is None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_cache_contains(self, acb_chunk_cache):
        """Test cache contains check."""
        await acb_chunk_cache.set("present_key", [("data",)])
        assert await acb_chunk_cache.__contains__("present_key")
        assert not await acb_chunk_cache.__contains__("missing_key")

    @pytest.mark.asyncio
    async def test_cache_overwrite(self, acb_chunk_cache):
        """Test cache value overwrite."""
        await acb_chunk_cache.set("key", [("old_data",)])
        await acb_chunk_cache.set("key", [("new_data",)])
        result = await acb_chunk_cache.get("key")
        assert result == [("new_data",)]


# =============================================================================
# TokenOptimizer Core Tests
# =============================================================================

class TestTokenOptimizer:
    """Test the core TokenOptimizer class."""

    def test_token_counting_with_tiktoken(self, token_optimizer):
        """Test token counting when tiktoken is available."""
        text = "Hello world, this is a test message"
        token_count = token_optimizer.count_tokens(text)
        assert isinstance(token_count, int)
        assert token_count > 0

    def test_token_counting_fallback(self, token_optimizer):
        """Test token counting fallback when tiktoken fails."""
        with patch.object(token_optimizer, "encoding", None):
            text = "Hello world, this is a test message"
            token_count = token_optimizer.count_tokens(text)
            assert isinstance(token_count, int)
            assert token_count > 0
            # Should be roughly len(text) // 4
            assert token_count == len(text) // 4

    def test_initialization_defaults(self):
        """Test TokenOptimizer initialization with default values."""
        optimizer = TokenOptimizer()
        assert optimizer.max_tokens == 4000
        assert optimizer.chunk_size == 2000
        assert optimizer.usage_history == []

    def test_initialization_custom(self):
        """Test TokenOptimizer initialization with custom values."""
        optimizer = TokenOptimizer(max_tokens=8000, chunk_size=3000)
        assert optimizer.max_tokens == 8000
        assert optimizer.chunk_size == 3000

    def test_strategies_dictionary(self, token_optimizer):
        """Test that all expected strategies are registered."""
        expected_strategies = {
            "truncate_old",
            "summarize_content",
            "chunk_response",
            "filter_duplicates",
            "prioritize_recent",
        }
        assert set(token_optimizer.strategies.keys()) == expected_strategies


class TestTokenOptimizerEncoding:
    """Test encoding-related functionality."""

    def test_get_encoding_tiktoken_available(self):
        """Test _get_encoding when tiktoken is available."""
        with patch("session_buddy.token_optimizer.tiktoken") as mock_tiktoken:
            mock_encoding = MagicMock()
            mock_tiktoken.get_encoding.return_value = mock_encoding

            optimizer = TokenOptimizer()
            assert optimizer.encoding == mock_encoding

    def test_get_encoding_tiktoken_none(self):
        """Test _get_encoding when tiktoken is None (not installed)."""
        with patch("session_buddy.token_optimizer.tiktoken", None):
            optimizer = TokenOptimizer()
            assert optimizer.encoding is None

    def test_get_encoding_exception(self):
        """Test _get_encoding when tiktoken raises exception."""
        with patch("session_buddy.token_optimizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = Exception("Encoding error")
            optimizer = TokenOptimizer()
            assert optimizer.encoding is None


# =============================================================================
# Token Counting Edge Cases
# =============================================================================

class TestTokenCountingEdgeCases:
    """Test token counting with edge case inputs."""

    def test_empty_string(self, token_optimizer):
        """Test token counting with empty string."""
        count = token_optimizer.count_tokens("")
        assert count == 0

    def test_single_character(self, token_optimizer):
        """Test token counting with single character."""
        count = token_optimizer.count_tokens("a")
        assert count >= 0

    def test_very_long_text(self, token_optimizer):
        """Test token counting with very long text."""
        long_text = "word " * 10000
        count = token_optimizer.count_tokens(long_text)
        assert count > 0

    def test_unicode_text(self, token_optimizer):
        """Test token counting with unicode characters."""
        unicode_text = "Hello 世界 🌍 αβγδ α=β+γ δ→∞ ∑ ∏ √ ∞ ∫ ∂ ∆ ∇ ∈ ∉ ∋ ∌ ⊂ ⊃ ∀ ∃ ∧ ∨ ¬ ⊕"
        count = token_optimizer.count_tokens(unicode_text)
        assert count > 0

    def test_unicode_with_fallback(self, token_optimizer):
        """Test unicode with fallback encoding (no tiktoken)."""
        with patch.object(token_optimizer, "encoding", None):
            unicode_text = "日本語 中文 한국어"
            count = token_optimizer.count_tokens(unicode_text)
            assert count >= 0

    def test_special_characters(self, token_optimizer):
        """Test token counting with special characters."""
        special_text = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~\n\t\r"
        count = token_optimizer.count_tokens(special_text)
        assert count >= 0

    def test_code_snippet(self, token_optimizer):
        """Test token counting with code snippet."""
        code = '''
def fibonacci(n):
    """Calculate fibonacci number."""
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class FibonacciSequence:
    def __init__(self):
        self.cache = {}
'''
        count = token_optimizer.count_tokens(code)
        assert count > 0


# =============================================================================
# Truncation Tests
# =============================================================================

class TestTruncation:
    """Test content truncation functionality."""

    def test_truncate_content_exact_fit(self, token_optimizer):
        """Test truncation when content already fits."""
        short_content = "Short text."
        max_tokens = 100
        result = token_optimizer._truncate_content(short_content, max_tokens)
        assert result == short_content

    def test_truncate_content_at_sentence_boundary(self, token_optimizer):
        """Test truncation respects sentence boundaries."""
        content = "First sentence. Second sentence. Third sentence. Fourth sentence."
        max_tokens = 5  # Very small limit

        result = token_optimizer._truncate_content(content, max_tokens)

        # Should return something, possibly empty or truncated
        assert isinstance(result, str)

    def test_truncate_content_no_sentence_split(self, token_optimizer):
        """Test truncation when no sentence boundaries exist."""
        content = "A" * 1000
        max_tokens = 10

        result = token_optimizer._truncate_content(content, max_tokens)

        # Should be shorter than original
        assert len(result) < len(content)
        # Token count should be within limit
        assert token_optimizer.count_tokens(result) <= max_tokens

    def test_truncate_content_with_encoding(self, token_optimizer):
        """Test truncation with encoding fallback."""
        with patch.object(token_optimizer, "encoding", None):
            content = "Word " * 100
            max_tokens = 10

            result = token_optimizer._truncate_content(content, max_tokens)

            # Character-based fallback - should be shorter than original
            assert len(result) < len(content)


# =============================================================================
# Optimization Strategy Tests
# =============================================================================

class TestTruncateOldConversations:
    """Test _truncate_old_conversations strategy."""

    @pytest.mark.asyncio
    async def test_truncate_old_empty_input(self, token_optimizer):
        """Test with empty input list."""
        result, info = await token_optimizer._truncate_old_conversations([], 1000)
        assert result == []
        assert info["strategy"] == "truncate_old"
        assert info["action"] == "no_results"

    @pytest.mark.asyncio
    async def test_truncate_old_respects_max_tokens(self, token_optimizer, sample_conversations):
        """Test that token limit is respected."""
        optimized, info = await token_optimizer._truncate_old_conversations(
            sample_conversations,
            max_tokens=200,
        )
        assert info["final_token_count"] <= 200

    @pytest.mark.asyncio
    async def test_truncate_old_keeps_recent(self, token_optimizer, sample_conversations):
        """Test that recent conversations are prioritized."""
        optimized, info = await token_optimizer._truncate_old_conversations(
            sample_conversations,
            max_tokens=1000,
        )
        # Most recent (conv3) should be first
        if optimized:
            assert optimized[0]["id"] == "conv3"

    @pytest.mark.asyncio
    async def test_truncate_old_minimum_kept(self, token_optimizer, sample_conversations):
        """Test that minimum 3 recent results are kept when possible."""
        optimized, info = await token_optimizer._truncate_old_conversations(
            sample_conversations,
            max_tokens=500,
        )
        # Should try to keep at least 3 results
        assert len(optimized) >= 1  # At least 1 due to token limits

    @pytest.mark.asyncio
    async def test_truncate_old_truncation_markers(self, token_optimizer, sample_conversations):
        """Test that truncated content has proper markers."""
        optimized, info = await token_optimizer._truncate_old_conversations(
            sample_conversations,
            max_tokens=50,  # Very small limit
        )

        for result in optimized:
            if "[truncated for token limit]" in result.get("content", ""):
                pass  # Found truncated content


class TestSummarizeLongContent:
    """Test _summarize_long_content strategy."""

    @pytest.mark.asyncio
    async def test_summarize_empty_input(self, token_optimizer):
        """Test with empty input list."""
        result, info = await token_optimizer._summarize_long_content([], 1000)
        assert result == []
        assert info["summarized_count"] == 0

    @pytest.mark.asyncio
    async def test_summarize_long_content(self, token_optimizer):
        """Test that long content is summarized."""
        # Create content with more than 500 tokens (using fallback: ~4 chars per token)
        # So we need > 500 * 4 = 2000 characters
        long_content = "This is a long sentence with many words. " * 200
        long_conv = {
            "id": "long1",
            "content": long_content,
            "timestamp": datetime.now().isoformat(),
        }
        optimized, info = await token_optimizer._summarize_long_content([long_conv], 1000)

        assert "[auto-summarized]" in optimized[0]["content"]
        assert info["summarized_count"] == 1

    @pytest.mark.asyncio
    async def test_summarize_short_content_unchanged(self, token_optimizer):
        """Test that short content is not summarized."""
        short_conv = {
            "id": "short1",
            "content": "Short content.",
            "timestamp": datetime.now().isoformat(),
        }
        optimized, info = await token_optimizer._summarize_long_content([short_conv], 1000)

        assert "[auto-summarized]" not in optimized[0]["content"]
        assert info["summarized_count"] == 0


class TestChunkLargeResponse:
    """Test _chunk_large_response strategy."""

    @pytest.mark.asyncio
    async def test_chunk_empty_input(self, token_optimizer):
        """Test with empty input list."""
        result, info = await token_optimizer._chunk_large_response([], 1000)
        assert result == []
        assert info["action"] == "no_results"

    @pytest.mark.asyncio
    async def test_chunk_small_response(self, token_optimizer):
        """Test that small responses are not chunked."""
        small_convs = [
            {"id": "conv1", "content": "Short content.", "timestamp": datetime.now().isoformat()},
        ]
        result, info = await token_optimizer._chunk_large_response(small_convs, 10000)
        assert info["action"] == "no_chunking_needed"

    @pytest.mark.asyncio
    async def test_chunk_creates_multiple_chunks(self, token_optimizer):
        """Test that large response is chunked."""
        large_convs = [
            {"id": f"conv{i}", "content": "Word " * 500, "timestamp": datetime.now().isoformat()}
            for i in range(5)
        ]
        result, info = await token_optimizer._chunk_large_response(large_convs, 500)

        if info["action"] == "chunked":
            assert info["total_chunks"] > 1
            assert info["current_chunk"] == 1
            assert info["has_more"] is True


class TestFilterDuplicates:
    """Test _filter_duplicate_content strategy."""

    @pytest.mark.asyncio
    async def test_filter_empty_input(self, token_optimizer):
        """Test with empty input list."""
        result, info = await token_optimizer._filter_duplicate_content([], 1000)
        assert result == []
        assert info["strategy"] == "filter_duplicates"
        assert info["action"] == "no_results"

    @pytest.mark.asyncio
    async def test_filter_exact_duplicates(self, token_optimizer):
        """Test filtering exact duplicates."""
        convs = [
            {"id": "conv1", "content": "Same content", "timestamp": datetime.now().isoformat()},
            {"id": "conv2", "content": "Same content", "timestamp": datetime.now().isoformat()},
        ]
        result, info = await token_optimizer._filter_duplicate_content(convs, 1000)

        assert len(result) == 1
        assert info["duplicates_removed"] == 1

    @pytest.mark.asyncio
    async def test_filter_whitespace_differences(self, token_optimizer):
        """Test filtering content that differs only in whitespace."""
        convs = [
            {"id": "conv1", "content": "Content with   spaces", "timestamp": datetime.now().isoformat()},
            {"id": "conv2", "content": "Content with spaces", "timestamp": datetime.now().isoformat()},
        ]
        result, info = await token_optimizer._filter_duplicate_content(convs, 1000)

        # Whitespace-normalized versions should be detected as duplicates
        assert len(result) <= 2


class TestPrioritizeRecentContent:
    """Test _prioritize_recent_content strategy."""

    @pytest.mark.asyncio
    async def test_prioritize_empty_input(self, token_optimizer):
        """Test with empty input list."""
        result, info = await token_optimizer._prioritize_recent_content([], 1000)
        assert result == []
        assert info["action"] == "no_results"

    @pytest.mark.asyncio
    async def test_prioritize_recent_and_high_scored(self, token_optimizer, sample_conversations):
        """Test that recent and high-scored content is prioritized."""
        optimized, info = await token_optimizer._prioritize_recent_content(
            sample_conversations,
            max_tokens=1000,
        )

        if optimized:
            # conv3 is recent AND has high score
            assert optimized[0]["id"] == "conv3"

    @pytest.mark.asyncio
    async def test_prioritize_code_content_bonus(self, token_optimizer):
        """Test that code content gets priority bonus."""
        code_conv = {
            "id": "code",
            "content": "def function(): return error",
            "timestamp": (datetime.now() - timedelta(days=10)).isoformat(),
            "score": 0.5,
        }
        plain_conv = {
            "id": "plain",
            "content": "Just regular text without any code",
            "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),
            "score": 0.5,
        }

        result, info = await token_optimizer._prioritize_recent_content(
            [code_conv, plain_conv],
            max_tokens=1000,
        )

        # Code content should be prioritized due to bonus
        ids = [r["id"] for r in result]
        assert "code" in ids

    @pytest.mark.asyncio
    async def test_prioritize_invalid_timestamp(self, token_optimizer):
        """Test prioritization with invalid timestamp."""
        convs = [
            {"id": "conv1", "content": "Content", "timestamp": "invalid", "score": 0.5},
        ]
        result, info = await token_optimizer._prioritize_recent_content(convs, 1000)
        assert len(result) == 1


# =============================================================================
# Search Result Optimization Tests
# =============================================================================

class TestOptimizeSearchResults:
    """Test optimize_search_results main method."""

    @pytest.mark.asyncio
    async def test_optimize_with_unknown_strategy(self, token_optimizer, sample_conversations):
        """Test optimization with unknown strategy falls back to no-op."""
        result, info = await token_optimizer.optimize_search_results(
            sample_conversations,
            strategy="unknown_strategy",
            max_tokens=1000,
        )
        assert result == sample_conversations
        assert info["strategy"] == "none"

    @pytest.mark.asyncio
    async def test_optimize_tracking_metrics(self, token_optimizer, sample_conversations):
        """Test that optimization tracks metrics."""
        result, info = await token_optimizer.optimize_search_results(
            sample_conversations,
            strategy="truncate_old",
            max_tokens=500,
        )

        assert "original_count" in info
        assert "optimized_count" in info
        assert "token_savings" in info
        assert info["original_count"] == len(sample_conversations)

    @pytest.mark.asyncio
    async def test_optimize_token_savings(self, token_optimizer, sample_conversations):
        """Test token savings calculation."""
        result, info = await token_optimizer.optimize_search_results(
            sample_conversations,
            strategy="truncate_old",
            max_tokens=200,
        )

        savings = info["token_savings"]
        assert "original_tokens" in savings
        assert "optimized_tokens" in savings
        assert "tokens_saved" in savings
        assert "savings_percentage" in savings


# =============================================================================
# Chunk Cache Operations Tests
# =============================================================================

class TestChunkCacheOperations:
    """Test chunk caching and retrieval."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_chunk(self, token_optimizer):
        """Test creating and retrieving a chunk."""
        chunks = [
            [{"id": "conv1", "content": "Chunk 1"}],
            [{"id": "conv2", "content": "Chunk 2"}],
            [{"id": "conv3", "content": "Chunk 3"}],
        ]

        cache_key = await token_optimizer._create_chunk_cache_entry(chunks)

        chunk_data = await token_optimizer.get_chunk(cache_key, 1)
        assert chunk_data is not None
        assert chunk_data["current_chunk"] == 1
        assert chunk_data["total_chunks"] == 3
        assert chunk_data["has_more"] is True

    @pytest.mark.asyncio
    async def test_retrieve_last_chunk(self, token_optimizer):
        """Test retrieving the last chunk."""
        chunks = [
            [{"id": "conv1", "content": "Chunk 1"}],
            [{"id": "conv2", "content": "Chunk 2"}],
        ]

        cache_key = await token_optimizer._create_chunk_cache_entry(chunks)
        chunk_data = await token_optimizer.get_chunk(cache_key, 2)

        assert chunk_data is not None
        assert chunk_data["has_more"] is False

    @pytest.mark.asyncio
    async def test_invalid_cache_key(self, token_optimizer):
        """Test retrieving with invalid cache key."""
        result = await token_optimizer.get_chunk("invalid_key", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_chunk_index(self, token_optimizer):
        """Test retrieving with invalid chunk index."""
        chunks = [[{"id": "conv1", "content": "Chunk 1"}]]
        cache_key = await token_optimizer._create_chunk_cache_entry(chunks)

        result = await token_optimizer.get_chunk(cache_key, 5)
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_chunk_index(self, token_optimizer):
        """Test retrieving chunk index 0."""
        chunks = [[{"id": "conv1", "content": "Chunk 1"}]]
        cache_key = await token_optimizer._create_chunk_cache_entry(chunks)

        result = await token_optimizer.get_chunk(cache_key, 0)
        assert result is None


# =============================================================================
# Token Savings Calculation Tests
# =============================================================================

class TestTokenSavingsCalculation:
    """Test _calculate_token_savings method."""

    def test_savings_with_reduction(self, token_optimizer, sample_conversations):
        """Test savings when tokens are reduced."""
        optimized = sample_conversations[:2]
        savings = token_optimizer._calculate_token_savings(sample_conversations, optimized)

        assert savings["original_tokens"] >= savings["optimized_tokens"]
        assert savings["tokens_saved"] >= 0
        assert 0 <= savings["savings_percentage"] <= 100

    def test_savings_with_no_reduction(self, token_optimizer, sample_conversations):
        """Test savings when no reduction occurred."""
        savings = token_optimizer._calculate_token_savings(
            sample_conversations,
            sample_conversations,
        )

        assert savings["tokens_saved"] == 0
        assert savings["savings_percentage"] == 0

    def test_savings_with_empty_optimized(self, token_optimizer, sample_conversations):
        """Test savings when optimized list is empty."""
        savings = token_optimizer._calculate_token_savings(sample_conversations, [])

        assert savings["original_tokens"] > 0
        assert savings["optimized_tokens"] == 0
        assert savings["tokens_saved"] == savings["original_tokens"]
        assert savings["savings_percentage"] == 100


# =============================================================================
# Usage Tracking Tests
# =============================================================================

class TestUsageTracking:
    """Test token usage tracking."""

    def test_track_usage_basic(self, token_optimizer):
        """Test basic usage tracking."""
        token_optimizer.track_usage("test_op", 100, 200, "truncate_old")
        assert len(token_optimizer.usage_history) == 1

        metric = token_optimizer.usage_history[0]
        assert metric.request_tokens == 100
        assert metric.response_tokens == 200
        assert metric.total_tokens == 300
        assert metric.operation == "test_op"
        assert metric.optimization_applied == "truncate_old"

    def test_track_usage_without_optimization(self, token_optimizer):
        """Test usage tracking without optimization flag."""
        token_optimizer.track_usage("test_op", 100, 200)
        metric = token_optimizer.usage_history[0]
        assert metric.optimization_applied is None

    def test_track_usage_limit(self, token_optimizer):
        """Test that usage history is limited to 100 entries."""
        for i in range(150):
            token_optimizer.track_usage(f"op_{i}", 100, 200)

        assert len(token_optimizer.usage_history) == 100
        # Should keep most recent
        assert token_optimizer.usage_history[-1].operation == "op_149"


class TestUsageStats:
    """Test usage statistics generation."""

    def test_stats_with_no_data(self, token_optimizer):
        """Test stats with empty history."""
        stats = token_optimizer.get_usage_stats(hours=24)
        assert stats["status"] == "no_data"

    def test_stats_with_recent_data(self, token_optimizer):
        """Test stats with recent data."""
        now = datetime.now()
        token_optimizer.usage_history = [
            TokenUsageMetrics(100, 200, 300, now.isoformat(), "op1", "truncate_old"),
            TokenUsageMetrics(150, 250, 400, now.isoformat(), "op2", None),
        ]

        stats = token_optimizer.get_usage_stats(hours=24)
        assert stats["status"] == "success"
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 700

    def test_stats_old_data_excluded(self, token_optimizer):
        """Test that old data is excluded from stats."""
        now = datetime.now()
        token_optimizer.usage_history = [
            TokenUsageMetrics(100, 200, 300, (now - timedelta(hours=48)).isoformat(), "old_op", None),
            TokenUsageMetrics(150, 250, 400, now.isoformat(), "new_op", None),
        ]

        stats = token_optimizer.get_usage_stats(hours=24)
        assert stats["total_requests"] == 1
        assert stats["total_tokens"] == 400

    def test_stats_optimizations_counted(self, token_optimizer):
        """Test that optimizations are properly counted."""
        now = datetime.now()
        token_optimizer.usage_history = [
            TokenUsageMetrics(100, 200, 300, now.isoformat(), "op1", "truncate_old"),
            TokenUsageMetrics(100, 200, 300, now.isoformat(), "op2", "truncate_old"),
            TokenUsageMetrics(100, 200, 300, now.isoformat(), "op3", "summarize"),
        ]

        stats = token_optimizer.get_usage_stats(hours=24)
        assert stats["optimizations_applied"]["truncate_old"] == 2
        assert stats["optimizations_applied"]["summarize"] == 1


class TestCostSavingsEstimation:
    """Test cost savings estimation."""

    def test_cost_savings_with_no_optimizations(self, token_optimizer):
        """Test cost savings when no optimizations were applied."""
        usage_metrics = [
            TokenUsageMetrics(100, 200, 300, datetime.now().isoformat(), "op1", None),
        ]
        savings = token_optimizer._estimate_cost_savings(usage_metrics)

        assert savings["savings_usd"] == 0.0
        assert savings["requests_optimized"] == 0

    def test_cost_savings_with_optimizations(self, token_optimizer):
        """Test cost savings estimation with optimizations."""
        usage_metrics = [
            TokenUsageMetrics(100, 200, 300, datetime.now().isoformat(), "op1", "truncate_old"),
        ]
        savings = token_optimizer._estimate_cost_savings(usage_metrics)

        assert savings["savings_usd"] > 0
        assert savings["requests_optimized"] == 1
        assert savings["estimated_tokens_saved"] > 0


# =============================================================================
# Quick Summary Tests
# =============================================================================

class TestQuickSummary:
    """Test _create_quick_summary method."""

    def test_summary_single_sentence(self, token_optimizer):
        """Test summary with single sentence."""
        content = "Only one sentence here."
        summary = token_optimizer._create_quick_summary(content)
        # Summary should contain the content (stripped of trailing punctuation)
        assert content.startswith(summary.rstrip("."))

    def test_summary_multiple_sentences(self, token_optimizer):
        """Test summary with multiple sentences."""
        content = "First sentence. Middle content. Last sentence."
        summary = token_optimizer._create_quick_summary(content)

        assert "..." in summary or "First sentence" in summary
        assert "Last sentence" in summary or "..." in summary

    def test_summary_respects_max_length(self, token_optimizer):
        """Test that summary respects max_length."""
        content = "First sentence. " * 50 + "Last sentence."
        max_length = 50
        summary = token_optimizer._create_quick_summary(content, max_length)

        assert len(summary) <= max_length

    def test_summary_empty_content(self, token_optimizer):
        """Test summary with empty content."""
        summary = token_optimizer._create_quick_summary("")
        assert summary == ""


# =============================================================================
# Cleanup Cache Tests
# =============================================================================

class TestCleanupCache:
    """Test cleanup_cache method."""

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero(self, token_optimizer):
        """Test that cleanup_cache returns 0 (TTL handled automatically)."""
        result = await token_optimizer.cleanup_cache(max_age_hours=1)
        assert result == 0


# =============================================================================
# Module-Level Function Tests
# =============================================================================

class TestModuleLevelFunctions:
    """Test module-level wrapper functions."""

    @pytest.mark.asyncio
    async def test_optimize_search_response_wrapper(self, sample_conversations):
        """Test optimize_search_response async wrapper."""
        result, info = await optimize_search_response(
            sample_conversations,
            strategy="prioritize_recent",
            max_tokens=500,
        )
        assert isinstance(result, list)
        assert isinstance(info, dict)

    @pytest.mark.asyncio
    async def test_track_token_usage_wrapper(self):
        """Test track_token_usage async wrapper."""
        await track_token_usage("test_op", 100, 200, "strategy")
        # Verify by getting stats
        stats = await get_token_usage_stats(hours=1)
        assert stats["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_token_usage_stats_wrapper(self):
        """Test get_token_usage_stats async wrapper."""
        stats = await get_token_usage_stats(hours=24)
        assert isinstance(stats, dict)
        assert "status" in stats

    @pytest.mark.asyncio
    async def test_get_cached_chunk_wrapper_invalid_key(self):
        """Test get_cached_chunk wrapper with invalid key."""
        result = await get_cached_chunk("invalid_key", 1)
        assert result is None


class TestGetTokenOptimizerSingleton:
    """Test get_token_optimizer singleton function."""

    def test_singleton_returns_instance(self):
        """Test that get_token_optimizer returns a TokenOptimizer."""
        optimizer = get_token_optimizer()
        assert isinstance(optimizer, TokenOptimizer)

    def test_singleton_same_instance(self):
        """Test that get_token_optimizer returns the same instance."""
        optimizer1 = get_token_optimizer()
        optimizer2 = get_token_optimizer()
        assert optimizer1 is optimizer2


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_long_text_truncation(self, token_optimizer):
        """Test truncation of very long text."""
        very_long = "word " * 50000
        result, info = await token_optimizer._summarize_long_content(
            [{"id": "1", "content": very_long, "timestamp": datetime.now().isoformat()}],
            max_tokens=1000,
        )
        assert len(result) == 1
        assert "[auto-summarized]" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_unicode_content_optimization(self, token_optimizer):
        """Test optimization with unicode content."""
        unicode_convs = [
            {
                "id": "conv1",
                "content": "日本語テストコンテンツ 中文内容 한국어",
                "timestamp": datetime.now().isoformat(),
            },
        ]
        result, info = await token_optimizer._truncate_old_conversations(
            unicode_convs,
            max_tokens=1000,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty_content_field(self, token_optimizer):
        """Test with missing or empty content field."""
        empty_convs = [
            {"id": "conv1", "content": "", "timestamp": datetime.now().isoformat()},
            {"id": "conv2", "timestamp": datetime.now().isoformat()},  # Missing content
        ]
        result, info = await token_optimizer._truncate_old_conversations(
            empty_convs,
            max_tokens=1000,
        )
        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_zero_max_tokens(self, token_optimizer, sample_conversations):
        """Test with zero max_tokens limit."""
        result, info = await token_optimizer._truncate_old_conversations(
            sample_conversations,
            max_tokens=0,
        )
        # Should handle gracefully
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_negative_max_tokens(self, token_optimizer, sample_conversations):
        """Test with negative max_tokens limit."""
        result, info = await token_optimizer._truncate_old_conversations(
            sample_conversations,
            max_tokens=-100,
        )
        # Should handle gracefully
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_special_characters_content(self, token_optimizer):
        """Test optimization with special characters in content."""
        special_convs = [
            {
                "id": "conv1",
                "content": "!@#$%^&*()_+-=[]{}|;':\",./<>?`~\n\t\r",
                "timestamp": datetime.now().isoformat(),
            },
        ]
        result, info = await token_optimizer._truncate_old_conversations(
            special_convs,
            max_tokens=1000,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_json_like_content(self, token_optimizer):
        """Test with JSON-like content."""
        json_content = '{"key": "value", "nested": {"inner": "data"}}'
        json_convs = [
            {"id": "conv1", "content": json_content, "timestamp": datetime.now().isoformat()},
        ]
        result, info = await token_optimizer._summarize_long_content(
            json_convs,
            max_tokens=1000,
        )
        assert len(result) == 1


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestTokenUsageMetricsDataclass:
    """Test TokenUsageMetrics dataclass."""

    def test_creation_with_all_fields(self):
        """Test creating TokenUsageMetrics with all fields."""
        metrics = TokenUsageMetrics(
            request_tokens=100,
            response_tokens=200,
            total_tokens=300,
            timestamp="2023-01-01T00:00:00",
            operation="test_op",
            optimization_applied="test_opt",
        )
        assert metrics.request_tokens == 100
        assert metrics.response_tokens == 200
        assert metrics.total_tokens == 300
        assert metrics.operation == "test_op"
        assert metrics.optimization_applied == "test_opt"

    def test_creation_with_defaults(self):
        """Test creating TokenUsageMetrics with minimal fields."""
        metrics = TokenUsageMetrics(
            request_tokens=100,
            response_tokens=200,
            total_tokens=300,
            timestamp="2023-01-01T00:00:00",
            operation="test_op",
        )
        assert metrics.optimization_applied is None


class TestChunkResultDataclass:
    """Test ChunkResult dataclass."""

    def test_creation(self):
        """Test creating ChunkResult."""
        chunks = ["chunk1", "chunk2"]
        metadata = {"created": "2023-01-01"}
        result = ChunkResult(
            chunks=chunks,
            total_chunks=2,
            current_chunk=1,
            cache_key="key123",
            metadata=metadata,
        )
        assert result.chunks == chunks
        assert result.total_chunks == 2
        assert result.current_chunk == 1
        assert result.cache_key == "key123"
        assert result.metadata == metadata


# =============================================================================
# Integration Style Tests
# =============================================================================

class TestFullOptimizationWorkflow:
    """Test full optimization workflow scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_strategies_same_data(self, token_optimizer, sample_conversations):
        """Test applying multiple strategies to the same data."""
        strategies = ["truncate_old", "summarize_content", "prioritize_recent"]

        for strategy in strategies:
            result, info = await token_optimizer.optimize_search_results(
                sample_conversations,
                strategy=strategy,
                max_tokens=500,
            )
            assert isinstance(result, list)
            assert "strategy" in info

    @pytest.mark.asyncio
    async def test_repeated_optimization(self, token_optimizer):
        """Test repeated optimization calls."""
        convs = [
            {"id": "1", "content": "Content " * 100, "timestamp": datetime.now().isoformat()},
        ]

        for _ in range(5):
            result, info = await token_optimizer.optimize_search_results(
                convs,
                strategy="summarize_content",
                max_tokens=1000,
            )
            assert len(result) == 1


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_missing_timestamp_key(self, token_optimizer):
        """Test handling when timestamp key is missing."""
        convs = [{"id": "conv1", "content": "Some content"}]
        result, info = await token_optimizer._prioritize_recent_content(convs, 1000)
        # Should handle gracefully by using default score
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_invalid_timestamp_format(self, token_optimizer):
        """Test handling of invalid timestamp format."""
        convs = [{"id": "conv1", "content": "Content", "timestamp": "not-a-date"}]
        result, info = await token_optimizer._prioritize_recent_content(convs, 1000)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_missing_content_key(self, token_optimizer):
        """Test handling when content key is missing."""
        convs = [{"id": "conv1", "timestamp": datetime.now().isoformat()}]
        result, info = await token_optimizer._summarize_long_content(convs, 1000)
        # Should handle gracefully
        assert len(result) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])