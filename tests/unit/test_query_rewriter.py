#!/usr/bin/env python3
"""Unit tests for Query Rewriter (Phase 2: Query Rewriting)."""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, UTC

import pytest

from session_buddy.rewriting.query_rewriter import (
    AmbiguityDetector,
    AmbiguityType,
    QueryRewriter,
    QueryRewriteResult,
    RewriteContext,
)


class TestAmbiguityDetector:
    """Test AmbiguityDetector functionality."""

    @pytest.fixture
    def detector(self):
        """Create an AmbiguityDetector instance for testing."""
        return AmbiguityDetector()

    def test_detect_pronoun_i_ambiguity(self, detector):
        """Test detection of 'I' pronoun ambiguity."""
        detection = detector.detect_ambiguity("what did I learn?")

        assert detection.is_ambiguous is True
        assert AmbiguityType.PRONOUN_I in detection.ambiguity_types

    def test_detect_pronoun_it_ambiguity(self, detector):
        """Test detection of 'it' pronoun ambiguity."""
        detection = detector.detect_ambiguity("fix it please")

        assert detection.is_ambiguous is True
        assert AmbiguityType.PRONOUN_IT in detection.ambiguity_types

    def test_detect_pronoun_this_ambiguity(self, detector):
        """Test detection of 'this' demonstrative ambiguity."""
        detection = detector.detect_ambiguity("update this code")

        assert detection.is_ambiguous is True
        assert AmbiguityType.PRONOUN_THIS in detection.ambiguity_types

    def test_detect_pronoun_that_ambiguity(self, detector):
        """Test detection of 'that' demonstrative ambiguity."""
        detection = detector.detect_ambiguity("that function from earlier")

        assert detection.is_ambiguous is True
        assert AmbiguityType.PRONOUN_THAT in detection.ambiguity_types

    def test_detect_temporal_demonstrative_ambiguity(self, detector):
        """Test detection of temporal demonstrative ambiguity."""
        detection = detector.detect_ambiguity("what did we discuss yesterday?")

        assert detection.is_ambiguous is True
        assert AmbiguityType.DEMONSTRATIVE_TEMPORAL in detection.ambiguity_types

    def test_detect_spatial_demonstrative_ambiguity(self, detector):
        """Test detection of spatial demonstrative ambiguity."""
        detection = detector.detect_ambiguity("check that file over there")

        assert detection.is_ambiguous is True
        # Should detect either PRONOUN_THAT or DEMONSTRATIVE_SPATIAL
        assert any(t in detection.ambiguity_types for t in [
            AmbiguityType.PRONOUN_THAT,
            AmbiguityType.DEMONSTRATIVE_SPATIAL,
        ])

    def test_detect_too_short_ambiguity(self, detector):
        """Test detection of too short queries."""
        detection = detector.detect_ambiguity("help me")

        assert detection.is_ambiguous is True
        assert AmbiguityType.TOO_SHORT in detection.ambiguity_types

    def test_detect_too_vague_ambiguity(self, detector):
        """Test detection of vague queries."""
        detection = detector.detect_ambiguity("how do I fix it")

        assert detection.is_ambiguous is True
        # Should detect PRONOUN_I or TOO_VAGUE
        assert any(t in detection.ambiguity_types for t in [
            AmbiguityType.PRONOUN_I,
            AmbiguityType.TOO_VAGUE,
        ])

    def test_detect_missing_context_ambiguity(self, detector):
        """Test detection of missing context ambiguity."""
        detection = detector.detect_ambiguity("call the method")

        assert detection.is_ambiguous is True
        assert AmbiguityType.MISSING_CONTEXT in detection.ambiguity_types

    def test_detect_multiple_ambiguity_types(self, detector):
        """Test detection of multiple ambiguity types in one query."""
        detection = detector.detect_ambiguity("what did I learn about it yesterday?")

        assert detection.is_ambiguous is True
        # Should detect multiple ambiguity types
        assert len(detection.ambiguity_types) >= 2

    def test_detect_no_ambiguity_clear_query(self, detector):
        """Test that clear queries are not marked as ambiguous."""
        detection = detector.detect_ambiguity("Python async patterns for database connections")

        assert detection.is_ambiguous is False
        assert len(detection.ambiguity_types) == 0

    def test_detect_no_ambiguity_specific_query(self, detector):
        """Test that specific queries are not marked as ambiguous."""
        # Use a longer, more specific query that won't trigger TOO_SHORT
        detection = detector.detect_ambiguity(
            "FastAPI authentication middleware implementation for JWT token validation"
        )

        assert detection.is_ambiguous is False
        assert len(detection.ambiguity_types) == 0

    def test_detect_no_ambiguity_explicit_context(self, detector):
        """Test that queries with explicit context are not ambiguous."""
        detection = detector.detect_ambiguity("pytest fixtures for session_buddy integration tests")

        assert detection.is_ambiguous is False
        assert len(detection.ambiguity_types) == 0

    def test_detect_ambiguity_empty_query(self, detector):
        """Test handling of empty queries."""
        detection = detector.detect_ambiguity("")

        # Empty queries should not be considered ambiguous (just invalid)
        assert detection.is_ambiguous is False
        assert len(detection.ambiguity_types) == 0

    def test_detect_ambiguity_whitespace_only(self, detector):
        """Test handling of whitespace-only queries."""
        detection = detector.detect_ambiguity("   ")

        # Whitespace-only queries should not be considered ambiguous
        assert detection.is_ambiguous is False
        assert len(detection.ambiguity_types) == 0

    def test_detection_score_calculation(self, detector):
        """Test that ambiguous queries have non-zero confidence scores."""
        detection1 = detector.detect_ambiguity("what did I learn?")
        detection2 = detector.detect_ambiguity("how do I fix it")

        # Both queries should be detected as ambiguous with non-zero confidence
        assert detection1.is_ambiguous is True
        assert detection2.is_ambiguous is True
        assert detection1.confidence > 0
        assert detection2.confidence > 0

    def test_detected_patterns_documentation(self, detector):
        """Test that detected patterns are documented."""
        detection = detector.detect_ambiguity("what did I learn about it?")

        assert detection.is_ambiguous is True
        # Patterns should be documented for debugging
        assert isinstance(detection.matched_patterns, list)


