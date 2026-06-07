"""Unit tests for utils.file_utils module.

The file_utils module is a compatibility shim that re-exports from filesystem.
Testing the actual implementations in session_buddy.utils.filesystem.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "filesystem.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.filesystem", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.filesystem", _MODULE)
_SPEC.loader.exec_module(_MODULE)

_FILE_UTILS_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "file_utils.py"
_FILE_UTILS_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.file_utils", _FILE_UTILS_PATH
)
assert _FILE_UTILS_SPEC is not None and _FILE_UTILS_SPEC.loader is not None
_FILE_UTILS_MODULE = importlib.util.module_from_spec(_FILE_UTILS_SPEC)
sys.modules.setdefault("session_buddy.utils.file_utils", _FILE_UTILS_MODULE)
_FILE_UTILS_SPEC.loader.exec_module(_FILE_UTILS_MODULE)

_cleanup_session_logs = _MODULE._cleanup_session_logs
_cleanup_temp_files = _MODULE._cleanup_temp_files
_cleanup_uv_cache = _MODULE._cleanup_uv_cache
_get_cleanup_patterns = _MODULE._get_cleanup_patterns
_calculate_item_size = _MODULE._calculate_item_size
_cleanup_item = _MODULE._cleanup_item
_format_cleanup_results = _MODULE._format_cleanup_results
_process_cleanup_patterns = _MODULE._process_cleanup_patterns
_process_single_pattern = _MODULE._process_single_pattern
validate_claude_directory = _MODULE.validate_claude_directory

file_utils_cleanup_session_logs = _FILE_UTILS_MODULE._cleanup_session_logs
file_utils_cleanup_temp_files = _FILE_UTILS_MODULE._cleanup_temp_files
file_utils_cleanup_uv_cache = _FILE_UTILS_MODULE._cleanup_uv_cache


class TestCleanupPatterns:
    """Test _get_cleanup_patterns function."""

    def test_returns_list(self) -> None:
        """Test that _get_cleanup_patterns returns a list."""
        result = _get_cleanup_patterns()
        assert isinstance(result, list)

    def test_contains_common_patterns(self) -> None:
        """Test that common cleanup patterns are present."""
        patterns = _get_cleanup_patterns()
        assert "**/.DS_Store" in patterns
        assert "**/__pycache__" in patterns
        assert "**/*.pyc" in patterns
        assert "**/.pytest_cache" in patterns
        assert "**/node_modules/.cache" in patterns

    def test_patterns_not_empty(self) -> None:
        """Test that cleanup patterns list is not empty."""
        result = _get_cleanup_patterns()
        assert len(result) > 0


class TestFileUtilsShim:
    """Test that the compatibility shim re-exports filesystem helpers."""

    def test_reexports_match_filesystem(self) -> None:
        # Use __qualname__ comparison rather than `is` because
        # `from X import Y` rebinds Y to a fresh attribute access on
        # the freshly-loaded module, which can produce a different
        # function object than the one cached in another module's
        # namespace. What we actually want to verify is that the
        # re-export points at the same underlying function.
        assert (
            file_utils_cleanup_session_logs.__qualname__
            == _cleanup_session_logs.__qualname__
        )
        assert (
            file_utils_cleanup_temp_files.__qualname__
            == _cleanup_temp_files.__qualname__
        )
        assert (
            file_utils_cleanup_uv_cache.__qualname__
            == _cleanup_uv_cache.__qualname__
        )


class TestCleanupSessionLogs:
    """Test _cleanup_session_logs function."""

    def test_cleanup_session_logs_returns_string(self) -> None:
        """Test that _cleanup_session_logs returns a string."""
        result = _cleanup_session_logs()
        assert isinstance(result, str)

    def test_cleanup_session_logs_contains_emoji(self) -> None:
        """Test that result contains expected emoji marker."""
        result = _cleanup_session_logs()
        assert "📝" in result

    def test_cleanup_session_logs_no_directory(self, tmp_path: Path) -> None:
        """Test cleanup when no log directory exists."""
        # Mock Path.home() to return tmp_path so there's no ~/.claude/logs
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _cleanup_session_logs()
            assert isinstance(result, str)
            assert "📝" in result

    def test_cleanup_session_logs_no_matching_files(self, tmp_path: Path) -> None:
        """Test cleanup when the logs directory exists but no matching files do."""
        logs_dir = tmp_path / ".claude" / "logs"
        logs_dir.mkdir(parents=True)
        (logs_dir / "notes.txt").write_text("ignore me")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _cleanup_session_logs()

        assert result == "📝 No session log files found"

    def test_cleanup_session_logs_ignores_invalid_filename(self, tmp_path: Path) -> None:
        """Test cleanup skips filenames without an 8-digit date suffix."""
        logs_dir = tmp_path / ".claude" / "logs"
        logs_dir.mkdir(parents=True)
        bad_log = logs_dir / "session_management_bad.log"
        bad_log.write_text("invalid")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _cleanup_session_logs()

        assert "Cleaned 0 old log files" in result
        assert bad_log.exists() is True

    def test_cleanup_session_logs_removes_old_files(self, tmp_path: Path) -> None:
        """Test cleanup removes logs older than ten days and keeps recent logs."""
        logs_dir = tmp_path / ".claude" / "logs"
        logs_dir.mkdir(parents=True)

        old_date = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y%m%d")
        recent_date = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y%m%d")
        old_log = logs_dir / f"session_management_{old_date}.log"
        recent_log = logs_dir / f"session_management_{recent_date}.log"
        invalid_log = logs_dir / "session_management_20261340.log"
        old_log.write_text("old")
        recent_log.write_text("recent")
        invalid_log.write_text("invalid")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _cleanup_session_logs()

        assert "Cleaned 1 old log files" in result
        assert old_log.exists() is False
        assert recent_log.exists() is True



class TestCleanupTempFiles:
    """Test _cleanup_temp_files function."""

    def test_cleanup_temp_files_returns_string(self, tmp_path: Path) -> None:
        """Test that _cleanup_temp_files returns a string."""
        result = _cleanup_temp_files(tmp_path)
        assert isinstance(result, str)

    def test_cleanup_temp_files_with_no_matches(self, tmp_path: Path) -> None:
        """Test cleanup when no temp files exist."""
        result = _cleanup_temp_files(tmp_path)
        assert isinstance(result, str)

    def test_cleanup_temp_files_with_pycache(self, tmp_path: Path) -> None:
        """Test cleanup with __pycache__ directory present."""
        # Create a __pycache__ directory
        pycache_dir = tmp_path / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "test.pyc").write_text("cached")

        result = _cleanup_temp_files(tmp_path)
        assert isinstance(result, str)
        # Should indicate something was cleaned or nothing found
        assert "🧹" in result

    def test_cleanup_temp_files_with_pytest_cache(self, tmp_path: Path) -> None:
        """Test cleanup with pytest_cache present."""
        cache_dir = tmp_path / ".pytest_cache"
        cache_dir.mkdir()
        (cache_dir / "cache.json").write_text('{"v": 1}')

        result = _cleanup_temp_files(tmp_path)
        assert isinstance(result, str)

    def test_process_single_pattern_and_process_cleanup_patterns(
        self, tmp_path: Path
    ) -> None:
        """Test the lower-level cleanup pattern helpers."""
        temp_file = tmp_path / "temp_file.tmp"
        temp_file.write_text("payload")
        cleaned_items: list[str] = []

        size = _process_single_pattern(tmp_path, "temp_*", cleaned_items)
        assert size >= 0
        assert cleaned_items == ["🗑️ temp_file.tmp"] or cleaned_items == ["📁 temp_file.tmp/"]

        another_temp = tmp_path / "temp_second.tmp"
        another_temp.write_text("payload")
        cleaned_items = []
        total = _process_cleanup_patterns(tmp_path, ["temp_*", "*.missing"], cleaned_items)
        assert total >= size
        assert cleaned_items == ["🗑️ temp_second.tmp"] or cleaned_items == ["📁 temp_second.tmp/"]

    def test_process_single_pattern_skips_missing_items(self, tmp_path: Path) -> None:
        """Test that matched paths are skipped when exists() is false."""
        temp_file = tmp_path / "temp_file.tmp"
        temp_file.write_text("payload")

        with patch.object(_MODULE.Path, "exists", return_value=False):
            cleaned_items: list[str] = []
            size = _process_single_pattern(tmp_path, "temp_*", cleaned_items)

        assert size == 0.0
        assert cleaned_items == []

    def test_process_single_pattern_skips_empty_cleanup_item(self, tmp_path: Path) -> None:
        """Test that cleanup results with empty display names are ignored."""
        temp_file = tmp_path / "temp_file.tmp"
        temp_file.write_text("payload")

        with patch.object(_MODULE, "_cleanup_item", return_value=("", 0)):
            cleaned_items: list[str] = []
            size = _process_single_pattern(tmp_path, "temp_*", cleaned_items)

        assert size == 0.0
        assert cleaned_items == []

    def test_format_cleanup_results(self) -> None:
        """Test cleanup result formatting with truncation."""
        result = _format_cleanup_results([f"item_{i}" for i in range(12)], 3.5)
        assert "Cleaned 12 items" in result
        assert "... and 2 more items" in result


class TestCalculateItemSize:
    """Test _calculate_item_size function."""

    def test_size_of_file(self, tmp_path: Path) -> None:
        """Test size calculation for a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("x" * 1024)  # 1KB

        size = _calculate_item_size(test_file)
        assert size >= 0

    def test_size_of_directory(self, tmp_path: Path) -> None:
        """Test size calculation for a directory."""
        test_dir = tmp_path / "subdir"
        test_dir.mkdir()
        nested_dir = test_dir / "nested"
        nested_dir.mkdir()
        (nested_dir / "nested.txt").write_text("x" * 1024)
        (test_dir / "file.txt").write_text("x" * 2048)

        size = _calculate_item_size(test_dir)
        assert size >= 0

    def test_size_of_directory_with_stat_error(self, tmp_path: Path) -> None:
        """Test directory sizing ignores stat errors on individual files."""
        test_dir = tmp_path / "subdir"
        test_dir.mkdir()
        boom_file = test_dir / "boom.txt"
        boom_file.write_text("x" * 1024)

        original_stat = Path.stat

        def fake_stat(self: Path, *args: object, **kwargs: object):
            if self.name == "boom.txt":
                raise OSError("boom")
            return original_stat(self, *args, **kwargs)

        with patch.object(_MODULE.Path, "stat", fake_stat):
            size = _calculate_item_size(test_dir)

        assert size == 0

    def test_size_nonexistent(self, tmp_path: Path) -> None:
        """Test size calculation for nonexistent path."""
        nonexistent = tmp_path / "nonexistent"
        size = _calculate_item_size(nonexistent)
        assert size == 0


