"""Tests for the database helpers module.

NOTE: ``session_buddy.utils.database_helpers`` was renamed to
``session_buddy.utils.database_tools`` in commit 9afd2db7 ("Update config,
core, deps, docs, tests"). The functional surface is identical — every
function that lived in ``database_helpers`` (``require_reflection_database``,
``safe_database_operation``, ``safe_database_operation_with_message``,
``batch_database_operation``, ``check_database_available``,
``get_database_stats``) now lives in ``database_tools``. These tests import
from the current location so they exercise the live code path; once the old
``database_helpers`` import path is removed everywhere the test target should
move with it (see also ``tests/unit/test_database_tools.py``).

The tests are written defensively against the real module's runtime import
graph so they never permanently replace ``session_buddy.utils`` /
``error_management`` / ``instance_managers`` in ``sys.modules`` — that pattern
previously broke downstream tests that needed ``ValidationError`` from the
real ``error_management`` package.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module-loading harness
# ---------------------------------------------------------------------------

# The current canonical home of the helpers is database_tools.py (the former
# database_helpers.py). Loading it via importlib.util keeps the test isolated
# from the heavyweight package-init graph that real ``session_buddy.utils``
# imports pull in.
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "session_buddy"
    / "utils"
    / "database_tools.py"
)
_MODULE_NAME = "session_buddy.utils.database_tools"  # historical = database_helpers


@pytest.fixture(scope="module", autouse=True)
def _isolated_database_tools_module() -> types.ModuleType:
    """Install lightweight stubs and load database_tools.py in isolation.

    Returns the loaded module so individual tests can reach symbols not
    re-exported on the test module's namespace.
    """

    saved_modules: dict[str, types.ModuleType | None] = {
        name: sys.modules.get(name)
        for name in (
            "session_buddy.utils",
            "session_buddy.utils.error_management",
            "session_buddy.utils.instance_managers",
            _MODULE_NAME,
        )
    }

    utils_pkg = types.ModuleType("session_buddy.utils")
    utils_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils"] = utils_pkg

    error_mgmt = types.ModuleType("session_buddy.utils.error_management")

    class _DatabaseUnavailableError(Exception):
        pass

    error_mgmt.DatabaseUnavailableError = _DatabaseUnavailableError
    error_mgmt._get_logger = lambda: MagicMock()
    sys.modules["session_buddy.utils.error_management"] = error_mgmt

    instance_managers = types.ModuleType("session_buddy.utils.instance_managers")
    instance_managers.get_reflection_database = lambda: None
    sys.modules["session_buddy.utils.instance_managers"] = instance_managers

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
    if spec is None or spec.loader is None:
        msg = f"could not load spec for {_MODULE_NAME} from {_MODULE_PATH}"
        pytest.fail(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)

    # Re-export on the test module namespace for ergonomic access in tests.
    current = sys.modules[__name__]
    current.database_helpers = module  # historical alias
    current.database_tools = module
    current.batch_database_operation = module.batch_database_operation
    current.check_database_available = module.check_database_available
    current.get_database_stats = module.get_database_stats
    current.require_reflection_database = module.require_reflection_database
    current.safe_database_operation = module.safe_database_operation
    current.safe_database_operation_with_message = (
        module.safe_database_operation_with_message
    )
    current.DatabaseUnavailableError = _DatabaseUnavailableError

    try:
        yield module
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


# ---------------------------------------------------------------------------
# require_reflection_database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_reflection_database_returns_resolved_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await require_reflection_database()

    assert result is fake_db


@pytest.mark.asyncio
async def test_require_reflection_database_raises_helpful_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    with pytest.raises(DatabaseUnavailableError) as exc_info:
        await require_reflection_database()

    message = str(exc_info.value)
    # The error message must point the operator at the install path so they
    # can self-recover without reading source.
    assert "Reflection database not available" in message
    assert "uv sync" in message
    assert "--extra embeddings" in message


@pytest.mark.asyncio
async def test_require_reflection_database_raises_falsy_check_not_just_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``if not db`` must catch any falsy resolver result, not only ``None``."""

    async def fake_resolve() -> int:
        return 0

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    with pytest.raises(DatabaseUnavailableError):
        await require_reflection_database()


# ---------------------------------------------------------------------------
# safe_database_operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_database_operation_returns_operation_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(db: object) -> str:
        assert db is fake_db
        return "ok"

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await safe_database_operation(operation, "Search reflections")

    assert result == "ok"


@pytest.mark.asyncio
async def test_safe_database_operation_reraises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    async def operation(_db: object) -> str:
        return "unreachable"

    with pytest.raises(DatabaseUnavailableError):
        await safe_database_operation(operation, "Search reflections")


@pytest.mark.asyncio
async def test_safe_database_operation_reraises_other_exceptions_after_logging(
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

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_helpers, "_get_logger", lambda: logger)

    with pytest.raises(RuntimeError, match="boom"):
        await safe_database_operation(operation, "Search reflections")

    logger.exception.assert_called_once()
    # First positional arg of the logger call carries the formatted prefix.
    logged = logger.exception.call_args.args[0]
    assert "Search reflections" in logged


@pytest.mark.asyncio
async def test_safe_database_operation_default_error_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_helpers, "_get_logger", lambda: logger)

    with pytest.raises(RuntimeError):
        await safe_database_operation(operation)

    logged = logger.exception.call_args.args[0]
    # When no custom message is supplied, the default "Database operation"
    # label must appear in the log entry.
    assert "Database operation" in logged


