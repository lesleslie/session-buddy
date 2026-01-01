"""Compatibility shim for the Oneiric reflection adapter.

This module preserves the historical import path while routing to the
Oneiric-native implementation.
"""

from __future__ import annotations

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric as ReflectionDatabaseAdapter,
)

__all__ = ["ReflectionDatabaseAdapter"]
