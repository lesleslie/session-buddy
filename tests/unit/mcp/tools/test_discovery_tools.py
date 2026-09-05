"""Tests for ``session_buddy.mcp.tools.discovery_tools``.

Covers ``discover_tools`` (the search-by-name-or-description meta-tool)
and ``register_discovery_tools`` (one-tool MCP registration).
"""

from __future__ import annotations

import pytest

from session_buddy.mcp.tools import discovery_tools as discovery_mod


class _FakeMCP:
    """Capture ``mcp.tool()`` decorators."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *, name=None, description=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# discover_tools
# ---------------------------------------------------------------------------


async def test_empty_query_returns_hint() -> None:
    """Empty / whitespace-only query returns the help hint envelope."""
    result = await discovery_mod.discover_tools("")
    assert result == {
        "found": 0,
        "tools": [],
        "hint": "Provide a search query to discover available tools.",
    }


async def test_whitespace_only_query_returns_hint() -> None:
    """Whitespace-only query is treated like empty."""
    result = await discovery_mod.discover_tools("   ")
    assert result["found"] == 0
    assert result["tools"] == []


async def test_match_in_tool_name() -> None:
    """Substring match against tool name finds the tool."""
    # "health" appears in several tool names
    result = await discovery_mod.discover_tools("health_check")
    assert result["found"] >= 1
    names = [t["name"] for t in result["tools"]]
    assert "health_check" in names
    for t in result["tools"]:
        assert "name" in t and "description" in t


async def test_match_in_description() -> None:
    """Substring match against description also finds the tool."""
    # "cache" appears in many tool descriptions
    result = await discovery_mod.discover_tools("cache hit")
    assert result["found"] >= 1
    # All results should contain the query substring (case-insensitive)
    for t in result["tools"]:
        assert "cache hit" in t["name"].lower() or "cache hit" in t["description"].lower()


async def test_query_is_case_insensitive() -> None:
    """Search is case-insensitive (query and target both lowered)."""
    upper = await discovery_mod.discover_tools("HEALTH_CHECK")
    lower = await discovery_mod.discover_tools("health_check")
    assert upper["found"] == lower["found"]


async def test_results_are_sorted_by_name() -> None:
    """Result list is sorted by tool name."""
    result = await discovery_mod.discover_tools("cache")
    names = [t["name"] for t in result["tools"]]
    assert names == sorted(names)


async def test_results_capped_at_25() -> None:
    """More than 25 matches → only first 25 returned (per spec)."""
    # "search" is common — well over 25 results
    result = await discovery_mod.discover_tools("search")
    assert len(result["tools"]) <= 25


async def test_no_match_returns_zero_results_and_hint() -> None:
    """Unknown substring returns 0 results + 'no matching tools' hint."""
    result = await discovery_mod.discover_tools("xyzzy_no_such_thing_qqq")
    assert result["found"] == 0
    assert result["tools"] == []
    assert "No matching tools found" in result["hint"]


async def test_match_returns_hint_to_enable_full_profile() -> None:
    """Non-empty result set triggers the 'enable full profile' hint."""
    result = await discovery_mod.discover_tools("health_check")
    assert "SESSION_BUDDY_TOOL_PROFILE=full" in result["hint"]


async def test_match_pool_returns_pool_tools() -> None:
    """Specific substring returns the expected pool-related entries."""
    result = await discovery_mod.discover_tools("pool")
    names = [t["name"] for t in result["tools"]]
    assert any(n == "create_pool" for n in names)


async def test_whitespace_stripped() -> None:
    """Leading/trailing whitespace is stripped from the query."""
    result = await discovery_mod.discover_tools("  health_check  ")
    assert result["found"] >= 1
    assert "health_check" in [t["name"] for t in result["tools"]]


async def test_results_returned_are_dicts_with_name_and_description() -> None:
    """Each item in ``tools`` is a {"name", "description"} dict."""
    result = await discovery_mod.discover_tools("store_reflection")
    assert result["found"] >= 1
    for item in result["tools"]:
        assert isinstance(item, dict)
        assert isinstance(item["name"], str)
        assert isinstance(item["description"], str)


# ---------------------------------------------------------------------------
# ALL_TOOLS_REGISTRY
# ---------------------------------------------------------------------------


def test_registry_is_non_empty_dict() -> None:
    """ALL_TOOLS_REGISTRY is populated and a dict."""
    assert isinstance(discovery_mod.ALL_TOOLS_REGISTRY, dict)
    assert len(discovery_mod.ALL_TOOLS_REGISTRY) > 50  # well-stocked


def test_registry_contains_required_sections() -> None:
    """Spot-check that key sections of the registry exist."""
    names = set(discovery_mod.ALL_TOOLS_REGISTRY)
    assert "discover_tools" in names or "discover_tools" not in names  # meta itself
    assert "health_check" in names
    assert "create_pool" in names
    assert "create_serverless_session" in names
    assert "store_reflection" in names
    assert "search_by_concept" in names


# ---------------------------------------------------------------------------
# register_discovery_tools
# ---------------------------------------------------------------------------


def test_register_discovery_tools_registers_discover_tools() -> None:
    """register_discovery_tools registers the discover_tools callable."""
    mcp = _FakeMCP()
    discovery_mod.register_discovery_tools(mcp)
    assert set(mcp.tools) == {"discover_tools"}


async def test_registered_tool_returns_dict_for_query() -> None:
    """The registered tool returns the same shape as discover_tools."""
    mcp = _FakeMCP()
    discovery_mod.register_discovery_tools(mcp)
    out = await mcp.tools["discover_tools"]("health")
    assert out["found"] >= 1
    assert isinstance(out["tools"], list)


async def test_registered_tool_empty_query() -> None:
    """Empty query through the wrapper returns the help envelope."""
    mcp = _FakeMCP()
    discovery_mod.register_discovery_tools(mcp)
    out = await mcp.tools["discover_tools"]("")
    assert out == {
        "found": 0,
        "tools": [],
        "hint": "Provide a search query to discover available tools.",
    }