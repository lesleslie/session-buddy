from __future__ import annotations

import inspect
import typing as t
from contextlib import suppress
from dataclasses import dataclass

if t.TYPE_CHECKING:
    from session_buddy.di.config import SessionPaths

ServiceHook = t.Callable[[], t.Awaitable[t.Any] | t.Any]


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    name: str
    category: str
    init: ServiceHook | None = None
    health: ServiceHook | None = None
    cleanup: ServiceHook | None = None


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: list[ServiceSpec] = []

    def register(self, service: ServiceSpec) -> None:
        self._services.append(service)

    async def init_all(self) -> None:
        for service in self._services:
            await _maybe_call(service.init)

    async def health_all(self) -> dict[str, t.Any]:
        results: dict[str, t.Any] = {}
        for service in self._services:
            results[service.name] = await _maybe_call(service.health)
        return results

    async def cleanup_all(self) -> None:
        for service in self._services:
            await _maybe_call(service.cleanup)


_registry: ServiceRegistry | None = None


def get_service_registry() -> ServiceRegistry:
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
        _register_defaults(_registry)
    return _registry


def _register_defaults(registry: ServiceRegistry) -> None:
    registry.register(
        ServiceSpec(
            name="core.di_config",
            category="core",
            init=_init_di_config,
            health=_health_di_config,
            cleanup=_noop,
        )
    )
    registry.register(
        ServiceSpec(
            name="core.permissions_manager",
            category="core",
            init=_init_permissions_manager,
            health=_health_permissions_manager,
            cleanup=_noop,
        )
    )
    registry.register(
        ServiceSpec(
            name="core.lifecycle_manager",
            category="core",
            init=_init_lifecycle_manager,
            health=_health_lifecycle_manager,
            cleanup=_noop,
        )
    )
    registry.register(
        ServiceSpec(
            name="memory.reflection_db",
            category="memory",
            init=_init_reflection_db,
            health=_health_reflection_db,
            cleanup=_cleanup_reflection_db,
        )
    )
    registry.register(
        ServiceSpec(
            name="memory.knowledge_graph",
            category="memory",
            init=_init_knowledge_graph,
            health=_health_knowledge_graph,
            cleanup=_cleanup_knowledge_graph,
        )
    )
    registry.register(
        ServiceSpec(
            name="adapters.storage",
            category="adapters",
            init=_init_storage_adapters,
            health=_health_storage_adapters,
            cleanup=_cleanup_storage_adapters,
        )
    )
    registry.register(
        ServiceSpec(
            name="adapters.caches",
            category="adapters",
            init=_init_cache_adapters,
            health=_health_cache_adapters,
            cleanup=_cleanup_cache_adapters,
        )
    )
    registry.register(
        ServiceSpec(
            name="tools.registry",
            category="tools",
            init=_noop,
            health=_health_tools_registry,
            cleanup=_noop,
        )
    )
    registry.register(
        ServiceSpec(
            name="utils.logging",
            category="utils",
            init=_init_logging,
            health=_health_logging,
            cleanup=_noop,
        )
    )


async def _maybe_call(hook: ServiceHook | None) -> t.Any:
    if hook is None:
        return None
    result = hook()
    if inspect.isawaitable(result):
        return await result
    return result


def _init_di_config() -> None:
    from session_buddy.di import configure

    configure()


def _health_di_config() -> bool:
    from session_buddy.di.config import SessionPaths
    from session_buddy.di.container import depends

    with suppress(Exception):
        return isinstance(depends.get_sync(SessionPaths), SessionPaths)
    return False


def _init_permissions_manager() -> None:
    from session_buddy.core.permissions import SessionPermissionsManager
    from session_buddy.di.container import depends

    with suppress(Exception):
        if isinstance(
            depends.get_sync(SessionPermissionsManager), SessionPermissionsManager
        ):
            return

    paths = _ensure_session_paths()
    manager = SessionPermissionsManager(paths.claude_dir)
    depends.set(SessionPermissionsManager, manager)


