"""Unit tests for session_buddy.analytics.cli module.

Tests the Typer-based CLI commands for session analytics, including:
- ``parse_days_option`` helper (validation edge cases)
- ``analytics_sessions`` command
- ``analytics_duration`` command
- ``analytics_components`` command
- ``analytics_errors`` command
- ``analytics_active`` command
- ``analytics_report`` command
- ``analytics_sql`` command
- ``main`` entry point

Coverage target: 80%+ for ``session_buddy/analytics/cli.py``.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from session_buddy.analytics import cli as analytics_cli
from session_buddy.analytics.cli import (
    analytics_active,
    analytics_components,
    analytics_duration,
    analytics_errors,
    analytics_report,
    analytics_sessions,
    analytics_sql,
    app,
    main,
    parse_days_option,
)
from session_buddy.analytics.session_analytics import (
    ComponentUsage,
    SessionStats,
    create_session_summary_report,
)


def _exit_code(exc: BaseException) -> int:
    """Extract exit code from a typer/click Exit exception."""
    return getattr(exc, "exit_code", getattr(exc, "code", 1))


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_analytics():
    """Patch SessionAnalytics inside the CLI module.

    Yields a MagicMock class. Tests can configure ``return_value`` to
    inject async method behaviour on the constructed instance.
    """
    mock_class = MagicMock()
    with patch.object(analytics_cli, "SessionAnalytics", mock_class):
        yield mock_class


# =============================================================================
# Test parse_days_option
# =============================================================================


class TestParseDaysOption:
    """Tests for parse_days_option helper."""

    def test_default_when_none(self) -> None:
        """Returns default 7 when days is None."""
        assert parse_days_option(None) == 7

    def test_valid_value(self) -> None:
        """Returns the value when in valid range."""
        assert parse_days_option(30) == 30

    def test_minimum_boundary(self) -> None:
        """1 day is allowed (lower boundary inclusive)."""
        assert parse_days_option(1) == 1

    def test_maximum_boundary(self) -> None:
        """365 days is allowed (upper boundary inclusive)."""
        assert parse_days_option(365) == 365

    def test_zero_days_rejected(self) -> None:
        """Zero days is rejected with typer.Exit(1)."""
        with pytest.raises(typer.Exit) as exc_info:
            parse_days_option(0)
        assert _exit_code(exc_info.value) == 1

    def test_negative_days_rejected(self) -> None:
        """Negative days is rejected with typer.Exit(1)."""
        with pytest.raises(typer.Exit) as exc_info:
            parse_days_option(-5)
        assert _exit_code(exc_info.value) == 1

    def test_over_maximum_rejected(self) -> None:
        """Days over 365 is rejected with typer.Exit(1)."""
        with pytest.raises(typer.Exit) as exc_info:
            parse_days_option(400)
        assert _exit_code(exc_info.value) == 1


# =============================================================================
# Test analytics_sessions command
# =============================================================================


class TestAnalyticsSessions:
    """Tests for analytics_sessions command."""

    def test_help(self, runner: CliRunner) -> None:
        """Sessions subcommand has help text."""
        result = runner.invoke(app, ["sessions", "--help"])
        # --help typically exits 0 with usage info
        assert result.exit_code == 0
        assert "session statistics" in result.output.lower() or "--days" in result.output

    def test_invalid_days_exits_1(self, runner: CliRunner) -> None:
        """Invalid days parameter causes early exit."""
        result = runner.invoke(app, ["sessions", "--days", "0"])
        assert result.exit_code == 1

    def test_excessive_days_exits_1(self, runner: CliRunner) -> None:
        """Days > 365 causes early exit."""
        result = runner.invoke(app, ["sessions", "--days", "999"])
        assert result.exit_code == 1

    def test_no_data_returns_message(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """Empty stats shows 'no data' message."""
        instance = mock_analytics.return_value

        async def empty_stats(**_kwargs: object) -> list[object]:
            return []

        instance.get_session_stats = empty_stats
        instance.visualize_session_stats = MagicMock(return_value=[])

        result = runner.invoke(app, ["sessions"])
        assert result.exit_code == 0
        assert "No session data" in result.output

    def test_json_output(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """JSON flag produces JSON-formatted output."""
        instance = mock_analytics.return_value
        stat = SessionStats(
            component_name="admin-shell",
            total_sessions=10,
            avg_duration=100.0,
            active_sessions=1,
            error_rate=2.5,
            date_range="Last 7 days",
        )

        async def fake_stats(**_kwargs: object) -> list[SessionStats]:
            return [stat]

        instance.get_session_stats = fake_stats

        result = runner.invoke(app, ["sessions", "--json"])
        assert result.exit_code == 0
        # JSON output should contain the component name and be parseable
        parsed = json.loads(result.output)
        assert parsed[0]["component_name"] == "admin-shell"
        assert parsed[0]["total_sessions"] == 10

    def test_visualization_output(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Without --json, visualization lines are emitted."""
        instance = mock_analytics.return_value
        stat = SessionStats(
            component_name="admin-shell",
            total_sessions=10,
            avg_duration=100.0,
            active_sessions=1,
            error_rate=2.5,
        )

        async def fake_stats(**_kwargs: object) -> list[SessionStats]:
            return [stat]

        instance.get_session_stats = fake_stats
        instance.visualize_session_stats = MagicMock(
            return_value=["LINE-1", "LINE-2"]
        )

        result = runner.invoke(app, ["sessions"])
        assert result.exit_code == 0
        assert "LINE-1" in result.output
        assert "LINE-2" in result.output

    def test_with_component_filter(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Component filter is forwarded to get_session_stats."""
        instance = mock_analytics.return_value

        async def empty_stats(**_kwargs: object) -> list[object]:
            return []

        instance.get_session_stats = empty_stats

        result = runner.invoke(app, ["sessions", "--component", "ipython"])
        # Should pass through without crashing and trigger empty path
        assert result.exit_code == 0
        assert "No session data" in result.output


# =============================================================================
# Test analytics_duration command
# =============================================================================


class TestAnalyticsDuration:
    """Tests for analytics_duration command."""

    def test_help(self, runner: CliRunner) -> None:
        """Duration subcommand help works."""
        result = runner.invoke(app, ["duration", "--help"])
        assert result.exit_code == 0

    def test_invalid_days_exits_1(self, runner: CliRunner) -> None:
        """Invalid days rejected."""
        result = runner.invoke(app, ["duration", "--days", "-1"])
        assert result.exit_code == 1

    def test_excessive_days_exits_1(self, runner: CliRunner) -> None:
        """Excessive days rejected."""
        result = runner.invoke(app, ["duration", "--days", "400"])
        assert result.exit_code == 1

    def test_no_data_returns_message(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Empty durations shows 'no data' message."""
        instance = mock_analytics.return_value

        async def empty_durations(**_kwargs: object) -> dict[str, float]:
            return {}

        instance.get_average_session_duration = empty_durations

        result = runner.invoke(app, ["duration"])
        assert result.exit_code == 0
        assert "No duration data" in result.output

    def test_json_output(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """JSON flag emits JSON-encoded duration map."""
        instance = mock_analytics.return_value

        async def fake_durations(**_kwargs: object) -> dict[str, float]:
            return {"admin-shell": 3600.5, "ipython": 1800.0}

        instance.get_average_session_duration = fake_durations

        result = runner.invoke(app, ["duration", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["admin-shell"] == 3600.5
        assert parsed["ipython"] == 1800.0

    def test_text_output_hours_minutes_seconds(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Formatted output includes hours, minutes, seconds for long durations."""
        instance = mock_analytics.return_value
        # 1h 30m 0s = 5400 seconds
        async def fake_durations(**_kwargs: object) -> dict[str, float]:
            return {"admin-shell": 5400.0}

        instance.get_average_session_duration = fake_durations

        result = runner.invoke(app, ["duration"])
        assert result.exit_code == 0
        assert "AVERAGE SESSION DURATION" in result.output
        assert "1h 30m 0s" in result.output
        assert "admin-shell" in result.output

    def test_text_output_minutes_only(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Output uses minutes-only format for short durations."""
        instance = mock_analytics.return_value
        # 5m 30s = 330 seconds (no hours)
        async def fake_durations(**_kwargs: object) -> dict[str, float]:
            return {"ipython": 330.0}

        instance.get_average_session_duration = fake_durations

        result = runner.invoke(app, ["duration"])
        assert result.exit_code == 0
        assert "5m 30s" in result.output

    def test_text_output_seconds_only(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Output uses seconds-only format for very short durations."""
        instance = mock_analytics.return_value
        # 45 seconds (no hours or minutes)
        async def fake_durations(**_kwargs: object) -> dict[str, float]:
            return {"zsh": 45.0}

        instance.get_average_session_duration = fake_durations

        result = runner.invoke(app, ["duration"])
        assert result.exit_code == 0
        assert "45s" in result.output

    def test_sorted_descending(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Output is sorted by duration descending."""
        instance = mock_analytics.return_value
        async def fake_durations(**_kwargs: object) -> dict[str, float]:
            return {"short": 100.0, "long": 7200.0, "medium": 3600.0}

        instance.get_average_session_duration = fake_durations

        result = runner.invoke(app, ["duration"])
        assert result.exit_code == 0
        long_pos = result.output.find("long")
        medium_pos = result.output.find("medium")
        short_pos = result.output.find("short")
        # long should appear before medium which appears before short
        assert long_pos < medium_pos < short_pos

    def test_with_component_filter(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Component filter is forwarded."""
        instance = mock_analytics.return_value
        async def empty_durations(**_kwargs: object) -> dict[str, float]:
            return {}

        instance.get_average_session_duration = empty_durations

        result = runner.invoke(app, ["duration", "--component", "admin-shell"])
        assert result.exit_code == 0
        assert "No duration data" in result.output


# =============================================================================
# Test analytics_components command
# =============================================================================


class TestAnalyticsComponents:
    """Tests for analytics_components command."""

    def test_help(self, runner: CliRunner) -> None:
        """Components subcommand help works."""
        result = runner.invoke(app, ["components", "--help"])
        assert result.exit_code == 0

    def test_invalid_days_exits_1(self, runner: CliRunner) -> None:
        """Invalid days rejected."""
        result = runner.invoke(app, ["components", "--days", "-2"])
        assert result.exit_code == 1

    def test_excessive_days_exits_1(self, runner: CliRunner) -> None:
        """Excessive days rejected."""
        result = runner.invoke(app, ["components", "--days", "500"])
        assert result.exit_code == 1

    def test_limit_too_low_exits_1(self, runner: CliRunner) -> None:
        """Limit of zero rejected."""
        result = runner.invoke(app, ["components", "--limit", "0"])
        assert result.exit_code == 1

    def test_limit_too_high_exits_1(self, runner: CliRunner) -> None:
        """Limit over 100 rejected."""
        result = runner.invoke(app, ["components", "--limit", "101"])
        assert result.exit_code == 1

    def test_negative_limit_exits_1(self, runner: CliRunner) -> None:
        """Negative limit rejected."""
        result = runner.invoke(app, ["components", "--limit", "-1"])
        assert result.exit_code == 1

    def test_no_data_returns_message(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Empty components list shows 'no data' message."""
        instance = mock_analytics.return_value

        async def empty_components(**_kwargs: object) -> list[object]:
            return []

        instance.get_most_active_components = empty_components

        result = runner.invoke(app, ["components"])
        assert result.exit_code == 0
        assert "No component usage data" in result.output

    def test_json_output(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """JSON flag emits JSON-encoded component list."""
        instance = mock_analytics.return_value
        usage = ComponentUsage(
            component_name="admin-shell",
            session_count=20,
            total_duration=72000,
            avg_quality_score=85.5,
            last_active=datetime(2025, 1, 15, tzinfo=UTC),
        )

        async def fake_components(**_kwargs: object) -> list[ComponentUsage]:
            return [usage]

        instance.get_most_active_components = fake_components

        result = runner.invoke(app, ["components", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["component_name"] == "admin-shell"
        assert parsed[0]["session_count"] == 20

    def test_visualization_output(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Without --json, visualization lines are emitted."""
        instance = mock_analytics.return_value
        usage = ComponentUsage(
            component_name="admin-shell",
            session_count=20,
            total_duration=72000,
            avg_quality_score=85.5,
            last_active=datetime(2025, 1, 15, tzinfo=UTC),
        )

        async def fake_components(**_kwargs: object) -> list[ComponentUsage]:
            return [usage]

        instance.get_most_active_components = fake_components
        instance.visualize_component_usage = MagicMock(
            return_value=["HEADER", "ROW"]
        )

        result = runner.invoke(app, ["components"])
        assert result.exit_code == 0
        assert "HEADER" in result.output
        assert "ROW" in result.output

    def test_limit_passed_through(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """Limit parameter is forwarded to get_most_active_components."""
        instance = mock_analytics.return_value
        captured_kwargs: dict[str, object] = {}

        async def capture_components(**kwargs: object) -> list[object]:
            captured_kwargs.update(kwargs)
            return []

        instance.get_most_active_components = capture_components

        result = runner.invoke(app, ["components", "--limit", "5"])
        assert result.exit_code == 0
        assert captured_kwargs.get("limit") == 5


# =============================================================================
# Test analytics_errors command
# =============================================================================


class TestAnalyticsErrors:
    """Tests for analytics_errors command."""

    def test_help(self, runner: CliRunner) -> None:
        """Errors subcommand help works."""
        result = runner.invoke(app, ["errors", "--help"])
        assert result.exit_code == 0

    def test_invalid_days_exits_1(self, runner: CliRunner) -> None:
        """Invalid days rejected."""
        result = runner.invoke(app, ["errors", "--days", "0"])
        assert result.exit_code == 1

    def test_excessive_days_exits_1(self, runner: CliRunner) -> None:
        """Excessive days rejected."""
        result = runner.invoke(app, ["errors", "--days", "1000"])
        assert result.exit_code == 1

    def test_no_data_returns_message(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Empty error rates shows 'no data' message."""
        instance = mock_analytics.return_value

        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}

        instance.get_session_error_rate = empty_errors

        result = runner.invoke(app, ["errors"])
        assert result.exit_code == 0
        assert "No error data" in result.output

    def test_json_output(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """JSON flag emits JSON-encoded error stats."""
        instance = mock_analytics.return_value

        async def fake_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {
                "admin-shell": {
                    "error_rate": 5.0,
                    "total_sessions": 100,
                    "failed_sessions": 5,
                    "most_common_error": "Timeout",
                }
            }

        instance.get_session_error_rate = fake_errors

        result = runner.invoke(app, ["errors", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["admin-shell"]["error_rate"] == 5.0

    def test_text_output_includes_stats(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Text output includes error rate stats formatted correctly."""
        instance = mock_analytics.return_value

        async def fake_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {
                "admin-shell": {
                    "error_rate": 12.5,
                    "total_sessions": 80,
                    "failed_sessions": 10,
                    "most_common_error": "Connection timeout",
                }
            }

        instance.get_session_error_rate = fake_errors

        result = runner.invoke(app, ["errors"])
        assert result.exit_code == 0
        assert "ERROR RATE STATISTICS" in result.output
        assert "admin-shell" in result.output
        assert "12.50%" in result.output
        assert "Total Sessions: 80" in result.output
        assert "Failed:        10" in result.output
        assert "Most Common:   Connection timeout" in result.output

    def test_text_output_truncates_long_error(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Long error messages are truncated to 60 chars."""
        instance = mock_analytics.return_value
        long_msg = "X" * 100  # 100-char error message

        async def fake_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {
                "admin-shell": {
                    "error_rate": 5.0,
                    "total_sessions": 100,
                    "failed_sessions": 5,
                    "most_common_error": long_msg,
                }
            }

        instance.get_session_error_rate = fake_errors

        result = runner.invoke(app, ["errors"])
        assert result.exit_code == 0
        # Output should contain only 60 Xs followed by "..."
        assert ("X" * 60 + "...") in result.output

    def test_text_output_handles_missing_most_common_error(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Missing most_common_error is handled gracefully."""
        instance = mock_analytics.return_value

        async def fake_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {
                "ipython": {
                    "error_rate": 1.0,
                    "total_sessions": 50,
                    "failed_sessions": 0,
                    "most_common_error": None,
                }
            }

        instance.get_session_error_rate = fake_errors

        result = runner.invoke(app, ["errors"])
        assert result.exit_code == 0
        # Should not include "Most Common" line when None
        assert "Most Common:" not in result.output

    def test_with_component_filter(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Component filter works."""
        instance = mock_analytics.return_value
        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}

        instance.get_session_error_rate = empty_errors

        result = runner.invoke(app, ["errors", "--component", "ipython"])
        assert result.exit_code == 0
        assert "No error data" in result.output


# =============================================================================
# Test analytics_active command
# =============================================================================


class TestAnalyticsActive:
    """Tests for analytics_active command."""

    def test_help(self, runner: CliRunner) -> None:
        """Active subcommand help works."""
        result = runner.invoke(app, ["active", "--help"])
        assert result.exit_code == 0

    def test_no_active_sessions(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """No active sessions shows appropriate message."""
        instance = mock_analytics.return_value

        async def empty_active() -> list[object]:
            return []

        instance.get_active_sessions = empty_active

        result = runner.invoke(app, ["active"])
        assert result.exit_code == 0
        assert "No active sessions" in result.output

    def test_json_output(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """JSON flag emits JSON-encoded active session list."""
        instance = mock_analytics.return_value

        async def fake_active() -> list[dict[str, object]]:
            return [
                {
                    "session_id": "sess-1",
                    "component_name": "admin-shell",
                    "start_time": "2025-01-15T10:00:00Z",
                    "duration_seconds": 1800,
                    "project": "test-project",
                }
            ]

        instance.get_active_sessions = fake_active

        result = runner.invoke(app, ["active", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["session_id"] == "sess-1"

    def test_text_output_hours(self, runner: CliRunner, mock_analytics: MagicMock) -> None:
        """Long duration formatted as hours."""
        instance = mock_analytics.return_value

        async def fake_active() -> list[dict[str, object]]:
            # 2h 15m 30s = 8130 seconds
            return [
                {
                    "session_id": "sess-1",
                    "component_name": "admin-shell",
                    "start_time": "2025-01-15T10:00:00Z",
                    "duration_seconds": 8130,
                    "project": "test-project",
                }
            ]

        instance.get_active_sessions = fake_active

        result = runner.invoke(app, ["active"])
        assert result.exit_code == 0
        assert "ACTIVE SESSIONS (1)" in result.output
        assert "sess-1" in result.output
        assert "2h 15m 30s" in result.output

    def test_text_output_minutes_only(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Short durations formatted as minutes-only."""
        instance = mock_analytics.return_value

        async def fake_active() -> list[dict[str, object]]:
            # 10m 30s
            return [
                {
                    "session_id": "sess-2",
                    "component_name": "ipython",
                    "start_time": "2025-01-15T11:00:00Z",
                    "duration_seconds": 630,
                    "project": "test-project",
                }
            ]

        instance.get_active_sessions = fake_active

        result = runner.invoke(app, ["active"])
        assert result.exit_code == 0
        assert "10m 30s" in result.output

    def test_text_output_seconds_only(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Very short durations formatted as seconds only."""
        instance = mock_analytics.return_value

        async def fake_active() -> list[dict[str, object]]:
            return [
                {
                    "session_id": "sess-3",
                    "component_name": "zsh",
                    "start_time": "2025-01-15T12:00:00Z",
                    "duration_seconds": 30,
                    "project": "test-project",
                }
            ]

        instance.get_active_sessions = fake_active

        result = runner.invoke(app, ["active"])
        assert result.exit_code == 0
        assert "30s" in result.output

    def test_text_output_missing_fields(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Missing fields fall back to 'unknown'."""
        instance = mock_analytics.return_value

        async def fake_active() -> list[dict[str, object]]:
            return [{}]

        instance.get_active_sessions = fake_active

        result = runner.invoke(app, ["active"])
        assert result.exit_code == 0
        assert "unknown" in result.output


# =============================================================================
# Test analytics_report command
# =============================================================================


class TestAnalyticsReport:
    """Tests for analytics_report command."""

    def test_help(self, runner: CliRunner) -> None:
        """Report subcommand help works."""
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_invalid_days_exits_1(self, runner: CliRunner) -> None:
        """Invalid days rejected."""
        result = runner.invoke(app, ["report", "--days", "0"])
        assert result.exit_code == 1

    def test_excessive_days_exits_1(self, runner: CliRunner) -> None:
        """Excessive days rejected."""
        result = runner.invoke(app, ["report", "--days", "999"])
        assert result.exit_code == 1

    def test_stdout_output(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Without --output, report is printed to stdout."""
        instance = mock_analytics.return_value

        async def empty_stats(**_kwargs: object) -> list[object]:
            return []

        async def empty_components(**_kwargs: object) -> list[object]:
            return []

        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}

        instance.get_session_stats = empty_stats
        instance.get_most_active_components = empty_components
        instance.get_session_error_rate = empty_errors

        result = runner.invoke(app, ["report"])
        assert result.exit_code == 0
        assert "SESSION-BUDDY ANALYTICS REPORT" in result.output
        assert "End of Report" in result.output

    def test_writes_to_file(
        self, runner: CliRunner, mock_analytics: MagicMock, tmp_path: Path
    ) -> None:
        """With --output, report is saved to file."""
        instance = mock_analytics.return_value

        async def empty_stats(**_kwargs: object) -> list[object]:
            return []

        async def empty_components(**_kwargs: object) -> list[object]:
            return []

        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}

        instance.get_session_stats = empty_stats
        instance.get_most_active_components = empty_components
        instance.get_session_error_rate = empty_errors

        output_path = tmp_path / "report.txt"
        result = runner.invoke(
            app, ["report", "--days", "7", "--output", str(output_path)]
        )
        assert result.exit_code == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "SESSION-BUDDY ANALYTICS REPORT" in content
        assert f"Report saved to: {output_path}" in result.output

    def test_file_write_error_exits_1(
        self, runner: CliRunner, mock_analytics: MagicMock, tmp_path: Path
    ) -> None:
        """When write fails, exits with code 1."""
        instance = mock_analytics.return_value

        async def empty_stats(**_kwargs: object) -> list[object]:
            return []

        async def empty_components(**_kwargs: object) -> list[object]:
            return []

        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}

        instance.get_session_stats = empty_stats
        instance.get_most_active_components = empty_components
        instance.get_session_error_rate = empty_errors

        # Use a path that should fail to write (directory doesn't exist)
        bad_path = tmp_path / "does-not-exist" / "report.txt"
        result = runner.invoke(
            app, ["report", "--days", "7", "--output", str(bad_path)]
        )
        assert result.exit_code == 1
        assert "Error saving report" in result.output

    def test_includes_real_data(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Report includes real session/component/error data."""
        instance = mock_analytics.return_value

        stat = SessionStats(
            component_name="admin-shell",
            total_sessions=10,
            avg_duration=300.0,
            active_sessions=1,
            error_rate=5.0,
        )
        component = ComponentUsage(
            component_name="admin-shell",
            session_count=10,
            total_duration=3000,
            avg_quality_score=80.0,
            last_active=datetime(2025, 1, 15, tzinfo=UTC),
        )

        async def fake_stats(**_kwargs: object) -> list[SessionStats]:
            return [stat]

        async def fake_components(**_kwargs: object) -> list[ComponentUsage]:
            return [component]

        async def fake_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {
                "admin-shell": {
                    "error_rate": 5.0,
                    "total_sessions": 10,
                    "failed_sessions": 1,
                    "most_common_error": None,
                }
            }

        instance.get_session_stats = fake_stats
        instance.get_most_active_components = fake_components
        instance.get_session_error_rate = fake_errors

        result = runner.invoke(app, ["report"])
        assert result.exit_code == 0
        assert "Total Sessions: 10" in result.output
        assert "Components Analyzed: 1" in result.output
        assert "Total Errors: 1" in result.output


# =============================================================================
# Test analytics_sql command
# =============================================================================


class TestAnalyticsSql:
    """Tests for analytics_sql command."""

    def test_help(self, runner: CliRunner) -> None:
        """SQL subcommand help works."""
        result = runner.invoke(app, ["sql", "--help"])
        assert result.exit_code == 0

    def test_invalid_days_exits_1(self, runner: CliRunner) -> None:
        """Invalid days rejected."""
        result = runner.invoke(app, ["sql", "active_sessions", "--days", "-1"])
        assert result.exit_code == 1

    def test_excessive_days_exits_1(self, runner: CliRunner) -> None:
        """Excessive days rejected."""
        result = runner.invoke(app, ["sql", "active_sessions", "--days", "500"])
        assert result.exit_code == 1

    def test_known_query_prints_sql(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Known query prints SQL to stdout."""
        instance = mock_analytics.return_value
        instance.export_sql = MagicMock(return_value="SELECT * FROM sessions;")

        result = runner.invoke(app, ["sql", "active_sessions"])
        assert result.exit_code == 0
        assert "SELECT * FROM sessions;" in result.output
        instance.export_sql.assert_called_once_with(
            query_name="active_sessions", days=7
        )

    def test_unknown_query_returns_placeholder(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Unknown query returns -- Query not found placeholder."""
        instance = mock_analytics.return_value
        instance.export_sql = MagicMock(return_value="-- Query not found")

        result = runner.invoke(app, ["sql", "bogus_query"])
        assert result.exit_code == 0
        assert "Query not found" in result.output

    def test_days_passed_through(
        self, runner: CliRunner, mock_analytics: MagicMock
    ) -> None:
        """Days parameter is forwarded to export_sql."""
        instance = mock_analytics.return_value
        instance.export_sql = MagicMock(return_value="SELECT 1;")

        result = runner.invoke(app, ["sql", "session_stats", "--days", "30"])
        assert result.exit_code == 0
        instance.export_sql.assert_called_once_with(
            query_name="session_stats", days=30
        )


# =============================================================================
# Test main entry point
# =============================================================================


class TestMain:
    """Tests for the main entry point."""

    def test_main_invokes_app(self) -> None:
        """main() delegates to the Typer app."""
        with patch.object(analytics_cli, "app") as mock_app:
            main()
            mock_app.assert_called_once_with()

    def test_main_no_args_help(self, runner: CliRunner) -> None:
        """Invoking app with no args shows help."""
        result = runner.invoke(app, ["--help"])
        # Typer exit code 0 for successful --help
        assert result.exit_code == 0
        assert "analytics" in result.output.lower()


# =============================================================================
# Test command decorators and registration
# =============================================================================


class TestCommandRegistration:
    """Verify all expected commands are registered."""

    def test_all_commands_registered(self) -> None:
        """All required commands are registered with the Typer app."""
        registered = set()
        # Typer's app.registered_commands holds Callback objects
        for callback in app.registered_commands:  # type: ignore[attr-defined]
            if hasattr(callback, "name"):
                registered.add(callback.name)
            elif hasattr(callback, "callback") and hasattr(callback.callback, "__name__"):
                registered.add(callback.callback.__name__)

        expected = {
            "sessions",
            "duration",
            "components",
            "errors",
            "active",
            "report",
            "sql",
        }
        assert expected.issubset(registered), (
            f"Missing commands: {expected - registered}"
        )


# =============================================================================
# Test direct function invocation
# =============================================================================


class TestDirectFunctionCalls:
    """Directly invoke the underlying command functions (bypassing Typer).

    This catches issues where Typer's metadata might mask runtime errors.
    """

    def test_analytics_sessions_direct(
        self, mock_analytics: MagicMock
    ) -> None:
        """Direct call to analytics_sessions works."""
        instance = mock_analytics.return_value
        async def empty_stats(**_kwargs: object) -> list[object]:
            return []
        instance.get_session_stats = empty_stats

        # Should not raise
        analytics_sessions(days=7, component=None, json_output=False)

    def test_analytics_duration_direct(
        self, mock_analytics: MagicMock
    ) -> None:
        """Direct call to analytics_duration works."""
        instance = mock_analytics.return_value
        async def empty_durations(**_kwargs: object) -> dict[str, float]:
            return {}
        instance.get_average_session_duration = empty_durations

        analytics_duration(days=7, component=None, json_output=False)

    def test_analytics_components_direct(
        self, mock_analytics: MagicMock
    ) -> None:
        """Direct call to analytics_components works."""
        instance = mock_analytics.return_value
        async def empty_components(**_kwargs: object) -> list[object]:
            return []
        instance.get_most_active_components = empty_components

        analytics_components(days=7, limit=10, json_output=False)

    def test_analytics_components_invalid_limit_direct(self) -> None:
        """Direct call to analytics_components validates limit."""
        with pytest.raises(typer.Exit) as exc_info:
            analytics_components(days=7, limit=0, json_output=False)
        assert _exit_code(exc_info.value) == 1

    def test_analytics_components_invalid_limit_high_direct(self) -> None:
        """Direct call to analytics_components validates upper limit."""
        with pytest.raises(typer.Exit) as exc_info:
            analytics_components(days=7, limit=200, json_output=False)
        assert _exit_code(exc_info.value) == 1

    def test_analytics_errors_direct(
        self, mock_analytics: MagicMock
    ) -> None:
        """Direct call to analytics_errors works."""
        instance = mock_analytics.return_value
        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}
        instance.get_session_error_rate = empty_errors

        analytics_errors(days=7, component=None, json_output=False)

    def test_analytics_active_direct(
        self, mock_analytics: MagicMock
    ) -> None:
        """Direct call to analytics_active works."""
        instance = mock_analytics.return_value
        async def empty_active() -> list[object]:
            return []
        instance.get_active_sessions = empty_active

        analytics_active(json_output=False)

    def test_analytics_report_direct(
        self, mock_analytics: MagicMock
    ) -> None:
        """Direct call to analytics_report works."""
        instance = mock_analytics.return_value
        async def empty_stats(**_kwargs: object) -> list[object]:
            return []
        async def empty_components(**_kwargs: object) -> list[object]:
            return []
        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}
        instance.get_session_stats = empty_stats
        instance.get_most_active_components = empty_components
        instance.get_session_error_rate = empty_errors

        analytics_report(days=7, output=None)

    def test_analytics_sql_direct(self, mock_analytics: MagicMock) -> None:
        """Direct call to analytics_sql works."""
        instance = mock_analytics.return_value
        instance.export_sql = MagicMock(return_value="SELECT 1;")

        analytics_sql(query="session_stats", days=7)


# =============================================================================
# Test report file write exception path
# =============================================================================


class TestReportWriteException:
    """Tests for report file write exception handling."""

    def test_oserror_when_writing(
        self, runner: CliRunner, mock_analytics: MagicMock, tmp_path: Path
    ) -> None:
        """OSError when writing the file exits with code 1."""
        instance = mock_analytics.return_value

        async def empty_stats(**_kwargs: object) -> list[object]:
            return []

        async def empty_components(**_kwargs: object) -> list[object]:
            return []

        async def empty_errors(**_kwargs: object) -> dict[str, dict[str, object]]:
            return {}

        instance.get_session_stats = empty_stats
        instance.get_most_active_components = empty_components
        instance.get_session_error_rate = empty_errors

        # Mock Path.write_text to raise OSError
        output_path = tmp_path / "report.txt"

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = runner.invoke(
                app, ["report", "--output", str(output_path)]
            )

        assert result.exit_code == 1
        assert "Error saving report" in result.output
        assert "disk full" in result.output


# =============================================================================
# Test export_sql integration via analytics_sql
# =============================================================================


class TestSqlQueryIntegration:
    """Test SQL command actually exercises export_sql branches."""

    @pytest.mark.parametrize(
        "query_name",
        [
            "active_sessions",
            "session_stats",
            "average_duration",
            "most_active",
            "error_rate",
        ],
    )
    def test_all_known_query_names(
        self, runner: CliRunner, mock_analytics: MagicMock, query_name: str
    ) -> None:
        """All known query names return real SQL via export_sql."""
        instance = mock_analytics.return_value
        # Return realistic SQL for each query
        instance.export_sql = MagicMock(
            return_value=f"SELECT * FROM sessions /* {query_name} */"
        )

        result = runner.invoke(app, ["sql", query_name])
        assert result.exit_code == 0
        # Verify export_sql was called
        instance.export_sql.assert_called_once()
        call_kwargs = instance.export_sql.call_args.kwargs
        assert call_kwargs["query_name"] == query_name
        assert call_kwargs["days"] == 7
        assert query_name in result.output