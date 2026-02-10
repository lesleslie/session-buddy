#!/usr/bin/env python3
"""Unit tests for Session MCP tools.

Phase 2.1: MCP Session Tools Tests
Tests for session initialization, checkpoint, status, and end tools.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

from session_buddy.mcp.tools.session.session_tools import (
    _start_impl,
    _checkpoint_impl,
    _end_impl,
    _status_impl,
    register_session_tools,
    SessionOutputBuilder,
    _get_session_manager,
    _get_client_working_directory,
    _setup_uv_dependencies,
    _create_session_shortcuts,
    _format_successful_end,
    _format_recommendations,
    _format_session_summary,
)
from session_buddy.core import SessionLifecycleManager


@pytest.mark.asyncio
class TestSessionTools:
    """Test suite for session management MCP tools."""

    async def test_start_tool_success(self, tmp_path, mock_project_factory):
        """Test successful session initialization."""
        # Create a test project directory
        test_project = tmp_path / "test-project"
        test_project.mkdir()
        mock_project_factory(
            test_project,
            features={
                "has_pyproject_toml": True,
                "has_git_repo": True,
                "has_readme": True,
            },
        )

        # Mock the session manager
        mock_manager = Mock()
        mock_manager.current_project = "test-project"
        mock_manager.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "test-project",
                "working_directory": str(test_project),
                "quality_score": 85,
                "quality_data": {
                    "breakdown": {
                        "code_quality": 30.0,
                        "project_health": 25.0,
                        "dev_velocity": 15.0,
                        "security": 8.0,
                    },
                    "recommendations": ["Excellent setup!"],
                },
                "project_context": {
                    "has_git_repo": True,
                    "has_pyproject_toml": True,
                    "has_tests": False,
                },
                "claude_directory": str(test_project / ".claude"),
                "previous_session": None,
            }
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _start_impl(str(test_project))

            assert "Session initialization completed successfully" in result
            assert "test-project" in result
            assert "85" in result  # quality score
            mock_manager.initialize_session.assert_called_once()

    async def test_start_tool_failure(self, tmp_path):
        """Test session initialization with failure."""
        test_dir = tmp_path / "test-dir"
        test_dir.mkdir()

        mock_manager = Mock()
        mock_manager.initialize_session = AsyncMock(
            return_value={"success": False, "error": "Test error"}
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _start_impl(str(test_dir))

            assert "initialization failed" in result.lower() or "test error" in result.lower()

    async def test_checkpoint_tool_success(
        self, tmp_path, mock_project_factory, mock_git_repo_factory
    ):
        """Test successful checkpoint creation."""
        test_project = tmp_path / "test-project"
        test_project.mkdir()
        mock_project_factory(
            test_project,
            features={"has_pyproject_toml": True, "has_git_repo": True, "has_tests": True},
        )
        mock_git_repo_factory(test_project)

        mock_manager = Mock()
        mock_manager.current_project = "test-project"
        mock_manager.checkpoint_session = AsyncMock(
            return_value={
                "success": True,
                "quality_score": 88,
                "quality_output": [
                    "✅ Session quality: GOOD (Score: 88/100)",
                    "📈 Quality breakdown (code health metrics):",
                ],
                "git_output": ["✅ Git checkpoint created"],
                "timestamp": datetime.now().isoformat(),
                "auto_store_decision": Mock(should_store=False),
                "auto_store_summary": "Skipped auto-store",
                "insights_extracted": 0,
            }
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            with patch(
                "session_buddy.mcp.tools.session.session_tools.should_suggest_compact",
                return_value=(False, "Context is manageable"),
            ):
                result = await _checkpoint_impl(str(test_project))

                assert "Checkpoint completed" in result
                assert "88" in result  # quality score
                mock_manager.checkpoint_session.assert_called_once_with(
                    str(test_project), is_manual=True
                )

    async def test_checkpoint_tool_failure(self, tmp_path):
        """Test checkpoint with failure."""
        test_dir = tmp_path / "test-dir"
        test_dir.mkdir()

        mock_manager = Mock()
        mock_manager.current_project = "test"
        mock_manager.checkpoint_session = AsyncMock(
            return_value={"success": False, "error": "Checkpoint failed"}
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _checkpoint_impl(str(test_dir))

            assert "failed" in result.lower()

    async def test_end_tool_success(self, tmp_path):
        """Test successful session end."""
        test_dir = tmp_path / "test-dir"
        test_dir.mkdir()

        mock_manager = Mock()
        mock_manager.current_project = "test-project"
        mock_manager.end_session = AsyncMock(
            return_value={
                "success": True,
                "summary": {
                    "project": "test-project",
                    "final_quality_score": 90,
                    "session_end_time": datetime.now().isoformat(),
                    "working_directory": str(test_dir),
                    "recommendations": ["Keep up the good work"],
                    "handoff_documentation": None,
                    "insights_extracted": 2,
                },
            }
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            with patch(
                "session_buddy.mcp.tools.session.session_tools._queue_akosha_sync_background"
            ):
                result = await _end_impl(str(test_dir))

                assert "Session ended successfully" in result or "test-project" in result
                assert "90" in result  # quality score
                mock_manager.end_session.assert_called_once_with(str(test_dir))

    async def test_end_tool_failure(self, tmp_path):
        """Test session end with failure."""
        test_dir = tmp_path / "test-dir"
        test_dir.mkdir()

        mock_manager = Mock()
        mock_manager.end_session = AsyncMock(
            return_value={"success": False, "error": "End failed"}
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _end_impl(str(test_dir))

            assert "failed" in result.lower()

    async def test_status_tool_success(self, tmp_path, mock_project_factory):
        """Test successful status retrieval."""
        test_project = tmp_path / "test-project"
        test_project.mkdir()
        mock_project_factory(
            test_project, features={"has_pyproject_toml": True, "has_git_repo": True}
        )

        mock_manager = Mock()
        mock_manager.current_project = "test-project"
        mock_manager.get_session_status = AsyncMock(
            return_value={
                "success": True,
                "project": "test-project",
                "working_directory": str(test_project),
                "quality_score": 85,
                "quality_breakdown": {
                    "code_quality": 30.0,
                    "project_health": 25.0,
                    "dev_velocity": 15.0,
                    "security": 8.0,
                },
                "recommendations": ["Good setup"],
                "project_context": {"has_git_repo": True, "has_pyproject_toml": True},
                "system_health": {
                    "uv_available": True,
                    "git_repository": True,
                    "claude_directory": True,
                },
                "timestamp": datetime.now().isoformat(),
            }
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            result = await _status_impl(str(test_project))

            assert "test-project" in result
            assert "85" in result
            assert "Quality breakdown" in result


class TestSessionOutputBuilder:
    """Test suite for SessionOutputBuilder helper class."""

    def test_add_header(self):
        """Test adding header to output."""
        builder = SessionOutputBuilder()
        builder.add_header("Test Title")
        output = builder.build()

        assert "Test Title" in output
        assert "=" in output

    def test_add_section(self):
        """Test adding section to output."""
        builder = SessionOutputBuilder()
        builder.add_section("Test Section", ["Item 1", "Item 2"])
        output = builder.build()

        assert "Test Section" in output
        assert "Item 1" in output
        assert "Item 2" in output

    def test_add_status_item(self):
        """Test adding status item."""
        builder = SessionOutputBuilder()
        builder.add_status_item("Test Feature", True)
        builder.add_status_item("Disabled Feature", False)
        output = builder.build()

        assert "✅" in output
        assert "❌" in output
        assert "Test Feature" in output

    def test_build_simple(self):
        """Test building simple output."""
        builder = SessionOutputBuilder()
        builder.add_simple_item("Simple line")
        output = builder.build()

        assert "Simple line" in output


class TestSessionHelpers:
    """Test suite for session tool helper functions."""

    @patch("shutil.which")
    def test_setup_uv_dependencies_available(self, mock_which, tmp_path):
        """Test UV setup when UV is available."""
        mock_which.return_value = "/usr/bin/uv"

        test_project = tmp_path / "test-project"
        test_project.mkdir()
        (test_project / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        with patch("subprocess.run", return_value=Mock(returncode=0, stderr="")):
            result = _setup_uv_dependencies(test_project)

            assert "UV dependencies synchronized" in "\n".join(result) or "Found pyproject.toml" in "\n".join(result)

    @patch("shutil.which")
    def test_setup_uv_dependencies_not_available(self, mock_which, tmp_path):
        """Test UV setup when UV is not available."""
        mock_which.return_value = None

        result = _setup_uv_dependencies(tmp_path)

        output = "\n".join(result)
        assert "UV not found" in output or "Install UV" in output

    def test_create_session_shortcuts_new(self, tmp_path):
        """Test creating session shortcuts when none exist."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        commands_dir = claude_dir / "commands"
        commands_dir.mkdir()

        with patch("pathlib.Path.home", return_value=claude_dir.parent):
            result = _create_session_shortcuts()

            assert result["created"] is True
            assert "start" in result["shortcuts"]
            assert "checkpoint" in result["shortcuts"]
            assert "end" in result["shortcuts"]

    def test_format_successful_end(self):
        """Test formatting successful session end."""
        summary = {
            "project": "test-project",
            "final_quality_score": 92,
            "session_end_time": "2024-01-01T12:00:00Z",
            "working_directory": "/path/to/project",
            "recommendations": ["Great work!", "Add more tests"],
            "handoff_documentation": "/path/to/handoff.md",
        }

        result = _format_successful_end(summary)

        assert "test-project" in result
        assert "92" in result
        assert "Great work!" in result

    def test_format_recommendations(self):
        """Test formatting recommendations."""
        recommendations = ["Tip 1", "Tip 2", "Tip 3"]

        result = _format_recommendations(recommendations)

        assert "Tip 1" in result
        assert "Tip 2" in result
        assert "Tip 3" in result

    def test_format_session_summary(self):
        """Test formatting session summary."""
        summary = {
            "working_directory": "/test/path",
            "handoff_documentation": "/test/handoff.md",
        }

        result = _format_session_summary(summary)

        assert "/test/path" in result
        assert "Session data has been logged" in result

    @patch.dict("os.environ", {"CLIENT_PWD": "/test/client/dir"})
    def test_get_client_working_directory_from_env(self, tmp_path):
        """Test getting working directory from environment variable."""
        # Create a directory that exists
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        with patch.dict("os.environ", {"CLIENT_PWD": str(test_dir)}):
            result = _get_client_working_directory()

            assert result == str(test_dir)


