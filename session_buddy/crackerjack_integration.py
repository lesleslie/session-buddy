"""Crackerjack Integration module for progress tracking and test monitoring.

This module provides deep integration with Crackerjack for:
- Progress tracking output parsing for memory enrichment
- Test result monitoring for context enhancement
- Command execution with result capture
- Quality metrics integration
"""

import asyncio
import json
import logging
import operator
import sqlite3
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from session_buddy.utils.crackerjack import (
    CrackerjackOutputParser,
)

logger = logging.getLogger(__name__)


class CrackerjackCommand(Enum):
    """Supported Crackerjack commands."""

    # Core quality commands
    ANALYZE = "analyze"  # Comprehensive analysis command
    CHECK = "check"
    TEST = "test"
    LINT = "lint"
    FORMAT = "format"
    TYPECHECK = "typecheck"  # Type checking support

    # Security and complexity
    SECURITY = "security"
    COMPLEXITY = "complexity"
    COVERAGE = "coverage"

    # Build and maintenance
    BUILD = "build"
    CLEAN = "clean"

    # Documentation
    DOCS = "docs"

    # Release management
    RELEASE = "release"  # Release command support


class TestStatus(Enum):
    """Test execution status."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    XFAIL = "xfail"
    XPASS = "xpass"


class QualityMetric(Enum):
    """Quality metrics tracked."""

    CODE_COVERAGE = "coverage"
    COMPLEXITY = "complexity"
    LINT_SCORE = "lint_score"
    SECURITY_SCORE = "security_score"
    TEST_PASS_RATE = "test_pass_rate"  # nosec B105
    BUILD_STATUS = "build_status"


@dataclass
class CrackerjackResult:
    """Result of Crackerjack command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    timestamp: datetime
    working_directory: str
    parsed_data: dict[str, Any] | None
    quality_metrics: dict[str, float]
    test_results: list[dict[str, Any]]
    memory_insights: list[str]


@dataclass
class TestResult:
    """Individual test result information."""

    test_id: str
    test_name: str
    status: TestStatus
    duration: float
    file_path: str
    line_number: int | None
    error_message: str | None
    traceback: str | None
    tags: list[str]
    coverage_data: dict[str, Any] | None


@dataclass
class ProgressSnapshot:
    """Progress tracking snapshot."""

    timestamp: datetime
    project_path: str
    command: str
    stage: str
    progress_percentage: float
    current_task: str
    completed_tasks: list[str]
    failed_tasks: list[str]
    quality_metrics: dict[str, float]
    estimated_completion: datetime | None
    memory_context: list[str]


# PatternMappingsBuilder and CrackerjackOutputParser classes have been extracted
# to session_buddy.utils.crackerjack module for better modularity and reusability.