def _health_permissions_manager() -> bool:
    from session_buddy.core.permissions import SessionPermissionsManager
    from session_buddy.di.container import depends

    with suppress(Exception):
        return isinstance(
            depends.get_sync(SessionPermissionsManager), SessionPermissionsManager
        )
    return False


def _init_lifecycle_manager() -> None:
    from session_buddy.core.session_manager import SessionLifecycleManager
    from session_buddy.di.container import depends

    with suppress(Exception):
        if isinstance(
            depends.get_sync(SessionLifecycleManager), SessionLifecycleManager
        ):
            return

    depends.set(SessionLifecycleManager, SessionLifecycleManager())


def _health_lifecycle_manager() -> bool:
    from session_buddy.core.session_manager import SessionLifecycleManager
    from session_buddy.di.container import depends

    with suppress(Exception):
        return isinstance(
            depends.get_sync(SessionLifecycleManager), SessionLifecycleManager
        )
    return False


async def _init_reflection_db() -> None:
    from session_buddy.adapters.lifecycle import init_reflection_adapter

    with suppress(Exception):
        await init_reflection_adapter()


def _health_reflection_db() -> bool:
    from session_buddy.adapters.lifecycle import health_reflection_adapter

    return health_reflection_adapter()


async def _cleanup_reflection_db() -> None:
    from session_buddy.adapters.lifecycle import cleanup_reflection_adapter

    with suppress(Exception):
        await cleanup_reflection_adapter()


async def _init_knowledge_graph() -> None:
    from session_buddy.adapters.lifecycle import init_knowledge_graph_adapter

    with suppress(Exception):
        await init_knowledge_graph_adapter()


def _health_knowledge_graph() -> bool:
    from session_buddy.adapters.lifecycle import health_knowledge_graph_adapter

    return health_knowledge_graph_adapter()


def _cleanup_knowledge_graph() -> None:
    from session_buddy.adapters.lifecycle import cleanup_knowledge_graph_adapter

    with suppress(Exception):
        cleanup_knowledge_graph_adapter()


def _init_storage_adapters() -> None:
    from session_buddy.adapters.lifecycle import init_storage_adapters

    with suppress(Exception):
        init_storage_adapters()


def _health_storage_adapters() -> bool:
    from session_buddy.adapters.lifecycle import health_storage_adapters

    return health_storage_adapters()


async def _cleanup_storage_adapters() -> None:
    from session_buddy.adapters.lifecycle import cleanup_storage_adapters

    with suppress(Exception):
        await cleanup_storage_adapters()


def _init_cache_adapters() -> None:
    from session_buddy.adapters.lifecycle import init_cache_adapters

    with suppress(Exception):
        init_cache_adapters()


def _health_cache_adapters() -> bool:
    from session_buddy.adapters.lifecycle import health_cache_adapters

    return health_cache_adapters()


async def _cleanup_cache_adapters() -> None:
    from session_buddy.adapters.lifecycle import cleanup_cache_adapters

    with suppress(Exception):
        await cleanup_cache_adapters()


def _health_tools_registry() -> bool:
    with suppress(Exception):
        return True
    return False


def _init_logging() -> None:
    from session_buddy.utils.logging import get_session_logger

    get_session_logger()


def _health_logging() -> bool:
    from session_buddy.di.container import depends
    from session_buddy.utils.logging import SessionLogger

    with suppress(Exception):
        return isinstance(depends.get_sync(SessionLogger), SessionLogger)
    return False


def _ensure_session_paths() -> SessionPaths:
    from session_buddy.di import get_sync_typed
    from session_buddy.di.config import SessionPaths
    from session_buddy.di.container import depends

    with suppress(Exception):
        paths = get_sync_typed(SessionPaths)  # type: ignore[no-any-return]
        if isinstance(paths, SessionPaths):
            return paths

    paths = SessionPaths.from_home()
    paths.ensure_directories()
    depends.set(SessionPaths, paths)
    return paths


def _noop() -> None:
    return None


__all__ = ["ServiceRegistry", "ServiceSpec", "get_service_registry"]
