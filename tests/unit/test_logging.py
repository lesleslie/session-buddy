from __future__ import annotations

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "logging.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.logging", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
logging_module = importlib.util.module_from_spec(_SPEC)
_SESSION_BUDDY_ROOT = Path(__file__).resolve().parents[2] / "session_buddy"
_session_buddy_pkg = types.ModuleType("session_buddy")
_session_buddy_pkg.__path__ = [str(_SESSION_BUDDY_ROOT)]
sys.modules["session_buddy"] = _session_buddy_pkg
sys.modules["session_buddy.utils.logging"] = logging_module
_SPEC.loader.exec_module(logging_module)


def test_safe_json_serialize_handles_serializable_values() -> None:
    result = logging_module._safe_json_serialize({"name": "alice", "count": 3})

    assert json.loads(result) == {"name": "alice", "count": 3}


def test_safe_json_serialize_handles_non_serializable_values() -> None:
    class Unserializable:
        def __str__(self) -> str:
            return "custom-object"

    result = logging_module._safe_json_serialize({"item": Unserializable(), "count": 1})

    assert json.loads(result) == {"item": "custom-object", "count": 1}


def test_safe_json_serialize_falls_back_to_string() -> None:
    class Unserializable:
        pass

    result = logging_module._safe_json_serialize(Unserializable())

    assert json.loads(result).startswith("<")


def test_get_console_handler_skips_file_handlers(tmp_path: Path) -> None:
    logger = logging.getLogger("test_get_console_handler_skips_file_handlers")
    logger.handlers.clear()
    file_handler = logging.FileHandler(tmp_path / "test.log")
    logger.addHandler(file_handler)

    assert logging_module._get_console_handler(logger) is None


def test_get_console_handler_returns_stream_handler() -> None:
    logger = logging.getLogger("test_get_console_handler_returns_stream_handler")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    logger.addHandler(handler)

    assert logging_module._get_console_handler(logger) is handler


def test_get_file_handler_matches_path(tmp_path: Path) -> None:
    logger = logging.getLogger("test_get_file_handler_matches_path")
    logger.handlers.clear()
    log_file = tmp_path / "session.log"
    handler = logging.FileHandler(log_file)
    logger.addHandler(handler)

    assert logging_module._get_file_handler(logger, log_file) is handler


def test_get_file_handler_ignores_handler_errors(tmp_path: Path) -> None:
    logger = logging.getLogger("test_get_file_handler_ignores_handler_errors")
    logger.handlers.clear()
    handler = MagicMock(spec=logging.FileHandler)
    type(handler).baseFilename = property(lambda _self: (_ for _ in ()).throw(RuntimeError("boom")))
    logger.addHandler(handler)

    assert logging_module._get_file_handler(logger, tmp_path / "session.log") is None


def test_replace_file_handlers_removes_only_file_handlers(tmp_path: Path) -> None:
    logger = logging.getLogger("test_replace_file_handlers_removes_only_file_handlers")
    logger.handlers.clear()
    file_handler = logging.FileHandler(tmp_path / "file.log")
    stream_handler = logging.StreamHandler(sys.stderr)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    logging_module._replace_file_handlers(logger, tmp_path / "new.log")

    assert file_handler not in logger.handlers
    assert stream_handler in logger.handlers


def test_resolve_logs_dir_uses_session_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_paths = SimpleNamespace(logs_dir=tmp_path / "logs")

    monkeypatch.setattr(
        logging_module.depends,
        "get_sync",
        lambda _typ: fake_paths,
    )

    result = logging_module._resolve_logs_dir()

    assert result == fake_paths.logs_dir
    assert result.exists()


