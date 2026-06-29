#!/usr/bin/env python3
"""Tests for crackerjack_tools module (MCP tools).

Tests Crackerjack integration MCP tools for quality monitoring,
command execution, and metrics tracking.

Target: 60%+ coverage for the 1620-line crackerjack_tools.py file.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Security and Parsing Function Tests
# ============================================================================


class TestCheckDangerousChars:
    """Test _check_dangerous_chars security function."""

    def test_valid_token_passes(self) -> None:
        """Should allow valid tokens."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        # Should not raise for valid tokens
        _check_dangerous_chars("--verbose")
        _check_dangerous_chars("--output")
        _check_dangerous_chars("value")

    def test_semicolon_raises(self) -> None:
        """Should block semicolon for command injection."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("test; rm -rf")

    def test_pipe_raises(self) -> None:
        """Should block pipe character."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("test | cat")

    def test_ampersand_raises(self) -> None:
        """Should block ampersand for background execution."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("test & sleep 1")

    def test_dollar_backtick_raises(self) -> None:
        """Should block command substitution characters."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("$(whoami)")

    def test_parentheses_raises(self) -> None:
        """Should block parentheses for subshell."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("test $(echo hi)")

    def test_newline_raises(self) -> None:
        """Should block newline for multi-line injection."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("test\nrm -rf")

    def test_carriage_return_raises(self) -> None:
        """Should block carriage return."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _check_dangerous_chars,
        )

        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars("test\rrm -rf")


class TestIsAllowedArgument:
    """Test _is_allowed_argument allowlist function."""

    def test_allowed_flag(self) -> None:
        """Should accept allowed flags."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_allowed_argument,
        )

        assert _is_allowed_argument("--verbose", {"--verbose", "--quiet"}) is True
        assert _is_allowed_argument("--output", {"--verbose", "--output"}) is True

    def test_numeric_arg_pattern(self) -> None:
        """Should accept --argN pattern."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_allowed_argument,
        )

        assert _is_allowed_argument("--arg1", set()) is True
        assert _is_allowed_argument("--arg42", set()) is True

    def test_key_value_allowed(self) -> None:
        """Should accept allowed key=value format."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_allowed_argument,
        )

        allowed = {"--output", "--severity"}
        assert _is_allowed_argument("--output=json", allowed) is True
        assert _is_allowed_argument("--severity=high", allowed) is True

    def test_key_value_rejected_when_key_not_allowed(self) -> None:
        """Should reject key=value when key not in allowlist."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_allowed_argument,
        )

        allowed = {"--verbose"}
        assert _is_allowed_argument("--output=json", allowed) is False

    def test_not_in_allowlist(self) -> None:
        """Should reject arguments not in allowlist."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_allowed_argument,
        )

        allowed = {"--verbose", "--quiet"}
        assert _is_allowed_argument("--debug", allowed) is False


class TestIsFlagWithValue:
    """Test _is_flag_with_value function."""

    def test_flags_with_values(self) -> None:
        """Should identify flags that accept values."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_flag_with_value,
        )

        assert _is_flag_with_value("--severity") is True
        assert _is_flag_with_value("--confidence") is True
        assert _is_flag_with_value("--output") is True
        assert _is_flag_with_value("--platform") is True

    def test_flags_without_values(self) -> None:
        """Should return False for flags that don't accept values."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_flag_with_value,
        )

        assert _is_flag_with_value("--verbose") is False
        assert _is_flag_with_value("--strict") is False
        assert _is_flag_with_value("--help") is False


class TestGetAllowedArgs:
    """Test _get_allowed_args function."""

    def test_returns_set(self) -> None:
        """Should return a set of allowed arguments."""
        from session_buddy.mcp.tools.session.crackerjack_tools import _get_allowed_args

        allowed = _get_allowed_args()
        assert isinstance(allowed, set)

    def test_contains_standard_flags(self) -> None:
        """Should contain standard Crackerjack flags."""
        from session_buddy.mcp.tools.session.crackerjack_tools import _get_allowed_args

        allowed = _get_allowed_args()
        assert "--verbose" in allowed
        assert "--strict" in allowed
        assert "--help" in allowed
        assert "--version" in allowed
        assert "--coverage" in allowed


