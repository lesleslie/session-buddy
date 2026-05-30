"""Session Management MCP Server.

Provides comprehensive session management, conversation memory,
and quality monitoring for Claude Code projects.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.7.4"

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