def test_resolve_logs_dir_falls_back_to_temp_on_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = Path("/nonexistent/home")
    original_mkdir = Path.mkdir

    monkeypatch.setattr(
        logging_module.depends,
        "get_sync",
        lambda _typ: SimpleNamespace(other_dir=fake_home / "other"),
    )
    monkeypatch.setattr(logging_module.Path, "home", lambda: fake_home)
    monkeypatch.setattr(
        logging_module.Path,
        "mkdir",
        lambda self, *args, **kwargs: (
            (_ for _ in ()).throw(PermissionError("denied"))
            if self == fake_home
            else original_mkdir(self, *args, **kwargs)
        ),
    )

    result = logging_module._resolve_logs_dir()

    assert "session-buddy" in str(result)


def test_resolve_logs_dir_falls_back_when_session_paths_missing_logs_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_paths = SimpleNamespace(other_dir=tmp_path / "other")

    monkeypatch.setattr(
        logging_module.depends,
        "get_sync",
        lambda _typ: fake_paths,
    )
    monkeypatch.setattr(logging_module.Path, "home", lambda: tmp_path)

    result = logging_module._resolve_logs_dir()

    assert result == tmp_path / ".claude" / "logs"


def test_get_session_logger_reuses_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = MagicMock(spec=logging_module.SessionLogger)
    monkeypatch.setattr(
        logging_module,
        "get_sync_typed",
        lambda _typ: existing,
    )

    result = logging_module.get_session_logger()

    assert result is existing


def test_get_session_logger_falls_back_on_wrong_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created = MagicMock(spec=logging_module.SessionLogger)
    monkeypatch.setattr(logging_module, "get_sync_typed", lambda _typ: object())
    monkeypatch.setattr(logging_module, "_resolve_logs_dir", lambda: tmp_path)
    monkeypatch.setattr(logging_module, "SessionLogger", lambda log_dir: created)
    set_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(
        logging_module.depends,
        "set",
        lambda key, value: set_calls.append((key, value)),
    )

    result = logging_module.get_session_logger()

    assert result is created
    assert set_calls == [(logging_module.SessionLogger, created)]


def test_get_session_logger_creates_and_registers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    created = MagicMock(spec=logging_module.SessionLogger)
    monkeypatch.setattr(
        logging_module,
        "get_sync_typed",
        lambda _typ: (_ for _ in ()).throw(KeyError("missing")),
    )
    monkeypatch.setattr(
        logging_module,
        "_resolve_logs_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        logging_module,
        "SessionLogger",
        lambda log_dir: created,
    )
    set_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(
        logging_module.depends,
        "set",
        lambda key, value: set_calls.append((key, value)),
    )

    result = logging_module.get_session_logger()

    assert result is created
    assert set_calls == [(logging_module.SessionLogger, created)]


def test_session_logger_initializes_handlers(tmp_path: Path) -> None:
    logger = logging.getLogger("test_session_logger_initializes_handlers")
    logger.handlers.clear()

    original_get_logger = logging_module.logging.getLogger
    monkeypatch_logger = MagicMock(return_value=logger)
    logging_module.logging.getLogger = monkeypatch_logger
    try:
        session_logger = logging_module.SessionLogger(tmp_path)
    finally:
        logging_module.logging.getLogger = original_get_logger

    assert session_logger.log_dir == tmp_path
    assert session_logger.log_file.parent == tmp_path
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)
    assert any(isinstance(handler, logging.FileHandler) for handler in logger.handlers)


def test_session_logger_uses_fallback_dir_on_handler_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logger = logging.getLogger("test_session_logger_uses_fallback_dir_on_handler_error")
    logger.handlers.clear()
    monkeypatch.setattr(logging_module, "_get_console_handler", lambda _logger: None)
    monkeypatch.setattr(logging_module, "_get_file_handler", lambda _logger, _log_file: None)
    real_file_handler = logging_module.logging.FileHandler

    class FakeFileHandler(real_file_handler):
        def __init__(self, path: Path, *args: object, **kwargs: object) -> None:
            if path.parent == tmp_path:
                raise PermissionError("denied")
            super().__init__(path, *args, **kwargs)

    monkeypatch.setattr(logging_module.logging, "FileHandler", FakeFileHandler)

    session_logger = logging_module.SessionLogger(tmp_path)

    assert "session-buddy" in str(session_logger.log_dir)
    assert session_logger.log_file.parent == session_logger.log_dir
    assert any(isinstance(handler, logging.FileHandler) for handler in session_logger.logger.handlers)


