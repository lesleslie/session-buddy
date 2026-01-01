"""Tests for the DI-backed instance manager helpers."""

from __future__ import annotations

import os
import sys
import types
from typing import TYPE_CHECKING, Any

import pytest
from session_buddy.di import configure
from session_buddy.di import reset as reset_di
from session_buddy.di.container import depends
from session_buddy.utils import instance_managers

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_di_after() -> None:
    """Ensure DI state is reset after each test."""
    yield
    reset_di()
    instance_managers.reset_instances()


@pytest.mark.asyncio
async def test_get_app_monitor_registers_singleton(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """App monitor is created once and cached through the DI container."""
    module = types.ModuleType("session_buddy.app_monitor")
    module.__spec__ = types.SimpleNamespace(name="session_buddy.app_monitor")  # type: ignore[attr-defined]

    class DummyMonitor:
        def __init__(self, data_dir: str, project_paths: list[str]) -> None:
            self.data_dir = data_dir
            self.project_paths = project_paths
            self.started = False

        async def start_monitoring(
            self, project_paths: list[str] | None = None
        ) -> None:
            self.started = True

    module.ApplicationMonitor = DummyMonitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.app_monitor", module)

    # Monkeypatch HOME first, then reset and configure
    monkeypatch.setenv("HOME", str(tmp_path))
    os.chdir(tmp_path)
    from session_buddy.core.permissions import SessionPermissionsManager

    SessionPermissionsManager.reset_singleton()
    configure(force=True)

    # First call creates and registers the monitor
    monitor = await instance_managers.get_app_monitor()
    assert isinstance(monitor, DummyMonitor)

    # Second call should return the same instance (cached in DI)
    monitor2 = await instance_managers.get_app_monitor()
    assert monitor2 is monitor


@pytest.mark.asyncio
async def test_get_llm_manager_uses_di_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """LLM manager is provided from DI and preserved between calls."""
    module = types.ModuleType("session_buddy.llm_providers")
    module.__spec__ = types.SimpleNamespace(name="session_buddy.llm_providers")  # type: ignore[attr-defined]

    class DummyLLMManager:
        def __init__(self, config: str | None = None) -> None:
            self.config = config

    module.LLMManager = DummyLLMManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.llm_providers", module)

    # Monkeypatch HOME first, then reset and configure
    monkeypatch.setenv("HOME", str(tmp_path))
    from session_buddy.core.permissions import SessionPermissionsManager

    SessionPermissionsManager.reset_singleton()
    configure(force=True)

    # First and second calls should return the same cached instance
    first = await instance_managers.get_llm_manager()
    second = await instance_managers.get_llm_manager()

    assert isinstance(first, DummyLLMManager)
    assert first is second  # Singleton behavior verified


@pytest.mark.asyncio
async def test_serverless_manager_uses_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Serverless manager resolves through DI and respects config loading."""
    module = types.ModuleType("session_buddy.serverless_mode")
    module.__spec__ = types.SimpleNamespace(name="session_buddy.serverless_mode")  # type: ignore[attr-defined]

    class DummyStorage:
        def __init__(self, config: dict[str, Any]) -> None:
            self.config = config

    class DummyConfigManager:
        called = False

        @staticmethod
        def load_config(path: str | None) -> dict[str, Any]:
            DummyConfigManager.called = True
            return {"path": path or "memory"}

        @staticmethod
        def create_storage_backend(config: dict[str, Any]) -> DummyStorage:
            return DummyStorage(config)

    class DummyServerlessManager:
        def __init__(self, backend: DummyStorage) -> None:
            self.backend = backend

        async def create_session(
            self,
            user_id: str,
            project_id: str,
            session_data: dict[str, Any] | None,
            ttl_hours: int,
        ) -> str:
            return "session-id"

    module.ServerlessConfigManager = DummyConfigManager  # type: ignore[attr-defined]
    module.ServerlessSessionManager = DummyServerlessManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.serverless_mode", module)

    # Monkeypatch HOME first, then reset and configure
    monkeypatch.setenv("HOME", str(tmp_path))
    from session_buddy.core.permissions import SessionPermissionsManager

    SessionPermissionsManager.reset_singleton()
    configure(force=True)

    manager = await instance_managers.get_serverless_manager()
    assert isinstance(manager, DummyServerlessManager)
    assert DummyConfigManager.called is True
    assert manager.backend.config["path"] == "memory"

    # Test singleton behavior without triggering bevy's async machinery
    manager2 = await instance_managers.get_serverless_manager()
    assert manager2 is manager  # Singleton behavior verified
