#!/usr/bin/env python3
"""Additional tests for crackerjack_tools module.

Targets uncovered branches identified by coverage report:
- _format_execution_status (failure path with hooks and stderr)
- _parse_with_line_scanner and _extract_hook_name branches
- _parse_hook_results_table and section detection helpers
- _format_metrics_section (with quality_metrics and memory_insights)
- _format_basic_result (failure path, hook tables, stderr)
- _build_error_troubleshooting (all error-type branches)
- _format_history_output and supporting helpers
- _crackerjack_history_impl success path
- _crackerjack_quality_trends_impl and trend helpers (insights/recommendations)
- _crackerjack_health_check_impl (history storage + exception branches)
- register_crackerjack_tools
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# _format_execution_status
# ============================================================================


class TestFormatExecutionStatus:
    """Cover failure and success branches of _format_execution_status."""

    def test_failure_with_failed_hooks_and_stderr(self) -> None:
        """Failure path should include failed hooks and error details."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_execution_status,
        )

        result = SimpleNamespace(
            exit_code=1,
            stdout="Ruff... ❌ Failed\nTests... ❌ Failed",
            stderr="error: lint failed badly",
            execution_time=0.0,
            quality_metrics={},
            memory_insights=[],
        )

        output = _format_execution_status(result)
        assert "Failed" in output
        assert "Ruff" in output
        assert "Tests" in output
        assert "Error Details" in output

    def test_failure_without_stderr(self) -> None:
        """Failure without stderr should not include error details."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_execution_status,
        )

        result = SimpleNamespace(
            exit_code=2,
            stdout="Ruff... ❌ Failed",
            stderr="",
            execution_time=0.0,
            quality_metrics={},
            memory_insights=[],
        )

        output = _format_execution_status(result)
        assert "Failed" in output
        assert "Error Details" not in output

    def test_success_with_hooks(self) -> None:
        """Success with parsed hooks should mention hook count."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_execution_status,
        )

        result = SimpleNamespace(
            exit_code=0,
            stdout="Ruff... ✅ Passed\nTests... ✅ Passed",
            stderr="",
            execution_time=0.0,
            quality_metrics={},
            memory_insights=[],
        )

        output = _format_execution_status(result)
        assert "Success" in output
        assert "2 hooks passed" in output

    def test_success_no_hooks(self) -> None:
        """Success without parseable hooks returns plain success."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_execution_status,
        )

        result = SimpleNamespace(
            exit_code=0,
            stdout="No markers here",
            stderr="",
            execution_time=0.0,
            quality_metrics={},
            memory_insights=[],
        )

        output = _format_execution_status(result)
        assert "Success" in output
        assert "hooks passed" not in output


# ============================================================================
# _parse_with_line_scanner and _extract_hook_name
# ============================================================================


class TestParseWithLineScanner:
    """Cover line scanner fallback parser and hook name extraction."""

    def test_extract_hook_name_basic(self) -> None:
        """Extract hook name from line containing ... marker."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_hook_name,
        )

        assert _extract_hook_name("Ruff... Passed") == "Ruff"
        assert _extract_hook_name("Format ... ✅") == "Format"

    def test_extract_hook_name_rejects_dash_prefix(self) -> None:
        """Lines starting with dash should not extract a hook name."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_hook_name,
        )

        assert _extract_hook_name("- ... Passed") is None

    def test_extract_hook_name_empty(self) -> None:
        """Empty hook name should return None."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _extract_hook_name,
        )

        assert _extract_hook_name("   ... Passed") is None

    def test_categorize_pass_and_fail(self) -> None:
        """Categorize hooks correctly into passed/failed lists."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _categorize_hook,
        )

        passed: list[str] = []
        failed: list[str] = []
        _categorize_hook("Ruff", "Ruff... ✅ Passed", passed, failed)
        _categorize_hook("Test", "Test... ❌ Failed", passed, failed)
        assert passed == ["Ruff"]
        assert failed == ["Test"]

    def test_parse_with_line_scanner(self) -> None:
        """Line scanner should return both passed and failed hooks."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_with_line_scanner,
        )

        output = (
            "Starting...\n"
            "Ruff... ✅ Passed\n"
            "Tests... ❌ Failed\n"
            "Done.\n"
        )
        passed, failed = _parse_with_line_scanner(output)
        assert passed == ["Ruff"]
        assert failed == ["Tests"]

    def test_should_parse_line(self) -> None:
        """_should_parse_line requires both ... and a marker."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _should_parse_line,
        )

        assert _should_parse_line("Ruff... ✅") is True
        assert _should_parse_line("Ruff... Failed") is True
        assert _should_parse_line("Ruff... Passed") is True
        assert _should_parse_line("no markers") is False
        assert _should_parse_line("No ellipsis here") is False


# ============================================================================
# _parse_hook_results_table + section helpers
# ============================================================================


class TestParseHookResultsTable:
    """Cover results table parser and section detection helpers."""

    def test_is_results_section_header(self) -> None:
        """Detect both fast and comprehensive section headers."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_results_section_header,
        )

        assert _is_results_section_header("Fast Hook Results:") is True
        assert _is_results_section_header("Comprehensive Hook Results:") is True
        assert _is_results_section_header("Random line") is False

    def test_is_new_section_start(self) -> None:
        """Detect new section indicators."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_new_section_start,
        )

        assert _is_new_section_start("⏳ Started: build") is True
        assert _is_new_section_start("Workflow started") is True
        assert _is_new_section_start("Building project") is True
        assert _is_new_section_start("normal line") is False

    def test_is_separator_line(self) -> None:
        """Detect dash-only separator lines."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _is_separator_line,
        )

        assert _is_separator_line("-" * 20) is True
        assert _is_separator_line("- - - - - - - - - -") is True
        assert _is_separator_line("not a separator") is False
        assert _is_separator_line("-") is False  # too short

    def test_should_add_to_results(self) -> None:
        """Accept empty lines, separator lines, and lines with :: markers."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _should_add_to_results,
        )

        assert _should_add_to_results("") is True
        assert _should_add_to_results("   ") is True
        assert _should_add_to_results("ERROR::message") is True
        assert _should_add_to_results("-" * 20) is True
        assert _should_add_to_results("plain line") is False

    def test_parse_hook_results_table_with_section(self) -> None:
        """Extract a results table when the section header is present."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_hook_results_table,
        )

        output = (
            "Fast Hook Results:\n"
            "ERROR::ruff failed\n"
            "-" * 20 + "\n"
            "Workflow summary\n"
        )
        result = _parse_hook_results_table(output)
        assert "Fast Hook Results" in result
        assert "ERROR::ruff failed" in result

    def test_parse_hook_results_table_empty(self) -> None:
        """Empty input returns empty string."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_hook_results_table,
        )

        assert _parse_hook_results_table("") == ""


# ============================================================================
# _format_metrics_section
# ============================================================================


class TestFormatMetricsSection:
    """Cover formatting helpers with and without metrics."""

    def test_with_quality_metrics_and_insights(self) -> None:
        """Should render quality metrics and memory insights."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_metrics_section,
        )

        result = SimpleNamespace(
            exit_code=0,
            stdout="",
            stderr="",
            execution_time=2.5,
            quality_metrics={"coverage": 87.5, "complexity": 5.0},
            memory_insights=["insight a", "insight b", "insight c"],
        )

        output = _format_metrics_section(result)
        assert "Coverage" in output
        assert "Complexity" in output
        assert "Insights" in output
        assert "2.50s" in output

    def test_insights_truncated_to_five(self) -> None:
        """Memory insights should be limited to 5 entries."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_metrics_section,
        )

        result = SimpleNamespace(
            exit_code=0,
            stdout="",
            stderr="",
            execution_time=1.0,
            quality_metrics={},
            memory_insights=[f"insight-{i}" for i in range(20)],
        )

        output = _format_metrics_section(result)
        for i in range(5):
            assert f"insight-{i}" in output
        assert "insight-5" not in output


# ============================================================================
# _format_output_sections
# ============================================================================


class TestFormatOutputSections:
    """Cover stdout/stderr rendering."""

    def test_both_stdout_and_stderr(self) -> None:
        """Output should include both stdout and stderr sections."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_output_sections,
        )

        result = SimpleNamespace(stdout="ok\n", stderr="warn\n")
        output = _format_output_sections(result)
        assert "Output" in output
        assert "Errors" in output

    def test_only_stdout(self) -> None:
        """Output should include only stdout when stderr is empty."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_output_sections,
        )

        result = SimpleNamespace(stdout="hello", stderr="   ")
        output = _format_output_sections(result)
        assert "Output" in output
        assert "Errors" not in output


# ============================================================================
# _format_basic_result
# ============================================================================


class TestFormatBasicResult:
    """Cover success/failure and hook-table branches."""

    def _make_result(self, exit_code: int, stdout: str, stderr: str = "") -> object:
        return SimpleNamespace(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            execution_time=0.0,
            quality_metrics={},
            memory_insights=[],
        )

    def test_success_path_with_hooks(self) -> None:
        """Success should list passed hooks."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_basic_result,
        )

        result = self._make_result(
            0, "Ruff... ✅ Passed\nTests... ✅ Passed"
        )
        output = _format_basic_result(result, "test")
        assert "Success" in output
        assert "Ruff" in output
        assert "Tests" in output

    def test_failure_path_with_both_hook_lists(self) -> None:
        """Failure should list both passed and failed hooks."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_basic_result,
        )

        result = self._make_result(
            1, "Ruff... ✅ Passed\nTests... ❌ Failed"
        )
        output = _format_basic_result(result, "test")
        assert "Failed" in output
        assert "Ruff" in output
        assert "Tests" in output

    def test_failure_with_stderr_logging(self) -> None:
        """Failure with stderr should render structured logging section."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_basic_result,
        )

        result = self._make_result(1, "Ruff... ❌ Failed", stderr="warn line")
        output = _format_basic_result(result, "test")
        assert "Structured Logging" in output
        assert "warn line" in output


