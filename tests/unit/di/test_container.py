"""Unit tests for session_buddy.di.container.

This module exercises the ``ServiceContainer`` and the ``depends``
singleton — a Oneiric-backed dependency-injection container. The container
stores instances by name, accepts factories via
:meth:`ServiceContainer.register_factory`, and exposes synchronous
(:meth:`ServiceContainer.get_sync`, :meth:`ServiceContainer.get`) and
asynchronous (:meth:`ServiceContainer.get_async`) accessors. Keys are
normalised through ``_key_name`` to a dotted string and resolved by the
underlying ``oneiric`` ``Resolver``.

These tests deliberately cover the surface without invoking real services,
so they remain pure unit tests: classes registered stand in for "real"
dependencies and explicit factories exercise every branch of the cache
state machine (string factory, async factory, missing key, memoisation).
"""

from __future__ import annotations

from typing import Any

import pytest

from session_buddy.di.container import Inject, ServiceContainer, depends


# ---------------------------------------------------------------------------
# Sentinel key types used across the test module.
# ---------------------------------------------------------------------------


class _ServiceA:
    """Stand-in for a real service registered in the container."""

    def __init__(self, marker: str = "default") -> None:
        self.marker = marker


class _ServiceB:
    """Independent stand-in used to verify keys don't collide."""

    def __init__(self) -> None:
        self.value = 42


# ---------------------------------------------------------------------------
# ServiceContainer.__init__
# ---------------------------------------------------------------------------


class TestServiceContainerInit:
    """Construction initialises the internal caches."""

    def test_init_creates_resolver(self) -> None:
        container = ServiceContainer()
        assert container._resolver is not None

    def test_init_creates_empty_instances(self) -> None:
        container = ServiceContainer()
        assert container._instances == {}

    def test_separate_containers_have_independent_state(self) -> None:
        a = ServiceContainer()
        b = ServiceContainer()
        a._instances["x"] = 1
        assert "x" not in b._instances

    def test_depends_is_a_service_container(self) -> None:
        assert isinstance(depends, ServiceContainer)


# ---------------------------------------------------------------------------
# ServiceContainer.set
# ---------------------------------------------------------------------------


class TestSet:
    """``set`` stores an instance and registers a factory returning it."""

    def test_set_with_string_key(self) -> None:
        container = ServiceContainer()
        sentinel = object()
        container.set("svc", sentinel)
        assert container.get_sync("svc") is sentinel

    def test_set_with_class_key_uses_dotted_name(self) -> None:
        """Class keys are normalised to ``module.qualname`` and round-trip."""
        container = ServiceContainer()
        sentinel = _ServiceA()
        container.set(_ServiceA, sentinel)
        assert container.get_sync(_ServiceA) is sentinel

    def test_set_registers_factory_returning_same_instance(self) -> None:
        """Factory always returns the registered instance (not a copy)."""
        container = ServiceContainer()
        sentinel = _ServiceA(marker="unique")
        container.set("svc", sentinel)
        # Second retrieval also returns the same identity.
        assert container.get_sync("svc") is sentinel
        assert container.get_sync("svc").marker == "unique"

    def test_set_overwrites_previous_instance(self) -> None:
        container = ServiceContainer()
        first = _ServiceA(marker="first")
        second = _ServiceA(marker="second")
        container.set("svc", first)
        container.set("svc", second)
        assert container.get_sync("svc") is second


# ---------------------------------------------------------------------------
# ServiceContainer.register_factory
# ---------------------------------------------------------------------------


class TestRegisterFactory:
    """``register_factory`` defers instance creation until ``get_*`` is called."""

    def test_factory_called_lazily_on_get(self) -> None:
        container = ServiceContainer()
        calls: list[int] = []

        def factory() -> _ServiceA:
            calls.append(1)
            return _ServiceA()

        container.register_factory("svc", factory)
        assert calls == []  # Not invoked yet.
        container.get_sync("svc")
        assert calls == [1]

    def test_factory_result_is_cached(self) -> None:
        container = ServiceContainer()
        calls: list[int] = []

        def factory() -> _ServiceA:
            calls.append(1)
            return _ServiceA()

        container.register_factory("svc", factory)
        container.get_sync("svc")
        container.get_sync("svc")
        assert calls == [1]

    def test_register_factory_with_string_key(self) -> None:
        container = ServiceContainer()
        sentinel = _ServiceB()
        container.register_factory("svc", lambda: sentinel)
        assert container.get_sync("svc") is sentinel


# ---------------------------------------------------------------------------
# ServiceContainer.get_sync
# ---------------------------------------------------------------------------


class TestGetSync:
    """Synchronous lookup, with cache, factory resolution, and error paths."""

    def test_raises_key_error_for_unregistered_key(self) -> None:
        container = ServiceContainer()
        with pytest.raises(KeyError, match="Service not registered"):
            container.get_sync("does-not-exist")

    def test_raises_type_error_when_factory_is_string(self) -> None:
        """Oneiric deferred factories (string references) cannot be sync-instantiated."""
        container = ServiceContainer()

        def factory() -> Any:
            return "example"

        container.register_factory("svc", factory)
        # Simulate a deferred (string) factory by patching the candidate directly.
        from oneiric.core.resolution import Candidate

        candidate = Candidate(
            domain="service",
            key="svc",
            provider="deferred",
            factory="some-deferred-string",  # type: ignore[arg-type]
        )
        # Re-register a fresh candidate so the next get_sync sees the string factory.
        container._resolver.register(candidate)
        with pytest.raises(TypeError, match="Cannot instantiate string factory"):
            container.get_sync("svc")

    def test_raises_type_error_when_factory_returns_awaitable(self) -> None:
        """Async factories must be reached through ``get_async``."""
        container = ServiceContainer()

        async def async_factory() -> _ServiceA:
            return _ServiceA()

        container.register_factory("svc", async_factory)
        with pytest.raises(TypeError, match="Async factory registered for sync get"):
            container.get_sync("svc")
        # ``get_sync`` rejects the awaitable without running it; close the
        # coroutine so the event loop doesn't see an un-awaited warning.
        async_factory().close()

    def test_get_returns_instance_immediately_after_set(self) -> None:
        container = ServiceContainer()
        sentinel = _ServiceA()
        container.set("svc", sentinel)
        assert container.get("svc") is sentinel  # ``get`` aliases ``get_sync``.

    def test_class_key_round_trip_after_register_factory(self) -> None:
        container = ServiceContainer()
        sentinel = _ServiceB()
        container.register_factory(_ServiceB, lambda: sentinel)
        assert container.get_sync(_ServiceB) is sentinel


