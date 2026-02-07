#!/usr/bin/env python3
"""File and directory utilities for session management.

This module provides file system operations following crackerjack
architecture patterns with single responsibility principle.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _cleanup_session_logs() -> str:
    """Clean up old session log files, keeping recent ones."""
    claude_dir = Path.home() / ".claude" / "logs"
    if not claude_dir.exists():
        return "📝 No log directory found"

    log_files = list(claude_dir.glob("session_management_*.log"))
    if not log_files:
        return "📝 No session log files found"

    # Keep logs from last 10 days
    cutoff_date = datetime.now(UTC) - timedelta(days=10)
    cleaned_count = 0

    for log_file in log_files:
        try:
            # Extract date from filename: session_management_YYYYMMDD.log
            date_str = log_file.stem.split("_")[-1]  # Gets the YYYYMMDD part
            if len(date_str) == 8 and date_str.isdigit():
                log_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
                if log_date < cutoff_date:
                    log_file.unlink()
                    cleaned_count += 1
        except (ValueError, OSError):
            # Skip files with invalid names or permission issues
            continue

    remaining_count = len(list(claude_dir.glob("session_management_*.log")))
    return f"📝 Cleaned {cleaned_count} old log files, {remaining_count} retained"


def _get_cleanup_patterns() -> list[str]:
    """Get list of file patterns to clean up."""
    return [
        "**/.DS_Store",
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        "**/node_modules/.cache",
        "**/.pytest_cache",
        "**/coverage.xml",
        "**/.coverage",
        "**/htmlcov",
        "**/tmp_*",
        "**/.tmp",
        "**/temp_*",
    ]


def _calculate_item_size(item: Path) -> int:
    """Calculate size of file or directory in MB."""
    size_mb = 0
    with suppress(OSError, PermissionError):
        if item.is_file():
            size_mb = int(item.stat().st_size / (1024 * 1024))
        elif item.is_dir():
            # Calculate directory size
            with suppress(PermissionError, OSError):
                for subitem in item.rglob("*"):
                    if subitem.is_file():
                        size_mb += int(subitem.stat().st_size / (1024 * 1024))
    return size_mb


def _cleanup_item(item: Path) -> tuple[str, int]:
    """Clean up a single item and return its display name and size."""
    with suppress(PermissionError, OSError):
        if item.is_file():
            size_mb = _calculate_item_size(item)
            item.unlink()
            return f"🗑️ {item.name}", size_mb
        if item.is_dir():
            size_mb = _calculate_item_size(item)
            shutil.rmtree(item, ignore_errors=True)
            return f"📁 {item.name}/", size_mb
    return "", 0


def _cleanup_temp_files(current_dir: Path) -> str:
    """Clean up temporary files and caches."""
    cleanup_patterns = _get_cleanup_patterns()
    cleaned_items: list[str] = []

    total_size_mb = _process_cleanup_patterns(
        current_dir,
        cleanup_patterns,
        cleaned_items,
    )

    if not cleaned_items:
        return "🧹 No temporary files found to clean"

    return _format_cleanup_results(cleaned_items, total_size_mb)


def _process_cleanup_patterns(
    current_dir: Path,
    patterns: list[str],
    cleaned_items: list[str],
) -> float:
    """Process each cleanup pattern and collect results."""
    total_size_mb = 0.0
    for pattern in patterns:
        total_size_mb += _process_single_pattern(current_dir, pattern, cleaned_items)
    return total_size_mb


def _process_single_pattern(
    current_dir: Path,
    pattern: str,
    cleaned_items: list[str],
) -> float:
    """Process a single cleanup pattern."""
    pattern_size_mb = 0.0
    with suppress(PermissionError, OSError):
        for item in current_dir.glob(pattern):
            if item.exists():
                display_name, size_mb = _cleanup_item(item)
                if display_name:
                    cleaned_items.append(display_name)
                    pattern_size_mb += size_mb
    return pattern_size_mb


def _format_cleanup_results(cleaned_items: list[str], total_size_mb: float) -> str:
    """Format cleanup results for display."""
    display_items = cleaned_items[:10]
    if len(cleaned_items) > 10:
        display_items.append(f"... and {len(cleaned_items) - 10} more items")

    return (
        f"🧹 Cleaned {len(cleaned_items)} items ({total_size_mb:.1f} MB): "
        + ", ".join(display_items)
    )


def _cleanup_uv_cache() -> str:
    """Clean up UV package manager cache to free space."""
    try:
        # Run uv cache clean command with timeout to prevent hanging
        result = subprocess.run(
            ["uv", "cache", "clean"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,  # 30 second timeout to prevent test hangs
        )

        if result.returncode == 0:
            # Parse output for size information
            output = result.stdout.strip()
            if "freed" in output.lower() or "removed" in output.lower():
                return f"📦 UV cache cleaned: {output}"
            return "📦 UV cache cleaned successfully"
        return f"⚠️ UV cache clean failed: {result.stderr.strip()}"

    except FileNotFoundError:
        return "⚠️ UV not found, skipping cache cleanup"
    except subprocess.TimeoutExpired:
        return "⚠️ UV cache cleanup timed out after 30 seconds"
    except Exception as e:
        return f"⚠️ UV cache cleanup error: {e}"


def validate_claude_directory() -> dict[str, Any]:
    """Validate and set up Claude directory structure."""
    claude_dir = Path.home() / ".claude"
    results = _initialize_validation_results(claude_dir)

    try:
        _setup_main_directory(claude_dir, results)
        _setup_subdirectories(claude_dir, results)
        _calculate_directory_size(claude_dir, results)
        _validate_permissions(claude_dir, results)
    except Exception as e:
        results["success"] = False
        results["error"] = str(e)

    return results


def _initialize_validation_results(claude_dir: Path) -> dict[str, Any]:
    """Initialize validation results dictionary."""
    return {
        "success": True,
        "directory": str(claude_dir),
        "created": False,
        "structure": {},
        "permissions": "ok",
        "size_mb": 0.0,
    }


def _setup_main_directory(claude_dir: Path, results: dict[str, Any]) -> None:
    """Set up main Claude directory."""
    if not claude_dir.exists():
        claude_dir.mkdir(parents=True, exist_ok=True)
        results["created"] = True


def _setup_subdirectories(claude_dir: Path, results: dict[str, Any]) -> None:
    """Set up Claude subdirectories."""
    subdirs = ["logs", "data", "temp", "backups"]
    for subdir in subdirs:
        subdir_path = claude_dir / subdir
        subdir_path.mkdir(exist_ok=True)
        results["structure"][subdir] = {
            "exists": True,
            "writable": os.access(subdir_path, os.W_OK),
            "files": len(list(subdir_path.iterdir())) if subdir_path.exists() else 0,
        }


def _calculate_directory_size(claude_dir: Path, results: dict[str, Any]) -> None:
    """Calculate total directory size."""
    total_size = 0
    for item in claude_dir.rglob("*"):
        if item.is_file():
            try:
                total_size += item.stat().st_size
            except (OSError, PermissionError):
                continue

    results["size_mb"] = total_size / (1024 * 1024)


def _validate_permissions(claude_dir: Path, results: dict[str, Any]) -> None:
    """Validate directory permissions."""
    if not os.access(claude_dir, os.W_OK):
        results["permissions"] = "readonly"
        results["success"] = False
