"""Core functionality for session-mgmt-mcp."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "HooksManager": ("session_buddy.core.hooks", "HooksManager"),
    "SessionLifecycleManager": (
        "session_buddy.core.session_manager",
        "SessionLifecycleManager",
    ),
    "capture_conversation_context": (
        "session_buddy.core.conversation_storage",
        "capture_conversation_context",
    ),
    "store_conversation_checkpoint": (
        "session_buddy.core.conversation_storage",
        "store_conversation_checkpoint",
    ),
    "get_conversation_stats": (
        "session_buddy.core.conversation_storage",
        "get_conversation_stats",
    ),
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


__all__ = list(_LAZY_EXPORTS)