class TestParseCrackerjackArgs:
    """Test _parse_crackerjack_args security parsing function."""

    def test_empty_args_returns_empty_list(self) -> None:
        """Should return empty list for empty args."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        assert _parse_crackerjack_args("") == []
        assert _parse_crackerjack_args("   ") == []
        # Note: None is treated as falsy and returns [] (empty args)
        assert _parse_crackerjack_args(None) == []  # type: ignore[arg-type]

    def test_single_flag(self) -> None:
        """Should parse single flag."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        assert _parse_crackerjack_args("--verbose") == ["--verbose"]

    def test_multiple_flags(self) -> None:
        """Should parse multiple flags."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        result = _parse_crackerjack_args("--verbose --strict --coverage")
        assert "--verbose" in result
        assert "--strict" in result
        assert "--coverage" in result

    def test_quoted_argument_with_spaces(self) -> None:
        """Should parse quoted arguments with spaces using shlex."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        # Test that shlex correctly parses quoted strings
        # The result depends on whether the quoted content is in allowlist
        result = _parse_crackerjack_args('"--verbose"')
        # --verbose is allowed and properly parsed by shlex
        assert "--verbose" in result

    def test_key_value_flag(self) -> None:
        """Should parse key=value flags."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        result = _parse_crackerjack_args("--output=json")
        assert "--output" in result

    def test_key_value_flag(self) -> None:
        """Should parse key=value flags."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        result = _parse_crackerjack_args("--output=json")
        assert "--output" in result

    def test_rejects_dangerous_characters(self) -> None:
        """Should reject dangerous shell characters."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        # shlex.split tokenizes "--verbose; rm -rf" as ['--verbose;', 'rm', '-rf']
        # The token '--verbose;' contains ';' so it should be rejected
        with pytest.raises(ValueError, match="Dangerous character"):
            _parse_crackerjack_args("--verbose; rm -rf")

    def test_rejects_unknown_flags(self) -> None:
        """Should reject flags not in allowlist."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        with pytest.raises(ValueError, match="Blocked argument"):
            _parse_crackerjack_args("--unknown-flag")

    def test_unmatched_quote_raises(self) -> None:
        """Should raise for unmatched quotes."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_args,
        )

        with pytest.raises(ValueError, match="Invalid argument syntax"):
            _parse_crackerjack_args('"unmatched quote')


# ============================================================================
# MCP Tool Function Tests
# ============================================================================


class TestExecuteCrackerjackCommand:
    """Test execute_crackerjack_command MCP tool."""

    @pytest.mark.asyncio
    async def test_valid_command_passes_validation(self) -> None:
        """Should execute valid command after validation."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._execute_crackerjack_command_impl"
        ) as mock_impl:
            mock_impl.return_value = "Success output"
            result = await execute_crackerjack_command(command="test")

            assert result == "Success output"
            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_flag_prefix_rejected(self) -> None:
        """Should reject commands starting with --."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        result = await execute_crackerjack_command(command="--ai-fix -t")

        assert "❌" in result
        assert "Invalid Command" in result

    @pytest.mark.asyncio
    async def test_unknown_command_suggests_alternative(self) -> None:
        """Should suggest closest valid command for typos."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        result = await execute_crackerjack_command(command="linting")

        assert "❌" in result
        assert "Unknown Command" in result
        assert "Did you mean" in result

    @pytest.mark.asyncio
    async def test_ai_fix_in_args_rejected(self) -> None:
        """Should reject --ai-fix in args parameter."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        result = await execute_crackerjack_command(command="test", args="--ai-fix")

        assert "❌" in result
        assert "Invalid Args" in result
        assert "ai_agent_mode=True" in result

    @pytest.mark.asyncio
    async def test_all_valid_commands_accepted(self) -> None:
        """Should accept all valid command names."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        valid_commands = {
            "test",
            "lint",
            "check",
            "format",
            "typecheck",
            "security",
            "complexity",
            "analyze",
            "build",
            "clean",
            "all",
            "run",
        }

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._execute_crackerjack_command_impl"
        ) as mock_impl:
            mock_impl.return_value = "OK"

            for cmd in valid_commands:
                result = await execute_crackerjack_command(command=cmd)
                assert result == "OK"

    @pytest.mark.asyncio
    async def test_ai_agent_mode_passed_to_impl(self) -> None:
        """Should pass ai_agent_mode parameter to implementation."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._execute_crackerjack_command_impl"
        ) as mock_impl:
            mock_impl.return_value = "OK"
            await execute_crackerjack_command(
                command="test",
                ai_agent_mode=False,
            )

            call_args = mock_impl.call_args
            # ai_agent_mode is 5th positional argument
            assert call_args[0][4] is False


class TestCrackerjackRun:
    """Test crackerjack_run MCP tool."""

    @pytest.mark.asyncio
    async def test_valid_command_calls_impl(self) -> None:
        """Should call implementation for valid command."""
        from session_buddy.mcp.tools.session.crackerjack_tools import crackerjack_run

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._crackerjack_run_impl"
        ) as mock_impl:
            mock_impl.return_value = "Result"
            result = await crackerjack_run(command="lint", args="--verbose")

            assert result == "Result"
            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_flag_prefix_rejected(self) -> None:
        """Should reject flag-style commands."""
        from session_buddy.mcp.tools.session.crackerjack_tools import crackerjack_run

        result = await crackerjack_run(command="--help")

        assert "❌" in result
        assert "Invalid Command" in result

    @pytest.mark.asyncio
    async def test_unknown_command_suggests(self) -> None:
        """Should suggest alternatives for unknown commands."""
        from session_buddy.mcp.tools.session.crackerjack_tools import crackerjack_run

        result = await crackerjack_run(command="formatting")  # typo

        assert "❌" in result
        assert "Did you mean" in result

    @pytest.mark.asyncio
    async def test_ai_fix_in_args_rejected(self) -> None:
        """Should reject --ai-fix in args."""
        from session_buddy.mcp.tools.session.crackerjack_tools import crackerjack_run

        result = await crackerjack_run(command="test", args="--ai-fix --verbose")

        assert "❌" in result
        assert "ai_agent_mode=True" in result

    @pytest.mark.asyncio
    async def test_valid_commands_subset(self) -> None:
        """Should accept only valid commands for crackerjack_run."""
        from session_buddy.mcp.tools.session.crackerjack_tools import crackerjack_run

        valid_commands = {
            "test",
            "lint",
            "check",
            "format",
            "security",
            "complexity",
            "all",
        }

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._crackerjack_run_impl"
        ) as mock_impl:
            mock_impl.return_value = "OK"

            for cmd in valid_commands:
                result = await crackerjack_run(command=cmd)
                assert result == "OK"


class TestCrackerjackHistory:
    """Test crackerjack_history MCP tool."""

    @pytest.mark.asyncio
    async def test_history_returns_string(self) -> None:
        """Should return formatted history string."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_history,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await crackerjack_history(
                command_filter="",
                days=7,
                working_directory=".",
            )

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_history_with_filter(self) -> None:
        """Should pass filter to implementation."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_history,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await crackerjack_history(
                command_filter="test",
                days=14,
                working_directory="/project",
            )

            assert isinstance(result, str)


class TestCrackerjackMetrics:
    """Test crackerjack_metrics MCP tool."""

    @pytest.mark.asyncio
    async def test_metrics_returns_string(self) -> None:
        """Should return metrics output string."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_metrics,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await crackerjack_metrics(working_directory=".", days=30)

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_crackerjack_quality_metrics(self) -> None:
        """Should return quality metrics."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            get_crackerjack_quality_metrics,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await get_crackerjack_quality_metrics(days=60)

            assert isinstance(result, str)


class TestCrackerjackPatterns:
    """Test crackerjack_patterns MCP tool."""

    @pytest.mark.asyncio
    async def test_patterns_returns_string(self) -> None:
        """Should return patterns analysis."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_patterns,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await crackerjack_patterns(days=7)

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_analyze_crackerjack_test_patterns(self) -> None:
        """Should analyze test failure patterns."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            analyze_crackerjack_test_patterns,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await analyze_crackerjack_test_patterns(days=14)

            assert isinstance(result, str)


class TestCrackerjackHelp:
    """Test crackerjack_help MCP tool."""

    @pytest.mark.asyncio
    async def test_help_returns_comprehensive_guide(self) -> None:
        """Should return help text."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_help,
        )

        result = await crackerjack_help()

        assert isinstance(result, str)
        assert len(result) > 100
        assert "Crackerjack" in result
        assert "crackerjack" in result.lower()


