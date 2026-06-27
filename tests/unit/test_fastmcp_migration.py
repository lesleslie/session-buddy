"""Regression test for Plan 7 Phase 2: import-path migration.

Asserts that session-buddy's production and test code imports FastMCP /
Context / Middleware from the centralised re-export surface
(``mcp_common.fastmcp``) and **not** directly from the upstream
``fastmcp`` package.

Why:

- Centralised re-exports give mcp-common a single place to absorb
  FastMCP version drift (Plan 7 Phase 1 contract).
- Direct ``from fastmcp import ...`` in consumer code defeats the
  purpose and is a code-review smell that this test fails loudly.

Scope: every ``.py`` file under ``session_buddy/`` and ``tests/`` is
scanned for the upstream import shape.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS: tuple[Path, ...] = (REPO_ROOT / "session_buddy", REPO_ROOT / "tests")

# The exact upstream import shapes the migration forbids. We block every
# ``from fastmcp import ...`` and ``from fastmcp.<submodule> import ...``
# in the production code and tests, including function-local lazy imports
# inside ``TYPE_CHECKING`` blocks. Docstring examples (lines starting with
# ``>>>``) are excluded because they are illustrative, not executable.
_UPSTREAM_IMPORT_PATTERN = re.compile(
    r"^[ \t]*from\s+fastmcp(?:\.\w+)*\s+import\s+",
    re.MULTILINE,
)
_DOCSTRING_EXAMPLE_PATTERN = re.compile(r"^\s*>>>")


def _iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def _scan_upstream_fastmcp_imports() -> dict[str, list[tuple[str, int]]]:
    """Return {filepath: [(line_text, lineno), ...]} for upstream imports."""
    hits: dict[str, list[tuple[str, int]]] = {}
    for path in _iter_python_files(SCAN_DIRS):
        # Skip this test file itself and any vendored or generated code.
        if path.name in {"test_fastmcp_migration.py", "test_fastmcp_version.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        matches: list[tuple[str, int]] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _DOCSTRING_EXAMPLE_PATTERN.match(line):
                continue
            if _UPSTREAM_IMPORT_PATTERN.match(line):
                matches.append((line.strip(), lineno))
        if matches:
            hits[str(path.relative_to(REPO_ROOT))] = matches
    return hits


def test_no_upstream_fastmcp_imports_in_session_buddy() -> None:
    """session_buddy/ must not import directly from upstream fastmcp."""
    hits = _scan_upstream_fastmcp_imports()
    production_hits = {
        path: lines for path, lines in hits.items() if path.startswith("session_buddy/")
    }
    assert not production_hits, (
        "Upstream `from fastmcp import ...` found in session_buddy/; "
        "migrate to `from mcp_common.fastmcp import ...`. "
        f"Hits: {production_hits}"
    )


def test_no_upstream_fastmcp_imports_in_tests() -> None:
    """tests/ must not import directly from upstream fastmcp either."""
    hits = _scan_upstream_fastmcp_imports()
    test_hits = {
        path: lines for path, lines in hits.items() if path.startswith("tests/")
    }
    assert not test_hits, (
        "Upstream `from fastmcp import ...` found in tests/; "
        "migrate to `from mcp_common.fastmcp import ...`. "
        f"Hits: {test_hits}"
    )


@pytest.mark.parametrize(
    "module_path",
    [
        "session_buddy.server_optimized",
        "session_buddy.mcp.tools.session.session_tools",
        "session_buddy.mcp.tools.infrastructure.pools",
        "session_buddy.mcp.tools.monitoring.monitoring_tools",
    ],
)
def test_module_imports_clean(module_path: str) -> None:
    """Spot-check: a representative set of modules must import without errors.

    These modules register MCP tools; if any of them still pulls in
    upstream ``fastmcp`` directly, the migration is incomplete and
    the central re-export contract is broken.
    """
    importlib = pytest.importorskip("importlib")
    importlib.import_module(module_path)


def test_mcp_common_fastmcp_reexports_match_upstream() -> None:
    """The centralised re-exports must reference the exact same objects."""
    import fastmcp
    import fastmcp.server.middleware

    from mcp_common.fastmcp import (  # noqa: PLC0415
        Context,
        FastMCP,
        Middleware,
        MiddlewareContext,
        RateLimitingMiddleware,
    )

    assert FastMCP is fastmcp.FastMCP
    assert Context is fastmcp.Context
    assert Middleware is fastmcp.server.middleware.Middleware
    assert MiddlewareContext is fastmcp.server.middleware.MiddlewareContext
    # RateLimitingMiddleware is re-exported but identity-equal upstream
    assert RateLimitingMiddleware is fastmcp.server.middleware.rate_limiting.RateLimitingMiddleware
