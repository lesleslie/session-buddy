"""Tests for session_buddy.utils.logging.

Covers the SessionLogger and its helpers: the safe JSON serializer for
non-JSON-serializable values, the file/console handler detection and
replacement helpers, the logs-directory resolution with permission-
error fallback, the get_session_logger factory, and the SessionLogger
class itself (initialization, handler reuse, fallback on handler error).

NOTE: Earlier revisions imported the module via
``importlib.util.spec_from_file_location`` which bypassed coverage
hooks. Normal imports let pytest-cov track the executed lines.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from session_buddy.utils import logging as logging_module
from session_buddy.utils.logging import SessionLogger


# ---------------------------------------------------------------------------
# _safe_json_serialize
# ---------------------------------------------------------------------------


class TestSafeJsonSerialize:
    def test_serializable_values(self) -> None:
        result = logging_module._safe_json_serialize({"name": "alice", "count": 3})
        assert json.loads(result) == {"name": "alice", "count": 3}

    def test_non_serializable_falls_back_to_str(self) -> None:
        class Unserializable:
            def __str__(self) -> str:
                return "custom-object"

        result = logging_module._safe_json_serialize(
            {"item": Unserializable(), "count": 1}
        )
        assert json.loads(result) == {"item": "custom-object", "count": 1}

    def test_object_without_str_falls_back_to_repr(self) -> None:
        class Unserializable:
            pass

        result = logging_module._safe_json_serialize(Unserializable())
        # Default __repr__ is "<class_name object at 0x...>"
        assert json.loads(result).startswith("<")


# ---------------------------------------------------------------------------
# Handler helpers
# ---------------------------------------------------------------------------


class TestGetConsoleHandler:
    def test_skips_file_handlers(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_skips_file_handlers")
        logger.handlers.clear()
        file_handler = logging.FileHandler(tmp_path / "test.log")
        logger.addHandler(file_handler)

        assert logging_module._get_console_handler(logger) is None

    def test_returns_stream_handler(self) -> None:
        logger = logging.getLogger("test_returns_stream_handler")
        logger.handlers.clear()
        handler = logging.StreamHandler(sys.stderr)
        logger.addHandler(handler)

        assert logging_module._get_console_handler(logger) is handler


class TestGetFileHandler:
    def test_matches_path(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_matches_path")
        logger.handlers.clear()
        log_file = tmp_path / "session.log"
        handler = logging.FileHandler(log_file)
        logger.addHandler(handler)

        assert logging_module._get_file_handler(logger, log_file) is handler

    def test_ignores_handler_errors(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_ignores_handler_errors")
        logger.handlers.clear()
        handler = MagicMock(spec=logging.FileHandler)
        # baseFilename access raises RuntimeError — get_file_handler catches it.
        type(handler).baseFilename = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        logger.addHandler(handler)

        assert logging_module._get_file_handler(logger, tmp_path / "session.log") is None


class TestReplaceFileHandlers:
    def test_removes_only_file_handlers(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_replace_only_file")
        logger.handlers.clear()
        file_handler = logging.FileHandler(tmp_path / "file.log")
        stream_handler = logging.StreamHandler(sys.stderr)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        logging_module._replace_file_handlers(logger, tmp_path / "new.log")

        assert file_handler not in logger.handlers
        assert stream_handler in logger.handlers


# ---------------------------------------------------------------------------
# _resolve_logs_dir
# ---------------------------------------------------------------------------


class TestResolveLogsDir:
    def test_uses_session_paths(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake_paths = SimpleNamespace(logs_dir=tmp_path / "logs")
        monkeypatch.setattr(logging_module.depends, "get_sync", lambda _typ: fake_paths)

        result = logging_module._resolve_logs_dir()
        assert result == fake_paths.logs_dir
        assert result.exists()

    def test_falls_back_on_permission_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test_falls_back_when_logs_dir_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_paths = SimpleNamespace(other_dir=tmp_path / "other")
        monkeypatch.setattr(logging_module.depends, "get_sync", lambda _typ: fake_paths)
        monkeypatch.setattr(logging_module.Path, "home", lambda: tmp_path)

        result = logging_module._resolve_logs_dir()
        assert result == tmp_path / ".claude" / "logs"


# ---------------------------------------------------------------------------
# get_session_logger factory
# ---------------------------------------------------------------------------


class TestGetSessionLogger:
    def test_reuses_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        existing = MagicMock(spec=SessionLogger)
        monkeypatch.setattr(logging_module, "get_sync_typed", lambda _typ: existing)

        result = logging_module.get_session_logger()
        assert result is existing

    def test_falls_back_on_wrong_type(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        created = MagicMock(spec=SessionLogger)
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
        # The set call uses the patched SessionLogger (a lambda), so the
        # key in the captured tuple is the lambda, not the original class.
        assert len(set_calls) == 1
        assert set_calls[0][1] is created

    def test_creates_and_registers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        created = MagicMock(spec=SessionLogger)
        monkeypatch.setattr(
            logging_module,
            "get_sync_typed",
            lambda _typ: (_ for _ in ()).throw(KeyError("missing")),
        )
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
        assert len(set_calls) == 1
        assert set_calls[0][1] is created


# ---------------------------------------------------------------------------
# SessionLogger class
# ---------------------------------------------------------------------------


class TestSessionLogger:
    def test_initializes_handlers(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_session_logger_init")
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
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)

    def test_fallback_dir_on_handler_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        logger = logging.getLogger("test_fallback_on_handler_error")
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
        assert any(isinstance(h, logging.FileHandler) for h in session_logger.logger.handlers)

    def test_reuses_existing_file_handler(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_reuses_existing")
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

    def test_skips_replace_when_file_handler_exists(self, tmp_path: Path) -> None:
        logger = logging.getLogger("test_skips_replace")
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

    def test_context_methods(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
        logger.warning.assert_called_once_with('warning | Context: {"value": 6}')
        logger.error.assert_any_call('error | Context: {"value": 2}')
        logger.error.assert_any_call('exception | Context: {"value": 4}')
        logger.debug.assert_called_once_with('debug | Context: {"value": 3}')
        logger.critical.assert_called_once_with('critical | Context: {"value": 5}')

    def test_methods_without_context(self, tmp_path: Path) -> None:
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