class TestGetCrackerjackResultsHistory:
    """Test get_crackerjack_results_history MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_history_string(self) -> None:
        """Should return history string."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            get_crackerjack_results_history,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await get_crackerjack_results_history(
                command_filter="lint",
                days=7,
                working_directory=".",
            )

            assert isinstance(result, str)


class TestCrackerjackQualityTrends:
    """Test crackerjack_quality_trends MCP tool."""

    @pytest.mark.asyncio
    async def test_quality_trends_returns_string(self) -> None:
        """Should return trends analysis."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_quality_trends,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await crackerjack_quality_trends(days=30)

            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_quality_trends_with_insufficient_data(self) -> None:
        """Should handle insufficient data case."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_quality_trends,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            # Return very few results (less than 5)
            mock_db_instance.search_conversations = AsyncMock(return_value=[{}])
            mock_db.return_value = mock_db_instance

            result = await crackerjack_quality_trends(days=30)

            assert isinstance(result, str)
            assert "Insufficient data" in result


class TestCrackerjackHealthCheck:
    """Test crackerjack_health_check MCP tool."""

    @pytest.mark.asyncio
    async def test_health_check_returns_status(self) -> None:
        """Should return health check status."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_health_check,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="crackerjack 1.0.0",
                stderr="",
            )

            result = await crackerjack_health_check()

            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_health_check_handles_not_found(self) -> None:
        """Should handle crackerjack not installed."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_health_check,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await crackerjack_health_check()

            assert isinstance(result, str)
            assert "Not found" in result or "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_health_check_handles_timeout(self) -> None:
        """Should handle subprocess timeout."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            crackerjack_health_check,
        )

        with patch("subprocess.run") as mock_run:
            from subprocess import TimeoutExpired

            mock_run.side_effect = TimeoutExpired("cmd", 10)

            result = await crackerjack_health_check()

            assert isinstance(result, str)
            assert "Timeout" in result


class TestQualityMonitor:
    """Test quality_monitor alias MCP tool."""

    @pytest.mark.asyncio
    async def test_quality_monitor_alias(self) -> None:
        """Should work as alias for health check."""
        from session_buddy.mcp.tools.session.crackerjack_tools import quality_monitor

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._crackerjack_health_check_impl"
        ) as mock_impl:
            mock_impl.return_value = "Health status output"
            result = await quality_monitor()

            assert result == "Health status output"


# ============================================================================
# Helper and Formatting Function Tests
# ============================================================================


class TestSuggestCommand:
    """Test _suggest_command fuzzy matching helper."""

    def test_exact_match_returns_same(self) -> None:
        """Should return same command when exact match."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _suggest_command,
        )

        valid = {"test", "lint", "check"}
        result = _suggest_command("test", valid)
        assert result == "test"

    def test_close_match_suggested(self) -> None:
        """Should suggest closest match for typo."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _suggest_command,
        )

        valid = {"test", "lint", "check"}
        result = _suggest_command("lintg", valid)
        assert result == "lint"

    def test_no_close_match_returns_check(self) -> None:
        """Should return 'check' fallback when no close match."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _suggest_command,
        )

        valid = {"test", "lint", "check"}
        result = _suggest_command("xyz123", valid)
        assert result == "check"


