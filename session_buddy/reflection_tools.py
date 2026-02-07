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

# Import the new modular implementation
from session_buddy.reflection.database import (
    ReflectionDatabase as _ReflectionDatabase,
)
from session_buddy.reflection.database import get_reflection_database

# Create alias for backward compatibility
ReflectionDatabase = _ReflectionDatabase

# Export for backward compatibility
__all__ = [
    "ReflectionDatabase",
    "get_reflection_database",
]
