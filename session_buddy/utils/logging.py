#!/usr/bin/env python3
"""Structured logging utilities for session management."""

from __future__ import annotations

import json
import logging
import sys
import typing as t
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from acb.depends import depends
from session_buddy.di.constants import LOGS_DIR_KEY


class SessionLogger:
    """Structured logging for session management with context."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = (
            log_dir / f"session_management_{datetime.now().strftime('%Y%m%d')}.log"
        )

        # Configure logger
        self.logger = logging.getLogger("session_management")
        self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
        )

        # Ensure console handler exists with correct settings
        console_handler = _get_console_handler(self.logger)
        if console_handler is None:
            console_handler = logging.StreamHandler(sys.stderr)
            self.logger.addHandler(console_handler)
        console_handler.setLevel(logging.ERROR)
        console_handler.setFormatter(formatter)

        # Ensure file handler for this log directory exists
        file_handler = _get_file_handler(self.logger, self.log_file)
        if file_handler is None:
            file_handler = logging.FileHandler(self.log_file)
            self.logger.addHandler(file_handler)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

    def info(self, message: str, **context: t.Any) -> None:
        """Log info with optional context."""
        if context:
            message = f"{message} | Context: {_safe_json_serialize(context)}"
        self.logger.info(message)

    def warning(self, message: str, **context: t.Any) -> None:
        """Log warning with optional context."""
        if context:
            message = f"{message} | Context: {_safe_json_serialize(context)}"
        self.logger.warning(message)

    def error(self, message: str, **context: t.Any) -> None:
        """Log error with optional context."""
        if context:
            message = f"{message} | Context: {_safe_json_serialize(context)}"
        self.logger.error(message)

    def debug(self, message: str, **context: t.Any) -> None:
        """Log debug with optional context."""
        if context:
            message = f"{message} | Context: {_safe_json_serialize(context)}"
        self.logger.debug(message)

    def exception(self, message: str, **context: t.Any) -> None:
        """Log exception with optional context."""
        if context:
            message = f"{message} | Context: {_safe_json_serialize(context)}"
        self.logger.error(message)

    def critical(self, message: str, **context: t.Any) -> None:
        """Log critical with optional context."""
        if context:
            message = f"{message} | Context: {_safe_json_serialize(context)}"
        self.logger.critical(message)


def get_session_logger() -> SessionLogger:
    """Get the global session logger instance managed by the DI container."""
    from bevy.injection_types import DependencyResolutionError

    with suppress(
        KeyError, AttributeError, RuntimeError, TypeError, DependencyResolutionError
    ):
        # RuntimeError: when adapter requires async
        # TypeError: when bevy has DI confusion between string keys and classes
        # DependencyResolutionError: when dependency not registered in DI container
        logger = depends.get_sync(SessionLogger)
        if isinstance(logger, SessionLogger):
            return logger

    logger = SessionLogger(_resolve_logs_dir())
    depends.set(SessionLogger, logger)
    return logger


def _resolve_logs_dir() -> Path:
    from bevy.injection_types import DependencyResolutionError

    # Try to get SessionPaths from DI (modern ACB pattern)
    with suppress(
        KeyError, AttributeError, RuntimeError, TypeError, DependencyResolutionError
    ):
        from session_buddy.di.config import SessionPaths

        paths = depends.get_sync(SessionPaths)
        if hasattr(paths, "logs_dir") and isinstance(paths.logs_dir, Path):
            paths.logs_dir.mkdir(parents=True, exist_ok=True)
            return paths.logs_dir

    # Fallback: create default logs directory
    logs_dir = Path.home() / ".claude" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _get_console_handler(
    logger: logging.Logger,
) -> logging.StreamHandler[t.TextIO] | None:
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler,
            logging.FileHandler,
        ):
            return handler
    return None


def _get_file_handler(
    logger: logging.Logger,
    log_file: Path,
) -> logging.FileHandler | None:
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if Path(handler.baseFilename) == log_file:
                    return handler
            except Exception:
                continue
    return None


def _safe_json_serialize(obj: t.Any) -> str:
    """Safely serialize objects to JSON, converting non-serializable objects to strings."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        # Convert non-serializable objects to string representation
        if isinstance(obj, dict):
            return json.dumps(
                {
                    # Use explicit None check for better type inference (refurb FURB168)
                    k: str(v)
                    if v is not None and not isinstance(v, (str, int, float, bool))
                    else v
                    for k, v in obj.items()
                },
            )
        return json.dumps(str(obj))
