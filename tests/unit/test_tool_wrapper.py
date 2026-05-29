from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Awaitable, cast

import pytest


def _load_tool_wrapper_module():
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

    error_management = types.ModuleType("session_buddy.utils.error_management")

    class ToolError(Exception):
        pass

    class DatabaseUnavailableError(ToolError):
        pass

    class ValidationError(ToolError):
        pass

    def _get_logger() -> Any:
        import logging

        return logging.getLogger("session_buddy.utils.tool_wrapper")

    def validate_required(value: Any, field_name: str) -> None:
        if value is None or (isinstance(value, str) and not value.strip()) or (
            isinstance(value, (list, dict, set, tuple)) and not value
        ):
            raise ValidationError(f"{field_name} is required")

    def validate_type(value: Any, expected_type: type, field_name: str) -> None:
        if not isinstance(value, expected_type):
            raise ValidationError(
                f"{field_name} must be {expected_type.__name__}, got {type(value).__name__}"
            )

    def validate_range(value: Any, min_val: Any, max_val: Any, field_name: str) -> None:
        if not isinstance(value, (int, float)) or value < min_val or value > max_val:
            raise ValidationError(
                f"{field_name} must be between {min_val} and {max_val}, got {value}"
            )

    error_management.ToolError = ToolError  # type: ignore[attr-defined]
    error_management.DatabaseUnavailableError = DatabaseUnavailableError  # type: ignore[attr-defined]
    error_management.ValidationError = ValidationError  # type: ignore[attr-defined]
    error_management._get_logger = _get_logger  # type: ignore[attr-defined]
    error_management.validate_required = validate_required  # type: ignore[attr-defined]
    error_management.validate_type = validate_type  # type: ignore[attr-defined]
    error_management.validate_range = validate_range  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils.error_management"] = error_management

    database_tools = types.ModuleType("session_buddy.utils.database_tools")

    async def require_reflection_database() -> object:
        raise DatabaseUnavailableError("unconfigured")

    database_tools.require_reflection_database = require_reflection_database  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils.database_tools"] = database_tools

    messages = types.ModuleType("session_buddy.utils.messages")

    class ToolMessages:
        @staticmethod
        def not_available(feature: str, install_hint: str = "") -> str:
            msg = f"❌ {feature} not available"
            if install_hint:
                msg += f". {install_hint}"
            return msg

        @staticmethod
        def operation_failed(operation: str, error: Exception | str) -> str:
            return f"❌ {operation} failed: {error}"

        @staticmethod
        def validation_error(field: str, message: str) -> str:
            return f"❌ Validation error: {field} - {message}"

        @staticmethod
        def empty_results(operation: str, suggestion: str = "") -> str:
            msg = f"ℹ️ No results found for {operation}"
            if suggestion:
                msg += f". {suggestion}"
            return msg

        @staticmethod
        def format_count(count: int, singular: str, plural: str | None = None) -> str:
            word = singular if count == 1 else (plural or f"{singular}s")
            return f"{count} {word}"

        @staticmethod
        def truncate_text(text: str, max_length: int) -> str:
            if len(text) <= max_length:
                return text
            return text[: max_length - 3] + "..."

    messages.ToolMessages = ToolMessages  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils.messages"] = messages

    module_path = repo_root / "session_buddy" / "utils" / "tool_wrapper.py"
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.tool_wrapper",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, error_management


tw, error_management = _load_tool_wrapper_module()
DatabaseUnavailableError = error_management.DatabaseUnavailableError
ValidationError = error_management.ValidationError


class FakeDB:
    async def search_reflections(self, q: str) -> list[dict[str, Any]]:
        return [{"content": q}]


@pytest.mark.asyncio
async def test_execute_database_tool_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(db: FakeDB) -> int:
        res = await db.search_reflections("abc")
        return len(res)

    def fmt(n: int) -> str:
        return f"Found {n}"

    out = await tw.execute_database_tool(op, fmt, "Search")
    assert out == "Found 1"


@pytest.mark.asyncio
async def test_execute_database_tool_validation_and_generic_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    validator = tw.create_validator(required_query="")

    out = await tw.execute_database_tool(
        lambda _db: pytest.fail("should not run"),
        lambda _result: "ok",
        "Search",
        validator=validator,
    )
    assert "validation" in out.lower()

    async def bad_op(_db: FakeDB) -> None:
        raise RuntimeError("boom")

    out = await tw.execute_database_tool(
        bad_op,
        lambda _result: "ok",
        "Search",
    )
    assert "failed" in out.lower()


@pytest.mark.asyncio
async def test_execute_database_tool_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_require_db() -> FakeDB:
        raise DatabaseUnavailableError("db missing")

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    out = await tw.execute_database_tool(
        lambda _db: cast(Awaitable[str], "unused"),
        lambda result: result,
        "Search",
    )
    assert "not available" in out.lower()


