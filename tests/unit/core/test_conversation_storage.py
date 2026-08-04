from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy import settings as settings_module
from session_buddy.core import conversation_storage as storage
from session_buddy.reflection import database as database_module


@pytest.fixture
def manager() -> MagicMock:
    value = MagicMock()
    value.current_project = "test-project"
    value._quality_history = {"test-project": [60, 70, 80, 90, 95, 100]}
    value.session_context = {
        "language": "python",
        "active_files": ["one.py", "two.py"],
        "options": {"strict": True},
        "opaque": object(),
    }
    return value


def _settings(
    *, enabled: bool = True, min_length: int = 1, max_length: int = 50_000
) -> SimpleNamespace:
    return SimpleNamespace(
        enable_conversation_storage=enabled,
        conversation_storage_min_length=min_length,
        conversation_storage_max_length=max_length,
    )


def _database(*, conversation_id: str = "conversation-1") -> MagicMock:
    db = MagicMock()
    db.initialize = AsyncMock()
    db.store_conversation = AsyncMock(return_value=conversation_id)
    db._get_conversation_count = AsyncMock(return_value=0)
    db._execute_query = AsyncMock(return_value=[])
    return db


def _install(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, db: MagicMock
) -> MagicMock:
    factory = MagicMock(return_value=db)
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(database_module, "ReflectionDatabase", factory)
    return factory


def test_get_conversation_logger_happy_and_unhappy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = storage.get_conversation_logger()
    assert isinstance(logger, logging.Logger)
    assert logger.name == "session_buddy.core.conversation_storage"

    get_logger = MagicMock(side_effect=RuntimeError("logging unavailable"))
    monkeypatch.setattr(storage, "logging", SimpleNamespace(getLogger=get_logger))
    with pytest.raises(RuntimeError, match="logging unavailable"):
        storage.get_conversation_logger()


async def test_capture_context_formats_supported_values(
    monkeypatch: pytest.MonkeyPatch, manager: MagicMock
) -> None:
    fixed_time = datetime(2026, 8, 3, 12, 30, tzinfo=UTC)
    monkeypatch.setattr(storage, "utc_now", lambda: fixed_time)

    result = await storage.capture_conversation_context(
        manager,
        checkpoint_type="manual",
        quality_score=98,
        metadata={"is_manual": True, "attempt": 2, "ignored": object()},
    )

    expected_fragments = (
        "# Conversation Context: MANUAL",
        "Project: test-project",
        f"Timestamp: {fixed_time.isoformat()}",
        "Quality Score: 98/100",
        "Recent scores: 70, 80, 90, 95, 100",
        "Trend: improving",
        "language: python",
        "active_files: 2 items",
        "options: 1 keys",
        "is_manual: True",
        "attempt: 2",
    )
    assert all(fragment in result for fragment in expected_fragments)
    assert "opaque:" not in result
    assert "ignored:" not in result


@pytest.mark.parametrize(
    ("scores", "expected_trend"),
    [([75], None), ([90, 75], "Trend: stable")],
)
async def test_capture_context_handles_sparse_optional_data(
    manager: MagicMock,
    scores: list[int],
    expected_trend: str | None,
) -> None:
    manager._quality_history = {"test-project": scores}
    manager.session_context = {}
    result = await storage.capture_conversation_context(manager)
    assert "Quality History" in result
    assert (expected_trend in result) if expected_trend else ("Trend:" not in result)


async def test_capture_context_handles_empty_data_and_inconsistent_history(
    manager: MagicMock,
) -> None:
    manager.current_project = None
    manager._quality_history = {}
    manager.session_context = {}
    result = await storage.capture_conversation_context(
        manager, quality_score=None, metadata=None
    )
    assert "Project: Unknown" in result
    for omitted in ("Quality Score:", "Quality History", "Session Context", "Metadata"):
        assert omitted not in result

    manager.current_project = "test-project"
    history = MagicMock()
    history.get.return_value = True
    history.__getitem__.return_value = []
    manager._quality_history = history
    result = await storage.capture_conversation_context(manager)
    assert "Quality History" not in result


