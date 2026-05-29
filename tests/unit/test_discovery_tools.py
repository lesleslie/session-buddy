"""Tests for discovery_tools.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.discovery_tools import (
    ALL_TOOLS_REGISTRY,
    discover_tools,
    register_discovery_tools,
)


# ---------------------------------------------------------------------------
# ALL_TOOLS_REGISTRY tests
# ---------------------------------------------------------------------------


class TestAllToolsRegistry:
    """Tests for the ALL_TOOLS_REGISTRY dict."""

    def test_registry_is_non_empty(self):
        """Registry must contain entries."""
        assert len(ALL_TOOLS_REGISTRY) > 0

    def test_registry_values_are_strings(self):
        """All registry values must be non-empty strings."""
        for name, description in ALL_TOOLS_REGISTRY.items():
            assert isinstance(name, str), f"Tool name {name!r} is not a string"
            assert isinstance(description, str), f"Description for {name} is not a string"
            assert len(description) > 0, f"Description for {name} is empty"

    def test_registry_keys_are_unique(self):
        """Tool names must be unique."""
        assert len(ALL_TOOLS_REGISTRY) == len(set(ALL_TOOLS_REGISTRY.keys()))

    def test_registry_has_expected_categories(self):
        """Registry should contain tools from expected categories."""
        expected_prefixes = [
            "ping",  # Health
            "start",  # Session lifecycle
            "search",  # Search
            "list_hooks",  # Hooks
            "store_conversation",  # Conversation
            "extract",  # Extraction
            "create_entity",  # Knowledge graph
            "clear_query_cache",  # Cache
            "detect_intent",  # Intent detection
            "crackerjack",  # Crackerjack integration
            "feature_flags",  # Feature flags
            "get_prometheus_metrics",  # Monitoring
            "create_pool",  # Pools
            "create_serverless_session",  # Serverless
            "create_team",  # Team tools
            "chat_with_llm",  # LLM tools
        ]
        for prefix in expected_prefixes:
            matches = [k for k in ALL_TOOLS_REGISTRY if k.startswith(prefix)]
            assert len(matches) > 0, f"No tools found with prefix '{prefix}'"

    def test_registry_has_aliases(self):
        """Registry should contain pool aliases."""
        alias_names = ["pool_list", "pool_create", "pool_delete", "pool_execute"]
        for name in alias_names:
            assert name in ALL_TOOLS_REGISTRY, f"Alias '{name}' not found in registry"


# ---------------------------------------------------------------------------
# discover_tools() function tests
# ---------------------------------------------------------------------------


class TestDiscoverTools:
    """Tests for the discover_tools() function."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock FastMCP server."""
        mcp = MagicMock()
        mcp.tool = MagicMock(return_value=lambda f: f)
        return mcp

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_results(self):
        """Empty query should return empty results with hint."""
        result = await discover_tools("")

        assert result["found"] == 0
        assert result["tools"] == []
        assert "hint" in result

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_empty_results(self):
        """Whitespace-only query should return empty results."""
        result = await discover_tools("   ")

        assert result["found"] == 0
        assert result["tools"] == []

    @pytest.mark.asyncio
    async def test_exact_tool_name_match(self):
        """Exact tool name match should return that tool."""
        result = await discover_tools("ping")

        assert result["found"] == 1
        assert result["tools"][0]["name"] == "ping"
        assert "Liveness probe" in result["tools"][0]["description"]

    @pytest.mark.asyncio
    async def test_partial_tool_name_match(self):
        """Partial tool name match should return matching tools."""
        result = await discover_tools("pool")

        assert result["found"] > 1
        names = [t["name"] for t in result["tools"]]
        assert all("pool" in n.lower() for n in names)

    @pytest.mark.asyncio
    async def test_description_match(self):
        """Search should match tool descriptions."""
        result = await discover_tools("health check")

        # Should match health_check, get_health_status, pycharm_health, etc.
        assert result["found"] > 0
        # All returned tools should have "health" or "check" in name or description
        for tool in result["tools"]:
            text = tool["name"] + " " + tool["description"]
            assert "health" in text.lower() or "check" in text.lower()

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        """Search should be case-insensitive."""
        lower_result = await discover_tools("search")
        upper_result = await discover_tools("SEARCH")
        mixed_result = await discover_tools("SeArCh")

        assert lower_result["found"] == upper_result["found"]
        assert upper_result["found"] == mixed_result["found"]

    @pytest.mark.asyncio
    async def test_results_sorted_alphabetically(self):
        """Results should be sorted alphabetically by name."""
        result = await discover_tools("get")

        names = [t["name"] for t in result["tools"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_results_limited_to_25(self):
        """Results should be limited to 25 tools."""
        # Use a query that matches many tools
        result = await discover_tools("get")

        assert len(result["tools"]) <= 25

    @pytest.mark.asyncio
    async def test_no_match_returns_hint(self):
        """No matches should return helpful hint."""
        result = await discover_tools("xyzzy_nonexistent_tool")

        assert result["found"] == 0
        assert result["tools"] == []
        assert "No matching tools found" in result["hint"]

    @pytest.mark.asyncio
    async def test_matches_return_enablement_hint(self):
        """Matches should return profile enablement hint."""
        result = await discover_tools("ping")

        assert result["found"] > 0
        assert "hint" in result
        assert "SESSION_BUDDY_TOOL_PROFILE" in result["hint"]

    @pytest.mark.asyncio
    async def test_query_matching_both_name_and_description(self):
        """Tools matching on both name and description should be included."""
        # "search" matches in names (quick_search, search_conversations, etc.)
        # but also matches in descriptions containing "search"
        result = await discover_tools("search")

        assert result["found"] > 0
        for tool in result["tools"]:
            combined = tool["name"].lower() + " " + tool["description"].lower()
            assert "search" in combined

    @pytest.mark.asyncio
    async def test_capability_matching(self):
        """Test matching by capability keywords in descriptions."""
        # Search for something that appears in descriptions but not tool names
        result = await discover_tools("semantic")

        # Should find tools with "semantic" in their description
        for tool in result["tools"]:
            assert "semantic" in tool["description"].lower() or "semantic" in tool["name"].lower()

    @pytest.mark.asyncio
    async def test_registry_contains_expected_tools(self):
        """Verify specific important tools are in the registry."""
        important_tools = [
            "ping",
            "health_check",
            "start",
            "end",
            "status",
            "checkpoint",
            "quick_search",
            "progressive_search",
            "create_entity",
            "create_pool",
            "list_pools",
            "crackerjack_run",
            "sync_to_akosha",
        ]
        for tool_name in important_tools:
            assert tool_name in ALL_TOOLS_REGISTRY, f"Tool '{tool_name}' not in registry"


# ---------------------------------------------------------------------------
# register_discovery_tools() tests
# ---------------------------------------------------------------------------


class TestRegisterDiscoveryTools:
    """Tests for register_discovery_tools()."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock FastMCP server."""
        mcp = MagicMock()
        mcp.tool = MagicMock(return_value=lambda f: f)
        return mcp

    def test_registers_tool_decorator(self, mock_mcp):
        """register_discovery_tools should call mcp.tool()."""
        register_discovery_tools(mock_mcp)
        mock_mcp.tool.assert_called_once()

    def test_registers_discover_tools(self, mock_mcp):
        """register_discovery_tools should register discover_tools function."""
        register_discovery_tools(mock_mcp)

        # The decorator was applied, verify it was called with the function
        call_args = mock_mcp.tool.call_args
        assert call_args is not None

    def test_decorated_function_is_async(self, mock_mcp):
        """The decorated discover_tools should be an async function."""
        register_discovery_tools(mock_mcp)

        # Get the decorated function
        decorated_func = mock_mcp.tool.call_args[0][0]

        # It should be awaitable
        import asyncio
        result = decorated_func(query="ping")
        assert asyncio.iscoroutine(result)

    @pytest.mark.asyncio
    async def test_registered_function_behaves_correctly(self, mock_mcp):
        """The registered discover_tools should work correctly."""
        register_discovery_tools(mock_mcp)

        # Get the decorated function and call it
        decorated_func = mock_mcp.tool.call_args[0][0]
        result = await decorated_func(query="health")

        assert "found" in result
        assert "tools" in result
        assert "hint" in result


# ---------------------------------------------------------------------------
# Integration-style tests
# ---------------------------------------------------------------------------


class TestDiscoveryToolsIntegration:
    """Integration tests for discovery tools behavior."""

    @pytest.mark.asyncio
    async def test_search_returns_valid_structure(self):
        """Verify search results have expected structure."""
        result = await discover_tools("session")

        for tool in result["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)

    @pytest.mark.asyncio
    async def test_search_with_common_word(self):
        """Search with common words should return reasonable number of results."""
        result = await discover_tools("get")

        # "get" is a common prefix, should find many
        assert result["found"] > 10
        assert len(result["tools"]) == min(25, result["found"])

    @pytest.mark.asyncio
    async def test_search_tool_name_substring(self):
        """Tool name substring search should work."""
        # "conversation" appears in tool names
        result = await discover_tools("conversation")

        names = [t["name"] for t in result["tools"]]
        assert any("conversation" in n for n in names)

    @pytest.mark.asyncio
    async def test_registry_count_reasonable(self):
        """Registry should have a reasonable number of tools."""
        # Session-buddy should have many tools
        assert len(ALL_TOOLS_REGISTRY) >= 100

    @pytest.mark.asyncio
    async def test_phrase_search(self):
        """Search for multi-word phrase should work."""
        result = await discover_tools("health check")

        assert result["found"] > 0
        for tool in result["tools"]:
            combined = (tool["name"] + " " + tool["description"]).lower()
            assert "health" in combined or "check" in combined
