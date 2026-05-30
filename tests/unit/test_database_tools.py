from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_ERROR_MGMT = types.ModuleType("session_buddy.utils.error_management")


class DatabaseUnavailableError(Exception):
    pass


_ERROR_MGMT.DatabaseUnavailableError = DatabaseUnavailableError
_ERROR_MGMT._get_logger = lambda: MagicMock()
sys.modules.setdefault("session_buddy.utils.error_management", _ERROR_MGMT)

_INSTANCE_MANAGERS = types.ModuleType("session_buddy.utils.instance_managers")
_INSTANCE_MANAGERS.get_reflection_database = lambda: None
sys.modules.setdefault("session_buddy.utils.instance_managers", _INSTANCE_MANAGERS)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "database_tools.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.database_tools", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
database_tools = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.database_tools", database_tools)
_SPEC.loader.exec_module(database_tools)

batch_database_operation = database_tools.batch_database_operation
check_database_available = database_tools.check_database_available
get_database_stats = database_tools.get_database_stats
require_reflection_database = database_tools.require_reflection_database
safe_database_operation = database_tools.safe_database_operation
safe_database_operation_with_message = database_tools.safe_database_operation_with_message


@pytest.mark.asyncio
async def test_require_reflection_database_returns_db(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
        fake_resolve,
    )
    monkeypatch.setattr(
        database_tools,
        "_get_logger",
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
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
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
        database_tools,
        "resolve_reflection_database",
        fake_resolve,
    )
    monkeypatch.setattr(
        database_tools,
        "_get_logger",
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
        database_tools,
        "resolve_reflection_database",
        fake_resolve,
    )
    monkeypatch.setattr(
        database_tools,
        "_get_logger",
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


def test_check_database_available_false_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(name: str) -> object:
        raise ImportError("boom")

    monkeypatch.setattr(importlib.util, "find_spec", boom)

    assert check_database_available() is False


def test_check_database_available_true(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_find_spec(name: str) -> object | None:
        return object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is True


@pytest.mark.asyncio
async def test_get_database_stats_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_stats() -> dict[str, int]:
        return {"total_reflections": 1, "total_conversations": 2}

    fake_db = types.SimpleNamespace(get_stats=get_stats)

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(database_tools, "resolve_reflection_database", fake_resolve)

    stats = await get_database_stats()
    assert stats["available"] is True
    assert stats["total_reflections"] == 1

    async def fake_missing() -> None:
        return None

    monkeypatch.setattr(database_tools, "resolve_reflection_database", fake_missing)
    missing = await get_database_stats()
    assert missing["available"] is False
    assert missing["error"] == "Database not available"


@pytest.mark.asyncio
async def test_get_database_stats_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = types.SimpleNamespace(
        get_stats=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(database_tools, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_tools, "_get_logger", lambda: logger)

    stats = await get_database_stats()

    assert stats["available"] is False
    assert stats["error"] == "boom"
    logger.exception.assert_called_once()