class TestSessionToolRegistration:
    """Test suite for session tool registration."""

    def test_register_session_tools(self, mock_mcp_server):
        """Test that all session tools are registered."""
        register_session_tools(mock_mcp_server)

        # Verify that the tool decorator was called multiple times
        # (once for each tool: start, checkpoint, end, status, health_check, server_info, ping)
        assert mock_mcp_server.tool.call_count >= 7


@pytest.mark.asyncio
class TestSessionToolIntegration:
    """Integration tests for session tools."""

    async def test_full_session_lifecycle(self, tmp_path, mock_project_factory):
        """Test complete session lifecycle: start -> checkpoint -> end."""
        test_project = tmp_path / "test-project"
        test_project.mkdir()
        mock_project_factory(
            test_project,
            features={
                "has_pyproject_toml": True,
                "has_git_repo": True,
                "has_tests": True,
            },
        )

        mock_manager = Mock()
        mock_manager.current_project = "test-project"
        mock_manager.initialize_session = AsyncMock(
            return_value={
                "success": True,
                "project": "test-project",
                "working_directory": str(test_project),
                "quality_score": 80,
                "quality_data": {
                    "breakdown": {
                        "code_quality": 30.0,
                        "project_health": 25.0,
                        "dev_velocity": 15.0,
                        "security": 8.0,
                    },
                    "recommendations": [],
                },
                "project_context": {},
                "claude_directory": str(test_project / ".claude"),
                "previous_session": None,
            }
        )
        mock_manager.checkpoint_session = AsyncMock(
            return_value={
                "success": True,
                "quality_score": 85,
                "quality_output": ["Quality improved"],
                "git_output": ["Git checkpoint"],
                "timestamp": datetime.now().isoformat(),
                "auto_store_decision": Mock(should_store=False),
                "auto_store_summary": "",
                "insights_extracted": 0,
            }
        )
        mock_manager.end_session = AsyncMock(
            return_value={
                "success": True,
                "summary": {
                    "project": "test-project",
                    "final_quality_score": 88,
                    "session_end_time": datetime.now().isoformat(),
                    "working_directory": str(test_project),
                    "recommendations": [],
                    "handoff_documentation": None,
                    "insights_extracted": 1,
                },
            }
        )

        with patch(
            "session_buddy.mcp.tools.session.session_tools._get_session_manager",
            return_value=mock_manager,
        ):
            with patch(
                "session_buddy.mcp.tools.session.session_tools.should_suggest_compact",
                return_value=(False, ""),
            ):
                # Start session
                start_result = await _start_impl(str(test_project))
                assert "success" in start_result.lower() or "completed" in start_result.lower()

                # Create checkpoint
                checkpoint_result = await _checkpoint_impl(str(test_project))
                assert "checkpoint" in checkpoint_result.lower()

                # End session
                end_result = await _end_impl(str(test_project))
                assert "ended" in end_result.lower() or "successfully" in end_result.lower()
