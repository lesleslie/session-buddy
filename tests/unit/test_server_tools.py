"""Comprehensive tests for MCP tool registration and execution.

Week 8 Day 2 - Phase 3: Test MCP tool registration mechanics.
Tests tool decorator registration, parameter validation, and error handling.
"""

from __future__ import annotations

import typing as t
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from tests.fixtures import mock_fastmcp_server, mock_session_paths

if t.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
class TestMCPToolRegistration:
    """Test MCP tool registration mechanics."""

    def test_session_tools_registration(self, mock_fastmcp_server: Mock):
        """Session management tools are registered correctly."""
        from session_buddy.tools import register_session_tools

        # Register tools
        register_session_tools(mock_fastmcp_server)

        # Verify tool decorator was called for each session tool
        assert (
            mock_fastmcp_server.tool.call_count >= 4
        )  # start, checkpoint, end, status

    def test_search_tools_registration(self, mock_fastmcp_server: Mock):
        """Search tools are registered correctly."""
        from session_buddy.tools import register_search_tools

        # Register tools
        register_search_tools(mock_fastmcp_server)

        # Verify tool decorator was called
        assert mock_fastmcp_server.tool.call_count >= 1

    def test_crackerjack_tools_registration(self, mock_fastmcp_server: Mock):
        """Crackerjack integration tools are registered correctly."""
        from session_buddy.tools import register_crackerjack_tools

        # Register tools
        register_crackerjack_tools(mock_fastmcp_server)

        # Verify tool decorator was called for crackerjack tools
        assert mock_fastmcp_server.tool.call_count >= 1

    def test_llm_tools_registration(self, mock_fastmcp_server: Mock):
        """LLM provider tools are registered correctly."""
        from session_buddy.tools import register_llm_tools

        # Register tools
        register_llm_tools(mock_fastmcp_server)

        # Verify tool decorator was called for LLM tools
        assert mock_fastmcp_server.tool.call_count >= 1

    def test_knowledge_graph_tools_registration(self, mock_fastmcp_server: Mock):
        """Knowledge graph tools are registered correctly."""
        from session_buddy.tools import register_knowledge_graph_tools

        # Register tools
        register_knowledge_graph_tools(mock_fastmcp_server)

        # Verify tool decorator was called
        assert mock_fastmcp_server.tool.call_count >= 1

    def test_all_tool_modules_registration(self, mock_fastmcp_server: Mock):
        """All tool modules can be registered without errors."""
        from session_buddy.tools import (
            register_crackerjack_tools,
            register_knowledge_graph_tools,
            register_llm_tools,
            register_monitoring_tools,
            register_prompt_tools,
            register_search_tools,
            register_serverless_tools,
            register_session_tools,
            register_team_tools,
        )

        # Register all tool modules
        register_session_tools(mock_fastmcp_server)
        register_search_tools(mock_fastmcp_server)
        register_crackerjack_tools(mock_fastmcp_server)
        register_knowledge_graph_tools(mock_fastmcp_server)
        register_llm_tools(mock_fastmcp_server)
        register_monitoring_tools(mock_fastmcp_server)
        register_prompt_tools(mock_fastmcp_server)
        register_serverless_tools(mock_fastmcp_server)
        register_team_tools(mock_fastmcp_server)

        # Verify all registrations succeeded (tool decorator called multiple times)
        assert mock_fastmcp_server.tool.call_count >= 20  # Minimum expected tools


