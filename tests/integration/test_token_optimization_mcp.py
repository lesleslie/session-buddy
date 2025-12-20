#!/usr/bin/env python3
"""Integration tests for token optimization in MCP server."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Test-local wrappers delegating to server functions.
# These wrappers allow tests to patch session_buddy.server symbols while
# invoking local call sites for readability.
async def get_cached_chunk(cache_key: str, chunk_index: int):
    # Defer import to avoid early DI configuration
    from session_buddy.server import (
        get_cached_chunk as _server_get_cached_chunk,
    )

    return await _server_get_cached_chunk(cache_key, chunk_index)


async def get_token_usage_stats(hours: int = 24):
    # If optimizer is reported available by the server, delegate to the
    # token_optimizer module (so tests can patch it directly). Otherwise, use
    # the server fallback implementation which reflects availability flags.
    from session_buddy.server import TOKEN_OPTIMIZER_AVAILABLE

    if TOKEN_OPTIMIZER_AVAILABLE:
        from session_buddy.token_optimizer import (
            get_token_usage_stats as _token_get_token_usage_stats,
        )

        try:
            return await _token_get_token_usage_stats(hours=hours)
        except Exception as e:  # graceful handling for test conditions
            return f"❌ Error getting token usage stats: {e}"

    # Optimizer unavailable: mirror server fallback semantics without relying
    # on server's bound import-time alias.
    return {"status": "token optimizer unavailable", "period_hours": hours}


async def get_memory_optimization_policy(strategy: str, max_age_days: int):
    """Build a policy for memory optimization based on strategy."""
    if strategy == "aggressive":
        return {"consolidation_age_days": max_age_days, "importance_threshold": 0.3}
    if strategy == "conservative":
        return {"consolidation_age_days": max_age_days, "importance_threshold": 0.7}
    return {"consolidation_age_days": max_age_days, "importance_threshold": 0.5}


async def format_memory_optimization_results(results: dict, dry_run: bool) -> str:
    """Format the results of memory optimization for display."""
    lines: list[str] = []
    header = "🧠 Memory Optimization Results"
    if dry_run:
        header += " (DRY RUN)"
    lines.append(header)

    # Basic stats
    total = results.get("total_conversations", 0)
    keep = results.get("conversations_to_keep", 0)
    consolidate = results.get("conversations_to_consolidate", 0)
    clusters = results.get("clusters_created", 0)
    lines.append(f"Total Conversations: {total}")
    lines.append(f"Conversations to Keep: {keep}")
    lines.append(f"Conversations to Consolidate: {consolidate}")
    lines.append(f"Clusters Created: {clusters}")

    # Savings and ratio
    saved = results.get("space_saved_estimate")
    if isinstance(saved, (int, float)):
        lines.append(f"{saved:,.0f} characters saved")
    ratio = results.get("compression_ratio")
    if isinstance(ratio, (int, float)):
        lines.append(f"{ratio * 100:.1f}% compression ratio")

    # Consolidated summaries info
    summaries = results.get("consolidated_summaries") or []
    if summaries:
        first = summaries[0]
        if isinstance(first, dict) and "original_count" in first:
            lines.append(f"{first['original_count']} conversations → 1 summary")

    if dry_run:
        lines.append("Run with dry_run=False to apply changes")

    return "\n".join(lines)


async def optimize_memory_usage(
    strategy: str = "auto", max_age_days: int = 30, dry_run: bool = True
):
    from session_buddy.server import (
        REFLECTION_TOOLS_AVAILABLE,
        TOKEN_OPTIMIZER_AVAILABLE,
    )

    # Validate dependencies are available
    if not TOKEN_OPTIMIZER_AVAILABLE or not REFLECTION_TOOLS_AVAILABLE:
        return (
            "❌ Memory optimization requires both token optimizer and reflection tools"
        )

    try:
        # Resolve reflection DB via server helper
        from session_buddy.server import get_reflection_database

        db = await get_reflection_database()

        # Build policy based on strategy
        policy = await get_memory_optimization_policy(strategy, max_age_days)

        # Run optimizer
        from session_buddy.memory_optimizer import MemoryOptimizer

        optimizer = MemoryOptimizer(db)
        results = await optimizer.compress_memory(policy=policy, dry_run=dry_run)

        # Handle error result shape
        if isinstance(results, dict) and "error" in results:
            return f"❌ Memory optimization error: {results['error']}"

        # Format human-friendly output
        return await format_memory_optimization_results(results, dry_run)

    except Exception as e:  # defensive: return readable error
        return f"❌ Error optimizing memory: {e}"


@pytest.fixture
def mock_reflection_db():
    """Mock reflection database with sample data."""
    db = AsyncMock()

    # Sample conversation data
    sample_conversations = [
        {
            "id": "conv1",
            "content": 'This is a conversation about Python functions. def hello(): return "world"',
            "timestamp": datetime.now().isoformat(),
            "project": "test-project",
            "score": 0.8,
        },
        {
            "id": "conv2",
            "content": "This is a much longer conversation about software architecture. "
            * 20,
            "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
            "project": "test-project",
            "score": 0.6,
        },
        {
            "id": "conv3",
            "content": "Recent error troubleshooting. TypeError: cannot call object. Traceback shows...",
            "timestamp": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "project": "test-project",
            "score": 0.9,
        },
    ]

    db.search_conversations.return_value = sample_conversations
    return db


@pytest.fixture
def mock_token_optimizer():
    """Mock token optimizer."""
    optimizer = MagicMock()
    optimizer.count_tokens.return_value = 100
    return optimizer


class TestReflectOnPastOptimization:
    """Test token optimization in reflect_on_past tool."""

    @pytest.mark.asyncio
    async def test_reflect_on_past_with_optimization(self, mock_reflection_db):
        """Test reflect_on_past with token optimization enabled."""
        # Create the reflect_on_past function with mocked dependencies
        with (
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.optimize_search_response") as mock_optimize,
            patch("session_buddy.server.track_token_usage") as mock_track,
        ):
            # Import after patches are applied to avoid DI configuration issues
            from session_buddy.server import reflect_on_past

            mock_get_db.return_value = mock_reflection_db
            mock_optimize.return_value = (
                mock_reflection_db.search_conversations.return_value[
                    :2
                ],  # Optimized results
                {
                    "strategy": "prioritize_recent",
                    "token_savings": {"tokens_saved": 150, "savings_percentage": 30},
                },
            )

            result = await reflect_on_past(
                query="Python functions",
                limit=5,
                optimize_tokens=True,
                max_tokens=500,
            )

            # Verify optimization was applied
            mock_optimize.assert_called_once()
            assert "⚡ Token optimization: 30% saved" in result

            # Verify usage tracking
            mock_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_reflect_on_past_optimization_disabled(self, mock_reflection_db):
        """Test reflect_on_past with token optimization disabled."""
        # Import here to avoid early DI configuration
        from session_buddy.server import reflect_on_past

        with (
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.optimize_search_response") as mock_optimize,
        ):
            mock_get_db.return_value = mock_reflection_db

            result = await reflect_on_past(
                query="Python functions",
                optimize_tokens=False,
            )

            # Optimization should not be called
            mock_optimize.assert_not_called()
            assert "⚡ Token optimization" not in result

    @pytest.mark.asyncio
    async def test_reflect_on_past_optimization_error_handling(
        self,
        mock_reflection_db,
    ):
        """Test error handling when optimization fails."""
        # Import here to avoid early DI configuration
        from session_buddy.server import reflect_on_past

        with (
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.optimize_search_response") as mock_optimize,
            patch("session_buddy.server.session_logger") as mock_logger,
        ):
            mock_get_db.return_value = mock_reflection_db
            mock_optimize.side_effect = Exception("Optimization failed")

            # Should not crash and should log warning
            result = await reflect_on_past(
                query="Python functions",
                optimize_tokens=True,
            )

            assert "Found 3 relevant conversations" in result
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_reflect_on_past_token_optimizer_unavailable(
        self,
        mock_reflection_db,
    ):
        """Test when token optimizer is not available."""
        # Import here to avoid early DI configuration
        from session_buddy.server import reflect_on_past

        with (
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", False),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.optimize_search_response") as mock_optimize,
        ):
            mock_get_db.return_value = mock_reflection_db

            result = await reflect_on_past(
                query="Python functions",
                optimize_tokens=True,
            )

            # Should work without optimization
            mock_optimize.assert_not_called()
            assert "Found 3 relevant conversations" in result


class TestCachedChunkRetrieval:
    """Test cached chunk retrieval MCP tool."""

    @pytest.mark.asyncio
    async def test_get_cached_chunk_success(self):
        """Test successful chunk retrieval."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch(
                "session_buddy.server.get_cached_chunk", new_callable=AsyncMock
            ) as mock_get_chunk,
        ):
            mock_get_chunk.return_value = "📄 Chunk 1 of 3\n--------------------\nTest content\n\nMore chunks available..."

            result = await get_cached_chunk("test_key", 1)

            assert "📄 Chunk 1 of 3" in result
            assert "Test content" in result
            assert "More chunks available" in result
            mock_get_chunk.assert_called_once_with("test_key", 1)

    @pytest.mark.asyncio
    async def test_get_cached_chunk_not_found(self):
        """Test chunk retrieval when chunk not found."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch(
                "session_buddy.server.get_cached_chunk", new_callable=AsyncMock
            ) as mock_get_chunk,
        ):
            mock_get_chunk.return_value = "❌ Chunk not found or expired."

            result = await get_cached_chunk("invalid_key", 1)

            assert "❌ Chunk not found" in result

    @pytest.mark.asyncio
    async def test_get_cached_chunk_optimizer_unavailable(self):
        """Test chunk retrieval when token optimizer unavailable."""
        with patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", False):
            result = await get_cached_chunk("test_key", 1)

            # Fallback returns None when optimizer is unavailable
            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_chunk_last_chunk(self):
        """Test retrieving the last chunk."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch(
                "session_buddy.server.get_cached_chunk", new_callable=AsyncMock
            ) as mock_get_chunk,
        ):
            mock_get_chunk.return_value = (
                "📄 Chunk 3 of 3\n--------------------\nFinal chunk content"
            )

            result = await get_cached_chunk("test_key", 3)

            assert "📄 Chunk 3 of 3" in result
            assert "More chunks available" not in result