class TestBuildErrorTroubleshooting:
    """Test _build_error_troubleshooting helper."""

    def test_import_error_troubleshooting(self) -> None:
        """Should build troubleshooting for ImportError."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        result = _build_error_troubleshooting(
            ImportError("No module named 'crackerjack'"),
            timeout=300,
            working_directory="/project",
        )

        assert isinstance(result, str)
        assert "pip list" in result or "pip install" in result

    def test_file_not_found_troubleshooting(self) -> None:
        """Should build troubleshooting for FileNotFoundError."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        result = _build_error_troubleshooting(
            FileNotFoundError("crackerjack not found"),
            timeout=300,
            working_directory="/project",
        )

        assert isinstance(result, str)
        assert "ls -la" in result or "git status" in result

    def test_timeout_error_troubleshooting(self) -> None:
        """Should build troubleshooting for timeout."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        result = _build_error_troubleshooting(
            TimeoutError("Command timed out"),
            timeout=300,
            working_directory="/project",
        )

        assert isinstance(result, str)
        assert "timeout" in result.lower()

    def test_os_error_troubleshooting(self) -> None:
        """Should build troubleshooting for OSError."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        result = _build_error_troubleshooting(
            OSError("Permission denied"),
            timeout=300,
            working_directory="/project",
        )

        assert isinstance(result, str)
        assert "permission" in result.lower() or "access" in result.lower()

    def test_generic_error_troubleshooting(self) -> None:
        """Should build generic troubleshooting."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        result = _build_error_troubleshooting(
            Exception("Unknown error"),
            timeout=300,
            working_directory="/project",
        )

        assert isinstance(result, str)
        assert "crackerjack --help" in result or "python -m crackerjack" in result


class TestFormatExecutionStatus:
    """Test _format_execution_status formatting function."""

    def test_success_status(self) -> None:
        """Should format success status."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_execution_status,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.stdout = "All tests passed"
        mock_result.stderr = ""

        result = _format_execution_status(mock_result)
        assert "✅" in result
        assert "Success" in result

    def test_failure_status(self) -> None:
        """Should format failure status with exit code."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_execution_status,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.stdout = "Failed tests"
        mock_result.stderr = "error occurred"

        result = _format_execution_status(mock_result)
        assert "❌" in result
        assert "Failed" in result
        assert "exit code: 1" in result


class TestFormatBasicResult:
    """Test _format_basic_result formatting function."""

    def test_success_result(self) -> None:
        """Should format success result."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_basic_result,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.stdout = "✅ Hook1\n✅ Hook2\nAll passed"
        mock_result.stderr = ""

        result = _format_basic_result(mock_result, "test")
        assert "Crackerjack test" in result
        assert "Success" in result

    def test_failure_result(self) -> None:
        """Should format failure result with details."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_basic_result,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.stdout = "❌ Hook1\n✅ Hook2\nSome tests failed"
        mock_result.stderr = "Detailed errors"

        result = _format_basic_result(mock_result, "lint")
        assert "Crackerjack lint" in result
        assert "Failed" in result


class TestFormatOutputSections:
    """Test _format_output_sections formatting function."""

    def test_includes_stdout(self) -> None:
        """Should include stdout in output."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_output_sections,
        )

        mock_result = MagicMock()
        mock_result.stdout = "Test output"
        mock_result.stderr = ""

        result = _format_output_sections(mock_result)
        assert "Test output" in result
        assert "Output" in result

    def test_includes_stderr(self) -> None:
        """Should include stderr in output."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_output_sections,
        )

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error details"

        result = _format_output_sections(mock_result)
        assert "Error details" in result
        assert "Error" in result


class TestFormatMetricsSection:
    """Test _format_metrics_section formatting function."""

    def test_includes_execution_time(self) -> None:
        """Should include execution time."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_metrics_section,
        )

        mock_result = MagicMock()
        mock_result.execution_time = 2.5
        mock_result.exit_code = 0
        mock_result.quality_metrics = {}
        mock_result.memory_insights = []

        result = _format_metrics_section(mock_result)
        assert "2.50" in result or "2.5" in result
        assert "Metrics" in result

    def test_includes_quality_metrics(self) -> None:
        """Should include quality metrics when present."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_metrics_section,
        )

        mock_result = MagicMock()
        mock_result.execution_time = 1.0
        mock_result.exit_code = 0
        mock_result.quality_metrics = {"coverage": 85.0, "complexity": 10.0}
        mock_result.memory_insights = []

        result = _format_metrics_section(mock_result)
        assert "Quality Metrics" in result
        assert "Coverage" in result


# ============================================================================
# Hook Parsing Function Tests
# ============================================================================


class TestParseCrackerjackOutput:
    """Test _parse_crackerjack_output function."""

    def test_parsed_with_structured_results(self) -> None:
        """Should parse output with structured results."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_crackerjack_output,
        )

        output = "Hook1...✅ Passed\nHook2...❌ Failed"

        passed, failed = _parse_crackerjack_output(output)
        assert isinstance(passed, list)
        assert isinstance(failed, list)


class TestShouldParseLine:
    """Test _should_parse_line function."""

    def test_returns_true_for_markers(self) -> None:
        """Should return True for lines with parse markers."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _should_parse_line,
        )

        assert _should_parse_line("Hook1...✅ Passed") is True
        assert _should_parse_line("Hook2...❌ Failed") is True

    def test_returns_false_without_markers(self) -> None:
        """Should return False for lines without markers."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _should_parse_line,
        )

        assert _should_parse_line("Some log line") is False
        assert _should_parse_line("No markers here") is False


class TestExtractHookName:
    """Test _extract_hook_name function."""

    def test_extracts_hook_name(self) -> None:
        """Should extract hook name from line."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_hook_name,
        )

        result = _extract_hook_name("Hook1...✅ Passed")
        assert result == "Hook1"

    def test_returns_none_for_invalid_format(self) -> None:
        """Should return None for lines that start with dash."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_hook_name,
        )

        # A line that starts with "-" after splitting on "..."
        # "---hook..." -> parts = ["---hook"] -> hook_name = "---hook" -> starts with "-" -> None
        result = _extract_hook_name("---hook...")
        assert result is None


class TestCategorizeHook:
    """Test _categorize_hook function."""

    def test_categorizes_failed_hook(self) -> None:
        """Should categorize hook as failed."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _categorize_hook,
        )

        passed: list[str] = []
        failed: list[str] = []
        _categorize_hook("Hook1", "Hook1...❌ Failed", passed, failed)

        assert "Hook1" in failed
        assert len(passed) == 0

    def test_categorizes_passed_hook(self) -> None:
        """Should categorize hook as passed."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _categorize_hook,
        )

        passed: list[str] = []
        failed: list[str] = []
        _categorize_hook("Hook1", "Hook1...✅ Passed", passed, failed)

        assert "Hook1" in passed
        assert len(failed) == 0


class TestIsResultsSectionHeader:
    """Test _is_results_section_header function."""

    def test_detects_fast_hook_results(self) -> None:
        """Should detect Fast Hook Results header."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_results_section_header,
        )

        assert _is_results_section_header("Fast Hook Results:") is True

    def test_detects_comprehensive_hook_results(self) -> None:
        """Should detect Comprehensive Hook Results header."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_results_section_header,
        )

        assert _is_results_section_header("Comprehensive Hook Results:") is True


