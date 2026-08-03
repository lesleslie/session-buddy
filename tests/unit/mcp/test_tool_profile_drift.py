#!/usr/bin/env python3
"""Regression tests for tool-profile drift in Session-Buddy's MCP server.

These tests catch three classes of drift between the declarations in
:mod:`session_buddy.mcp.tools.profiles` and the actual capabilities wired
in :mod:`session_buddy.mcp.server`:

1. **Forward drift** -- a name in a profile tier (``PROFILE_REGISTRATIONS``)
   that no longer resolves to an importable ``register_*`` function.  The
   server logs a warning and skips the name; users get a smaller tool
   surface than the profile promises.

2. **Reverse drift** -- a ``register_*`` function imported in ``server.py``
   that is never scheduled for any profile tier.  The function is imported
   but never called, so the tools it registers are dead code.

3. **Structural drift** -- the cumulative ``MINIMAL ⊆ STANDARD ⊆ FULL``
   invariant is violated, or ``MANDATORY_REGISTRATIONS`` falls outside
   the FULL tier, or the doc-string tool estimate diverges from the
   actual tier composition.

The tests intentionally only read profiles.py and the server.py AST --
they do not import ``server.py`` itself, because that module executes
all registered tools at import time.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from session_buddy.mcp.tools.profiles import (
    FULL_REGISTRATIONS,
    MANDATORY_REGISTRATIONS,
    MINIMAL_REGISTRATIONS,
    PROFILE_REGISTRATIONS,
    STANDARD_REGISTRATIONS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVER_PY = _REPO_ROOT / "session_buddy" / "mcp" / "server.py"
_PROFILES_PY = _REPO_ROOT / "session_buddy" / "mcp" / "tools" / "profiles.py"
_TOOLS_PKG_ROOT = _REPO_ROOT / "session_buddy" / "mcp" / "tools"


def _parse_server_imports() -> dict[str, str]:
    """Return ``{register_name: import_module_path}`` from server.py.

    Walks every ``from .tools ... import ...`` block in server.py and
    maps each ``register_*`` name to the resolved module path
    (``session_buddy.mcp.tools.*`` form).  Both the bulk
    ``from .tools import (register_X, ...)`` import and the named
    per-module imports are captured.
    """
    source = _SERVER_PY.read_text()
    tree = ast.parse(source)

    # Parent package for ``server.py`` is ``session_buddy.mcp`` -- the
    # leading ``.`` in a relative import resolves to it.
    parent_package = "session_buddy.mcp"

    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level is None or node.level < 1:
            continue
        # ``from .tools import X`` -> module="tools"; ``from .tools.x import
        # Y`` -> module="tools.x".  We only care about imports that
        # touch the tools package.
        module = node.module or ""
        if not (module == "tools" or module.startswith("tools.")):
            continue
        resolved = f"{parent_package}.{module}" if module else parent_package
        for alias in node.names:
            if alias.name.startswith("register_"):
                imports[alias.name] = resolved

    return imports


def _parse_all_registers_keys() -> set[str]:
    """Return the set of ``"register_*"`` keys registered in the
    ``_ALL_REGISTERS`` dict inside server.py.

    Handles both bare (``_ALL_REGISTERS = {...}``) and annotated
    (``_ALL_REGISTERS: dict[str, Any] = {...}``) assignments.
    """
    source = _SERVER_PY.read_text()
    tree = ast.parse(source)

    keys: set[str] = set()
    for node in ast.walk(tree):
        # Unwrap ``AnnAssign`` to its underlying ``Assign`` so the
        # rest of the logic works for both ``_ALL_REGISTERS = {...}``
        # and ``_ALL_REGISTERS: dict[str, Any] = {...}``.
        if isinstance(node, ast.AnnAssign):
            candidate: ast.AST | None = node.value
            target_id = (
                node.target.id if isinstance(node.target, ast.Name) else None
            )
        elif isinstance(node, ast.Assign):
            candidate = node.value
            target_id = None
            if node.targets and isinstance(node.targets[0], ast.Name):
                target_id = node.targets[0].id
        else:
            continue

        if target_id != "_ALL_REGISTERS" or not isinstance(candidate, ast.Dict):
            continue

        for key in candidate.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)

    return keys


def _all_register_names_in_tools_pkg() -> set[str]:
    """Walk :mod:`session_buddy.mcp.tools` and collect every
    ``register_*`` name that is actually defined in the package or any
    of its submodules.

    A name is in the set iff it resolves to a callable exposed by
    :mod:`session_buddy.mcp.tools` (the package re-exports) or some
    submodule under ``session_buddy.mcp.tools.*``.  This is more
    accurate than reading the package ``__init__.py`` re-exports
    alone, because tools registered from a submodule do not always
    need to be re-exported by ``__init__.py`` to be callable.

    We use ``pathlib`` to enumerate the source tree directly rather
    than ``pkgutil.walk_packages`` because some subpackages in this
    repo (notably ``monitoring``) are namespace packages without
    ``__init__.py`` and are skipped by ``walk_packages``.
    """
    found: set[str] = set()

    # The package ``__init__.py`` re-exports functions that live
    # outside the package (e.g. ``register_health_tools_sb`` from
    # ``mcp_common.health`` and ``register_code_graph_tools`` from
    # ``session_buddy.subscribers``).  Those names are still callable
    # via ``session_buddy.mcp.tools.register_*`` so they belong in
    # the resolved set.
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
            # Some submodules have optional dependencies that may not
            # be installed in the test environment.  Skip the
            # non-resolvable ones -- the goal is to confirm names
            # *can* be resolved, not to fail on every config edge.
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

    The docstring declares ``~12`` / ``~35`` / ``~171`` tools for the
    MINIMAL/STANDARD/FULL tiers.  The numbers are surrounded by
    ``~`` so we strip that prefix before parsing as int.
    """
    text = _PROFILES_PY.read_text()
    # Pull only the leading module docstring (until the first blank line
    # at the top of the file or the end of the docstring, whichever
    # comes first).  The structure is plain text so a regex is the
    # simplest approach.
    docstring = text.split('"""', 2)[1]

    tier_labels: dict[str, str] = {
        "MINIMAL": "minimal",
        "STANDARD": "standard",
        "FULL": "full",
    }

    result: dict[str, int] = {}
    # Each block looks like ``MINIMAL\n    Core session lifecycle plus
    # health.  ~12 tools.``.  We look for the label followed by a line
    # containing ``~N tools``.
    for label, key in tier_labels.items():
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
    or removed, the server silently skips the registration at import
    time which shrinks the tool surface below the profile's promise.
    """
    available = _all_register_names_in_tools_pkg()
    orphans: list[str] = []
    for tier, names in PROFILE_REGISTRATIONS.items():
        for name in names:
            if name not in available:
                orphans.append(f"{tier.name}: {name}")

    assert not orphans, (
        "Profile drift: the following register_* names are declared in a "
        "profile tier but cannot be resolved via session_buddy.mcp.tools.*: "
        + ", ".join(orphans)
        + f" (resolved submodules exposed: {sorted(available)})"
    )


def test_no_orphan_imports() -> None:
    """Every register_* function imported in server.py that is not in
    MANDATORY_REGISTRATIONS must be scheduled for at least one profile
    tier.

    This catches the reverse drift: a function is imported (and added
    to ``_ALL_REGISTERS``) but never wired up to any profile, so it is
    dead code unless MANDATORY.
    """
    server_imports = set(_parse_server_imports())
    all_registers_keys = _parse_all_registers_keys()
    imported = server_imports | all_registers_keys

    scheduled: set[str] = set()
    for names in PROFILE_REGISTRATIONS.values():
        scheduled.update(names)
    scheduled.update(MANDATORY_REGISTRATIONS)

    excluded_builtins = {"register_discovery_tools"}  # always-on meta-tool
    unregistered = sorted(
        name
        for name in imported
        if name not in scheduled and name not in excluded_builtins
    )

    assert not unregistered, (
        "Profile drift: the following register_* functions are imported in "
        "server.py but never scheduled for any profile tier: "
        + ", ".join(unregistered)
    )


def test_profile_subset_invariant() -> None:
    """MINIMAL ⊆ STANDARD ⊆ FULL -- the cumulative property.

    Each tier is a superset of every smaller tier.  If a new register
    function is added to MINIMAL without being added to STANDARD, the
    STANDARD profile loses those tools.
    """
    minimal = set(MINIMAL_REGISTRATIONS)
    standard = set(STANDARD_REGISTRATIONS)
    full = set(FULL_REGISTRATIONS)

    missing_in_standard = sorted(minimal - standard)
    missing_in_full = sorted(standard - full)

    assert not missing_in_standard, (
        "Profile drift: MINIMAL_REGISTRATIONS contains names not in "
        "STANDARD_REGISTRATIONS: " + ", ".join(missing_in_standard)
    )
    assert not missing_in_full, (
        "Profile drift: STANDARD_REGISTRATIONS contains names not in "
        "FULL_REGISTRATIONS: " + ", ".join(missing_in_full)
    )


def test_mandatory_in_full() -> None:
    """MANDATORY_REGISTRATIONS ⊆ FULL_REGISTRATIONS.

    Mandatory tools are guaranteed to be registered regardless of
    profile choice.  If FULL ever drops one, the server skips it on
    FULL startup but still imports it -- exposing a hidden contract
    breach.
    """
    mandatory = set(MANDATORY_REGISTRATIONS)
    full = set(FULL_REGISTRATIONS)
    missing = sorted(mandatory - full)

    assert not missing, (
        "Profile drift: MANDATORY_REGISTRATIONS contains names not in "
        "FULL_REGISTRATIONS: " + ", ".join(missing)
    )


def test_profile_count_matches_doc_estimate() -> None:
    """The docstring claims ~12 / ~35 / ~171 tools per tier.  The number
    of unique register_* names in each tier should match the doc
    estimate within ±20% tolerance.

    This is a coarse sanity check: if a profile silently grew to 60
    register functions but the doc still says ``~35``, the drift is
    loud enough that the doc should be updated.
    """
    doc_estimate = _load_doc_estimate()

    actual_counts: dict[str, int] = {
        "minimal": len(set(MINIMAL_REGISTRATIONS)),
        "standard": len(set(STANDARD_REGISTRATIONS)),
        "full": len(set(FULL_REGISTRATIONS)),
    }

    drifts: list[str] = []
    for tier, expected in doc_estimate.items():
        actual = actual_counts[tier]
        if expected == 0:
            continue
        delta_ratio = abs(actual - expected) / expected
        if delta_ratio > 0.20:
            drifts.append(
                f"{tier}: expected ~{expected} per doc, "
                f"actual={actual} register_* names "
                f"(delta={delta_ratio:.0%})"
            )

    assert not drifts, (
        "Profile drift: register_* count diverges from doc estimate "
        "by more than ±20%: " + " | ".join(drifts)
    )


# ---------------------------------------------------------------------------
# Self-check: ensure the helpers we use are wired correctly
# ---------------------------------------------------------------------------


def test_helpers_see_server_imports() -> None:
    """Sanity check: the AST helpers should pick up at least the
    well-known register names from server.py."""
    server_imports = _parse_server_imports()
    assert "register_health_tools_sb" in server_imports
    assert "register_pool_tools" in server_imports
    assert "register_prometheus_metrics_tools" in server_imports


def test_helpers_see_all_registers_keys() -> None:
    """Sanity check: the AST helper for ``_ALL_REGISTERS`` should pick
    up a representative cross-section of register names."""
    keys = _parse_all_registers_keys()
    assert "register_health_tools_sb" in keys
    assert "register_pool_tools" in keys
    assert len(keys) > 20, f"expected plenty of keys, got {len(keys)}"


def test_helpers_parse_doc_estimate() -> None:
    """Sanity check: the docstring parser should extract all three
    tier counts from profiles.py."""
    estimate = _load_doc_estimate()
    assert set(estimate.keys()) == {"minimal", "standard", "full"}
    assert all(value > 0 for value in estimate.values())
