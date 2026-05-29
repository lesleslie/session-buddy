from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_error_management_module():
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

    module_path = repo_root / "session_buddy" / "utils" / "error_management.py"
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.error_management",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


em = _load_error_management_module()
DatabaseUnavailableError = em.DatabaseUnavailableError
ValidationError = em.ValidationError
handle_tool_errors = em.handle_tool_errors
handle_tool_errors_with_result = em.handle_tool_errors_with_result
validate_range = em.validate_range
validate_required = em.validate_required
validate_type = em.validate_type


@pytest.mark.asyncio
async def test_handle_tool_errors_success() -> None:
    async def operation(value: int) -> int:
        return value * 2

    result = await handle_tool_errors(operation, "Multiply", 21)

    assert result == 42


@pytest.mark.asyncio
async def test_handle_tool_errors_expected_failures() -> None:
    async def db_failure() -> None:
        raise DatabaseUnavailableError("database offline")

    async def validation_failure() -> None:
        raise ValidationError("invalid input")

    result = await handle_tool_errors(db_failure, "Lookup")
    validation_result = await handle_tool_errors(validation_failure, "Lookup")

    assert result == "❌ database offline"
    assert validation_result == "❌ Lookup validation failed: invalid input"


@pytest.mark.asyncio
async def test_handle_tool_errors_generic_failure_logs_and_formats() -> None:
    async def boom() -> None:
        raise RuntimeError("boom")

    result = await handle_tool_errors(boom, "Search")

    assert result == "❌ Search failed: boom"


@pytest.mark.asyncio
async def test_handle_tool_errors_with_result_branches() -> None:
    async def operation(value: int) -> int:
        return value + 1

    async def db_failure() -> None:
        raise DatabaseUnavailableError("database offline")

    async def validation_failure() -> None:
        raise ValidationError("invalid input")

    async def boom() -> None:
        raise RuntimeError("boom")

    success = await handle_tool_errors_with_result(operation, "Add", 9)
    db_result = await handle_tool_errors_with_result(db_failure, "Lookup")
    validation_result = await handle_tool_errors_with_result(
        validation_failure,
        "Lookup",
    )
    generic_result = await handle_tool_errors_with_result(boom, "Lookup")

    assert success == {"success": True, "data": 10}
    assert db_result == {"success": False, "error": "database offline"}
    assert validation_result == {
        "success": False,
        "error": "Lookup validation failed: invalid input",
    }
    assert generic_result == {"success": False, "error": "Lookup failed: boom"}


def test_validate_required_branches() -> None:
    with pytest.raises(ValidationError, match="name is required"):
        validate_required(None, "name")

    for value in ["", "   ", [], {}, set(), ()]:
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_required(value, "field")

    validate_required("ok", "field")
    validate_required([1], "field")


def test_validate_type_branches() -> None:
    with pytest.raises(ValidationError, match="must be str, got int"):
        validate_type(123, str, "field")

    validate_type("123", str, "field")


def test_validate_range_branches() -> None:
    with pytest.raises(ValidationError, match="must be a number"):
        validate_range("bad", 0, 10, "score")

    with pytest.raises(ValidationError, match="must be between 0 and 10, got -1"):
        validate_range(-1, 0, 10, "score")

    with pytest.raises(ValidationError, match="must be between 0 and 10, got 11"):
        validate_range(11, 0, 10, "score")

    validate_range(5, 0, 10, "score")