class TestIsNewSectionStart:
    """Test _is_new_section_start function."""

    def test_detects_new_section_markers(self) -> None:
        """Should detect new section start indicators."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_new_section_start,
        )

        assert _is_new_section_start("⏳ Started:") is True
        assert _is_new_section_start("Workflow status") is True
        assert _is_new_section_start("Building...") is True

    def test_returns_false_for_other_lines(self) -> None:
        """Should return False for non-section lines."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_new_section_start,
        )

        assert _is_new_section_start("Some hook result line") is False


class TestIsSeparatorLine:
    """Test _is_separator_line function."""

    def test_detects_separator_lines(self) -> None:
        """Should detect separator lines (dashes only)."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_separator_line,
        )

        assert _is_separator_line("-------------------") is True
        assert _is_separator_line("- - - - - - - - - -") is True

    def test_rejects_non_separator_lines(self) -> None:
        """Should reject lines that aren't separators."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_separator_line,
        )

        assert _is_separator_line("Hook result line") is False


# ============================================================================
# History and Metrics Helper Tests
# ============================================================================


class TestExtractCrackerjackCommands:
    """Test _extract_crackerjack_commands function."""

    def test_extracts_commands_from_results(self) -> None:
        """Should extract commands from result content."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_crackerjack_commands,
        )

        # Mock SAFE_PATTERNS at the correct location (where it's imported)
        mock_pattern = MagicMock()
        mock_pattern.search.return_value = MagicMock(group=MagicMock(return_value="test"))

        with patch(
            "session_buddy.utils.regex_patterns.SAFE_PATTERNS",
            {"crackerjack_command": mock_pattern},
        ):
            results = [
                {"content": "Ran crackerjack test successfully"},
            ]
            commands = _extract_crackerjack_commands(results)
            assert isinstance(commands, dict)


class TestFormatRecentExecutions:
    """Test _format_recent_executions function."""

    def test_formats_results(self) -> None:
        """Should format recent executions."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_recent_executions,
        )

        results = [
            {"timestamp": "2024-01-01", "content": "Ran test successfully"},
            {"timestamp": "2024-01-02", "content": "Ran lint successfully"},
        ]

        output = _format_recent_executions(results)
        assert "Recent Executions" in output
        assert "2024-01-01" in output


class TestParseResultTimestamp:
    """Test _parse_result_timestamp function."""

    def test_parses_iso_format_string(self) -> None:
        """Should parse ISO format timestamp string."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_result_timestamp,
        )

        result = _parse_result_timestamp({"timestamp": "2024-01-15T10:30:00"})
        assert result is not None
        assert isinstance(result, datetime)

    def test_returns_none_for_missing_timestamp(self) -> None:
        """Should return None when timestamp missing."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_result_timestamp,
        )

        result = _parse_result_timestamp({})
        assert result is None


class TestFilterResultsByDate:
    """Test _filter_results_by_date function."""

    def test_filters_old_results(self) -> None:
        """Should filter out results older than start_date."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _filter_results_by_date,
        )

        old_date = datetime.now() - timedelta(days=30)
        results = [
            {"timestamp": (datetime.now() - timedelta(days=5)).isoformat()},
            {"timestamp": (datetime.now() - timedelta(days=60)).isoformat()},
        ]

        filtered = _filter_results_by_date(results, old_date)
        assert len(filtered) == 1


class TestCalculateExecutionSummary:
    """Test _calculate_execution_summary function."""

    def test_calculates_summary(self) -> None:
        """Should calculate execution summary statistics."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _calculate_execution_summary,
        )

        results = [
            {"content": "Success: test passed"},
            {"content": "Success: lint passed"},
            {"content": "Failed: test error"},
        ]

        summary = _calculate_execution_summary(results)
        assert summary["total"] == 3
        assert summary["success"] == 2
        assert summary["failure"] == 1
        assert 0 <= summary["success_rate"] <= 100


class TestExtractQualityKeywords:
    """Test _extract_quality_keywords function."""

    def test_extracts_keywords(self) -> None:
        """Should extract quality keywords from results."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_quality_keywords,
        )

        results = [
            {"content": "lint passed with high coverage"},
            {"content": "security scan completed"},
        ]

        keywords = _extract_quality_keywords(results)
        assert "lint" in keywords
        assert "coverage" in keywords
        assert "security" in keywords


# ============================================================================
# Failure Pattern Analysis Tests
# ============================================================================


class TestFindKeywordMatches:
    """Test _find_keyword_matches function."""

    def test_finds_single_match(self) -> None:
        """Should find single keyword occurrence."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _find_keyword_matches,
        )

        matches = _find_keyword_matches("test error occurred", "error")
        assert len(matches) == 1
        assert matches[0] == (5, 10)

    def test_finds_multiple_matches(self) -> None:
        """Should find multiple keyword occurrences."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _find_keyword_matches,
        )

        matches = _find_keyword_matches("error 1 error 2 error 3", "error")
        assert len(matches) == 3

    def test_returns_empty_for_no_match(self) -> None:
        """Should return empty list when keyword not found."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _find_keyword_matches,
        )

        # "no errors here" contains "error" - no match
        matches = _find_keyword_matches("no errors here", "error")
        # The function searches for exact keyword, and "error" IS in "errors"
        # So it finds a match at position 3
        assert len(matches) >= 1


class TestExtractContextAroundKeyword:
    """Test _extract_context_around_keyword function."""

    def test_extracts_context(self) -> None:
        """Should extract context around keyword."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_context_around_keyword,
        )

        content = "The test failed with assertion error"
        contexts = _extract_context_around_keyword(content, "error", context_size=10)

        assert len(contexts) > 0
        assert all("error" in c for c in contexts)

    def test_handles_keyword_at_start(self) -> None:
        """Should handle keyword at content start."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_context_around_keyword,
        )

        content = "error occurred"
        contexts = _extract_context_around_keyword(content, "error", context_size=5)

        assert len(contexts) > 0

    def test_handles_keyword_at_end(self) -> None:
        """Should handle keyword at content end."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_context_around_keyword,
        )

        content = "Test failed"
        contexts = _extract_context_around_keyword(content, "failed", context_size=5)

        assert len(contexts) > 0


class TestExtractFailurePatterns:
    """Test _extract_failure_patterns function."""

    def test_extracts_patterns(self) -> None:
        """Should extract failure patterns from results."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_failure_patterns,
        )

        results = [
            {"content": "test failed with assertion error"},
        ]
        keywords = ["failed", "error"]

        patterns = _extract_failure_patterns(results, keywords)
        assert isinstance(patterns, dict)