# ============================================================================
# _build_error_troubleshooting
# ============================================================================


class TestBuildErrorTroubleshooting:
    """Cover all error-type branches."""

    def test_importerror_branch(self) -> None:
        """ImportError produces package-install steps."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        steps = _build_error_troubleshooting(ImportError("nope"), 60, ".")
        assert "crackerjack" in steps
        assert "uv pip install" in steps

    def test_filenotfound_branch(self) -> None:
        """FileNotFoundError produces directory-check steps."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        steps = _build_error_troubleshooting(
            FileNotFoundError("missing"), 60, "/tmp/proj"
        )
        assert "/tmp/proj" in steps
        assert "git status" in steps

    def test_timeout_branch(self) -> None:
        """TimeoutError produces timeout-specific steps."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        steps = _build_error_troubleshooting(TimeoutError("slow"), 120, ".")
        assert "120s" in steps
        assert "--skip-hooks" in steps

    def test_timeout_via_message(self) -> None:
        """A generic error mentioning 'timeout' also triggers the timeout branch."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        steps = _build_error_troubleshooting(
            RuntimeError("Operation timeout occurred"), 60, "."
        )
        assert "60s timeout" in steps

    def test_oserror_branch(self) -> None:
        """OSError/PermissionError produces permissions steps."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        steps = _build_error_troubleshooting(
            PermissionError("denied"), 60, "."
        )
        assert "permissions" in steps

    def test_fallback_branch(self) -> None:
        """Unknown error types return generic troubleshooting."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _build_error_troubleshooting,
        )

        steps = _build_error_troubleshooting(
            ValueError("random"), 60, "."
        )
        assert "python -m crackerjack" in steps


