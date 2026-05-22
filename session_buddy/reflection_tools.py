#!/usr/bin/env python3
"""Reflection Tools for Claude Session Management.

DEPRECATION NOTICE (Phase 2 - February 2025):
    This module is now a thin compatibility wrapper. The actual implementation
    has been moved to session_buddy.reflection module for better modularity.

    Migration Guide:
        # Old (deprecated):
        from session_buddy.reflection_tools import ReflectionDatabase

        # New (recommended):
        from session_buddy.reflection import ReflectionDatabase

    The new module provides:
    - Better code organization (6 focused modules vs 1 monolithic file)
    - Cleaner separation of concerns
    - Improved testability
    - Same API (100% backward compatible)

    This wrapper will be removed in a future release.
"""

# Module-level singleton cache for the reflection database
_reflection_db = None

# Import the adapter class so tests and callers can patch it at the module level.
try:
    from session_buddy.adapters.reflection_adapter import (
        ReflectionDatabaseAdapter,
    )
except ImportError:
    ReflectionDatabaseAdapter = None  # type: ignore[assignment,misc]

# Import the new modular implementation
from pathlib import Path

from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.reflection.database import (
    ReflectionDatabase as _ReflectionDatabase,
)

# Create alias for backward compatibility
ReflectionDatabase = _ReflectionDatabase


async def get_reflection_database(db_path=None):
    """Get or create the reflection database singleton.

    This async wrapper uses the ReflectionDatabaseAdapter so that callers
    (and tests) can patch ``session_buddy.reflection_tools.ReflectionDatabaseAdapter``
    to control behaviour.
    """
    global _reflection_db

    if _reflection_db is not None:
        return _reflection_db

    # Instantiate via the adapter class so tests can mock it
    if ReflectionDatabaseAdapter is None:
        msg = "ReflectionDatabaseAdapter is not available"
        raise ImportError(msg)

    _reflection_db = ReflectionDatabaseAdapter() if db_path is None else ReflectionDatabaseAdapter(settings=ReflectionAdapterSettings(database_path=db_path if isinstance(db_path, (str, Path)) else Path(db_path)))
    return _reflection_db


# Export for backward compatibility
__all__ = [
    "ReflectionDatabase",
    "ReflectionDatabaseAdapter",
    "get_reflection_database",
]
