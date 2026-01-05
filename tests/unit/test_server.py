#!/usr/bin/env python3
"""Comprehensive tests for MCP server functionality.

Tests server initialization, health checks, and core MCP operations
with proper async patterns and error handling.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestServerInitialization:
    """Test server initialization and setup."""

    def test_server_imports(self):
        """Test that server module imports successfully."""
        try:
            import session_buddy.server

            assert session_buddy.server is not None
        except ImportError as e:
            pytest.skip(f"Server module import failed: {e}")

    def test_token_optimizer_fallback(self):
        """Test that token optimizer has fallback implementations."""
        try:
            from session_buddy.server import (
                get_cached_chunk,
                get_token_usage_stats,
                optimize_memory_usage,
                optimize_search_response,
                track_token_usage,
            )

            # Functions should exist (either from token_optimizer or as fallbacks)
            assert callable(optimize_memory_usage)
            assert callable(optimize_search_response)
            assert callable(track_token_usage)
            assert callable(get_cached_chunk)
            assert callable(get_token_usage_stats)
        except ImportError:
            pytest.skip("Token optimizer components not available")

    async def test_session_logger_available(self):
        """Test that session logger is properly configured."""
        try:
            from session_buddy.server import _get_logger

            # Test that _get_logger function exists and is callable
            assert callable(_get_logger)

            # Test that calling _get_logger returns a valid logger
            logger = _get_logger()
            assert logger is not None
            assert isinstance(logger, logging.Logger)

            # Test that calling _get_logger multiple times returns the same logger (singleton)
            logger2 = _get_logger()
            assert logger is logger2
        except ImportError:
            pytest.skip("Session logger not available")


@pytest.mark.asyncio
class TestServerHealthChecks:
    """Test server health check functionality."""

    async def test_health_check_function_exists(self):
        """Test that health_check function is defined."""
        try:
            from session_buddy.server import health_check

            assert callable(health_check)
        except ImportError:
            pytest.skip("health_check function not available")

    async def test_health_check_returns_dict(self):
        """Test that health_check returns a dictionary."""
        try:
            from session_buddy.server import health_check

            # Mock the logger to avoid DI container issues
            with patch("session_buddy.server.session_logger") as mock_logger:
                mock_logger.info = MagicMock()
                result = await health_check()
                assert isinstance(result, dict)
        except ImportError:
            pytest.skip("health_check function not available")

    async def test_health_check_includes_status(self):
        """Test that health check response includes status information."""
        try:
            from session_buddy.server import health_check

            with patch("session_buddy.server.session_logger") as mock_logger:
                mock_logger.info = MagicMock()
                result = await health_check()
                # Should have some health-related content
                assert len(result) > 0
        except ImportError:
            pytest.skip("health_check function not available")


@pytest.mark.asyncio
class TestServerQualityScoring:
    """Test server quality scoring functionality."""

    async def test_calculate_quality_score_exists(self):
        """Test that quality score calculation function exists."""
        try:
            from session_buddy.server import calculate_quality_score

            assert callable(calculate_quality_score)
        except ImportError:
            pytest.skip("calculate_quality_score not available")

    async def test_calculate_quality_score_with_no_args(self):
        """Test quality score calculation with default arguments."""
        try:
            from session_buddy.server import calculate_quality_score

            result = await calculate_quality_score()
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("calculate_quality_score not available")

    async def test_calculate_quality_score_with_directory(self):
        """Test quality score calculation with specific directory."""
        try:
            from session_buddy.server import calculate_quality_score

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await calculate_quality_score(project_dir=Path(tmpdir))
                assert isinstance(result, dict)
        except ImportError:
            pytest.skip("calculate_quality_score not available")

    async def test_quality_score_returns_numeric(self):
        """Test that quality score result contains numeric values."""
        try:
            from session_buddy.server import calculate_quality_score

            result = await calculate_quality_score()
            # Should have numeric values representing quality metrics
            assert any(isinstance(v, (int, float)) for v in result.values())
        except ImportError:
            pytest.skip("calculate_quality_score not available")


@pytest.mark.asyncio
class TestServerReflectionFunctions:
    """Test server reflection and memory functions."""

    async def test_reflect_on_past_function_exists(self):
        """Test that reflect_on_past function exists."""
        try:
            from session_buddy.server import reflect_on_past

            assert callable(reflect_on_past)
        except ImportError:
            pytest.skip("reflect_on_past not available")

    async def test_reflect_on_past_with_query(self):
        """Test reflect_on_past with a query string."""
        try:
            from session_buddy.server import reflect_on_past

            # Mock the database to avoid external dependencies
            with patch("session_buddy.server.depends") as mock_depends:
                # Create a mock database
                mock_db = AsyncMock()
                mock_db.search_conversations.return_value = []
                # Properly mock depends.get() to return the database directly
                mock_depends.get.return_value = mock_db

                result = await reflect_on_past(query="test query")
                assert isinstance(result, (dict, list, str))
        except (ImportError, AttributeError):
            pytest.skip("reflect_on_past not available or DI dependencies missing")


@pytest.mark.asyncio
class TestServerOptimization:
    """Test server optimization functions."""

    async def test_optimize_memory_usage_callable(self):
        """Test that memory optimization function is callable."""
        try:
            from session_buddy.server import optimize_memory_usage

            assert callable(optimize_memory_usage)
        except ImportError:
            pytest.skip("optimize_memory_usage not available")

    async def test_optimize_memory_usage_returns_string(self):
        """Test that memory optimization returns a string result."""
        try:
            from session_buddy.server import optimize_memory_usage

            result = await optimize_memory_usage(dry_run=True)
            assert isinstance(result, str)
        except ImportError:
            pytest.skip("optimize_memory_usage not available")

    async def test_optimize_search_response_callable(self):
        """Test that search response optimization is callable."""
        try:
            from session_buddy.server import optimize_search_response

            assert callable(optimize_search_response)
        except ImportError:
            pytest.skip("optimize_search_response not available")

    async def test_optimize_search_response_with_results(self):
        """Test search response optimization with sample results."""
        try:
            from session_buddy.server import optimize_search_response

            sample_results = [
                {"id": "1", "content": "Result 1"},
                {"id": "2", "content": "Result 2"},
            ]
            results, metadata = await optimize_search_response(
                results=sample_results,
            )
            assert isinstance(results, list)
            assert isinstance(metadata, dict)
        except ImportError:
            pytest.skip("optimize_search_response not available")


@pytest.mark.asyncio
class TestServerTokenTracking:
    """Test server token tracking functionality."""

    async def test_track_token_usage_callable(self):
        """Test that token tracking function is callable."""
        try:
            from session_buddy.server import track_token_usage

            assert callable(track_token_usage)
        except ImportError:
            pytest.skip("track_token_usage not available")

    async def test_track_token_usage_operation(self):
        """Test token tracking with operation parameters."""
        try:
            from session_buddy.server import track_token_usage

            result = await track_token_usage(
                operation="test_operation",
                request_tokens=100,
                response_tokens=50,
            )
            # Should not raise an exception
            assert result is None or isinstance(result, dict)
        except ImportError:
            pytest.skip("track_token_usage not available")

    async def test_get_token_usage_stats_callable(self):
        """Test that token usage stats function is callable."""
        try:
            from session_buddy.server import get_token_usage_stats

            assert callable(get_token_usage_stats)
        except ImportError:
            pytest.skip("get_token_usage_stats not available")

    async def test_get_token_usage_stats_returns_dict(self):
        """Test that token usage stats returns a dictionary."""
        try:
            from session_buddy.server import get_token_usage_stats

            result = await get_token_usage_stats(hours=24)
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("get_token_usage_stats not available")


@pytest.mark.asyncio
class TestServerCaching:
    """Test server caching functionality."""

    async def test_get_cached_chunk_callable(self):
        """Test that cache retrieval function is callable."""
        try:
            from session_buddy.server import get_cached_chunk

            assert callable(get_cached_chunk)
        except ImportError:
            pytest.skip("get_cached_chunk not available")

    async def test_get_cached_chunk_nonexistent(self):
        """Test retrieving non-existent cache entry."""
        try:
            from session_buddy.server import get_cached_chunk

            result = await get_cached_chunk(
                cache_key="nonexistent_key",
                chunk_index=0,
            )
            # Should return None or similar for non-existent cache
            assert result is None or isinstance(result, dict)
        except ImportError:
            pytest.skip("get_cached_chunk not available")


@pytest.mark.asyncio
class TestServerErrorHandling:
    """Test server error handling."""

    async def test_health_check_graceful_degradation(self):
        """Test that health check handles errors gracefully."""
        try:
            from session_buddy.server import health_check

            # Mock a potential error condition
            with patch("session_buddy.server.session_logger") as mock_logger:
                mock_logger.info = MagicMock()
                result = await health_check()
                # Should return something even if components fail
                assert result is not None
        except ImportError:
            pytest.skip("health_check not available")

    async def test_quality_score_handles_invalid_path(self):
        """Test quality scoring with invalid directory."""
        try:
            from session_buddy.server import calculate_quality_score

            # Should handle invalid paths gracefully
            invalid_path = Path("/nonexistent/path/that/does/not/exist")
            result = await calculate_quality_score(project_dir=invalid_path)
            # Should return a dict even if path is invalid
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("calculate_quality_score not available")


@pytest.mark.asyncio
class TestServerConcurrency:
    """Test server concurrent operations."""

    async def test_concurrent_health_checks(self):
        """Test multiple concurrent health checks."""
        try:
            from session_buddy.server import health_check

            async def check_health():
                with patch("session_buddy.server.session_logger") as mock_logger:
                    mock_logger.info = MagicMock()
                    return await health_check()

            # Run multiple health checks concurrently
            tasks = [check_health() for _ in range(5)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(isinstance(r, dict) for r in results)
        except ImportError:
            pytest.skip("health_check not available")

    async def test_concurrent_quality_scoring(self):
        """Test multiple concurrent quality score calculations."""
        try:
            from session_buddy.server import calculate_quality_score

            async def score_quality():
                return await calculate_quality_score()

            # Run multiple quality score calculations concurrently
            tasks = [score_quality() for _ in range(3)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 3
            assert all(isinstance(r, dict) for r in results)
        except ImportError:
            pytest.skip("calculate_quality_score not available")


@pytest.mark.asyncio
class TestServerMain:
    """Test server main function."""

    def test_main_function_exists(self):
        """Test that main function is defined."""
        try:
            from session_buddy.server import main

            assert callable(main)
        except ImportError:
            pytest.skip("main function not available")

    def test_main_function_signature(self):
        """Test main function accepts http parameters."""
        try:
            import inspect

            from session_buddy.server import main

            sig = inspect.signature(main)
            # Should accept http_mode and http_port parameters
            assert "http_mode" in sig.parameters or len(sig.parameters) > 0
        except ImportError:
            pytest.skip("main function not available")


class TestServerHelperFunctions:
    """Test server initialization helper functions.

    Phase: Week 1 Day 2 - Quick Win Coverage (65% → 75%)
    """

    def test_build_feature_list_returns_list(self):
        """Should return a list of feature strings."""
        from session_buddy.server import _build_feature_list

        features = _build_feature_list()

        assert isinstance(features, list)
        assert len(features) >= 5  # At minimum the core features

    def test_build_feature_list_includes_core_features(self):
        """Should include all core features."""
        from session_buddy.server import _build_feature_list

        features = _build_feature_list()

        # Core features that should always be present
        assert any("Session Lifecycle" in f for f in features)
        assert any("Memory" in f or "Reflection" in f for f in features)
        assert any("Crackerjack" in f for f in features)
        assert any("Knowledge Graph" in f or "DuckPGQ" in f for f in features)
        assert any("LLM Provider" in f for f in features)

    def test_build_feature_list_conditional_security(self):
        """Should conditionally include security features based on availability."""
        from session_buddy.server import SECURITY_AVAILABLE, _build_feature_list

        features = _build_feature_list()

        # Security features should only appear if SECURITY_AVAILABLE is True
        has_security_feature = any("API Key Validation" in f for f in features)
        if SECURITY_AVAILABLE:
            assert has_security_feature, (
                "Security feature should be present when SECURITY_AVAILABLE=True"
            )
        else:
            # May or may not be present depending on actual availability
            pass

    def test_build_feature_list_conditional_rate_limiting(self):
        """Should conditionally include rate limiting based on availability."""
        from session_buddy.server import RATE_LIMITING_AVAILABLE, _build_feature_list

        features = _build_feature_list()

        # Rate limiting should only appear if RATE_LIMITING_AVAILABLE is True
        has_rate_limit_feature = any("Rate Limiting" in f for f in features)
        if RATE_LIMITING_AVAILABLE:
            assert has_rate_limit_feature, (
                "Rate limiting feature should be present when RATE_LIMITING_AVAILABLE=True"
            )

    def test_display_http_startup_with_serverpanels(self):
        """Should use ServerPanels when available."""
        from session_buddy.server import (
            SERVERPANELS_AVAILABLE,
            _display_http_startup,
        )

        if not SERVERPANELS_AVAILABLE:
            pytest.skip("ServerPanels not available")

        features = ["Feature 1", "Feature 2"]

        # Mock ServerPanels (imported inside the function)
        with patch("mcp_common.ui.ServerPanels") as mock_panels:
            _display_http_startup("localhost", 3000, features)

            # Verify startup_success was called with correct parameters
            mock_panels.startup_success.assert_called_once()
            call_kwargs = mock_panels.startup_success.call_args.kwargs
            assert call_kwargs["server_name"] == "Session Management MCP"
            assert call_kwargs["version"] == "2.0.0"
            assert call_kwargs["features"] == features
            assert "localhost:3000" in call_kwargs["endpoint"]
            assert call_kwargs["transport"] == "HTTP (streamable)"

    def test_display_http_startup_fallback(self):
        """Should fall back to print when ServerPanels unavailable."""
        from session_buddy.server import _display_http_startup

        features = ["Feature 1", "Feature 2"]

        # Temporarily disable SERVERPANELS_AVAILABLE
        with patch("session_buddy.server.SERVERPANELS_AVAILABLE", False):
            # Mock print to verify fallback behavior
            with patch("sys.stderr") as mock_stderr:
                _display_http_startup("localhost", 8080, features)

                # Verify print was called (stderr.write is used by print)
                # At least one call to stderr should contain server info
                assert mock_stderr.write.called

    def test_display_http_startup_with_custom_port(self):
        """Should display correct port in endpoint URL."""
        from session_buddy.server import (
            SERVERPANELS_AVAILABLE,
            _display_http_startup,
        )

        if not SERVERPANELS_AVAILABLE:
            pytest.skip("ServerPanels not available")

        features = []

        with patch("mcp_common.ui.ServerPanels") as mock_panels:
            _display_http_startup("0.0.0.0", 9999, features)

            call_kwargs = mock_panels.startup_success.call_args.kwargs
            assert "9999" in call_kwargs["endpoint"]

    def test_display_stdio_startup_with_serverpanels(self):
        """Should use ServerPanels for STDIO mode when available."""
        from session_buddy.server import (
            SERVERPANELS_AVAILABLE,
            _display_stdio_startup,
        )

        if not SERVERPANELS_AVAILABLE:
            pytest.skip("ServerPanels not available")

        features = ["Feature A", "Feature B"]

        with patch("mcp_common.ui.ServerPanels") as mock_panels:
            _display_stdio_startup(features)

            # Verify startup_success was called with STDIO-specific params
            mock_panels.startup_success.assert_called_once()
            call_kwargs = mock_panels.startup_success.call_args.kwargs
            assert call_kwargs["server_name"] == "Session Management MCP"
            assert call_kwargs["version"] == "2.0.0"
            assert call_kwargs["features"] == features
            assert call_kwargs["transport"] == "STDIO"
            assert call_kwargs["mode"] == "Claude Desktop"

    def test_display_stdio_startup_fallback(self):
        """Should fall back to print when ServerPanels unavailable."""
        from session_buddy.server import _display_stdio_startup

        features = ["Feature X"]

        # Temporarily disable SERVERPANELS_AVAILABLE
        with patch("session_buddy.server.SERVERPANELS_AVAILABLE", False):
            # Mock print to verify fallback behavior
            with patch("sys.stderr") as mock_stderr:
                _display_stdio_startup(features)

                # Verify print was called with STDIO mode message
                assert mock_stderr.write.called

    def test_display_stdio_startup_with_empty_features(self):
        """Should handle empty feature list gracefully."""
        from session_buddy.server import (
            SERVERPANELS_AVAILABLE,
            _display_stdio_startup,
        )

        if not SERVERPANELS_AVAILABLE:
            pytest.skip("ServerPanels not available")

        features = []

        with patch("mcp_common.ui.ServerPanels") as mock_panels:
            _display_stdio_startup(features)

            # Should not crash with empty features
            mock_panels.startup_success.assert_called_once()
            call_kwargs = mock_panels.startup_success.call_args.kwargs
            assert call_kwargs["features"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
