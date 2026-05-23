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


@pytest.fixture
def temp_integration():
    """Create integration with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    integration = CrackerjackIntegration(db_path=db_path)
    yield integration

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestDatabaseIntegration:
    """Test database-related functionality."""

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


class TestHealthCheck:
    """Test health check functionality."""

    async def test_health_check_healthy(self):
        """Test health check when crackerjack and DB are available."""
        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            health = await integration.health_check()

            assert "status" in health
            assert "crackerjack_available" in health
            assert "database_accessible" in health
            assert "recommendations" in health

    async def test_health_check_crackerjack_not_available(self):
        """Test health check when crackerjack is not available."""
        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 1  # Not available
            mock_create.return_value = mock_process

            health = await integration.health_check()

            assert health["crackerjack_available"] is False

    async def test_health_check_with_database_error(self):
        """Test health check handles database errors gracefully."""
        integration = CrackerjackIntegration()

        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            # Force database error by using invalid db path
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                integration.db_path = str(Path(tmpdir) / "nonexistent" / "db.sqlite")
                health = await integration.health_check()
                # Should not raise, should handle gracefully


class TestQualityMetricsCalculation:
    """Test quality metrics calculation methods."""

    def test_calculate_test_metrics_with_results(self):
        """Test _calculate_test_metrics with test results."""
        integration = CrackerjackIntegration()
        parsed_data = {
            "test_results": [
                {"status": "passed"},
                {"status": "passed"},
                {"status": "failed"},
            ]
        }
        metrics = integration._calculate_test_metrics(parsed_data)
        assert "test_pass_rate" in metrics
        assert metrics["test_pass_rate"] == pytest.approx(66.67, rel=0.1)

    def test_calculate_test_metrics_no_results(self):
        """Test _calculate_test_metrics with no results."""
        integration = CrackerjackIntegration()
        parsed_data = {}
        metrics = integration._calculate_test_metrics(parsed_data)
        assert metrics == {}

    def test_calculate_coverage_metrics(self):
        """Test _calculate_coverage_metrics."""
        integration = CrackerjackIntegration()
        parsed_data = {"coverage_summary": {"total_coverage": 85.5}}
        metrics = integration._calculate_coverage_metrics(parsed_data)
        assert "code_coverage" in metrics
        assert metrics["code_coverage"] == 85.5

    def test_calculate_lint_metrics(self):
        """Test _calculate_lint_metrics."""
        integration = CrackerjackIntegration()
        parsed_data = {"lint_summary": {"total_issues": 5}}
        metrics = integration._calculate_lint_metrics(parsed_data)
        assert "lint_score" in metrics
        assert metrics["lint_score"] == 95.0  # 100 - 5

    def test_calculate_security_metrics(self):
        """Test _calculate_security_metrics."""
        integration = CrackerjackIntegration()
        parsed_data = {"security_summary": {"total_issues": 3}}
        metrics = integration._calculate_security_metrics(parsed_data)
        assert "security_score" in metrics
        assert metrics["security_score"] == 70.0  # 100 - (3 * 10)

    def test_calculate_complexity_metrics(self):
        """Test _calculate_complexity_metrics."""
        integration = CrackerjackIntegration()
        parsed_data = {"complexity_summary": {"total_files": 10, "high_complexity_files": 2}}
        metrics = integration._calculate_complexity_metrics(parsed_data)
        assert "complexity_score" in metrics
        assert metrics["complexity_score"] == 80.0  # 100 - (2/10 * 100)

    def test_calculate_quality_metrics_full(self):
        """Test _calculate_quality_metrics combines all metrics."""
        integration = CrackerjackIntegration()
        parsed_data = {
            "test_results": [{"status": "passed"}],
            "coverage_summary": {"total_coverage": 90.0},
            "lint_summary": {"total_issues": 3},
            "security_summary": {"total_issues": 1},
            "complexity_summary": {"total_files": 5, "high_complexity_files": 1},
        }
        metrics = integration._calculate_quality_metrics(parsed_data, exit_code=0)
        assert "test_pass_rate" in metrics
        assert "code_coverage" in metrics
        assert "lint_score" in metrics
        assert "security_score" in metrics
        assert "complexity_score" in metrics
        assert "build_status" in metrics
        assert metrics["build_status"] == 100.0


class TestGetRecentResults:
    """Test get_recent_results method."""

    async def test_get_recent_results_empty(self, temp_integration):
        """Test get_recent_results with no data."""
        results = await temp_integration.get_recent_results(hours=1)
        assert results == []

    async def test_get_recent_results_with_data(self, temp_integration):
        """Test get_recent_results returns stored results."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            await temp_integration.execute_crackerjack_command("test", [], ".")

        results = await temp_integration.get_recent_results(hours=1)
        assert len(results) == 1

    async def test_get_recent_results_filter_by_command(self, temp_integration):
        """Test get_recent_results filters by command."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            await temp_integration.execute_crackerjack_command("lint", [], ".")

        results = await temp_integration.get_recent_results(hours=1, command="lint")
        assert len(results) == 1
        assert results[0]["command"] == "lint"


class TestGetQualityMetricsHistory:
    """Test get_quality_metrics_history method."""

    async def test_get_quality_metrics_history_empty(self, temp_integration):
        """Test get_quality_metrics_history with no data."""
        metrics = await temp_integration.get_quality_metrics_history("/test/path")
        assert metrics == []

    async def test_get_quality_metrics_history_with_data(self, temp_integration):
        """Test get_quality_metrics_history returns stored metrics."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            await temp_integration.execute_crackerjack_command("test", [], "/test/path")

        metrics = await temp_integration.get_quality_metrics_history("/test/path")
        assert len(metrics) > 0

    async def test_get_quality_metrics_history_filter_by_type(self, temp_integration):
        """Test get_quality_metrics_history filters by metric type."""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process

            await temp_integration.execute_crackerjack_command("test", [], "/test/path")

        metrics = await temp_integration.get_quality_metrics_history(
            "/test/path", metric_type="test_pass_rate"
        )
        # Filter by type should work
        for m in metrics:
            if m.get("metric_type"):
                assert m["metric_type"] == "test_pass_rate"


