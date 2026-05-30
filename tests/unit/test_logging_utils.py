"""Tests for logging utilities.

Tests the SessionLogger class and structured logging functionality.
"""

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LOGGING_UTILS_PATH = (
    Path(__file__).resolve().parents[2]
    / "session_buddy"
    / "utils"
    / "logging_utils.py"
)
_LOGGING_UTILS_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.logging_utils",
    _LOGGING_UTILS_PATH,
)
assert _LOGGING_UTILS_SPEC is not None and _LOGGING_UTILS_SPEC.loader is not None

_LOGGING_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "logging.py"
)
_LOGGING_MODULE_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.logging",
    _LOGGING_MODULE_PATH,
)
assert _LOGGING_MODULE_SPEC is not None and _LOGGING_MODULE_SPEC.loader is not None
_LOGGING_MODULE = importlib.util.module_from_spec(_LOGGING_MODULE_SPEC)
sys.modules[_LOGGING_MODULE_SPEC.name] = _LOGGING_MODULE
_LOGGING_MODULE_SPEC.loader.exec_module(_LOGGING_MODULE)

if "session_buddy.utils" not in sys.modules:
    _utils_package = types.ModuleType("session_buddy.utils")
    _utils_package.__path__ = []  # type: ignore[attr-defined]
    _utils_package.logging = _LOGGING_MODULE  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils"] = _utils_package
else:
    setattr(sys.modules["session_buddy.utils"], "logging", _LOGGING_MODULE)

_LOGGING_UTILS_MODULE = importlib.util.module_from_spec(_LOGGING_UTILS_SPEC)
sys.modules[_LOGGING_UTILS_SPEC.name] = _LOGGING_UTILS_MODULE
_LOGGING_UTILS_SPEC.loader.exec_module(_LOGGING_UTILS_MODULE)
SessionLogger = _LOGGING_UTILS_MODULE.SessionLogger


@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """Create temporary log directory for testing."""
    return tmp_path / "logs"


@pytest.fixture
def session_logger(temp_log_dir: Path) -> SessionLogger:
    """Create SessionLogger instance for testing."""
    return SessionLogger(temp_log_dir)


class TestSessionLoggerInitialization:
    """Test SessionLogger initialization and setup."""

    def test_creates_log_directory(self, temp_log_dir: Path) -> None:
        """Test that log directory is created."""
        assert not temp_log_dir.exists()
        SessionLogger(temp_log_dir)
        assert temp_log_dir.exists()
        assert temp_log_dir.is_dir()

    def test_creates_log_file(self, session_logger: SessionLogger) -> None:
        """Test that log file is created with date stamp."""
        assert session_logger.log_file.exists()
        assert session_logger.log_file.name.startswith("session_management_")
        assert session_logger.log_file.name.endswith(".log")

    def test_logger_has_correct_level(self, session_logger: SessionLogger) -> None:
        """Test that logger is configured with INFO level."""
        assert session_logger.logger.level == logging.INFO

    def test_logger_has_file_handler(self, session_logger: SessionLogger) -> None:
        """Test that logger has file handler configured."""
        handlers = session_logger.logger.handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0
        assert file_handlers[0].level == logging.INFO

    def test_logger_has_console_handler(self, session_logger: SessionLogger) -> None:
        """Test that logger has console handler configured."""
        handlers = session_logger.logger.handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) > 0
        assert stream_handlers[0].level == logging.ERROR

    def test_no_duplicate_handlers(self, temp_log_dir: Path) -> None:
        """Test that creating multiple loggers doesn't duplicate handlers."""
        logger1 = SessionLogger(temp_log_dir)
        initial_handler_count = len(logger1.logger.handlers)

        logger2 = SessionLogger(temp_log_dir)
        # Should reuse existing logger, not add more handlers
        assert len(logger2.logger.handlers) == initial_handler_count


class TestSessionLoggerBasicLogging:
    """Test basic logging operations."""

    def test_info_logging(self, session_logger: SessionLogger) -> None:
        """Test info level logging."""
        with patch.object(session_logger.logger, "info") as mock_info:
            session_logger.info("Test message")
            mock_info.assert_called_once_with("Test message")

    def test_warning_logging(self, session_logger: SessionLogger) -> None:
        """Test warning level logging."""
        with patch.object(session_logger.logger, "warning") as mock_warning:
            session_logger.warning("Warning message")
            mock_warning.assert_called_once_with("Warning message")

    def test_error_logging(self, session_logger: SessionLogger) -> None:
        """Test error level logging."""
        with patch.object(session_logger.logger, "error") as mock_error:
            session_logger.error("Error message")
            mock_error.assert_called_once_with("Error message")


