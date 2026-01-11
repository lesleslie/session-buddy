"""Tests for insights console output utilities."""

import io
import sys
from unittest.mock import patch

from session_buddy.insights.console import (
    log_extraction_error,
    log_insight_statistics,
    log_insights_captured,
    log_insights_injected,
    log_insights_pruned,
    log_manual_capture,
    log_no_insights_found,
)


class TestConsoleOutput:
    """Test console output functions produce expected output."""

    def test_log_insights_captured_single(self, capsys):
        """Single insight capture should show singular form."""
        log_insights_captured(1, "response")
        captured = capsys.readouterr()
        assert "✅ Captured 1 insight from response" in captured.out

    def test_log_insights_capped_multiple(self, capsys):
        """Multiple insights should show plural form."""
        log_insights_captured(3, "checkpoint")
        captured = capsys.readouterr()
        assert "✅ Captured 3 insights from checkpoint" in captured.out

    def test_log_insights_captured_zero(self, capsys):
        """Zero insights should not print to stdout."""
        log_insights_captured(0, "response")
        captured = capsys.readouterr()
        assert captured.out == ""  # No stdout output

    def test_log_insights_injected_single(self, capsys):
        """Single insight injection should show singular form."""
        log_insights_injected(1, "async patterns")
        captured = capsys.readouterr()
        assert "💡 Injected 1 relevant insight from past sessions" in captured.out
        assert "async patterns" in captured.out

    def test_log_insights_injected_multiple(self, capsys):
        """Multiple insights should show plural form."""
        log_insights_injected(3)
        captured = capsys.readouterr()
        assert "💡 Injected 3 relevant insights from past sessions" in captured.out

    def test_log_insights_injected_zero(self, capsys):
        """Zero insights should show 'no insights found' message."""
        log_insights_injected(0, "database query")
        captured = capsys.readouterr()
        assert "💭 No relevant insights found for this query" in captured.out

    def test_log_insights_pruned_with_reason(self, capsys):
        """Pruning with reason should include reason in output."""
        log_insights_pruned(5, "unused for 90 days")
        captured = capsys.readouterr()
        assert "🗑️ Pruned 5 stale insights (unused for 90 days)" in captured.out

    def test_log_insights_pruned_no_reason(self, capsys):
        """Pruning without reason should omit parentheses."""
        log_insights_pruned(2)
        captured = capsys.readouterr()
        assert "🗑️ Pruned 2 stale insights" in captured.out
        assert "(" not in captured.out  # No reason text

    def test_log_insight_statistics(self, capsys):
        """Statistics should show formatted summary."""
        log_insight_statistics({
            "total": 100,
            "avg_quality": 0.75,
            "avg_usage": 3.2
        })
        captured = capsys.readouterr()
        assert "📊 Insights: 100 total, quality: 75%, avg usage: 3.2" in captured.out

    def test_log_extraction_error_with_details(self, capsys):
        """Extraction error with details should include details."""
        log_extraction_error("Embedding failed", "Model not loaded")
        captured = capsys.readouterr()
        assert "⚠️ Insight extraction failed (continuing): Model not loaded" in captured.out
        # Note: 'error' param goes to logger, 'details' goes to stdout

    def test_log_extraction_error_no_details(self, capsys):
        """Extraction error without details should omit colon."""
        log_extraction_error("Database error")
        captured = capsys.readouterr()
        assert "⚠️ Insight extraction failed (continuing)" in captured.out
        assert ":" not in captured.out  # No details after

    def test_log_manual_capture(self, capsys):
        """Manual capture should show topic."""
        log_manual_capture("async patterns")
        captured = capsys.readouterr()
        assert "✅ Manually captured insight: async patterns" in captured.out

    def test_log_no_insights_found_with_query(self, capsys):
        """No insights with query should include query."""
        log_no_insights_found("database optimization")
        captured = capsys.readouterr()
        assert "💭 No relevant insights found for 'database optimization'" in captured.out

    def test_log_no_insights_found_no_query(self, capsys):
        """No insights without query should omit query text."""
        log_no_insights_found()
        captured = capsys.readouterr()
        assert "💭 No relevant insights found" in captured.out
        assert "for '" not in captured.out  # No query text

    def test_long_query_truncated(self, capsys):
        """Long queries should be truncated with ellipsis."""
        long_query = "a" * 50
        log_insights_injected(2, long_query)
        captured = capsys.readouterr()
        assert "..." in captured.out  # Should have ellipsis
        # Note: Output includes ANSI color codes, so we just check for truncation marker

    def test_colors_in_output(self, capsys):
        """Output should contain ANSI color codes."""
        log_insights_captured(1)
        captured = capsys.readouterr()
        assert "\033[" in captured.out  # ANSI escape sequences present
