from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import importlib.util

import pytest

from session_buddy.utils.database_tools import (
    batch_database_operation,
    check_database_available,
    get_database_stats,
    require_reflection_database,
    safe_database_operation,
    safe_database_operation_with_message,
)
from session_buddy.utils.error_management import DatabaseUnavailableError


@pytest.mark.asyncio
async def test_require_reflection_database_returns_db(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    result = await require_reflection_database()

    assert result is fake_db


@pytest.mark.asyncio
async def test_require_reflection_database_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    with pytest.raises(DatabaseUnavailableError, match="Reflection database not available"):
        await require_reflection_database()


@pytest.mark.asyncio
async def test_safe_database_operation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(db: object) -> str:
        assert db is fake_db
        return "ok"

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    result = await safe_database_operation(operation, "Search reflections")

    assert result == "ok"


@pytest.mark.asyncio
async def test_safe_database_operation_reraises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    async def operation(_db: object) -> str:
        return "unreachable"

    with pytest.raises(DatabaseUnavailableError):
        await safe_database_operation(operation, "Search reflections")


@pytest.mark.asyncio
async def test_safe_database_operation_reraises_other_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )
    monkeypatch.setattr(
        "session_buddy.utils.database_tools._get_logger",
        lambda: logger,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await safe_database_operation(operation, "Search reflections")

    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_string_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> str:
        return "done"

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    result = await safe_database_operation_with_message(operation, "Search reflections")

    assert result == "done"


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_non_string_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> dict[str, int]:
        return {"count": 2}

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    result = await safe_database_operation_with_message(operation, "Search reflections")

    assert result == "{'count': 2}"


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    async def operation(_db: object) -> str:
        return "unreachable"

    result = await safe_database_operation_with_message(operation, "Search reflections")

    assert result == "❌ Reflection database not available. Install dependencies: uv sync --extra embeddings"


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_other_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> str:
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )
    monkeypatch.setattr(
        "session_buddy.utils.database_tools._get_logger",
        lambda: logger,
    )

    result = await safe_database_operation_with_message(operation, "Search reflections")

    assert result == "❌ Search reflections failed: boom"
    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_batch_database_operation_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(db: object, item: int) -> str:
        assert db is fake_db
        if item == 2:
            msg = "bad item"
            raise RuntimeError(msg)
        return f"value-{item}"

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )
    monkeypatch.setattr(
        "session_buddy.utils.database_tools._get_logger",
        lambda: logger,
    )

    result = await batch_database_operation([1, 2, 3], operation, batch_size=2)

    assert result == ["value-1", None, "value-3"]
    assert logger.exception.call_count == 1


def test_check_database_available_false_when_reflection_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == "session_buddy.reflection_tools" else object(),
    )

    assert check_database_available() is False


def test_check_database_available_true_when_dependencies_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object(),
    )

    assert check_database_available() is True


def test_check_database_available_handles_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_find_spec(name: str) -> object:
        raise ImportError("boom")

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is False


@pytest.mark.asyncio
async def test_get_database_stats_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDB:
        async def get_stats(self) -> dict[str, int]:
            return {"total_reflections": 3, "total_conversations": 2}

    async def fake_require() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.require_reflection_database",
        fake_require,
    )

    result = await get_database_stats()

    assert result == {
        "total_reflections": 3,
        "total_conversations": 2,
        "available": True,
    }


@pytest.mark.asyncio
async def test_get_database_stats_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_require() -> None:
        raise DatabaseUnavailableError("Reflection database not available")

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.require_reflection_database",
        fake_require,
    )

    result = await get_database_stats()

    assert result == {
        "available": False,
        "error": "Database not available",
        "total_reflections": 0,
        "total_conversations": 0,
    }


@pytest.mark.asyncio
async def test_get_database_stats_generic_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_require() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.require_reflection_database",
        fake_require,
    )
    monkeypatch.setattr(
        "session_buddy.utils.database_tools._get_logger",
        lambda: logger,
    )

    result = await get_database_stats()

    assert result == {
        "available": False,
        "error": "boom",
        "total_reflections": 0,
        "total_conversations": 0,
    }
    logger.exception.assert_called_once()


def test_check_database_available_false_when_duckdb_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util

    def fake_find_spec(name: str) -> object | None:
        if name == "session_buddy.reflection_tools":
            return object()
        if name == "duckdb":
            return None
        return object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is False


def test_check_database_available_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util

    def fake_find_spec(name: str) -> object | None:
        return object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is True


@pytest.mark.asyncio
async def test_get_database_stats_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = SimpleNamespace(get_stats=AsyncMock(return_value={"total_reflections": 7}))

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    result = await get_database_stats()

    assert result == {
        "total_reflections": 7,
        "available": True,
    }


@pytest.mark.asyncio
async def test_get_database_stats_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        fake_resolve,
    )

    result = await get_database_stats()

    assert result == {
        "available": False,
        "error": "Database not available",
        "total_reflections": 0,
        "total_conversations": 0,
    }


@pytest.mark.asyncio
async def test_get_database_stats_other_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return object()

    async def fake_get_stats() -> dict[str, int]:
        msg = "stats failed"
        raise RuntimeError(msg)

    db = SimpleNamespace(get_stats=fake_get_stats)

    async def resolve() -> object:
        return db

    monkeypatch.setattr(
        "session_buddy.utils.database_tools.resolve_reflection_database",
        resolve,
    )
    monkeypatch.setattr(
        "session_buddy.utils.database_tools._get_logger",
        lambda: logger,
    )

    result = await get_database_stats()

    assert result == {
        "available": False,
        "error": "stats failed",
        "total_reflections": 0,
        "total_conversations": 0,
    }
    logger.exception.assert_called_once()
