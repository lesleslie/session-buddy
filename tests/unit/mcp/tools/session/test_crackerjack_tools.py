"""Tests for ``session_buddy.mcp.tools.session.crackerjack_tools``.

Targets ``crackerjack_tools.py`` (1771 LOC, 9.3% baseline coverage).
Covers:
- Argument parsing helpers (``_parse_crackerjack_args``, ``_check_dangerous_chars``,
  ``_is_allowed_argument``, ``_is_flag_with_value``, ``_get_allowed_args``)
- Top-level validator wrappers (``execute_crackerjack_command``,
  ``crackerjack_run``)
- Output formatting helpers (``_format_execution_status``,
  ``_parse_crackerjack_output``, ``_parse_with_line_scanner``,
  ``_should_parse_line``, ``_extract_hook_name``, ``_categorize_hook``,
  ``_parse_hook_results_table``, ``_is_results_section_header``,
  ``_parse_hook_stage_results``, ``_extract_single_stage_results``,
  ``_should_add_to_results``, ``_is_separator_line``, ``_is_new_section_start``,
  ``_format_output_sections``, ``_format_metrics_section``,
  ``_format_basic_result``, ``_build_execution_metadata``,
  ``_store_execution_result``, ``_build_error_troubleshooting``)
- History / metrics / patterns implementations
- Quality-trends helpers
- Health check
- Registration via ``register_crackerjack_tools``
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.session import crackerjack_tools as mod
from session_buddy.mcp.tools.session.crackerjack_tools import (
    _build_error_troubleshooting,
    _build_execution_metadata,
    _calculate_execution_summary,
    _calculate_trend_success_rate,
    _categorize_hook,
    _check_dangerous_chars,
    _crackerjack_health_check_impl,
    _crackerjack_help_impl,
    _crackerjack_history_impl,
    _crackerjack_metrics_impl,
    _crackerjack_patterns_impl,
    _crackerjack_run_impl,
    _crackerjack_quality_trends_impl,
    _execute_crackerjack_command_impl,
    _extract_crackerjack_commands,
    _extract_failure_patterns,
    _extract_hook_name,
    _extract_quality_keywords,
    _extract_single_stage_results,
    _filter_results_by_date,
    _find_keyword_matches,
    _format_basic_result,
    _format_execution_status,
    _format_failure_patterns,
    _format_history_output,
    _format_metrics_section,
    _format_output_sections,
    _format_patterns_header,
    _format_quality_metrics_history,
    _format_quality_metrics_output,
    _format_recent_executions,
    _format_trend_overview,
    _format_trend_quality_insights,
    _format_trend_recommendations,
    _get_ai_recommendations_with_history,
    _get_allowed_args,
    _get_failure_keywords,
    _get_failure_pattern_results,
    _get_logger,
    _get_reflection_db,
    _is_allowed_argument,
    _is_flag_with_value,
    _is_new_section_start,
    _is_results_section_header,
    _is_separator_line,
    _parse_crackerjack_args,
    _parse_crackerjack_output,
    _parse_hook_results_table,
    _parse_hook_stage_results,
    _parse_result_timestamp,
    _parse_with_line_scanner,
    _parse_with_structured_results,
    _should_add_to_results,
    _should_parse_line,
    _store_execution_result,
    _suggest_command,
    analyze_crackerjack_test_patterns,
    crackerjack_health_check,
    crackerjack_help,
    crackerjack_history,
    crackerjack_metrics,
    crackerjack_patterns,
    crackerjack_quality_trends,
    crackerjack_run,
    execute_crackerjack_command,
    get_crackerjack_quality_metrics,
    get_crackerjack_results_history,
    quality_monitor,
    register_crackerjack_tools,
)


# ---------------------------------------------------------------------------
# _FakeMCP
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Capture-only stand-in for the FastMCP server."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    def add_tool(self, fn: Any, name: str | None = None, **_kwargs: Any) -> None:
        self.tools[name or fn.__name__] = fn


# ---------------------------------------------------------------------------
# _check_dangerous_chars
# ---------------------------------------------------------------------------


class TestCheckDangerousChars:
    @pytest.mark.parametrize(
        "char",
        [";", "|", "&", "$", "`", "(", ")", "<", ">", "\n", "\r"],
    )
    def test_each_dangerous_char_raises(self, char: str) -> None:
        with pytest.raises(ValueError, match="Dangerous character"):
            _check_dangerous_chars(f"x{char}y")

    def test_safe_string_passes(self) -> None:
        _check_dangerous_chars("--verbose")


# ---------------------------------------------------------------------------
# _is_allowed_argument
# ---------------------------------------------------------------------------


class TestIsAllowedArgument:
    def test_simple_allowed(self) -> None:
        assert _is_allowed_argument("--verbose", {"--verbose", "--strict"})

    def test_simple_disallowed(self) -> None:
        assert not _is_allowed_argument("--unknown", {"--verbose"})

    def test_keyvalue_allowed(self) -> None:
        assert _is_allowed_argument("--output=json", {"--output"})

    def test_keyvalue_unknown(self) -> None:
        assert not _is_allowed_argument("--unknown=v", {"--output"})

    def test_arg_n_pattern(self) -> None:
        assert _is_allowed_argument("--arg1", set())
        assert _is_allowed_argument("--arg42", set())

    def test_keyvalue_arg_n_pattern(self) -> None:
        assert _is_allowed_argument("--arg5=foo", set())


# ---------------------------------------------------------------------------
# _is_flag_with_value
# ---------------------------------------------------------------------------


class TestIsFlagWithValue:
    @pytest.mark.parametrize("flag", ["--severity", "--confidence", "--output", "--platform"])
    def test_known_flags(self, flag: str) -> None:
        assert _is_flag_with_value(flag) is True

    def test_unknown_flag(self) -> None:
        assert _is_flag_with_value("--verbose") is False


# ---------------------------------------------------------------------------
# _get_allowed_args
# ---------------------------------------------------------------------------


class TestGetAllowedArgs:
    def test_returns_set(self) -> None:
        args = _get_allowed_args()
        assert isinstance(args, set)
        assert "--verbose" in args
        assert "--strict" in args
        assert "--coverage" in args


# ---------------------------------------------------------------------------
# _parse_crackerjack_args
# ---------------------------------------------------------------------------


class TestParseCrackerjackArgs:
    def test_empty_returns_empty(self) -> None:
        assert _parse_crackerjack_args("") == []
        assert _parse_crackerjack_args("   ") == []

    def test_simple_flags(self) -> None:
        assert _parse_crackerjack_args("--verbose --strict") == ["--verbose", "--strict"]

    def test_quoted_value_with_allowed_token(self) -> None:
        # When a known allow-listed token is quoted (e.g. ``--output "verbose"``),
        # shlex produces two tokens; the second token is consumed as the value
        # of ``--output`` because ``--output`` is in ``FLAGS_WITH_VALUES``.
        tokens = _parse_crackerjack_args('--output "verbose"')
        assert tokens == ["--output", "verbose"]

    def test_dangerous_char_raises(self) -> None:
        with pytest.raises(ValueError, match="Dangerous character"):
            _parse_crackerjack_args("--verbose; rm -rf /")

    def test_unknown_arg_raises(self) -> None:
        with pytest.raises(ValueError, match="Blocked argument"):
            _parse_crackerjack_args("--totally-unknown")

    def test_invalid_shlex_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid argument syntax"):
            _parse_crackerjack_args("\"unterminated")

    def test_keyvalue_normalized_into_pair(self) -> None:
        # ``--output=foo`` should normalize to ``["--output", "foo"]``.
        tokens = _parse_crackerjack_args("--output=json")
        assert tokens == ["--output", "json"]

    def test_flag_with_value_consumes_next_token(self) -> None:
        # ``--severity high`` is consumed together because --severity is in FLAGS_WITH_VALUES.
        tokens = _parse_crackerjack_args("--severity high")
        assert tokens == ["--severity", "high"]


# ---------------------------------------------------------------------------
# execute_crackerjack_command / crackerjack_run validators
# ---------------------------------------------------------------------------


class TestExecuteCrackerjackCommandValidator:
    @pytest.mark.asyncio
    async def test_rejects_flag_command(self) -> None:
        out = await execute_crackerjack_command(command="--ai-fix -t")
        assert "Invalid Command" in out
        assert "--ai-fix" in out

    @pytest.mark.asyncio
    async def test_rejects_unknown_command(self) -> None:
        out = await execute_crackerjack_command(command="frobnicate")
        assert "Unknown Command" in out
        # Suggestion should be a valid command (fuzzy match fallback).
        assert "Did you mean" in out

    @pytest.mark.asyncio
    async def test_rejects_ai_fix_in_args(self) -> None:
        out = await execute_crackerjack_command(command="test", args="--ai-fix")
        assert "Invalid Args" in out
        assert "ai_agent_mode" in out

    @pytest.mark.asyncio
    async def test_delegates_to_impl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "delegated-ok"

        monkeypatch.setattr(mod, "_execute_crackerjack_command_impl", fake_impl)
        out = await execute_crackerjack_command(command="test")
        assert out == "delegated-ok"


class TestCrackerjackRunValidator:
    @pytest.mark.asyncio
    async def test_rejects_flag_command(self) -> None:
        out = await crackerjack_run(command="--ai-fix -t")
        assert "Invalid Command" in out

    @pytest.mark.asyncio
    async def test_rejects_unknown_command(self) -> None:
        out = await crackerjack_run(command="frobnicate")
        assert "Unknown Command" in out

    @pytest.mark.asyncio
    async def test_rejects_ai_fix_in_args(self) -> None:
        out = await crackerjack_run(command="test", args="--ai-fix")
        assert "Invalid Args" in out

    @pytest.mark.asyncio
    async def test_delegates_to_impl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "delegated-ok"

        monkeypatch.setattr(mod, "_crackerjack_run_impl", fake_impl)
        out = await crackerjack_run(command="test")
        assert out == "delegated-ok"


# ---------------------------------------------------------------------------
# _execute_crackerjack_command_impl
# ---------------------------------------------------------------------------


class TestExecuteCrackerjackCommandImpl:
    @pytest.mark.asyncio
    async def test_import_error_returns_friendly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "session_buddy.crackerjack_integration":
                raise ImportError("blocked")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        out = await _execute_crackerjack_command_impl(command="test")
        assert "Crackerjack integration not available" in out

    @pytest.mark.asyncio
    async def test_exception_returns_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("boom")

        class FakeIntegration:
            async def execute_crackerjack_command(self, *args: Any, **kwargs: Any) -> Any:
                return await boom()

        # Patch the CrackerjackIntegration class.
        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        out = await _execute_crackerjack_command_impl(command="test")
        assert "Crackerjack execution failed" in out

    @pytest.mark.asyncio
    async def test_success_includes_sections(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = MagicMock()
        result.exit_code = 0
        result.stdout = "hello\n"
        result.stderr = ""
        result.quality_metrics = {}
        result.execution_time = 1.5
        result.memory_insights = []
        result.working_directory = "/wd"

        class FakeIntegration:
            async def execute_crackerjack_command(self, *args: Any, **kwargs: Any) -> Any:
                return result

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )

        out = await _execute_crackerjack_command_impl(command="test")
        assert "Crackerjack test" in out
        assert "Status" in out
        assert "hello" in out


# ---------------------------------------------------------------------------
# _format_execution_status
# ---------------------------------------------------------------------------


class TestFormatExecutionStatus:
    def test_success_with_hooks(self) -> None:
        result = MagicMock()
        result.exit_code = 0
        result.stdout = ""
        result.stderr = ""
        out = _format_execution_status(result)
        assert "Success" in out

    def test_failure_includes_stderr(self) -> None:
        result = MagicMock()
        result.exit_code = 1
        result.stdout = ""
        result.stderr = "something errored"
        out = _format_execution_status(result)
        assert "Failed" in out
        assert "Error Details" in out

    def test_failure_without_error_keyword(self) -> None:
        result = MagicMock()
        result.exit_code = 1
        result.stdout = ""
        result.stderr = "warning only"
        out = _format_execution_status(result)
        assert "Failed" in out
        # No error keyword → no Error Details block.
        assert "Error Details" not in out


# ---------------------------------------------------------------------------
# _parse_crackerjack_output / structured + line-scanner
# ---------------------------------------------------------------------------


class TestParseCrackerjackOutput:
    def test_structured_path(self) -> None:
        # The structured parser succeeds → no fallback to line scanner.
        passed, failed = _parse_crackerjack_output("hookname ... Passed")
        # structured parser may produce empty list if line doesn't match structured
        # format; line scanner is the fallback. We just need both to be lists.
        assert isinstance(passed, list)
        assert isinstance(failed, list)


class TestParseWithLineScanner:
    def test_passes_and_fails(self) -> None:
        text = (
            "some line\n"
            "hook1 ... ✅ Passed\n"
            "hook2 ... ❌ Failed\n"
            "another line\n"
        )
        passed, failed = _parse_with_line_scanner(text)
        assert "hook1" in passed
        assert "hook2" in failed


class TestShouldParseLine:
    def test_valid_line(self) -> None:
        assert _should_parse_line("hook ... ✅ Passed") is True

    def test_no_marker(self) -> None:
        assert _should_parse_line("hook ... something") is False

    def test_no_dots(self) -> None:
        assert _should_parse_line("hook Passed") is False


class TestExtractHookName:
    def test_extracts_first_segment(self) -> None:
        assert _extract_hook_name("hook1 ... Passed") == "hook1"

    def test_empty_returns_none(self) -> None:
        assert _extract_hook_name("... bare") is None

    def test_leading_dash_returns_none(self) -> None:
        assert _extract_hook_name("-hook ... Passed") is None


class TestCategorizeHook:
    def test_failure_marker(self) -> None:
        passed: list[str] = []
        failed: list[str] = []
        _categorize_hook("hook", "hook ... ❌ Failed", passed, failed)
        assert passed == []
        assert failed == ["hook"]

    def test_pass_marker(self) -> None:
        passed: list[str] = []
        failed: list[str] = []
        _categorize_hook("hook", "hook ... ✅ Passed", passed, failed)
        assert passed == ["hook"]
        assert failed == []

    def test_neither_marker(self) -> None:
        passed: list[str] = []
        failed: list[str] = []
        _categorize_hook("hook", "hook ... neutral", passed, failed)
        assert passed == []
        assert failed == []


class TestParseWithStructuredResults:
    def test_returns_lists(self) -> None:
        passed, failed = _parse_with_structured_results("hookname ... Passed")
        assert isinstance(passed, list)
        assert isinstance(failed, list)


# ---------------------------------------------------------------------------
# _parse_hook_results_table / stage parsing
# ---------------------------------------------------------------------------


class TestParseHookResultsTable:
    def test_empty_returns_empty(self) -> None:
        assert _parse_hook_results_table("nothing relevant here") == ""

    def test_results_section_header(self) -> None:
        out = _parse_hook_results_table("Fast Hook Results:\n--------\nhook ... ok\n")
        assert "Fast Hook Results:" in out


class TestIsResultsSectionHeader:
    @pytest.mark.parametrize("line", ["Fast Hook Results:", "Comprehensive Hook Results:"])
    def test_recognized(self, line: str) -> None:
        assert _is_results_section_header(line) is True

    def test_unrecognized(self) -> None:
        assert _is_results_section_header("Random section") is False


class TestParseHookStageResults:
    def test_empty(self) -> None:
        assert _parse_hook_stage_results("nothing here") == ""

    def test_single_stage(self) -> None:
        text = (
            "Fast Hook Results:\n"
            "----------\n"
            "hook ... ✅ Passed\n"
        )
        out = _parse_hook_stage_results(text)
        assert "Fast Hook Results:" in out


class TestExtractSingleStageResults:
    def test_minimal(self) -> None:
        lines = ["Fast Hook Results:", "----------", "hook ... ok", "⏳ Started:"]
        out = _extract_single_stage_results(lines, 0)
        assert out[0] == "Fast Hook Results:"

    def test_terminates_at_new_section(self) -> None:
        lines = ["Fast Hook Results:", "----------", "⏳ Started: next"]
        out = _extract_single_stage_results(lines, 0)
        # Should stop before the "Started" line.
        assert all("Started" not in line for line in out)


class TestShouldAddToResults:
    def test_blank_line(self) -> None:
        assert _should_add_to_results("") is True

    def test_dash_only_separator_line(self) -> None:
        # Pure dashes don't have a space so ``_is_separator_line`` returns False;
        # however the blank-or-double-colon branches make this a non-result line
        # only via the separator detector. A pure-dash line below the 10-char
        # threshold actually falls through to "False" — exercise the threshold.
        assert _should_add_to_results("-") is False

    def test_has_double_colon(self) -> None:
        assert _should_add_to_results("hello::world") is True

    def test_other(self) -> None:
        assert _should_add_to_results("hello world") is False


class TestIsSeparatorLine:
    def test_dashes_only_with_space(self) -> None:
        # Per the function definition, a "separator" must be only dashes
        # and spaces; pure dashes don't qualify because no space is present.
        assert _is_separator_line("--------") is False

    def test_mixed_with_spaces(self) -> None:
        # At least 10 chars of only dashes-and-spaces.
        assert _is_separator_line("-- -- -- --") is True

    def test_short_string(self) -> None:
        assert _is_separator_line("--") is False  # len < 10

    def test_underscore_only(self) -> None:
        # Underscores aren't separators by this definition.
        assert _is_separator_line("__________") is False


class TestIsNewSectionStart:
    @pytest.mark.parametrize("line", ["⏳ Started:", "Workflow", "Building"])
    def test_recognized(self, line: str) -> None:
        assert _is_new_section_start(line) is True

    def test_unrecognized(self) -> None:
        assert _is_new_section_start("nothing here") is False


# ---------------------------------------------------------------------------
# _format_output_sections
# ---------------------------------------------------------------------------


class TestFormatOutputSections:
    def test_stdout_only(self) -> None:
        result = MagicMock(stdout="hello", stderr="")
        out = _format_output_sections(result)
        assert "Output" in out
        assert "hello" in out
        assert "Errors" not in out

    def test_stderr_only(self) -> None:
        result = MagicMock(stdout="", stderr="bad")
        out = _format_output_sections(result)
        assert "Errors" in out
        assert "Output" not in out

    def test_both(self) -> None:
        result = MagicMock(stdout="hi", stderr="bad")
        out = _format_output_sections(result)
        assert "Output" in out
        assert "Errors" in out


# ---------------------------------------------------------------------------
# _format_metrics_section
# ---------------------------------------------------------------------------


class TestFormatMetricsSection:
    def test_unavailable_branch(self) -> None:
        result = MagicMock()
        result.quality_metrics = {"unavailable": True}
        result.memory_insights = ["one"]
        result.working_directory = "/wd"

        out = _format_metrics_section(result)
        assert "Quality metrics unavailable" in out
        assert "Notes" in out
        assert "/wd" in out

    def test_normal_metrics(self) -> None:
        result = MagicMock()
        result.quality_metrics = {
            "code_quality": 30.0,
            "test_coverage": 80.0,
            "security_score": 9.0,
        }
        result.execution_time = 1.5
        result.exit_code = 0
        result.memory_insights = ["a", "b", "c", "d", "e", "f"]

        out = _format_metrics_section(result)
        assert "Code Quality" in out
        assert "Execution time" in out
        # Memory insights should be truncated to top 5.
        assert "f" not in out

    def test_exit_code_nonzero(self) -> None:
        result = MagicMock()
        result.quality_metrics = {}
        result.execution_time = 0.5
        result.exit_code = 2
        result.memory_insights = []
        out = _format_metrics_section(result)
        assert "Exit code: 2" in out

    def test_metric_with_none_value(self) -> None:
        result = MagicMock()
        result.quality_metrics = {"foo": None}
        result.execution_time = None
        result.exit_code = 0
        result.memory_insights = None

        out = _format_metrics_section(result)
        assert "unavailable" in out


# ---------------------------------------------------------------------------
# _format_basic_result
# ---------------------------------------------------------------------------


class TestFormatBasicResult:
    def test_success(self) -> None:
        result = MagicMock()
        result.exit_code = 0
        result.stdout = "out"
        result.stderr = "err"
        out = _format_basic_result(result, "test")
        assert "Success" in out
        assert "out" in out
        assert "err" in out

    def test_failure_includes_hooks(self) -> None:
        result = MagicMock()
        result.exit_code = 1
        result.stdout = "hook1 ... ✅ Passed\nhook2 ... ❌ Failed"
        result.stderr = ""
        out = _format_basic_result(result, "test")
        assert "Failed" in out
        assert "hook1" in out
        assert "hook2" in out


# ---------------------------------------------------------------------------
# _build_execution_metadata / _store_execution_result
# ---------------------------------------------------------------------------


class TestBuildExecutionMetadata:
    def test_minimal(self) -> None:
        result = MagicMock(exit_code=0, execution_time=1.0)
        metrics = MagicMock()
        metrics.to_dict.return_value = {"a": 1}
        meta = _build_execution_metadata("/wd", result, metrics)
        assert meta["project"] == Path("/wd").name
        assert meta["exit_code"] == 0
        assert meta["execution_time"] == 1.0
        assert meta["metrics"] == {"a": 1}

    def test_with_recommendations_and_history(self) -> None:
        result = MagicMock(exit_code=1, execution_time=2.0)
        metrics = MagicMock()
        metrics.to_dict.return_value = {}

        rec = MagicMock()
        rec.agent.value = "tester"
        rec.confidence = 0.9
        rec.reason = "because"
        rec.quick_fix_command = "fix-it"

        history = {
            "patterns": [1, 2, 3],
            "total_executions": 5,
            "insights": ["a", "b", "c"],
        }

        meta = _build_execution_metadata(
            "/wd", result, metrics, recommendations=[rec], history_analysis=history
        )
        assert meta["agent_recommendations"][0]["agent"] == "tester"
        assert meta["pattern_analysis"]["total_patterns"] == 3


class TestStoreExecutionResult:
    @pytest.mark.asyncio
    async def test_ai_mode_failure_stores_via_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = MagicMock(exit_code=1, execution_time=0.1)
        metrics = MagicMock()
        db = AsyncMock()
        msg = await _store_execution_result(
            "test",
            "formatted",
            result,
            metrics,
            "/wd",
            ai_agent_mode=True,
            db=db,
        )
        assert "Execution stored" in msg
        db.store_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = MagicMock(exit_code=0, execution_time=0.1)
        metrics = MagicMock()

        async def fake_db() -> None:
            return None

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)

        msg = await _store_execution_result(
            "test",
            "formatted",
            result,
            metrics,
            "/wd",
            ai_agent_mode=False,
        )
        assert msg == ""

    @pytest.mark.asyncio
    async def test_exception_silenced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class ExplodingDB:
            async def store_conversation(self, *args: Any, **kwargs: Any) -> Any:
                raise OSError("disk gone")

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        result = MagicMock(exit_code=1, execution_time=0.1)
        metrics = MagicMock()
        db = ExplodingDB()
        msg = await _store_execution_result(
            "test",
            "formatted",
            result,
            metrics,
            "/wd",
            ai_agent_mode=False,
            db=db,
        )
        # No exception bubbles up.
        assert msg == ""


# ---------------------------------------------------------------------------
# _suggest_command
# ---------------------------------------------------------------------------


class TestSuggestCommand:
    def test_returns_close_match(self) -> None:
        assert _suggest_command("tets", {"test", "lint"}) == "test"

    def test_returns_fallback_when_no_match(self) -> None:
        assert _suggest_command("zzz", {"test", "lint"}) == "check"


# ---------------------------------------------------------------------------
# _build_error_troubleshooting
# ---------------------------------------------------------------------------


class TestBuildErrorTroubleshooting:
    def test_importerror(self) -> None:
        out = _build_error_troubleshooting(ImportError("missing"), 60, "/wd")
        assert "crackerjack" in out.lower()

    def test_filenotfounderror(self) -> None:
        out = _build_error_troubleshooting(FileNotFoundError("missing"), 60, "/wd")
        assert "/wd" in out

    def test_timeout_error(self) -> None:
        out = _build_error_troubleshooting(TimeoutError("slow"), 60, "/wd")
        assert "60" in out

    def test_oserror(self) -> None:
        out = _build_error_troubleshooting(OSError("denied"), 60, "/wd")
        assert "permissions" in out.lower() or "write access" in out.lower()

    def test_fallback_for_other(self) -> None:
        out = _build_error_troubleshooting(ValueError("misc"), 60, "/wd")
        assert "crackerjack" in out.lower() or "logs" in out.lower()


# ---------------------------------------------------------------------------
# _crackerjack_run_impl
# ---------------------------------------------------------------------------


class TestCrackerjackRunImpl:
    @pytest.mark.asyncio
    async def test_import_error_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "session_buddy.crackerjack_integration":
                raise ImportError("blocked")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        out = await _crackerjack_run_impl(command="test")
        assert "Enhanced crackerjack run failed" in out

    @pytest.mark.asyncio
    async def test_success_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = MagicMock()
        result.exit_code = 0
        result.stdout = "ok"
        result.stderr = ""

        class FakeIntegration:
            async def execute_crackerjack_command(self, *args: Any, **kwargs: Any) -> Any:
                return result

        class FakeMetrics:
            def __init__(self) -> None:
                pass

            def format_for_display(self) -> str:
                return ""

            def to_dict(self) -> dict[str, Any]:
                return {}

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        monkeypatch.setattr(
            "session_buddy.tools.quality_metrics.QualityMetricsExtractor",
            MagicMock(extract=lambda *a, **k: FakeMetrics()),
        )
        # Skip storage to avoid reflection DB requirement.
        async def fake_store(*args: Any, **kwargs: Any) -> str:
            return ""

        monkeypatch.setattr(mod, "_store_execution_result", fake_store)

        out = await _crackerjack_run_impl(command="test", working_directory="/wd")
        assert "Crackerjack test" in out

    @pytest.mark.asyncio
    async def test_failure_path_uses_ai_recommendations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = MagicMock()
        result.exit_code = 1
        result.stdout = "failed"
        result.stderr = ""

        class FakeIntegration:
            async def execute_crackerjack_command(self, *args: Any, **kwargs: Any) -> Any:
                return result

        class FakeMetrics:
            def __init__(self) -> None:
                pass

            def format_for_display(self) -> str:
                return ""

            def to_dict(self) -> dict[str, Any]:
                return {}

        async def fake_ai(*args: Any, **kwargs: Any) -> tuple[str, list[Any], dict[str, Any]]:
            return ("\nAI advice\n", [], {})

        async def fake_store(*args: Any, **kwargs: Any) -> str:
            return ""

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        monkeypatch.setattr(
            "session_buddy.tools.quality_metrics.QualityMetricsExtractor",
            MagicMock(extract=lambda *a, **k: FakeMetrics()),
        )
        monkeypatch.setattr(mod, "_get_ai_recommendations_with_history", fake_ai)
        monkeypatch.setattr(mod, "_store_execution_result", fake_store)

        out = await _crackerjack_run_impl(command="test", working_directory="/wd")
        assert "Failed" in out
        assert "AI advice" in out


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


class TestExtractCrackerjackCommands:
    def test_filters_by_keyword(self) -> None:
        results = [
            {"content": "crackerjack test ran"},
            {"content": "crackerjack lint ran"},
            {"content": "no command here"},
        ]
        out = _extract_crackerjack_commands(results)
        # The regex normalizes "crackerjack test" → command name "test".
        assert "test" in out
        assert "lint" in out
        assert len(out) == 2

    def test_groups_duplicate_commands(self) -> None:
        results = [
            {"content": "crackerjack test ran"},
            {"content": "crackerjack test ran again"},
        ]
        out = _extract_crackerjack_commands(results)
        assert "test" in out
        assert len(out["test"]) == 2

    def test_no_crack_keyword_excluded(self) -> None:
        results = [{"content": "just a normal line"}]
        out = _extract_crackerjack_commands(results)
        assert out == {}


class TestFormatRecentExecutions:
    def test_caps_at_ten(self) -> None:
        results = [{"timestamp": "t", "content": f"exec-{i}"} for i in range(15)]
        out = _format_recent_executions(results)
        assert "exec-0" in out
        assert "exec-9" in out
        assert "exec-10" not in out


class TestParseResultTimestamp:
    def test_iso_string(self) -> None:
        result = {"timestamp": "2026-01-01T00:00:00"}
        ts = _parse_result_timestamp(result)
        assert ts is not None
        assert ts.year == 2026

    def test_passthrough_datetime(self) -> None:
        from datetime import datetime

        ts = datetime(2026, 1, 1)
        result = {"timestamp": ts}
        assert _parse_result_timestamp(result) == ts

    def test_missing(self) -> None:
        assert _parse_result_timestamp({}) is None

    def test_invalid_string(self) -> None:
        result = {"timestamp": "not-a-date"}
        assert _parse_result_timestamp(result) is None


class TestFilterResultsByDate:
    def test_includes_results_without_date(self) -> None:
        results = [{"timestamp": "bad"}, {"timestamp": "2026-01-01T00:00:00"}]
        from datetime import datetime, timezone

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = _filter_results_by_date(results, start)
        # Both should be included (bad timestamp always included; explicit past one too).
        assert len(out) == 2

    def test_filters_out_old_results(self) -> None:
        from datetime import datetime, timezone

        results = [{"timestamp": "2020-01-01T00:00:00"}]
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = _filter_results_by_date(results, start)
        assert out == []

    def test_naive_datetime_normalized(self) -> None:
        from datetime import datetime, timezone

        results = [{"timestamp": "2026-01-01T00:00:00"}]
        # Naive start date — code should normalize it to UTC.
        start = datetime(2026, 1, 1)
        out = _filter_results_by_date(results, start)
        assert len(out) == 1


class TestFormatHistoryOutput:
    def test_includes_total(self) -> None:
        results = [{"timestamp": "t", "content": "crackerjack test"}]
        out = _format_history_output(results, 7)
        assert "Crackerjack History" in out
        assert "last 7 days" in out
        assert "crackerjack test" in out


class TestCrackerjackHistoryImpl:
    @pytest.mark.asyncio
    async def test_no_db_returns_friendly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_db() -> None:
            return None

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_history_impl()
        assert "Reflection database not available" in out

    @pytest.mark.asyncio
    async def test_empty_results_returns_no_executions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeDB:
            async def search_conversations(self, *args: Any, **kwargs: Any) -> list[Any]:
                return []

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        async def fake_db() -> Any:
            return FakeDB()

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_history_impl()
        assert "No crackerjack executions" in out

    @pytest.mark.asyncio
    async def test_exception_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_db() -> Any:
            raise RuntimeError("db boom")

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_history_impl()
        assert "History retrieval failed" in out


# ---------------------------------------------------------------------------
# Quality metrics helpers
# ---------------------------------------------------------------------------


class TestCalculateExecutionSummary:
    def test_empty(self) -> None:
        assert _calculate_execution_summary([]) == {
            "total": 0,
            "success": 0,
            "failure": 0,
            "success_rate": 0,
        }

    def test_mixed(self) -> None:
        results = [{"content": "success pass"}, {"content": "failure"}]
        out = _calculate_execution_summary(results)
        assert out["total"] == 2
        assert out["success"] == 1
        assert out["failure"] == 1
        assert out["success_rate"] == 50.0


class TestExtractQualityKeywords:
    def test_counts(self) -> None:
        results = [{"content": "lint issue"}, {"content": "lint and test"}, {"content": "security"}]
        out = _extract_quality_keywords(results)
        assert out["lint"] == 2
        assert out["test"] == 1
        assert out["security"] == 1


class TestFormatQualityMetricsOutput:
    def test_with_keywords(self) -> None:
        out = _format_quality_metrics_output(
            7,
            {"total": 5, "success": 3, "failure": 2, "success_rate": 60.0},
            {"lint": 3, "test": 1},
        )
        assert "60.0%" in out
        assert "Lint" in out


# ---------------------------------------------------------------------------
# Patterns helpers
# ---------------------------------------------------------------------------


class TestFindKeywordMatches:
    def test_multiple_matches(self) -> None:
        matches = _find_keyword_matches("foo bar foo", "foo")
        assert matches == [(0, 3), (8, 11)]

    def test_no_match(self) -> None:
        assert _find_keyword_matches("xyz", "foo") == []


class TestExtractFailurePatterns:
    def test_patterns(self) -> None:
        results = [{"content": "test failed and error happened"}]
        out = _extract_failure_patterns(results, ["failed", "error"])
        # We should record contexts around each keyword occurrence.
        assert out

    def test_no_patterns(self) -> None:
        results = [{"content": "all good"}]
        out = _extract_failure_patterns(results, ["failed", "error"])
        assert out == {}


class TestFormatFailurePatterns:
    def test_empty(self) -> None:
        out = _format_failure_patterns({})
        assert "No clear failure patterns" in out

    def test_caps_at_ten(self) -> None:
        # Top 10 patterns by count. Key the dict by count so sort order is
        # deterministic: "pat0" has count 0, "pat14" has count 14. The function
        # emits the top 10 by count (descending), starting at 1.
        patterns = {f"pat{i:02d}": i for i in range(15)}
        out = _format_failure_patterns(patterns)
        # Highest counts (pat14 down to pat05) appear.
        assert "pat14" in out
        assert "pat05" in out
        # The lowest-count patterns are excluded.
        assert "pat00" not in out
        assert "pat01" not in out


class TestGetFailureKeywords:
    def test_returns_list(self) -> None:
        assert _get_failure_keywords() == [
            "failed",
            "error",
            "exception",
            "assertion",
            "timeout",
        ]


class TestCrackerjackPatternsImpl:
    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_results(*args: Any, **kwargs: Any) -> list[Any]:
            return []

        monkeypatch.setattr(mod, "_get_failure_pattern_results", fake_results)
        out = await _crackerjack_patterns_impl()
        assert "No test failure patterns" in out

    @pytest.mark.asyncio
    async def test_with_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_results(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return [
                {"content": "test failed and error happened"},
                {"content": "another failed run"},
            ]

        monkeypatch.setattr(mod, "_get_failure_pattern_results", fake_results)
        out = await _crackerjack_patterns_impl()
        assert "Test Failure Patterns" in out

    @pytest.mark.asyncio
    async def test_exception_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_results(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("patterns fail")

        monkeypatch.setattr(mod, "_get_failure_pattern_results", fake_results)
        out = await _crackerjack_patterns_impl()
        assert "Pattern analysis failed" in out


# ---------------------------------------------------------------------------
# Help / health check
# ---------------------------------------------------------------------------


class TestCrackerjackHelpImpl:
    @pytest.mark.asyncio
    async def test_returns_help(self) -> None:
        out = await _crackerjack_help_impl()
        assert "Crackerjack Command Guide" in out
        assert "MCP Integration" in out


class TestCrackerjackHealthCheckImpl:
    @pytest.mark.asyncio
    async def test_handles_missing_subprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio as real_asyncio
        import subprocess as real_subprocess

        async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            r = MagicMock()
            r.returncode = 0
            r.stdout = "crackerjack 1.0"
            r.stderr = ""
            return r

        monkeypatch.setattr(real_asyncio, "to_thread", fake_to_thread)
        # Mark integration as available via the importlib find_spec probe.
        import importlib.util as _ilu

        monkeypatch.setattr(_ilu, "find_spec", lambda name: object())
        # Reflection DB unavailable.
        async def fake_db() -> None:
            return None

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)

        out = await _crackerjack_health_check_impl()
        assert "Crackerjack Health Check" in out
        assert "Available" in out

    @pytest.mark.asyncio
    async def test_timeout_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import asyncio as real_asyncio
        import subprocess as real_subprocess

        async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            raise real_subprocess.TimeoutExpired(cmd="python", timeout=10)

        monkeypatch.setattr(real_asyncio, "to_thread", fake_to_thread)

        out = await _crackerjack_health_check_impl()
        assert "Timeout" in out

    @pytest.mark.asyncio
    async def test_filenotfound_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import asyncio as real_asyncio

        async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("no python")

        monkeypatch.setattr(real_asyncio, "to_thread", fake_to_thread)

        out = await _crackerjack_health_check_impl()
        assert "Not found" in out

    @pytest.mark.asyncio
    async def test_integration_module_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio as real_asyncio
        import importlib.util as _ilu

        async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            r = MagicMock()
            r.returncode = 1
            r.stdout = ""
            r.stderr = "bad"
            return r

        monkeypatch.setattr(real_asyncio, "to_thread", fake_to_thread)
        # Pretend importlib can't find the integration module.
        monkeypatch.setattr(_ilu, "find_spec", lambda name: None)
        # Reflection DB OK with stats.
        class FakeDB:
            async def get_stats(self) -> dict[str, Any]:
                return {"conversation_count": 7}

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        async def fake_db() -> Any:
            return FakeDB()

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)

        out = await _crackerjack_health_check_impl()
        assert "Not working properly" in out
        assert "Not available" in out
        assert "Conversations: 7" in out


# ---------------------------------------------------------------------------
# Quality trends helpers
# ---------------------------------------------------------------------------


class TestFormatInsufficientTrendData:
    def test_appends_message(self) -> None:
        out = mod._format_insufficient_trend_data("header\n")
        assert "Insufficient data" in out


class TestAnalyzeQualityTrendResults:
    def test_mixed(self) -> None:
        results = [
            {"content": "successful run", "timestamp": "t1"},
            {"content": "failed run", "timestamp": "t2"},
            {"content": "✅ ok", "timestamp": "t3"},
            {"content": "❌ bad", "timestamp": "t4"},
        ]
        success, failure = mod._analyze_quality_trend_results(results)
        assert "t1" in success
        assert "t3" in success
        assert "t2" in failure
        assert "t4" in failure


class TestCalculateTrendSuccessRate:
    def test_zero_runs(self) -> None:
        assert _calculate_trend_success_rate([], []) == 0

    def test_only_success(self) -> None:
        assert _calculate_trend_success_rate(["a", "b"], []) == 100.0

    def test_mixed(self) -> None:
        assert _calculate_trend_success_rate(["a"], ["a", "a"]) == pytest.approx(33.333, rel=0.01)


class TestFormatTrendOverview:
    def test_basic(self) -> None:
        out = _format_trend_overview(["a", "b"], ["a"], 66.6)
        assert "Total quality runs: 3" in out
        assert "66.6%" in out


class TestFormatTrendQualityInsights:
    def test_excellent(self) -> None:
        assert "Excellent" in _format_trend_quality_insights(85)

    def test_good(self) -> None:
        assert "Good" in _format_trend_quality_insights(70)

    def test_attention_needed(self) -> None:
        assert "attention" in _format_trend_quality_insights(40).lower()


class TestFormatTrendRecommendations:
    def test_low(self) -> None:
        out = _format_trend_recommendations(50)
        assert "ai-fix" in out

    def test_high(self) -> None:
        out = _format_trend_recommendations(80)
        assert "Maintain" in out


class TestCrackerjackQualityTrendsImpl:
    @pytest.mark.asyncio
    async def test_no_db_returns_friendly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_db() -> None:
            return None

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_quality_trends_impl()
        assert "Reflection database not available" in out

    @pytest.mark.asyncio
    async def test_insufficient_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeDB:
            async def search_conversations(self, *args: Any, **kwargs: Any) -> list[Any]:
                return []

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        async def fake_db() -> Any:
            return FakeDB()

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_quality_trends_impl()
        assert "Insufficient data" in out

    @pytest.mark.asyncio
    async def test_with_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeDB:
            async def search_conversations(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                # Need >= 5 results to avoid the insufficient-data branch.
                return [
                    {"content": "success", "timestamp": "t1"},
                    {"content": "failed", "timestamp": "t2"},
                    {"content": "✅ ok", "timestamp": "t3"},
                    {"content": "❌ bad", "timestamp": "t4"},
                    {"content": "success again", "timestamp": "t5"},
                ]

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        async def fake_db() -> Any:
            return FakeDB()

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_quality_trends_impl()
        assert "Quality Trends Analysis" in out
        assert "Total quality runs" in out

    @pytest.mark.asyncio
    async def test_exception_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_db() -> Any:
            raise RuntimeError("trends boom")

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        out = await _crackerjack_quality_trends_impl()
        assert "Trend analysis failed" in out


# ---------------------------------------------------------------------------
# Metrics impl
# ---------------------------------------------------------------------------


class TestCrackerjackMetricsImpl:
    @pytest.mark.asyncio
    async def test_legacy_path_no_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force the primary integration path to raise so we fall through.
        async def fake_integration_get(*args: Any, **kwargs: Any) -> list[Any]:
            raise RuntimeError("primary fail")

        async def fake_unavailable(*args: Any, **kwargs: Any) -> bool:
            return False

        async def fake_db() -> None:
            return None

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.get_quality_metrics_history",
            fake_integration_get,
        )
        monkeypatch.setattr(mod, "_latest_crackerjack_result_unavailable", fake_unavailable)
        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)

        out = await _crackerjack_metrics_impl(working_directory="/wd")
        assert "Reflection database not available" in out

    @pytest.mark.asyncio
    async def test_legacy_path_with_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_integration_get(*args: Any, **kwargs: Any) -> list[Any]:
            raise RuntimeError("primary fail")

        async def fake_unavailable(*args: Any, **kwargs: Any) -> bool:
            return False

        class FakeDB:
            async def search_conversations(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                return [{"content": "lint issue"}, {"content": "test failure"}]

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        async def fake_db() -> Any:
            return FakeDB()

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.get_quality_metrics_history",
            fake_integration_get,
        )
        monkeypatch.setattr(mod, "_latest_crackerjack_result_unavailable", fake_unavailable)
        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)

        out = await _crackerjack_metrics_impl(working_directory="/wd")
        assert "Quality Metrics" in out
        assert "Execution Summary" in out

    @pytest.mark.asyncio
    async def test_primary_path_with_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_integration_get(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "id": 1,
                    "metric_type": "test_coverage",
                    "metric_value": 85.0,
                    "timestamp": "2026-01-01",
                }
            ]

        async def fake_unavailable(*args: Any, **kwargs: Any) -> bool:
            return False

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.get_quality_metrics_history",
            fake_integration_get,
        )
        monkeypatch.setattr(mod, "_latest_crackerjack_result_unavailable", fake_unavailable)

        out = await _crackerjack_metrics_impl(working_directory="/wd")
        assert "Total Samples**: 1" in out
        assert "test_coverage" in out

    @pytest.mark.asyncio
    async def test_primary_path_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_integration_get(*args: Any, **kwargs: Any) -> list[Any]:
            return []

        async def fake_unavailable(*args: Any, **kwargs: Any) -> bool:
            return True

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.get_quality_metrics_history",
            fake_integration_get,
        )
        monkeypatch.setattr(mod, "_latest_crackerjack_result_unavailable", fake_unavailable)

        out = await _crackerjack_metrics_impl(working_directory="/wd")
        assert "No measurements available" in out


class TestLatestCrackerjackResultUnavailable:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_recent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeIntegration:
            async def get_recent_results(self, *args: Any, **kwargs: Any) -> list[Any]:
                return []

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        out = await mod._latest_crackerjack_result_unavailable("/wd", 1)
        assert out is False

    @pytest.mark.asyncio
    async def test_returns_true_when_flagged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeIntegration:
            async def get_recent_results(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                return [{"quality_metrics": {"unavailable": True}}]

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        out = await mod._latest_crackerjack_result_unavailable("/wd", 1)
        assert out is True

    @pytest.mark.asyncio
    async def test_parses_json_string_metrics(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeIntegration:
            async def get_recent_results(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                return [{"quality_metrics": json.dumps({"unavailable": True})}]

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        out = await mod._latest_crackerjack_result_unavailable("/wd", 1)
        assert out is True

    @pytest.mark.asyncio
    async def test_swallows_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeIntegration:
            async def get_recent_results(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

        monkeypatch.setattr(
            "session_buddy.crackerjack_integration.CrackerjackIntegration",
            FakeIntegration,
        )
        out = await mod._latest_crackerjack_result_unavailable("/wd", 1)
        assert out is False


class TestFormatQualityMetricsHistory:
    def test_unavailable(self) -> None:
        out = _format_quality_metrics_history(7, [], unavailable=True)
        assert "No measurements available" in out

    def test_with_history(self) -> None:
        history = [
            {
                "id": 1,
                "metric_type": "test_coverage",
                "metric_value": 80.0,
                "timestamp": "2026-01-01",
            },
            {
                "id": 2,
                "metric_type": "lint",
                "metric_value": 0.0,
                "timestamp": "2026-01-02",
            },
        ]
        out = _format_quality_metrics_history(7, history)
        assert "Total Samples**" in out
        assert "test_coverage" in out
        assert "Recent Samples" in out


# ---------------------------------------------------------------------------
# _get_logger / _get_reflection_db
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_object(self) -> None:
        logger = _get_logger()
        assert logger is not None


class TestGetReflectionDb:
    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_resolve() -> None:
            return None

        # Patch the symbol the module imported under (not the dotted string,
        # since ``crackerjack_tools`` did ``from ... import get_reflection_database``).
        monkeypatch.setattr(mod, "resolve_reflection_database", fake_resolve)
        out = await _get_reflection_db()
        assert out is None

    @pytest.mark.asyncio
    async def test_returns_db_when_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = object()

        async def fake_resolve() -> Any:
            return sentinel

        monkeypatch.setattr(mod, "resolve_reflection_database", fake_resolve)
        out = await _get_reflection_db()
        assert out is sentinel


# ---------------------------------------------------------------------------
# Aliases and wrappers
# ---------------------------------------------------------------------------


class TestAliases:
    @pytest.mark.asyncio
    async def test_get_crackerjack_results_history_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "history-ok"

        monkeypatch.setattr(mod, "_crackerjack_history_impl", fake_impl)
        out = await get_crackerjack_results_history()
        assert out == "history-ok"

    @pytest.mark.asyncio
    async def test_get_crackerjack_quality_metrics_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "metrics-ok"

        monkeypatch.setattr(mod, "_crackerjack_metrics_impl", fake_impl)
        out = await get_crackerjack_quality_metrics()
        assert out == "metrics-ok"

    @pytest.mark.asyncio
    async def test_analyze_crackerjack_test_patterns_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "patterns-ok"

        monkeypatch.setattr(mod, "_crackerjack_patterns_impl", fake_impl)
        out = await analyze_crackerjack_test_patterns()
        assert out == "patterns-ok"

    @pytest.mark.asyncio
    async def test_crackerjack_history_top_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "history-top-ok"

        monkeypatch.setattr(mod, "_crackerjack_history_impl", fake_impl)
        out = await crackerjack_history()
        assert out == "history-top-ok"

    @pytest.mark.asyncio
    async def test_crackerjack_metrics_top_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "metrics-top-ok"

        monkeypatch.setattr(mod, "_crackerjack_metrics_impl", fake_impl)
        out = await crackerjack_metrics()
        assert out == "metrics-top-ok"

    @pytest.mark.asyncio
    async def test_crackerjack_patterns_top_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "patterns-top-ok"

        monkeypatch.setattr(mod, "_crackerjack_patterns_impl", fake_impl)
        out = await crackerjack_patterns()
        assert out == "patterns-top-ok"

    @pytest.mark.asyncio
    async def test_crackerjack_quality_trends_top_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "trends-ok"

        monkeypatch.setattr(mod, "_crackerjack_quality_trends_impl", fake_impl)
        out = await crackerjack_quality_trends()
        assert out == "trends-ok"

    @pytest.mark.asyncio
    async def test_crackerjack_health_check_top_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "health-ok"

        monkeypatch.setattr(mod, "_crackerjack_health_check_impl", fake_impl)
        out = await crackerjack_health_check()
        assert out == "health-ok"

    @pytest.mark.asyncio
    async def test_crackerjack_help_top_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "help-ok"

        monkeypatch.setattr(mod, "_crackerjack_help_impl", fake_impl)
        out = await crackerjack_help()
        assert out == "help-ok"

    @pytest.mark.asyncio
    async def test_quality_monitor_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_impl(*args: Any, **kwargs: Any) -> str:
            return "qm-ok"

        monkeypatch.setattr(mod, "_crackerjack_health_check_impl", fake_impl)
        out = await quality_monitor()
        assert out == "qm-ok"


# ---------------------------------------------------------------------------
# _get_ai_recommendations_with_history
# ---------------------------------------------------------------------------


class TestGetAiRecommendations:
    @pytest.mark.asyncio
    async def test_no_db_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Build a result object with the expected attributes.
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        result.exit_code = 1

        async def fake_db() -> None:
            return None

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)

        out, recs, history = await _get_ai_recommendations_with_history(result, "/wd")
        # When db is None, history_analysis stays empty.
        assert recs is not None or recs == []
        assert history == {}

    @pytest.mark.asyncio
    async def test_with_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        result.exit_code = 1

        class FakeDB:
            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        async def fake_db() -> Any:
            return FakeDB()

        monkeypatch.setattr(mod, "_get_reflection_db", fake_db)
        # Patch the lazy imports inside _get_ai_recommendations_with_history.

        # Patch RecommendationEngine.analyze_history
        from session_buddy.mcp.tools.advanced.recommendation_engine import (
            RecommendationEngine,
        )

        async def fake_analyze_history(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "agent_effectiveness": {},
                "patterns": [],
                "total_executions": 0,
                "insights": [],
            }

        monkeypatch.setattr(
            RecommendationEngine, "analyze_history", fake_analyze_history
        )

        out, recs, history = await _get_ai_recommendations_with_history(result, "/wd")
        assert isinstance(out, str)
        assert isinstance(recs, list)
        # When agent_effectiveness is empty, history retains its full keys
        # (patterns, total_executions, insights, agent_effectiveness).
        assert history.get("agent_effectiveness") == {}
        assert history.get("patterns") == []
        assert history.get("total_executions") == 0
        assert history.get("insights") == []


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegisterCrackerjackTools:
    def test_registers_all_tools(self) -> None:
        captured: list[Any] = []

        class _Capturing:
            def tool(self, *_args: Any, **_kwargs: Any) -> Any:
                def decorator(fn: Any) -> Any:
                    captured.append(fn)
                    return fn

                return decorator

        register_crackerjack_tools(_Capturing())  # type: ignore[arg-type]
        registered_names = {fn.__name__ for fn in captured}
        expected = {
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
        }
        # At minimum, the core set should be present (allows for renames).
        assert expected.issubset(registered_names)
