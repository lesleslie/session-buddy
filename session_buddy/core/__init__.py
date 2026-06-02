"""Core functionality for session-mgmt-mcp."""

from __future__ import annotations

from session_buddy.core.conversation_storage import (
    capture_conversation_context,
    get_conversation_stats,
    store_conversation_checkpoint,
)
from session_buddy.core.hooks import HooksManager

# IMPORTANT: Import session_manager FIRST because it has a circular
# dependency with conversation_storage. All other imports must come after.
from session_buddy.core.session_manager import SessionLifecycleManager

__all__ = [
    "HooksManager",
    "SessionLifecycleManager",
    "capture_conversation_context",
    "store_conversation_checkpoint",
    "get_conversation_stats",
]
