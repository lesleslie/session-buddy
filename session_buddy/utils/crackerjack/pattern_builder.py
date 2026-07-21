"""Pattern mappings builder for Crackerjack output parsing.

This module provides a builder pattern for creating pattern mapping configurations
used in parsing Crackerjack tool output.
"""

from __future__ import annotations


class PatternMappingsBuilder:
    """Builder for creating pattern mappings configuration."""

    def __init__(self) -> None:
        """Initialize pattern mappings builder."""
        self._patterns: dict[str, str] = {}

    def add_test_patterns(self) -> PatternMappingsBuilder:
        """Add test-related patterns."""
        test_patterns = {
            "pytest_result": "pytest_result",
            "pytest_summary": "pytest_result",
            "pytest_coverage": "coverage_summary",
        }
        self._patterns.update(test_patterns)
        return self

    def add_lint_patterns(self) -> PatternMappingsBuilder:
        """Add linting-related patterns."""
        lint_patterns = {
            "ruff_error": "ruff_error",
            "pyright_error": "mypy_error",
        }
        self._patterns.update(lint_patterns)
        return self

    def add_security_patterns(self) -> PatternMappingsBuilder:
        """Add security-related patterns."""
        security_patterns = {
            "bandit_issue": "bandit_finding",
            "bandit_severity": "bandit_finding",
        }
        self._patterns.update(security_patterns)
        return self

    def add_quality_patterns(self) -> PatternMappingsBuilder:
        """Add quality-related patterns."""
        quality_patterns = {
            "quality_score": "quality_score",
            "complexity_score": "quality_score",
        }
        self._patterns.update(quality_patterns)
        return self

    def add_progress_patterns(self) -> PatternMappingsBuilder:
        """Add progress-related patterns."""
        progress_patterns = {
            "progress_indicator": "progress_indicator",
            "percentage": "progress_indicator",
            "task_completion": "progress_indicator",
            "task_failure": "progress_indicator",
        }
        self._patterns.update(progress_patterns)
        return self

    def add_coverage_patterns(self) -> PatternMappingsBuilder:
        """Add coverage-related patterns."""
        coverage_patterns = {
            "coverage_line": "coverage_summary",
            "coverage_total": "coverage_total",
        }
        self._patterns.update(coverage_patterns)
        return self

    def add_misc_patterns(self) -> PatternMappingsBuilder:
        """Add miscellaneous patterns."""
        misc_patterns = {
            "git_commit": "git_commit_hash",
            "file_path_line": "file_path_with_line",
            "execution_time": "execution_time",
        }
        self._patterns.update(misc_patterns)
        return self

    def build(self) -> dict[str, str]:
        """Build the final pattern mappings dictionary."""
        return self._patterns.copy()
