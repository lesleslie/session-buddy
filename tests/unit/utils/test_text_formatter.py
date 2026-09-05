"""Unit tests for session_buddy.utils.text_formatter.

All sixteen functions in the module are private (underscore-prefixed). Each
test class targets one function and exercises its happy path plus the
branches that handle empty inputs, missing keys, and edge-case unicode or
length boundaries.
"""

from __future__ import annotations

from session_buddy.utils import text_formatter as tf


# ---------------------------------------------------------------------------
# _format_statistics_header
# ---------------------------------------------------------------------------


class TestFormatStatisticsHeader:
    """Tests for _format_statistics_header."""

    def test_returns_two_lines(self) -> None:
        result = tf._format_statistics_header("alice")
        assert len(result) == 2

    def test_first_line_contains_user_id(self) -> None:
        result = tf._format_statistics_header("alice")
        assert result[0] == "📊 **Interruption Statistics for alice**"

    def test_second_line_is_blank(self) -> None:
        result = tf._format_statistics_header("bob")
        assert result[1] == ""

    def test_unicode_user_id_preserved(self) -> None:
        user_id = "user-éñ中"
        result = tf._format_statistics_header(user_id)
        assert user_id in result[0]

    def test_empty_user_id_does_not_raise(self) -> None:
        result = tf._format_statistics_header("")
        # Format is "... Statistics for {user_id}" — empty user_id leaves a trailing space.
        assert result[0] == "📊 **Interruption Statistics for **"
        assert result[1] == ""


# ---------------------------------------------------------------------------
# _format_session_statistics
# ---------------------------------------------------------------------------


class TestFormatSessionStatistics:
    """Tests for _format_session_statistics."""

    def test_empty_sessions_returns_no_data_message(self) -> None:
        result = tf._format_session_statistics({})
        assert result == ["📝 No session data available"]

    def test_falsy_sessions_returns_no_data_message(self) -> None:
        # Falsy mapping short-circuits.
        assert tf._format_session_statistics({}) == ["📝 No session data available"]

    def test_populated_sessions_includes_counts(self) -> None:
        sessions = {"total": 10, "avg_duration_minutes": 23.4, "max_duration_minutes": 99.9}
        result = tf._format_session_statistics(sessions)
        joined = "\n".join(result)
        assert "**Session Activity:**" in joined
        assert "Total sessions: 10" in joined
        assert "Average duration: 23.4 minutes" in joined
        assert "Longest session: 99.9 minutes" in joined

    def test_missing_keys_fall_back_to_zero(self) -> None:
        # Only ``total`` provided — other keys default to 0 via .get().
        result = tf._format_session_statistics({"total": 1})
        joined = "\n".join(result)
        assert "Total sessions: 1" in joined
        assert "Average duration: 0.0 minutes" in joined
        assert "Longest session: 0.0 minutes" in joined

    def test_trailing_blank_line(self) -> None:
        result = tf._format_session_statistics({"total": 1})
        assert result[-1] == ""


# ---------------------------------------------------------------------------
# _format_interruption_type_details
# ---------------------------------------------------------------------------


class TestFormatInterruptionTypeDetails:
    """Tests for _format_interruption_type_details."""

    def test_empty_list_returns_empty_lines(self) -> None:
        assert tf._format_interruption_type_details([]) == []

    def test_single_item_formats_with_icon(self) -> None:
        result = tf._format_interruption_type_details(
            [{"type": "phone", "count": 3}],
        )
        assert result[0] == "**Interruption Types:**"
        assert "• phone: 3 occurrences" in result

    def test_caps_at_top_five(self) -> None:
        by_type = [{"type": f"t{i}", "count": i} for i in range(8)]
        result = tf._format_interruption_type_details(by_type)
        # Header + 5 entries + trailing blank line.
        assert len(result) == 7
        # Past the first 5, "t5" and "t6" must NOT appear.
        joined = "\n".join(result)
        assert "t5" not in joined
        assert "t6" not in joined

    def test_includes_trailing_blank_line(self) -> None:
        result = tf._format_interruption_type_details([{"type": "x", "count": 1}])
        assert result[-1] == ""