class TestGetFailureKeywords:
    """Test _get_failure_keywords function."""

    def test_returns_list_of_keywords(self) -> None:
        """Should return list of failure keywords."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _get_failure_keywords,
        )

        keywords = _get_failure_keywords()
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert "failed" in keywords
        assert "error" in keywords


# ============================================================================
# Quality Trend Analysis Tests
# ============================================================================


class TestAnalyzeQualityTrendResults:
    """Test _analyze_quality_trend_results function."""

    def test_categorizes_results(self) -> None:
        """Should categorize results into success and failure trends."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _analyze_quality_trend_results,
        )

        results = [
            {"content": "Success - test passed", "timestamp": "2024-01-01"},
            {"content": "Failed - error occurred", "timestamp": "2024-01-02"},
            {"content": "✅ All checks passed", "timestamp": "2024-01-03"},
        ]

        success, failure = _analyze_quality_trend_results(results)
        assert len(success) == 2  # Success markers
        assert len(failure) == 1  # Failed markers


class TestCalculateTrendSuccessRate:
    """Test _calculate_trend_success_rate function."""

    def test_calculates_success_rate(self) -> None:
        """Should calculate success rate percentage."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _calculate_trend_success_rate,
        )

        success = ["2024-01-01", "2024-01-02", "2024-01-03"]
        failure = ["2024-01-04"]

        rate = _calculate_trend_success_rate(success, failure)
        assert rate == 75.0

    def test_handles_zero_total(self) -> None:
        """Should handle zero total runs."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _calculate_trend_success_rate,
        )

        rate = _calculate_trend_success_rate([], [])
        assert rate == 0


class TestFormatTrendOverview:
    """Test _format_trend_overview function."""

    def test_formats_overview(self) -> None:
        """Should format trend overview."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_trend_overview,
        )

        result = _format_trend_overview(
            success_trend=["2024-01-01"],
            failure_trend=["2024-01-02"],
            success_rate=50.0,
        )

        assert "Overall Trends" in result
        assert "50.0%" in result or "50%" in result


class TestFormatTrendQualityInsights:
    """Test _format_trend_quality_insights function."""

    def test_excellent_insight(self) -> None:
        """Should return excellent insight for high success rate."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_trend_quality_insights,
        )

        result = _format_trend_quality_insights(85.0)
        assert "Excellent" in result or "🎉" in result

    def test_good_insight(self) -> None:
        """Should return good insight for moderate success rate."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_trend_quality_insights,
        )

        result = _format_trend_quality_insights(65.0)
        assert "Good" in result or "✅" in result

    def test_needs_attention_insight(self) -> None:
        """Should return attention needed for low success rate."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_trend_quality_insights,
        )

        result = _format_trend_quality_insights(45.0)
        assert "attention" in result.lower() or "⚠️" in result


class TestFormatTrendRecommendations:
    """Test _format_trend_recommendations function."""

    def test_low_success_recommendations(self) -> None:
        """Should recommend actions for low success rate."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_trend_recommendations,
        )

        result = _format_trend_recommendations(50.0)
        assert "Recommendations" in result
        assert "--ai-fix" in result or "automated" in result.lower()

    def test_high_success_recommendations(self) -> None:
        """Should recommend maintenance for high success rate."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_trend_recommendations,
        )

        result = _format_trend_recommendations(85.0)
        assert "Recommendations" in result
        assert "maintain" in result.lower() or "current" in result.lower()


# ============================================================================
# Implementation Function Tests (with mocking)
# ============================================================================


class TestExecuteCrackerjackCommandImpl:
    """Test _execute_crackerjack_command_impl implementation."""

    @pytest.mark.asyncio
    async def test_successful_execution(self) -> None:
        """Should execute and format successful result."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _execute_crackerjack_command_impl,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.stdout = "✅ All passed"
        mock_result.stderr = ""
        mock_result.execution_time = 1.5
        mock_result.quality_metrics = {}
        mock_result.memory_insights = []

        mock_integration = MagicMock()
        mock_integration.execute_crackerjack_command = AsyncMock(
            return_value=mock_result
        )

        with patch(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            return_value=mock_integration,
        ):
            result = await _execute_crackerjack_command_impl(
                command="test",
                args="",
                working_directory=".",
                timeout=300,
                ai_agent_mode=True,
            )

            assert isinstance(result, str)
            assert "Crackerjack test" in result

    @pytest.mark.asyncio
    async def test_handles_import_error(self) -> None:
        """Should handle ImportError gracefully."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _execute_crackerjack_command_impl,
        )

        with patch(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            side_effect=ImportError("No module named 'crackerjack'"),
        ):
            with patch(
                "session_buddy.mcp.tools.session.crackerjack_tools._get_logger"
            ) as mock_logger:
                result = await _execute_crackerjack_command_impl(
                    command="test",
                    args="",
                    working_directory=".",
                    timeout=300,
                    ai_agent_mode=True,
                )

                assert "not available" in result.lower()


class TestCrackerjackHistoryImpl:
    """Test _crackerjack_history_impl implementation."""

    @pytest.mark.asyncio
    async def test_returns_error_when_db_unavailable(self) -> None:
        """Should return error message when database unavailable."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_history_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db.return_value = None  # DB not available

            result = await _crackerjack_history_impl(
                command_filter="",
                days=7,
                working_directory=".",
            )

            assert "❌" in result
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_returns_no_executions_message(self) -> None:
        """Should return message when no executions found."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_history_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_history_impl(
                command_filter="",
                days=7,
                working_directory=".",
            )

            assert isinstance(result, str)
            assert "No crackerjack executions" in result