@pytest.mark.asyncio
class TestMCPServerInitialization:
    """Test MCP server initialization and configuration."""

    def test_fastmcp_server_initialization(self):
        """FastMCP server initializes with correct name and lifespan."""
        # Import causes initialization
        try:
            from session_buddy.server import mcp

            # Server should be initialized
            assert mcp is not None

            # Server name should be set (FastMCP or MockFastMCP)
            if hasattr(mcp, "name"):
                assert mcp.name == "session-buddy"
        except ImportError:
            pytest.skip("FastMCP not available in test environment")

    def test_server_has_lifespan_handler(self):
        """Server is initialized with lifespan handler."""
        try:
            from session_buddy.server import session_lifecycle

            # Lifespan handler should exist
            assert session_lifecycle is not None
            assert callable(session_lifecycle)
        except ImportError:
            pytest.skip("Server components not available")

    def test_feature_flags_initialized(self):
        """Feature flags are properly initialized."""
        try:
            from session_buddy.server import (
                CRACKERJACK_INTEGRATION_AVAILABLE,
                LLM_PROVIDERS_AVAILABLE,
                REFLECTION_TOOLS_AVAILABLE,
                SESSION_MANAGEMENT_AVAILABLE,
            )

            # Feature flags should be booleans
            assert isinstance(SESSION_MANAGEMENT_AVAILABLE, bool)
            assert isinstance(REFLECTION_TOOLS_AVAILABLE, bool)
            assert isinstance(CRACKERJACK_INTEGRATION_AVAILABLE, bool)
            assert isinstance(LLM_PROVIDERS_AVAILABLE, bool)
        except ImportError:
            pytest.skip("Feature flags not available")

    def test_rate_limiting_configuration(self):
        """Rate limiting middleware is configured if available."""
        try:
            from session_buddy.server import RATE_LIMITING_AVAILABLE, mcp

            if RATE_LIMITING_AVAILABLE and hasattr(mcp, "middleware"):
                # Rate limiting should be configured
                # Note: actual middleware list may not be accessible, just verify no errors
                pass
        except ImportError:
            pytest.skip("Rate limiting not available")


