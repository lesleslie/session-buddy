"""Verify session_buddy/mcp/server.py calls _apply_tool_profile() + golden fixtures match.

The W0 helper from mcp-common>=0.18.0 is the canonical way to apply a
ToolProfile at startup. These tests guard:

1. AST guard: ``session_buddy/mcp/server.py`` actually calls
   ``_apply_tool_profile`` (or its sync alias ``apply_tool_profile``) so the
   profile machinery can't be removed without breaking the build.
2. Golden fixture comparison at MINIMAL/STANDARD/FULL so a future refactor
   that accidentally drops or duplicates tools is caught.
3. ``SESSION_BUDDY_MANDATORY_GROUPS`` is a subset of
   ``REGISTRATION_MAP.keys()`` (the W0 helper requires each mandatory key
   to resolve to a callable).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _server_path() -> Path:
    return Path("session_buddy/mcp/server.py")


def _read_server_source() -> str:
    return _server_path().read_text()


def _tree() -> ast.AST:
    return ast.parse(_read_server_source())


def test_server_calls_apply_tool_profile() -> None:
    """AST guard: server.py must call _apply_tool_profile or apply_tool_profile.

    The W1.1 mahavishnu review flagged aliasing ``_apply_tool_profile``
    as ``apply_tool_profile`` because the sync wrapper raises in async
    context; the AST check accepts either symbol so the test still passes
    if a future maintainer renames the helper.
    """
    tree = _tree()
    found = any(
        isinstance(node, ast.Call)
        and getattr(node.func, "id", "") in {"_apply_tool_profile", "apply_tool_profile"}
        for node in ast.walk(tree)
    )
    assert found, (
        "session_buddy/mcp/server.py must call _apply_tool_profile() or "
        "apply_tool_profile() to wire the W0 profile dispatch helper"
    )


def _list_tools_in_subprocess(profile: str) -> list[str]:
    """List tools at the given profile via a fresh subprocess.

    session-buddy performs module-load side effects (Prometheus counter
    registration, AutoCheckpointLoop lifespan wiring) that cannot be
    safely re-run in the same Python interpreter, so each profile check
    uses an isolated subprocess.
    """
    script = (
        "import asyncio, json, os, sys\n"
        "os.environ['SESSION_BUDDY_TOOL_PROFILE'] = %r\n"
        "from session_buddy.mcp.server import mcp\n"
        "names = sorted(t.name for t in asyncio.run(mcp.list_tools()))\n"
        "print(json.dumps(names))\n"
    ) % profile
    env = os.environ.copy()
    # Pass the current env (already inherits SESSION_BUDDY_TOOL_PROFILE
    # when invoked via the per-profile shell loop below). Also pin the
    # project root so subprocess finds the venv.
    project_root = str(Path.cwd().resolve())
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={**env, "PWD": project_root},
        cwd=project_root,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("profile", ["minimal", "standard", "full"])
def test_profile_matches_golden_fixture(profile: str) -> None:
    """Tools at each profile must match the pre-refactor golden fixture."""
    actual = _list_tools_in_subprocess(profile)
    fixture = Path(f"tests/fixtures/{profile}/tool_names.json")
    expected = json.loads(fixture.read_text())
    assert actual == expected, (
        f"{profile} profile tool set differs from golden fixture "
        f"(missing={set(expected) - set(actual)}, extra={set(actual) - set(expected)})"
    )


def test_mandatory_groups_subset_of_registration_map() -> None:
    """SESSION_BUDDY_MANDATORY_GROUPS must be a subset of REGISTRATION_MAP keys.

    The W0 helper iterates ``mandatory_groups`` and looks up each key in
    ``registration_map``; any key not present raises ``ValueError`` at
    startup.
    """
    from session_buddy.mcp.tools.profiles import (
        REGISTRATION_MAP,
        SESSION_BUDDY_MANDATORY_GROUPS,
    )

    missing = SESSION_BUDDY_MANDATORY_GROUPS - set(REGISTRATION_MAP.keys())
    assert not missing, (
        f"MANDATORY groups {missing} not in REGISTRATION_MAP; "
        f"add them or pass mandatory_groups=set() to disable"
    )


def test_registration_map_keys_are_callables() -> None:
    """Every REGISTRATION_MAP value must be callable (the W0 helper calls them)."""
    from session_buddy.mcp.tools.profiles import REGISTRATION_MAP

    for name, fn in REGISTRATION_MAP.items():
        assert callable(fn), f"REGISTRATION_MAP[{name!r}] is not callable: {fn!r}"


def test_profile_registrations_full_uses_all_tools() -> None:
    """PROFILE_REGISTRATIONS[FULL] should be ALL_TOOLS so register_all_fn drives FULL."""
    from mcp_common.tools.dispatch import ALL_TOOLS

    from session_buddy.mcp.tools.profiles import PROFILE_REGISTRATIONS, ToolProfile

    assert PROFILE_REGISTRATIONS[ToolProfile.FULL] is ALL_TOOLS, (
        "FULL profile must use the ALL_TOOLS sentinel so the W0 helper "
        "calls register_all_fn once"
    )


def test_minimal_profile_excludes_mandatory_groups() -> None:
    """MINIMAL_REGISTRATIONS must not list any mandatory group to avoid double-register."""
    from session_buddy.mcp.tools.profiles import (
        MINIMAL_REGISTRATIONS,
        SESSION_BUDDY_MANDATORY_GROUPS,
    )

    overlap = set(MINIMAL_REGISTRATIONS) & SESSION_BUDDY_MANDATORY_GROUPS
    assert not overlap, (
        f"MINIMAL_REGISTRATIONS overlaps with mandatory groups: {overlap}. "
        f"The W0 helper re-registers mandatory groups; listing them here "
        f"causes duplicate FastMCP tool warnings."
    )


def test_standard_profile_excludes_mandatory_groups() -> None:
    """STANDARD_REGISTRATIONS must not list any mandatory group."""
    from session_buddy.mcp.tools.profiles import (
        SESSION_BUDDY_MANDATORY_GROUPS,
        STANDARD_REGISTRATIONS,
    )

    overlap = set(STANDARD_REGISTRATIONS) & SESSION_BUDDY_MANDATORY_GROUPS
    assert not overlap, (
        f"STANDARD_REGISTRATIONS overlaps with mandatory groups: {overlap}."
    )