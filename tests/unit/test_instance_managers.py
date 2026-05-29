"""Tests for the DI-backed instance manager helpers."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from typing import TYPE_CHECKING, Any
from pathlib import Path

import pytest


def _load_instance_managers_module():
    repo_root = Path(__file__).resolve().parents[2]

    if "session_buddy" not in sys.modules:
        package = types.ModuleType("session_buddy")
        package.__path__ = [str(repo_root / "session_buddy")]  # type: ignore[attr-defined]
        sys.modules["session_buddy"] = package

    utils_package_name = "session_buddy.utils"
    if utils_package_name not in sys.modules:
        utils_package = types.ModuleType(utils_package_name)
        utils_package.__path__ = [str(repo_root / "session_buddy" / "utils")]  # type: ignore[attr-defined]
        sys.modules[utils_package_name] = utils_package

    adapters_package_name = "session_buddy.adapters"
    if adapters_package_name not in sys.modules:
        adapters_package = types.ModuleType(adapters_package_name)
        adapters_package.__path__ = [str(repo_root / "session_buddy" / "adapters")]  # type: ignore[attr-defined]
        sys.modules[adapters_package_name] = adapters_package

    module_path = repo_root / "session_buddy" / "utils" / "instance_managers.py"
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.instance_managers",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


from session_buddy.di.config import SessionPaths
from session_buddy.di.container import depends

instance_managers = _load_instance_managers_module()

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_di_after() -> None:
    """Ensure DI state is reset after each test."""
    yield
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
    cache: dict[object, object] = {}
    monkeypatch.setattr(
        instance_managers,
        "get_sync_typed",
        lambda typ: cache[typ] if typ in cache else (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(instance_managers.depends, "set", lambda key, value: cache.__setitem__(key, value))

    # Monkeypatch HOME first, then reset and configure
    monkeypatch.setenv("HOME", str(tmp_path))
    os.chdir(tmp_path)

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
    cache: dict[object, object] = {}
    monkeypatch.setattr(
        instance_managers,
        "get_sync_typed",
        lambda typ: cache[typ] if typ in cache else (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(instance_managers.depends, "set", lambda key, value: cache.__setitem__(key, value))

    # Monkeypatch HOME first, then reset and configure
    monkeypatch.setenv("HOME", str(tmp_path))

    # First and second calls should return the same cached instance
    first = await instance_managers.get_llm_manager()
    second = await instance_managers.get_llm_manager()

    assert isinstance(first, DummyLLMManager)
    assert first is second  # Singleton behavior verified


def test_reset_instances_calls_depends_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def fake_reset() -> None:
        called["value"] = True

    monkeypatch.setattr(instance_managers.depends, "reset", fake_reset)

    instance_managers.reset_instances()

    assert called["value"] is True


def test_resolve_claude_dir_uses_di_session_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    claude_dir = tmp_path / ".claude"
    paths = SessionPaths(
        claude_dir=claude_dir,
        logs_dir=claude_dir / "logs",
        commands_dir=claude_dir / "commands",
        data_dir=claude_dir / "data",
    )

    monkeypatch.setattr(instance_managers.depends, "get_sync", lambda _typ: paths)

    result = instance_managers._resolve_claude_dir()

    assert result == claude_dir
    assert result.exists()


def test_resolve_claude_dir_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        instance_managers.depends,
        "get_sync",
        lambda _typ: (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(instance_managers.os.path, "expanduser", lambda _path: str(tmp_path))

    result = instance_managers._resolve_claude_dir()

    assert result == tmp_path / ".claude"
    assert result.exists()


def test_resolve_claude_dir_falls_back_on_wrong_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(instance_managers.depends, "get_sync", lambda _typ: object())
    monkeypatch.setattr(instance_managers.os.path, "expanduser", lambda _path: str(tmp_path))

    result = instance_managers._resolve_claude_dir()

    assert result == tmp_path / ".claude"
    assert result.exists()


@pytest.mark.asyncio
async def test_get_app_monitor_creates_and_registers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = types.ModuleType("session_buddy.app_monitor")
    module.__spec__ = types.SimpleNamespace(name="session_buddy.app_monitor")  # type: ignore[attr-defined]

    class DummyMonitor:
        def __init__(self, data_dir: str, project_paths: list[str]) -> None:
            self.data_dir = data_dir
            self.project_paths = project_paths

    module.ApplicationMonitor = DummyMonitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.app_monitor", module)
    monkeypatch.setattr(
        instance_managers,
        "_resolve_claude_dir",
        lambda: tmp_path / ".claude",
    )
    monkeypatch.setattr(
        instance_managers,
        "get_sync_typed",
        lambda _typ: (_ for _ in ()).throw(KeyError("missing")),
    )
    calls: list[tuple[object, object]] = []
    monkeypatch.setattr(
        instance_managers.depends,
        "set",
        lambda key, value: calls.append((key, value)),
    )

    result = await instance_managers.get_app_monitor()

    assert isinstance(result, DummyMonitor)
    assert result.data_dir.endswith("data/app_monitoring")
    assert calls == [(DummyMonitor, result)]


@pytest.mark.asyncio
async def test_get_interruption_manager_creates_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("session_buddy.interruption_manager")
    module.__spec__ = types.SimpleNamespace(name="session_buddy.interruption_manager")  # type: ignore[attr-defined]

    class DummyInterruptionManager:
        def __init__(self) -> None:
            self.started = True

    module.InterruptionManager = DummyInterruptionManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.interruption_manager", module)
    cache: dict[object, object] = {}
    monkeypatch.setattr(
        instance_managers,
        "get_sync_typed",
        lambda typ: cache[typ] if typ in cache else (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(instance_managers.depends, "set", lambda key, value: cache.__setitem__(key, value))

    result = await instance_managers.get_interruption_manager()
    cached = await instance_managers.get_interruption_manager()

    assert isinstance(result, DummyInterruptionManager)
    assert cached is result


@pytest.mark.asyncio
async def test_singleton_fallbacks_when_di_returns_wrong_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_monitor = types.ModuleType("session_buddy.app_monitor")
    app_monitor.__spec__ = types.SimpleNamespace(name="session_buddy.app_monitor")  # type: ignore[attr-defined]

    class DummyMonitor:
        def __init__(self, data_dir: str, project_paths: list[str]) -> None:
            self.data_dir = data_dir
            self.project_paths = project_paths

    app_monitor.ApplicationMonitor = DummyMonitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.app_monitor", app_monitor)

    llm = types.ModuleType("session_buddy.llm_providers")
    llm.__spec__ = types.SimpleNamespace(name="session_buddy.llm_providers")  # type: ignore[attr-defined]

    class DummyLLMManager:
        def __init__(self, config: str | None = None) -> None:
            self.config = config

    llm.LLMManager = DummyLLMManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.llm_providers", llm)

    interruption = types.ModuleType("session_buddy.interruption_manager")
    interruption.__spec__ = types.SimpleNamespace(name="session_buddy.interruption_manager")  # type: ignore[attr-defined]

    class DummyInterruptionManager:
        def __init__(self) -> None:
            self.started = True

    interruption.InterruptionManager = DummyInterruptionManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.interruption_manager", interruption)

    serverless = types.ModuleType("session_buddy.serverless_mode")
    serverless.__spec__ = types.SimpleNamespace(name="session_buddy.serverless_mode")  # type: ignore[attr-defined]

    class DummyStorage:
        def __init__(self, config: dict[str, Any]) -> None:
            self.config = config

    class DummyConfigManager:
        @staticmethod
        def load_config(path: str | None) -> dict[str, Any]:
            return {"path": path or "memory"}

        @staticmethod
        def create_storage_backend(config: dict[str, Any]) -> DummyStorage:
            return DummyStorage(config)

    class DummyServerlessManager:
        def __init__(self, backend: DummyStorage) -> None:
            self.backend = backend

    serverless.ServerlessConfigManager = DummyConfigManager  # type: ignore[attr-defined]
    serverless.ServerlessSessionManager = DummyServerlessManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.serverless_mode", serverless)

    cache: dict[object, object] = {
        DummyMonitor: object(),
        DummyLLMManager: object(),
        DummyInterruptionManager: object(),
        DummyServerlessManager: object(),
    }

    monkeypatch.setattr(
        instance_managers,
        "get_sync_typed",
        lambda typ: cache[typ],
    )
    monkeypatch.setattr(
        instance_managers.depends,
        "set",
        lambda key, value: cache.__setitem__(key, value),
    )
    monkeypatch.setattr(instance_managers, "_resolve_claude_dir", lambda: tmp_path / ".claude")

    monitor = await instance_managers.get_app_monitor()
    llm_manager = await instance_managers.get_llm_manager()
    interruption_manager = await instance_managers.get_interruption_manager()
    serverless_manager = await instance_managers.get_serverless_manager()

    assert isinstance(monitor, DummyMonitor)
    assert isinstance(llm_manager, DummyLLMManager)
    assert isinstance(interruption_manager, DummyInterruptionManager)
    assert isinstance(serverless_manager, DummyServerlessManager)


@pytest.mark.asyncio
async def test_get_reflection_database_uses_cached_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("session_buddy.adapters.reflection_adapter_oneiric")
    module.__spec__ = types.SimpleNamespace(
        name="session_buddy.adapters.reflection_adapter_oneiric",
    )  # type: ignore[attr-defined]

    class DummyAdapter:
        pass

    module.ReflectionDatabaseAdapterOneiric = DummyAdapter  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        module,
    )
    cached = DummyAdapter()
    monkeypatch.setattr(instance_managers.depends, "get_sync", lambda _typ: cached)

    result = await instance_managers.get_reflection_database()

    assert result is cached


@pytest.mark.asyncio
async def test_get_app_monitor_returns_none_when_import_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.app_monitor",
        types.ModuleType("session_buddy.app_monitor"),
    )

    assert await instance_managers.get_app_monitor() is None


@pytest.mark.asyncio
async def test_get_llm_manager_returns_none_when_import_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.llm_providers",
        types.ModuleType("session_buddy.llm_providers"),
    )

    assert await instance_managers.get_llm_manager() is None


@pytest.mark.asyncio
async def test_get_serverless_manager_returns_none_when_import_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.serverless_mode",
        types.ModuleType("session_buddy.serverless_mode"),
    )

    assert await instance_managers.get_serverless_manager() is None


@pytest.mark.asyncio
async def test_get_reflection_database_returns_none_when_import_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        types.ModuleType("session_buddy.adapters.reflection_adapter_oneiric"),
    )
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter",
        types.ModuleType("session_buddy.adapters.reflection_adapter"),
    )

    assert await instance_managers.get_reflection_database() is None


@pytest.mark.asyncio
async def test_get_reflection_database_falls_back_to_legacy_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = types.ModuleType("session_buddy.adapters.reflection_adapter")
    legacy.__spec__ = types.SimpleNamespace(
        name="session_buddy.adapters.reflection_adapter",
    )  # type: ignore[attr-defined]

    class DummyLegacyAdapter:
        pass

    legacy.ReflectionDatabaseAdapter = DummyLegacyAdapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.adapters.reflection_adapter", legacy)
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        types.ModuleType("session_buddy.adapters.reflection_adapter_oneiric"),
    )

    cached = DummyLegacyAdapter()
    monkeypatch.setattr(instance_managers.depends, "get_sync", lambda _typ: cached)

    result = await instance_managers.get_reflection_database()

    assert result is cached


@pytest.mark.asyncio
async def test_get_reflection_database_falls_back_after_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("session_buddy.adapters.reflection_adapter_oneiric")
    module.__spec__ = types.SimpleNamespace(
        name="session_buddy.adapters.reflection_adapter_oneiric",
    )  # type: ignore[attr-defined]

    class DummyAdapter:
        pass

    module.ReflectionDatabaseAdapterOneiric = DummyAdapter  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        module,
    )

    lifecycle = types.ModuleType("session_buddy.adapters.lifecycle")

    async def init_reflection_adapter() -> None:
        return None

    lifecycle.init_reflection_adapter = init_reflection_adapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.adapters.lifecycle", lifecycle)
    cached = DummyAdapter()
    calls = {"count": 0}

    def fake_get_sync(_typ):
        calls["count"] += 1
        return object() if calls["count"] == 1 else cached

    monkeypatch.setattr(instance_managers.depends, "get_sync", fake_get_sync)

    assert await instance_managers.get_reflection_database() is cached


@pytest.mark.asyncio
async def test_get_reflection_database_returns_none_after_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("session_buddy.adapters.reflection_adapter_oneiric")
    module.__spec__ = types.SimpleNamespace(
        name="session_buddy.adapters.reflection_adapter_oneiric",
    )  # type: ignore[attr-defined]

    class DummyAdapter:
        pass

    module.ReflectionDatabaseAdapterOneiric = DummyAdapter  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter_oneiric",
        module,
    )

    lifecycle = types.ModuleType("session_buddy.adapters.lifecycle")

    async def init_reflection_adapter() -> None:
        return None

    lifecycle.init_reflection_adapter = init_reflection_adapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "session_buddy.adapters.lifecycle", lifecycle)
    monkeypatch.setattr(instance_managers.depends, "get_sync", lambda _typ: object())

    assert await instance_managers.get_reflection_database() is None


def test_iter_dependencies_collects_available_types(monkeypatch: pytest.MonkeyPatch) -> None:
    app_monitor = types.ModuleType("session_buddy.app_monitor")
    llm = types.ModuleType("session_buddy.llm_providers")
    interruption = types.ModuleType("session_buddy.interruption_manager")
    serverless = types.ModuleType("session_buddy.serverless_mode")
    reflection = types.ModuleType("session_buddy.adapters.reflection_adapter")

    class DummyAppMonitor:
        pass

    class DummyLLMManager:
        pass

    class DummyInterruptionManager:
        pass

    class DummyServerlessSessionManager:
        pass

    class DummyReflectionDatabaseAdapter:
        pass

    app_monitor.ApplicationMonitor = DummyAppMonitor  # type: ignore[attr-defined]
    llm.LLMManager = DummyLLMManager  # type: ignore[attr-defined]
    interruption.InterruptionManager = DummyInterruptionManager  # type: ignore[attr-defined]
    serverless.ServerlessSessionManager = DummyServerlessSessionManager  # type: ignore[attr-defined]
    reflection.ReflectionDatabaseAdapter = DummyReflectionDatabaseAdapter  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "session_buddy.app_monitor", app_monitor)
    monkeypatch.setitem(sys.modules, "session_buddy.llm_providers", llm)
    monkeypatch.setitem(sys.modules, "session_buddy.interruption_manager", interruption)
    monkeypatch.setitem(sys.modules, "session_buddy.serverless_mode", serverless)
    monkeypatch.setitem(
        sys.modules,
        "session_buddy.adapters.reflection_adapter",
        reflection,
    )

    deps = instance_managers._iter_dependencies()

    assert deps == [
        DummyAppMonitor,
        DummyLLMManager,
        DummyInterruptionManager,
        DummyServerlessSessionManager,
        DummyReflectionDatabaseAdapter,
    ]


def test_iter_dependencies_returns_empty_when_all_imports_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [
        "session_buddy.app_monitor",
        "session_buddy.llm_providers",
        "session_buddy.interruption_manager",
        "session_buddy.serverless_mode",
        "session_buddy.adapters.reflection_adapter",
    ]:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    assert instance_managers._iter_dependencies() == []


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
    cache: dict[object, object] = {}
    monkeypatch.setattr(
        instance_managers,
        "get_sync_typed",
        lambda typ: cache[typ] if typ in cache else (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(instance_managers.depends, "set", lambda key, value: cache.__setitem__(key, value))

    # Monkeypatch HOME first, then reset and configure
    monkeypatch.setenv("HOME", str(tmp_path))

    manager = await instance_managers.get_serverless_manager()
    assert isinstance(manager, DummyServerlessManager)
    assert DummyConfigManager.called is True
    assert manager.backend.config["path"] == "memory"

    # Test singleton behavior without triggering bevy's async machinery
    manager2 = await instance_managers.get_serverless_manager()
    assert manager2 is manager  # Singleton behavior verified