# ---------------------------------------------------------------------------
# _format_interruption_statistics
# ---------------------------------------------------------------------------


class TestFormatInterruptionStatistics:
    """Tests for _format_interruption_statistics."""

    def test_empty_returns_no_data_message(self) -> None:
        result = tf._format_interruption_statistics({})
        assert result == ["🚫 No interruption data available"]

    def test_basic_fields_rendered(self) -> None:
        data = {
            "total": 12,
            "avg_per_session": 1.5,
            "peak_hour": 14,
        }
        result = tf._format_interruption_statistics(data)
        joined = "\n".join(result)
        assert "**Interruption Patterns:**" in joined
        assert "Total interruptions: 12" in joined
        assert "Average per session: 1.5" in joined
        assert "Most active hour: 14" in joined

    def test_peak_hour_defaults_to_unknown(self) -> None:
        result = tf._format_interruption_statistics({"total": 1})
        joined = "\n".join(result)
        assert "Most active hour: Unknown" in joined

    def test_by_type_branch_appends_breakdown(self) -> None:
        data = {
            "total": 5,
            "avg_per_session": 0.5,
            "peak_hour": 9,
            "by_type": [{"type": "slack", "count": 3}],
        }
        result = tf._format_interruption_statistics(data)
        joined = "\n".join(result)
        assert "**Interruption Types:**" in joined
        assert "slack: 3 occurrences" in joined

    def test_without_by_type_branch(self) -> None:
        data = {"total": 5, "avg_per_session": 0.5, "peak_hour": 9}
        result = tf._format_interruption_statistics(data)
        joined = "\n".join(result)
        assert "Interruption Types:" not in joined


# ---------------------------------------------------------------------------
# _format_snapshot_statistics
# ---------------------------------------------------------------------------


class TestFormatSnapshotStatistics:
    """Tests for _format_snapshot_statistics."""

    def test_empty_returns_no_data_message(self) -> None:
        result = tf._format_snapshot_statistics({})
        assert result == ["💾 No snapshot data available"]

    def test_populated_renders_three_metrics(self) -> None:
        data = {"total": 7, "successful_restores": 5, "avg_size_kb": 12.34}
        result = tf._format_snapshot_statistics(data)
        joined = "\n".join(result)
        assert "**Context Snapshots:**" in joined
        assert "Total snapshots: 7" in joined
        assert "Successful restores: 5" in joined
        assert "Average snapshot size: 12.3 KB" in joined

    def test_missing_keys_default_to_zero(self) -> None:
        result = tf._format_snapshot_statistics({"total": 2})
        joined = "\n".join(result)
        assert "Successful restores: 0" in joined
        assert "Average snapshot size: 0.0 KB" in joined


# ---------------------------------------------------------------------------
# _calculate_efficiency_rates
# ---------------------------------------------------------------------------


