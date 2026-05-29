from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_error_management_module():
    module_path = (
        Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "error_management.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.error_management", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


em = _load_error_management_module()


def test_get_logger_returns_module_logger() -> None:
    logger = em._get_logger()
    assert logger.name == em.__name__


@pytest.mark.asyncio
async def test_handle_tool_errors_success() -> None:
    async def double(value: int) -> int:
        return value * 2

    result = await em.handle_tool_errors(double, "Multiply", 5)

    assert result == 10


@pytest.mark.asyncio
async def test_handle_tool_errors_database_unavailable() -> None:
    async def boom() -> None:
        raise em.DatabaseUnavailableError("db offline")

    result = await em.handle_tool_errors(boom, "Search")

    assert result == "❌ db offline"


@pytest.mark.asyncio
async def test_handle_tool_errors_validation_error() -> None:
    async def boom() -> None:
        raise em.ValidationError("bad input")

    result = await em.handle_tool_errors(boom, "Search")

    assert result == "❌ Search validation failed: bad input"


@pytest.mark.asyncio
async def test_handle_tool_errors_logs_generic_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_logger = SimpleNamespace(exception=lambda *_args, **_kwargs: None)
    calls: list[str] = []

    def fake_exception(message: str) -> None:
        calls.append(message)

    fake_logger = SimpleNamespace(exception=fake_exception)
    monkeypatch.setattr(em, "_get_logger", lambda: fake_logger)

    async def boom() -> None:
        raise RuntimeError("boom")

    result = await em.handle_tool_errors(boom, "Search")
    structured = await em.handle_tool_errors_with_result(boom, "Search")

    assert result == "❌ Search failed: boom"
    assert structured == {"success": False, "error": "Search failed: boom"}
    assert calls == ["Error in Search: boom", "Error in Search: boom"]


@pytest.mark.asyncio
async def test_handle_tool_errors_with_result_success() -> None:
    async def payload() -> dict[str, str]:
        return {"status": "ok"}

    result = await em.handle_tool_errors_with_result(payload, "Fetch")

    assert result == {"success": True, "data": {"status": "ok"}}


@pytest.mark.asyncio
async def test_handle_tool_errors_with_result_database_unavailable() -> None:
    async def boom() -> None:
        raise em.DatabaseUnavailableError("db offline")

    result = await em.handle_tool_errors_with_result(boom, "Fetch")

    assert result == {"success": False, "error": "db offline"}


@pytest.mark.asyncio
async def test_handle_tool_errors_with_result_validation_error() -> None:
    async def boom() -> None:
        raise em.ValidationError("bad input")

    result = await em.handle_tool_errors_with_result(boom, "Fetch")

    assert result == {
        "success": False,
        "error": "Fetch validation failed: bad input",
    }


def test_validate_required_accepts_non_empty_values() -> None:
    em.validate_required("value", "field")
    em.validate_required([1], "field")
    em.validate_required({"key": "value"}, "field")
    em.validate_required((1,), "field")


@pytest.mark.parametrize(
    ("value", "field_name", "message"),
    [
        (None, "name", "name is required"),
        ("   ", "name", "name cannot be empty"),
        ([], "items", "items cannot be empty"),
        ({}, "mapping", "mapping cannot be empty"),
        (set(), "choices", "choices cannot be empty"),
        ((), "tuple", "tuple cannot be empty"),
    ],
)
def test_validate_required_rejects_missing_values(
    value: object, field_name: str, message: str
) -> None:
    with pytest.raises(em.ValidationError, match=message):
        em.validate_required(value, field_name)


def test_validate_type_accepts_and_rejects_values() -> None:
    em.validate_type("value", str, "field")

    with pytest.raises(em.ValidationError, match="field must be str, got int"):
        em.validate_type(1, str, "field")


def test_validate_range_accepts_and_rejects_values() -> None:
    em.validate_range(1, 0, 2, "score")
    em.validate_range(0, 0, 2, "score")
    em.validate_range(2, 0, 2, "score")

    with pytest.raises(em.ValidationError, match="score must be a number"):
        em.validate_range("high", 0, 2, "score")

    with pytest.raises(
        em.ValidationError, match="score must be between 0 and 2, got 3"
    ):
        em.validate_range(3, 0, 2, "score")
