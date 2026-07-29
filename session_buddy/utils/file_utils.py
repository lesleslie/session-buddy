"""Re-exports from session_buddy.utils.filesystem for backward compatibility.

This module exists so that external callers (and tests) that reference
``session_buddy.utils.file_utils`` continue to resolve correctly.
"""

from session_buddy.utils.filesystem import (
    _cleanup_session_logs,
    _cleanup_temp_files,
    _cleanup_uv_cache,
)

__all__ = [
    "_cleanup_session_logs",
    "_cleanup_temp_files",
    "_cleanup_uv_cache",
]
