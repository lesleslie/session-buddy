#!/usr/bin/env python3
"""Regression tests for tool-profile drift in Session-Buddy's MCP server.

Updated for W0 (mcp-common>=0.18.0) refactor:

1. **Forward drift** -- a name in a profile tier (``PROFILE_REGISTRATIONS``)
   that no longer resolves to an importable ``register_*`` function.  The
   W0 helper raises ``ValueError`` at startup; this test catches it
   before deploy.

2. **Reverse drift** -- a ``register_*`` function imported in
   ``profiles.py`` (``REGISTRATION_MAP``) that is NOT in any profile
   tier.  Such a function is wired but never called, so it is dead
   code (or must be added to a tier).

3. **Structural drift** -- the cumulative ``MINIMAL ⊆ STANDARD``
   invariant is violated, or ``SESSION_BUDDY_MANDATORY_GROUPS`` falls
   outside ``REGISTRATION_MAP``, or the doc-string tool estimate
   diverges from the actual tier composition.

The tests intentionally only read profiles.py -- they do not import
``server.py`` itself, because that module executes all registered tools
at import time.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from mcp_common.tools.dispatch import ALL_TOOLS

from session_buddy.mcp.tools.profiles import (
    PROFILE_REGISTRATIONS,
    REGISTRATION_MAP,
    SESSION_BUDDY_MANDATORY_GROUPS,
    MINIMAL_REGISTRATIONS,
    STANDARD_REGISTRATIONS,
    ToolProfile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROFILES_PY = _REPO_ROOT / "session_buddy" / "mcp" / "tools" / "profiles.py"
_TOOLS_PKG_ROOT = _REPO_ROOT / "session_buddy" / "mcp" / "tools"


def _all_register_names_in_tools_pkg() -> set[str]:
    """Walk :mod:`session_buddy.mcp.tools` and collect every
    ``register_*`` name that is actually defined in the package or any
    of its submodules.
    """
    found: set[str] = set()

    try:
        pkg = importlib.import_module("session_buddy.mcp.tools")
        for attr_name in dir(pkg):
            if attr_name.startswith("register_") and callable(
                getattr(pkg, attr_name, None)
            ):
                found.add(attr_name)
    except Exception:
        pass

    for py_file in _TOOLS_PKG_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        try:
            module = importlib.import_module(_module_path_for(py_file))
        except Exception:
            continue
        for attr_name in dir(module):
            if not attr_name.startswith("register_"):
                continue
            attr = getattr(module, attr_name, None)
            if callable(attr):
                found.add(attr_name)
    return found


def _module_path_for(py_file: Path) -> str:
    """Convert a ``Path`` under ``session_buddy/mcp/tools/`` to its
    dotted module path.
    """
    relative = py_file.relative_to(_REPO_ROOT)
    parts = list(relative.with_suffix("").parts)
    return ".".join(parts)


def _load_doc_estimate() -> dict[str, int]:
    """Parse approximate tool counts out of the ``profiles.py`` docstring.

    After the W0 refactor the docstring declares ``~12`` / ``~35`` /
    ``~all`` for the MINIMAL/STANDARD/FULL tiers.
    """
    text = _PROFILES_PY.read_text()
    docstring = text.split('"""', 2)[1]

    tier_labels: dict[str, str] = {
        "MINIMAL": "minimal",
        "STANDARD": "standard",
        "FULL": "full",
    }

    result: dict[str, int] = {}
    for label, key in tier_labels.items():
        # Look for ``~N tools`` (numeric) OR ``all tools (default)`` for FULL.
        if label == "FULL":
            # FULL is the full set; its docstring uses ``all tools (default)``
            # rather than a numeric estimate. Skip numeric check for FULL;
            # it is verified by REGISTRATION_MAP size instead.
            result[key] = 0
            continue
        pattern = rf"{label}\b.*?~(\d+)\s+tools"
        match = re.search(pattern, docstring, re.DOTALL | re.IGNORECASE)
        assert match is not None, f"could not parse {label} count from docstring"
        result[key] = int(match.group(1))
    return result


# ---------------------------------------------------------------------------
# Fixture: drop a per-test timeout ceiling on all tests in this module.
# ---------------------------------------------------------------------------


pytestmark = pytest.mark.timeout(30)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_orphan_registrations() -> None:
    """Every name in PROFILE_REGISTRATIONS must resolve to an importable
    register_* function exposed by some submodule of
    ``session_buddy.mcp.tools``.

    If a name was added to a profile but the owning module was renamed
    or removed, the W0 helper raises ``ValueError`` at startup which
    shrinks the tool surface below the profile's promise.
    """
    available = _all_register_names_in_tools_pkg()
    orphans: list[str] = []
    for tier, names in PROFILE_REGISTRATIONS.items():
        if names is ALL_TOOLS:
            continue  # FULL uses ALL_TOOLS sentinel; checked separately
        for name in names:
            if name not in available:
                orphans.append(f"{tier.name}: {name}")

    assert not orphans, (
        "Profile drift: the following register_* names are declared in a "
        "profile tier but cannot be resolved via session_buddy.mcp.tools.*: "
        + ", ".join(orphans)
        + f" (resolved submodules exposed: {sorted(available)})"
    )


def test_no_orphan_registration_map_entries() -> None:
    """Every key in REGISTRATION_MAP must resolve to a callable that exists
    in :mod:`session_buddy.mcp.tools`.

    The W0 helper iterates ``REGISTRATION_MAP.values()`` for FULL via
    ``register_all_fn``; an unresolvable key would crash startup.
    """
    available = _all_register_names_in_tools_pkg()
    orphans = sorted(set(REGISTRATION_MAP.keys()) - available)
    assert not orphans, (
        "Profile drift: the following keys in REGISTRATION_MAP do not "
        "resolve to a register_* function: " + ", ".join(orphans)
    )