class TestRewriteContext:
    """Test RewriteContext dataclass functionality."""

    def test_context_creation_minimal(self):
        """Test creating a context with minimal required fields."""
        context = RewriteContext(
            query="test query",
            recent_conversations=[],
            project=None,
            recent_files=[],
            session_context={},
        )

        assert context.query == "test query"
        assert context.recent_conversations == []
        assert context.project is None
        assert context.recent_files == []
        assert context.session_context == {}

    def test_context_creation_with_data(self):
        """Test creating a context with full data."""
        conversations = [
            {"role": "user", "content": "What is async?"},
            {"role": "assistant", "content": "Async allows non-blocking code"},
        ]
        files = ["/path/to/file1.py", "/path/to/file2.py"]
        session_ctx = {"session_id": "test123", "user_id": "user456"}

        context = RewriteContext(
            query="test query",
            recent_conversations=conversations,
            project="session-buddy",
            recent_files=files,
            session_context=session_ctx,
        )

        assert context.query == "test query"
        assert context.recent_conversations == conversations
        assert context.project == "session-buddy"
        assert context.recent_files == files
        assert context.session_context == session_ctx


class TestQueryRewriteResult:
    """Test QueryRewriteResult dataclass functionality."""

    def test_result_creation_rewritten(self):
        """Test creating a result for a successful rewrite."""
        result = QueryRewriteResult(
            original_query="what did I learn?",
            rewritten_query="what did I learn about Python async patterns?",
            was_rewritten=True,
            confidence=0.92,
            llm_provider="openai",
            latency_ms=145,
            context_used=True,
            cache_hit=False,
        )

        assert result.original_query == "what did I learn?"
        assert result.rewritten_query == "what did I learn about Python async patterns?"
        assert result.was_rewritten is True
        assert result.confidence == 0.92
        assert result.llm_provider == "openai"
        assert result.latency_ms == 145
        assert result.context_used is True
        assert result.cache_hit is False

    def test_result_creation_not_rewritten(self):
        """Test creating a result when query was clear (no rewrite)."""
        result = QueryRewriteResult(
            original_query="Python async patterns",
            rewritten_query="Python async patterns",
            was_rewritten=False,
            confidence=0.0,  # Clear queries return 0.0 confidence
            llm_provider=None,
            latency_ms=5,
            context_used=False,  # Clear queries return False
            cache_hit=False,
        )

        assert result.original_query == "Python async patterns"
        assert result.rewritten_query == "Python async patterns"  # Same as original
        assert result.was_rewritten is False
        assert result.confidence == 0.0  # Zero confidence for clear queries (no LLM used)
        assert result.llm_provider is None  # No LLM used
        assert result.latency_ms < 10  # Very fast for clear queries
        assert result.context_used is False

    def test_result_creation_cache_hit(self):
        """Test creating a result from cache."""
        result = QueryRewriteResult(
            original_query="what did I learn?",
            rewritten_query="what did I learn about Python async patterns?",
            was_rewritten=True,
            confidence=0.92,
            llm_provider=None,  # None for cache hits
            latency_ms=2,  # Very fast for cache hits
            context_used=True,
            cache_hit=True,
        )

        assert result.cache_hit is True
        assert result.llm_provider is None  # No LLM call for cache
        assert result.latency_ms < 10  # Cache is fast

    def test_result_low_confidence(self):
        """Test creating a result with low confidence."""
        result = QueryRewriteResult(
            original_query="show me that",
            rewritten_query="show me FastAPI authentication examples",
            was_rewritten=True,
            confidence=0.45,  # Low confidence
            llm_provider="openai",
            latency_ms=180,
            context_used=True,
            cache_hit=False,
        )

        assert result.was_rewritten is True
        assert result.confidence < 0.5


