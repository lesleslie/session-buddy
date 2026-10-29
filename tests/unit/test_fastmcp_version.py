"""Regression test for the FastMCP consumer pin.

Asserts the installed ``fastmcp`` runtime version satisfies the pin
declared in ``pyproject.toml``.

This guard catches two failure modes:

1. The pin in ``pyproject.toml`` is reverted below the ecosystem
   baseline (drift).
2. The lockfile resolves to a distribution the pin excludes
   (uv mis-resolution).

If either happens, the ecosystem-wide baseline is broken without any
local code change, so this test fails loudly in CI.

The floor and the ceiling are READ from ``pyproject.toml`` rather than
hardcoded here. A hardcoded copy of the pin is a second source of
truth, and it drifts the moment the pin moves -- which is how this test
came to assert a ``<4`` ceiling for a project whose consumer baseline
had already been raised to the 4.x line. Only the baseline itself
(the "not below 4.0.0" check) stays hardcoded, because detecting a
reverted pin is the whole point of that one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import fastmcp
import pytest

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: The ecosystem-wide FastMCP baseline. The pin in ``pyproject.toml``
#: may be RAISED above this, but never lowered below it.
_BASELINE_FLOOR = (4, 0, 0)


def _parse_version(value: str) -> tuple[int, ...]:
    """Parse the leading numeric components of a PEP 440 version string.

    Tolerates a partial version -- a ``<5`` ceiling names no minor
    component -- and pads the missing ones with zero, so ``4.1`` and
    ``4.1.0`` compare equal.
    """
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if match is None:
        raise ValueError(f"Unparsable version: {value!r}")
    return tuple(int(part) if part is not None else 0 for part in match.groups())


def _declared_pin() -> str:
    """Return the ``fastmcp`` requirement string declared in pyproject.toml."""
    document = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    for dependency in document["project"]["dependencies"]:
        name = re.split(r"[<>=!~\[ ]", dependency, maxsplit=1)[0]
        if name == "fastmcp":
            return dependency
    msg = f"pyproject.toml declares no fastmcp dependency: {_PYPROJECT}"
    raise AssertionError(msg)


def _declared_bounds() -> tuple[tuple[int, ...] | None, tuple[int, ...] | None]:
    """Extract the ``>=`` floor and the ``<`` ceiling from the declared pin.

    Either bound is ``None`` when the pin does not express it.
    """
    _, _, specifier = _declared_pin().partition("fastmcp")
    floor: tuple[int, ...] | None = None
    ceiling: tuple[int, ...] | None = None
    for clause in specifier.split(","):
        clause = clause.strip()
        if clause.startswith(">="):
            floor = _parse_version(clause[2:])
        elif clause.startswith("<"):
            ceiling = _parse_version(clause[1:])
    return floor, ceiling


def test_the_declared_pin_is_not_reverted_below_the_baseline() -> None:
    """The pin in pyproject.toml must not be lowered below the baseline.

    This is the one bound that stays hardcoded on purpose: the whole
    point of the check is to notice a pin that was moved BACKWARDS.
    """
    floor, _ = _declared_bounds()
    if floor is None:
        pytest.skip("the declared fastmcp pin expresses no floor")
    assert floor >= _BASELINE_FLOOR, (
        f"the declared fastmcp pin {_declared_pin()!r} was lowered below the "
        f"ecosystem baseline {'.'.join(str(p) for p in _BASELINE_FLOOR)}"
    )


def test_fastmcp_version_meets_the_declared_floor() -> None:
    """Installed fastmcp must be at or above the declared floor."""
    floor, _ = _declared_bounds()
    if floor is None:
        pytest.skip("the declared fastmcp pin expresses no floor")
    installed = _parse_version(fastmcp.__version__)
    assert installed >= floor, (
        f"fastmcp.__version__={fastmcp.__version__!r} is below the declared "
        f"floor {'.'.join(str(p) for p in floor)}; refresh the lockfile"
    )


def test_fastmcp_version_below_the_declared_ceiling() -> None:
    """Installed fastmcp must be below the declared ceiling."""
    _, ceiling = _declared_bounds()
    if ceiling is None:
        pytest.skip("the declared fastmcp pin expresses no ceiling")
    installed = _parse_version(fastmcp.__version__)
    assert installed < ceiling, (
        f"fastmcp.__version__={fastmcp.__version__!r} crossed the declared "
        f"ceiling {'.'.join(str(p) for p in ceiling)}"
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
    # Each symbol must be the *same object* as the upstream fastmcp export.
    import fastmcp as _fastmcp
    from mcp_common.fastmcp import Context, FastMCP, Middleware

    assert FastMCP is _fastmcp.FastMCP
    assert Context is _fastmcp.Context
    assert Middleware is _fastmcp.server.middleware.Middleware
