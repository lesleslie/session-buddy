"""Instance managers for MCP server singletons.

This module provides lazy initialization and access to global singleton instances
for application monitoring, LLM providers, and serverless session management.

Extracted from server.py Phase 2.6 to reduce cognitive complexity.
"""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_buddy.di import SessionPaths, get_sync_typed
from session_buddy.di.container import depends

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import (
        ReflectionDatabaseAdapter as ReflectionDatabase,
    )
    from session_buddy.app_monitor import ApplicationMonitor
    from session_buddy.interruption_manager import InterruptionManager
    from session_buddy.llm_providers import LLMManager
    from session_buddy.serverless_mode import ServerlessSessionManager


async def get_app_monitor() -> ApplicationMonitor | None:
    """Resolve application monitor via DI, creating it on demand.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    """
    try:
        from session_buddy.app_monitor import ApplicationMonitor
    except ImportError:
        return None

    with suppress(Exception):
        monitor = get_sync_typed(ApplicationMonitor)  # type: ignore[no-any-return]
        if isinstance(monitor, ApplicationMonitor):
            return monitor

    data_dir = _resolve_claude_dir() / "data" / "app_monitoring"
    working_dir = Path(os.environ.get("PWD", str(Path.cwd())))
    project_paths = [str(working_dir)] if working_dir.exists() else []

    monitor = ApplicationMonitor(str(data_dir), project_paths)
    depends.set(ApplicationMonitor, monitor)
    return monitor


async def get_llm_manager() -> LLMManager | None:
    """Resolve LLM manager via DI, creating it on demand.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    """
    try:
        from session_buddy.llm_providers import LLMManager
    except ImportError:
        return None

    with suppress(Exception):
        manager = get_sync_typed(LLMManager)  # type: ignore[no-any-return]
        if isinstance(manager, LLMManager):
            return manager

    config_path = _resolve_claude_dir() / "data" / "llm_config.json"
    manager = LLMManager(str(config_path) if config_path.exists() else None)
    depends.set(LLMManager, manager)
    return manager


async def get_serverless_manager() -> ServerlessSessionManager | None:
    """Resolve serverless session manager via DI, creating it on demand.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    """
    try:
        from session_buddy.serverless_mode import (
            ServerlessConfigManager,
            ServerlessSessionManager,
        )
    except ImportError:
        return None

    with suppress(Exception):
        manager = get_sync_typed(ServerlessSessionManager)  # type: ignore[no-any-return]
        if isinstance(manager, ServerlessSessionManager):
            return manager

    claude_dir = _resolve_claude_dir()
    config_path = claude_dir / "data" / "serverless_config.json"
    config = ServerlessConfigManager.load_config(
        str(config_path) if config_path.exists() else None,
    )
    storage_backend = ServerlessConfigManager.create_storage_backend(config)
    manager = ServerlessSessionManager(storage_backend)
    depends.set(ServerlessSessionManager, manager)
    return manager


async def get_reflection_database() -> ReflectionDatabase | None:
    """Resolve reflection database via DI, creating it on demand.

    Note:
        Returns ReflectionDatabaseAdapter which maintains API compatibility
        with the original ReflectionDatabase while using Oneiric DuckDB.

    """
    try:
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric as ReflectionDatabaseAdapter,
        )
    except ImportError:
        try:
            from session_buddy.adapters.reflection_adapter import (
                ReflectionDatabaseAdapter,
            )
        except ImportError:
            return None

    # Note: We use ReflectionDatabaseAdapter as the key for the new implementation
    with suppress(Exception):
        db = depends.get_sync(ReflectionDatabaseAdapter)
        if isinstance(db, ReflectionDatabaseAdapter):
            return db

    from session_buddy.adapters.lifecycle import init_reflection_adapter

    await init_reflection_adapter()
    with suppress(Exception):
        db = depends.get_sync(ReflectionDatabaseAdapter)
        if isinstance(db, ReflectionDatabaseAdapter):
            return db
    return None


async def get_interruption_manager() -> InterruptionManager | None:
    """Resolve interruption manager via DI, creating it on demand.

    Note:
        Uses the Oneiric-backed service container for singleton resolution.

    """
    try:
        from session_buddy.interruption_manager import InterruptionManager
    except ImportError:
        return None

    with suppress(Exception):
        manager = get_sync_typed(InterruptionManager)  # type: ignore[no-any-return]
        if isinstance(manager, InterruptionManager):
            return manager

    manager = InterruptionManager()
    depends.set(InterruptionManager, manager)
    return manager


def reset_instances() -> None:
    """Reset registered instances in the DI container."""
    depends.reset()


def _resolve_claude_dir() -> Path:
    """Resolve claude directory via type-safe DI.

    Returns:
        Path to .claude directory, using SessionPaths from DI container
        or falling back to default home directory.

    Note:
        Uses SessionPaths type for DI resolution instead of string keys.

    """
    with suppress(KeyError, AttributeError, RuntimeError, TypeError):
        # RuntimeError: when adapter requires async
        # TypeError: when DI has type confusion
        paths = depends.get_sync(SessionPaths)
        if isinstance(paths, SessionPaths):
            paths.claude_dir.mkdir(parents=True, exist_ok=True)
            return paths.claude_dir

    # Fallback: create default paths if not registered
    default_dir = Path(os.path.expanduser("~")) / ".claude"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


def _iter_dependencies() -> list[type[Any]]:
    deps: list[type[Any]] = []
    with suppress(ImportError):
        from session_buddy.app_monitor import ApplicationMonitor

        deps.append(ApplicationMonitor)
    with suppress(ImportError):
        from session_buddy.llm_providers import LLMManager

        deps.append(LLMManager)
    with suppress(ImportError):
        from session_buddy.interruption_manager import InterruptionManager

        deps.append(InterruptionManager)
    with suppress(ImportError):
        from session_buddy.serverless_mode import ServerlessSessionManager

        deps.append(ServerlessSessionManager)
    with suppress(ImportError):
        from session_buddy.adapters.reflection_adapter import (
            ReflectionDatabaseAdapter,
        )

        deps.append(ReflectionDatabaseAdapter)
    return deps