class TestCalculateEfficiencyRates:
    """Tests for _calculate_efficiency_rates."""

    def test_zero_sessions_yields_zero_rates(self) -> None:
        result = tf._calculate_efficiency_rates({}, {}, {})
        assert result == {
            "interruption_rate": 0.0,
            "recovery_rate": 0.0,
            "productivity_score": 100.0,
        }

    def test_interruption_rate_computed_when_sessions_present(self) -> None:
        sessions = {"total": 4}
        interruptions = {"total": 10}
        result = tf._calculate_efficiency_rates(sessions, interruptions, {})
        assert result["interruption_rate"] == 2.5

    def test_recovery_rate_computed_when_snapshots_present(self) -> None:
        snapshots = {"total": 8, "successful_restores": 6}
        result = tf._calculate_efficiency_rates({}, {}, snapshots)
        assert result["recovery_rate"] == 0.75

    def test_productivity_score_floors_at_zero(self) -> None:
        # Many interruptions per session -> score would be negative; max(0, ...) clamps.
        sessions = {"total": 1}
        interruptions = {"total": 1000}
        result = tf._calculate_efficiency_rates(sessions, interruptions, {})
        assert result["productivity_score"] == 0.0

    def test_productivity_score_high_when_no_interruptions(self) -> None:
        sessions = {"total": 5}
        result = tf._calculate_efficiency_rates(sessions, {}, {})
        # interruption_rate is 0 -> 100 - 0 = 100.
        assert result["productivity_score"] == 100.0

    def test_all_keys_present(self) -> None:
        result = tf._calculate_efficiency_rates(
            {"total": 3},
            {"total": 6},
            {"total": 2, "successful_restores": 1},
        )
        assert set(result.keys()) == {
            "interruption_rate",
            "recovery_rate",
            "productivity_score",
        }
        assert result["interruption_rate"] == 2.0
        assert result["recovery_rate"] == 0.5
        # 100 - 40 = 60
        assert result["productivity_score"] == 60.0


# ---------------------------------------------------------------------------
# _format_efficiency_metrics
# ---------------------------------------------------------------------------


class TestFormatEfficiencyMetrics:
    """Tests for _format_efficiency_metrics."""

    def test_renders_all_three_metrics(self) -> None:
        result = tf._format_efficiency_metrics(
            {"total": 10},
            {"total": 5},
            {"total": 4, "successful_restores": 4},
        )
        joined = "\n".join(result)
        assert "**Efficiency Metrics:**" in joined
        assert "Interruption rate: 0.50 per session" in joined
        assert "Context recovery rate: 100.0%" in joined
        assert "Productivity score: 90.0/100" in joined

    def test_zero_inputs_render_zero_rates(self) -> None:
        result = tf._format_efficiency_metrics({}, {}, {})
        joined = "\n".join(result)
        assert "Interruption rate: 0.00 per session" in joined
        assert "Context recovery rate: 0.0%" in joined
        assert "Productivity score: 100.0/100" in joined

    def test_ends_with_blank_line(self) -> None:
        result = tf._format_efficiency_metrics({}, {}, {})
        assert result[-1] == ""


# ---------------------------------------------------------------------------
# _has_statistics_data
# ---------------------------------------------------------------------------


class TestHasStatisticsData:
    """Tests for _has_statistics_data."""

    def test_all_empty_returns_false(self) -> None:
        assert tf._has_statistics_data({}, {}, {}) is False

    def test_sessions_present_returns_true(self) -> None:
        assert tf._has_statistics_data({"total": 1}, {}, {}) is True

    def test_interruptions_present_returns_true(self) -> None:
        assert tf._has_statistics_data({}, {"total": 1}, {}) is True

    def test_snapshots_present_returns_true(self) -> None:
        assert tf._has_statistics_data({}, {}, {"total": 1}) is True

    def test_total_zero_is_falsy(self) -> None:
        assert tf._has_statistics_data({"total": 0}, {"total": 0}, {"total": 0}) is False


# ---------------------------------------------------------------------------
# _format_no_data_message
# ---------------------------------------------------------------------------


class TestFormatNoDataMessage:
    """Tests for _format_no_data_message."""

    def test_returns_nonempty_lines(self) -> None:
        result = tf._format_no_data_message("alice")
        assert len(result) > 0
        assert all(isinstance(line, str) for line in result)

    def test_contains_user_id(self) -> None:
        result = tf._format_no_data_message("alice")
        joined = "\n".join(result)
        assert "alice" in joined
        assert "No Statistics Available" in joined

    def test_contains_guidance_bullets(self) -> None:
        result = tf._format_no_data_message("alice")
        joined = "\n".join(result)
        assert "start_interruption_monitoring" in joined
        assert "•" in joined


