from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from session_buddy import adapters as _adapters_pkg
from session_buddy.adapters import settings as _adapter_settings
from session_buddy.adapters.settings import (
    KnowledgeGraphAdapterSettings,
    ReflectionAdapterSettings,
    StorageAdapterSettings,
    _resolve_data_dir,
    default_session_buckets,
)


def test_resolve_data_dir_with_absolute_path(monkeypatch) -> None:
    fake_settings = SimpleNamespace(data_dir=Path("/var/tmp/session-buddy"))
    # Use the 3-arg form with explicit module reference to avoid pytest's
    # dotted-string resolver (which can fail when other tests in the batch
    # have left module-level state that confuses the path walker).
    monkeypatch.setattr(
        _adapter_settings, "get_settings", lambda: fake_settings
    )

    assert _resolve_data_dir() == Path("/var/tmp/session-buddy")


def test_resolve_data_dir_with_relative_path(monkeypatch) -> None:
    fake_settings = SimpleNamespace(data_dir=Path("relative/data"))
    monkeypatch.setattr(
        _adapter_settings, "get_settings", lambda: fake_settings
    )
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/test"))

    assert _resolve_data_dir() == Path("/Users/test/relative/data")


def test_default_session_buckets() -> None:
    buckets = default_session_buckets(Path("/tmp/data"))

    assert buckets == {
        "sessions": "/tmp/data/sessions",
        "checkpoints": "/tmp/data/checkpoints",
        "handoffs": "/tmp/data/handoffs",
        "test": "/tmp/data/test",
    }


def test_from_settings_builds_adapter_configs(monkeypatch) -> None:
    fake_settings = SimpleNamespace(data_dir=Path("/tmp/session-buddy"))
    monkeypatch.setattr(
        _adapter_settings, "get_settings", lambda: fake_settings
    )

    reflection = ReflectionAdapterSettings.from_settings()
    knowledge = KnowledgeGraphAdapterSettings.from_settings()
    storage = StorageAdapterSettings.from_settings()

    assert reflection.database_path == Path("/tmp/session-buddy/reflection.duckdb")
    assert knowledge.database_path == Path(
        "/tmp/session-buddy/knowledge_graph.duckdb"
    )
    assert storage.local_path == Path("/tmp/session-buddy")
    assert storage.buckets == {
        "sessions": "/tmp/session-buddy/sessions",
        "checkpoints": "/tmp/session-buddy/checkpoints",
        "handoffs": "/tmp/session-buddy/handoffs",
        "test": "/tmp/session-buddy/test",
    }