@pytest.mark.asyncio
async def test_execute_simple_database_tool_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_require_db() -> FakeDB:
        msg = "db missing"
        raise DatabaseUnavailableError(msg)

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(db: FakeDB) -> str:
        return "ok"

    out = await tw.execute_simple_database_tool(op, "Op")
    assert "not available" in out.lower() or out.startswith("❌")


@pytest.mark.asyncio
async def test_execute_simple_database_tool_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(_db: FakeDB) -> str:
        raise RuntimeError("boom")

    out = await tw.execute_simple_database_tool(op, "Op")
    assert "failed" in out.lower()


@pytest.mark.asyncio
async def test_execute_database_tool_with_dict_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    async def op(db: FakeDB) -> dict[str, int]:
        res = await db.search_reflections("x")
        return {"count": len(res)}

    def validator() -> None:
        return None

    result = await tw.execute_database_tool_with_dict(op, "Search", validator)
    assert result["success"] is True
    assert result["data"]["count"] == 1


@pytest.mark.asyncio
async def test_execute_database_tool_with_dict_validation_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_require_db() -> FakeDB:
        return FakeDB()

    monkeypatch.setattr(tw, "require_reflection_database", fake_require_db)

    validator = tw.create_validator(required_query="")
    result = await tw.execute_database_tool_with_dict(
        lambda _db: pytest.fail("should not run"),
        "Search",
        validator,
    )
    assert result["success"] is False
    assert "validation failed" in result["error"].lower()

    async def bad_op(_db: FakeDB) -> dict[str, int]:
        raise RuntimeError("boom")

    result = await tw.execute_database_tool_with_dict(bad_op, "Search")
    assert result["success"] is False
    assert "failed" in result["error"].lower()

    async def unavailable_db() -> FakeDB:
        raise DatabaseUnavailableError("db unavailable")

    monkeypatch.setattr(tw, "require_reflection_database", unavailable_db)
    result = await tw.execute_database_tool_with_dict(bad_op, "Search")
    assert result["success"] is False
    assert result["error"] == "db unavailable"


@pytest.mark.asyncio
async def test_execute_no_database_tool_formatting() -> None:
    async def op() -> dict[str, str]:
        return {"k": "v"}

    def fmt(d: dict[str, str]) -> str:
        return ",".join(sorted(d.keys()))

    out = await tw.execute_no_database_tool(op, fmt, "Fmt")
    assert out == "k"


@pytest.mark.asyncio
async def test_execute_no_database_tool_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    async def op() -> dict[str, str]:
        raise RuntimeError("boom")

    out = await tw.execute_no_database_tool(op, lambda _data: "ok", "Fmt")
    assert "failed" in out.lower()


def test_create_validator_and_field_helpers() -> None:
    validator = tw.create_validator(
        required_name="alice",
        type_age_int=(3, int),
        range_score=(5, 1, 10),
    )
    validator()

    with pytest.raises(ValidationError):
        tw.create_validator(required_name="")()

    with pytest.raises(ValidationError):
        tw.create_validator(type_age_int=("x", int))()

    with pytest.raises(ValidationError):
        tw.create_validator(range_score=(15, 1, 10))()

    tw._validate_type_field("type_bad", "ignored")
    tw._validate_range_field("range_bad", "ignored")
    tw._validate_type_field("type_age_int", (3,))
    tw._validate_range_field("range_score", (5, 1))
    tw.create_validator(unknown_rule="ignored")()


def test_formatters_cover_all_branches() -> None:
    assert "failed" in tw.format_reflection_result(False, "content").lower()

    plain = tw.format_reflection_result(True, "short content")
    assert "Tags:" not in plain
    assert "Stored:" not in plain

    stored = tw.format_reflection_result(
        True,
        "a" * 120,
        tags=["one", "two"],
        timestamp="2025-01-01 00:00:00",
    )
    assert "Reflection stored successfully" in stored
    assert "Tags:" in stored
    assert "Stored:" in stored
    assert "..." in stored

    empty = tw.format_search_results([], "query")
    assert "no results" in empty.lower()

    detailed = tw.format_search_results(
        [
            {"content": "alpha", "score": 0.95, "timestamp": "now"},
            {"content": "beta"},
        ],
        "query",
        show_details=True,
        max_results=1,
    )
    assert "Found 2 results" in detailed
    assert "alpha" in detailed
    assert "more results" in detailed

    summary_only = tw.format_search_results(
        [{"content": "alpha"}],
        "query",
        show_details=False,
    )
    assert "Found 1 result" in summary_only

    mixed = tw.format_search_results(
        [
            {"content": "alpha", "score": 0.95},
            {"content": "beta", "timestamp": "later"},
            {"content": "gamma"},
        ],
        "query",
        show_details=True,
        max_results=2,
    )
    assert "more results" in mixed

    exact = tw.format_search_results(
        [{"content": "alpha"}, {"content": "beta"}],
        "query",
        show_details=True,
        max_results=2,
    )
    assert "more results" not in exact