def test_session_logger_reuses_existing_file_handler(
    tmp_path: Path,
) -> None:
    logger = logging.getLogger("test_session_logger_reuses_existing_file_handler")
    logger.handlers.clear()
    existing_file_handler = MagicMock(spec=logging.FileHandler)
    existing_file_handler.baseFilename = str(tmp_path / "session_management_20260524.log")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(logging_module, "_get_console_handler", lambda _logger: None)
    calls = iter([None, existing_file_handler])
    monkeypatch.setattr(
        logging_module,
        "_get_file_handler",
        lambda _logger, _log_file: next(calls),
    )
    monkeypatch.setattr(logging_module.logging, "getLogger", lambda name: logger)
    try:
        session_logger = logging_module.SessionLogger(tmp_path)
    finally:
        monkeypatch.undo()

    assert session_logger.log_file.parent == tmp_path
    existing_file_handler.setLevel.assert_called_once()
    existing_file_handler.setFormatter.assert_called_once()


def test_session_logger_skips_replace_when_file_handler_exists(
    tmp_path: Path,
) -> None:
    logger = logging.getLogger("test_session_logger_skips_replace_when_file_handler_exists")
    logger.handlers.clear()
    existing_file_handler = MagicMock(spec=logging.FileHandler)
    existing_file_handler.baseFilename = str(tmp_path / "session_management_20260524.log")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(logging_module, "_get_console_handler", lambda _logger: None)
    monkeypatch.setattr(
        logging_module,
        "_get_file_handler",
        lambda _logger, _log_file: existing_file_handler,
    )
    replace_mock = MagicMock()
    monkeypatch.setattr(logging_module, "_replace_file_handlers", replace_mock)
    monkeypatch.setattr(logging_module.logging, "getLogger", lambda name: logger)
    try:
        session_logger = logging_module.SessionLogger(tmp_path)
    finally:
        monkeypatch.undo()

    assert session_logger.log_file.parent == tmp_path
    replace_mock.assert_not_called()
    existing_file_handler.setLevel.assert_called_once()
    existing_file_handler.setFormatter.assert_called_once()


def test_session_logger_context_methods(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session_logger = logging_module.SessionLogger(tmp_path)
    logger = MagicMock(spec=logging.Logger)
    session_logger.logger = logger

    session_logger.info("info", value=1)
    session_logger.warning("warning", value=6)
    session_logger.error("error", value=2)
    session_logger.debug("debug", value=3)
    session_logger.exception("exception", value=4)
    session_logger.critical("critical", value=5)

    logger.info.assert_called_once()
    logger.warning.assert_called_once_with("warning | Context: {\"value\": 6}")
    logger.error.assert_any_call("error | Context: {\"value\": 2}")
    logger.error.assert_any_call("exception | Context: {\"value\": 4}")
    logger.debug.assert_called_once_with("debug | Context: {\"value\": 3}")
    logger.critical.assert_called_once_with("critical | Context: {\"value\": 5}")


def test_session_logger_methods_without_context(tmp_path: Path) -> None:
    session_logger = logging_module.SessionLogger(tmp_path)
    logger = MagicMock(spec=logging.Logger)
    session_logger.logger = logger

    session_logger.info("info")
    session_logger.warning("warning")
    session_logger.error("error")
    session_logger.debug("debug")
    session_logger.exception("exception")
    session_logger.critical("critical")

    logger.info.assert_called_once_with("info")
    logger.warning.assert_called_once_with("warning")
    logger.error.assert_any_call("error")
    logger.error.assert_any_call("exception")
    logger.debug.assert_called_once_with("debug")
    logger.critical.assert_called_once_with("critical")