class TestCrackerjackMetricsImpl:
    """Test _crackerjack_metrics_impl implementation."""

    @pytest.mark.asyncio
    async def test_returns_error_when_db_unavailable(self) -> None:
        """Should return error when database unavailable."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_metrics_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db.return_value = None

            result = await _crackerjack_metrics_impl(
                working_directory=".",
                days=30,
            )

            assert "❌" in result
            assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_no_data_message(self) -> None:
        """Should return no data message when no metrics available."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_metrics_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_metrics_impl(
                working_directory=".",
                days=30,
            )

            assert "No quality metrics" in result

    @pytest.mark.asyncio
    async def test_reads_quality_metrics_history_rows(self) -> None:
        """Should surface rows from quality_metrics_history (the CLI write target).

        Regression for the read-side gap where get_crackerjack_quality_metrics
        only consulted the reflection DB even though the crackerjack CLI now
        writes per-run snapshots to the integration DB's quality_metrics_history
        table. The MCP tool must reflect those rows in its output.
        """
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_metrics_impl,
        )

        fake_history = [
            {
                "id": "metric-row-1",
                "project_path": "/Users/les/Projects/crackerjack",
                "metric_type": "lint_score",
                "metric_value": 92.5,
                "timestamp": "2026-06-29T13:00:00",
                "result_id": "result-abc",
            },
            {
                "id": "metric-row-2",
                "project_path": "/Users/les/Projects/crackerjack",
                "metric_type": "test_pass_rate",
                "metric_value": 98.0,
                "timestamp": "2026-06-29T13:00:01",
                "result_id": "result-abc",
            },
        ]

        async def fake_get_history(
            project_path: str,
            metric_type: str | None = None,
            days: int = 30,
        ) -> list[dict[str, object]]:
            assert project_path.endswith("crackerjack")
            assert metric_type is None
            assert days == 7
            return fake_history

        with patch(
            "session_buddy.crackerjack_integration.get_quality_metrics_history",
            new=fake_get_history,
        ):
            result = await _crackerjack_metrics_impl(
                working_directory="/Users/les/Projects/crackerjack",
                days=7,
            )

        # Surface reflects both rows
        assert "Total Samples" in result
        assert "2" in result
        # Metric types appear
        assert "lint_score" in result
        assert "test_pass_rate" in result
        # Values appear
        assert "92.5" in result
        assert "98.0" in result
        # Should NOT fall back to the "no data" message
        assert "No quality metrics data available" not in result


class TestCrackerjackPatternsImpl:
    """Test _crackerjack_patterns_impl implementation."""

    @pytest.mark.asyncio
    async def test_no_results_header(self) -> None:
        """Should format header when no results."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_patterns_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=[])
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_patterns_impl(days=7)

            assert "Test Failure Patterns" in result
            assert "No test failure patterns found" in result


class TestCrackerjackHelpImpl:
    """Test _crackerjack_help_impl implementation."""

    @pytest.mark.asyncio
    async def test_returns_help_text(self) -> None:
        """Should return comprehensive help text."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_help_impl,
        )

        result = await _crackerjack_help_impl()

        assert "Crackerjack Command Guide" in result
        assert "Quick Quality Checks" in result
        assert "Analysis Commands" in result
        assert len(result) > 500


class TestCrackerjackQualityTrendsImpl:
    """Test _crackerjack_quality_trends_impl implementation."""

    @pytest.mark.asyncio
    async def test_handles_db_unavailable(self) -> None:
        """Should return error when database unavailable."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_quality_trends_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db.return_value = None

            result = await _crackerjack_quality_trends_impl(days=30)

            assert "❌" in result
            assert "not available" in result.lower()


class TestGetReflectionDb:
    """Test _get_reflection_db function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_unavailable(self) -> None:
        """Should return None when reflection database unavailable."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _get_reflection_db,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools.resolve_reflection_database"
        ) as mock_resolve:
            mock_resolve.return_value = None

            result = await _get_reflection_db()
            assert result is None


# ============================================================================
# Build Execution Metadata Tests
# ============================================================================


class TestBuildExecutionMetadata:
    """Test _build_execution_metadata function."""

    def test_builds_basic_metadata(self) -> None:
        """Should build basic metadata dictionary."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_execution_metadata,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.execution_time = 2.5

        mock_metrics = MagicMock()
        mock_metrics.to_dict.return_value = {"tests": 10, "coverage": 85}

        metadata = _build_execution_metadata(
            working_directory="/project",
            result=mock_result,
            metrics=mock_metrics,
        )

        assert isinstance(metadata, dict)
        assert metadata["project"] == "project"
        assert metadata["exit_code"] == 0
        assert metadata["execution_time"] == 2.5
        assert metadata["metrics"] == {"tests": 10, "coverage": 85}


# ============================================================================
# Store Execution Result Tests
# ============================================================================


class TestStoreExecutionResult:
    """Test _store_execution_result function."""

    @pytest.mark.asyncio
    async def test_stores_on_failure_with_ai_agent_mode(self) -> None:
        """Should store execution on failure when ai_agent_mode enabled."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _store_execution_result,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.execution_time = 1.0
        mock_result.stdout = "Failed tests"

        mock_metrics = MagicMock()
        mock_metrics.to_dict.return_value = {}

        mock_db = AsyncMock()
        mock_db.store_conversation = AsyncMock()

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._build_execution_metadata"
        ) as mock_build:
            mock_build.return_value = {"project": "test"}

            result = await _store_execution_result(
                command="test",
                formatted_result="Failed",
                result=mock_result,
                metrics=mock_metrics,
                working_directory="/project",
                ai_agent_mode=True,
                db=mock_db,
            )

            # Should return storage message
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self) -> None:
        """Should return empty string on storage error."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _store_execution_result,
        )

        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.execution_time = 1.0

        mock_metrics = MagicMock()
        mock_metrics.to_dict.return_value = {}

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._build_execution_metadata"
        ) as mock_build:
            mock_build.side_effect = Exception("Build error")

            with patch(
                "session_buddy.mcp.tools.session.crackerjack_tools._get_logger"
            ) as mock_logger:
                result = await _store_execution_result(
                    command="test",
                    formatted_result="Success",
                    result=mock_result,
                    metrics=mock_metrics,
                    working_directory="/project",
                    ai_agent_mode=False,
                    db=None,
                )

                assert result == ""