class TestTestFailurePatterns:
    """Test get_test_failure_patterns method."""

    async def test_get_test_failure_patterns_empty(self, temp_integration):
        """Test get_test_failure_patterns with no data."""
        patterns = await temp_integration.get_test_failure_patterns(days=7)
        assert "failed_tests" in patterns
        assert "flaky_tests" in patterns
        assert "failing_files" in patterns
        assert "analysis_period_days" in patterns


class TestQualityTrends:
    """Test get_quality_trends method."""

    async def test_get_quality_trends_empty(self, temp_integration):
        """Test get_quality_trends with no data."""
        trends = await temp_integration.get_quality_trends("/test/path")
        assert "trends" in trends
        assert "overall" in trends
        assert "recommendations" in trends

    async def test_get_quality_trends_with_insufficient_data(self, temp_integration):
        """Test get_quality_trends with insufficient data points."""
        trends = await temp_integration.get_quality_trends("/test/path", days=30)
        assert trends["overall"]["analysis_period_days"] == 30


class TestTrendCalculation:
    """Test trend calculation helper methods."""

    def test_filter_metrics_by_type(self, temp_integration):
        """Test _filter_metrics_by_type."""
        metrics = [
            {"metric_type": "test_pass_rate", "metric_value": 80.0, "timestamp": "2024-01-02"},
            {"metric_type": "test_pass_rate", "metric_value": 90.0, "timestamp": "2024-01-01"},
            {"metric_type": "code_coverage", "metric_value": 70.0, "timestamp": "2024-01-01"},
        ]
        filtered = temp_integration._filter_metrics_by_type(metrics, "test_pass_rate")
        assert len(filtered) == 2
        # Should be sorted by timestamp descending
        assert filtered[0]["timestamp"] > filtered[1]["timestamp"]

    def test_calculate_trend_direction(self, temp_integration):
        """Test _calculate_trend_direction."""
        assert temp_integration._calculate_trend_direction(5.0) == "improving"
        assert temp_integration._calculate_trend_direction(-5.0) == "declining"
        assert temp_integration._calculate_trend_direction(0.0) == "stable"

    def test_calculate_trend_strength(self, temp_integration):
        """Test _calculate_trend_strength."""
        assert temp_integration._calculate_trend_strength(10.0) == "strong"
        assert temp_integration._calculate_trend_strength(3.0) == "moderate"
        assert temp_integration._calculate_trend_strength(0.5) == "weak"

    def test_create_trend_data_insufficient_data(self, temp_integration):
        """Test _create_trend_data with insufficient data."""
        # Only one data point
        metrics = [{"metric_value": 80.0}]
        trend = temp_integration._create_trend_data(metrics)
        assert trend["direction"] == "insufficient_data"
        assert trend["data_points"] == 1

    def test_create_trend_data_with_sufficient_data(self, temp_integration):
        """Test _create_trend_data with sufficient data."""
        metrics = [
            {"metric_value": 90.0, "timestamp": "2024-01-03"},
            {"metric_value": 80.0, "timestamp": "2024-01-02"},
            {"metric_value": 70.0, "timestamp": "2024-01-01"},
        ]
        trend = temp_integration._create_trend_data(metrics)
        assert trend["direction"] == "improving"
        assert trend["data_points"] == 3

    def test_calculate_overall_assessment(self, temp_integration):
        """Test _calculate_overall_assessment."""
        trends = {
            "test_pass_rate": {"direction": "improving"},
            "code_coverage": {"direction": "improving"},
            "lint_score": {"direction": "declining"},
        }
        assessment = temp_integration._calculate_overall_assessment(trends, 30)
        assert assessment["overall_direction"] == "improving"
        assert assessment["improving_count"] == 2
        assert assessment["declining_count"] == 1
        assert assessment["stable_count"] == 0
        assert assessment["analysis_period_days"] == 30

    def test_generate_trend_recommendations(self, temp_integration):
        """Test _generate_trend_recommendations."""
        trends = {
            "test_pass_rate": {
                "direction": "declining",
                "trend_strength": "strong",
                "change": 10.0,
                "recent_average": 70.0,
            },
            "code_coverage": {
                "direction": "improving",
                "trend_strength": "strong",
                "change": 5.0,
                "recent_average": 90.0,
            },
        }
        recommendations = temp_integration._generate_trend_recommendations(trends)
        assert len(recommendations) > 0


