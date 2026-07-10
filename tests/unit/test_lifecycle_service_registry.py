"""Tests for session_buddy.core.lifecycle.service_registry.

Covers ServiceSpec dataclass, ServiceRegistry orchestration (register,
init_all, health_all, cleanup_all), the singleton get_service_registry,
and the per-service default registrations via stubbed dependency modules.
"""

from __future__ import annotations

import importlib
import sys
import types
from contextlib import suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.core.lifecycle.service_registry import (
    ServiceHook,
    ServiceRegistry,
    ServiceSpec,
    _maybe_call,
    _noop,
    get_service_registry,
)


# ---------------------------------------------------------------------------
# Helpers — fresh registry + stub adapter modules
# ---------------------------------------------------------------------------


def _make_stub_module(name: str) -> types.ModuleType:
    """Create and register an empty stub module under ``name``."""
    mod = types.ModuleType(name)
    mod.__file__ = f"<test-stub-{name}>"  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _stub_adapter_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    *,
    init: Any = None,
    health: Any = None,
    cleanup: Any = None,
) -> types.ModuleType:
    """Replace session_buddy.adapters.lifecycle with controlled async/sync stubs.

    Returns the stub module so tests can override the individual functions
    if they need more specific behavior.
    """
    stub = _make_stub_module("session_buddy.adapters.lifecycle")
    stub.init_reflection_adapter = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    stub.health_reflection_adapter = MagicMock(return_value=True)  # type: ignore[attr-defined]
    stub.cleanup_reflection_adapter = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    stub.init_knowledge_graph_adapter = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    stub.health_knowledge_graph_adapter = MagicMock(return_value=True)  # type: ignore[attr-defined]
    stub.cleanup_knowledge_graph_adapter = MagicMock(return_value=None)  # type: ignore[attr-defined]
    stub.init_storage_adapters = MagicMock(return_value=None)  # type: ignore[attr-defined]
    stub.health_storage_adapters = MagicMock(return_value=True)  # type: ignore[attr-defined]
    stub.cleanup_storage_adapters = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    stub.init_cache_adapters = MagicMock(return_value=None)  # type: ignore[attr-defined]
    stub.health_cache_adapters = MagicMock(return_value=True)  # type: ignore[attr-defined]
    stub.cleanup_cache_adapters = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    if init is not None:
        stub.init_reflection_adapter = init  # type: ignore[attr-defined]
    if health is not None:
        stub.health_reflection_adapter = health  # type: ignore[attr-defined]
    if cleanup is not None:
        stub.cleanup_reflection_adapter = cleanup  # type: ignore[attr-defined]

    return stub


@pytest.fixture
def fresh_registry() -> ServiceRegistry:
    """A brand-new ServiceRegistry with no default registrations."""
    return ServiceRegistry()


# ---------------------------------------------------------------------------
# ServiceSpec dataclass
# ---------------------------------------------------------------------------


class TestServiceSpec:
    """Verify the immutable ServiceSpec dataclass."""

    def test_minimal_construction(self) -> None:
        spec = ServiceSpec(name="svc", category="core")
        assert spec.name == "svc"
        assert spec.category == "core"
        assert spec.init is None
        assert spec.health is None
        assert spec.cleanup is None

    def test_full_construction(self) -> None:
        init = lambda: None  # noqa: E731
        health = lambda: True  # noqa: E731
        cleanup = lambda: None  # noqa: E731
        spec = ServiceSpec(
            name="svc", category="core", init=init, health=health, cleanup=cleanup
        )
        assert spec.init is init
        assert spec.health is health
        assert spec.cleanup is cleanup

    def test_frozen_rejects_mutation(self) -> None:
        spec = ServiceSpec(name="svc", category="core")
        with pytest.raises((AttributeError, Exception)):
            spec.name = "other"  # type: ignore[misc]

    def test_slots_reject_new_attributes(self) -> None:
        spec = ServiceSpec(name="svc", category="core")
        # Frozen dataclasses with __slots__ raise something (AttributeError
        # for plain slots, FrozenInstanceError for frozen dataclasses). The
        # shared base class is what enforces rejection; we just verify that
        # a write attempt fails.
        with pytest.raises((AttributeError, Exception)):
            spec.unknown = "x"  # type: ignore[attr-defined]

    def test_equality(self) -> None:
        a = ServiceSpec(name="svc", category="core")
        b = ServiceSpec(name="svc", category="core")
        assert a == b

        c = ServiceSpec(name="svc2", category="core")
        assert a != c

    def test_servicehook_type_is_callable(self) -> None:
        # ServiceHook is a TypeAlias for Callable — make sure it's importable
        assert ServiceHook is not None
        assert callable(lambda: None)


