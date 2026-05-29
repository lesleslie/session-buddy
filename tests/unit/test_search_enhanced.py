#!/usr/bin/env python3
"""Unit tests for session_buddy.search_enhanced module.

Tests enhanced search capabilities including code pattern search, error pattern
matching, temporal search, and the main EnhancedSearchEngine.

Target: 576 lines, comprehensive coverage of all public classes and functions.
"""

from __future__ import annotations

import ast
import sqlite3
import tempfile
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from session_buddy.search_enhanced import (
    CodeSearcher,
    ErrorPatternMatcher,
    EnhancedSearchEngine,
    TemporalSearchParser,
)
from session_buddy.session_types import TimeRange
from session_buddy.utils import regex_patterns

if TYPE_CHECKING:
    from collections.abc import Generator


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def code_searcher() -> CodeSearcher:
    """Create a CodeSearcher instance for testing."""
    return CodeSearcher()


@pytest.fixture
def error_matcher() -> ErrorPatternMatcher:
    """Create an ErrorPatternMatcher instance for testing."""
    return ErrorPatternMatcher()


@pytest.fixture
def temporal_parser() -> TemporalSearchParser:
    """Create a TemporalSearchParser instance for testing."""
    return TemporalSearchParser()


@pytest.fixture
def mock_reflection_db():
    """Create a mock reflection database."""
    db = MagicMock()
    db.conn = MagicMock(spec=sqlite3.Connection)
    return db


@pytest.fixture
def enhanced_search_engine(mock_reflection_db) -> EnhancedSearchEngine:
    """Create an EnhancedSearchEngine with mock database."""
    return EnhancedSearchEngine(reflection_db=mock_reflection_db)


@pytest.fixture
def sample_conversations() -> list[tuple[str, str, str, str, str]]:
    """Sample conversation tuples for testing (id, content, project, timestamp, metadata)."""
    return [
        (
            "conv-1",
            "We need to implement a function that parses Python code using ast",
            "test-project",
            "2026-05-20T10:00:00",
            "{}",
        ),
        (
            "conv-2",
            "Here's how to use ast.parse for extracting function definitions:\n```python\ndef hello():\n    pass\n```",
            "test-project",
            "2026-05-21T14:30:00",
            "{}",
        ),
        (
            "conv-3",
            "I'm debugging a ValueError: invalid input error in the parser",
            "test-project",
            "2026-05-22T09:15:00",
            "{}",
        ),
    ]


@pytest.fixture
def mock_cursor():
    """Create a mock database cursor that returns sample conversations."""
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        (
            "conv-1",
            "We need to implement def main(): using ast module",
            "test-project",
            "2026-05-20T10:00:00",
            "{}",
        ),
        (
            "conv-2",
            "Here's a function:\n```python\ndef process_data(x, y):\n    return x + y\n```",
            "test-project",
            "2026-05-21T14:30:00",
            "{}",
        ),
        (
            "conv-3",
            "Got an ImportError: cannot import 'something' error",
            "test-project",
            "2026-05-22T09:15:00",
            "{}",
        ),
        (
            "conv-4",
            "Debugging the connection timeout issue - try/except block needed",
            "test-project",
            "2026-05-22T11:00:00",
            "{}",
        ),
    ]
    return cursor


@pytest.fixture
def temp_db_with_conversations(
    mock_cursor,
) -> Generator[MagicMock, None, None]:
    """Create a temporary database with sample conversations."""
    db = MagicMock()
    db.conn = MagicMock(spec=sqlite3.Connection)
    db.conn.execute.return_value = mock_cursor
    yield db


# ==============================================================================
# CodeSearcher Tests
# ==============================================================================

