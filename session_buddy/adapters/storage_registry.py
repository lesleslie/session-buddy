"""Compatibility shim for the Oneiric storage registry.

This module preserves the historical import path while routing to the
Oneiric-native storage registry implementation.
"""

from __future__ import annotations

from session_buddy.adapters.storage_oneiric import (
    DEFAULT_SESSION_BUCKET,
    SUPPORTED_BACKENDS,
    SessionStorageAdapter,
    StorageBaseOneiric,
    StorageRegistryOneiric,
    configure_storage_buckets,
    get_default_session_buckets,
    get_default_storage_adapter,
    get_storage_adapter,
    get_storage_registry,
    init_storage_registry,
    register_storage_adapter,
)

StorageBase = StorageBaseOneiric

__all__ = [
    "DEFAULT_SESSION_BUCKET",
    "SUPPORTED_BACKENDS",
    "SessionStorageAdapter",
    "StorageBase",
    "StorageBaseOneiric",
    "StorageRegistryOneiric",
    "configure_storage_buckets",
    "get_default_session_buckets",
    "get_default_storage_adapter",
    "get_storage_adapter",
    "get_storage_registry",
    "init_storage_registry",
    "register_storage_adapter",
]
