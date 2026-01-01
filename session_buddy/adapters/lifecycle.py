from __future__ import annotations

import inspect
import typing as t
from contextlib import suppress

from session_buddy.adapters.settings import (
    CacheAdapterSettings,
    KnowledgeGraphAdapterSettings,
    ReflectionAdapterSettings,
    StorageAdapterSettings,
)
from session_buddy.di import get_sync_typed
from session_buddy.di.container import depends


def get_reflection_settings() -> ReflectionAdapterSettings:
    with suppress(Exception):
        settings = get_sync_typed(ReflectionAdapterSettings)  # type: ignore[no-any-return]
        if isinstance(settings, ReflectionAdapterSettings):
            return settings
    settings = ReflectionAdapterSettings.from_settings()
    depends.set(ReflectionAdapterSettings, settings)
    return settings


def get_knowledge_graph_settings() -> KnowledgeGraphAdapterSettings:
    with suppress(Exception):
        settings = get_sync_typed(KnowledgeGraphAdapterSettings)  # type: ignore[no-any-return]
        if isinstance(settings, KnowledgeGraphAdapterSettings):
            return settings
    settings = KnowledgeGraphAdapterSettings.from_settings()
    depends.set(KnowledgeGraphAdapterSettings, settings)
    return settings


def get_storage_settings() -> StorageAdapterSettings:
    with suppress(Exception):
        settings = get_sync_typed(StorageAdapterSettings)  # type: ignore[no-any-return]
        if isinstance(settings, StorageAdapterSettings):
            return settings
    settings = StorageAdapterSettings.from_settings()
    depends.set(StorageAdapterSettings, settings)
    return settings


def get_cache_settings() -> CacheAdapterSettings:
    with suppress(Exception):
        settings = get_sync_typed(CacheAdapterSettings)  # type: ignore[no-any-return]
        if isinstance(settings, CacheAdapterSettings):
            return settings
    settings = CacheAdapterSettings()
    depends.set(CacheAdapterSettings, settings)
    return settings


async def init_reflection_adapter() -> None:
    """Initialize reflection adapter using Oneiric implementation."""
    # Try to use Oneiric implementation first
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric as ReflectionDatabaseAdapter,
        )
    except ImportError:
        # Fallback to ACB implementation for compatibility
        from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

    with suppress(Exception):
        existing = depends.get_sync(ReflectionDatabaseAdapter)
        if isinstance(existing, ReflectionDatabaseAdapter):
            return

    settings = get_reflection_settings()
    adapter = ReflectionDatabaseAdapter(settings=settings)
    await adapter.initialize()
    depends.set(ReflectionDatabaseAdapter, adapter)


def health_reflection_adapter() -> bool:
    """Check health of reflection adapter (supports both Oneiric and ACB implementations)."""
    # Try Oneiric implementation first
    with suppress(ImportError):
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        with suppress(Exception):
            adapter = depends.get_sync(ReflectionDatabaseAdapterOneiric)
            return isinstance(adapter, ReflectionDatabaseAdapterOneiric)

    # Fallback to ACB implementation
    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

    with suppress(Exception):
        adapter = depends.get_sync(ReflectionDatabaseAdapter)
        return isinstance(adapter, ReflectionDatabaseAdapter)
    return False


async def cleanup_reflection_adapter() -> None:
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric as ReflectionDatabaseAdapter,
        )
    except ImportError:
        from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

    with suppress(Exception):
        adapter = depends.get_sync(ReflectionDatabaseAdapter)
        if hasattr(adapter, "close"):
            result = adapter.close()
            if inspect.isawaitable(result):
                await result


async def init_knowledge_graph_adapter() -> None:
    """Initialize knowledge graph adapter using Oneiric implementation."""
    # Try to use Oneiric implementation first
    try:
        from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
            KnowledgeGraphDatabaseAdapterOneiric as KnowledgeGraphDatabaseAdapter,
        )
    except ImportError:
        # Fallback to ACB implementation for compatibility
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

    with suppress(Exception):
        existing = depends.get_sync(KnowledgeGraphDatabaseAdapter)
        if isinstance(existing, KnowledgeGraphDatabaseAdapter):
            return

    settings = get_knowledge_graph_settings()
    adapter = KnowledgeGraphDatabaseAdapter(settings=settings)
    await adapter.initialize()
    depends.set(KnowledgeGraphDatabaseAdapter, adapter)


