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
from session_buddy.paths import config_dir, data_dir

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import (
        ReflectionDatabaseAdapter as ReflectionDatabase,
    )
    from session_buddy.app_monitor import ApplicationMonitor
    from session_buddy.interruption_manager import InterruptionManager
    from session_buddy.llm_providers import LLMManager
    from session_buddy.rewriting.query_rewriter import QueryRewriter
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
        monitor = get_sync_typed(ApplicationMonitor)
        if isinstance(monitor, ApplicationMonitor):
            return monitor

    data_root = _resolve_data_dir() / "app_monitoring"
    working_dir = Path(os.environ.get("PWD", str(Path.cwd())))
    project_paths = [str(working_dir)] if working_dir.exists() else []

    monitor = ApplicationMonitor(str(data_root), project_paths)
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
        manager = get_sync_typed(LLMManager)
        if isinstance(manager, LLMManager):
            return manager

    config_path = config_dir() / "llm_config.json"
    manager = LLMManager(str(config_path) if config_path.exists() else None)
    depends.set(LLMManager, manager)
    return manager


async def get_query_rewriter() -> QueryRewriter | None:
    """Resolve query rewriter via DI, creating it on demand.

    Bug 1 follow-up: ``QueryRewriter`` was previously not registered with
    DI, so ``depends.get_sync("QueryRewriter")`` (the bare-string lookup
    in ``rewriting_tools.py``) raised ``KeyError`` on first exercise.
    This helper registers the singleton under its class key.
    """
    try:
        from session_buddy.rewriting.query_rewriter import QueryRewriter
    except ImportError:
        return None

    with suppress(Exception):
        rewriter = get_sync_typed(QueryRewriter)
        if isinstance(rewriter, QueryRewriter):
            return rewriter

    rewriter = QueryRewriter()
    depends.set(QueryRewriter, rewriter)
    return rewriter


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
        manager = get_sync_typed(ServerlessSessionManager)
        if isinstance(manager, ServerlessSessionManager):
            return manager

    config_path = config_dir() / "serverless_config.json"
    config = ServerlessConfigManager.load_config(
        str(config_path) if config_path.exists() else None,
    )
    storage_backend = ServerlessConfigManager.create_storage_backend(config)
    manager = ServerlessSessionManager(storage_backend)
    depends.set(ServerlessSessionManager, manager)
    return manager


async def _ensure_initialized(db: ReflectionDatabase) -> ReflectionDatabase:
    """Return the adapter, connected if it is not connected yet.

    The DI container registers the reflection adapter WITHOUT opening its
    DuckDB connection -- the adapter connects lazily in
    ``await adapter.initialize()``, and its registration documents that
    "consumers must invoke await adapter.initialize() after fetching the
    singleton". So a registered adapter is not necessarily a READY one.

    Handing out an unconnected adapter makes every consumer that reads
    ``adapter.conn`` fail with "called before initialize()". The session
    handoff's cross-repo-work query hit exactly that, and reported "No
    cross-repo work captured" when there was cross-repo work to capture.

    ``initialize()`` is idempotent, so this costs a flag check once the
    adapter is connected.
    """
    if not getattr(db, "_initialized", False):
        # An adapter with no initializer (a test double, or a legacy
        # implementation) is as ready as it is ever going to be. Calling
        # it unconditionally would raise, and the surrounding
        # ``suppress(Exception)`` would swallow the failure and fall
        # through to a different code path entirely.
        initializer = getattr(db, "initialize", None)
        if initializer is not None:
            await initializer()
    return db


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
            return await _ensure_initialized(db)

    from session_buddy.adapters.lifecycle import init_reflection_adapter

    await init_reflection_adapter()
    with suppress(Exception):
        db = depends.get_sync(ReflectionDatabaseAdapter)
        if isinstance(db, ReflectionDatabaseAdapter):
            return await _ensure_initialized(db)
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
        manager = get_sync_typed(InterruptionManager)
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


def _resolve_data_dir() -> Path:
    """Resolve the Session-Buddy data directory via type-safe DI.

    Returns:
        Path to the XDG data directory, using SessionPaths from the DI
        container or falling back to the environment-resolved XDG root.

    """
    with suppress(KeyError, AttributeError, RuntimeError, TypeError):
        paths = depends.get_sync(SessionPaths)
        if isinstance(paths, SessionPaths):
            paths.data_dir.mkdir(parents=True, exist_ok=True)
            return paths.data_dir

    return data_dir()


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