# ---------------------------------------------------------------------------
# _build_search_header
# ---------------------------------------------------------------------------


class TestBuildSearchHeader:
    """Tests for _build_search_header."""

    def test_without_chunk_info(self) -> None:
        result = tf._build_search_header("python", 42)
        joined = "\n".join(result)
        assert "🔍 **Search Results for: 'python'**" in joined
        assert "📊 Found 42 results" in joined
        # Page label should NOT appear without chunk_info.
        assert "Page " not in joined

    def test_with_chunk_info_includes_page_label(self) -> None:
        result = tf._build_search_header(
            "python",
            100,
            {"current_chunk": 2, "total_chunks": 5},
        )
        joined = "\n".join(result)
        assert "📊 Found 100 results (Page 2/5)" in joined

    def test_empty_chunk_info_dict_falls_back_to_no_page_label(self) -> None:
        # An empty dict is falsy in Python, so the no-chunk-info branch is taken.
        result = tf._build_search_header("q", 7, {})
        joined = "\n".join(result)
        assert "Page " not in joined
        assert "📊 Found 7 results" in joined

    def test_unicode_query_preserved(self) -> None:
        result = tf._build_search_header("café", 1)
        assert "café" in result[0]


# ---------------------------------------------------------------------------
# _format_search_results
# ---------------------------------------------------------------------------


class TestFormatSearchResults:
    """Tests for _format_search_results."""

    def test_empty_results_returns_no_results_message(self) -> None:
        assert tf._format_search_results([]) == ["No results found"]

    def test_single_result_format(self) -> None:
        results = [
            {"content": "hello world", "project": "alpha", "timestamp": "2026-01-01"},
        ]
        out = tf._format_search_results(results)
        joined = "\n".join(out)
        assert "1. [alpha]" in joined
        assert "hello world" in joined
        assert "2026-01-01" in joined

    def test_content_truncated_above_300_chars(self) -> None:
        long_content = "x" * 1000
        results = [{"content": long_content, "project": "p", "timestamp": "t"}]
        out = tf._format_search_results(results)
        # The content line should contain at most 300 chars + "..."
        content_line = next(line for line in out if line.startswith("   "))
        assert "..." in content_line
        # The displayed body should be 300 chars total (297 + "...")
        body = content_line.strip()
        # body = "x" * 297 + "..."
        assert len(body) == 300

    def test_content_at_boundary_not_truncated(self) -> None:
        # Exactly 300 chars -> no truncation (uses len > 300).
        content = "y" * 300
        results = [{"content": content, "project": "p", "timestamp": "t"}]
        out = tf._format_search_results(results)
        body_line = next(line for line in out if line.startswith("   "))
        assert "..." not in body_line

    def test_strips_whitespace_around_content(self) -> None:
        results = [{"content": "   spaced out   ", "project": "p", "timestamp": "t"}]
        out = tf._format_search_results(results)
        body_line = next(line for line in out if line.startswith("   "))
        assert body_line == "   spaced out"

    def test_default_project_when_missing(self) -> None:
        results = [{"content": "c", "timestamp": "t"}]
        out = tf._format_search_results(results)
        assert "[Unknown]" in "\n".join(out)

    def test_default_timestamp_empty_string(self) -> None:
        results = [{"content": "c", "project": "p"}]
        out = tf._format_search_results(results)
        # Empty timestamp -> trailing space after "**N. [p]** ".
        assert any(line.endswith("** ") or line.endswith("**") for line in out)

    def test_multiple_results_numbered_in_order(self) -> None:
        results = [
            {"content": "a", "project": "x", "timestamp": "t1"},
            {"content": "b", "project": "y", "timestamp": "t2"},
            {"content": "c", "project": "z", "timestamp": "t3"},
        ]
        out = tf._format_search_results(results)
        joined = "\n".join(out)
        assert "1. [x]" in joined
        assert "2. [y]" in joined
        assert "3. [z]" in joined


