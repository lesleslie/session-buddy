"""Unit tests for ``session_buddy.utils.logging_utils`` (re-export shim)."""

from __future__ import annotations

import session_buddy.utils.logging as log_module
import session_buddy.utils.logging_utils as shim_module


class TestLoggingUtilsImports:
    """The two log symbols must be importable from the shim."""

    def test_session_logger_importable(self) -> None:
        from session_buddy.utils.logging_utils import SessionLogger

        assert SessionLogger is not None

    def test_get_session_logger_importable(self) -> None:
        from session_buddy.utils.logging_utils import get_session_logger

        assert get_session_logger is not None

    def test_both_importable_via_star(self) -> None:
        names = set(shim_module.__all__)
        assert {"SessionLogger", "get_session_logger"} <= names


class TestLoggingUtilsAllExports:
    """``__all__`` must match the imports exactly."""

    def test_all_contents(self) -> None:
        assert shim_module.__all__ == [
            "SessionLogger",
            "get_session_logger",
        ]

    def test_all_is_list(self) -> None:
        assert isinstance(shim_module.__all__, list)

    def test_all_length_is_two(self) -> None:
        assert len(shim_module.__all__) == 2


class TestLoggingUtilsReExportIdentity:
    """Shim must re-export the SAME objects as the source module."""

    def test_session_logger_is_same_class(self) -> None:
        from session_buddy.utils.logging_utils import SessionLogger

        assert SessionLogger is log_module.SessionLogger

    def test_get_session_logger_is_same_function(self) -> None:
        from session_buddy.utils.logging_utils import get_session_logger

        assert get_session_logger is log_module.get_session_logger

    def test_module_attribute_resolution_matches(self) -> None:
        """``getattr(shim, name) is getattr(source, name)`` for every name."""
        for name in shim_module.__all__:
            assert getattr(shim_module, name) is getattr(log_module, name)