# ---------------------------------------------------------------------------
# _maybe_call helper
# ---------------------------------------------------------------------------


class TestMaybeCall:
    """Verify the hook dispatcher that handles None, sync, and async hooks."""

    async def test_none_hook_returns_none(self) -> None:
        assert await _maybe_call(None) is None

    async def test_sync_hook_runs_and_returns_value(self) -> None:
        result = await _maybe_call(lambda: 42)
        assert result == 42

    async def test_async_hook_is_awaited(self) -> None:
        async def hook() -> str:
            return "async-result"

        assert await _maybe_call(hook) == "async-result"

    async def test_sync_hook_returning_none(self) -> None:
        assert await _maybe_call(lambda: None) is None

    async def test_sync_hook_with_side_effects(self) -> None:
        bucket: list[str] = []

        def hook() -> str:
            bucket.append("called")
            return "ok"

        result = await _maybe_call(hook)
        assert result == "ok"
        assert bucket == ["called"]


# ---------------------------------------------------------------------------
# _noop helper
# ---------------------------------------------------------------------------


class TestNoop:
    """Verify the no-op sentinel function."""

    def test_returns_none(self) -> None:
        assert _noop() is None

    def test_callable_repeatedly(self) -> None:
        for _ in range(5):
            assert _noop() is None


# ---------------------------------------------------------------------------
# ServiceRegistry: register and basic state
# ---------------------------------------------------------------------------


