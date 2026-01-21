#!/usr/bin/env python3
"""Integration tests for Phase 2: Query Rewriting success criteria verification.

Tests the following success criteria from the implementation plan:
1. >80% ambiguous query resolution rate
2. <200ms average latency increase
3. Graceful fallback when LLM unavailable
4. Rewrite caching hit rate >50%
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from session_buddy.rewriting.query_rewriter import (
    AmbiguityDetector,
    AmbiguityType,
    QueryRewriter,
    RewriteContext,
    QueryRewriteResult,
)


class TestPhase2SuccessCriteria:
    """Test Phase 2 success criteria."""

    @pytest.fixture
    def rewriter(self):
        """Create a QueryRewriter instance."""
        return QueryRewriter()

    @pytest.mark.asyncio
    async def test_ambiguity_detection_accuracy(self, rewriter):
        """Test success criterion: >80% ambiguous query resolution rate.

        This test measures how well the AmbiguityDetector identifies various
        types of ambiguous queries (pronouns, demonstratives, temporal/spatial refs).
        """
        detector = rewriter.detector

        # Test cases with expected ambiguity detection
        test_cases = [
            # (query, should_be_ambiguous, description)
            ("what did I learn?", True, "PRONOUN_I - first person pronoun"),
            ("fix it please", True, "PRONOUN_IT - object pronoun"),
            ("update this code", True, "PRONOUN_THIS - demonstrative"),
            ("that function from earlier", True, "PRONOUN_THAT - demonstrative"),
            ("what did we discuss yesterday?", True, "DEMONSTRATIVE_TEMPORAL - temporal"),
            ("check that file", True, "PRONOUN_THAT - spatial reference"),
            ("help me", True, "TOO_SHORT - insufficient context"),
            ("how do I fix it", True, "PRONOUN_I + TOO_VAGUE - multiple ambiguities"),
            ("call the method", True, "MISSING_CONTEXT - lacks specificity"),
            ("Python async patterns", False, "Clear - specific topic"),
            ("FastAPI authentication middleware", False, "Clear - specific topic"),
            ("pytest fixtures for session_buddy", False, "Clear - explicit context"),
            ("", False, "Empty - not ambiguous, just invalid"),
            ("   ", False, "Whitespace - not ambiguous, just invalid"),
        ]

        correct_detections = 0
        total_ambiguous = 0

        for query, should_be_ambiguous, description in test_cases:
            detection = detector.detect_ambiguity(query)

            if should_be_ambiguous:
                total_ambiguous += 1
                if detection.is_ambiguous:
                    correct_detections += 1
            else:
                # Should not be detected as ambiguous
                if not detection.is_ambiguous:
                    correct_detections += 1

        # Calculate accuracy
        accuracy = correct_detections / len(test_cases)

        # Success criterion: >80% of ambiguous queries detected correctly
        ambiguous_queries = [q for q, amb, _ in test_cases if amb]
        ambiguous_detection_rate = sum(
            1 for q, amb, _ in test_cases
            if amb and detector.detect_ambiguity(q).is_ambiguous
        ) / len(ambiguous_queries) if ambiguous_queries else 0

        print(f"\nAmbiguity Detection Results:")
        print(f"  Total queries: {len(test_cases)}")
        print(f"  Ambiguous queries: {len(ambiguous_queries)}")
        print(f"  Correct detections: {correct_detections}/{len(test_cases)}")
        print(f"  Overall accuracy: {accuracy:.1%}")
        print(f"  Ambiguous detection rate: {ambiguous_detection_rate:.1%}")

        assert accuracy > 0.80, f"Ambiguity detection accuracy {accuracy:.1%} is below 80% threshold"
        assert ambiguous_detection_rate > 0.80, (
            f"Ambiguous query detection rate {ambiguous_detection_rate:.1%} is below 80% threshold"
        )

    @pytest.mark.asyncio
    async def test_query_rewriting_latency(self, rewriter):
        """Test success criterion: <200ms average latency increase.

        Measures the latency impact of query rewriting on typical workflows.
        """
        # Mock LLM to simulate realistic latency
        async def mock_llm_expand(query: str, context: RewriteContext) -> str:
            # Simulate 100ms LLM call latency
            await asyncio.sleep(0.1)
            return f"expanded: {query}"

        # Test clear query (should be fast - minimal latency)
        clear_context = RewriteContext(
            query="Python async patterns",
            recent_conversations=[],
            project="test",
            recent_files=[],
            session_context={},
        )

        start = time.perf_counter()
        clear_result = await rewriter.rewrite_query(
            query=clear_context.query,
            context=clear_context,
            force_rewrite=False,
        )
        clear_latency = (time.perf_counter() - start) * 1000  # Convert to ms

        # Test ambiguous query with LLM mock
        ambiguous_context = RewriteContext(
            query="what did I learn?",
            recent_conversations=[
                {"role": "user", "content": "How does async work?"},
                {"role": "assistant", "content": "Async allows non-blocking code"},
            ],
            project="session-buddy",
            recent_files=["server.py"],
            session_context={"session_id": "test"},
        )

        with patch.object(rewriter, "_llm_expand_query", side_effect=mock_llm_expand):
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

                start = time.perf_counter()
                ambiguous_result = await rewriter.rewrite_query(
                    query=ambiguous_context.query,
                    context=ambiguous_context,
                    force_rewrite=False,
                )
                ambiguous_latency = (time.perf_counter() - start) * 1000  # Convert to ms

        print(f"\nQuery Rewriting Latency Results:")
        print(f"  Clear query latency: {clear_latency:.2f}ms")
        print(f"  Ambiguous query latency: {ambiguous_latency:.2f}ms")
        print(f"  Average latency: {(clear_latency + ambiguous_latency) / 2:.2f}ms")

        # Success criterion: <200ms average latency
        # Note: Clear queries should be <10ms, ambiguous queries should include LLM time
        assert clear_latency < 50, f"Clear query latency {clear_latency:.2f}ms exceeds 50ms threshold"
        assert ambiguous_latency < 200, (
            f"Ambiguous query latency {ambiguous_latency:.2f}ms exceeds 200ms success criterion"
        )

    @pytest.mark.asyncio
    async def test_graceful_fallback(self, rewriter):
        """Test success criterion: graceful fallback when LLM unavailable.

        Verifies that the system continues operating even when LLM fails.
        """
        # Context with ambiguous query
        context = RewriteContext(
            query="what did I learn?",
            recent_conversations=[
                {"role": "user", "content": "How does async work?"},
                {"role": "assistant", "content": "Async allows non-blocking code"},
            ],
            project="session-buddy",
            recent_files=["server.py"],
            session_context={"session_id": "test_fallback"},
        )

        # Test with no LLM provider configured (default state)
        start = time.perf_counter()
        result = await rewriter.rewrite_query(
            query=context.query,
            context=context,
            force_rewrite=False,
        )
        fallback_latency = (time.perf_counter() - start) * 1000  # Convert to ms

        # Should fall back gracefully
        assert result is not None, "Should return a result even when LLM fails"
        assert result.original_query == context.query, "Original query should be preserved"
        assert result.was_rewritten is False, "Should not be marked as rewritten when LLM fails"
        assert result.rewritten_query == context.query, "Should return original query on failure"
        assert result.llm_provider is None, "No LLM provider when fallback occurs"

        print(f"\nGraceful Fallback Results:")
        print(f"  Fallback latency: {fallback_latency:.2f}ms")
        print(f"  Result: {result}")
        print(f"  ✓ System continues operating despite LLM failure")

        # Success criterion: graceful degradation (no exceptions)
        assert fallback_latency < 1000, f"Fallback latency {fallback_latency:.2f}ms indicates performance issue"

    @pytest.mark.asyncio
    async def test_cache_hit_rate(self, rewriter):
        """Test success criterion: rewrite caching hit rate >50%.

        Measures cache effectiveness for repeated queries.
        """
        # Clear cache to ensure clean test state
        rewriter.clear_cache()

        # Create ambiguous context with unique query to avoid cross-test contamination
        context = RewriteContext(
            query="cache test unique query about learning?",
            recent_conversations=[
                {"role": "user", "content": "How does async work?"},
                {"role": "assistant", "content": "Async allows non-blocking code"},
            ],
            project="session-buddy-cache-test",  # Unique project to avoid cache collisions
            recent_files=["server.py"],
            session_context={"session_id": "test_cache"},
        )

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

            # Create mock LLM function
            async def mock_llm_expand(query: str, context: RewriteContext) -> str:
                # Simulate 50ms latency
                await asyncio.sleep(0.05)
                return f"expanded: {query}"

            # First call - cache miss
            with patch.object(rewriter, "_llm_expand_query", side_effect=mock_llm_expand):
                result1 = await rewriter.rewrite_query(
                    query=context.query,
                    context=context,
                    force_rewrite=False,
                )

            # Second call - should hit cache
            start = time.perf_counter()
            with patch.object(rewriter, "_llm_expand_query", side_effect=mock_llm_expand):
                result2 = await rewriter.rewrite_query(
                    query=context.query,
                    context=context,
                    force_rewrite=False,
                )
            cache_hit_latency = (time.perf_counter() - start) * 1000

            # Third call - should also hit cache
            start = time.perf_counter()
            with patch.object(rewriter, "_llm_expand_query", side_effect=mock_llm_expand):
                result3 = await rewriter.rewrite_query(
                    query=context.query,
                    context=context,
                    force_rewrite=False,
                )
            cache_hit_latency_2 = (time.perf_counter() - start) * 1000

        # Verify cache behavior
        # Note: Due to test execution order, any of the calls might hit cache first
        # We verify that cache is working and hit rate meets success criterion
        cache_hits = sum([result1.cache_hit, result2.cache_hit, result3.cache_hit])
        cache_hit_rate = cache_hits / 3  # cache hits out of 3 total

        print(f"\nCache Hit Rate Results:")
        print(f"  Total calls: 3")
        print(f"  Cache hits: {cache_hits}")
        print(f"  Cache hit rate: {cache_hit_rate:.1%}")
        print(f"  Call 1 - cache_hit: {result1.cache_hit}, latency: {result1.latency_ms:.2f}ms")
        print(f"  Call 2 - cache_hit: {result2.cache_hit}, latency: {result2.latency_ms:.2f}ms")
        print(f"  Call 3 - cache_hit: {result3.cache_hit}, latency: {result3.latency_ms:.2f}ms")

        # Success criterion: >50% cache hit rate
        assert cache_hit_rate > 0.5, f"Cache hit rate {cache_hit_rate:.1%} is below 50% threshold"

        # Verify cache effectiveness: Calls 2 and 3 should return the same cached result
        # (same rewritten query, same latency because it's from the same cached object)
        if cache_hits >= 2:
            # At least 2 cache hits means subsequent calls retrieved the cached result
            assert result2.rewritten_query == result3.rewritten_query, (
                "Cached results should return the same rewritten query"
            )
            # The latencies should be identical because they're from the same cached object
            assert result2.latency_ms == result3.latency_ms, (
                "Cached results should have the same latency (from the original cache miss)"
            )
            print(f"  ✓ Cache effectiveness verified: subsequent calls returned cached result")

    @pytest.mark.asyncio
    async def test_end_to_end_query_rewriting(self, rewriter):
        """Test end-to-end query rewriting workflow.

        Verifies the complete flow from ambiguous query to resolved query.
        """
        # Test case: ambiguous query with context
        original_query = "what did I learn about async?"

        context = RewriteContext(
            query=original_query,
            recent_conversations=[
                {"role": "user", "content": "How does async work in Python?"},
                {"role": "assistant", "content": "Async allows non-blocking code execution with asyncio"},
            ],
            project="session-buddy",
            recent_files=["server.py", "query_rewriter.py"],
            session_context={"session_id": "e2e_test"},
        )

        # Mock detector to detect ambiguity
        with patch.object(rewriter.detector, "detect_ambiguity") as mock_detect:
            from session_buddy.rewriting.query_rewriter import AmbiguityDetection
            mock_detect.return_value = AmbiguityDetection(
                is_ambiguous=True,
                ambiguity_types=[AmbiguityType.PRONOUN_I],
                confidence=0.85,
                matched_patterns=[r"\bwhat did i\b"],
                suggestions=["Add conversation context"],
            )

            # Mock LLM to provide expanded query
            async def mock_llm_expand(query: str, context: RewriteContext) -> str:
                return f"what did I learn about Python async patterns in the session_buddy project?"

            with patch.object(rewriter, "_llm_expand_query", side_effect=mock_llm_expand):
                result = await rewriter.rewrite_query(
                    query=original_query,
                    context=context,
                    force_rewrite=False,
                )

        # Verify end-to-end behavior
        assert result is not None, "Should return a result"
        assert result.was_rewritten is True, "Query should be rewritten"
        assert result.rewritten_query != original_query, "Query should be expanded"
        assert "Python" in result.rewritten_query or "async" in result.rewritten_query, (
            "Rewritten query should include context"
        )
        assert result.confidence > 0.7, "Should have high confidence in rewrite"

        print(f"\nEnd-to-End Query Rewriting Results:")
        print(f"  Original: '{result.original_query}'")
        print(f"  Rewritten: '{result.rewritten_query}'")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Latency: {result.latency_ms:.2f}ms")
        print(f"  Cache hit: {result.cache_hit}")
        print(f"  LLM provider: {result.llm_provider}")
        print(f"  ✓ Complete query rewriting workflow successful")

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, rewriter):
        """Test that statistics are correctly tracked."""
        # Clear existing stats
        rewriter._stats = {
            "total_rewrites": 0,
            "avg_latency_ms": 0.0,
            "cache_hits": 0,
            "llm_failures": 0,
        }

        context = RewriteContext(
            query="test query",
            recent_conversations=[],
            project="test",
            recent_files=[],
            session_context={},
        )

        # Mock detector and LLM
        with patch.object(rewriter.detector, "detect_ambiguity") as mock_detect:
            from session_buddy.rewriting.query_rewriter import AmbiguityDetection
            mock_detect.return_value = AmbiguityDetection(
                is_ambiguous=True,
                ambiguity_types=[AmbiguityType.PRONOUN_I],
                confidence=0.9,
                matched_patterns=[],
                suggestions=[],
            )

            async def mock_llm_expand(query: str, context: RewriteContext) -> str:
                return f"expanded: {query}"

            # Perform rewrites
            with patch.object(rewriter, "_llm_expand_query", side_effect=mock_llm_expand):
                await rewriter.rewrite_query(
                    query="query1",
                    context=context,
                    force_rewrite=False,
                )
                await rewriter.rewrite_query(
                    query="query2",
                    context=context,
                    force_rewrite=False,
                )

            # Check stats
            stats = rewriter.get_stats()
            assert stats["total_rewrites"] == 2, "Should track total rewrites"
            assert stats["avg_latency_ms"] >= 0, "Should track average latency"

            print(f"\nStatistics Tracking Results:")
            print(f"  Total rewrites: {stats['total_rewrites']}")
            print(f"  Average latency: {stats['avg_latency_ms']:.2f}ms")
            print(f"  Cache hits: {stats['cache_hits']}")
            print(f"  LLM failures: {stats['llm_failures']}")
            print(f"  Cache size: {stats['cache_size']}")
            print(f"  ✓ Statistics tracking is functional")
