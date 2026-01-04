#!/usr/bin/env python3
"""Unit tests for CrackerjackIntegration class.

These tests specifically target the issues encountered during development:
1. Missing execute_command method (CommandRunner protocol compliance)
2. Incorrect crackerjack command structure
3. Result type mismatches
4. Method existence and signature verification
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from session_buddy.crackerjack_integration import (
    CrackerjackIntegration,
    CrackerjackResult,
)


class TestCrackerjackIntegrationMethodExists:
    """Test that required methods exist with correct signatures."""

    def test_execute_command_method_exists(self):
        """Test that execute_command method exists (CommandRunner protocol)."""
        integration = CrackerjackIntegration()

        # Method must exist
        assert hasattr(integration, "execute_command"), "execute_command method missing"

        # Method must be callable
        assert callable(integration.execute_command), "execute_command not callable"

    def test_execute_crackerjack_command_method_exists(self):
        """Test that execute_crackerjack_command method exists."""
        integration = CrackerjackIntegration()

        # Method must exist
        assert hasattr(integration, "execute_crackerjack_command"), (
            "execute_crackerjack_command method missing"
        )

        # Method must be callable
        assert callable(integration.execute_crackerjack_command), (
            "execute_crackerjack_command not callable"
        )

    def test_execute_command_signature(self):
        """Test execute_command has correct signature for CommandRunner protocol."""
        import inspect

        integration = CrackerjackIntegration()
        sig = inspect.signature(integration.execute_command)

        # Should have cmd parameter
        assert "cmd" in sig.parameters, "execute_command missing 'cmd' parameter"

        # cmd should be annotated as list[str]
        cmd_param = sig.parameters["cmd"]
        assert cmd_param.annotation == list[str], (
            f"cmd parameter type annotation incorrect: {cmd_param.annotation}"
        )

    def test_execute_crackerjack_command_signature(self):
        """Test execute_crackerjack_command has correct async signature."""
        import inspect

        integration = CrackerjackIntegration()

        # Method should be async
        assert asyncio.iscoroutinefunction(integration.execute_crackerjack_command), (
            "execute_crackerjack_command not async"
        )

        sig = inspect.signature(integration.execute_crackerjack_command)

        # Should have required parameters
        required_params = [
            "command",
            "args",
            "working_directory",
            "timeout",
            "ai_agent_mode",
        ]
        for param in required_params:
            assert param in sig.parameters, (
                f"execute_crackerjack_command missing '{param}' parameter"
            )


class TestExecuteCommandMethod:
    """Test the synchronous execute_command method."""

    @patch("subprocess.run")
    def test_execute_command_basic_call(self, mock_run):
        """Test execute_command makes correct subprocess call."""
        # Setup
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        integration = CrackerjackIntegration()

        # Execute
        result = integration.execute_command(["crackerjack", "--fast"])

        # Verify subprocess.run was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args

        assert call_args[0][0] == ["crackerjack", "--fast"]
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["text"] is True

        # Verify result format
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["returncode"] == 0
        assert result["stdout"] == "success output"
        assert result["stderr"] == ""

    @patch("subprocess.run")
    def test_execute_command_with_error(self, mock_run):
        """Test execute_command handles command errors correctly."""
        # Setup
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error occurred"
        mock_run.return_value = mock_result

        integration = CrackerjackIntegration()

        # Execute
        result = integration.execute_command(["crackerjack", "--invalid"])

        # Verify error handling
        assert result["success"] is False
        assert result["returncode"] == 1
        assert result["stderr"] == "error occurred"

    @patch("subprocess.run")
    def test_execute_command_timeout(self, mock_run):
        """Test execute_command handles timeouts correctly."""
        # Setup timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired(["crackerjack"], 30)

        integration = CrackerjackIntegration()

        # Execute
        result = integration.execute_command(["crackerjack"], timeout=1)

        # Verify timeout handling
        assert result["success"] is False
        assert result["returncode"] == -1
        assert "timed out" in result["stderr"].lower()

    @patch("subprocess.run")
    def test_execute_command_with_kwargs(self, mock_run):
        """Test execute_command passes kwargs correctly."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        integration = CrackerjackIntegration()

        # Execute with custom kwargs
        integration.execute_command(["crackerjack", "--test"], cwd="/tmp", timeout=60)

        # Verify kwargs were passed
        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == "/tmp"
        assert call_args[1]["timeout"] == 60


