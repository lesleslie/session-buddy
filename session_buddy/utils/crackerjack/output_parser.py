"""Crackerjack output parser for structured data extraction.

This module provides parsing capabilities for Crackerjack tool output,
extracting test results, lint issues, security findings, coverage data,
complexity metrics, and progress information.
"""

from __future__ import annotations

import operator
from typing import Any

from session_buddy.utils.crackerjack.pattern_builder import PatternMappingsBuilder
from session_buddy.utils.regex_patterns import SAFE_PATTERNS


class CrackerjackOutputParser:
    """Parses Crackerjack output for structured data extraction."""

    def __init__(self) -> None:
        """Initialize output parser with builder pattern."""
        self.patterns = self._create_patterns()

    def _create_patterns(self) -> dict[str, str]:
        """Create pattern mappings using builder pattern."""
        return (
            PatternMappingsBuilder()
            .add_test_patterns()
            .add_lint_patterns()
            .add_security_patterns()
            .add_quality_patterns()
            .add_progress_patterns()
            .add_coverage_patterns()
            .add_misc_patterns()
            .build()
        )

    def parse_output(
        self,
        command: str,
        stdout: str,
        stderr: str,
    ) -> tuple[dict[str, Any], list[str]]:
        """Parse Crackerjack output and extract insights."""
        parsed_data = self._init_parsed_data(command)
        memory_insights: list[str] = []
        full_output = f"{stdout}\n{stderr}"

        # Apply applicable parsers based on command
        for parser_type in self._get_applicable_parsers(command):
            self._apply_parser(parser_type, full_output, parsed_data, memory_insights)

        # Always parse progress information
        self._apply_parser("progress", full_output, parsed_data, memory_insights)

        return parsed_data, memory_insights

    def _init_parsed_data(self, command: str) -> dict[str, Any]:
        """Initialize parsed data structure."""
        return {
            "command": command,
            "test_results": [],
            "lint_issues": [],
            "security_issues": [],
            "coverage_data": {},
            "complexity_data": {},
            "progress_info": {},
            "quality_metrics": {},
        }

    def _get_applicable_parsers(self, command: str) -> list[str]:
        """Get list of parsers to apply for a command."""
        parser_map = {
            "test": ["test", "coverage"],
            "check": ["test", "lint", "security", "coverage", "complexity"],
            "lint": ["lint"],
            "format": ["lint"],
            "security": ["security"],
            "coverage": ["coverage"],
            "complexity": ["complexity"],
        }
        return parser_map.get(command, [])

    def _apply_parser(
        self,
        parser_type: str,
        output: str,
        parsed_data: dict[str, Any],
        insights: list[str],
    ) -> None:
        """Apply a specific parser and extract insights."""
        parser_methods = {
            "test": (self._parse_test_output, self._extract_test_insights),
            "lint": (self._parse_lint_output, self._extract_lint_insights),
            "security": (self._parse_security_output, self._extract_security_insights),
            "coverage": (self._parse_coverage_output, self._extract_coverage_insights),
            "complexity": (
                self._parse_complexity_output,
                self._extract_complexity_insights,
            ),
            "progress": (self._parse_progress_output, self._extract_progress_insights),
        }

        if parser_type in parser_methods:
            parse_method, extract_method = parser_methods[parser_type]
            parsed_data.update(parse_method(output))
            insights.extend(extract_method(parsed_data))

    def _parse_test_output(self, output: str) -> dict[str, Any]:
        """Parse pytest output for test results."""
        data: dict[str, Any] = {"test_results": [], "test_summary": {}}

        lines = output.split("\n")

        for line in lines:
            # Test result lines
            pytest_pattern = SAFE_PATTERNS[self.patterns["pytest_result"]]
            match = pytest_pattern.search(line)
            if match:
                file_path, test_name, status, coverage, duration = match.groups()
                data["test_results"].append(
                    {
                        "file": file_path,
                        "test": test_name,
                        "status": status.lower(),
                        "coverage": coverage,
                        "duration": duration,
                    },
                )

            # Summary lines
            summary_pattern = SAFE_PATTERNS[self.patterns["pytest_summary"]]
            summary_match = summary_pattern.search(line)
            if summary_match:
                summary_text = summary_match.group(1)
                if "passed" in summary_text or "failed" in summary_text:
                    data["test_summary"]["summary"] = summary_text

        return data

    def _parse_lint_output(self, output: str) -> dict[str, Any]:
        """Parse lint output for code quality issues."""
        data: dict[str, Any] = {"lint_issues": [], "lint_summary": {}}

        lines = output.split("\n")
        total_errors = 0

        for line in lines:
            # Ruff errors
            ruff_pattern = SAFE_PATTERNS[self.patterns["ruff_error"]]
            ruff_match = ruff_pattern.search(line)
            if ruff_match:
                file_path, line_num, col_num, error_type, message = ruff_match.groups()
                data["lint_issues"].append(
                    {
                        "tool": "ruff",
                        "file": file_path,
                        "line": int(line_num),
                        "column": int(col_num),
                        "type": error_type,
                        "message": message,
                    },
                )
                total_errors += 1

            # Pyright errors
            pyright_pattern = SAFE_PATTERNS[self.patterns["pyright_error"]]
            pyright_match = pyright_pattern.search(line)
            if pyright_match:
                file_path, line_num, col_num, severity, message = pyright_match.groups()
                data["lint_issues"].append(
                    {
                        "tool": "pyright",
                        "file": file_path,
                        "line": int(line_num),
                        "column": int(col_num),
                        "type": severity,
                        "message": message,
                    },
                )
                total_errors += 1

        data["lint_summary"] = {"total_issues": total_errors}
        return data

    def _parse_security_output(self, output: str) -> dict[str, Any]:
        """Parse bandit security scan output."""
        data: dict[str, Any] = {"security_issues": [], "security_summary": {}}

        lines = output.split("\n")
        current_issue = None

        for line in lines:
            bandit_issue_pattern = SAFE_PATTERNS[self.patterns["bandit_issue"]]
            issue_match = bandit_issue_pattern.search(line)
            if issue_match:
                issue_id, description = issue_match.groups()
                current_issue = {
                    "id": issue_id,
                    "description": description,
                    "severity": None,
                    "confidence": None,
                }
                data["security_issues"].append(current_issue)

            bandit_severity_pattern = SAFE_PATTERNS[self.patterns["bandit_severity"]]
            severity_match = bandit_severity_pattern.search(line)
            if severity_match and current_issue:
                severity, confidence = severity_match.groups()
                current_issue["severity"] = severity
                current_issue["confidence"] = confidence

        data["security_summary"] = {"total_issues": len(data["security_issues"])}
        return data

    def _parse_coverage_output(self, output: str) -> dict[str, Any]:
        """Parse coverage report output."""
        data: dict[str, Any] = {"coverage_data": {}, "coverage_summary": {}}

        lines = output.split("\n")

        for line in lines:
            # Individual file coverage
            coverage_line_pattern = SAFE_PATTERNS[self.patterns["coverage_line"]]
            coverage_match = coverage_line_pattern.search(line)
            if coverage_match:
                groups = coverage_match.groups()
                if len(groups) == 4:
                    file_path, statements, missing, coverage = groups
                    data["coverage_data"][file_path] = {
                        "statements": int(statements),
                        "missing": int(missing),
                        "coverage": float(coverage.rstrip("%")),
                    }
                elif len(groups) == 1:
                    # TOTAL-row variant — capture only the percent
                    data["coverage_summary"]["total_coverage"] = float(
                        groups[0].rstrip("%"),
                    )

            # Total coverage
            pytest_coverage_pattern = SAFE_PATTERNS[self.patterns["pytest_coverage"]]
            total_match = pytest_coverage_pattern.search(line)
            if total_match:
                total_coverage = float(total_match.group(1))
                data["coverage_summary"]["total_coverage"] = total_coverage

        return data

    def _parse_complexity_output(self, output: str) -> dict[str, Any]:
        """Parse complexity analysis output."""
        data: dict[str, Any] = {"complexity_data": {}, "complexity_summary": {}}

        lines = output.split("\n")
        total_files = 0
        high_complexity = 0

        for line in lines:
            complexity_pattern = SAFE_PATTERNS[self.patterns["complexity_score"]]
            complexity_match = complexity_pattern.search(line)
            if complexity_match:
                file_path, lines_count, complexity_score = complexity_match.groups()
                complexity_val = float(complexity_score)
                data["complexity_data"][file_path] = {
                    "lines": int(lines_count),
                    "complexity": complexity_val,
                }
                total_files += 1
                if complexity_val > 10:  # Configurable threshold
                    high_complexity += 1

        data["complexity_summary"] = {
            "total_files": total_files,
            "high_complexity_files": high_complexity,
        }
        return data

    def _parse_progress_output(self, output: str) -> dict[str, Any]:
        """Parse progress indicators from output."""
        data: dict[str, Any] = {"progress_info": {}}
        lines = output.split("\n")

        progress_state = self._initialize_progress_state()

        for line in lines:
            self._process_progress_line(line, data, progress_state)

        self._finalize_progress_data(data, progress_state)
        return data

    def _initialize_progress_state(self) -> dict[str, Any]:
        """Initialize progress parsing state."""
        return {
            "completed_tasks": [],
            "failed_tasks": [],
            "current_percentage": 0.0,
        }

    def _process_progress_line(
        self,
        line: str,
        data: dict[str, Any],
        progress_state: dict[str, Any],
    ) -> None:
        """Process a single line for progress indicators."""
        self._extract_current_task(line, data)
        self._extract_percentage(line, progress_state)
        self._extract_completed_tasks(line, progress_state)
        self._extract_failed_tasks(line, progress_state)

    def _extract_current_task(self, line: str, data: dict[str, Any]) -> None:
        """Extract current task from line."""
        progress_pattern = SAFE_PATTERNS[self.patterns["progress_indicator"]]
        progress_match = progress_pattern.search(line)
        if progress_match:
            data["progress_info"]["current_task"] = progress_match.group(1)

    def _extract_percentage(self, line: str, progress_state: dict[str, Any]) -> None:
        """Extract percentage completion from line."""
        percentage_pattern = SAFE_PATTERNS[self.patterns["percentage"]]
        percentage_match = percentage_pattern.search(line)
        if percentage_match:
            progress_state["current_percentage"] = float(percentage_match.group(1))

    def _extract_completed_tasks(
        self,
        line: str,
        progress_state: dict[str, Any],
    ) -> None:
        """Extract completed tasks from line."""
        completion_pattern = SAFE_PATTERNS[self.patterns["task_completion"]]
        completion_match = completion_pattern.search(line)
        if completion_match:
            task = self._get_task_from_match(completion_match)
            if task:
                progress_state["completed_tasks"].append(task.strip())

    def _extract_failed_tasks(self, line: str, progress_state: dict[str, Any]) -> None:
        """Extract failed tasks from line."""
        failure_pattern = SAFE_PATTERNS[self.patterns["task_failure"]]
        failure_match = failure_pattern.search(line)
        if failure_match:
            task = self._get_task_from_match(failure_match)
            if task:
                progress_state["failed_tasks"].append(task.strip())

    def _get_task_from_match(self, match: Any) -> str | None:
        """Extract task name from pattern match groups."""
        return match.group(1) or match.group(2) or match.group(3)  # type: ignore[no-any-return]

    def _finalize_progress_data(
        self,
        data: dict[str, Any],
        progress_state: dict[str, Any],
    ) -> None:
        """Update final progress data with collected state."""
        data["progress_info"].update(
            {
                "percentage": progress_state["current_percentage"],
                "completed_tasks": progress_state["completed_tasks"],
                "failed_tasks": progress_state["failed_tasks"],
            },
        )

    def _extract_test_insights(self, parsed_data: dict[str, Any]) -> list[str]:
        """Extract memory insights from test results."""
        insights = []
        test_results = parsed_data.get("test_results", [])

        if test_results:
            passed = sum(1 for t in test_results if t["status"] == "passed")
            failed = sum(1 for t in test_results if t["status"] == "failed")
            total = len(test_results)

            if total > 0:
                pass_rate = (passed / total) * 100
                insights.append(
                    f"Test suite: {passed}/{total} tests passed ({pass_rate:.1f}% pass rate)",
                )

                if failed > 0:
                    failed_files = {
                        t["file"] for t in test_results if t["status"] == "failed"
                    }
                    insights.append(
                        f"Test failures found in {len(failed_files)} files: {', '.join(failed_files)}",
                    )

                if pass_rate == 100:
                    insights.append("All tests passing - code quality is stable")
                elif pass_rate < 80:
                    insights.append(
                        "Test pass rate below 80% - investigate failing tests",
                    )

        return insights

    def _extract_lint_insights(self, parsed_data: dict[str, Any]) -> list[str]:
        """Extract memory insights from lint results."""
        insights = []
        lint_issues = parsed_data.get("lint_issues", [])

        if lint_issues:
            total_issues = len(lint_issues)
            by_type: dict[str, int] = {}
            by_file: dict[str, int] = {}

            for issue in lint_issues:
                issue_type = issue.get("type", "unknown")
                file_path = issue.get("file", "unknown")

                by_type[issue_type] = by_type.get(issue_type, 0) + 1
                by_file[file_path] = by_file.get(file_path, 0) + 1

            insights.append(f"Code quality: {total_issues} lint issues found")

            # Top issue types
            top_types = sorted(
                by_type.items(), key=operator.itemgetter(1), reverse=True
            )[:3]
            if top_types:
                type_summary = ", ".join(f"{t}: {c}" for t, c in top_types)
                insights.append(f"Most common issues: {type_summary}")

            # Files needing attention
            top_files = sorted(
                by_file.items(), key=operator.itemgetter(1), reverse=True
            )[:3]
            if top_files and top_files[0][1] > 5:
                insights.append(
                    f"Files needing attention: {top_files[0][0]} ({top_files[0][1]} issues)",
                )
        else:
            insights.append("Code quality: No lint issues found - code is clean")

        return insights

    def _extract_security_insights(self, parsed_data: dict[str, Any]) -> list[str]:
        """Extract memory insights from security scan."""
        insights = []
        security_issues = parsed_data.get("security_issues", [])

        if security_issues:
            total_issues = len(security_issues)
            high_severity = sum(
                1 for i in security_issues if i.get("severity") == "HIGH"
            )

            insights.append(
                f"Security scan: {total_issues} potential security issues found",
            )

            if high_severity > 0:
                insights.append(
                    f"⚠️ {high_severity} high-severity security issues require immediate attention",
                )
            else:
                insights.append("No high-severity security issues detected")
        else:
            insights.append(
                "Security scan: No security issues detected - code appears secure",
            )

        return insights

    def _extract_coverage_insights(self, parsed_data: dict[str, Any]) -> list[str]:
        """Extract memory insights from coverage data."""
        insights = []
        coverage_summary = parsed_data.get("coverage_summary", {})

        if "total_coverage" in coverage_summary:
            coverage = coverage_summary["total_coverage"]
            insights.append(f"Test coverage: {coverage}% of code is covered by tests")

            if coverage >= 90:
                insights.append("Excellent test coverage - code is well tested")
            elif coverage >= 80:
                insights.append("Good test coverage - consider adding more tests")
            elif coverage >= 60:
                insights.append(
                    "Moderate test coverage - significant testing gaps exist",
                )
            else:
                insights.append(
                    "Low test coverage - critical testing gaps need attention",
                )

        return insights

    def _extract_complexity_insights(self, parsed_data: dict[str, Any]) -> list[str]:
        """Extract memory insights from complexity analysis."""
        insights = []
        complexity_summary = parsed_data.get("complexity_summary", {})

        if complexity_summary:
            total_files = complexity_summary.get("total_files", 0)
            high_complexity = complexity_summary.get("high_complexity_files", 0)

            if total_files > 0:
                complexity_rate = (high_complexity / total_files) * 100
                insights.append(
                    f"Code complexity: {high_complexity}/{total_files} files have high complexity ({complexity_rate:.1f}%)",
                )

                if complexity_rate == 0:
                    insights.append("Code complexity is well managed")
                elif complexity_rate > 20:
                    insights.append(
                        "Consider refactoring high-complexity files for maintainability",
                    )

        return insights

    def _extract_progress_insights(self, parsed_data: dict[str, Any]) -> list[str]:
        """Extract memory insights from progress information."""
        insights = []
        progress_info = parsed_data.get("progress_info", {})

        completed_tasks = progress_info.get("completed_tasks", [])
        failed_tasks = progress_info.get("failed_tasks", [])
        percentage = progress_info.get("percentage", 0)

        if completed_tasks:
            insights.append(f"Progress: Completed {len(completed_tasks)} tasks")

        if failed_tasks:
            insights.append(
                f"⚠️ {len(failed_tasks)} tasks failed: {', '.join(failed_tasks[:3])}",
            )

        if percentage > 0:
            insights.append(f"Overall progress: {percentage}% complete")

        return insights