def health_knowledge_graph_adapter() -> bool:
    """Check health of knowledge graph adapter (supports both Oneiric and ACB implementations)."""
    # Try Oneiric implementation first
    with suppress(ImportError):
        from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
            KnowledgeGraphDatabaseAdapterOneiric,
        )

        with suppress(Exception):
            adapter = depends.get_sync(KnowledgeGraphDatabaseAdapterOneiric)
            return isinstance(adapter, KnowledgeGraphDatabaseAdapterOneiric)

    # Fallback to ACB implementation
    from session_buddy.adapters.knowledge_graph_adapter import (
        KnowledgeGraphDatabaseAdapter,
    )

    with suppress(Exception):
        adapter = depends.get_sync(KnowledgeGraphDatabaseAdapter)
        return isinstance(adapter, KnowledgeGraphDatabaseAdapter)
    return False


def cleanup_knowledge_graph_adapter() -> None:
    try:
        from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
            KnowledgeGraphDatabaseAdapterOneiric as KnowledgeGraphDatabaseAdapter,
        )
    except ImportError:
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

    with suppress(Exception):
        adapter = depends.get_sync(KnowledgeGraphDatabaseAdapter)
        if hasattr(adapter, "close"):
            adapter.close()


def init_storage_adapters() -> None:
    """Initialize storage adapters using Oneiric implementation."""
    # Try to use Oneiric implementation first
    with suppress(ImportError):
        from session_buddy.adapters.storage_oneiric import (
            configure_storage_buckets,
            init_storage_registry,
        )

        # Synchronous initialization
        init_storage_registry()
        settings = get_storage_settings()
        if settings.buckets:
            configure_storage_buckets(settings.buckets)
        return

    # Fallback to ACB implementation
    from session_buddy.adapters.storage_registry import (
        configure_storage_buckets,
        register_storage_adapter,
    )

    settings = get_storage_settings()
    if settings.buckets:
        configure_storage_buckets(settings.buckets)
    register_storage_adapter(settings.default_backend)


def health_storage_adapters() -> bool:
    """Check health of storage adapters (supports both Oneiric and ACB implementations)."""
    # Try Oneiric implementation first
    with suppress(ImportError):
        from session_buddy.adapters.storage_oneiric import get_storage_adapter

        settings = get_storage_settings()
        with suppress(Exception):
            adapter = get_storage_adapter(settings.default_backend)
            return adapter is not None

    # Fallback to ACB implementation
    from session_buddy.adapters.storage_registry import get_storage_adapter

    settings = get_storage_settings()
    with suppress(Exception):
        adapter = get_storage_adapter(settings.default_backend)
        return adapter is not None
    return False


async def _cleanup_adapter(adapter: t.Any) -> bool:
    """Helper to cleanup a single adapter."""
    for attr in ("aclose", "close", "cleanup"):
        handler = getattr(adapter, attr, None)
        if callable(handler):
            result = handler()
            if inspect.isawaitable(result):
                await result
            return True
    return False


async def cleanup_storage_adapters() -> None:
    # Try Oneiric implementation first
    with suppress(ImportError):
        from session_buddy.adapters.storage_oneiric import get_storage_adapter

        settings = get_storage_settings()
        with suppress(Exception):
            adapter = get_storage_adapter(settings.default_backend)
            if await _cleanup_adapter(adapter):
                return

    # Fallback to ACB implementation
    from session_buddy.adapters.storage_registry import get_storage_adapter

    settings = get_storage_settings()
    with suppress(Exception):
        adapter = get_storage_adapter(settings.default_backend)
        await _cleanup_adapter(adapter)


def init_cache_adapters() -> None:
    # Oneiric-only: Cache functionality handled by Oneiric adapters
    pass


def health_cache_adapters() -> bool:
    # Oneiric-only: Cache health now handled by Oneiric adapters
    return True  # Oneiric adapters are always healthy


async def cleanup_cache_adapters() -> None:
    # Oneiric-only: Cache cleanup handled by Oneiric adapters
    # No ACB cache cleanup needed
    pass