class CrackerjackIntegration:
    """Main integration class for Crackerjack command execution and monitoring."""

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize Crackerjack integration."""
        self.db_path = db_path or str(
            Path.home() / ".claude" / "data" / "crackerjack_integration.db",
        )
        self.parser = CrackerjackOutputParser()
        self._lock = threading.Lock()
        try:
            self._init_database()
        except Exception:
            # Fall back to a temp-writable path if the default is not writable
            tmp_db = (
                Path(tempfile.gettempdir())
                / "session-mgmt-mcp"
                / "data"
                / "crackerjack_integration.db"
            )
            tmp_db.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(tmp_db)
            self._init_database()

    def execute_command(
        self,
        cmd: list[str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute command synchronously (for CommandRunner protocol compatibility).

        This is a synchronous wrapper around execute_crackerjack_command for
        compatibility with crackerjack's CommandRunner protocol.
        """
        import os
        import subprocess  # nosec B404

        try:
            env = kwargs.get("env", os.environ.copy())

            # Execute the command directly using subprocess
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout", 300),
                cwd=kwargs.get("cwd", "."),
                env=env,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k not in {"timeout", "cwd", "env"}
                },
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired as e:
            return {
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": e.stderr.decode() if e.stderr else "Command timed out",
                "returncode": -1,
                "success": False,
            }
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "returncode": -2, "success": False}

    def _init_database(self) -> None:
        """Initialize SQLite database for Crackerjack integration."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crackerjack_results (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    exit_code INTEGER,
                    stdout TEXT,
                    stderr TEXT,
                    execution_time REAL,
                    timestamp TIMESTAMP,
                    working_directory TEXT,
                    parsed_data TEXT,  -- JSON
                    quality_metrics TEXT,  -- JSON
                    memory_insights TEXT  -- JSON array
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration REAL,
                    file_path TEXT,
                    line_number INTEGER,
                    error_message TEXT,
                    timestamp TIMESTAMP,
                    FOREIGN KEY (result_id) REFERENCES crackerjack_results(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS progress_snapshots (
                    id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    command TEXT NOT NULL,
                    stage TEXT,
                    progress_percentage REAL,
                    current_task TEXT,
                    completed_tasks TEXT,  -- JSON array
                    failed_tasks TEXT,     -- JSON array
                    quality_metrics TEXT,  -- JSON
                    timestamp TIMESTAMP,
                    memory_context TEXT    -- JSON array
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_metrics_history (
                    id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    timestamp TIMESTAMP,
                    result_id TEXT,
                    FOREIGN KEY (result_id) REFERENCES crackerjack_results(id)
                )
            """)

            # Create indices
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_timestamp ON crackerjack_results(timestamp)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_command ON crackerjack_results(command)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_progress_project ON progress_snapshots(project_path)",
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_type ON quality_metrics_history(metric_type)",
            )

    def _build_command_flags(self, command: str, ai_agent_mode: bool) -> list[str]:
        """Build appropriate command flags for the given command.

        Crackerjack CLI structure (v0.47+):
        - Uses 'run' subcommand followed by flags
        - Example: python -m crackerjack run --fast --quick
        - Example: python -m crackerjack run --comp --run-tests
        - Example: python -m crackerjack run --all patch (release workflow)

        IMPORTANT: --all requires an argument (patch|minor|major|auto|interactive)
        For general quality checks, use 'run' with no flags or --fast/--comp
        """
        command_mappings = {
            # Fast hooks only (formatters and basic checks)
            "lint": ["run", "--fast"],
            "format": ["run", "--fast"],
            # Comprehensive hooks (type checking, security, complexity)
            "check": ["run", "--comp"],
            "typecheck": ["run", "--comp"],
            "security": ["run", "--comp"],  # Security is part of comprehensive hooks
            "complexity": [
                "run",
                "--comp",
            ],  # Complexity is part of comprehensive hooks
            "analyze": ["run", "--comp"],  # Comprehensive analysis
            # Test execution
            "test": ["run", "--run-tests"],
            # Build and maintenance (default run with no special flags)
            "build": ["run"],
            "clean": ["run"],  # Clean happens automatically in current version
            # All quality checks (use default run, NOT --all which is for release)
            "all": ["run"],  # Just run with no special flags
            "run": ["run"],
            # Standalone commands (no 'run' prefix)
            "run-tests": ["run-tests"],
        }

        flags = command_mappings.get(command.lower(), ["run"])
        if ai_agent_mode:
            flags.append("--ai-fix")
        return flags

    async def _execute_process(
        self,
        full_command: list[str],
        working_directory: str,
        timeout: int,
    ) -> tuple[int, str, str, float]:
        """Execute the subprocess and return exit code, stdout, stderr, and execution time."""
        import os

        start_time = time.time()

        env = os.environ.copy()

        process = await asyncio.create_subprocess_exec(
            *full_command,
            cwd=working_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        exit_code = process.returncode or 0
        execution_time = time.time() - start_time
        stdout_text = stdout.decode("utf-8", errors="ignore")
        stderr_text = stderr.decode("utf-8", errors="ignore")

        return exit_code, stdout_text, stderr_text, execution_time

    def _create_error_result(
        self,
        command: str,
        exit_code: int,
        stderr: str,
        execution_time: float,
        working_directory: str,
        memory_insight: str,
    ) -> CrackerjackResult:
        """Create a standardized error result."""
        return CrackerjackResult(
            command=command,
            exit_code=exit_code,
            stdout="",
            stderr=stderr,
            execution_time=execution_time,
            timestamp=datetime.now(),
            working_directory=working_directory,
            parsed_data={},
            quality_metrics={},
            test_results=[],
            memory_insights=[memory_insight],
        )

    async def execute_crackerjack_command(
        self,
        command: str,
        args: list[str] | None = None,
        working_directory: str = ".",
        timeout: int = 300,
        ai_agent_mode: bool = False,
    ) -> CrackerjackResult:
        """Execute Crackerjack command and capture results."""
        args = args or []
        command_flags = self._build_command_flags(command, ai_agent_mode)
        quick_commands = {"lint", "check", "test", "format", "typecheck"}
        if command.lower() in quick_commands and "--quick" not in args:
            if "--ai-fix" in command_flags:
                command_flags.insert(command_flags.index("--ai-fix"), "--quick")
            else:
                command_flags.append("--quick")
        full_command = ["python", "-m", "crackerjack", *command_flags, *args]

        start_time = time.time()
        result_id = f"cj_{int(start_time * 1000)}"

        try:
            (
                exit_code,
                stdout_text,
                stderr_text,
                execution_time,
            ) = await self._execute_process(full_command, working_directory, timeout)

            parsed_data, memory_insights = self.parser.parse_output(
                command,
                stdout_text,
                stderr_text,
            )
            quality_metrics = self._calculate_quality_metrics(
                parsed_data,
                exit_code,
                stderr_text,
            )

            result = CrackerjackResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                execution_time=execution_time,
                timestamp=datetime.now(),
                working_directory=working_directory,
                parsed_data=parsed_data,
                quality_metrics=quality_metrics,
                test_results=parsed_data.get("test_results", []),
                memory_insights=memory_insights,
            )

            await self._store_result(result_id, result)
            await self._store_progress_snapshot(result_id, result, working_directory)
            return result

        except TimeoutError:
            execution_time = time.time() - start_time
            error_result = self._create_error_result(
                command,
                -1,
                f"Command timed out after {timeout} seconds",
                execution_time,
                working_directory,
                f"Command '{command}' timed out - consider optimizing or increasing timeout",
            )
            await self._store_result(result_id, error_result)
            return error_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_result = self._create_error_result(
                command,
                -2,
                f"Execution error: {e!s}",
                execution_time,
                working_directory,
                f"Command '{command}' failed with error: {e!s}",
            )
            await self._store_result(result_id, error_result)
            return error_result

    async def get_recent_results(
        self,
        hours: int = 24,
        command: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent Crackerjack execution results."""
        since = datetime.now() - timedelta(hours=hours)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where_conditions = ["timestamp >= ?"]
            params = [since.isoformat()]

            if command:
                where_conditions.append("command = ?")
                params.append(command)

            # Build SQL safely - all user input is parameterized via params list
            query = (
                "SELECT * FROM crackerjack_results WHERE "
                + " AND ".join(where_conditions)
                + " ORDER BY timestamp DESC"
            )

            cursor = conn.execute(query, params)
            results = []

            for row in cursor.fetchall():
                result = dict(row)
                result["parsed_data"] = json.loads(result["parsed_data"] or "{}")
                result["quality_metrics"] = json.loads(
                    result["quality_metrics"] or "{}",
                )
                result["memory_insights"] = json.loads(
                    result["memory_insights"] or "[]",
                )
                results.append(result)

            return results

    async def get_quality_metrics_history(
        self,
        project_path: str,
        metric_type: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get quality metrics history for trend analysis."""
        since = datetime.now() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where_conditions = ["project_path = ?", "timestamp >= ?"]
            params = [project_path, since.isoformat()]

            if metric_type:
                where_conditions.append("metric_type = ?")
                params.append(metric_type)

            # Build SQL safely - all user input is parameterized via params list
            query = (
                "SELECT * FROM quality_metrics_history WHERE "
                + " AND ".join(where_conditions)
                + " ORDER BY timestamp DESC"
            )

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    async def get_test_failure_patterns(self, days: int = 7) -> dict[str, Any]:
        """Analyze test failure patterns for insights."""
        since = datetime.now() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Get failed tests
            failed_tests = conn.execute(
                """
                SELECT test_name, file_path, error_message, COUNT(*) as failure_count
                FROM test_results
                WHERE status = 'failed' AND timestamp >= ?
                GROUP BY test_name, file_path, error_message
                ORDER BY failure_count DESC
            """,
                (since.isoformat(),),
            ).fetchall()

            # Get flaky tests (alternating pass/fail)
            flaky_tests = conn.execute(
                """
                SELECT test_name, file_path,
                       COUNT(DISTINCT status) as status_count,
                       COUNT(*) as total_runs
                FROM test_results
                WHERE timestamp >= ?
                GROUP BY test_name, file_path
                HAVING status_count > 1 AND total_runs >= 3
                ORDER BY status_count DESC, total_runs DESC
            """,
                (since.isoformat(),),
            ).fetchall()

            # Get most failing files
            failing_files = conn.execute(
                """
                SELECT file_path, COUNT(*) as failure_count
                FROM test_results
                WHERE status = 'failed' AND timestamp >= ?
                GROUP BY file_path
                ORDER BY failure_count DESC
                LIMIT 10
            """,
                (since.isoformat(),),
            ).fetchall()

            return {
                "failed_tests": [dict(row) for row in failed_tests],
                "flaky_tests": [dict(row) for row in flaky_tests],
                "failing_files": [dict(row) for row in failing_files],
                "analysis_period_days": days,
            }

    def _filter_metrics_by_type(
        self,
        metrics_history: list[dict[str, Any]],
        metric_type: str,
    ) -> list[dict[str, Any]]:
        """Filter metrics history by type and sort by timestamp."""
        metric_values = [m for m in metrics_history if m["metric_type"] == metric_type]
        metric_values.sort(key=operator.itemgetter("timestamp"), reverse=True)
        return metric_values

    def _calculate_trend_direction(self, change: float) -> str:
        """Determine trend direction from change value."""
        if change > 0:
            return "improving"
        if change < 0:
            return "declining"
        return "stable"

    def _calculate_trend_strength(self, change: float) -> str:
        """Determine trend strength from absolute change value."""
        abs_change = abs(change)
        if abs_change > 5:
            return "strong"
        if abs_change > 1:
            return "moderate"
        return "weak"

    def _create_trend_data(self, metric_values: list[dict[str, Any]]) -> dict[str, Any]:
        """Create trend data from metric values with sufficient data."""
        mid_point = len(metric_values) // 2
        recent = metric_values[:mid_point] if mid_point > 0 else metric_values
        older = metric_values[mid_point:] if mid_point > 0 else []

        if not (recent and older):
            current_avg = sum(m["metric_value"] for m in metric_values) / len(
                metric_values,
            )
            return {
                "direction": "insufficient_data",
                "change": 0,
                "change_percentage": 0,
                "recent_average": current_avg,
                "previous_average": current_avg,
                "data_points": len(metric_values),
                "trend_strength": "unknown",
            }

        recent_avg = sum(m["metric_value"] for m in recent) / len(recent)
        older_avg = sum(m["metric_value"] for m in older) / len(older)
        change = recent_avg - older_avg

        return {
            "direction": self._calculate_trend_direction(change),
            "change": abs(change),
            "change_percentage": (abs(change) / older_avg * 100)
            if older_avg > 0
            else 0,
            "recent_average": recent_avg,
            "previous_average": older_avg,
            "data_points": len(metric_values),
            "trend_strength": self._calculate_trend_strength(change),
        }

    def _calculate_overall_assessment(
        self,
        trends: dict[str, Any],
        days: int,
    ) -> dict[str, Any]:
        """Calculate overall trend assessment from individual trend data."""
        improving_metrics = sum(
            1 for t in trends.values() if t["direction"] == "improving"
        )
        declining_metrics = sum(
            1 for t in trends.values() if t["direction"] == "declining"
        )

        if improving_metrics > declining_metrics:
            overall_direction = "improving"
        elif declining_metrics > improving_metrics:
            overall_direction = "declining"
        else:
            overall_direction = "stable"

        return {
            "overall_direction": overall_direction,
            "improving_count": improving_metrics,
            "declining_count": declining_metrics,
            "stable_count": len(trends) - improving_metrics - declining_metrics,
            "analysis_period_days": days,
        }

    async def get_quality_trends(
        self,
        project_path: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Analyze quality trends over time."""
        metrics_history = await self.get_quality_metrics_history(
            project_path,
            None,
            days,
        )

        metric_types = (
            "test_pass_rate",
            "code_coverage",
            "lint_score",
            "security_score",
            "complexity_score",
        )
        trends = {}

        for metric_type in metric_types:
            metric_values = self._filter_metrics_by_type(metrics_history, metric_type)
            if len(metric_values) >= 2:
                trends[metric_type] = self._create_trend_data(metric_values)

        overall_assessment = self._calculate_overall_assessment(trends, days)

        return {
            "trends": trends,
            "overall": overall_assessment,
            "recommendations": self._generate_trend_recommendations(trends),
        }

    def _get_declining_recommendation(
        self,
        metric_type: str,
        change: float,
    ) -> str | None:
        """Get recommendation for declining metrics."""
        recommendations_map = {
            "test_pass_rate": f"⚠️ Test pass rate declining by {change:.1f}% - investigate failing tests",
            "code_coverage": f"⚠️ Code coverage declining by {change:.1f}% - add more tests",
            "lint_score": "⚠️ Code quality declining - address lint issues",
            "security_score": "🔒 Security score declining - review security findings",
            "complexity_score": "🔧 Code complexity increasing - consider refactoring",
        }
        return recommendations_map.get(metric_type)

    def _get_improving_recommendation(
        self,
        metric_type: str,
        recent_avg: float,
    ) -> str | None:
        """Get recommendation for improving metrics with high averages."""
        if metric_type == "test_pass_rate" and recent_avg > 95:
            return "✅ Excellent test pass rate trend - maintain current practices"
        if metric_type == "code_coverage" and recent_avg > 85:
            return "✅ Great coverage improvement - continue testing efforts"
        return None

    def _generate_trend_recommendations(self, trends: dict[str, Any]) -> list[str]:
        """Generate recommendations based on quality trends."""
        recommendations = []

        for metric_type, trend_data in trends.items():
            direction = trend_data["direction"]
            strength = trend_data["trend_strength"]
            change = trend_data["change"]
            recent_avg = trend_data["recent_average"]

            if direction == "declining" and strength in {"strong", "moderate"}:
                recommendation = self._get_declining_recommendation(metric_type, change)
                if recommendation:
                    recommendations.append(recommendation)
            elif direction == "improving" and strength == "strong":
                recommendation = self._get_improving_recommendation(
                    metric_type,
                    recent_avg,
                )
                if recommendation:
                    recommendations.append(recommendation)

        if not recommendations:
            recommendations.append(
                "📈 Quality metrics are stable - continue current practices",
            )

        return recommendations

    async def health_check(self) -> dict[str, Any]:
        """Check integration health and dependencies."""
        health: dict[str, Any] = {
            "crackerjack_available": False,
            "database_accessible": False,
            "version_compatible": False,
            "recommendations": [],
            "status": "unhealthy",
        }

        try:
            await self._check_crackerjack_availability(health)
            await self._check_database_health(health)
            health["status"] = self._determine_health_status(health)

        except sqlite3.Error as e:
            health["database_accessible"] = False
            health["recommendations"].append(f"❌ Database error: {e}")
        except Exception as e:
            health["error"] = str(e)
            health["recommendations"].append(f"❌ Health check error: {e}")

        return health

    async def _check_crackerjack_availability(self, health: dict[str, Any]) -> None:
        """Check if crackerjack command is available."""
        process = await asyncio.create_subprocess_exec(
            "crackerjack",
            "--help",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        health["crackerjack_available"] = process.returncode == 0

        if health["crackerjack_available"]:
            health["recommendations"].append(
                "✅ Crackerjack is available and responding",
            )
        else:
            health["recommendations"].append(
                "❌ Crackerjack not available - install with 'uv add crackerjack'",
            )

    async def _check_database_health(self, health: dict[str, Any]) -> None:
        """Check database accessibility and data availability."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("SELECT 1").fetchone()
            health["database_accessible"] = True
            health["recommendations"].append("✅ Database connection successful")

            cursor = conn.execute("SELECT COUNT(*) FROM crackerjack_results")
            result_count = cursor.fetchone()[0]

            if result_count > 0:
                health["recommendations"].append(
                    f"📊 {result_count} execution records available",
                )
            else:
                health["recommendations"].append(
                    "📝 No execution history - run some crackerjack commands",
                )

    def _determine_health_status(self, health: dict[str, Any]) -> str:
        """Determine overall health status from component health."""
        if health["crackerjack_available"] and health["database_accessible"]:
            return "healthy"
        if health["database_accessible"]:
            return "partial"
        return "unhealthy"

    def _calculate_quality_metrics(
        self,
        parsed_data: dict[str, Any],
        exit_code: int,
        stderr_content: str = "",
    ) -> dict[str, float]:
        """Calculate quality metrics from parsed data."""
        metrics = {}

        metrics.update(self._calculate_test_metrics(parsed_data))
        metrics.update(self._calculate_coverage_metrics(parsed_data))
        metrics.update(self._calculate_lint_metrics(parsed_data))
        metrics.update(self._calculate_security_metrics(parsed_data))
        metrics.update(self._calculate_complexity_metrics(parsed_data))

        if stderr_content:
            metrics.update(self._parse_stderr_metrics(stderr_content))

        metrics["build_status"] = float(100 if exit_code == 0 else 0)

        return metrics

    def _calculate_test_metrics(self, parsed_data: dict[str, Any]) -> dict[str, float]:
        """Calculate test pass rate metrics."""
        metrics = {}
        test_results = parsed_data.get("test_results", [])
        if test_results:
            passed = sum(1 for t in test_results if t["status"] == "passed")
            total = len(test_results)
            metrics["test_pass_rate"] = float(
                (passed / total) * 100 if total > 0 else 0,
            )
        return metrics

    def _calculate_coverage_metrics(
        self, parsed_data: dict[str, Any]
    ) -> dict[str, float]:
        """Calculate code coverage metrics."""
        metrics = {}
        coverage_summary = parsed_data.get("coverage_summary", {})
        if "total_coverage" in coverage_summary:
            metrics["code_coverage"] = float(coverage_summary["total_coverage"])
        return metrics

    def _calculate_lint_metrics(self, parsed_data: dict[str, Any]) -> dict[str, float]:
        """Calculate lint score metrics (inverted so higher is better)."""
        metrics = {}
        lint_summary = parsed_data.get("lint_summary", {})
        if "total_issues" in lint_summary:
            total_issues = lint_summary["total_issues"]
            metrics["lint_score"] = float(
                max(0, 100 - total_issues) if total_issues < 100 else 0,
            )
        return metrics

    def _calculate_security_metrics(
        self, parsed_data: dict[str, Any]
    ) -> dict[str, float]:
        """Calculate security score metrics (inverted so higher is better)."""
        metrics = {}
        security_summary = parsed_data.get("security_summary", {})
        if "total_issues" in security_summary:
            total_issues = security_summary["total_issues"]
            metrics["security_score"] = float(
                max(0, 100 - (total_issues * 10)) if total_issues < 10 else 0,
            )
        return metrics

    def _calculate_complexity_metrics(
        self, parsed_data: dict[str, Any]
    ) -> dict[str, float]:
        """Calculate complexity score metrics (inverted so higher is better)."""
        metrics = {}
        complexity_summary = parsed_data.get("complexity_summary", {})
        if complexity_summary:
            total_files = complexity_summary.get("total_files", 0)
            high_complexity = complexity_summary.get("high_complexity_files", 0)
            if total_files > 0:
                complexity_rate = (high_complexity / total_files) * 100
                metrics["complexity_score"] = float(max(0, 100 - complexity_rate))
        return metrics

    def _parse_stderr_metrics(self, stderr_content: str) -> dict[str, float]:
        """Parse quality metrics from structured logging in stderr."""
        metrics = {}

        # Look for common structured logging patterns in stderr
        lines = stderr_content.split("\n")

        for line in lines:
            # Parse structured log entries that might contain quality metrics
            if '"quality"' in line or '"metric"' in line or '"score"' in line:
                # This is a simplified approach - would in practice need to
                # handle the actual structured format
                import re

                # Look for patterns like: "quality": value or "metric": value
                quality_pattern = r'"quality"\s*:\s*(\d+\.?\d*)'
                metric_pattern = r'"metric"\s*:\s*(\d+\.?\d*)'
                score_pattern = r'"score"\s*:\s*(\d+\.?\d*)'

                quality_match = re.search(quality_pattern, line)
                if quality_match:
                    metrics["parsed_quality"] = float(quality_match.group(1))

                metric_match = re.search(metric_pattern, line)
                if metric_match:
                    metrics["parsed_metric"] = float(metric_match.group(1))

                score_match = re.search(score_pattern, line)
                if score_match:
                    metrics["parsed_score"] = float(score_match.group(1))

        return metrics

    async def _store_result(self, result_id: str, result: CrackerjackResult) -> None:
        """Store Crackerjack result in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO crackerjack_results
                    (id, command, exit_code, stdout, stderr, execution_time, timestamp,
                     working_directory, parsed_data, quality_metrics, memory_insights)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        result_id,
                        result.command,
                        result.exit_code,
                        result.stdout,
                        result.stderr,
                        result.execution_time,
                        result.timestamp.isoformat(),
                        result.working_directory,
                        json.dumps(result.parsed_data),
                        json.dumps(result.quality_metrics),
                        json.dumps(result.memory_insights),
                    ),
                )

                # Store individual test results
                for test_result in result.test_results:
                    test_id = (
                        f"test_{result_id}_{hash(test_result.get('test', 'unknown'))}"
                    )
                    conn.execute(
                        """
                        INSERT INTO test_results
                        (id, result_id, test_name, status, duration, file_path, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            test_id,
                            result_id,
                            test_result.get("test", ""),
                            test_result.get("status", ""),
                            test_result.get("duration", 0),
                            test_result.get("file", ""),
                            result.timestamp,
                        ),
                    )

                # Store quality metrics
                for metric_name, metric_value in result.quality_metrics.items():
                    metric_id = f"metric_{result_id}_{metric_name}"
                    conn.execute(
                        """
                        INSERT INTO quality_metrics_history
                        (id, project_path, metric_type, metric_value, timestamp, result_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            metric_id,
                            result.working_directory,
                            metric_name,
                            metric_value,
                            result.timestamp.isoformat(),
                            result_id,
                        ),
                    )
        except Exception:
            # In sandboxed/readonly environments, skip persistence
            return

    async def _store_progress_snapshot(
        self,
        result_id: str,
        result: CrackerjackResult,
        project_path: str,
    ) -> None:
        """Store progress snapshot from result."""
        progress_info: dict[str, Any] = (
            result.parsed_data.get("progress_info", {}) if result.parsed_data else {}
        )

        if progress_info:
            snapshot_id = f"progress_{result_id}"
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO progress_snapshots
                        (id, project_path, command, stage, progress_percentage, current_task,
                         completed_tasks, failed_tasks, quality_metrics, timestamp, memory_context)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            snapshot_id,
                            project_path,
                            result.command,
                            progress_info.get("stage", ""),
                            progress_info.get("percentage", 0),
                            progress_info.get("current_task", ""),
                            json.dumps(progress_info.get("completed_tasks", [])),
                            json.dumps(progress_info.get("failed_tasks", [])),
                            json.dumps(result.quality_metrics),
                            result.timestamp.isoformat(),
                            json.dumps(result.memory_insights),
                        ),
                    )
            except Exception:
                # In sandboxed/readonly environments, skip persistence
                return


# Global integration instance
_crackerjack_integration = None


def get_crackerjack_integration() -> CrackerjackIntegration:
    """Get global Crackerjack integration instance."""
    global _crackerjack_integration
    if _crackerjack_integration is None:
        _crackerjack_integration = CrackerjackIntegration()
    return _crackerjack_integration


# Public API functions for MCP tools
async def execute_crackerjack_command(
    command: str,
    args: list[str] | None = None,
    working_directory: str = ".",
    timeout: int = 300,
    ai_agent_mode: bool = False,
) -> dict[str, Any]:
    """Execute Crackerjack command and return structured results."""
    integration = get_crackerjack_integration()
    result = await integration.execute_crackerjack_command(
        command,
        args,
        working_directory,
        timeout,
        ai_agent_mode,
    )
    return asdict(result)


async def get_recent_crackerjack_results(
    hours: int = 24,
    command: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent Crackerjack execution results."""
    integration = get_crackerjack_integration()
    return await integration.get_recent_results(hours, command)


async def get_quality_metrics_history(
    project_path: str,
    metric_type: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Get quality metrics history for trend analysis."""
    integration = get_crackerjack_integration()
    return await integration.get_quality_metrics_history(
        project_path,
        metric_type,
        days,
    )


async def analyze_test_failure_patterns(days: int = 7) -> dict[str, Any]:
    """Analyze test failure patterns for insights."""
    integration = get_crackerjack_integration()
    return await integration.get_test_failure_patterns(days)


async def get_quality_trends(
    project_path: str,
    days: int = 30,
) -> dict[str, Any]:
    """Analyze quality trends over time."""
    integration = get_crackerjack_integration()
    return await integration.get_quality_trends(project_path, days)


async def crackerjack_health_check() -> dict[str, Any]:
    """Check Crackerjack integration health and dependencies."""
    integration = get_crackerjack_integration()
    return await integration.health_check()