# ============================================================================
# _format_history_output + _format_recent_executions
# ============================================================================


class TestFormatHistoryHelpers:
    """Cover history output formatting helpers."""

    def test_format_recent_executions(self) -> None:
        """Format the first 10 recent executions."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_recent_executions,
        )

        results = [
            {"timestamp": f"2024-01-0{i}T00:00:00", "content": f"run {i}"}
            for i in range(1, 4)
        ]
        output = _format_recent_executions(results)
        assert "Recent Executions" in output
        assert "run 1" in output
        assert "run 3" in output

    def test_format_history_output(self) -> None:
        """Format the full history output section."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _format_history_output,
        )

        results = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "content": "crackerjack test passed",
            },
            {
                "timestamp": "2024-01-02T00:00:00",
                "content": "crackerjack lint success",
            },
        ]
        output = _format_history_output(results, days=14)
        assert "Crackerjack History" in output
        assert "14" in output
        assert "Total Executions" in output
        assert "Recent Executions" in output


# ============================================================================
# _parse_result_timestamp
# ============================================================================


class TestParseResultTimestamp:
    """Cover string, missing, and invalid timestamp branches."""

    def test_iso_string_timestamp(self) -> None:
        """ISO string timestamp should parse to datetime."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_result_timestamp,
        )

        ts = _parse_result_timestamp(
            {"timestamp": "2024-01-01T00:00:00"}
        )
        assert ts is not None
        assert ts.year == 2024

    def test_missing_timestamp(self) -> None:
        """Missing timestamp returns None."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_result_timestamp,
        )

        assert _parse_result_timestamp({}) is None
        assert _parse_result_timestamp({"timestamp": ""}) is None

    def test_invalid_string_returns_none(self) -> None:
        """Invalid string should return None, not raise."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_result_timestamp,
        )

        assert _parse_result_timestamp({"timestamp": "not-a-date"}) is None

    def test_non_string_timestamp_returned_as_is(self) -> None:
        """Non-string timestamp value should be returned directly."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _parse_result_timestamp,
        )

        sentinel = 12345
        assert _parse_result_timestamp({"timestamp": sentinel}) == sentinel


