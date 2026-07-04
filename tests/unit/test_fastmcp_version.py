"""Regression test for Plan 7 Phase 2: FastMCP 3.4 consumer bump.

Asserts the installed ``fastmcp`` runtime version satisfies the new floor
set in ``pyproject.toml`` (``fastmcp>=3.4.0,<4``).

This guard catches two failure modes:

1. The pin in ``pyproject.toml`` is reverted below 3.4.0 (drift).
2. The lockfile resolves to a sub-3.4 distribution (uv mis-resolution).

If either happens, the ecosystem-wide 3.4+ baseline (Plan 7) is broken
without any local code change, so this test fails loudly in CI.
"""

from __future__ import annotations

import re

import fastmcp
import pytest


def _parse_version(value: str) -> tuple[int, ...]:
    """Parse the leading ``X.Y.Z`` triplet from a PEP 440 version string."""
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        raise ValueError(f"Unparsable version: {value!r}")
    parts: tuple[int, ...] = (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)) if match.group(3) is not None else 0,
    )
    return parts


def test_fastmcp_version_meets_3_4_floor() -> None:
    """Installed fastmcp must be >= 3.4.0 (Plan 7 ecosystem baseline)."""
    installed = _parse_version(fastmcp.__version__)
    assert installed >= (3, 4, 0), (
        f"fastmcp.__version__={fastmcp.__version__!r} is below the Plan 7 "
        f"3.4.0 floor; bump the pin and refresh the lockfile"
    )


def test_fastmcp_version_below_4_ceiling() -> None:
    """Installed fastmcp must be < 4 (semver-major-bound per Plan 7)."""
    installed = _parse_version(fastmcp.__version__)
    assert installed < (4, 0, 0), (
        f"fastmcp.__version__={fastmcp.__version__!r} crossed the major "
        f"boundary; Plan 7 pins fastmcp>=3.4.0,<4"
    )


@pytest.mark.parametrize(
    ("symbol",),
    [
        ("FastMCP",),
        ("Context",),
    ],
)
def test_fastmcp_public_symbols_are_importable(symbol: str) -> None:
    """FastMCP public API surface required by session-buddy remains importable."""
    module = __import__("fastmcp", fromlist=[symbol])
    assert hasattr(module, symbol), f"fastmcp.{symbol} must remain importable"


def test_mcp_common_fastmcp_re_exports_canonical_symbols() -> None:
    """mcp_common.fastmcp re-export surface must expose the canonical symbols.

    Plan 7 Phase 1 (mcp-common foundation) ships
    ``from mcp_common.fastmcp import FastMCP, Context, Middleware, ...``.
    Consumer repos import from this path so version drift can be
    centralised in mcp-common.
    """
    from mcp_common.fastmcp import Context, FastMCP, Middleware

    # Each symbol must be the *same object* as the upstream fastmcp export.
    import fastmcp as _fastmcp

    assert FastMCP is _fastmcp.FastMCP
    assert Context is _fastmcp.Context
    assert Middleware is _fastmcp.server.middleware.Middleware