class TestBuildCommandFlags:
    """Test _build_command_flags with various commands."""

    def test_build_command_flags_all_commands(self):
        """Test _build_command_flags for all known commands."""
        integration = CrackerjackIntegration()
        test_cases = [
            ("lint", ["run", "--fast"]),
            ("format", ["run", "--fast"]),
            ("check", ["run", "--comp"]),
            ("typecheck", ["run", "--comp"]),
            ("security", ["run", "--comp"]),
            ("complexity", ["run", "--comp"]),
            ("analyze", ["run", "--comp"]),
            ("test", ["run", "--run-tests"]),
            ("build", ["run"]),
            ("clean", ["run"]),
            ("all", ["run"]),
            ("run", ["run"]),
            ("run-tests", ["run-tests"]),
        ]
        for command, expected in test_cases:
            result = integration._build_command_flags(command, ai_agent_mode=False)
            assert result == expected, f"Command '{command}' failed: {result} != {expected}"

    def test_build_command_flags_ai_agent_mode(self):
        """Test _build_command_flags adds --ai-fix when ai_agent_mode=True."""
        integration = CrackerjackIntegration()
        flags = integration._build_command_flags("lint", ai_agent_mode=True)
        assert "--ai-fix" in flags

    def test_build_command_flags_unknown_command(self):
        """Test _build_command_flags for unknown command."""
        integration = CrackerjackIntegration()
        flags = integration._build_command_flags("unknown_command", ai_agent_mode=False)
        assert flags == ["run"]


