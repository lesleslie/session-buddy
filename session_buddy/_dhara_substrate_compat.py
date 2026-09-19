"""Substrate-compat gate — lazy resolver for the optional Dhara substrate.

Producer modules query the substrate via :func:`dhara_calltime`; the
helper lazy-loads the ``dhara`` module on first call and resolves
``dhara.<name>``, returning ``None`` when the package is missing or
the attribute is unbound. No module-load-time dependency on dhara.

Mirrors ``mahavishnu/core/_dhara_substrate_compat.py`` — same surface,
same lazy semantics. Phase 8 of the Dhara MCP retirement plan dropped
the old ``stamp_dhara_attr`` helper that monkey-patched the live
``dhara`` module at import time; no in-repo caller depended on that
side effect after the migration.

Usage in producer modules:

    from session_buddy._dhara_substrate_compat import dhara_calltime
    put = dhara_calltime("put")
    if put is not None:
        put(key, validated)
"""

from __future__ import annotations

from typing import Any


def _try_load_dhara() -> Any | None:
    """Resolve the optional ``dhara`` module at call time.

    Returns the ``dhara`` module if importable, else ``None``. The shim
    does not declare ``dhara`` as a hard dependency at module-load time
    — only this lazy resolver touches it.
    """
    try:
        import dhara  # ty: ignore[unresolved-import] - optional dep; lazy resolver
    except ImportError:
        return None
    return dhara


def dhara_calltime(name: str) -> Any:
    """Resolve ``dhara.<name>`` at call time. Returns ``None`` when unbound.

    Use this in producer modules instead of importing ``dhara`` directly.
    Returns ``None`` when the ``dhara`` package is not importable (no
    ImportError leaks to the caller) AND when the attribute is absent.
    """
    dhara = _try_load_dhara()
    if dhara is None:
        return None
    return getattr(dhara, name, None)