class TestExecuteCrackerjackCommandMethod:
    """Test the async execute_crackerjack_command method."""

    def test_command_mapping(self):
        """Test that command mappings are correct (NEW CLI v0.47+)."""
        integration = CrackerjackIntegration()

        # Test the command mappings directly via _build_command_flags
        test_cases = [
            ("lint", ["run", "--fast"]),
            ("check", ["run", "--comp"]),
            ("test", ["run", "--run-tests"]),
            ("format", ["run", "--fast"]),
            ("typecheck", ["run", "--comp"]),
            ("security", ["run", "--comp"]),  # Security in comprehensive hooks
            ("complexity", ["run", "--comp"]),  # Complexity in comprehensive hooks
            ("analyze", ["run", "--comp"]),  # Comprehensive analysis
            ("clean", ["run"]),  # Clean happens automatically in current version
            ("build", ["run"]),
            ("all", ["run"]),  # General quality checks (NOT --all which is for release)
            ("run", ["run"]),
            ("run-tests", ["run-tests"]),  # Standalone command
        ]

        # Test the _build_command_flags method
        for command, expected_flags in test_cases:
            flags = integration._build_command_flags(command, ai_agent_mode=False)
            assert flags == expected_flags, (
                f"Command '{command}' has incorrect flags: {flags} != {expected_flags}"
            )

    @patch("asyncio.create_subprocess_exec")
    async def test_execute_crackerjack_command_basic(self, mock_create_subprocess):
        """Test basic execution of crackerjack command."""
        # Setup mock process
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"success", b"")
        mock_process.returncode = 0
        mock_create_subprocess.return_value = mock_process

        integration = CrackerjackIntegration()

        # Execute
        result = await integration.execute_crackerjack_command("lint", [], ".")

        # Verify subprocess was called correctly
        mock_create_subprocess.assert_called_once()
        call_args = mock_create_subprocess.call_args

        # Should be called with python -m crackerjack run + flags (NEW CLI v0.47+)
        expected_cmd = [
            "python",
            "-m",
            "crackerjack",
            "run",
            "--fast",
            "--quick",
        ]  # lint maps to run --fast --quick
        assert call_args[0] == tuple(expected_cmd)

        # Verify result type and content
        assert isinstance(result, CrackerjackResult)
        assert result.exit_code == 0
        assert result.stdout == "success"
        assert result.command == "lint"

    @patch("asyncio.create_subprocess_exec")
    async def test_execute_crackerjack_command_with_args(self, mock_create_subprocess):
        """Test command execution with additional args."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"output", b"")
        mock_process.returncode = 0
        mock_create_subprocess.return_value = mock_process

        integration = CrackerjackIntegration()

        # Execute with additional args
        await integration.execute_crackerjack_command("test", ["--verbose"], "/tmp")

        # Verify command construction (NEW CLI v0.47+)
        call_args = mock_create_subprocess.call_args
        expected_cmd = [
            "python",
            "-m",
            "crackerjack",
            "run",
            "--run-tests",
            "--quick",
            "--verbose",
        ]
        assert call_args[0] == tuple(expected_cmd)

        # Verify working directory
        assert call_args[1]["cwd"] == "/tmp"

    @patch("asyncio.create_subprocess_exec")
    async def test_execute_crackerjack_command_ai_agent_mode(
        self, mock_create_subprocess
    ):
        """Test AI agent mode flag is added correctly."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"ai output", b"")
        mock_process.returncode = 0
        mock_create_subprocess.return_value = mock_process

        integration = CrackerjackIntegration()

        # Execute with AI agent mode
        await integration.execute_crackerjack_command(
            "check", [], ".", ai_agent_mode=True
        )

        # Verify AI agent flag is included (NEW CLI structure)
        call_args = mock_create_subprocess.call_args
        expected_cmd = ["python", "-m", "crackerjack", "run", "--comp", "--quick", "--ai-fix"]
        assert call_args[0] == tuple(expected_cmd)

    @patch("asyncio.create_subprocess_exec")
    @patch("asyncio.wait_for")
    async def test_execute_crackerjack_command_timeout(
        self, mock_wait_for, mock_create_subprocess
    ):
        """Test command timeout handling."""
        # Setup timeout
        mock_wait_for.side_effect = TimeoutError()

        integration = CrackerjackIntegration()

        # Execute
        result = await integration.execute_crackerjack_command(
            "lint", [], ".", timeout=1
        )

        # Verify timeout result
        assert result.exit_code == -1
        assert "timed out" in result.stderr.lower()
        assert result.command == "lint"

    async def test_invalid_command_gets_empty_flags(self):
        """Test that invalid commands get empty flags (default behavior)."""
        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            # Execute with invalid command
            await integration.execute_crackerjack_command("invalid_command", [], ".")

            # Should call with python -m crackerjack run (no flags for unknown commands, NEW CLI v0.47+)
            call_args = mock_create.call_args
            expected_cmd = [
                "python",
                "-m",
                "crackerjack",
                "run",
            ]  # No flags for unknown command (uses 'run' subcommand)
            assert call_args[0] == tuple(expected_cmd)