# ============================================================================
# _crackerjack_history_impl success path
# ============================================================================


class TestCrackerjackHistoryImplSuccess:
    """Cover the success path of _crackerjack_history_impl."""

    @pytest.mark.asyncio
    async def test_history_with_results(self) -> None:
        """Should return formatted history with results."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_history_impl,
        )

        sample = [
            {
                "timestamp": "2099-01-01T00:00:00",
                "content": "crackerjack test passed",
            },
        ]

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(return_value=sample)
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_history_impl(
                command_filter="",
                days=7,
                working_directory="/tmp/proj",
            )

            assert "Crackerjack History" in result
            assert "7" in result

    @pytest.mark.asyncio
    async def test_history_exception_returns_error(self) -> None:
        """Exception path should return error string."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_history_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(
                side_effect=RuntimeError("boom")
            )
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_history_impl(
                command_filter="",
                days=7,
                working_directory=".",
            )
            assert "❌" in result
            assert "boom" in result


# ============================================================================
# _crackerjack_quality_trends_impl
# ============================================================================


class TestCrackerjackQualityTrendsImpl:
    """Cover trend analysis branches including insufficient data."""

    @pytest.mark.asyncio
    async def test_insufficient_data(self) -> None:
        """Fewer than 5 results should yield insufficient-data message."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_quality_trends_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(
                return_value=[{"timestamp": "t", "content": "ok"}]
            )
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_quality_trends_impl(
                days=30, working_directory="."
            )
            assert "Insufficient data" in result

    @pytest.mark.asyncio
    async def test_trends_excellent(self) -> None:
        """High success rate should produce excellent trend message."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_quality_trends_impl,
        )

        # 9 successes, 1 failure = 90% success
        results = [
            {"timestamp": f"t{i}", "content": "crackerjack success ✅"}
            for i in range(9)
        ] + [
            {"timestamp": "t10", "content": "crackerjack failed ❌"}
        ]

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(
                return_value=results
            )
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_quality_trends_impl(
                days=30, working_directory="."
            )
            assert "Excellent quality trend" in result

    @pytest.mark.asyncio
    async def test_trends_attention_needed(self) -> None:
        """Low success rate should produce attention-needed message."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_quality_trends_impl,
        )

        results = (
            [{"timestamp": f"s{i}", "content": "crackerjack success ✅"} for i in range(2)]
            + [{"timestamp": f"f{i}", "content": "crackerjack failed ❌"} for i in range(4)]
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db_instance = AsyncMock()
            mock_db_instance.search_conversations = AsyncMock(
                return_value=results
            )
            mock_db.return_value = mock_db_instance

            result = await _crackerjack_quality_trends_impl(
                days=30, working_directory="."
            )
            assert "Quality attention needed" in result

    @pytest.mark.asyncio
    async def test_trends_db_unavailable(self) -> None:
        """Missing database should return error message."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_quality_trends_impl,
        )

        with patch(
            "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
        ) as mock_db:
            mock_db.return_value = None
            result = await _crackerjack_quality_trends_impl(
                days=30, working_directory="."
            )
            assert "❌" in result
            assert "not available" in result.lower()


# ============================================================================
# _crackerjack_health_check_impl
# ============================================================================


