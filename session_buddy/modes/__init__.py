"""Session-Buddy operational modes.

This module provides different operational modes for Session-Buddy:
- Lite: In-memory, zero-dependency mode for testing and CI/CD
- Standard: Full-featured mode with persistent storage

Example:
    >>> from session_buddy.modes import get_mode
    >>>
    >>> # Get mode from environment or config
    >>> mode = get_mode()
    >>> print(f"Running in {mode.name} mode")
"""

from session_buddy.modes.base import OperationMode, get_mode
from session_buddy.modes.lite import LiteMode
from session_buddy.modes.standard import StandardMode

__all__ = [
    "OperationMode",
    "LiteMode",
    "StandardMode",
    "get_mode",
]