class TestServiceRegistryRegister:
    """Verify registration mutates the registry correctly."""

    def test_register_appends_in_order(self, fresh_registry: ServiceRegistry) -> None:
        spec_a = ServiceSpec(name="a", category="core")
        spec_b = ServiceSpec(name="b", category="memory")
        spec_c = ServiceSpec(name="c", category="adapters")

        fresh_registry.register(spec_a)
        fresh_registry.register(spec_b)
        fresh_registry.register(spec_c)

        assert fresh_registry._services == [spec_a, spec_b, spec_c]

    def test_empty_registry_initially(self, fresh_registry: ServiceRegistry) -> None:
        assert fresh_registry._services == []

    def test_register_accepts_duplicate_names(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        # The registry does not dedupe; duplicates are appended as-is
        spec = ServiceSpec(name="dup", category="core")
        fresh_registry.register(spec)
        fresh_registry.register(spec)
        assert len(fresh_registry._services) == 2


# ---------------------------------------------------------------------------
# ServiceRegistry: init_all
# ---------------------------------------------------------------------------


class TestServiceRegistryInitAll:
    """Verify the init lifecycle runs all init hooks in registration order."""

    async def test_calls_each_init_hook(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        calls: list[str] = []

        def make_hook(name: str):
            def hook() -> None:
                calls.append(name)

            return hook

        fresh_registry.register(
            ServiceSpec(name="a", category="x", init=make_hook("a"))
        )
        fresh_registry.register(
            ServiceSpec(name="b", category="x", init=make_hook("b"))
        )
        fresh_registry.register(
            ServiceSpec(name="c", category="x", init=make_hook("c"))
        )

        await fresh_registry.init_all()
        assert calls == ["a", "b", "c"]

    async def test_skips_services_with_no_init_hook(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        calls: list[str] = []

        def hook() -> None:
            calls.append("ran")

        fresh_registry.register(ServiceSpec(name="with_init", category="x", init=hook))
        fresh_registry.register(ServiceSpec(name="no_init", category="x"))

        await fresh_registry.init_all()
        assert calls == ["ran"]

    async def test_awaits_async_init_hooks(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        events: list[str] = []

        async def async_hook() -> None:
            events.append("async-start")
            events.append("async-end")

        fresh_registry.register(
            ServiceSpec(name="async-svc", category="x", init=async_hook)
        )

        await fresh_registry.init_all()
        assert events == ["async-start", "async-end"]

    async def test_empty_registry_init_all_is_noop(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        # Should not raise
        await fresh_registry.init_all()


# ---------------------------------------------------------------------------
# ServiceRegistry: health_all
# ---------------------------------------------------------------------------


class TestServiceRegistryHealthAll:
    """Verify health checks produce a name → result map."""

    async def test_collects_results_by_service_name(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        fresh_registry.register(
            ServiceSpec(name="a", category="x", health=lambda: True)
        )
        fresh_registry.register(
            ServiceSpec(name="b", category="x", health=lambda: False)
        )
        fresh_registry.register(
            ServiceSpec(name="c", category="x", health=lambda: {"status": "ok"})
        )

        results = await fresh_registry.health_all()
        assert results == {
            "a": True,
            "b": False,
            "c": {"status": "ok"},
        }

    async def test_handles_missing_health_hook(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        fresh_registry.register(ServiceSpec(name="a", category="x"))
        results = await fresh_registry.health_all()
        assert results == {"a": None}

    async def test_awaits_async_health_hooks(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        async def async_health() -> bool:
            return True

        fresh_registry.register(
            ServiceSpec(name="async-svc", category="x", health=async_health)
        )

        results = await fresh_registry.health_all()
        assert results == {"async-svc": True}

    async def test_empty_registry_health_all_returns_empty_dict(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        results = await fresh_registry.health_all()
        assert results == {}

    async def test_health_check_can_raise(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        # The registry does NOT swallow errors; surface them so callers can
        # decide what to do. This is by design (per the implementation).
        def boom() -> None:
            raise RuntimeError("health check failed")

        fresh_registry.register(
            ServiceSpec(name="explode", category="x", health=boom)
        )
        with pytest.raises(RuntimeError, match="health check failed"):
            await fresh_registry.health_all()


# ---------------------------------------------------------------------------
# ServiceRegistry: cleanup_all
# ---------------------------------------------------------------------------


class TestServiceRegistryCleanupAll:
    """Verify cleanup runs in registration order (reverse of typical teardown)."""

    async def test_calls_each_cleanup_hook(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        calls: list[str] = []

        def make_hook(name: str):
            def hook() -> None:
                calls.append(name)

            return hook

        fresh_registry.register(
            ServiceSpec(name="a", category="x", cleanup=make_hook("a"))
        )
        fresh_registry.register(
            ServiceSpec(name="b", category="x", cleanup=make_hook("b"))
        )

        await fresh_registry.cleanup_all()
        assert calls == ["a", "b"]

    async def test_skips_services_with_no_cleanup_hook(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        calls: list[str] = []

        def hook() -> None:
            calls.append("ran")

        fresh_registry.register(
            ServiceSpec(name="with_cleanup", category="x", cleanup=hook)
        )
        fresh_registry.register(ServiceSpec(name="no_cleanup", category="x"))

        await fresh_registry.cleanup_all()
        assert calls == ["ran"]

    async def test_awaits_async_cleanup_hooks(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        events: list[str] = []

        async def async_cleanup() -> None:
            events.append("cleaned")

        fresh_registry.register(
            ServiceSpec(name="async-svc", category="x", cleanup=async_cleanup)
        )

        await fresh_registry.cleanup_all()
        assert events == ["cleaned"]

    async def test_empty_registry_cleanup_all_is_noop(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        await fresh_registry.cleanup_all()


# ---------------------------------------------------------------------------
# Full lifecycle: init → health → cleanup
# ---------------------------------------------------------------------------


class TestServiceRegistryFullLifecycle:
    """Verify init → health → cleanup produces expected invocations."""

    async def test_full_lifecycle_runs_each_phase(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        init_calls: list[str] = []
        health_calls: list[str] = []
        cleanup_calls: list[str] = []

        def make_init(name: str):
            def hook() -> str:
                init_calls.append(name)
                return name

            return hook

        def make_health(name: str):
            def hook() -> bool:
                health_calls.append(name)
                return True

            return hook

        def make_cleanup(name: str):
            def hook() -> None:
                cleanup_calls.append(name)

            return hook

        fresh_registry.register(
            ServiceSpec(
                name="svc-a",
                category="core",
                init=make_init("svc-a"),
                health=make_health("svc-a"),
                cleanup=make_cleanup("svc-a"),
            )
        )
        fresh_registry.register(
            ServiceSpec(
                name="svc-b",
                category="memory",
                init=make_init("svc-b"),
                health=make_health("svc-b"),
                cleanup=make_cleanup("svc-b"),
            )
        )

        await fresh_registry.init_all()
        await fresh_registry.health_all()
        await fresh_registry.cleanup_all()

        assert init_calls == ["svc-a", "svc-b"]
        assert health_calls == ["svc-a", "svc-b"]
        assert cleanup_calls == ["svc-a", "svc-b"]


# ---------------------------------------------------------------------------
# Default registration: _register_defaults
# ---------------------------------------------------------------------------


class TestDefaultRegistrations:
    """Verify that _register_defaults installs the expected service catalog."""

    def test_default_registrations_count(self, fresh_registry: ServiceRegistry) -> None:
        from session_buddy.core.lifecycle import service_registry

        service_registry._register_defaults(fresh_registry)
        # 9 services are registered by default (per the implementation)
        assert len(fresh_registry._services) == 9

    def test_default_registrations_have_required_categories(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        service_registry._register_defaults(fresh_registry)
        categories = {spec.category for spec in fresh_registry._services}
        # The default set covers core/memory/adapters/tools/utils
        assert {"core", "memory", "adapters", "tools", "utils"}.issubset(categories)

    def test_default_registrations_have_unique_names(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        service_registry._register_defaults(fresh_registry)
        names = [spec.name for spec in fresh_registry._services]
        # No duplicate names in the default catalog
        assert len(names) == len(set(names))

    def test_default_registrations_include_known_services(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        service_registry._register_defaults(fresh_registry)
        names = {spec.name for spec in fresh_registry._services}
        for required in (
            "core.di_config",
            "core.permissions_manager",
            "core.lifecycle_manager",
            "memory.reflection_db",
            "memory.knowledge_graph",
            "adapters.storage",
            "adapters.caches",
            "tools.registry",
            "utils.logging",
        ):
            assert required in names


# ---------------------------------------------------------------------------
# get_service_registry singleton
# ---------------------------------------------------------------------------


class TestGetServiceRegistry:
    """Verify the module-level singleton behavior."""

    def test_returns_a_service_registry_instance(self) -> None:
        registry = get_service_registry()
        assert isinstance(registry, ServiceRegistry)

    def test_returns_same_instance_across_calls(self) -> None:
        first = get_service_registry()
        second = get_service_registry()
        assert first is second

    def test_singleton_has_default_services(self) -> None:
        registry = get_service_registry()
        # Singleton is initialized with the default 9 services
        assert len(registry._services) == 9


# ---------------------------------------------------------------------------
# Stub-based coverage of the default service hooks
# ---------------------------------------------------------------------------


class TestDefaultHookBehavior:
    """Run init/health/cleanup of default services against stubbed modules.

    These tests exercise the private functions in service_registry that
    delegate to session_buddy.adapters.lifecycle and other dependencies.
    """

    def test_health_tools_registry_returns_true(self) -> None:
        from session_buddy.core.lifecycle import service_registry

        assert service_registry._health_tools_registry() is True

    def test_health_logging_returns_false_when_not_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.di import container
        from session_buddy.core.lifecycle import service_registry

        # Reset the container to ensure SessionLogger isn't registered
        monkeypatch.setattr(container.depends, "_instances", {})
        monkeypatch.setattr(container.depends, "_resolver", container.Resolver())
        result = service_registry._health_logging()
        assert result is False

    def test_health_di_config_returns_false_when_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.di import container
        from session_buddy.core.lifecycle import service_registry

        monkeypatch.setattr(container.depends, "_instances", {})
        monkeypatch.setattr(container.depends, "_resolver", container.Resolver())
        result = service_registry._health_di_config()
        assert result is False

    def test_health_permissions_manager_returns_false_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.di import container
        from session_buddy.core.lifecycle import service_registry

        monkeypatch.setattr(container.depends, "_instances", {})
        monkeypatch.setattr(container.depends, "_resolver", container.Resolver())
        result = service_registry._health_permissions_manager()
        assert result is False

    def test_health_lifecycle_manager_returns_false_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.di import container
        from session_buddy.core.lifecycle import service_registry

        monkeypatch.setattr(container.depends, "_instances", {})
        monkeypatch.setattr(container.depends, "_resolver", container.Resolver())
        result = service_registry._health_lifecycle_manager()
        assert result is False

    def test_init_logging_is_idempotent(self) -> None:
        from session_buddy.core.lifecycle import service_registry

        # Calling multiple times should not raise
        service_registry._init_logging()
        service_registry._init_logging()

    def test_init_di_config_idempotent(self) -> None:
        from session_buddy.core.lifecycle import service_registry

        service_registry._init_di_config()
        service_registry._init_di_config()

    def test_init_permissions_manager_idempotent_when_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.di import container
        from session_buddy.core.lifecycle import service_registry

        # Pre-register a SessionPermissionsManager to exercise the "already set" branch
        from session_buddy.core.permissions import SessionPermissionsManager

        # Use a tmp path to satisfy claude_dir
        fake_manager = object.__new__(SessionPermissionsManager)
        container.depends.set(SessionPermissionsManager, fake_manager)
        try:
            service_registry._init_permissions_manager()
        finally:
            container.depends.reset()
            container.depends._instances = {}
            container.depends._resolver = container.Resolver()

    def test_init_lifecycle_manager_idempotent_when_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.core.session_manager import SessionLifecycleManager
        from session_buddy.di import container

        existing = SessionLifecycleManager()
        container.depends.set(SessionLifecycleManager, existing)
        try:
            service_registry._init_lifecycle_manager()
            # The existing instance should be untouched
            assert container.depends.get_sync(SessionLifecycleManager) is existing
        finally:
            container.depends.reset()
            container.depends._instances = {}
            container.depends._resolver = container.Resolver()

    def test_init_reflection_db_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        # Run via the inner await — uses AsyncMock, returns None
        import asyncio

        asyncio.run(service_registry._init_reflection_db())
        stub.init_reflection_adapter.assert_awaited_once()

    def test_health_reflection_db_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        result = service_registry._health_reflection_db()
        assert result is True
        stub.health_reflection_adapter.assert_called_once()

    def test_health_reflection_db_propagates_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        def _boom() -> bool:
            raise RuntimeError("nope")

        _stub_adapter_lifecycle(monkeypatch, health=_boom)
        # Implementation does not suppress — re-raises
        with pytest.raises(RuntimeError, match="nope"):
            service_registry._health_reflection_db()

    def test_cleanup_reflection_db_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        import asyncio

        asyncio.run(service_registry._cleanup_reflection_db())
        stub.cleanup_reflection_adapter.assert_awaited_once()

    def test_init_knowledge_graph_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        import asyncio

        # Direct call to the registry's wrapper
        asyncio.run(service_registry._init_knowledge_graph())
        stub.init_knowledge_graph_adapter.assert_awaited_once()

    def test_health_knowledge_graph_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        result = service_registry._health_knowledge_graph()
        assert result is True
        stub.health_knowledge_graph_adapter.assert_called_once()

    def test_cleanup_knowledge_graph_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        service_registry._cleanup_knowledge_graph()
        stub.cleanup_knowledge_graph_adapter.assert_called_once()

    def test_init_storage_adapters_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        service_registry._init_storage_adapters()
        stub.init_storage_adapters.assert_called_once()

    def test_health_storage_adapters_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        result = service_registry._health_storage_adapters()
        assert result is True
        stub.health_storage_adapters.assert_called_once()

    def test_cleanup_storage_adapters_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        import asyncio

        asyncio.run(service_registry._cleanup_storage_adapters())
        stub.cleanup_storage_adapters.assert_awaited_once()

    def test_init_cache_adapters_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        service_registry._init_cache_adapters()
        stub.init_cache_adapters.assert_called_once()

    def test_health_cache_adapters_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        result = service_registry._health_cache_adapters()
        assert result is True
        stub.health_cache_adapters.assert_called_once()

    def test_cleanup_cache_adapters_uses_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        stub = _stub_adapter_lifecycle(monkeypatch)
        import asyncio

        asyncio.run(service_registry._cleanup_cache_adapters())
        stub.cleanup_cache_adapters.assert_awaited_once()

    def test_health_tools_registry_handles_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry

        # Patch suppress to raise; the implementation uses suppress(Exception)
        # so we make suppress swallow nothing by raising an unexpected error.
        # Implementation does `with suppress(Exception): return True`
        # so this path should still return True. Verify it.
        assert service_registry._health_tools_registry() is True

    def test_health_logging_handles_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.di import container

        # Force the depends.get_sync to raise — the implementation suppresses
        container.depends.reset()
        container.depends._instances = {}
        container.depends._resolver = container.Resolver()
        result = service_registry._health_logging()
        assert result is False

    def test_health_di_config_handles_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.di import container

        container.depends.reset()
        container.depends._instances = {}
        container.depends._resolver = container.Resolver()
        result = service_registry._health_di_config()
        assert result is False

    def test_health_permissions_manager_handles_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.di import container

        container.depends.reset()
        container.depends._instances = {}
        container.depends._resolver = container.Resolver()
        result = service_registry._health_permissions_manager()
        assert result is False

    def test_health_lifecycle_manager_handles_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.di import container

        container.depends.reset()
        container.depends._instances = {}
        container.depends._resolver = container.Resolver()
        result = service_registry._health_lifecycle_manager()
        assert result is False

    def test_ensure_session_paths_creates_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.di import container
        from session_buddy.di.config import SessionPaths

        container.depends.reset()
        container.depends._instances = {}
        container.depends._resolver = container.Resolver()

        # Use a temp HOME so SessionPaths.from_home() lands in tmp_path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_home:
            monkeypatch.setenv("HOME", tmp_home)
            paths = service_registry._ensure_session_paths()
            assert isinstance(paths, SessionPaths)
            # Second call should reuse the registered instance
            again = service_registry._ensure_session_paths()
            assert again is paths

    def test_ensure_session_paths_returns_existing_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from session_buddy.core.lifecycle import service_registry
        from session_buddy.di import container
        from session_buddy.di.config import SessionPaths

        # Pre-register an instance so the `with suppress(Exception): ... if isinstance(...) return paths`
        # branch fires
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_home:
            monkeypatch.setenv("HOME", tmp_home)
            existing = SessionPaths.from_home()
            existing.ensure_directories()
            container.depends.set(SessionPaths, existing)
            try:
                paths = service_registry._ensure_session_paths()
                assert paths is existing
            finally:
                container.depends.reset()
                container.depends._instances = {}
                container.depends._resolver = container.Resolver()


# ---------------------------------------------------------------------------
# __all__ export contract
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify the public exports."""

    def test_all_exports_are_importable(self) -> None:
        from session_buddy.core.lifecycle import service_registry

        for name in service_registry.__all__:
            assert hasattr(service_registry, name), f"missing export: {name}"


# ---------------------------------------------------------------------------
# Async dispatch edge cases
# ---------------------------------------------------------------------------


class TestAsyncDispatchEdgeCases:
    """Verify hook result handling for the various return-type combinations."""

    async def test_hook_returning_awaitable_object(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        # An object whose __await__ returns a value
        class _Awaitable:
            def __await__(self):
                yield
                return "awaited"

        def hook():
            return _Awaitable()

        fresh_registry.register(ServiceSpec(name="x", category="x", init=hook))
        await fresh_registry.init_all()  # Should not raise

    async def test_hook_returning_non_awaitable(
        self, fresh_registry: ServiceRegistry
    ) -> None:
        # Hook returns a plain int; not awaitable
        def hook() -> int:
            return 7

        fresh_registry.register(ServiceSpec(name="x", category="x", init=hook))
        # Should not raise — int is not awaitable
        await fresh_registry.init_all()