@pytest.mark.parametrize("db_path", [None, "/tmp/conversations.duckdb"])
async def test_store_checkpoint_persists_context_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
    manager: MagicMock,
    db_path: str | None,
) -> None:
    db = _database()
    factory = _install(monkeypatch, _settings(), db)
    capture = AsyncMock(return_value="x" * 120)
    fixed_time = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
    monkeypatch.setattr(storage, "capture_conversation_context", capture)
    monkeypatch.setattr(storage, "utc_now", lambda: fixed_time)

    result = await storage.store_conversation_checkpoint(
        manager,
        checkpoint_type="manual",
        quality_score=91,
        is_manual=True,
        db_path=db_path,
    )

    assert result == {
        "success": True,
        "conversation_id": "conversation-1",
        "error": None,
    }
    factory.assert_called_once_with(*(() if db_path is None else (db_path,)))
    capture.assert_awaited_once_with(
        manager,
        checkpoint_type="manual",
        quality_score=91,
        metadata={"is_manual": True},
    )
    db.store_conversation.assert_awaited_once_with(
        content="x" * 120,
        metadata={
            "project": "test-project",
            "checkpoint_type": "manual",
            "is_manual": True,
            "quality_score": 91,
            "timestamp": fixed_time.isoformat(),
        },
    )
    db.close.assert_called_once_with()


async def test_store_checkpoint_truncates_and_uses_unknown_project(
    monkeypatch: pytest.MonkeyPatch, manager: MagicMock
) -> None:
    manager.current_project = None
    db = _database(conversation_id="truncated-conversation")
    _install(monkeypatch, _settings(max_length=5), db)
    monkeypatch.setattr(
        storage, "capture_conversation_context", AsyncMock(return_value="abcdefghij")
    )

    result = await storage.store_conversation_checkpoint(manager)

    assert result["success"] is True
    kwargs = db.store_conversation.await_args.kwargs
    assert kwargs["content"] == "abcde\n... [truncated]"
    assert kwargs["metadata"]["project"] == "unknown"


async def test_store_checkpoint_guards_disabled_and_short_context(
    monkeypatch: pytest.MonkeyPatch, manager: MagicMock
) -> None:
    disabled_db = _database()
    disabled_factory = _install(monkeypatch, _settings(enabled=False), disabled_db)
    capture = AsyncMock()
    monkeypatch.setattr(storage, "capture_conversation_context", capture)

    disabled = await storage.store_conversation_checkpoint(manager)

    assert disabled["error"] == "Conversation storage disabled"
    capture.assert_not_awaited()
    disabled_factory.assert_not_called()

    short_db = _database()
    short_factory = _install(monkeypatch, _settings(min_length=10), short_db)
    monkeypatch.setattr(
        storage, "capture_conversation_context", AsyncMock(return_value="short")
    )
    short = await storage.store_conversation_checkpoint(manager)

    assert short["error"] == "Conversation text too short (min 10 chars)"
    short_factory.assert_not_called()
    short_db.initialize.assert_not_awaited()


async def test_store_checkpoint_reports_store_and_lock_failures(
    monkeypatch: pytest.MonkeyPatch, manager: MagicMock
) -> None:
    db = _database()
    db.store_conversation.side_effect = RuntimeError("write failed")
    _install(monkeypatch, _settings(), db)
    monkeypatch.setattr(
        storage, "capture_conversation_context", AsyncMock(return_value="x" * 120)
    )

    failed = await storage.store_conversation_checkpoint(manager)

    assert failed["error"] == "write failed"
    assert failed["success"] is False
    db.close.assert_called_once_with()

    logger = MagicMock()
    monkeypatch.setattr(storage, "get_conversation_logger", lambda: logger)
    monkeypatch.setattr(
        settings_module,
        "get_settings",
        MagicMock(side_effect=database_module.DatabaseLockedError("locked")),
    )
    locked = await storage.store_conversation_checkpoint(manager)

    assert locked["error"] == "locked"
    logger.debug.assert_called_once()
    logger.exception.assert_not_called()


async def test_store_checkpoint_reports_capture_failure(
    monkeypatch: pytest.MonkeyPatch, manager: MagicMock
) -> None:
    db = _database()
    _install(monkeypatch, _settings(), db)
    logger = MagicMock()
    monkeypatch.setattr(storage, "get_conversation_logger", lambda: logger)
    monkeypatch.setattr(
        storage,
        "capture_conversation_context",
        AsyncMock(side_effect=ValueError("capture failed")),
    )

    result = await storage.store_conversation_checkpoint(manager)

    assert result["error"] == "capture failed"
    logger.exception.assert_called_once()
    db.initialize.assert_not_awaited()


