"""Unit tests for ``session_buddy.utils.file_utils`` (re-export shim)."""

from __future__ import annotations

import session_buddy.utils.filesystem as fs_module
import session_buddy.utils.file_utils as fu_module


class TestFileUtilsImports:
    """The three cleanup helpers must be importable from the shim."""

    def test_cleanup_session_logs_importable(self) -> None:
        from session_buddy.utils.file_utils import _cleanup_session_logs

        assert _cleanup_session_logs is not None

    def test_cleanup_temp_files_importable(self) -> None:
        from session_buddy.utils.file_utils import _cleanup_temp_files

        assert _cleanup_temp_files is not None

    def test_cleanup_uv_cache_importable(self) -> None:
        from session_buddy.utils.file_utils import _cleanup_uv_cache

        assert _cleanup_uv_cache is not None

    def test_all_three_importable_via_star(self) -> None:
        import session_buddy.utils.file_utils as mod

        names = {n for n in mod.__all__}
        assert {
            "_cleanup_session_logs",
            "_cleanup_temp_files",
            "_cleanup_uv_cache",
        } <= names


class TestFileUtilsAllExports:
    """``__all__`` is the contract callers and ``from X import *`` rely on."""

    def test_all_contents(self) -> None:
        assert fu_module.__all__ == [
            "_cleanup_session_logs",
            "_cleanup_temp_files",
            "_cleanup_uv_cache",
        ]

    def test_all_is_list(self) -> None:
        assert isinstance(fu_module.__all__, list)

    def test_all_length_matches_imports(self) -> None:
        # Exactly 3 names; no extras, no missing.
        assert len(fu_module.__all__) == 3


class TestFileUtilsReExportIdentity:
    """Shim must re-export the SAME objects as the source module."""

    def test_cleanup_session_logs_is_same_object(self) -> None:
        from session_buddy.utils.file_utils import _cleanup_session_logs

        assert _cleanup_session_logs is fs_module._cleanup_session_logs

    def test_cleanup_temp_files_is_same_object(self) -> None:
        from session_buddy.utils.file_utils import _cleanup_temp_files

        assert _cleanup_temp_files is fs_module._cleanup_temp_files

    def test_cleanup_uv_cache_is_same_object(self) -> None:
        from session_buddy.utils.file_utils import _cleanup_uv_cache

        assert _cleanup_uv_cache is fs_module._cleanup_uv_cache

    def test_module_attribute_resolution_matches(self) -> None:
        """``getattr(shim, name) is getattr(source, name)`` for every name."""
        for name in fu_module.__all__:
            assert getattr(fu_module, name) is getattr(fs_module, name)