# ---------------------------------------------------------------------------
# _format_monitoring_status
# ---------------------------------------------------------------------------


class TestFormatMonitoringStatus:
    """Tests for _format_monitoring_status."""

    def test_monitor_active_branch(self) -> None:
        data = {
            "monitoring_active": True,
            "last_check": "2026-09-04T10:00:00Z",
            "total_checks": 12,
        }
        result = tf._format_monitoring_status(data)
        joined = "\n".join(result)
        assert "✅ Quality monitoring is active" in joined
        assert "2026-09-04T10:00:00Z" in joined
        assert "Checks performed: 12" in joined

    def test_monitor_inactive_branch(self) -> None:
        result = tf._format_monitoring_status({"monitoring_active": False})
        joined = "\n".join(result)
        assert "⏸️ Quality monitoring is inactive" in joined
        assert "quality_monitor" in joined

    def test_monitor_inactive_default_last_check(self) -> None:
        # When monitoring_active True but last_check missing, fallback to "Unknown".
        result = tf._format_monitoring_status({"monitoring_active": True})
        joined = "\n".join(result)
        assert "Last check: Unknown" in joined

    def test_inactive_omits_checks_line(self) -> None:
        # Inactive path should NOT include "Checks performed:".
        result = tf._format_monitoring_status({"monitoring_active": False})
        assert not any("Checks performed" in line for line in result)

    def test_ends_with_blank_line(self) -> None:
        result = tf._format_monitoring_status({"monitoring_active": False})
        assert result[-1] == ""


# ---------------------------------------------------------------------------
# _format_quality_trend
# ---------------------------------------------------------------------------


class TestFormatQualityTrend:
    """Tests for _format_quality_trend."""

    def test_empty_trend_returns_no_data_message(self) -> None:
        assert tf._format_quality_trend({}) == ["📈 No trend data available"]

    def test_empty_dict_trend_branch(self) -> None:
        # Explicit empty mapping also triggers the "no trend" branch.
        assert tf._format_quality_trend({"trend": {}}) == ["📈 No trend data available"]

    def test_full_trend_rendered(self) -> None:
        data = {
            "trend": {
                "current_score": 85,
                "direction": "up",
                "change": 2.5,
            },
        }
        result = tf._format_quality_trend(data)
        joined = "\n".join(result)
        assert "📈 **Quality Trend Analysis**" in joined
        assert "Current quality score: 85/100" in joined
        assert "Trend direction: up" in joined
        assert "Change from last check: +2.5 points" in joined

    def test_negative_change_signed(self) -> None:
        data = {"trend": {"current_score": 60, "direction": "down", "change": -1.5}}
        result = tf._format_quality_trend(data)
        joined = "\n".join(result)
        assert "-1.5 points" in joined

    def test_missing_trend_keys_use_defaults(self) -> None:
        result = tf._format_quality_trend({"trend": {}})
        # empty trend -> early return
        assert result == ["📈 No trend data available"]


# ---------------------------------------------------------------------------
# _format_quality_alerts
# ---------------------------------------------------------------------------