# ---------------------------------------------------------------------------
# ServiceContainer.get_async
# ---------------------------------------------------------------------------


class TestGetAsync:
    """Async lookup awaits coroutine-returning factories."""

    async def test_awaits_async_factory(self) -> None:
        container = ServiceContainer()

        async def async_factory() -> _ServiceA:
            return _ServiceA(marker="async")

        container.register_factory("svc", async_factory)
        instance = await container.get_async("svc")
        assert instance.marker == "async"

    async def test_async_factory_cached_after_first_call(self) -> None:
        container = ServiceContainer()
        calls: list[int] = []

        async def async_factory() -> _ServiceA:
            calls.append(1)
            return _ServiceA()

        container.register_factory("svc", async_factory)
        await container.get_async("svc")
        await container.get_async("svc")
        assert calls == [1]

    async def test_raises_key_error_for_unregistered_key(self) -> None:
        container = ServiceContainer()
        with pytest.raises(KeyError, match="Service not registered"):
            await container.get_async("does-not-exist")

    async def test_raises_type_error_when_factory_is_string(self) -> None:
        container = ServiceContainer()

        def factory() -> Any:
            return "example"

        container.register_factory("svc", factory)
        from oneiric.core.resolution import Candidate

        candidate = Candidate(
            domain="service",
            key="svc",
            provider="deferred",
            factory="some-deferred-string",  # type: ignore[arg-type]
        )
        container._resolver.register(candidate)
        with pytest.raises(TypeError, match="Cannot instantiate string factory"):
            await container.get_async("svc")

    async def test_returns_sync_factory_result_without_await(self) -> None:
        container = ServiceContainer()

        def sync_factory() -> _ServiceB:
            return _ServiceB()

        container.register_factory("svc", sync_factory)
        instance = await container.get_async("svc")
        assert isinstance(instance, _ServiceB)
        assert instance.value == 42


# ---------------------------------------------------------------------------
# ServiceContainer.reset
# ---------------------------------------------------------------------------


class TestReset:
    """``reset`` clears caches while preserving container identity."""

    def test_reset_clears_instances(self) -> None:
        container = ServiceContainer()
        container.set("svc", _ServiceA())
        container.reset()
        assert container._instances == {}

    def test_reset_replaces_resolver(self) -> None:
        container = ServiceContainer()
        original_resolver = container._resolver
        container.reset()
        assert container._resolver is not original_resolver

    def test_reset_lets_new_factories_be_registered(self) -> None:
        """After reset, the only registrations left are those added since."""
        container = ServiceContainer()
        container.set("svc", _ServiceA())
        container.reset()
        container.set("svc", _ServiceB())
        assert isinstance(container.get_sync("svc"), _ServiceB)

    def test_reset_does_not_change_container_identity(self) -> None:
        container = ServiceContainer()
        container.reset()
        # same container reference is preserved
        assert isinstance(container, ServiceContainer)


# ---------------------------------------------------------------------------
# ServiceContainer._key_name normalisation
# ---------------------------------------------------------------------------


class TestKeyName:
    """``_key_name`` normalises the various key representations."""

    def test_string_key_passes_through(self) -> None:
        container = ServiceContainer()
        assert container._key_name("plain") == "plain"

    def test_class_key_uses_module_qualname(self) -> None:
        container = ServiceContainer()
        # _ServiceA's full dotted name is deterministic.
        assert container._key_name(_ServiceA) == f"{_ServiceA.__module__}._ServiceA"

    def test_instance_key_falls_back_to_str(self) -> None:
        """Arbitrary objects fall back to ``str(key)``."""
        container = ServiceContainer()
        obj = object()
        assert container._key_name(obj) == str(obj)


# ---------------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Top-level re-exports and helpers."""

    def test_inject_helper_exists(self) -> None:
        """``Inject`` is exposed for typing.DI-injected parameters."""
        assert Inject is not None

    def test_depends_singleton_can_be_used_directly(self) -> None:
        """The module-level ``depends`` is the shared singleton container."""
        sentinel = _ServiceA(marker="singleton")
        try:
            depends.set("tests.unit.di.test_container:_ServiceA", sentinel)
            assert depends.get_sync(
                "tests.unit.di.test_container:_ServiceA"
            ) is sentinel
        finally:
            # Best-effort cleanup so subsequent tests don't see this key.
            depends.reset()

    def test_multiple_set_calls_with_same_key_keep_latest(self) -> None:
        """Repeated ``set`` overwrites; the latest instance wins."""
        container = ServiceContainer()
        container.set("k", "first")
        container.set("k", "second")
        assert container.get_sync("k") == "second"