class TestSessionLoggerStructuredLogging:
    """Test structured logging with context."""

    def test_info_with_context(self, session_logger: SessionLogger) -> None:
        """Test info logging with structured context."""
        with patch.object(session_logger.logger, "info") as mock_info:
            session_logger.info("Test message", user="alice", action="login")

            call_args = mock_info.call_args[0][0]
            assert "Test message" in call_args
            assert "Context:" in call_args
            assert "user" in call_args
            assert "alice" in call_args
            assert "action" in call_args
            assert "login" in call_args

    def test_warning_with_context(self, session_logger: SessionLogger) -> None:
        """Test warning logging with structured context."""
        with patch.object(session_logger.logger, "warning") as mock_warning:
            session_logger.warning("Rate limit", attempts=5, ip="127.0.0.1")

            call_args = mock_warning.call_args[0][0]
            assert "Rate limit" in call_args
            assert "attempts" in call_args
            assert "5" in call_args

    def test_error_with_context(self, session_logger: SessionLogger) -> None:
        """Test error logging with structured context."""
        with patch.object(session_logger.logger, "error") as mock_error:
            session_logger.error("Database error", table="users", error_code=500)

            call_args = mock_error.call_args[0][0]
            assert "Database error" in call_args
            assert "table" in call_args
            assert "error_code" in call_args

    def test_context_serialization(self, session_logger: SessionLogger) -> None:
        """Test that context is properly JSON serialized."""
        with patch.object(session_logger.logger, "info") as mock_info:
            context = {"key": "value", "number": 42, "nested": {"data": "test"}}
            session_logger.info("Message", **context)

            call_args = mock_info.call_args[0][0]
            # Should contain valid JSON
            assert "Context:" in call_args
            context_str = call_args.split("Context:")[1].strip()
            # Should be valid JSON
            parsed = json.loads(context_str)
            assert parsed == context


class TestSessionLoggerFileOutput:
    """Test actual file logging output."""

    def test_log_written_to_file(self, session_logger: SessionLogger) -> None:
        """Test that log messages are written to file."""
        test_message = "Test log entry"
        session_logger.info(test_message)

        # Read log file
        log_content = session_logger.log_file.read_text()
        assert test_message in log_content

    def test_log_format_structure(self, session_logger: SessionLogger) -> None:
        """Test that log format includes expected components."""
        session_logger.info("Test message")

        log_content = session_logger.log_file.read_text()
        # Should have timestamp, level, function, line number, message
        assert "INFO" in log_content
        assert "|" in log_content  # Separator character

    def test_multiple_log_entries(self, session_logger: SessionLogger) -> None:
        """Test multiple log entries are written correctly."""
        messages = ["Message 1", "Message 2", "Message 3"]
        for msg in messages:
            session_logger.info(msg)

        log_content = session_logger.log_file.read_text()
        for msg in messages:
            assert msg in log_content


class TestSessionLoggerEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_message(self, session_logger: SessionLogger) -> None:
        """Test logging empty message."""
        with patch.object(session_logger.logger, "info") as mock_info:
            session_logger.info("")
            mock_info.assert_called_once_with("")

    def test_none_in_context(self, session_logger: SessionLogger) -> None:
        """Test handling None values in context."""
        with patch.object(session_logger.logger, "info") as mock_info:
            session_logger.info("Message", value=None, other="test")
            call_args = mock_info.call_args[0][0]
            # Should handle None gracefully (JSON serializes to null)
            assert "null" in call_args or "None" in call_args

    def test_special_characters_in_message(self, session_logger: SessionLogger) -> None:
        """Test logging message with special characters."""
        special_msg = "Message with ñ, 中文, and emoji 🚀"
        with patch.object(session_logger.logger, "info") as mock_info:
            session_logger.info(special_msg)
            mock_info.assert_called_once_with(special_msg)

    def test_large_context(self, session_logger: SessionLogger) -> None:
        """Test logging with large context dictionary."""
        large_context = {f"key_{i}": f"value_{i}" for i in range(100)}
        with patch.object(session_logger.logger, "info") as mock_info:
            session_logger.info("Large context test", **large_context)
            # Should complete without error
            assert mock_info.called

    def test_existing_log_directory(self, temp_log_dir: Path) -> None:
        """Test initialization with existing log directory."""
        temp_log_dir.mkdir(parents=True, exist_ok=True)
        logger = SessionLogger(temp_log_dir)
        # Should not raise error, should use existing directory
        assert logger.log_dir.exists()
