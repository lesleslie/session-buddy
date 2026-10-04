"""Session Management MCP Server.

Provides comprehensive session management, conversation memory,
and quality monitoring for Claude Code projects.

``__version__`` is derived from the installed distribution metadata via
``importlib.metadata.version()`` so :file:`pyproject.toml` is the single
source of truth for the version string. Editable installs without a
built ``.dist-info`` fall back to ``"0+unknown"`` (PEP 440 local-version
label) so the import never crashes.
"""

from __future__ import annotations

from importlib import import_module
from importlib import metadata as _metadata
from typing import Any

# PEP 440 local-version label; sentinel for "metadata not found" rather
# than a real release version.
_VERSION_FALLBACK = "0+unknown"


def _resolve_version() -> str:
    """Return the distribution version, falling back to a known sentinel.

    Wrapped in a function so tests can monkeypatch the lookup without
    having to reload the package.
    """
    try:
        return _metadata.version("session-buddy")
    except _metadata.PackageNotFoundError:
        return _VERSION_FALLBACK


__version__ = _resolve_version()

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AdvancedFeaturesHub": ("session_buddy.advanced_features", "AdvancedFeaturesHub"),
    "SessionPermissionsManager": (
        "session_buddy.core.permissions",
        "SessionPermissionsManager",
    ),
    "SessionLogger": ("session_buddy.utils.logging", "SessionLogger"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    # Advanced features
    "AdvancedFeaturesHub",
    # Core components are not directly exposed
    "SessionLogger",
    "SessionPermissionsManager",
    # Package metadata
    "__version__",
]