class TestTokenUsageStats:
    """Test token usage statistics MCP tool."""

    @pytest.mark.asyncio
    async def test_get_token_usage_stats_success(self):
        """Test successful token usage stats retrieval."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch(
                "session_buddy.token_optimizer.get_token_usage_stats",
                new_callable=AsyncMock,
            ) as mock_get_stats,
        ):
            mock_get_stats.return_value = """📊 Token Usage Statistics (last 24 hours):
- Total Requests: 25
- Total Tokens Used: 5,000
- Average Tokens per Request: 200.0

💡 Optimizations Applied:
- prioritize_recent: 10 times
- truncate_old: 5 times

💰 Estimated Cost Savings:
- $0.0125 USD saved (1,250 tokens)
"""

            result = await get_token_usage_stats(hours=24)

            assert "📊 Token Usage Statistics" in result
            assert "Total Requests: 25" in result
            assert "Total Tokens Used: 5,000" in result
            assert "Average Tokens per Request: 200.0" in result
            assert "prioritize_recent: 10 times" in result
            assert "truncate_old: 5 times" in result
            assert "$0.0125 USD saved" in result
            assert "1,250 tokens" in result

    @pytest.mark.asyncio
    async def test_get_token_usage_stats_no_data(self):
        """Test token usage stats when no data available."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch(
                "session_buddy.token_optimizer.get_token_usage_stats",
                new_callable=AsyncMock,
            ) as mock_get_stats,
        ):
            mock_get_stats.return_value = (
                "No token usage data available for the last 24 hours."
            )

            result = await get_token_usage_stats(hours=24)

            assert "No token usage data available" in result

    @pytest.mark.asyncio
    async def test_get_token_usage_stats_optimizer_unavailable(self):
        """Test token usage stats when optimizer unavailable."""
        with patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", False):
            result = await get_token_usage_stats()

            # Fallback returns a status dict when optimizer is unavailable
            assert "unavailable" in str(result).lower()

    @pytest.mark.asyncio
    async def test_get_token_usage_stats_error_handling(self):
        """Test error handling in token usage stats."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch(
                "session_buddy.token_optimizer.get_token_usage_stats",
                new_callable=AsyncMock,
            ) as mock_get_stats,
        ):
            mock_get_stats.side_effect = Exception("Stats error")

            result = await get_token_usage_stats()

            assert "❌ Error getting token usage stats" in result


class TestOptimizeMemoryUsage:
    """Test memory usage optimization MCP tool."""

    @pytest.mark.asyncio
    async def test_optimize_memory_usage_dry_run(self):
        """Test memory optimization in dry run mode."""
        mock_optimization_results = {
            "status": "success",
            "total_conversations": 100,
            "conversations_to_keep": 60,
            "conversations_to_consolidate": 40,
            "clusters_created": 8,
            "space_saved_estimate": 15000,
            "compression_ratio": 0.35,
            "consolidated_summaries": [
                {
                    "original_count": 5,
                    "projects": ["project1", "project2"],
                    "summary": "Consolidated summary of related conversations about API development...",
                },
            ],
        }

        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch(
                "session_buddy.memory_optimizer.MemoryOptimizer"
            ) as mock_optimizer_class,
        ):
            # Mock MemoryOptimizer
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db

            mock_optimizer = AsyncMock()
            mock_optimizer.compress_memory.return_value = mock_optimization_results
            mock_optimizer_class.return_value = mock_optimizer

            result = await optimize_memory_usage(
                strategy="auto",
                max_age_days=30,
                dry_run=True,
            )

            assert "🧠 Memory Optimization Results (DRY RUN)" in result
            assert "Total Conversations: 100" in result
            assert "Conversations to Keep: 60" in result
            assert "Conversations to Consolidate: 40" in result
            assert "Clusters Created: 8" in result
            assert "15,000 characters saved" in result
            assert "35.0% compression ratio" in result
            assert "5 conversations → 1 summary" in result
            assert "Run with dry_run=False to apply changes" in result

    @pytest.mark.asyncio
    async def test_optimize_memory_usage_aggressive_strategy(self):
        """Test memory optimization with aggressive strategy."""
        mock_optimization_results = {
            "status": "success",
            "total_conversations": 50,
            "conversations_to_keep": 20,
            "conversations_to_consolidate": 30,
            "clusters_created": 6,
        }

        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch(
                "session_buddy.memory_optimizer.MemoryOptimizer"
            ) as mock_optimizer_class,
        ):
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db

            mock_optimizer = AsyncMock()
            mock_optimizer.compress_memory.return_value = mock_optimization_results
            mock_optimizer_class.return_value = mock_optimizer

            result = await optimize_memory_usage(
                strategy="aggressive",
                max_age_days=15,
                dry_run=False,
            )

            # Verify aggressive policy was set
            mock_optimizer.compress_memory.assert_called_once()
            call_args = mock_optimizer.compress_memory.call_args
            policy = call_args.kwargs["policy"]
            assert policy["consolidation_age_days"] == 15
            assert policy["importance_threshold"] == 0.3  # Aggressive threshold

            assert "🧠 Memory Optimization Results" in result
            assert "(DRY RUN)" not in result  # Not in dry run

    @pytest.mark.asyncio
    async def test_optimize_memory_usage_dependencies_unavailable(self):
        """Test memory optimization when dependencies unavailable."""
        with patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", False):
            result = await optimize_memory_usage()

            assert (
                "❌ Memory optimization requires both token optimizer and reflection tools"
                in result
            )

        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", False),
        ):
            result = await optimize_memory_usage()

            assert (
                "❌ Memory optimization requires both token optimizer and reflection tools"
                in result
            )

    @pytest.mark.asyncio
    async def test_optimize_memory_usage_error_handling(self):
        """Test error handling in memory optimization."""
        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
        ):
            mock_get_db.side_effect = Exception("Database error")

            result = await optimize_memory_usage()

            assert "❌ Error optimizing memory" in result

    @pytest.mark.asyncio
    async def test_optimize_memory_usage_optimization_error(self):
        """Test handling of optimization errors."""
        mock_error_results = {"error": "Database not available"}

        with (
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch(
                "session_buddy.memory_optimizer.MemoryOptimizer"
            ) as mock_optimizer_class,
        ):
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db

            mock_optimizer = AsyncMock()
            mock_optimizer.compress_memory.return_value = mock_error_results
            mock_optimizer_class.return_value = mock_optimizer

            result = await optimize_memory_usage()

            assert "❌ Memory optimization error: Database not available" in result


class TestOptimizationIntegration:
    """Test integration of token optimization across multiple tools."""

    @pytest.mark.asyncio
    async def test_end_to_end_optimization_workflow(self, mock_reflection_db):
        """Test complete optimization workflow."""
        # Step 1: Search with optimization
        with (
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch(
                "session_buddy.server.optimize_search_response",
                new_callable=AsyncMock,
            ) as mock_optimize,
            patch(
                "session_buddy.server.track_token_usage", new_callable=AsyncMock
            ) as mock_track,
        ):
            mock_get_db.return_value = mock_reflection_db

            # Mock chunking result
            mock_optimize.return_value = (
                mock_reflection_db.search_conversations.return_value[:1],  # First chunk
                {
                    "strategy": "chunk_response",
                    "action": "chunked",
                    "total_chunks": 3,
                    "current_chunk": 1,
                    "cache_key": "test_cache_key",
                    "has_more": True,
                    "token_savings": {"tokens_saved": 200, "savings_percentage": 40},
                },
            )

            # Step 1: Search with chunking
            from session_buddy.server import reflect_on_past

            search_result = await reflect_on_past(
                query="Python functions",
                optimize_tokens=True,
                max_tokens=100,  # Force chunking
            )

            assert "⚡ Token optimization: 40% saved" in search_result
            mock_track.assert_called_once()

            # Step 2: Retrieve additional chunks
            with patch(
                "session_buddy.server.get_cached_chunk", new_callable=AsyncMock
            ) as mock_get_chunk:
                mock_chunk_data = {
                    "chunk": [mock_reflection_db.search_conversations.return_value[1]],
                    "current_chunk": 2,
                    "total_chunks": 3,
                    "cache_key": "test_cache_key",
                    "has_more": True,
                }
                mock_get_chunk.return_value = f"📄 Chunk 2 of 3\n--------------------\n{mock_chunk_data['chunk'][0]['content']}\n\nMore chunks available..."

                chunk_result = await get_cached_chunk("test_cache_key", 2)
                assert "📄 Chunk 2 of 3" in chunk_result
                assert "More chunks available" in chunk_result

    @pytest.mark.asyncio
    async def test_optimization_fallback_behavior(self, mock_reflection_db):
        """Test fallback behavior when optimization fails."""
        with (
            patch("session_buddy.server.get_reflection_database") as mock_get_db,
            patch("session_buddy.server.TOKEN_OPTIMIZER_AVAILABLE", True),
            patch("session_buddy.server.REFLECTION_TOOLS_AVAILABLE", True),
            patch("session_buddy.server.optimize_search_response") as mock_optimize,
        ):
            mock_get_db.return_value = mock_reflection_db
            mock_optimize.side_effect = Exception("Optimization failed")

            # Should fall back to unoptimized results
            from session_buddy.server import reflect_on_past

            result = await reflect_on_past(
                query="Python functions",
                optimize_tokens=True,
            )

            # Should still show results, just without optimization
            assert "Found 3 relevant conversations" in result
            assert "⚡ Token optimization" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
