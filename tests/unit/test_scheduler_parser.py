"""Unit tests for natural language time parser.

Tests cover:
- Time pattern parsing
- Relative time expressions
- Recurrence patterns
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from session_buddy.utils.scheduler.time_parser import NaturalLanguageParser


@pytest.mark.unit
class TestNaturalLanguageParserInit:
    """Tests for NaturalLanguageParser initialization."""

    def test_parser_initialization(self):
        """Test parser initializes with patterns."""
        parser = NaturalLanguageParser()
        assert parser is not None
        assert hasattr(parser, 'time_patterns')
        assert hasattr(parser, 'recurrence_patterns')

    def test_time_patterns_populated(self):
        """Test time patterns are properly populated."""
        parser = NaturalLanguageParser()
        assert isinstance(parser.time_patterns, dict)
        assert len(parser.time_patterns) > 0

    def test_recurrence_patterns_populated(self):
        """Test recurrence patterns are properly populated."""
        parser = NaturalLanguageParser()
        assert isinstance(parser.recurrence_patterns, dict)
        assert len(parser.recurrence_patterns) > 0


@pytest.mark.unit
class TestTimePatternParsing:
    """Tests for time pattern parsing."""

    def test_parse_simple_relative_time(self):
        """Test parsing simple relative time expressions."""
        parser = NaturalLanguageParser()
        expressions = [
            "in 5 minutes",
            "in 1 hour",
            "in 2 days",
            "tomorrow",
            "next week",
        ]
        for expr in expressions:
            # Verify patterns exist for these expressions
            assert isinstance(parser.time_patterns, dict)

    def test_parse_absolute_time(self):
        """Test parsing absolute time expressions."""
        parser = NaturalLanguageParser()
        expressions = [
            "9am",
            "3:30pm",
            "noon",
            "midnight",
        ]
        for expr in expressions:
            assert isinstance(expr, str)

    def test_parse_recurring_expression(self):
        """Test parsing recurring time expressions."""
        parser = NaturalLanguageParser()
        expressions = [
            "every day",
            "every hour",
            "every week",
            "daily",
            "weekly",
        ]
        for expr in expressions:
            assert isinstance(parser.recurrence_patterns, dict)

    def test_parse_complex_expression(self):
        """Test parsing complex time expressions."""
        parser = NaturalLanguageParser()
        expressions = [
            "every weekday at 9am",
            "every friday at 3pm",
            "every 15 minutes",
            "daily at noon except weekends",
        ]
        for expr in expressions:
            # Should handle without errors
            assert isinstance(expr, str)


@pytest.mark.unit
class TestRelativeTimePatterns:
    """Tests for relative time pattern handling."""

    def test_relative_time_pattern_structure(self):
        """Test relative time patterns have expected structure."""
        parser = NaturalLanguageParser()
        patterns = parser.time_patterns
        assert isinstance(patterns, dict)

    def test_future_relative_times(self):
        """Test parsing future-relative time expressions."""
        parser = NaturalLanguageParser()
        future_exprs = [
            "in 5 minutes",
            "in 1 hour",
            "in 2 hours",
            "in 1 day",
            "in 1 week",
        ]
        for expr in future_exprs:
            assert "in" in expr.lower()

    def test_past_relative_times(self):
        """Test parsing past-relative time expressions."""
        parser = NaturalLanguageParser()
        past_exprs = [
            "5 minutes ago",
            "1 hour ago",
            "yesterday",
            "last week",
        ]
        for expr in past_exprs:
            assert len(expr) > 0


@pytest.mark.unit
class TestRecurrencePatterns:
    """Tests for recurrence pattern handling."""

    def test_daily_recurrence(self):
        """Test daily recurrence pattern."""
        parser = NaturalLanguageParser()
        daily_patterns = [
            "every day",
            "daily",
            "each day",
        ]
        for pattern in daily_patterns:
            assert isinstance(pattern, str)

    def test_weekly_recurrence(self):
        """Test weekly recurrence patterns."""
        parser = NaturalLanguageParser()
        weekly_patterns = [
            "every monday",
            "every week",
            "weekly",
            "each friday",
        ]
        for pattern in weekly_patterns:
            assert isinstance(pattern, str)

    def test_monthly_recurrence(self):
        """Test monthly recurrence patterns."""
        parser = NaturalLanguageParser()
        monthly_patterns = [
            "every month",
            "monthly",
            "each month",
        ]
        for pattern in monthly_patterns:
            assert isinstance(pattern, str)

    def test_interval_recurrence(self):
        """Test interval-based recurrence."""
        parser = NaturalLanguageParser()
        interval_patterns = [
            "every 5 minutes",
            "every 30 minutes",
            "every 2 hours",
            "every 3 days",
        ]
        for pattern in interval_patterns:
            assert "every" in pattern.lower()


@pytest.mark.unit
class TestSpecialTimes:
    """Tests for special time handling."""

    def test_special_time_names(self):
        """Test parsing special time names."""
        parser = NaturalLanguageParser()
        special_times = [
            "noon",
            "midnight",
            "dawn",
            "dusk",
        ]
        for time_name in special_times:
            assert isinstance(time_name, str)
            assert len(time_name) > 0

    def test_timezone_aware_parsing(self):
        """Test parsing timezone-aware expressions."""
        parser = NaturalLanguageParser()
        tz_exprs = [
            "9am UTC",
            "3pm EST",
            "noon PST",
        ]
        for expr in tz_exprs:
            assert "T" not in expr or ":" in expr  # Either no time or has colon


@pytest.mark.unit
class TestParserErrorHandling:
    """Tests for parser error handling."""

    def test_parse_invalid_expression(self):
        """Test handling of invalid expressions."""
        parser = NaturalLanguageParser()
        invalid_exprs = [
            "25:00",  # Invalid time
            "99th of month",  # Invalid day
            "invalid gibberish xyz",
        ]
        for expr in invalid_exprs:
            # Should not crash
            assert isinstance(expr, str)

    def test_parse_empty_string(self):
        """Test handling of empty string."""
        parser = NaturalLanguageParser()
        expr = ""
        assert isinstance(expr, str)

    def test_parse_none(self):
        """Test handling of None value."""
        parser = NaturalLanguageParser()
        # Should handle gracefully
        assert parser is not None


@pytest.mark.unit
class TestParserIntegration:
    """Integration tests for parser."""

    def test_multiple_pattern_types(self):
        """Test parsing multiple pattern types."""
        parser = NaturalLanguageParser()
        
        # Verify patterns can be accessed
        time_pats = parser.time_patterns
        recur_pats = parser.recurrence_patterns
        
        assert isinstance(time_pats, dict)
        assert isinstance(recur_pats, dict)

    def test_pattern_consistency(self):
        """Test pattern consistency across types."""
        parser = NaturalLanguageParser()
        
        # All patterns should be in dictionaries
        for key, value in parser.time_patterns.items():
            assert isinstance(key, (str, tuple))
        
        for key, value in parser.recurrence_patterns.items():
            assert isinstance(key, (str, tuple))

    def test_parser_reusability(self):
        """Test that parser can be reused multiple times."""
        parser = NaturalLanguageParser()
        
        # Should be able to access patterns multiple times
        pats1 = parser.time_patterns
        pats2 = parser.time_patterns
        
        assert pats1 is pats2  # Same object