class TestProtocolCompliance:
    """Test that CrackerjackIntegration complies with expected protocols."""

    def test_implements_command_runner_protocol(self):
        """Test that class can be used as CommandRunner."""
        # This would be how crackerjack might use it
        integration = CrackerjackIntegration()

        # Should be able to call execute_command with list of strings
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # This call pattern should work without errors
            result = integration.execute_command(["crackerjack", "--help"])
            assert isinstance(result, dict)
            assert "returncode" in result

    def test_return_types_consistency(self):
        """Test that both methods return expected types."""
        integration = CrackerjackIntegration()

        # execute_command should return dict
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = integration.execute_command(["test"])
            assert isinstance(result, dict)
            assert all(
                key in result for key in ["stdout", "stderr", "returncode", "success"]
            )

    async def test_async_method_returns_crackerjack_result(self):
        """Test that async method returns CrackerjackResult."""
        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            result = await integration.execute_crackerjack_command("test", [], ".")
            assert isinstance(result, CrackerjackResult)

            # Check required fields
            assert hasattr(result, "command")
            assert hasattr(result, "exit_code")
            assert hasattr(result, "stdout")
            assert hasattr(result, "stderr")
            assert hasattr(result, "execution_time")


class TestDatabaseIntegration:
    """Test database-related functionality."""

    @pytest.fixture
    def temp_integration(self):
        """Create integration with temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        integration = CrackerjackIntegration(db_path=db_path)
        yield integration

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    async def test_result_storage(self, temp_integration):
        """Test that results are stored in database."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"test output", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            # Execute command
            await temp_integration.execute_crackerjack_command("test", [], ".")

            # Verify result was stored
            recent_results = await temp_integration.get_recent_results(hours=1)
            assert len(recent_results) == 1
            assert recent_results[0]["command"] == "test"


# Integration tests for MCP tool compatibility
class TestMCPToolIntegration:
    """Test integration with MCP tools."""

    def test_crackerjack_integration_can_be_imported(self):
        """Test that CrackerjackIntegration can be imported in MCP tools."""
        # This test catches import errors
        from session_buddy.crackerjack_integration import CrackerjackIntegration

        # Should be able to instantiate
        integration = CrackerjackIntegration()
        assert integration is not None

    def test_method_calls_dont_raise_attribute_error(self):
        """Test that method calls don't raise AttributeError."""
        integration = CrackerjackIntegration()

        # These should not raise AttributeError
        assert hasattr(integration, "execute_command")
        assert hasattr(integration, "execute_crackerjack_command")

        # Method signatures should be callable
        import inspect

        assert inspect.signature(integration.execute_command)
        assert inspect.signature(integration.execute_crackerjack_command)


# Regression tests for specific bugs
class TestRegressionTests:
    """Tests that specifically catch the bugs we encountered."""

    def test_execute_command_method_exists_regression(self):
        """Regression test for 'execute_command' method missing."""
        # This is the exact error we encountered:
        # "'CrackerjackIntegration' object has no attribute 'execute_command'"

        integration = CrackerjackIntegration()

        # This should NOT raise AttributeError
        try:
            method = integration.execute_command
            assert callable(method)
        except AttributeError as e:
            pytest.fail(f"execute_command method missing: {e}")

    def test_crackerjack_command_structure_regression(self):
        """Regression test for incorrect command structure."""
        # Original bug: passing 'lint' as separate argument to crackerjack
        # causing "Got unexpected extra argument (lint)" error

        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            # Execute lint command
            asyncio.run(integration.execute_crackerjack_command("lint", [], "."))

            # Verify command structure is correct
            call_args = mock_create.call_args
            cmd = call_args[0]

            # Should be ['python', '-m', 'crackerjack', 'run', '--fast', '--quick'], NOT ['crackerjack', 'lint']
            assert cmd == ("python", "-m", "crackerjack", "run", "--fast", "--quick")
            assert "lint" not in cmd, (
                "Command should not contain 'lint' as separate argument"
            )

    async def test_result_type_mismatch_regression(self):
        """Regression test for result type mismatches."""
        # Original bug: MCP tools expected dict but got CrackerjackResult

        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            # Async method should return CrackerjackResult
            async_result = await integration.execute_crackerjack_command(
                "test", [], "."
            )
            assert isinstance(async_result, CrackerjackResult)

            # Sync method should return dict
            with patch("subprocess.run") as mock_run:
                mock_run_result = Mock()
                mock_run_result.returncode = 0
                mock_run_result.stdout = "output"
                mock_run_result.stderr = ""
                mock_run.return_value = mock_run_result

                sync_result = integration.execute_command(["crackerjack"])
                assert isinstance(sync_result, dict)

                # Dict should have expected keys for MCP tool compatibility
                required_keys = ["stdout", "stderr", "returncode", "success"]
                assert all(key in sync_result for key in required_keys)


if __name__ == "__main__":
    pytest.main([__file__])