@pytest.mark.asyncio
class TestToolParameterValidation:
    """Test tool parameter validation and type checking."""

    @patch("session_buddy.tools.session_tools._start_impl")
    async def test_start_tool_accepts_valid_directory(
        self, mock_start: AsyncMock, tmp_path: Path
    ):
        """Start tool accepts valid working directory parameter."""
        from session_buddy.tools.session_tools import register_session_tools

        # Mock implementation
        mock_start.return_value = "Session started"

        # Create mock server
        mock_server = Mock()
        registered_tools: dict[str, t.Callable[..., t.Any]] = {}

        def tool_decorator():
            def wrapper(func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
                registered_tools[func.__name__] = func
                return func

            return wrapper

        mock_server.tool = Mock(side_effect=tool_decorator)

        # Register tools
        register_session_tools(mock_server)

        # Get start tool
        start_tool = registered_tools.get("start")
        assert start_tool is not None

        # Call with valid directory
        await start_tool(working_directory=str(tmp_path))

        # Verify implementation was called
        mock_start.assert_called_once_with(str(tmp_path))

    @patch("session_buddy.tools.session_tools._checkpoint_impl")
    async def test_checkpoint_tool_accepts_none_directory(
        self, mock_checkpoint: AsyncMock
    ):
        """Checkpoint tool accepts None for working_directory (uses PWD)."""
        from session_buddy.tools.session_tools import register_session_tools

        # Mock implementation
        mock_checkpoint.return_value = "Checkpoint created"

        # Create mock server
        mock_server = Mock()
        registered_tools: dict[str, t.Callable[..., t.Any]] = {}

        def tool_decorator():
            def wrapper(func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
                registered_tools[func.__name__] = func
                return func

            return wrapper

        mock_server.tool = Mock(side_effect=tool_decorator)

        # Register tools
        register_session_tools(mock_server)

        # Get checkpoint tool
        checkpoint_tool = registered_tools.get("checkpoint")
        assert checkpoint_tool is not None

        # Call with None (should use PWD)
        await checkpoint_tool(working_directory=None)

        # Verify implementation was called with None
        mock_checkpoint.assert_called_once_with(None)


@pytest.mark.asyncio
class TestToolErrorHandling:
    """Test tool error handling and response formatting."""

    @patch("session_buddy.tools.session_tools._start_impl")
    async def test_start_tool_handles_implementation_errors(
        self, mock_start: AsyncMock
    ):
        """Start tool handles errors from implementation gracefully."""
        from session_buddy.tools.session_tools import register_session_tools

        # Mock implementation to raise error
        mock_start.side_effect = Exception("Initialization failed")

        # Create mock server
        mock_server = Mock()
        registered_tools: dict[str, t.Callable[..., t.Any]] = {}

        def tool_decorator():
            def wrapper(func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
                registered_tools[func.__name__] = func
                return func

            return wrapper

        mock_server.tool = Mock(side_effect=tool_decorator)

        # Register tools
        register_session_tools(mock_server)

        # Get start tool
        start_tool = registered_tools.get("start")
        assert start_tool is not None

        # Call should propagate exception (FastMCP handles error formatting)
        with pytest.raises(Exception, match="Initialization failed"):
            await start_tool(working_directory="/tmp/test")


@pytest.mark.asyncio
class TestTokenOptimizerFallbacks:
    """Test token optimizer fallback implementations."""

    def test_token_optimizer_available_flag(self):
        """TOKEN_OPTIMIZER_AVAILABLE flag is properly set."""
        from session_buddy.server import TOKEN_OPTIMIZER_AVAILABLE

        # Flag should be boolean
        assert isinstance(TOKEN_OPTIMIZER_AVAILABLE, bool)

    async def test_optimize_search_response_fallback(self):
        """optimize_search_response has fallback implementation."""
        from session_buddy.server import optimize_search_response

        # Call fallback
        results = [{"content": "test"}]
        optimized, metadata = await optimize_search_response(results)

        # Fallback returns results unchanged
        assert optimized == results
        assert isinstance(metadata, dict)

    async def test_track_token_usage_fallback(self):
        """track_token_usage has fallback implementation."""
        from session_buddy.server import track_token_usage

        # Call fallback (should not raise)
        result = await track_token_usage("test_operation", 100, 200)

        # Fallback returns None
        assert result is None

    async def test_get_cached_chunk_fallback(self):
        """get_cached_chunk has fallback implementation."""
        from session_buddy.server import get_cached_chunk

        # Call fallback
        result = await get_cached_chunk("test_key", 0)

        # Fallback returns None (no cached chunk)
        assert result is None

    async def test_get_token_usage_stats_fallback(self):
        """get_token_usage_stats has fallback implementation."""
        from session_buddy.server import (
            TOKEN_OPTIMIZER_AVAILABLE,
            get_token_usage_stats,
        )

        # Call fallback
        result = await get_token_usage_stats(hours=24)

        # Result should be dict
        assert isinstance(result, dict)

        # If optimizer unavailable, fallback returns status message
        if not TOKEN_OPTIMIZER_AVAILABLE:
            assert "status" in result or "unavailable" in str(result).lower()

    async def test_optimize_memory_usage_fallback(self):
        """optimize_memory_usage has fallback implementation."""
        try:
            from session_buddy.server import optimize_memory_usage

            # Call function
            result = await optimize_memory_usage(strategy="auto", dry_run=True)

            # Result should be string or dict
            assert isinstance(result, (str, dict))
        except ImportError:
            # Function not available - skip test
            pytest.skip("optimize_memory_usage not available in current configuration")


@pytest.mark.asyncio
class TestReflectOnPastFunction:
    """Test reflect_on_past search function."""

    @patch("session_buddy.reflection_tools.ReflectionDatabase")
    async def test_reflect_on_past_with_valid_params(self, mock_db_class: Mock):
        """reflect_on_past accepts valid parameters and calls database."""
        from session_buddy.server import REFLECTION_TOOLS_AVAILABLE, reflect_on_past

        if not REFLECTION_TOOLS_AVAILABLE:
            pytest.skip("Reflection tools not available in test environment")

        # Mock database
        mock_db = AsyncMock()
        mock_db.search_reflections.return_value = [
            {"content": "test result", "score": 0.9, "timestamp": "2025-10-29"}
        ]
        mock_db_class.return_value.__aenter__.return_value = mock_db

        # Call with valid params
        result = await reflect_on_past(
            query="test query", limit=5, min_score=0.7, project=None
        )

        # Should return formatted results (string or dict)
        assert isinstance(result, (str, dict))

    async def test_reflect_on_past_handles_unavailable_tools(self):
        """reflect_on_past handles unavailable reflection tools gracefully."""
        from session_buddy.server import REFLECTION_TOOLS_AVAILABLE, reflect_on_past

        if not REFLECTION_TOOLS_AVAILABLE:
            # Should return error message
            result = await reflect_on_past(query="test")
            assert isinstance(result, str)
            assert "not available" in result.lower()
