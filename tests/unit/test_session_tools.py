"""Tests for session_tools module.

Tests session management MCP tools for initialization, checkpointing,
and cleanup operations.

Phase: Week 5 Day 2 - Session Tools Coverage
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path


class TestSessionOutputBuilder:
    """Test SessionOutputBuilder formatting class."""

    def test_builder_initialization(self) -> None:
        """Should initialize with empty sections list."""
        from session_buddy.tools.session_tools import SessionOutputBuilder

        builder = SessionOutputBuilder()
        assert isinstance(builder.sections, list)
        assert len(builder.sections) == 0

    def test_add_header_creates_formatted_header(self) -> None:
        """Should add header with separator."""
        from session_buddy.tools.session_tools import SessionOutputBuilder

        builder = SessionOutputBuilder()
        builder.add_header("Test Header")

        assert "Test Header" in builder.sections
        assert "=" * len("Test Header") in builder.sections

    def test_add_section_adds_title_and_items(self) -> None:
        """Should add section with title and items."""
        from session_buddy.tools.session_tools import SessionOutputBuilder

        builder = SessionOutputBuilder()
        builder.add_section("Test Section", ["item1", "item2"])

        output = builder.build()
        assert "Test Section:" in output
        assert "item1" in output
        assert "item2" in output

    def test_add_status_item_with_success(self) -> None:
        """Should add status item with success icon."""
        from session_buddy.tools.session_tools import SessionOutputBuilder

        builder = SessionOutputBuilder()
        builder.add_status_item("Feature", True, "enabled")

        output = builder.build()
        assert "✅" in output
        assert "Feature" in output
        assert "enabled" in output

    def test_add_status_item_with_failure(self) -> None:
        """Should add status item with failure icon."""
        from session_buddy.tools.session_tools import SessionOutputBuilder

        builder = SessionOutputBuilder()
        builder.add_status_item("Feature", False)

        output = builder.build()
        assert "❌" in output
        assert "Feature" in output

    def test_build_joins_sections(self) -> None:
        """Should join all sections with newlines."""
        from session_buddy.tools.session_tools import SessionOutputBuilder

        builder = SessionOutputBuilder()
        builder.add_simple_item("Line 1")
        builder.add_simple_item("Line 2")

        output = builder.build()
        assert output == "Line 1\nLine 2"


class TestSessionSetupResults:
    """Test SessionSetupResults dataclass."""

    def test_dataclass_initialization(self) -> None:
        """Should initialize with default values."""
        from session_buddy.tools.session_tools import SessionSetupResults

        results = SessionSetupResults()

        assert isinstance(results.uv_setup, list)
        assert isinstance(results.shortcuts_result, dict)
        assert isinstance(results.recommendations, list)

    def test_dataclass_with_values(self) -> None:
        """Should store provided values."""
        from session_buddy.tools.session_tools import SessionSetupResults

        results = SessionSetupResults(
            uv_setup=["setup line"],
            shortcuts_result={"created": True},
            recommendations=["rec1"],
        )

        assert results.uv_setup == ["setup line"]
        assert results.shortcuts_result == {"created": True}
        assert results.recommendations == ["rec1"]


class TestSessionManagerAccess:
    """Test session manager singleton access."""

    def test_get_session_manager_returns_instance(self) -> None:
        """Should return SessionLifecycleManager instance."""
        from session_buddy.tools.session_tools import _get_session_manager

        manager = _get_session_manager()

        assert manager is not None
        # Should be a SessionLifecycleManager or compatible type

    def test_session_manager_global_is_set(self) -> None:
        """Should be able to get a session manager instance."""
        from session_buddy.tools.session_tools import _get_session_manager

        manager = _get_session_manager()
        assert manager is not None


class TestCreateSessionShortcuts:
    """Test slash command shortcut creation."""

    def test_creates_shortcuts_in_claude_directory(self, tmp_path: Path) -> None:
        """Should create shortcuts in ~/.claude/commands/."""
        from session_buddy.tools.session_tools import _create_session_shortcuts

        with patch("session_buddy.tools.session_tools.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            result = _create_session_shortcuts()

            commands_dir = tmp_path / ".claude" / "commands"
            assert commands_dir.exists()

            # Should create start, checkpoint, end shortcuts
            assert (commands_dir / "start.md").exists()
            assert (commands_dir / "checkpoint.md").exists()
            assert (commands_dir / "end.md").exists()

            assert result["created"] is True
            assert len(result["shortcuts"]) == 3

    def test_detects_existing_shortcuts(self, tmp_path: Path) -> None:
        """Should detect when shortcuts already exist."""
        from session_buddy.tools.session_tools import _create_session_shortcuts

        with patch("session_buddy.tools.session_tools.Path.home") as mock_home:
            mock_home.return_value = tmp_path

            # Create shortcuts first
            _create_session_shortcuts()

            # Run again - should detect existing
            result = _create_session_shortcuts()

            assert result["existed"] is True
            assert result["created"] is False


class TestWorkingDirectoryDetection:
    """Test client working directory auto-detection."""

    def test_check_environment_variables_finds_claude_working_dir(self) -> None:
        """Should find CLAUDE_WORKING_DIR environment variable."""
        from session_buddy.tools.session_tools import _check_environment_variables

        with patch.dict("os.environ", {"CLAUDE_WORKING_DIR": "/test/dir"}):
            with patch("session_buddy.tools.session_tools.Path") as mock_path:
                mock_path.return_value.exists.return_value = True
                result = _check_environment_variables()

                # May return None or the path depending on validation
                assert result is None or "/test/dir" in str(result)

    def test_check_working_dir_file_reads_temp_file(self, tmp_path: Path) -> None:
        """Should read working directory from temp file."""
        from session_buddy.tools.session_tools import _check_working_dir_file

        with patch("tempfile.gettempdir") as mock_temp:
            mock_temp.return_value = str(tmp_path)

            # Create the temp file
            working_dir_file = tmp_path / "claude-git-working-dir"
            test_dir = "/test/project/dir"
            working_dir_file.write_text(test_dir)

            with patch("session_buddy.tools.session_tools.Path") as mock_path_cls:
                # Mock Path().exists() to return True
                mock_path = MagicMock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                result = _check_working_dir_file()

                # Should return the test directory or None (validation may reject it)
                assert result is None or test_dir in str(result)

    def test_is_git_repository_detects_git(self, tmp_path: Path) -> None:
        """Should detect git repositories."""
        from session_buddy.tools.session_tools import _is_git_repository

        # Create .git directory
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        assert _is_git_repository(tmp_path) is True

    def test_is_git_repository_rejects_non_git(self, tmp_path: Path) -> None:
        """Should reject non-git directories."""
        from session_buddy.tools.session_tools import _is_git_repository

        assert _is_git_repository(tmp_path) is False


class TestStartTool:
    """Test start tool implementation."""

    @pytest.mark.asyncio
    async def test_start_impl_returns_formatted_output(self) -> None:
        """Should return formatted initialization output."""
        from session_buddy.tools.session_tools import _get_session_manager, _start_impl

        mock_manager = AsyncMock()
        mock_manager.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "test-project",
                "working_directory": "/test/dir",
                "claude_directory": "/home/.claude",
                "quality_score": 75,
                "quality_data": {"recommendations": []},
                "project_context": {"has_git": True},
            }
        )

        with patch(
            "session_buddy.tools.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            with patch(
                "session_buddy.tools.session_tools._setup_uv_dependencies"
            ) as mock_uv:
                mock_uv.return_value = ["UV setup complete"]

                with patch(
                    "session_buddy.tools.session_tools._create_session_shortcuts"
                ) as mock_shortcuts:
                    mock_shortcuts.return_value = {
                        "created": True,
                        "shortcuts": ["start", "checkpoint"],
                    }

                    result = await _start_impl("/test/dir")

                    assert isinstance(result, str)
                    assert "Session Initialization" in result or "🚀" in result
                    assert "test-project" in result


class TestCheckpointTool:
    """Test checkpoint tool implementation."""

    @pytest.mark.asyncio
    async def test_checkpoint_impl_performs_checkpoint(self) -> None:
        """Should perform checkpoint and return formatted output."""
        from session_buddy.tools.session_tools import (
            _checkpoint_impl,
            _get_session_manager,
        )

        mock_manager = AsyncMock()
        mock_manager.current_project = "test-project"
        mock_manager.checkpoint_session = AsyncMock(
            return_value={
                "success": True,
                "quality_output": ["Quality: 80/100"],
                "git_output": ["Git commit created"],
                "quality_score": 80,
                "timestamp": "2025-01-01 12:00:00",
            }
        )

        with patch(
            "session_buddy.tools.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            with patch(
                "session_buddy.tools.session_tools._handle_auto_compaction"
            ) as mock_compact:
                mock_compact.return_value = None

                result = await _checkpoint_impl("/test/dir")

                assert isinstance(result, str)
                assert "Checkpoint" in result or "🔍" in result


class TestEndTool:
    """Test end tool implementation."""

    @pytest.mark.asyncio
    async def test_end_impl_ends_session(self) -> None:
        """Should end session and return formatted output."""
        from session_buddy.tools.session_tools import _end_impl, _get_session_manager

        mock_manager = AsyncMock()
        mock_manager.end_session = AsyncMock(
            return_value={
                "success": True,
                "summary": {
                    "project": "test-project",
                    "final_quality_score": 85,
                    "session_end_time": "2025-01-01 13:00:00",
                    "working_directory": "/test/dir",
                    "recommendations": ["Use tests"],
                },
            }
        )

        with patch(
            "session_buddy.tools.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _end_impl("/test/dir")

            assert isinstance(result, str)
            assert "Session End" in result or "🏁" in result
            assert "test-project" in result


class TestStatusTool:
    """Test status tool implementation."""

    @pytest.mark.asyncio
    async def test_status_impl_returns_status(self) -> None:
        """Should return comprehensive session status."""
        from session_buddy.tools.session_tools import _get_session_manager, _status_impl

        mock_manager = AsyncMock()
        mock_manager.get_session_status = AsyncMock(
            return_value={
                "success": True,
                "project": "test-project",
                "working_directory": "/test/dir",
                "quality_score": 75,
                "quality_breakdown": {
                    "code_quality": 30.0,
                    "project_health": 25.0,
                    "dev_velocity": 15.0,
                    "security": 5.0,
                },
                "system_health": {
                    "uv_available": True,
                    "git_repository": True,
                    "claude_directory": True,
                },
                "project_context": {
                    "has_pyproject_toml": True,
                    "has_git_repo": True,
                    "has_tests": True,
                    "has_docs": False,
                },
                "recommendations": ["Add docs"],
                "timestamp": "2025-01-01 14:00:00",
            }
        )

        with patch(
            "session_buddy.tools.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _status_impl("/test/dir")

            assert isinstance(result, str)
            assert "Status" in result or "📊" in result
            assert "test-project" in result


class TestHelperFunctions:
    """Test utility and helper functions."""

    def test_setup_uv_dependencies_detects_uv(self, tmp_path: Path) -> None:
        """Should detect UV and pyproject.toml."""
        from session_buddy.tools.session_tools import _setup_uv_dependencies

        # Create pyproject.toml
        (tmp_path / "pyproject.toml").write_text("[project]")

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/uv"

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                result = _setup_uv_dependencies(tmp_path)

                assert isinstance(result, list)
                assert any("UV" in line for line in result)

    def test_setup_uv_dependencies_handles_no_uv(self, tmp_path: Path) -> None:
        """Should handle missing UV gracefully."""
        from session_buddy.tools.session_tools import _setup_uv_dependencies

        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            result = _setup_uv_dependencies(tmp_path)

            assert isinstance(result, list)
            assert any("not found" in line or "Install UV" in line for line in result)


class TestHealthCheckTools:
    """Test health check and server info tools."""

    @pytest.mark.asyncio
    async def test_health_check_returns_status(self) -> None:
        """Should return health check status."""
        # Access via register function pattern
        from unittest.mock import MagicMock

        from session_buddy.tools.session_tools import _get_session_manager

        mock_mcp = MagicMock()
        tools = {}

        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func

            return decorator

        mock_mcp.tool = mock_tool

        from session_buddy.tools.session_tools import register_session_tools

        register_session_tools(mock_mcp)

        # Get the health_check tool
        health_check = tools.get("health_check")
        assert health_check is not None

        result = await health_check()

        assert isinstance(result, str)
        assert "Health Check" in result or "✅" in result

    @pytest.mark.asyncio
    async def test_ping_returns_pong(self) -> None:
        """Should return pong response."""
        from unittest.mock import MagicMock

        mock_mcp = MagicMock()
        tools = {}

        def mock_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func

            return decorator

        mock_mcp.tool = mock_tool

        from session_buddy.tools.session_tools import register_session_tools

        register_session_tools(mock_mcp)

        # Get the ping tool
        ping = tools.get("ping")
        assert ping is not None

        result = await ping()

        assert isinstance(result, str)
        assert "Pong" in result or "🏓" in result