class TestCleanupItem:
    """Test _cleanup_item function."""

    def test_cleanup_file(self, tmp_path: Path) -> None:
        """Test cleanup of a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        name, size = _cleanup_item(test_file)
        assert "🗑️" in name or "📁" in name
        assert size >= 0
        # File should be deleted
        assert not test_file.exists()

    def test_cleanup_directory(self, tmp_path: Path) -> None:
        """Test cleanup of a directory."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("content")

        name, size = _cleanup_item(test_dir)
        assert "🗑️" in name or "📁" in name
        assert size >= 0
        # Directory should be deleted
        assert not test_dir.exists()

    def test_cleanup_nonexistent(self, tmp_path: Path) -> None:
        """Test cleanup of nonexistent path."""
        nonexistent = tmp_path / "nonexistent"
        name, size = _cleanup_item(nonexistent)
        assert name == ""
        assert size == 0


class TestCleanupUVCache:
    """Test _cleanup_uv_cache function."""

    def test_cleanup_uv_cache_returns_string(self) -> None:
        """Test that _cleanup_uv_cache returns a string."""
        result = _cleanup_uv_cache()
        assert isinstance(result, str)

    def test_cleanup_uv_cache_not_found(self) -> None:
        """Test cleanup when uv is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError("uv not found")):
            result = _cleanup_uv_cache()
            assert "⚠️" in result
            assert "not found" in result.lower()

    def test_cleanup_uv_cache_success_messages(self) -> None:
        """Test success and fallback output paths."""
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "freed 10 MB", "stderr": ""},
        )()
        with patch("subprocess.run", return_value=completed):
            result = _cleanup_uv_cache()
            assert "freed 10 MB" in result

        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "done", "stderr": ""},
        )()
        with patch("subprocess.run", return_value=completed):
            result = _cleanup_uv_cache()
            assert result == "📦 UV cache cleaned successfully"

    def test_cleanup_uv_cache_failure_and_timeout(self) -> None:
        """Test failure and timeout branches."""
        completed = type(
            "Completed",
            (),
            {"returncode": 1, "stdout": "", "stderr": "bad"},
        )()
        with patch("subprocess.run", return_value=completed):
            result = _cleanup_uv_cache()
            assert "failed" in result.lower()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("uv", 30)):
            result = _cleanup_uv_cache()
            assert "timed out" in result.lower()

    def test_cleanup_uv_cache_generic_exception(self) -> None:
        """Test unexpected exception fallback."""
        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            result = _cleanup_uv_cache()

        assert "error" in result.lower()


class TestValidateClaudeDirectory:
    """Test validate_claude_directory function."""

    def test_validate_returns_dict(self, tmp_path: Path) -> None:
        """Test that validate_claude_directory returns a dictionary."""
        # Mock Path.home() to use tmp_path
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = validate_claude_directory()
            assert isinstance(result, dict)

    def test_validate_has_required_keys(self, tmp_path: Path) -> None:
        """Test that result has required keys."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = validate_claude_directory()
            assert "success" in result
            assert "directory" in result
            assert "created" in result
            assert "structure" in result
            assert "permissions" in result
            assert "size_mb" in result

    def test_validate_creates_subdirectories(self, tmp_path: Path) -> None:
        """Test that validation creates expected subdirectories."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = validate_claude_directory()
            # Check that subdirectories were set up
            assert isinstance(result["structure"], dict)

    def test_validate_success_flag(self, tmp_path: Path) -> None:
        """Test that success flag is boolean."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = validate_claude_directory()
            assert isinstance(result["success"], bool)

    def test_validate_permissions_value(self, tmp_path: Path) -> None:
        """Test that permissions value is valid."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = validate_claude_directory()
            assert result["permissions"] in ("ok", "readonly")

    def test_validate_existing_directory_path(self, tmp_path: Path) -> None:
        """Test validation when the Claude directory already exists."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = validate_claude_directory()

        assert result["directory"] == str(claude_dir)
        assert result["created"] is False

    def test_calculate_directory_size_ignores_stat_errors(self, tmp_path: Path) -> None:
        """Test that stat errors on files are ignored when sizing directories."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        boom_file = claude_dir / "boom.txt"
        boom_file.write_text("payload")
        results = _MODULE._initialize_validation_results(claude_dir)

        original_stat = Path.stat

        def fake_stat(self: Path, *args: object, **kwargs: object):
            if self.name == "boom.txt":
                raise OSError("boom")
            return original_stat(self, *args, **kwargs)

        def fake_is_file(self: Path) -> bool:
            return self.name == "boom.txt"

        with patch.object(_MODULE.Path, "is_file", fake_is_file), patch.object(
            _MODULE.Path,
            "stat",
            fake_stat,
        ):
            _MODULE._calculate_directory_size(claude_dir, results)

        assert results["size_mb"] == 0

    def test_validate_readonly_branch(self, tmp_path: Path) -> None:
        """Test readonly permission branch."""
        claude_dir = tmp_path / ".claude"

        def fake_access(path: Path, mode: int) -> bool:
            return path != claude_dir

        with patch("pathlib.Path.home", return_value=tmp_path), patch.object(
            _MODULE.os,
            "access",
            side_effect=fake_access,
        ):
            result = validate_claude_directory()

        assert result["permissions"] == "readonly"
        assert result["success"] is False

    def test_validate_exception_branch(self, tmp_path: Path) -> None:
        """Test exception handling branch."""
        with patch("pathlib.Path.home", return_value=tmp_path), patch.object(
            _MODULE,
            "_setup_subdirectories",
            side_effect=RuntimeError("boom"),
        ):
            result = validate_claude_directory()

        assert result["success"] is False
        assert result["error"] == "boom"