class TestCrackerjackHealthCheckImpl:
    """Cover the inner impl of the health check."""

    @pytest.mark.asyncio
    async def test_health_check_integration_module_unavailable(self) -> None:
        """If integration module is missing, output reflects that."""
        import importlib

        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_health_check_impl,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="crackerjack 1.0",
                stderr="",
            )
            with patch.object(
                importlib.util,
                "find_spec",
                return_value=None,
            ):
                with patch(
                    "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
                ) as mock_db:
                    mock_db.return_value = None
                    result = await _crackerjack_health_check_impl()
        assert "Integration Module" in result
        assert "Not available" in result

    @pytest.mark.asyncio
    async def test_health_check_integration_available_with_db(self) -> None:
        """When integration and DB are both present, history is reported."""
        import importlib

        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_health_check_impl,
        )

        mock_spec = MagicMock()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="some error",
            )
            with patch.object(
                importlib.util,
                "find_spec",
                return_value=mock_spec,
            ):
                with patch(
                    "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
                ) as mock_db:
                    mock_db_instance = AsyncMock()
                    mock_db_instance.get_stats = AsyncMock(
                        return_value={"conversation_count": 7}
                    )
                    mock_db.return_value = mock_db_instance
                    result = await _crackerjack_health_check_impl()
        assert "Integration Module" in result
        assert "History Storage" in result
        assert "7" in result

    @pytest.mark.asyncio
    async def test_health_check_subprocess_generic_exception(self) -> None:
        """A generic subprocess exception surfaces as error message."""
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            _crackerjack_health_check_impl,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("unexpected")
            with patch(
                "session_buddy.mcp.tools.session.crackerjack_tools._get_reflection_db"
            ) as mock_db:
                mock_db.return_value = None
                result = await _crackerjack_health_check_impl()
        assert "Error" in result


# ============================================================================
# register_crackerjack_tools
# ============================================================================


class TestRegisterCrackerjackTools:
    """Cover tool registration via the public FastMCP API.

    Plan 7 Phase 2 removed the pre-3.x ``mcp._tools`` / ``mcp.tools`` /
    ``mcp.get_tools`` monkey-patch shim. Tool registration now goes
    exclusively through ``@tool()`` decorators; tests below assert
    the public surface is the only side effect.
    """

    EXPECTED_TOOLS = (
        "execute_crackerjack_command",
        "crackerjack_run",
        "crackerjack_history",
        "crackerjack_metrics",
        "crackerjack_patterns",
        "crackerjack_help",
        "get_crackerjack_results_history",
        "get_crackerjack_quality_metrics",
        "analyze_crackerjack_test_patterns",
        "crackerjack_quality_trends",
        "crackerjack_health_check",
        "quality_monitor",
    )

    def test_registers_all_tools_via_public_decorator(self) -> None:
        """Each tool function must be registered exactly once via ``mcp.tool()``."""
        from session_buddy.mcp.tools.session import crackerjack_tools

        mcp = MagicMock()
        crackerjack_tools.register_crackerjack_tools(mcp)

        # Public API: the ``@tool()`` decorator was invoked once per tool.
        assert mcp.tool.call_count == len(self.EXPECTED_TOOLS)
        # Plan 7 migration removed the compat shim; private / non-public
        # attributes must NOT be mutated by the registration helper.
        assert not mcp.get_tools.called, (
            "mcp.get_tools must not be monkey-patched (Plan 7 Phase 2)"
        )
        assert not hasattr(mcp, "_tools") or not mcp._tools.called, (
            "mcp._tools must not be monkey-patched (Plan 7 Phase 2)"
        )

    def test_registered_tool_callables_match_expected_functions(self) -> None:
        """Each ``mcp.tool()`` invocation must wrap the expected function."""
        from session_buddy.mcp.tools.session import crackerjack_tools

        mcp = MagicMock()
        crackerjack_tools.register_crackerjack_tools(mcp)

        registered = {
            call.args[0].__name__ for call in mcp.tool.return_value.call_args_list
        }
        assert registered == set(self.EXPECTED_TOOLS)

    @pytest.mark.asyncio
    async def test_no_get_tools_shadowing(self) -> None:
        """The pre-3.x compat shim that overwrote ``mcp.get_tools`` is gone.

        Plan 7 migration drops the closure injection of ``get_tools``
        (FastMCP 3.4 already exposes its own async ``get_tools`` method
        via ``server.get_tool(name)`` and ``server.list_tools()``).
        """
        from session_buddy.mcp.tools.session.crackerjack_tools import (
            register_crackerjack_tools,
        )

        mcp = MagicMock()
        register_crackerjack_tools(mcp)

        # ``get_tools`` should remain a MagicMock attribute (untouched),
        # not have been overwritten with a real async function.
        assert isinstance(mcp.get_tools, MagicMock)