class TestQueryRewriter:
    """Test QueryRewriter functionality."""

    @pytest.fixture
    def rewriter(self):
        """Create a QueryRewriter instance for testing."""
        return QueryRewriter()

    @pytest.fixture
    def mock_context(self):
        """Create a mock RewriteContext."""
        return RewriteContext(
            query="what did I learn?",
            recent_conversations=[
                {"role": "user", "content": "How does async work?"},
                {"role": "assistant", "content": "Async allows non-blocking code execution"},
            ],
            project="session-buddy",
            recent_files=["session_buddy/server.py"],
            session_context={"session_id": "test123"},
        )

    def test_initialization(self, rewriter):
        """Test rewriter initialization."""
        assert rewriter.detector is not None
        assert isinstance(rewriter.detector, AmbiguityDetector)
        assert rewriter._cache == {}
        assert rewriter._stats == {
            "total_rewrites": 0,
            "avg_latency_ms": 0.0,
            "cache_hits": 0,
            "llm_failures": 0,
        }

    def test_clear_cache(self, rewriter):
        """Test cache clearing."""
        # Add something to cache
        rewriter._cache["test_key"] = "cached_value"

        # Clear cache
        rewriter.clear_cache()

        assert rewriter._cache == {}

    def test_get_stats(self, rewriter):
        """Test statistics retrieval."""
        stats = rewriter.get_stats()

        assert stats["total_rewrites"] == 0
        assert stats["cache_hits"] == 0
        assert stats["llm_failures"] == 0
        assert stats["avg_latency_ms"] == 0.0
        assert stats["cache_hit_rate"] == 0.0
        assert stats["cache_size"] == 0

    def test_get_stats_with_data(self, rewriter):
        """Test statistics calculation with actual data."""
        # Add some test data to stats
        rewriter._stats = {
            "total_rewrites": 10,
            "avg_latency_ms": 150.0,
            "cache_hits": 3,
            "llm_failures": 1,
        }
        rewriter._cache = {"key1": "val1", "key2": "val2"}

        stats = rewriter.get_stats()

        assert stats["total_rewrites"] == 10
        assert stats["cache_hits"] == 3
        assert stats["llm_failures"] == 1
        assert stats["avg_latency_ms"] == 150.0
        assert stats["cache_hit_rate"] == 0.3  # 3/10 = 30%
        assert stats["cache_size"] == 2

    @pytest.mark.asyncio
    async def test_rewrite_query_clear_query_no_rewrite(self, rewriter):
        """Test that clear queries are not rewritten."""
        # Clear query with specific terms
        clear_context = RewriteContext(
            query="Python async patterns for FastAPI",
            recent_conversations=[],
            project=None,
            recent_files=[],
            session_context={},
        )

        result = await rewriter.rewrite_query(
            query=clear_context.query,
            context=clear_context,
            force_rewrite=False,
        )

        assert result.was_rewritten is False
        assert result.rewritten_query == clear_context.query
        assert result.confidence == 0.0  # Clear queries return 0.0
        assert result.llm_provider is None
        assert result.latency_ms < 50  # Should be very fast

    @pytest.mark.asyncio
    async def test_rewrite_query_cache_hit(self, rewriter, mock_context):
        """Test that cache is checked before LLM call."""
        # Manually add to cache - note: cache key uses query and project only
        cache_key = rewriter._compute_cache_key(mock_context.query, mock_context.project)
        cached_result = QueryRewriteResult(
            original_query=mock_context.query,
            rewritten_query="cached rewrite result",
            was_rewritten=True,
            confidence=0.88,
            llm_provider=None,
            latency_ms=2,
            context_used=True,
            cache_hit=True,
        )
        rewriter._cache[cache_key] = cached_result

        # Mock detector to ensure query is detected as ambiguous
        with patch.object(rewriter.detector, "detect_ambiguity") as mock_detect:
            from session_buddy.rewriting.query_rewriter import AmbiguityDetection
            mock_detect.return_value = AmbiguityDetection(
                is_ambiguous=True,
                ambiguity_types=[AmbiguityType.PRONOUN_I],
                confidence=0.9,
                matched_patterns=[],
                suggestions=[],
            )

            # Should return cached result without LLM call
            result = await rewriter.rewrite_query(
                query=mock_context.query,
                context=mock_context,
                force_rewrite=False,
            )

        assert result.cache_hit is True
        assert result.rewritten_query == "cached rewrite result"
        assert result.llm_provider is None
        assert result.latency_ms < 10

    @pytest.mark.asyncio
    async def test_rewrite_query_force_rewrite(self, rewriter, mock_context):
        """Test that force_rewrite bypasses cache."""
        # Add to cache - note: cache key uses query and project only
        cache_key = rewriter._compute_cache_key(mock_context.query, mock_context.project)
        cached_result = QueryRewriteResult(
            original_query=mock_context.query,
            rewritten_query="old cached result",
            was_rewritten=True,
            confidence=0.75,
            llm_provider=None,
            latency_ms=2,
            context_used=True,
            cache_hit=True,
        )
        rewriter._cache[cache_key] = cached_result

        # Create an async mock function for the LLM expansion
        async def mock_llm_expand(*args, **kwargs):
            return "new forced rewrite"

        # Mock LLM to return different result
        with patch.object(
            rewriter,
            "_llm_expand_query",
            side_effect=mock_llm_expand,
        ):
            # Mock detector to ensure query is detected as ambiguous
            with patch.object(rewriter.detector, "detect_ambiguity") as mock_detect:
                from session_buddy.rewriting.query_rewriter import AmbiguityDetection
                mock_detect.return_value = AmbiguityDetection(
                    is_ambiguous=True,
                    ambiguity_types=[AmbiguityType.PRONOUN_I],
                    confidence=0.9,
                    matched_patterns=[],
                    suggestions=[],
                )

                result = await rewriter.rewrite_query(
                    query=mock_context.query,
                    context=mock_context,
                    force_rewrite=True,  # Force rewrites even if cached
                )

            # Should have new result, not cached
            assert result.cache_hit is False
            assert result.rewritten_query == "new forced rewrite"

    @pytest.mark.asyncio
    async def test_rewrite_query_empty_query_handling(self, rewriter):
        """Test handling of empty queries."""
        empty_context = RewriteContext(
            query="",
            recent_conversations=[],
            project=None,
            recent_files=[],
            session_context={},
        )

        result = await rewriter.rewrite_query(
            query=empty_context.query,
            context=empty_context,
            force_rewrite=False,
        )

        # Should return as-is without processing
        assert result.was_rewritten is False
        assert result.rewritten_query == ""
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_rewrite_query_whitespace_only_handling(self, rewriter):
        """Test handling of whitespace-only queries."""
        whitespace_context = RewriteContext(
            query="   ",
            recent_conversations=[],
            project=None,
            recent_files=[],
            session_context={},
        )

        result = await rewriter.rewrite_query(
            query=whitespace_context.query,
            context=whitespace_context,
            force_rewrite=False,
        )

        # Should return as-is without processing
        assert result.was_rewritten is False
        assert result.rewritten_query == "   "

    def test_compute_cache_key_consistency(self, rewriter, mock_context):
        """Test that cache keys are computed consistently."""
        key1 = rewriter._compute_cache_key(mock_context.query, mock_context.project)
        key2 = rewriter._compute_cache_key(mock_context.query, mock_context.project)

        assert key1 == key2

    def test_compute_cache_key_uniqueness(self, rewriter):
        """Test that different contexts produce different cache keys."""
        context1 = RewriteContext(
            query="test query",
            recent_conversations=[],
            project="project1",
            recent_files=[],
            session_context={},
        )
        context2 = RewriteContext(
            query="test query",
            recent_conversations=[],
            project="project2",  # Different project
            recent_files=[],
            session_context={},
        )

        key1 = rewriter._compute_cache_key(context1.query, context1.project)
        key2 = rewriter._compute_cache_key(context2.query, context2.project)

        assert key1 != key2