class TestFormatQualityAlerts:
    """Tests for _format_quality_alerts."""

    def test_empty_alerts_returns_clean_message(self) -> None:
        assert tf._format_quality_alerts({}) == ["✅ No quality alerts"]

    def test_empty_alerts_list_branch(self) -> None:
        assert tf._format_quality_alerts({"alerts": []}) == ["✅ No quality alerts"]

    def test_severity_high_icon(self) -> None:
        result = tf._format_quality_alerts(
            {"alerts": [{"severity": "high", "message": "boom"}]},
        )
        joined = "\n".join(result)
        assert "🔴 boom" in joined

    def test_severity_medium_icon(self) -> None:
        result = tf._format_quality_alerts(
            {"alerts": [{"severity": "medium", "message": "warn"}]},
        )
        assert "🟡 warn" in "\n".join(result)

    def test_severity_low_icon(self) -> None:
        result = tf._format_quality_alerts(
            {"alerts": [{"severity": "low", "message": "fyi"}]},
        )
        assert "🔵 fyi" in "\n".join(result)

    def test_unknown_severity_falls_back_to_info_icon(self) -> None:
        result = tf._format_quality_alerts(
            {"alerts": [{"severity": "weird", "message": "x"}]},
        )
        assert "ℹ️ x" in "\n".join(result)

    def test_missing_severity_falls_back_to_info(self) -> None:
        result = tf._format_quality_alerts({"alerts": [{"message": "no-sev"}]})
        assert "ℹ️ no-sev" in "\n".join(result)

    def test_header_present(self) -> None:
        result = tf._format_quality_alerts(
            {"alerts": [{"severity": "low", "message": "x"}]},
        )
        assert result[0] == "🚨 **Quality Alerts**"

    def test_multiple_alerts_each_rendered(self) -> None:
        result = tf._format_quality_alerts(
            {
                "alerts": [
                    {"severity": "high", "message": "one"},
                    {"severity": "low", "message": "two"},
                ],
            },
        )
        joined = "\n".join(result)
        assert "one" in joined
        assert "two" in joined

    def test_ends_with_blank_line(self) -> None:
        result = tf._format_quality_alerts(
            {"alerts": [{"severity": "high", "message": "x"}]},
        )
        assert result[-1] == ""


# ---------------------------------------------------------------------------
# _format_proactive_recommendations
# ---------------------------------------------------------------------------


class TestFormatProactiveRecommendations:
    """Tests for _format_proactive_recommendations."""

    def test_empty_returns_no_recommendations_message(self) -> None:
        assert tf._format_proactive_recommendations({}) == [
            "💡 No recommendations at this time",
        ]

    def test_empty_list_branch(self) -> None:
        assert tf._format_proactive_recommendations({"recommendations": []}) == [
            "💡 No recommendations at this time",
        ]

    def test_single_recommendation_numbered(self) -> None:
        result = tf._format_proactive_recommendations(
            {"recommendations": ["Add tests"]},
        )
        joined = "\n".join(result)
        assert "💡 **Proactive Recommendations**" in joined
        assert "1. Add tests" in joined

    def test_multiple_recommendations_numbered_in_order(self) -> None:
        recs = ["a", "b", "c"]
        result = tf._format_proactive_recommendations({"recommendations": recs})
        joined = "\n".join(result)
        assert "1. a" in joined
        assert "2. b" in joined
        assert "3. c" in joined

    def test_unicode_recommendation_preserved(self) -> None:
        result = tf._format_proactive_recommendations(
            {"recommendations": ["add café tests"]},
        )
        assert "café" in "\n".join(result)

    def test_ends_with_blank_line(self) -> None:
        result = tf._format_proactive_recommendations(
            {"recommendations": ["x"]},
        )
        assert result[-1] == ""


# ---------------------------------------------------------------------------
# _format_monitor_usage_guidance
# ---------------------------------------------------------------------------


class TestFormatMonitorUsageGuidance:
    """Tests for _format_monitor_usage_guidance."""

    def test_returns_nonempty_static_message(self) -> None:
        result = tf._format_monitor_usage_guidance()
        assert len(result) > 0
        joined = "\n".join(result)
        assert "📖 **Usage Guidance**" in joined
        assert "Crackerjack" in joined

    def test_contains_four_bullets(self) -> None:
        result = tf._format_monitor_usage_guidance()
        bullet_lines = [line for line in result if line.startswith("•")]
        assert len(bullet_lines) == 4

    def test_returns_new_list_each_call(self) -> None:
        # The function returns a freshly constructed list, so mutations
        # on the result must not affect subsequent calls.
        first = tf._format_monitor_usage_guidance()
        first.clear()
        second = tf._format_monitor_usage_guidance()
        assert len(second) > 0