# ---------------------------------------------------------------------------
# safe_database_operation_with_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_returns_string_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> str:
        return "raw output"

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await safe_database_operation_with_message(operation, "Search reflections")

    assert result == "raw output"


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_stringifies_non_string_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> dict[str, int]:
        return {"count": 7}

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await safe_database_operation_with_message(operation, "Search reflections")

    # str(dict) produces Python's repr-style string. Confirm both that the
    # type was coerced and that the keys/values made it through.
    assert isinstance(result, str)
    assert "count" in result
    assert "7" in result


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_returns_failure_string_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    async def operation(_db: object) -> str:
        return "unreachable"

    result = await safe_database_operation_with_message(operation, "Search reflections")

    # The ❌ prefix is part of the contract: callers parse it visually.
    assert result.startswith("❌")
    assert "Reflection database not available" in result


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_returns_failure_string_on_exception(
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

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_helpers, "_get_logger", lambda: logger)

    result = await safe_database_operation_with_message(operation, "Search reflections")

    assert result == "❌ Search reflections failed: boom"
    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_safe_database_operation_with_message_default_error_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_helpers, "_get_logger", lambda: logger)

    result = await safe_database_operation_with_message(operation)

    # The default error prefix is "Database operation".
    assert result == "❌ Database operation failed: kaboom"


# ---------------------------------------------------------------------------
# batch_database_operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_database_operation_processes_all_items_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(db: object, item: int) -> int:
        assert db is fake_db
        return item * 10

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await batch_database_operation([1, 2, 3], operation, batch_size=2)

    assert result == [10, 20, 30]


@pytest.mark.asyncio
async def test_batch_database_operation_replaces_failing_items_with_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object, item: int) -> str:
        if item == 2:
            msg = "bad item"
            raise RuntimeError(msg)
        return f"value-{item}"

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_helpers, "_get_logger", lambda: logger)

    result = await batch_database_operation([1, 2, 3], operation, batch_size=2)

    # Output preserves input ordering and pads the failing slot with None.
    assert result == ["value-1", None, "value-3"]
    # Exactly one log line for the single failing item.
    assert logger.exception.call_count == 1


@pytest.mark.asyncio
async def test_batch_database_operation_empty_input_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object, _item: object) -> str:
        return "never called"

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await batch_database_operation([], operation)

    assert result == []


@pytest.mark.asyncio
async def test_batch_database_operation_single_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object, item: str) -> str:
        return item.upper()

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await batch_database_operation(["hello"], operation)

    assert result == ["HELLO"]


@pytest.mark.asyncio
async def test_batch_database_operation_propagates_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    async def operation(_db: object, _item: object) -> str:
        return "unreachable"

    with pytest.raises(DatabaseUnavailableError):
        await batch_database_operation([1, 2], operation)


@pytest.mark.asyncio
async def test_batch_database_operation_respects_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """batch_size=1 with 3 items still produces 3 results in order."""
    fake_db = object()
    seen_batches: list[int] = []

    async def fake_resolve() -> object:
        return fake_db

    async def operation(_db: object, item: int) -> int:
        seen_batches.append(item)
        return item

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    result = await batch_database_operation([10, 20, 30], operation, batch_size=1)

    assert result == [10, 20, 30]
    assert seen_batches == [10, 20, 30]


# ---------------------------------------------------------------------------
# check_database_available
# ---------------------------------------------------------------------------


def test_check_database_available_false_when_reflection_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_find_spec(name: str) -> object | None:
        return None if name == "session_buddy.reflection_tools" else object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is False


def test_check_database_available_false_when_duckdb_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_find_spec(name: str) -> object | None:
        # Both packages must be present; reflection_tools present, duckdb absent.
        if name == "duckdb":
            return None
        return object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is False


def test_check_database_available_false_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(name: str) -> object:
        raise ImportError("boom")

    monkeypatch.setattr(importlib.util, "find_spec", boom)

    assert check_database_available() is False


def test_check_database_available_true_when_both_specs_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_find_spec(name: str) -> object:
        return object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert check_database_available() is True


# ---------------------------------------------------------------------------
# get_database_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_database_stats_returns_db_stats_with_available_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_stats() -> dict[str, int]:
        return {"total_reflections": 5, "total_conversations": 3}

    fake_db = types.SimpleNamespace(get_stats=fake_get_stats)

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    stats = await get_database_stats()

    assert stats["available"] is True
    assert stats["total_reflections"] == 5
    assert stats["total_conversations"] == 3


@pytest.mark.asyncio
async def test_get_database_stats_preserves_existing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_stats() -> dict[str, object]:
        return {"total_reflections": 1, "total_conversations": 0, "custom_metric": "x"}

    fake_db = types.SimpleNamespace(get_stats=fake_get_stats)

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    stats = await get_database_stats()

    # The helper must NOT drop keys returned by the adapter.
    assert stats["available"] is True
    assert stats["custom_metric"] == "x"


@pytest.mark.asyncio
async def test_get_database_stats_returns_fallback_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve() -> None:
        return None

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)

    stats = await get_database_stats()

    assert stats == {
        "available": False,
        "error": "Database not available",
        "total_reflections": 0,
        "total_conversations": 0,
    }


@pytest.mark.asyncio
async def test_get_database_stats_returns_fallback_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = types.SimpleNamespace(
        get_stats=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    logger = MagicMock()
    logger.exception = MagicMock()

    async def fake_resolve() -> object:
        return fake_db

    monkeypatch.setattr(database_helpers, "resolve_reflection_database", fake_resolve)
    monkeypatch.setattr(database_helpers, "_get_logger", lambda: logger)

    stats = await get_database_stats()

    assert stats["available"] is False
    assert stats["error"] == "boom"
    assert stats["total_reflections"] == 0
    assert stats["total_conversations"] == 0
    logger.exception.assert_called_once()