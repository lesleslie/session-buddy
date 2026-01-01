from __future__ import annotations

import typing as t
from types import SimpleNamespace

from session_buddy.adapters import lifecycle
from session_buddy.di.container import depends

if t.TYPE_CHECKING:
    import pytest


async def test_cleanup_storage_adapters_prefers_oneiric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"aclose": False}

    class DummyStorage:
        async def aclose(self) -> None:
            called["aclose"] = True

    def _fake_get_storage_adapter(_: str | None = None) -> DummyStorage:
        return DummyStorage()

    monkeypatch.setattr(
        lifecycle,
        "get_storage_settings",
        lambda: SimpleNamespace(default_backend="file"),
    )
    monkeypatch.setattr(
        "session_buddy.adapters.storage_oneiric.get_storage_adapter",
        _fake_get_storage_adapter,
    )

    await lifecycle.cleanup_storage_adapters()

    assert called["aclose"] is True


def test_cleanup_knowledge_graph_adapter_prefers_oneiric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depends.reset()
    called = {"close": False}

    class DummyKnowledgeGraph:
        def close(self) -> None:
            called["close"] = True

    monkeypatch.setattr(
        "session_buddy.adapters.knowledge_graph_adapter_oneiric.KnowledgeGraphDatabaseAdapterOneiric",
        DummyKnowledgeGraph,
    )

    depends.set(DummyKnowledgeGraph, DummyKnowledgeGraph())
    lifecycle.cleanup_knowledge_graph_adapter()

    assert called["close"] is True


async def test_cleanup_reflection_adapter_prefers_oneiric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depends.reset()
    called = {"close": False}

    class DummyReflection:
        async def close(self) -> None:
            called["close"] = True

    monkeypatch.setattr(
        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric",
        DummyReflection,
    )

    depends.set(DummyReflection, DummyReflection())
    await lifecycle.cleanup_reflection_adapter()

    assert called["close"] is True
