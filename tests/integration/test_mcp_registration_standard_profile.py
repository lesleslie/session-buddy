"""Verify Task 9 wiring: store_cross_repo_work registered for STANDARD profile.

Tests three independent wiring steps:
1. ``register_cross_repo_work_tools`` is in ``STANDARD_REGISTRATIONS``.
2. ``register_cross_repo_work_tools`` is keyed in ``REGISTRATION_MAP``
   (W0 helper dispatch map in ``profiles.py`` -- replaces the legacy
   ``_ALL_REGISTERS`` dict that lived in ``server.py``).
3. The function composes the tool with the correct MCP-visible name.

These are integration tests because they touch multiple layers (profile
registry, profiles module, registration callable).

Step 2 deliberately uses AST parsing of ``profiles.py`` instead of
importing it. Importing ``session_buddy.mcp.profiles`` triggers a
pre-existing circular import through ``intelligence_tools.py``'s
eager ``from session_buddy.mcp.server import mcp``; the membership
check below is satisfied as long as the registration key is present in
the ``REGISTRATION_MAP`` dict literal at module level, which is the same
property the sibling drift test
(:mod:`tests.unit.mcp.test_tool_profile_drift`) verifies via AST.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILES_PY = _REPO_ROOT / "session_buddy" / "mcp" / "tools" / "profiles.py"


def test_register_cross_repo_work_tools_in_standard_profile() -> None:
    from session_buddy.mcp.tools.profiles import STANDARD_REGISTRATIONS

    assert "register_cross_repo_work_tools" in STANDARD_REGISTRATIONS, (
        f"register_cross_repo_work_tools missing from STANDARD; "
        f"profile has {STANDARD_REGISTRATIONS}"
    )


def test_register_cross_repo_work_tools_in_registration_map() -> None:
    """Assert the registration key is present in ``REGISTRATION_MAP`` via AST.

    After the W0 (mcp-common>=0.18.0) refactor, ``REGISTRATION_MAP`` lives
    in ``session_buddy/mcp/tools/profiles.py`` and is the canonical
    dispatch map consumed by ``_apply_tool_profile``. The legacy
    ``_ALL_REGISTERS`` dict in ``server.py`` has been removed.
    """
    tree = ast.parse(_PROFILES_PY.read_text())
    keys: set[str] = set()
    for node in ast.walk(tree):
        value: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "REGISTRATION_MAP":
                value = node.value
        elif isinstance(node, ast.Assign) and node.targets:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "REGISTRATION_MAP":
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