def _stats_database(
    *,
    total: int,
    embeddings: int | None,
    recent: int | None,
    projects: list[tuple[str | None, ...]],
    is_temp: bool,
) -> MagicMock:
    db = _database()
    db._get_conversation_count.return_value = total
    db.is_temp_db = is_temp
    db._execute_query.return_value = projects
    connection = MagicMock()
    embedding_cursor = MagicMock()
    embedding_cursor.fetchone.return_value = (
        (embeddings,) if embeddings is not None else None
    )
    recent_cursor = MagicMock()
    recent_cursor.fetchone.return_value = (recent,) if recent is not None else None
    connection.execute.side_effect = [embedding_cursor, recent_cursor]
    db._get_conn.return_value = connection
    return db


async def test_get_stats_reads_temp_database(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _stats_database(
        total=4,
        embeddings=3,
        recent=2,
        projects=[("alpha",), (), (None,), ("beta",)],
        is_temp=True,
    )
    factory = MagicMock(return_value=db)
    monkeypatch.setattr(database_module, "ReflectionDatabase", factory)

    result = await storage.get_conversation_stats("/tmp/stats.duckdb")

    assert result == {
        "total_conversations": 4,
        "with_embeddings": 3,
        "embedding_coverage": 75.0,
        "recent_conversations": 2,
        "projects": ["alpha", "beta"],
        "error": None,
    }
    factory.assert_called_once_with("/tmp/stats.duckdb")
    assert db._get_conn.return_value.execute.call_count == 2
    db.close.assert_called_once_with()


async def test_get_stats_handles_missing_rows_and_persistent_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_db = _stats_database(
        total=1, embeddings=None, recent=None, projects=[], is_temp=True
    )
    monkeypatch.setattr(
        database_module, "ReflectionDatabase", MagicMock(return_value=missing_db)
    )
    missing = await storage.get_conversation_stats()

    assert missing["with_embeddings"] == 0
    assert missing["embedding_coverage"] == 0.0
    assert missing["recent_conversations"] == 0

    persistent_db = _stats_database(
        total=2,
        embeddings=1,
        recent=1,
        projects=[("persistent",)],
        is_temp=False,
    )
    loop = MagicMock()
    loop.run_in_executor = AsyncMock(side_effect=lambda _executor, function: function())
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: loop)
    monkeypatch.setattr(
        database_module, "ReflectionDatabase", MagicMock(return_value=persistent_db)
    )
    persistent = await storage.get_conversation_stats()

    assert persistent["embedding_coverage"] == 50.0
    assert persistent["recent_conversations"] == 1
    assert persistent["projects"] == ["persistent"]
    assert loop.run_in_executor.await_count == 2
    persistent_db.close.assert_called_once_with()


async def test_get_stats_handles_empty_database_and_initialization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_db = _stats_database(
        total=0, embeddings=0, recent=0, projects=[], is_temp=True
    )
    empty_factory = MagicMock(return_value=empty_db)
    monkeypatch.setattr(database_module, "ReflectionDatabase", empty_factory)
    empty = await storage.get_conversation_stats()

    assert empty["total_conversations"] == 0
    assert empty["embedding_coverage"] == 0.0
    empty_db._get_conn.assert_not_called()
    empty_db._execute_query.assert_not_awaited()
    empty_factory.assert_called_once_with()
    empty_db.close.assert_called_once_with()

    broken_db = _database()
    broken_db.initialize.side_effect = RuntimeError("initialization failed")
    monkeypatch.setattr(
        database_module, "ReflectionDatabase", MagicMock(return_value=broken_db)
    )
    failed = await storage.get_conversation_stats("/tmp/broken.duckdb")

    assert failed["error"] == "initialization failed"
    assert failed["total_conversations"] == 0
    broken_db.close.assert_not_called()


def test_public_api_smoke_import() -> None:
    assert storage.get_conversation_logger is not None
    assert storage.capture_conversation_context is not None
    assert storage.store_conversation_checkpoint is not None
    assert storage.get_conversation_stats is not None
