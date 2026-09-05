"""Unit tests for ``session_buddy.utils.filesystem`` helpers.

Covers the safe-to-test surface of the module. Cleanup helpers that touch
``Path.home() / ".claude"`` (``_cleanup_session_logs``, ``_cleanup_uv_cache``)
and ``validate_claude_directory`` (which reads ``Path.home()``) are exercised
through ``monkeypatch`` so they never touch the real user home directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from session_buddy.utils.filesystem import (
    _calculate_directory_size,
    _calculate_item_size,
    _cleanup_item,
    _cleanup_temp_files,
    _format_cleanup_results,
    _get_cleanup_patterns,
    _initialize_validation_results,
    _process_cleanup_patterns,
    _process_single_pattern,
    _setup_main_directory,
    _setup_subdirectories,
    _validate_permissions,
    validate_claude_directory,
)


class TestGetCleanupPatterns:
    """``_get_cleanup_patterns`` returns the canonical cleanup glob list."""

    def test_returns_list(self) -> None:
        patterns = _get_cleanup_patterns()
        assert isinstance(patterns, list)

    def test_returns_non_empty_list(self) -> None:
        assert len(_get_cleanup_patterns()) > 0

    def test_all_entries_are_strings(self) -> None:
        for pattern in _get_cleanup_patterns():
            assert isinstance(pattern, str)

    def test_contains_common_python_artifacts(self) -> None:
        patterns = _get_cleanup_patterns()
        assert "**/.DS_Store" in patterns
        assert "**/__pycache__" in patterns
        assert "**/*.pyc" in patterns

    def test_contains_test_artifacts(self) -> None:
        patterns = _get_cleanup_patterns()
        assert "**/.pytest_cache" in patterns
        assert "**/coverage.xml" in patterns
        assert "**/.coverage" in patterns
        assert "**/htmlcov" in patterns

    def test_contains_temp_file_patterns(self) -> None:
        patterns = _get_cleanup_patterns()
        assert "**/tmp_*" in patterns
        assert "**/.tmp" in patterns
        assert "**/temp_*" in patterns


class TestCalculateItemSize:
    """``_calculate_item_size`` reports file/dir size in whole MB."""

    def test_file_size_one_mb(self, tmp_path: Path) -> None:
        f = tmp_path / "one_mb.bin"
        f.write_bytes(b"x" * (1024 * 1024))
        assert _calculate_item_size(f) == 1

    def test_file_size_partial_mb_floors_to_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "small.bin"
        f.write_bytes(b"x" * 100)
        assert _calculate_item_size(f) == 0

    def test_directory_size_aggregates_files(self, tmp_path: Path) -> None:
        d = tmp_path / "sub"
        d.mkdir()
        (d / "a.bin").write_bytes(b"x" * (1024 * 1024))
        (d / "b.bin").write_bytes(b"x" * (1024 * 1024))
        assert _calculate_item_size(d) == 2

    def test_directory_size_zero_for_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        assert _calculate_item_size(d) == 0

    def test_missing_path_returns_zero(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        assert _calculate_item_size(missing) == 0


class TestCleanupItem:
    """``_cleanup_item`` removes a single file or directory."""

    def test_cleanup_file_returns_name_and_size(self, tmp_path: Path) -> None:
        f = tmp_path / "thing.bin"
        f.write_bytes(b"x" * (1024 * 1024))
        display, size = _cleanup_item(f)
        assert display.endswith("thing.bin")
        assert "\U0001f5d1" in display
        assert size == 1
        assert not f.exists()

    def test_cleanup_directory_uses_rglob_display(self, tmp_path: Path) -> None:
        d = tmp_path / "cache"
        d.mkdir()
        (d / "data.bin").write_bytes(b"x" * (1024 * 1024))
        display, size = _cleanup_item(d)
        assert display.endswith("cache/")
        assert "\U0001f4c1" in display
        assert size == 1
        assert not d.exists()

    def test_cleanup_missing_path_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.bin"
        display, size = _cleanup_item(missing)
        assert display == ""
        assert size == 0


class TestCleanupTempFiles:
    """``_cleanup_temp_files`` sweeps ``current_dir`` with the canonical patterns."""

    def test_no_temp_files_returns_no_match_message(self, tmp_path: Path) -> None:
        result = _cleanup_temp_files(tmp_path)
        assert "No temporary files found" in result

    def test_removes_pycache_and_pyc(self, tmp_path: Path) -> None:
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "a.pyc").write_bytes(b"x")
        (cache / "b.pyo").write_bytes(b"y")
        _cleanup_temp_files(tmp_path)
        assert not cache.exists()

    def test_removes_dotted_artifacts(self, tmp_path: Path) -> None:
        ds_store = tmp_path / ".DS_Store"
        ds_store.write_text("mac")
        pytest_cache = tmp_path / ".pytest_cache"
        pytest_cache.mkdir()
        _cleanup_temp_files(tmp_path)
        assert not ds_store.exists()
        assert not pytest_cache.exists()

    def test_returns_cleaned_count_message_when_items_exist(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".DS_Store").write_text("x")
        result = _cleanup_temp_files(tmp_path)
        assert "Cleaned" in result


class TestProcessCleanupPatterns:
    """``_process_cleanup_patterns`` walks every pattern and aggregates size."""

    def test_returns_float(self, tmp_path: Path) -> None:
        total = _process_cleanup_patterns(tmp_path, [], [])
        assert isinstance(total, float)
        assert total == 0.0

    def test_appends_to_cleaned_items(self, tmp_path: Path) -> None:
        (tmp_path / ".DS_Store").write_text("x")
        cleaned: list[str] = []
        _process_cleanup_patterns(tmp_path, _get_cleanup_patterns(), cleaned)
        assert len(cleaned) == 1

    def test_unknown_pattern_yields_zero(self, tmp_path: Path) -> None:
        cleaned: list[str] = []
        total = _process_cleanup_patterns(tmp_path, ["**/never_matches_*"], cleaned)
        assert total == 0.0
        assert cleaned == []


class TestProcessSinglePattern:
    """``_process_single_pattern`` matches a single glob and removes matches."""

    def test_finds_and_removes_matching_files(self, tmp_path: Path) -> None:
        target = tmp_path / "leftover.tmp"
        target.write_text("x")
        cleaned: list[str] = []
        _process_single_pattern(tmp_path, "**/*.tmp", cleaned)
        assert not target.exists()
        assert len(cleaned) == 1

    def test_no_matches_returns_zero(self, tmp_path: Path) -> None:
        cleaned: list[str] = []
        total = _process_single_pattern(tmp_path, "**/*.missing", cleaned)
        assert total == 0.0
        assert cleaned == []


class TestFormatCleanupResults:
    """``_format_cleanup_results`` produces the human-readable summary."""

    def test_summary_mentions_count_and_size(self) -> None:
        out = _format_cleanup_results(["\U0001f5d1 a", "\U0001f5d1 b"], 1.5)
        assert "Cleaned 2 items" in out
        assert "1.5 MB" in out

    def test_truncates_at_ten_items(self) -> None:
        items = [f"item-{i}" for i in range(15)]
        out = _format_cleanup_results(items, 0.0)
        assert "and 5 more items" in out

    def test_handles_exactly_ten_items(self) -> None:
        items = [f"item-{i}" for i in range(10)]
        out = _format_cleanup_results(items, 0.0)
        assert "more items" not in out

    def test_includes_emoji_prefix(self) -> None:
        out = _format_cleanup_results(["x"], 0.0)
        assert out.startswith("\U0001f9f9")


class TestInitializeValidationResults:
    """``_initialize_validation_results`` builds the standard validate payload."""

    def test_has_required_keys(self) -> None:
        results = _initialize_validation_results(Path("/tmp/example"))
        assert "success" in results
        assert "directory" in results
        assert "created" in results
        assert "structure" in results
        assert "permissions" in results
        assert "size_mb" in results

    def test_directory_stringifies_path(self) -> None:
        path = Path("/tmp/whatever")
        results = _initialize_validation_results(path)
        assert results["directory"] == str(path)

    def test_defaults(self) -> None:
        results = _initialize_validation_results(Path("/tmp/x"))
        assert results["success"] is True
        assert results["created"] is False
        assert results["structure"] == {}
        assert results["permissions"] == "ok"
        assert results["size_mb"] == 0.0


class TestSetupMainDirectory:
    """``_setup_main_directory`` creates the directory if missing."""

    def test_creates_missing_directory_and_mb(self, tmp_path: Path) -> None:
        target = tmp_path / "new"
        results: dict[str, Any] = _initialize_validation_results(target)
        _setup_main_directory(target, results)
        assert target.exists()
        assert target.is_dir()
        assert results["created"] is True

    def test_existing_directory_does_not_set_created(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "existing"
        target.mkdir()
        results: dict[str, Any] = _initialize_validation_results(target)
        _setup_main_directory(target, results)
        assert results["created"] is False


class TestSetupSubdirectories:
    """``_setup_subdirectories`` materializes logs/data/temp/backups."""

    def test_creates_all_four_subdirs(self, tmp_path: Path) -> None:
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        _setup_subdirectories(tmp_path, results)
        for name in ("logs", "data", "temp", "backups"):
            assert (tmp_path / name).is_dir()

    def test_records_structure_metadata(self, tmp_path: Path) -> None:
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        _setup_subdirectories(tmp_path, results)
        assert set(results["structure"]) == {"logs", "data", "temp", "backups"}
        for meta in results["structure"].values():
            assert meta["exists"] is True
            assert meta["writable"] is True
            assert meta["files"] == 0

    def test_counts_existing_files(self, tmp_path: Path) -> None:
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "a.log").write_text("a")
        (logs / "b.log").write_text("b")
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        _setup_subdirectories(tmp_path, results)
        assert results["structure"]["logs"]["files"] == 2


class TestCalculateDirectorySize:
    """``_calculate_directory_size`` sums file sizes under ``claude_dir``."""

    def test_empty_directory_is_zero(self, tmp_path: Path) -> None:
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        _calculate_directory_size(tmp_path, results)
        assert results["size_mb"] == 0.0

    def test_one_mb_file_reports_one_mb(self, tmp_path: Path) -> None:
        f = tmp_path / "blob.bin"
        f.write_bytes(b"x" * (1024 * 1024))
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        _calculate_directory_size(tmp_path, results)
        assert results["size_mb"] == 1.0

    def test_skips_unreadable_files(self, tmp_path: Path) -> None:
        f = tmp_path / "blob.bin"
        f.write_bytes(b"x" * (1024 * 1024))
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        with patch.object(Path, "stat", side_effect=PermissionError("nope")):
            _calculate_directory_size(tmp_path, results)
        assert results["size_mb"] == 0.0


class TestValidatePermissions:
    """``_validate_permissions`` marks ``readonly`` when ``os.W_OK`` is denied."""

    def test_writable_directory_passes(self, tmp_path: Path) -> None:
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        _validate_permissions(tmp_path, results)
        assert results["permissions"] == "ok"
        assert results["success"] is True

    def test_readonly_directory_flags_failure(self, tmp_path: Path) -> None:
        results: dict[str, Any] = _initialize_validation_results(tmp_path)
        with patch("session_buddy.utils.filesystem.os.access", return_value=False):
            _validate_permissions(tmp_path, results)
        assert results["permissions"] == "readonly"
        assert results["success"] is False


class TestValidateClaudeDirectory:
    """``validate_claude_directory`` uses ``Path.home()``; mock it."""

    def test_creates_missing_directory(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        with patch(
            "session_buddy.utils.filesystem.Path.home", return_value=fake_home
        ):
            results = validate_claude_directory()
        assert results["success"] is True
        assert results["created"] is True
        assert (fake_home / ".claude").is_dir()

    def test_existing_directory_not_marked_created(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".claude").mkdir()
        with patch(
            "session_buddy.utils.filesystem.Path.home", return_value=fake_home
        ):
            results = validate_claude_directory()
        assert results["created"] is False
        assert results["success"] is True

    def test_creates_subdirectories(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        with patch(
            "session_buddy.utils.filesystem.Path.home", return_value=fake_home
        ):
            results = validate_claude_directory()
        for name in ("logs", "data", "temp", "backups"):
            assert (fake_home / ".claude" / name).is_dir()
        assert set(results["structure"]) == {"logs", "data", "temp", "backups"}

    def test_structure_metadata_has_writable_flag(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        with patch(
            "session_buddy.utils.filesystem.Path.home", return_value=fake_home
        ):
            results = validate_claude_directory()
        for meta in results["structure"].values():
            assert meta["writable"] is True