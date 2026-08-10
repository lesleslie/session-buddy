"""Verify Task 9 wiring: store_cross_repo_work registered for STANDARD profile.

Tests three independent wiring steps:
1. ``register_cross_repo_work_tools`` is appended to ``STANDARD_REGISTRATIONS``.
2. ``register_cross_repo_work_tools`` is keyed in ``_ALL_REGISTERS``.
3. The function composes the tool with the correct MCP-visible name.

These are integration tests because they touch multiple layers (profile
registry, server module, registration callable).

Step 2 deliberately uses AST parsing of ``server.py`` instead of importing
it. Importing ``session_buddy.mcp.server`` triggers a pre-existing
circular import through ``intelligence_tools.py``'s eager
``from session_buddy.mcp.server import mcp``; the membership check below
is satisfied as long as the registration key is present in the
``_ALL_REGISTERS`` dict literal at module level, which is the same
property the sibling drift test
(:mod:`tests.unit.mcp.test_tool_profile_drift`) verifies via AST.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_PY = _REPO_ROOT / "session_buddy" / "mcp" / "server.py"


def test_register_cross_repo_work_tools_in_standard_profile() -> None:
    from session_buddy.mcp.tools.profiles import STANDARD_REGISTRATIONS

    assert "register_cross_repo_work_tools" in STANDARD_REGISTRATIONS, (
        f"register_cross_repo_work_tools missing from STANDARD; "
        f"profile has {STANDARD_REGISTRATIONS}"
    )


def test_register_cross_repo_work_tools_in_all_registers() -> None:
    """Assert the registration key is present in ``_ALL_REGISTERS`` via AST."""
    tree = ast.parse(_SERVER_PY.read_text())
    keys: set[str] = set()
    for node in ast.walk(tree):
        value: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_ALL_REGISTERS":
                value = node.value
        elif isinstance(node, ast.Assign) and node.targets:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "_ALL_REGISTERS":
                value = node.value
        if not isinstance(value, ast.Dict):
            continue
        keys.update(
            k.value for k in value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        )
    assert "register_cross_repo_work_tools" in keys


def test_register_function_creates_store_cross_repo_work_tool() -> None:
    """Verify the registered tool is callable and named correctly."""
    from unittest.mock import MagicMock

    from session_buddy.mcp.tools.cross_repo_work_register import (
        register_cross_repo_work_tools,
    )

    fake_server = MagicMock()
    fake_server.tool = MagicMock()

    register_cross_repo_work_tools(fake_server)

    # Verify @mcp_server.tool was called with name="store_cross_repo_work"
    fake_server.tool.assert_called()
    call_kwargs = fake_server.tool.call_args.kwargs
    assert call_kwargs.get("name") == "store_cross_repo_work"
