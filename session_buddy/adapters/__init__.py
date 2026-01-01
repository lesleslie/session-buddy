"""Oneiric-only adapter implementations for session management.

This module provides Oneiric-only adapters that completely replace ACB adapters.
All adapters use native DuckDB implementations without any ACB dependencies.

Phase 5: Oneiric Adapter Conversion - Complete Oneiric-only implementation
"""

from __future__ import annotations

from .knowledge_graph_adapter_oneiric import (
    KnowledgeGraphDatabaseAdapterOneiric as KnowledgeGraphDatabaseAdapter,
)

# Import Oneiric-only adapters (no ACB fallbacks)
from .reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric as ReflectionDatabaseAdapter,
)

# Import the session storage adapter from its dedicated module
from .session_storage_adapter import (
    DEFAULT_SESSION_BUCKET,
    SessionStorageAdapter,
    get_default_storage_adapter,
)

# Use Oneiric-only storage implementation
from .storage_oneiric import (
    SUPPORTED_BACKENDS,
    configure_storage_buckets,
    get_default_session_buckets,
    get_storage_adapter,
    register_storage_adapter,
)

__all__ = [
    "DEFAULT_SESSION_BUCKET",
    "SUPPORTED_BACKENDS",
    # Knowledge graph adapter (Oneiric-only implementation)
    "KnowledgeGraphDatabaseAdapter",
    # Reflection adapter (Oneiric-only implementation)
    "ReflectionDatabaseAdapter",
    # Storage adapters (Oneiric-only implementations)
    "SessionStorageAdapter",
    "configure_storage_buckets",
    "get_default_session_buckets",
    "get_default_storage_adapter",
    "get_storage_adapter",
    "register_storage_adapter",
]
