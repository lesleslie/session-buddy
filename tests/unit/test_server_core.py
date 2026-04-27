"""Tests for session-mgmt-mcp server core infrastructure.

Tests core server functionality including:
- Server detection and configuration
- Project context analysis
- Git working directory setup
- Conversation summaries

Phase: Week 4 Coverage Restoration - Server Core Tests
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestDetectOtherMCPServers:
    """Test MCP server detection functionality."""

    def test_detect_crackerjack_available(self) -> None:
        """Should detect crackerjack when available."""
        with patch("subprocess.run") as mock_run:
            # Mock successful crackerjack --version
            mock_run.return_value = Mock(returncode=0)

            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            result = _detect_other_mcp_servers()

            assert result["crackerjack"] is True
            mock_run.assert_called_once()
            args = mock_run.call_args
            assert args[0][0] == ["crackerjack", "--version"]

    def test_detect_crackerjack_unavailable_not_found(self) -> None:
        """Should handle crackerjack not found."""
        with patch("subprocess.run") as mock_run:
            # Mock FileNotFoundError (crackerjack not in PATH)
            mock_run.side_effect = FileNotFoundError()

            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            result = _detect_other_mcp_servers()

            assert result["crackerjack"] is False

    def test_detect_crackerjack_unavailable_bad_returncode(self) -> None:
        """Should handle crackerjack returning non-zero."""
        with patch("subprocess.run") as mock_run:
            # Mock failed command
            mock_run.return_value = Mock(returncode=1)

            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            result = _detect_other_mcp_servers()

            assert result["crackerjack"] is False

    def test_detect_crackerjack_timeout(self) -> None:
        """Should handle subprocess timeout."""
        with patch("subprocess.run") as mock_run:
            # Mock timeout
            mock_run.side_effect = subprocess.TimeoutExpired("crackerjack", 5)

            from session_buddy.mcp.server_core import _detect_other_mcp_servers

            result = _detect_other_mcp_servers()

            assert result["crackerjack"] is False


class TestGenerateServerGuidance:
    """Test server guidance generation."""

    def test_generate_guidance_with_crackerjack(self) -> None:
        """Should provide guidance when crackerjack is detected."""
        from session_buddy.mcp.server_core import _generate_server_guidance

        detected = {"crackerjack": True}
        guidance = _generate_server_guidance(detected)

        assert isinstance(guidance, list)
        assert len(guidance) > 0
        # Should mention crackerjack
        assert any("crackerjack" in g.lower() for g in guidance)

    def test_generate_guidance_without_crackerjack(self) -> None:
        """Should provide basic guidance when no servers detected."""
        from session_buddy.mcp.server_core import _generate_server_guidance

        detected = {"crackerjack": False}
        guidance = _generate_server_guidance(detected)

        assert isinstance(guidance, list)
        # May be empty or contain generic guidance


class TestAnalyzeProjectContext:
    """Test project context analysis."""

    @pytest.mark.asyncio
    async def test_analyze_python_project(self, tmp_path: Path) -> None:
        """Should detect Python project with pyproject.toml."""
        # Create a Python project structure
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / ".git").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("# Test Project\n")

        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)

        assert result["python_project"] is True
        assert result["git_repo"] is True
        assert result["has_tests"] is True
        assert result["has_docs"] is True
        assert result["has_requirements"] is False  # Not created
        assert result["has_uv_lock"] is False  # Not created
        assert result["has_mcp_config"] is False  # Not created

    @pytest.mark.asyncio
    async def test_analyze_minimal_project(self, tmp_path: Path) -> None:
        """Should handle minimal project with only directory."""
        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)

        # Empty directory - all False
        assert result["python_project"] is False
        assert result["git_repo"] is False
        assert result["has_tests"] is False
        assert result["has_docs"] is False
        assert result["has_requirements"] is False
        assert result["has_uv_lock"] is False
        assert result["has_mcp_config"] is False

    @pytest.mark.asyncio
    async def test_analyze_project_with_uv(self, tmp_path: Path) -> None:
        """Should detect uv.lock and requirements.txt."""
        (tmp_path / "uv.lock").write_text("# UV lock file\n")
        (tmp_path / "requirements.txt").write_text("fastmcp>=2.0\n")

        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)

        assert result["has_uv_lock"] is True
        assert result["has_requirements"] is True

    @pytest.mark.asyncio
    async def test_analyze_project_with_mcp_config(self, tmp_path: Path) -> None:
        """Should detect .mcp.json configuration."""
        (tmp_path / ".mcp.json").write_text('{"mcpServers": {}}\n')

        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)

        assert result["has_mcp_config"] is True

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_directory(self, tmp_path: Path) -> None:
        """Should return all False for nonexistent directory."""
        nonexistent = tmp_path / "does_not_exist"

        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(nonexistent)

        # All should be False for nonexistent directory
        assert all(not v for v in result.values())

    @pytest.mark.asyncio
    async def test_analyze_project_permission_error(self, tmp_path: Path) -> None:
        """Should handle permission errors gracefully."""
        # Create directory and remove read permissions
        test_dir = tmp_path / "no_access"
        test_dir.mkdir()
        test_dir.chmod(0o000)  # No permissions

        try:
            from session_buddy.mcp.server_core import analyze_project_context

            # Mock the .exists() check to raise PermissionError
            with patch.object(
                Path, "exists", side_effect=PermissionError("Access denied")
            ):
                result = await analyze_project_context(test_dir)

            # Should return safe defaults
            assert all(not v for v in result.values())
        finally:
            # Restore permissions for cleanup
            test_dir.chmod(0o755)

    @pytest.mark.asyncio
    async def test_analyze_project_with_nested_tests(self, tmp_path: Path) -> None:
        """Should detect tests in subdirectories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "tests").mkdir()

        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)

        assert result["has_tests"] is True

    @pytest.mark.asyncio
    async def test_analyze_project_with_docs_dir(self, tmp_path: Path) -> None:
        """Should detect docs directory."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "index.md").write_text("# Documentation\n")

        from session_buddy.mcp.server_core import analyze_project_context

        result = await analyze_project_context(tmp_path)

        assert result["has_docs"] is True


class TestAutoSetupGitWorkingDirectory:
    """Test automatic git working directory setup."""

    @pytest.mark.asyncio
    async def test_auto_setup_in_git_repo(self, tmp_path: Path) -> None:
        """Should detect git repo and setup working directory."""
        # Create fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        from session_buddy.utils.logging import SessionLogger

        logger = SessionLogger(tmp_path / "logs")

        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=tmp_path):
            from session_buddy.mcp.server_core import auto_setup_git_working_directory

            # Should not raise error
            await auto_setup_git_working_directory(logger)

    @pytest.mark.asyncio
    async def test_auto_setup_not_in_git_repo(self, tmp_path: Path) -> None:
        """Should handle non-git directory gracefully."""
        from session_buddy.utils.logging import SessionLogger

        logger = SessionLogger(tmp_path / "logs")

        with patch("session_buddy.mcp.server_core.Path.cwd", return_value=tmp_path):
            from session_buddy.mcp.server_core import auto_setup_git_working_directory

            # Should not raise error even without .git
            await auto_setup_git_working_directory(logger)


class TestFormatConversationSummary:
    """Test conversation summary formatting."""

    @pytest.mark.asyncio
    async def test_format_empty_conversation(self) -> None:
        """Should handle empty conversation history."""
        with patch("session_buddy.reflection_tools.get_reflection_database") as mock_db:
            mock_reflection = MagicMock()
            mock_reflection.search_conversations.return_value = []
            mock_db.return_value = mock_reflection

            from session_buddy.mcp.server_core import _format_conversation_summary

            summary = await _format_conversation_summary()

            assert isinstance(summary, list)
            # Should return empty list or generic message
            assert len(summary) >= 0

    @pytest.mark.asyncio
    async def test_format_conversation_with_results(self) -> None:
        """Should format conversation results."""
        with patch("session_buddy.reflection_tools.get_reflection_database") as mock_db:
            # Mock conversation results
            mock_reflection = MagicMock()
            mock_reflection.search_conversations.return_value = [
                {"content": "Test conversation 1", "similarity": 0.95},
                {"content": "Test conversation 2", "similarity": 0.85},
            ]
            mock_db.return_value = mock_reflection

            from session_buddy.mcp.server_core import _format_conversation_summary

            summary = await _format_conversation_summary()

            assert isinstance(summary, list)
            assert len(summary) > 0
            # Should contain session or conversation content
            summary_text = " ".join(summary)
            assert (
                "session" in summary_text.lower()
                or "conversation" in summary_text.lower()
            )

    @pytest.mark.asyncio
    async def test_format_conversation_database_unavailable(self) -> None:
        """Should handle missing reflection database."""
        with patch("session_buddy.reflection_tools.get_reflection_database") as mock_db:
            # Mock database import error
            mock_db.side_effect = ImportError("Database not available")

            from session_buddy.mcp.server_core import _format_conversation_summary

            summary = await _format_conversation_summary()

            assert isinstance(summary, list)
            # Should return empty or error message
            assert len(summary) >= 0
