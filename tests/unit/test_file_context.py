"""Tests for file_context module."""

import tempfile
from pathlib import Path

from session_buddy.memory.file_context import build_file_context


def test_build_file_context_with_existing_file():
    """Test building file context for an existing file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        f.write("# Test file\nprint('hello world')\n# Another comment\n")
        temp_path = f.name

    try:
        result = build_file_context(temp_path, max_lines=2)
        assert "metadata" in result
        assert "snippet" in result
        assert result["metadata"]["file_path"] == temp_path
        assert result["metadata"]["file_name"] == Path(temp_path).name
        assert result["metadata"]["file_extension"] == ".py"
        assert result["metadata"]["size"] > 0
        assert result["snippet"] == "# Test file\nprint('hello world')"
    finally:
        Path(temp_path).unlink()


def test_build_file_context_with_nonexistent_file():
    """Test building file context for a nonexistent file."""
    result = build_file_context("/nonexistent/file.txt")
    assert "metadata" in result
    assert "snippet" in result
    assert result["metadata"]["file_path"] == "/nonexistent/file.txt"
    assert result["metadata"]["file_name"] == "file.txt"
    assert result["metadata"]["file_extension"] == ".txt"
    assert result["metadata"]["size"] == 0
    assert result["snippet"] == ""


def test_build_file_context_with_max_lines():
    """Test that max_lines parameter limits the snippet."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line1\nline2\nline3\nline4\nline5\n")
        temp_path = f.name

    try:
        result = build_file_context(temp_path, max_lines=3)
        assert result["snippet"] == "line1\nline2\nline3"
    finally:
        Path(temp_path).unlink()


def test_build_file_context_with_binary_file():
    """Test building file context for a binary file."""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".bin") as f:
        f.write(b"\x00\x01\x02\x03")
        temp_path = f.name

    try:
        result = build_file_context(temp_path)
        assert "metadata" in result
        assert "snippet" in result
        assert result["metadata"]["file_path"] == temp_path
    finally:
        Path(temp_path).unlink()