class TestCreateErrorResult:
    """Test _create_error_result method."""

    def test_create_error_result(self):
        """Test _create_error_result creates proper error result."""
        integration = CrackerjackIntegration()
        result = integration._create_error_result(
            command="test",
            exit_code=1,
            stderr="error occurred",
            execution_time=1.5,
            working_directory="/test",
            memory_insight="Test failed",
        )
        assert result.command == "test"
        assert result.exit_code == 1
        assert result.stderr == "error occurred"
        assert result.execution_time == 1.5
        assert result.working_directory == "/test"
        assert result.memory_insights == ["Test failed"]


class TestPublicAPI:
    """Test public API functions."""

    @pytest.mark.asyncio
    async def test_execute_crackerjack_command_function(self):
        """Test execute_crackerjack_command public function."""
        with patch("session_buddy.crackerjack_integration.get_crackerjack_integration") as mock_get:
            mock_integration = AsyncMock()
            mock_integration.execute_crackerjack_command.return_value = Mock(
                returncode=0,
                stdout="output",
                stderr="",
                success=True,
            )
            mock_get.return_value = mock_integration

            # Note: The public function returns asdict(result)
            from session_buddy.crackerjack_integration import execute_crackerjack_command as exec_func

            # This would require more complex mocking to test fully
            # Just verify it can be imported
            assert callable(exec_func)

    def test_get_recent_crackerjack_results_function(self):
        """Test get_recent_crackerjack_results public function."""
        from session_buddy.crackerjack_integration import get_recent_crackerjack_results

        assert callable(get_recent_crackerjack_results)

    def test_get_quality_metrics_history_function(self):
        """Test get_quality_metrics_history public function."""
        from session_buddy.crackerjack_integration import get_quality_metrics_history

        assert callable(get_quality_metrics_history)

    def test_analyze_test_failure_patterns_function(self):
        """Test analyze_test_failure_patterns public function."""
        from session_buddy.crackerjack_integration import analyze_test_failure_patterns

        assert callable(analyze_test_failure_patterns)

    def test_get_quality_trends_function(self):
        """Test get_quality_trends public function."""
        from session_buddy.crackerjack_integration import get_quality_trends

        assert callable(get_quality_trends)

    def test_crackerjack_health_check_function(self):
        """Test crackerjack_health_check public function."""
        from session_buddy.crackerjack_integration import crackerjack_health_check

        assert callable(crackerjack_health_check)

    def test_get_crackerjack_integration_function(self):
        """Test get_crackerjack_integration function."""
        from session_buddy.crackerjack_integration import get_crackerjack_integration

        assert callable(get_crackerjack_integration)
        # Calling it should return a CrackerjackIntegration instance
        integration = get_crackerjack_integration()
        assert isinstance(integration, CrackerjackIntegration)


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("asyncio.create_subprocess_exec")
    async def test_execute_crackerjack_command_exception(
        self, mock_create_subprocess
    ):
        """Test execute_crackerjack_command handles exceptions."""
        mock_create_subprocess.side_effect = Exception("Unknown error")

        integration = CrackerjackIntegration()
        result = await integration.execute_crackerjack_command("lint", [], ".")

        assert result.exit_code == -2
        assert "Unknown error" in result.stderr

    def test_execute_command_exception_handling(self):
        """Test execute_command handles unexpected exceptions."""
        integration = CrackerjackIntegration()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            result = integration.execute_command(["crackerjack"])

            assert result["returncode"] == -2
            assert "Unexpected error" in result["stderr"]

    def test_calculate_lint_metrics_high_issues(self):
        """Test _calculate_lint_metrics with high issue count."""
        integration = CrackerjackIntegration()
        parsed_data = {"lint_summary": {"total_issues": 150}}
        metrics = integration._calculate_lint_metrics(parsed_data)
        assert metrics["lint_score"] == 0.0  # Clamped to 0

    def test_calculate_security_metrics_many_issues(self):
        """Test _calculate_security_metrics with many issues."""
        integration = CrackerjackIntegration()
        parsed_data = {"security_summary": {"total_issues": 20}}
        metrics = integration._calculate_security_metrics(parsed_data)
        assert metrics["security_score"] == 0.0  # Clamped to 0


if __name__ == "__main__":
    pytest.main([__file__])