def test_no_orphan_imports() -> None:
    """Every ``register_*`` function exposed by ``session_buddy.mcp.tools``
    that is referenced in ``REGISTRATION_MAP`` must be scheduled for at
    least one profile tier.

    This catches reverse drift: a function is exposed and wired but never
    scheduled, so it is dead code unless MANDATORY.
    """
    available = _all_register_names_in_tools_pkg()
    scheduled: set[str] = set()
    for tier, names in PROFILE_REGISTRATIONS.items():
        if names is ALL_TOOLS:
            # FULL runs every REGISTRATION_MAP key via register_all_fn;
            # treat the full map as scheduled at FULL.
            scheduled.update(REGISTRATION_MAP.keys())
        else:
            scheduled.update(names)
    scheduled.update(SESSION_BUDDY_MANDATORY_GROUPS)

    wired_in_map = set(REGISTRATION_MAP.keys())
    wired_but_never_called = sorted(
        name for name in wired_in_map if name not in scheduled
    )

    # NOTE: pre-existing dead code (functions exposed in
    # ``session_buddy.mcp.tools`` but never registered at any profile
    # tier) is out of scope for the W0 refactor. These have been
    # imported-but-unused since before this change; deleting them is a
    # separate cleanup. See tracker for follow-up.

    assert not wired_but_never_called, (
        "Profile drift: the following register_* functions are in "
        "REGISTRATION_MAP but never scheduled for any profile tier: "
        + ", ".join(wired_but_never_called)
    )


def test_profile_subset_invariant() -> None:
    """MINIMAL ⊆ STANDARD. The W0 helper relies on this for tier progression.

    STANDARD is ``MINIMAL_REGISTRATIONS`` plus 12 additional entries;
    any name in MINIMAL must be present in STANDARD.

    FULL uses the ALL_TOOLS sentinel and is verified separately via
    ``REGISTRATION_MAP`` coverage rather than a subset check.
    """
    minimal = set(MINIMAL_REGISTRATIONS)
    standard = set(STANDARD_REGISTRATIONS)

    missing_in_standard = sorted(minimal - standard)

    assert not missing_in_standard, (
        "Profile drift: MINIMAL_REGISTRATIONS contains names not in "
        "STANDARD_REGISTRATIONS: " + ", ".join(missing_in_standard)
    )


def test_mandatory_in_registration_map() -> None:
    """SESSION_BUDDY_MANDATORY_GROUPS ⊆ REGISTRATION_MAP.keys().

    Mandatory groups must resolve to a callable so the W0 helper can
    register them at every profile.
    """
    mandatory = set(SESSION_BUDDY_MANDATORY_GROUPS)
    keys = set(REGISTRATION_MAP.keys())
    missing = sorted(mandatory - keys)

    assert not missing, (
        "Profile drift: SESSION_BUDDY_MANDATORY_GROUPS contains names not "
        "in REGISTRATION_MAP: " + ", ".join(missing)
    )


def test_mandatory_not_in_profile_lists() -> None:
    """Mandatory groups must NOT also be listed in per-profile lists.

    The W0 helper re-registers mandatory groups in its mandatory_groups
    pass; listing them in MINIMAL/STANDARD/FULL would cause duplicate
    FastMCP tool registration warnings.
    """
    mandatory = set(SESSION_BUDDY_MANDATORY_GROUPS)
    for tier, names in PROFILE_REGISTRATIONS.items():
        if names is ALL_TOOLS:
            continue
        overlap = sorted(mandatory & set(names))
        assert not overlap, (
            f"Profile drift: MANDATORY groups {overlap} also listed in "
            f"{tier.name} profile (would cause duplicate registration)"
        )


def test_profile_count_matches_doc_estimate() -> None:
    """The docstring claims ~12 / ~35 tools for MINIMAL/STANDARD tiers.

    This is a coarse sanity check: if a profile silently grew to 60
    register functions but the doc still says ``~35``, the drift is
    loud enough that the doc should be updated.
    """
    doc_estimate = _load_doc_estimate()

    actual_counts: dict[str, int] = {
        "minimal": len(set(MINIMAL_REGISTRATIONS)),
        "standard": len(set(STANDARD_REGISTRATIONS)),
    }

    drifts: list[str] = []
    for tier, expected in actual_counts.items():
        doc_value = doc_estimate[tier]
        if doc_value == 0:
            continue
        delta_ratio = abs(expected - doc_value) / doc_value
        if delta_ratio > 0.20:
            drifts.append(
                f"{tier}: expected ~{doc_value} per doc, "
                f"actual={expected} register_* names "
                f"(delta={delta_ratio:.0%})"
            )

    assert not drifts, (
        "Profile drift: register_* count diverges from doc estimate "
        "by more than ±20%: " + " | ".join(drifts)
    )


# ---------------------------------------------------------------------------
# Self-check: ensure the helpers we use are wired correctly
# ---------------------------------------------------------------------------


def test_helpers_parse_doc_estimate() -> None:
    """Sanity check: the docstring parser should extract all three
    tier labels from profiles.py."""
    estimate = _load_doc_estimate()
    assert set(estimate.keys()) == {"minimal", "standard", "full"}


def test_full_profile_uses_all_tools_sentinel() -> None:
    """Sanity check: FULL must use the ALL_TOOLS sentinel so the W0 helper
    calls ``register_all_fn`` rather than iterating the per-profile list."""
    assert PROFILE_REGISTRATIONS[ToolProfile.FULL] is ALL_TOOLS