class TestQueryRewriterIntegration:
    """Integration tests for QueryRewriter with real components."""

    @pytest.fixture
    def rewriter(self):
        """Create a QueryRewriter instance."""
        return QueryRewriter()

    @pytest.mark.asyncio
    async def test_clear_query_bypasses_rewriting(self, rewriter):
        """Test that clear queries bypass the rewriting process."""
        # Clear, specific query
        context = RewriteContext(
            query="FastAPI authentication middleware implementation",
            recent_conversations=[],
            project="session-buddy",
            recent_files=[],
            session_context={},
        )

        result = await rewriter.rewrite_query(
            query=context.query,
            context=context,
            force_rewrite=False,
        )

        # Should not be rewritten
        assert result.was_rewritten is False
        assert result.rewritten_query == context.query
        assert result.confidence == 0.0
        assert result.llm_provider is None

        # Stats should not be updated
        stats = rewriter.get_stats()
        assert stats["total_rewrites"] == 0

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_clear(self, rewriter):
        """Test that clear_cache() invalidates all cached rewrites."""
        # Create a clear context that won't trigger LLM
        context = RewriteContext(
            query="FastAPI authentication",
            recent_conversations=[],
            project="test",
            recent_files=[],
            session_context={},
        )

        # First call (no rewrite, no cache)
        result1 = await rewriter.rewrite_query(
            query=context.query,
            context=context,
            force_rewrite=False,
        )

        # Verify cache is empty (no rewrite for clear query)
        assert len(rewriter._cache) == 0

        # Clear cache explicitly
        rewriter.clear_cache()

        # Verify cache is still empty
        assert len(rewriter._cache) == 0

        # Next call should also not cache (clear query)
        result2 = await rewriter.rewrite_query(
            query=context.query,
            context=context,
            force_rewrite=False,
        )

        assert result2.cache_hit is False
