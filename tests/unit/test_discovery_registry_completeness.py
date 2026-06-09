"""Static + functional completeness tests for the cross-system discovery registry.

Phase 1.5 cross-component wiring (Item 5 of bodai-adoption-phase-1.5.md).

The ``ALL_TOOLS_REGISTRY`` dict in ``session_buddy/mcp/tools/discovery_tools.py``
is the meta-index that ``discover_tools(query)`` searches when a tool is
not loaded by the active profile. If a new MCP tool is added to
``session_buddy/mcp/tools/memory/search_tools.py`` without a matching
registry entry, it becomes invisible to Claude — the tool exists in the
codebase but is undiscoverable through the meta-tool.

These tests pin two contracts:

1. **Static completeness**: every function decorated with ``@mcp.tool()``
   inside ``search_tools.py`` has a key in ``ALL_TOOLS_REGISTRY``. This
   prevents future drift between the live MCP surface and the
   discovery meta-index.
2. **Functional relevance**: the new Phase 1.5 tools
   (``distill_skills_now`` and ``search_distilled_skills``) surface in
   the top 3 results when Claude asks ``discover_tools("distill
   skills")`` — the contract from the plan's acceptance criteria.

The plan's acceptance criterion is:

    ``discover_tools("distill skills")`` returns ``distill_skills_now``
    and ``search_distilled_skills`` in the top 3.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from session_buddy.mcp.tools.discovery_tools import (
    ALL_TOOLS_REGISTRY,
    discover_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SEARCH_TOOLS_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "mcp"
    / "tools"
    / "memory"
    / "search_tools.py"
)


def _tools_registered_in_search_module() -> set[str]:
    """Return the set of function names decorated with ``@mcp.tool()``.

    Walks ``search_tools.py`` with the ``ast`` module and picks up every
    ``FunctionDef`` / ``AsyncFunctionDef`` node whose nearest preceding
    decorator is ``mcp.tool`` (or ``mcp.tool()``).

    The decorators live on nested functions inside ``_register_*`` helpers
    (e.g. ``_register_specialized_search_tools``), so the walk is
    recursive rather than top-level-only.
    """
    source = _SEARCH_TOOLS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if _is_mcp_tool_decorator(decorator):
                names.add(node.name)
                break
    return names


def _is_mcp_tool_decorator(decorator: ast.expr) -> bool:
    """Return True iff ``decorator`` is ``@mcp.tool()`` (or ``@mcp.tool``)."""
    if isinstance(decorator, ast.Call):
        # ``@mcp.tool()`` — the call's func must be ``mcp.tool`` or
        # an attribute access of ``mcp.tool``.
        func = decorator.func
        return _is_mcp_tool_attribute(func)
    return _is_mcp_tool_attribute(decorator)


def _is_mcp_tool_attribute(node: ast.expr) -> bool:
    """True iff ``node`` is the ``mcp.tool`` attribute access."""
    if not isinstance(node, ast.Attribute):
        return False
    return node.attr == "tool" and isinstance(node.value, ast.Name) and node.value.id == "mcp"


# ---------------------------------------------------------------------------
# Static completeness check
# ---------------------------------------------------------------------------


class TestDiscoveryRegistryStaticCompleteness:
    """Every ``@mcp.tool()`` in search_tools.py must have a registry entry.

    The registry is the only way Claude can find tools that the active
    profile hasn't loaded, so omitting an entry makes a tool effectively
    invisible to the cross-system discovery flow.
    """

    def test_search_tools_module_exists(self) -> None:
        """Sanity check: the search_tools.py source file is locatable."""
        assert _SEARCH_TOOLS_PATH.is_file(), (
            f"Expected search_tools.py at {_SEARCH_TOOLS_PATH}"
        )

    def test_ast_walk_finds_at_least_one_tool(self) -> None:
        """Sanity check: the static walk actually finds decorated tools.

        Catches a silent failure mode where the AST walker returns an
        empty set (e.g., if a refactor moves the decorators elsewhere
        without updating the test).
        """
        registered = _tools_registered_in_search_module()
        assert len(registered) > 0, (
            "No @mcp.tool() decorated functions found in search_tools.py. "
            "Either the file no longer registers tools this way, or the "
            "static walker is broken."
        )

    def test_every_mcp_tool_has_registry_entry(self) -> None:
        """Static check: every @mcp.tool() in search_tools.py is in the registry.

        This is the primary contract from the plan's Item 5 acceptance:
        "every tool registered in the MCP server has a corresponding
        entry in ALL_TOOLS_REGISTRY".
        """
        registered = _tools_registered_in_search_module()
        missing = sorted(name for name in registered if name not in ALL_TOOLS_REGISTRY)

        assert not missing, (
            "The following @mcp.tool() functions in search_tools.py have "
            "no entry in ALL_TOOLS_REGISTRY. Add a one-line description "
            "for each (or sharpen the existing one) so cross-system "
            "discover_tools() can find them:\n"
            + "\n".join(f"  - {name}" for name in missing)
        )

    def test_phase_1_5_tools_present_in_registry(self) -> None:
        """The 5 Phase 1.5 tools must all be present in the registry.

        This pins the existing surface so a future refactor can't
        accidentally drop one of the new tools from the meta-index
        without the test catching it.
        """
        phase_1_5_tools = {
            "peer_context",
            "update_peer_model",
            "causal_chain",
            "distill_skills_now",
            "search_distilled_skills",
        }
        missing = sorted(phase_1_5_tools - set(ALL_TOOLS_REGISTRY.keys()))
        assert not missing, (
            "Phase 1.5 tool(s) missing from ALL_TOOLS_REGISTRY: "
            + ", ".join(missing)
        )

    @pytest.mark.parametrize(
        "tool_name",
        [
            "peer_context",
            "update_peer_model",
            "causal_chain",
            "distill_skills_now",
            "search_distilled_skills",
        ],
    )
    def test_phase_1_5_description_mentions_new_contract(self, tool_name: str) -> None:
        """Phase 1.5 descriptions must sharpen to mention the new contract.

        The plan requires the description to mention new contract details
        like the ``importance_score >= 0.7`` quality floor on
        ``distill_skills_now``. We assert a minimum length bump (the
        original descriptions were very terse) plus the presence of at
        least one Phase 1.5 marker keyword.
        """
        description = ALL_TOOLS_REGISTRY[tool_name]
        # Sharpened descriptions are at least 60 chars (the originals
        # were around 50-60 chars of boilerplate).
        assert len(description) >= 60, (
            f"Description for {tool_name!r} is too terse; expected at least "
            f"60 chars to surface the Phase 1.5 contract. Got: {description!r}"
        )
        lower = description.lower()
        marker_keywords = {
            "peer_context": ("peer", "context"),
            "update_peer_model": ("peer", "model"),
            "causal_chain": ("causal",),
            "distill_skills_now": ("distill", "skill"),
            "search_distilled_skills": ("distill", "skill"),
        }
        keywords = marker_keywords[tool_name]
        assert all(kw in lower for kw in keywords), (
            f"Description for {tool_name!r} is missing marker keywords "
            f"{keywords!r}; the plan requires the new contract to be visible. "
            f"Got: {description!r}"
        )


# ---------------------------------------------------------------------------
# Functional relevance check
# ---------------------------------------------------------------------------


class TestDiscoverToolsDistillSkills:
    """Functional contract from Item 5 acceptance.

    ``discover_tools("distill skills")`` must return both
    ``distill_skills_now`` and ``search_distilled_skills`` in the top 3
    results.
    """

    @pytest.mark.asyncio
    async def test_distill_skills_now_appears_in_top_3(self) -> None:
        """distill_skills_now is one of the top 3 results for 'distill skills'."""
        result = await discover_tools("distill skills")

        assert result["found"] >= 2, (
            f"Expected at least 2 matches for 'distill skills', "
            f"got {result['found']}"
        )
        top_3_names = [tool["name"] for tool in result["tools"][:3]]
        assert "distill_skills_now" in top_3_names, (
            f"distill_skills_now should be in the top 3 results, "
            f"got: {top_3_names}"
        )

    @pytest.mark.asyncio
    async def test_search_distilled_skills_appears_in_top_3(self) -> None:
        """search_distilled_skills is one of the top 3 results for 'distill skills'."""
        result = await discover_tools("distill skills")

        top_3_names = [tool["name"] for tool in result["tools"][:3]]
        assert "search_distilled_skills" in top_3_names, (
            f"search_distilled_skills should be in the top 3 results, "
            f"got: {top_3_names}"
        )

    @pytest.mark.asyncio
    async def test_distill_skills_query_returns_both_tools(self) -> None:
        """Combined assertion: both Phase 1.5 distill tools surface."""
        result = await discover_tools("distill skills")

        names = {tool["name"] for tool in result["tools"]}
        assert "distill_skills_now" in names
        assert "search_distilled_skills" in names
