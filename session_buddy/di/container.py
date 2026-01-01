from __future__ import annotations

import inspect
import typing as t

from oneiric.core.resolution import Candidate, Resolver

T = t.TypeVar("T")


class Inject[T]:
    """Typing helper to mirror DI-injected parameters."""


class ServiceContainer:
    def __init__(self) -> None:
        self._resolver = Resolver()
        self._instances: dict[str, t.Any] = {}

    def set(self, key: object, instance: t.Any) -> None:
        name = self._key_name(key)
        self._instances[name] = instance
        self._resolver.register(
            Candidate(
                domain="service",
                key=name,
                provider="instance",
                factory=lambda: instance,
            )
        )

    def register_factory(
        self,
        key: object,
        factory: t.Callable[[], t.Any],
        *,
        provider: str | None = None,
    ) -> None:
        name = self._key_name(key)
        self._resolver.register(
            Candidate(domain="service", key=name, provider=provider, factory=factory)
        )

    def get_sync(self, key: object) -> t.Any:
        name = self._key_name(key)
        if name in self._instances:
            return self._instances[name]
        candidate = self._resolver.resolve("service", name)
        if not candidate:
            msg = f"Service not registered: {name}"
            raise KeyError(msg)
        instance = candidate.factory()
        if inspect.isawaitable(instance):
            msg = f"Async factory registered for sync get: {name}"
            raise RuntimeError(msg)
        self._instances[name] = instance
        return instance

    def get(self, key: object) -> t.Any:
        return self.get_sync(key)

    async def get_async(self, key: object) -> t.Any:
        name = self._key_name(key)
        if name in self._instances:
            return self._instances[name]
        candidate = self._resolver.resolve("service", name)
        if not candidate:
            msg = f"Service not registered: {name}"
            raise KeyError(msg)
        instance = candidate.factory()
        if inspect.isawaitable(instance):
            instance = await instance
        self._instances[name] = instance
        return instance

    def reset(self) -> None:
        self._instances.clear()
        self._resolver = Resolver()

    def _key_name(self, key: object) -> str:
        if isinstance(key, str):
            return key
        if hasattr(key, "__module__") and hasattr(key, "__qualname__"):
            return f"{key.__module__}.{key.__qualname__}"
        return str(key)


depends = ServiceContainer()

__all__ = ["Inject", "ServiceContainer", "depends"]