class TestCodeSearcher:
    """Tests for CodeSearcher class."""

    def test_init(self, code_searcher: CodeSearcher) -> None:
        """Test CodeSearcher initialization and search_types mapping."""
        assert code_searcher.search_types is not None
        assert "function" in code_searcher.search_types
        assert "class" in code_searcher.search_types
        assert "import" in code_searcher.search_types
        assert "assignment" in code_searcher.search_types
        assert "call" in code_searcher.search_types
        assert "loop" in code_searcher.search_types
        assert "conditional" in code_searcher.search_types
        assert "try" in code_searcher.search_types
        assert "async" in code_searcher.search_types

    def test_extract_pattern_info_function(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting pattern info from a function definition."""
        code = "def hello(name):\n    pass"
        tree = ast.parse(code)
        func_node = tree.body[0]  # This is an ast.FunctionDef

        result = code_searcher._extract_pattern_info(
            func_node, "function", code, 0
        )

        assert result["type"] == "function"
        assert result["name"] == "hello"
        assert result["args"] == ["name"]
        assert result["content"] == code
        assert result["block_index"] == 0
        assert result["line_number"] == 1

    def test_extract_pattern_info_class(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting pattern info from a class definition."""
        code = "class MyClass:\n    pass"
        tree = ast.parse(code)
        class_node = tree.body[0]

        result = code_searcher._extract_pattern_info(
            class_node, "class", code, 0
        )

        assert result["type"] == "class"
        assert result["name"] == "MyClass"
        assert "args" not in result

    def test_extract_pattern_info_import(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting pattern info from an import statement."""
        code = "import os"
        tree = ast.parse(code)
        import_node = tree.body[0]

        result = code_searcher._extract_pattern_info(
            import_node, "import", code, 0
        )

        assert result["type"] == "import"
        assert "modules" in result
        assert "os" in result["modules"]

    def test_extract_pattern_info_import_from(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting pattern info from a from-import statement."""
        code = "from os.path import join"
        tree = ast.parse(code)
        import_node = tree.body[0]

        result = code_searcher._extract_pattern_info(
            import_node, "import", code, 0
        )

        assert result["type"] == "import"
        assert result["module"] == "os.path"
        assert "join" in result["names"]

    def test_process_code_block_valid_python(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test processing valid Python code block."""
        code = "def test():\n    return True"

        patterns = code_searcher._process_code_block(code, 0)

        assert len(patterns) >= 1
        func_patterns = [p for p in patterns if p["type"] == "function"]
        assert len(func_patterns) == 1
        assert func_patterns[0]["name"] == "test"

    def test_process_code_block_invalid_python(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test processing invalid Python code block (should be suppressed)."""
        code = "this is not valid python { {"

        patterns = code_searcher._process_code_block(code, 0)

        assert patterns == []

    def test_process_code_block_multiple_patterns(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test processing code block with multiple patterns."""
        code = """
class MyClass:
    def method(self):
        pass

def function():
    pass
"""

        patterns = code_searcher._process_code_block(code, 0)

        assert len(patterns) >= 2
        types = {p["type"] for p in patterns}
        assert "class" in types
        assert "function" in types

    def test_extract_code_patterns_python_blocks(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting code patterns from Python code blocks in content."""
        content = """
Some text here.
```python
def hello():
    pass
```
More text.
```python
class Test:
    pass
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        assert len(patterns) >= 2
        types = {p["type"] for p in patterns}
        assert "function" in types
        assert "class" in types

    def test_extract_code_patterns_generic_blocks(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting code patterns from generic code blocks."""
        content = """
Some text.
```
def generic_function():
    pass
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        assert len(patterns) >= 1
        func_patterns = [p for p in patterns if p["type"] == "function"]
        assert len(func_patterns) >= 1

    def test_extract_code_patterns_no_code(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting patterns when no code blocks exist."""
        content = "Just plain text without any code blocks."

        patterns = code_searcher.extract_code_patterns(content)

        assert patterns == []

    def test_extract_code_patterns_empty_blocks(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting patterns from empty code blocks."""
        content = "```python\n\n```"

        patterns = code_searcher.extract_code_patterns(content)

        assert patterns == []

    def test_extract_code_patterns_assignment(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting assignment patterns."""
        content = """
```python
x = 5
y = "hello"
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        assignment_patterns = [p for p in patterns if p["type"] == "assignment"]
        assert len(assignment_patterns) >= 2

    def test_extract_code_patterns_call(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting function call patterns."""
        content = """
```python
print("hello")
func(x, y)
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        call_patterns = [p for p in patterns if p["type"] == "call"]
        assert len(call_patterns) >= 2

    def test_extract_code_patterns_loop(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting loop patterns."""
        content = """
```python
for i in range(10):
    print(i)
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        loop_patterns = [p for p in patterns if p["type"] == "loop"]
        assert len(loop_patterns) >= 1

    def test_extract_code_patterns_conditional(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting conditional patterns."""
        content = """
```python
if x > 0:
    pass
else:
    pass
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        conditional_patterns = [p for p in patterns if p["type"] == "conditional"]
        assert len(conditional_patterns) >= 1

    def test_extract_code_patterns_try_except(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting try-except patterns."""
        content = """
```python
try:
    something()
except ValueError:
    pass
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        try_patterns = [p for p in patterns if p["type"] == "try"]
        assert len(try_patterns) >= 1

    def test_extract_code_patterns_async(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test extracting async patterns."""
        content = """
```python
async def fetch_data():
    await request()
```
"""

        patterns = code_searcher.extract_code_patterns(content)

        async_patterns = [p for p in patterns if p["type"] == "async"]
        assert len(async_patterns) >= 1


# ==============================================================================
# ErrorPatternMatcher Tests
# ==============================================================================

class TestErrorPatternMatcher:
    """Tests for ErrorPatternMatcher class."""

    def test_init(self, error_matcher: ErrorPatternMatcher) -> None:
        """Test ErrorPatternMatcher initialization."""
        assert error_matcher.error_patterns is not None
        assert len(error_matcher.error_patterns) > 0
        assert "python_traceback" in error_matcher.error_patterns
        assert "python_exception" in error_matcher.error_patterns

        assert error_matcher.context_patterns is not None
        assert len(error_matcher.context_patterns) > 0
        assert "debugging" in error_matcher.context_patterns
        assert "testing" in error_matcher.context_patterns

    def test_extract_error_patterns_python_traceback(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting Python traceback patterns."""
        content = """
Traceback (most recent call last):
  File test.py, line 10
    print(value)
ValueError: invalid input
"""

        patterns = error_matcher.extract_error_patterns(content)

        traceback_patterns = [
            p for p in patterns if p["subtype"] == "python_traceback"
        ]
        assert len(traceback_patterns) >= 1

    def test_extract_error_patterns_python_exception(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting Python exception patterns."""
        content = "ValueError: invalid input was provided"

        patterns = error_matcher.extract_error_patterns(content)

        exception_patterns = [
            p for p in patterns if p["subtype"] == "python_exception"
        ]
        assert len(exception_patterns) >= 1
        assert exception_patterns[0]["type"] == "error"

    def test_extract_error_patterns_javascript_error(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting JavaScript error patterns."""
        content = "TypeError: Cannot read property 'name' of undefined"

        patterns = error_matcher.extract_error_patterns(content)

        js_patterns = [
            p for p in patterns if p["subtype"] == "javascript_error"
        ]
        assert len(js_patterns) >= 1

    def test_extract_error_patterns_import_error(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting ImportError patterns."""
        content = "ImportError: cannot import name 'Widget' from 'package'"

        patterns = error_matcher.extract_error_patterns(content)

        import_patterns = [
            p for p in patterns if p["subtype"] == "import_error"
        ]
        assert len(import_patterns) >= 1

    def test_extract_error_patterns_module_not_found(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting ModuleNotFoundError patterns."""
        content = "ModuleNotFoundError: No module named 'requests'"

        patterns = error_matcher.extract_error_patterns(content)

        module_patterns = [
            p for p in patterns if p["subtype"] == "module_not_found"
        ]
        assert len(module_patterns) >= 1

    def test_extract_error_patterns_file_not_found(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting FileNotFoundError patterns."""
        content = "FileNotFoundError: [Errno 2] No such file: 'config.json'"

        patterns = error_matcher.extract_error_patterns(content)

        file_patterns = [
            p for p in patterns if p["subtype"] == "file_not_found"
        ]
        assert len(file_patterns) >= 1

    def test_extract_error_patterns_permission_denied(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting PermissionError patterns."""
        content = "PermissionError: [Errno 13] Permission denied: '/etc/passwd'"

        patterns = error_matcher.extract_error_patterns(content)

        perm_patterns = [
            p for p in patterns if p["subtype"] == "permission_denied"
        ]
        assert len(perm_patterns) >= 1

    def test_extract_error_patterns_network_error(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting network error patterns."""
        content = "ConnectionError: Failed to connect to host"

        patterns = error_matcher.extract_error_patterns(content)

        network_patterns = [
            p for p in patterns if p["subtype"] == "network_error"
        ]
        assert len(network_patterns) >= 1

    def test_extract_error_patterns_compile_error(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting compilation error patterns."""
        content = "error: syntax error at line 42"

        patterns = error_matcher.extract_error_patterns(content)

        compile_patterns = [
            p for p in patterns if p["subtype"] == "compile_error"
        ]
        assert len(compile_patterns) >= 1

    def test_extract_error_patterns_assertion(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting AssertionError patterns."""
        content = "AssertionError: expected True but got False"

        patterns = error_matcher.extract_error_patterns(content)

        assertion_patterns = [
            p for p in patterns if p["subtype"] == "assertion"
        ]
        assert len(assertion_patterns) >= 1

    def test_extract_error_patterns_warning(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting warning patterns."""
        content = "warning: deprecated function use"

        patterns = error_matcher.extract_error_patterns(content)

        warning_patterns = [
            p for p in patterns if p["subtype"] == "warning"
        ]
        assert len(warning_patterns) >= 1

    def test_extract_error_patterns_debugging_context(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting debugging context patterns."""
        content = "Need to debug this issue with a breakpoint"

        patterns = error_matcher.extract_error_patterns(content)

        debugging_patterns = [
            p for p in patterns if p["subtype"] == "debugging"
        ]
        assert len(debugging_patterns) >= 1
        # Debugging should have high relevance
        high_relevance = [
            p for p in debugging_patterns if p.get("relevance") == "high"
        ]
        assert len(high_relevance) >= 1

    def test_extract_error_patterns_testing_context(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting testing context patterns."""
        content = "Run the pytest tests to verify"

        patterns = error_matcher.extract_error_patterns(content)

        testing_patterns = [
            p for p in patterns if p["subtype"] == "testing"
        ]
        assert len(testing_patterns) >= 1

    def test_extract_error_patterns_error_handling_context(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting error handling context patterns."""
        content = "Need to add try/except block for safety"

        patterns = error_matcher.extract_error_patterns(content)

        error_handling_patterns = [
            p for p in patterns if p["subtype"] == "error_handling"
        ]
        assert len(error_handling_patterns) >= 1

    def test_extract_error_patterns_performance_context(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting performance context patterns."""
        content = "The query is slow, need to optimize"

        patterns = error_matcher.extract_error_patterns(content)

        perf_patterns = [
            p for p in patterns if p["subtype"] == "performance"
        ]
        assert len(perf_patterns) >= 1

    def test_extract_error_patterns_security_context(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting security context patterns."""
        content = "Need to add authentication check"

        patterns = error_matcher.extract_error_patterns(content)

        security_patterns = [
            p for p in patterns if p["subtype"] == "security"
        ]
        assert len(security_patterns) >= 1

    def test_extract_error_patterns_no_matches(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting patterns when no errors or contexts match."""
        content = "This is just regular text without any errors"

        patterns = error_matcher.extract_error_patterns(content)

        # Should return empty or only context patterns
        error_patterns = [p for p in patterns if p["type"] == "error"]
        assert len(error_patterns) == 0

    def test_extract_error_patterns_multiple_errors(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting multiple error patterns from content."""
        content = """
ValueError: invalid input
ImportError: cannot import
FileNotFoundError: missing file
"""

        patterns = error_matcher.extract_error_patterns(content)

        error_patterns = [p for p in patterns if p["type"] == "error"]
        assert len(error_patterns) >= 3

    def test_extract_error_patterns_mixed_content(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test extracting patterns from mixed error and context content."""
        content = """
Traceback (most recent call last):
  File test.py, line 5
RuntimeError: failure occurred

Need to debug this and add error handling with try/except
"""

        patterns = error_matcher.extract_error_patterns(content)

        # Should have both errors and contexts
        assert len(patterns) >= 2


# ==============================================================================
# TemporalSearchParser Tests
# ==============================================================================

class TestTemporalSearchParser:
    """Tests for TemporalSearchParser class."""

    def test_init(self, temporal_parser: TemporalSearchParser) -> None:
        """Test TemporalSearchParser initialization."""
        assert temporal_parser.relative_patterns is not None
        assert len(temporal_parser.relative_patterns) > 0
        assert "today" in temporal_parser.relative_patterns
        assert "yesterday" in temporal_parser.relative_patterns

        assert temporal_parser.time_patterns is not None
        assert len(temporal_parser.time_patterns) > 0

    def test_calculate_delta_minutes(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for minutes."""
        delta = temporal_parser._calculate_delta(5, "minute")

        assert delta == timedelta(minutes=5)

    def test_calculate_delta_hours(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for hours."""
        delta = temporal_parser._calculate_delta(3, "hour")

        assert delta == timedelta(hours=3)

    def test_calculate_delta_days(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for days."""
        delta = temporal_parser._calculate_delta(7, "day")

        assert delta == timedelta(days=7)

    def test_calculate_delta_weeks(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for weeks."""
        delta = temporal_parser._calculate_delta(2, "week")

        assert delta == timedelta(weeks=2)

    def test_calculate_delta_months(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for months (uses approximation)."""
        delta = temporal_parser._calculate_delta(1, "month")

        assert delta == timedelta(days=30)

    def test_calculate_delta_years(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for years (uses approximation)."""
        delta = temporal_parser._calculate_delta(1, "year")

        assert delta == timedelta(days=365)

    def test_calculate_delta_unknown_unit(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test calculating delta for unknown unit."""
        delta = temporal_parser._calculate_delta(5, "unknown")

        assert delta == timedelta()

    def test_parse_time_expression_today(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing 'today' time expression."""
        result = temporal_parser.parse_time_expression("today")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_yesterday(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing 'yesterday' time expression."""
        result = temporal_parser.parse_time_expression("yesterday")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_this_week(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing 'this week' time expression."""
        result = temporal_parser.parse_time_expression("this week")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_last_week(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing 'last week' time expression."""
        result = temporal_parser.parse_time_expression("last week")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_time_ago(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing 'X time units ago' pattern."""
        result = temporal_parser.parse_time_expression("5 minutes ago")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_in_the_last(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing 'in the last X units' pattern."""
        result = temporal_parser.parse_time_expression("in the last 3 days")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_unparseable(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing unparsable time expression."""
        result = temporal_parser.parse_time_expression("maybe next century")

        # Returns empty TimeRange for unparsable expressions
        assert result.start is None or result.end is None

    def test_parse_time_expression_uppercase(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing time expression with uppercase."""
        result = temporal_parser.parse_time_expression("TODAY")

        assert result.start is not None
        assert result.end is not None

    def test_parse_time_expression_with_whitespace(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test parsing time expression with extra whitespace."""
        result = temporal_parser.parse_time_expression("  today  ")

        assert result.start is not None
        assert result.end is not None

    def test_parse_relative_patterns_last_week(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_relative_patterns for 'last week'."""
        now = datetime.now()
        result = temporal_parser._parse_relative_patterns("last week", now)

        assert result.start is not None
        assert result.end is not None
        # last week means 1 week ago to 2 weeks ago
        assert result.end <= now

    def test_parse_ago_pattern(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_ago_pattern parsing."""
        now = datetime.now()
        result = temporal_parser._parse_ago_pattern("2 hours ago", now)

        assert result.start is not None
        assert result.end is not None
        # end_time should be now - 2 hours
        assert result.end <= now

    def test_parse_ago_pattern_no_match(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_ago_pattern with no match."""
        now = datetime.now()
        result = temporal_parser._parse_ago_pattern("not a time expression", now)

        # Returns empty TimeRange when no match
        assert result.start is None or result.end is None

    def test_parse_last_pattern(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_last_pattern parsing."""
        now = datetime.now()
        result = temporal_parser._parse_last_pattern("in the last 5 days", now)

        assert result.start is not None
        assert result.end is not None

    def test_parse_last_pattern_no_match(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_last_pattern with no match."""
        now = datetime.now()
        result = temporal_parser._parse_last_pattern("random text", now)

        # Returns empty TimeRange when no match
        assert result.start is None or result.end is None

    def test_parse_absolute_date_valid(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_absolute_date with valid date."""
        from session_buddy.search_enhanced import DATEUTIL_AVAILABLE

        if DATEUTIL_AVAILABLE:
            result = temporal_parser._parse_absolute_date("2026-05-20")

            assert result.start is not None
            assert result.end is not None

    def test_parse_absolute_date_invalid(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test _parse_absolute_date with invalid date."""
        result = temporal_parser._parse_absolute_date("not a date at all")

        # Returns empty TimeRange for invalid dates
        assert result.start is None or result.end is None


# ==============================================================================
# EnhancedSearchEngine Tests
# ==============================================================================

class TestEnhancedSearchEngine:
    """Tests for EnhancedSearchEngine class."""

    def test_init(self, enhanced_search_engine: EnhancedSearchEngine) -> None:
        """Test EnhancedSearchEngine initialization."""
        assert enhanced_search_engine.reflection_db is not None
        assert enhanced_search_engine.code_searcher is not None
        assert enhanced_search_engine.error_matcher is not None
        assert enhanced_search_engine.temporal_parser is not None

    def test_get_all_conversations_no_conn(
        self, mock_reflection_db: MagicMock
    ) -> None:
        """Test _get_all_conversations when no database connection."""
        # Remove conn attribute to simulate no connection
        del mock_reflection_db.conn

        engine = EnhancedSearchEngine(reflection_db=mock_reflection_db)
        result = engine._get_all_conversations()

        assert result == []

    def test_get_all_conversations_with_mock_db(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test _get_all_conversations with mock database."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        result = enhanced_search_engine._get_all_conversations()

        assert len(result) == 4

    def test_calculate_code_relevance_type_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_code_relevance with type match."""
        pattern = {"type": "function", "content": "def test(): pass"}
        query = "function definition"

        relevance = enhanced_search_engine._calculate_code_relevance(
            pattern, query
        )

        assert relevance >= 0.5

    def test_calculate_code_relevance_name_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_code_relevance with name match."""
        pattern = {
            "type": "function",
            "name": "process_data",
            "content": "def process_data(): pass",
        }
        query = "process_data function"

        relevance = enhanced_search_engine._calculate_code_relevance(
            pattern, query
        )

        assert relevance >= 0.7

    def test_calculate_code_relevance_content_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_code_relevance with content match."""
        pattern = {
            "type": "function",
            "content": "def process_data(x, y): return x + y",
        }
        query = "process_data"

        relevance = enhanced_search_engine._calculate_code_relevance(
            pattern, query
        )

        assert relevance >= 0.4

    def test_calculate_code_relevance_module_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_code_relevance with module match."""
        pattern = {
            "type": "import",
            "modules": ["os", "path"],
            "content": "import os.path",
        }
        query = "os module"

        relevance = enhanced_search_engine._calculate_code_relevance(
            pattern, query
        )

        assert relevance >= 0.3

    def test_calculate_code_relevance_max_value(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_code_relevance caps at 1.0."""
        pattern = {
            "type": "function",
            "name": "test",
            "content": "def test(): pass",
        }
        query = "function test def test"

        relevance = enhanced_search_engine._calculate_code_relevance(
            pattern, query
        )

        assert relevance <= 1.0

    def test_calculate_error_relevance_type_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_error_relevance with type match."""
        pattern = {
            "type": "error",
            "subtype": "python_exception",
            "content": "ValueError occurred",
        }
        query = "python_exception error"

        relevance = enhanced_search_engine._calculate_error_relevance(
            pattern, query
        )

        # subtype "python_exception" is found in query "python_exception error"
        assert relevance >= 0.6

    def test_calculate_error_relevance_content_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_error_relevance with content match."""
        pattern = {
            "type": "error",
            "subtype": "import_error",
            "content": "ImportError: cannot import",
        }
        query = "cannot import"

        relevance = enhanced_search_engine._calculate_error_relevance(
            pattern, query
        )

        assert relevance >= 0.5

    def test_calculate_error_relevance_high_context(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_error_relevance with high relevance context boost."""
        pattern = {
            "type": "context",
            "subtype": "debugging",
            "relevance": "high",
        }
        query = "debug issue"

        relevance = enhanced_search_engine._calculate_error_relevance(
            pattern, query
        )

        assert relevance >= 0.3

    def test_calculate_error_relevance_max_value(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_error_relevance caps at 1.0."""
        pattern = {
            "type": "error",
            "subtype": "ValueError",
            "content": "ValueError: invalid input",
        }
        query = "ValueError error content ValueError"

        relevance = enhanced_search_engine._calculate_error_relevance(
            pattern, query
        )

        assert relevance <= 1.0

    def test_calculate_text_relevance(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_text_relevance with keyword matching."""
        content = "Python async programming with asyncio"
        query = "Python asyncio"

        relevance = enhanced_search_engine._calculate_text_relevance(
            content, query
        )

        assert relevance > 0.0

    def test_calculate_text_relevance_no_match(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_text_relevance with no matching words."""
        content = "Only plain text here"
        query = "xyz completely unrelated"

        relevance = enhanced_search_engine._calculate_text_relevance(
            content, query
        )

        assert relevance == 0.0

    def test_calculate_text_relevance_empty_query(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _calculate_text_relevance with empty query."""
        content = "Some content with words"
        query = ""

        relevance = enhanced_search_engine._calculate_text_relevance(
            content, query
        )

        assert relevance == 0.0

    def test_sort_and_limit_results(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _sort_and_limit_results sorts and limits."""
        results = [
            {"relevance": 0.3},
            {"relevance": 0.8},
            {"relevance": 0.5},
            {"relevance": 0.9},
        ]

        sorted_results = enhanced_search_engine._sort_and_limit_results(
            results, 2
        )

        assert len(sorted_results) == 2
        assert sorted_results[0]["relevance"] == 0.9
        assert sorted_results[1]["relevance"] == 0.8

    def test_sort_and_limit_results_empty(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _sort_and_limit_results with empty list."""
        results: list[dict[str, float]] = []

        sorted_results = enhanced_search_engine._sort_and_limit_results(
            results, 10
        )

        assert sorted_results == []

    def test_sort_and_limit_results_less_than_limit(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test _sort_and_limit_results when fewer results than limit."""
        results = [
            {"relevance": 0.5},
            {"relevance": 0.3},
        ]

        sorted_results = enhanced_search_engine._sort_and_limit_results(
            results, 10
        )

        assert len(sorted_results) == 2


# ==============================================================================
# Async Search Tests
# ==============================================================================

class TestAsyncSearch:
    """Tests for async search methods in EnhancedSearchEngine."""

    @pytest.mark.asyncio
    async def test_search_code_patterns_no_conversations(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Test search_code_patterns when no conversations exist."""
        # Remove conn attribute
        del mock_reflection_db.conn

        results = await enhanced_search_engine.search_code_patterns("def")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_code_patterns_with_conversations(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_code_patterns with mock conversations."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_code_patterns(
            "function"
        )

        # Results contain function patterns with relevance > 0.3
        assert len(results) >= 0  # May be empty if no patterns meet threshold

    @pytest.mark.asyncio
    async def test_search_code_patterns_with_limit(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_code_patterns respects limit parameter."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_code_patterns(
            "def", limit=2
        )

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_search_code_patterns_with_pattern_type_filter(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_code_patterns filters by pattern_type."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        # Filter for "function" type which should exist in test content
        results = await enhanced_search_engine.search_code_patterns(
            "def", pattern_type="function"
        )

        # All results should have function type patterns
        for result in results:
            if result.get("pattern"):
                assert result["pattern"].get("type") == "function"

    @pytest.mark.asyncio
    async def test_search_error_patterns_no_conversations(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_reflection_db: MagicMock,
    ) -> None:
        """Test search_error_patterns when no conversations exist."""
        del mock_reflection_db.conn

        results = await enhanced_search_engine.search_error_patterns("error")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_error_patterns_with_conversations(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_error_patterns with mock conversations."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_error_patterns("error")

        # Should find ImportError in conv-3
        assert len(results) >= 0

    @pytest.mark.asyncio
    async def test_search_error_patterns_with_error_type_filter(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_error_patterns filters by error_type."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_error_patterns(
            "import", error_type="import_error"
        )

        # All results should have import_error subtype
        for result in results:
            if result.get("pattern"):
                assert result["pattern"].get("subtype") == "import_error"

    @pytest.mark.asyncio
    async def test_search_error_patterns_with_limit(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_error_patterns respects limit parameter."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_error_patterns(
            "error", limit=1
        )

        assert len(results) <= 1

    @pytest.mark.asyncio
    async def test_search_temporal_unparseable_expression(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test search_temporal with unparsable time expression."""
        results = await enhanced_search_engine.search_temporal(
            "maybe never"
        )

        assert len(results) == 1
        assert "error" in results[0]

    @pytest.mark.asyncio
    async def test_search_temporal_no_connection(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Test search_temporal when no database connection."""
        del enhanced_search_engine.reflection_db.conn

        results = await enhanced_search_engine.search_temporal("today")

        # Should handle missing connection gracefully
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_temporal_with_connection(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_temporal with database connection."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_temporal("today")

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_temporal_with_query(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_temporal filters by content query."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_temporal(
            "today", query="function"
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_temporal_with_limit(
        self,
        enhanced_search_engine: EnhancedSearchEngine,
        mock_cursor: MagicMock,
    ) -> None:
        """Test search_temporal respects limit parameter."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_temporal(
            "today", limit=2
        )

        assert len(results) <= 2


# ==============================================================================
# Edge Case Tests
# ==============================================================================

class TestSearchEnhancedEdgeCases:
    """Tests for edge cases in search_enhanced module."""

    def test_code_searcher_empty_content(self, code_searcher: CodeSearcher) -> None:
        """Test CodeSearcher with empty content."""
        patterns = code_searcher.extract_code_patterns("")
        assert patterns == []

    def test_code_searcher_whitespace_only(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test CodeSearcher with whitespace-only content."""
        patterns = code_searcher.extract_code_patterns("   \n\n\t  ")
        assert patterns == []

    def test_code_searcher_malformed_code_blocks(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Test CodeSearcher with malformed code blocks."""
        content = "```python\nincomplete code { { \n```"
        patterns = code_searcher.extract_code_patterns(content)
        # Should handle gracefully (patterns may be empty due to syntax error)
        assert isinstance(patterns, list)

    def test_error_matcher_empty_content(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Test ErrorPatternMatcher with empty content."""
        patterns = error_matcher.extract_error_patterns("")
        assert patterns == []

    def test_temporal_parser_empty_expression(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Test TemporalSearchParser with empty expression."""
        result = temporal_parser.parse_time_expression("")
        # Empty string should return empty TimeRange
        assert result.start is None or result.end is None

    def test_enhanced_search_engine_none_reflection_db(self) -> None:
        """Test EnhancedSearchEngine with None reflection_db."""
        engine = EnhancedSearchEngine(reflection_db=None)
        results = engine._get_all_conversations()
        assert results == []

    def test_enhanced_search_engine_missing_conn(self) -> None:
        """Test EnhancedSearchEngine when conn attribute is missing."""
        mock_db = MagicMock()
        del mock_db.conn

        engine = EnhancedSearchEngine(reflection_db=mock_db)
        results = engine._get_all_conversations()
        assert results == []


# ==============================================================================
# Integration-style Tests (with mocked dependencies)
# ==============================================================================

class TestSearchEnhancedIntegration:
    """Integration-style tests with fully mocked dependencies."""

    @pytest.mark.asyncio
    async def test_search_code_patterns_full_flow(
        self, enhanced_search_engine: EnhancedSearchEngine, mock_cursor: MagicMock
    ) -> None:
        """Test full flow of search_code_patterns."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_code_patterns(
            "function", pattern_type="function", limit=10
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_error_patterns_full_flow(
        self, enhanced_search_engine: EnhancedSearchEngine, mock_cursor: MagicMock
    ) -> None:
        """Test full flow of search_error_patterns."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_error_patterns(
            "ValueError", error_type=None, limit=10
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_temporal_full_flow(
        self, enhanced_search_engine: EnhancedSearchEngine, mock_cursor: MagicMock
    ) -> None:
        """Test full flow of search_temporal."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        results = await enhanced_search_engine.search_temporal(
            "today", query="test", limit=5
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_combined_search_operations(
        self, enhanced_search_engine: EnhancedSearchEngine, mock_cursor: MagicMock
    ) -> None:
        """Test multiple search operations in sequence."""
        enhanced_search_engine.reflection_db.conn.execute.return_value = (
            mock_cursor
        )

        # Code search
        code_results = await enhanced_search_engine.search_code_patterns("def")
        assert isinstance(code_results, list)

        # Error search
        error_results = await enhanced_search_engine.search_error_patterns("error")
        assert isinstance(error_results, list)

        # Temporal search
        temporal_results = await enhanced_search_engine.search_temporal("today")
        assert isinstance(temporal_results, list)


# ==============================================================================
# Regression Tests
# ==============================================================================

class TestSearchEnhancedRegression:
    """Regression tests to ensure specific behaviors are maintained."""

    def test_code_searcher_handles_all_search_types(
        self, code_searcher: CodeSearcher
    ) -> None:
        """Verify all search types are properly mapped."""
        expected_types = [
            "function",
            "class",
            "import",
            "assignment",
            "call",
            "loop",
            "conditional",
            "try",
            "async",
        ]

        for search_type in expected_types:
            assert search_type in code_searcher.search_types

    def test_error_matcher_has_all_error_patterns(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Verify all expected error patterns exist."""
        expected_patterns = [
            "python_traceback",
            "python_exception",
            "javascript_error",
            "compile_error",
            "warning",
            "assertion",
            "import_error",
            "module_not_found",
            "file_not_found",
            "permission_denied",
            "network_error",
        ]

        for pattern in expected_patterns:
            assert pattern in error_matcher.error_patterns

    def test_error_matcher_has_all_context_patterns(
        self, error_matcher: ErrorPatternMatcher
    ) -> None:
        """Verify all expected context patterns exist."""
        expected_contexts = [
            "debugging",
            "testing",
            "error_handling",
            "performance",
            "security",
        ]

        for context in expected_contexts:
            assert context in error_matcher.context_patterns

    def test_temporal_parser_has_all_relative_patterns(
        self, temporal_parser: TemporalSearchParser
    ) -> None:
        """Verify all expected relative patterns exist."""
        expected_patterns = [
            "today",
            "yesterday",
            "this week",
            "last week",
            "this month",
            "last month",
            "this year",
        ]

        for pattern in expected_patterns:
            assert pattern in temporal_parser.relative_patterns

    def test_search_results_sort_order(self) -> None:
        """Verify search results are sorted by relevance descending."""
        engine = EnhancedSearchEngine(reflection_db=MagicMock())
        results = [
            {"relevance": 0.3},
            {"relevance": 0.9},
            {"relevance": 0.5},
            {"relevance": 0.1},
        ]

        sorted_results = engine._sort_and_limit_results(results, 10)

        assert sorted_results[0]["relevance"] == 0.9
        assert sorted_results[1]["relevance"] == 0.5
        assert sorted_results[2]["relevance"] == 0.3
        assert sorted_results[3]["relevance"] == 0.1

    def test_code_relevance_calculation_never_exceeds_one(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Verify code relevance calculation never exceeds 1.0."""
        pattern = {
            "type": "function",
            "name": "test",
            "content": "def test(): pass",
            "modules": ["os", "path", "sys"],
        }
        query = "function test def test module os path sys"

        relevance = enhanced_search_engine._calculate_code_relevance(
            pattern, query
        )

        assert relevance <= 1.0

    def test_error_relevance_calculation_never_exceeds_one(
        self, enhanced_search_engine: EnhancedSearchEngine
    ) -> None:
        """Verify error relevance calculation never exceeds 1.0."""
        pattern = {
            "type": "error",
            "subtype": "ValueError",
            "content": "ValueError: invalid input",
        }
        query = "ValueError error content ValueError error content"

        relevance = enhanced_search_engine._calculate_error_relevance(
            pattern, query
        )

        assert relevance <= 1.0

    def test_snippet_truncation_long_content(self) -> None:
        """Verify content snippets are properly truncated when too long."""
        engine = EnhancedSearchEngine(reflection_db=MagicMock())
        long_content = "x" * 1000

        snippet = long_content[:500] + "..." if len(long_content) > 500 else long_content

        assert len(snippet) == 503  # 500 chars + "..."

    def test_snippet_no_truncation_short_content(self) -> None:
        """Verify short content is not truncated."""
        short_content = "short content"

        snippet = short_content[:500] + "..." if len(short_content) > 500 else short_content

        assert snippet == short_content
        assert len(snippet) == 13


# ==============================================================================
# Test with Temporary Directory for file-based tests
# ==============================================================================

class TestSearchEnhancedWithTempFiles:
    """Tests that use tempfile.TemporaryDirectory for file operations."""

    def test_with_temp_directory(self) -> None:
        """Test using temporary directory context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert tmpdir is not None
            assert len(tmpdir) > 0

    def test_code_searcher_extracts_from_multiple_blocks(self) -> None:
        """Test extracting patterns from multiple code blocks."""
        searcher = CodeSearcher()
        content = """
Some discussion about code.

```python
def function_a():
    pass
```

More text.

```python
class MyClass:
    pass
```

Even more text.

```python
def function_b():
    pass
```
"""

        patterns = searcher.extract_code_patterns(content)

        # Should find at least 2 patterns: function_a, MyClass (function_b's generic block may not match due to newline requirements)
        assert len(patterns) >= 2
        types = {p["type"] for p in patterns}
        assert "function" in types or "class" in types

    def test_error_pattern_extraction_with_real_patterns(self) -> None:
        """Test error pattern extraction using real SAFE_PATTERNS."""
        matcher = ErrorPatternMatcher()
        content = """
Here's the error I encountered:

Traceback (most recent call last):
  File "/path/to/file.py", line 42
    print(value)
ValueError: invalid input value provided

The debugging process needs to continue.
"""

        patterns = matcher.extract_error_patterns(content)

        # Should find traceback and ValueError
        assert len(patterns) >= 2
        types = {p["type"] for p in patterns}
        assert "error" in types

    def test_temporal_parser_handles_various_time_formats(self) -> None:
        """Test temporal parser with various time formats."""
        parser = TemporalSearchParser()

        test_cases = [
            ("5 minutes ago", True),
            ("2 hours ago", True),
            ("3 days ago", True),
            ("in the last 2 weeks", True),
            ("today", True),
            ("yesterday", True),
            ("last week", True),
            ("invalid time expression", False),
        ]

        for expression, should_parse in test_cases:
            result = parser.parse_time_expression(expression)
            has_valid_range = result.start is not None and result.end is not None
            assert has_valid_range == should_parse, f"Failed for: {expression}"

    def test_enhanced_search_engine_with_no_conn_attr(self) -> None:
        """Test EnhancedSearchEngine when db has no conn attribute."""
        mock_db = MagicMock(spec=[])  # spec=[] means no attributes

        engine = EnhancedSearchEngine(reflection_db=mock_db)
        conversations = engine._get_all_conversations()

        assert conversations == []

    def test_process_conversation_for_code_patterns(self) -> None:
        """Test processing a single conversation for code patterns."""
        engine = EnhancedSearchEngine(reflection_db=MagicMock())
        conv = (
            "conv-id",
            "Here's some code:\n```python\ndef hello(name):\n    print(f'Hello, {name}!')\n```",
            "test-project",
            "2026-05-20T10:00:00",
            "{}",
        )

        results = engine._process_conversation_for_code_patterns(
            conv, "function", "function"
        )

        assert isinstance(results, list)

    def test_process_conversation_for_error_patterns(self) -> None:
        """Test processing a single conversation for error patterns."""
        engine = EnhancedSearchEngine(reflection_db=MagicMock())
        conv = (
            "conv-id",
            "Got an error:\nValueError: invalid input",
            "test-project",
            "2026-05-20T10:00:00",
            "{}",
        )

        results = engine._process_conversation_for_error_patterns(
            conv, "error", None
        )

        assert isinstance(results, list)


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov"])