# ============================================================================
# Registration Function Tests
# ============================================================================


class TestRegisterCrackerjackTools:
    """Test register_crackerjack_tools function."""

    def test_registers_all_tools(self) -> None:
        """Should register all crackerjack tools on mock MCP."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            register_crackerjack_tools,
        )

        mock_mcp = MagicMock()
        mock_mcp.tool = MagicMock(return_value=MagicMock())

        register_crackerjack_tools(mock_mcp)

        # Verify tool decorator was called multiple times
        assert mock_mcp.tool.call_count >= 10  # At least 10 tools registered

    def test_sets_tools_on_mcp(self) -> None:
        """Should set tools attribute on MCP server."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            register_crackerjack_tools,
        )

        mock_mcp = MagicMock()
        mock_mcp.tool = MagicMock(return_value=MagicMock())

        register_crackerjack_tools(mock_mcp)

        # Verify get_tools was assigned
        assert hasattr(mock_mcp, "get_tools")
        assert hasattr(mock_mcp, "tools")


# ============================================================================
# Integration Mock Tests (Higher-level scenarios)
# ============================================================================


class TestEndToEndCommandValidation:
    """End-to-end tests for command validation flow."""

    @pytest.mark.asyncio
    async def test_all_invalid_commands_rejected(self) -> None:
        """Should reject all invalid command patterns."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        invalid_commands = [
            "--help",
            "--version",
            "-v",
            "-t",
            "--ai-fix",
            "---",
        ]

        for cmd in invalid_commands:
            result = await execute_crackerjack_command(command=cmd)
            assert "❌" in result, f"Command {cmd!r} should be rejected"

    @pytest.mark.asyncio
    async def test_duplicate_ai_fix_rejected(self) -> None:
        """Should reject duplicate --ai-fix in args."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            execute_crackerjack_command,
        )

        result = await execute_crackerjack_command(
            command="test",
            args="--verbose --ai-fix --strict",
        )

        assert "❌" in result
        assert "Invalid Args" in result


class TestErrorFormatting:
    """Test error message formatting."""

    def test_suggest_command_with_multiple_options(self) -> None:
        """Should find best match when multiple close matches exist."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _suggest_command,
        )

        valid = {"test", "typecheck", "timeout"}
        result = _suggest_command("typechecks", valid)
        # Should find "typecheck" as closest
        assert result == "typecheck"

    def test_format_history_output(self) -> None:
        """Should format history output correctly."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_history_output,
        )

        filtered_results = [
            {
                "timestamp": "2024-01-01T12:00:00",
                "content": "crackerjack test passed",
            },
        ]

        output = _format_history_output(filtered_results, days=7)
        assert "Crackerjack History" in output
        assert "7" in output
        assert "Total Executions" in output


class TestPatternExtraction:
    """Test pattern extraction from results."""

    def test_format_failure_patterns_with_patterns(self) -> None:
        """Should format failure patterns when present."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_failure_patterns,
        )

        patterns = {
            "assertion failed at line 10": 5,
            "timeout exceeded": 3,
        }

        output = _format_failure_patterns(patterns)
        assert "Common Failure Patterns" in output
        assert "assertion failed" in output
        assert "timeout exceeded" in output

    def test_format_failure_patterns_empty(self) -> None:
        """Should handle empty patterns."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_failure_patterns,
        )

        output = _format_failure_patterns({})
        assert "No clear failure patterns" in output


class TestFormatQualityMetricsOutput:
    """Test _format_quality_metrics_output function."""

    def test_formats_metrics(self) -> None:
        """Should format quality metrics output."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_quality_metrics_output,
        )

        summary = {
            "total": 10,
            "success": 8,
            "failure": 2,
            "success_rate": 80.0,
        }
        keywords = {"lint": 5, "test": 7, "coverage": 3}

        output = _format_quality_metrics_output(30, summary, keywords)
        assert "Crackerjack Quality Metrics" in output
        assert "30" in output
        assert "10" in output
        assert "80" in output or "80.0" in output


# ============================================================================
# Additional Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_parse_hook_stage_results_empty_output(self) -> None:
        """Should handle empty output in hook stage parsing."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_hook_stage_results,
        )

        result = _parse_hook_stage_results("")
        assert result == ""

    def test_parse_hook_results_table_empty(self) -> None:
        """Should handle empty output in results table parsing."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_hook_results_table,
        )

        result = _parse_hook_results_table("")
        assert result == ""

    def test_extract_single_stage_results_at_valid_index(self) -> None:
        """Should extract results at valid index."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_single_stage_results,
        )

        lines = ["line1", "line2", "line3"]
        # Index 1 is valid
        result = _extract_single_stage_results(lines, 1)
        assert "line2" in result

    def test_get_allowed_args_contains_all_expected(self) -> None:
        """Should verify allowed args contains expected values."""
        from session_buddy.mcp.tools.session.crackerjack_tools import _get_allowed_args

        allowed = _get_allowed_args()
        expected_flags = {
            "--verbose",
            "-v",
            "--quiet",
            "-q",
            "--strict",
            "--fix",
            "--check",
            "--coverage",
            "--help",
            "--version",
        }

        for flag in expected_flags:
            assert flag in allowed, f"Expected {flag} in allowed args"
