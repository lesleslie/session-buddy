"""Substrate-compat helper for cross-portfolio producer modules.

Stamp `dhara.put` (and other substrate attrs) at import time when the
local dhara distribution does not expose them. Tests monkeypatch the
attribute; production builds that expose it see a real callable.

The companion `dhara_calltime(name)` resolves the attribute at call
time so producers can skip+warn cleanly when the substrate is
unbound (G6 contract).

Usage in producer modules:

    from session_buddy._dhara_substrate_compat import (
        stamp_dhara_attr, dhara_calltime,
    )
    stamp_dhara_attr("put")
    put = dhara_calltime("put")
    if put is not None:
        put(key, validated)
"""
from __future__ import annotations

from typing import Any, Final

import dhara

_PUT: Final[str] = "put"
_GET: Final[str] = "get"
_LIST: Final[str] = "list"


def stamp_dhara_attr(name: str) -> None:
    """Stamp `name` onto the live `dhara` module if absent.

    Idempotent: safe to call multiple times. Mirrors the inline
    `if not hasattr(dhara, name): dhara.name = None` pattern that each
    producer carries today.
    """
    if not hasattr(dhara, name):
        setattr(dhara, name, None)  # type: ignore[attr-defined]


def dhara_calltime(name: str) -> Any:
    """Resolve `dhara.<name>` at call time. Returns None when unbound."""
    return getattr(dhara, name, None)
