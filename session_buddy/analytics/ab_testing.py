"""A/B testing framework for skills experimentation.

This module provides a complete A/B testing infrastructure for comparing
different skill selection strategies and measuring their effectiveness.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from scipy import stats

if TYPE_CHECKING:
    pass


@dataclass
class ABTestConfig:
    """Configuration for an A/B test.

    Attributes:
        test_name: Unique identifier for the test
        description: Human-readable test description
        control_strategy: Baseline strategy name (e.g., "semantic_search")
        treatment_strategy: New strategy to test (e.g., "workflow_aware_search")
        start_date: Test start date (ISO format)
        end_date: Optional test end date (ISO format)
        min_sample_size: Minimum samples per group before analysis
        metrics: List of metrics to track (e.g., ["completion_rate", "user_satisfaction"])
        assignment_ratio: Ratio for control group (0.0 to 1.0, default 0.5)
        status: Test status ("running", "completed", "stopped")
    """

    test_name: str
    description: str
    control_strategy: str
    treatment_strategy: str
    start_date: str
    end_date: str | None = None
    min_sample_size: int = 100
    metrics: list[str] = field(default_factory=lambda: ["completion_rate"])
    assignment_ratio: float = 0.5
    status: Literal["running", "completed", "stopped"] = "running"


@dataclass
class TestOutcome:
    """Outcome of a single skill invocation in an A/B test.

    Attributes:
        skill_name: Name of skill that was invoked
        completed: Whether skill completed successfully
        duration_seconds: How long the skill took
        user_rating: Optional user feedback (1-5 scale)
    """

    skill_name: str
    completed: bool
    duration_seconds: float | None = None
    user_rating: float | None = None


@dataclass
class TestAnalysisResult:
    """Results of A/B test analysis.

    Attributes:
        control_metrics: Metrics for control group
        treatment_metrics: Metrics for treatment group
        statistical_significance: P-value from statistical test
        winner: Which group won ("control", "treatment", or "inconclusive")
        recommendation: Human-readable recommendation
    """

    control_metrics: dict[str, object]
    treatment_metrics: dict[str, object]
    statistical_significance: float
    winner: Literal["control", "treatment", "inconclusive"]
    recommendation: str


class ABTestFramework:
    """Framework for running and analyzing A/B tests on skill strategies.

    Enables comparison of different skill recommendation strategies through
    randomized controlled trials with proper statistical analysis.

    Example:
        >>> framework = ABTestFramework(Path("skills.db"))
        >>> config = ABTestConfig(
        ...     test_name="semantic_vs_workflow_aware",
        ...     description="Compare semantic search vs workflow-aware search",
        ...     control_strategy="semantic_search",
        ...     treatment_strategy="workflow_aware_search",
        ...     start_date="2025-02-10T00:00:00",
        ... )
        >>> test_id = framework.create_test(config, assignment_ratio=0.5)
        >>> group = framework.assign_user_to_group(test_id, "user123")
        >>> framework.record_outcome(test_id, "user123", TestOutcome(
        ...     skill_name="pytest-run",
        ...     completed=True,
        ...     duration_seconds=45.0,
        ... ))
        >>> results = framework.analyze_results(test_id)
        >>> print(results.recommendation)
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize A/B testing framework.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def create_test(
        self,
        config: ABTestConfig,
        assignment_ratio: float = 0.5,
    ) -> int:
        """Create a new A/B test.

        Args:
            config: Test configuration
            assignment_ratio: Ratio for control group (0.0 to 1.0)

        Returns:
            test_id: ID of created test

        Raises:
            ValueError: If test name already exists
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if test name already exists
            cursor.execute(
                "SELECT test_id FROM ab_test_configs WHERE test_name = ?",
                (config.test_name,),
            )
            if cursor.fetchone() is not None:
                raise ValueError(f"Test '{config.test_name}' already exists")

            # Insert test configuration
            cursor.execute(
                """
                INSERT INTO ab_test_configs (
                    test_name, description,
                    control_strategy, treatment_strategy,
                    start_date, end_date,
                    min_sample_size, metrics,
                    assignment_ratio, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.test_name,
                    config.description,
                    config.control_strategy,
                    config.treatment_strategy,
                    config.start_date,
                    config.end_date,
                    config.min_sample_size,
                    ",".join(config.metrics),
                    assignment_ratio,
                    config.status,
                ),
            )

            return cursor.lastrowid

    def assign_user_to_group(
        self,
        test_id: int,
        user_id: str,
    ) -> Literal["control", "treatment"]:
        """Assign user to control or treatment group.

        Uses deterministic hashing to ensure consistent assignment
        for the same user across multiple calls.

        Args:
            test_id: Test identifier
            user_id: User identifier

        Returns:
            Group assignment: "control" or "treatment"

        Raises:
            ValueError: If test not found
        """
        # Get test configuration
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT assignment_ratio, status
                FROM ab_test_configs
                WHERE test_id = ?
                """,
                (test_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"Test {test_id} not found")

            if row["status"] != "running":
                raise ValueError(
                    f"Test {test_id} is not running (status: {row['status']})"
                )

            assignment_ratio = row["assignment_ratio"]

        # Deterministic assignment using hash
        hash_value = int(
            hashlib.sha256(f"{test_id}:{user_id}".encode()).hexdigest(), 16
        )
        hash_float = (hash_value % 10000) / 10000.0  # Normalize to [0, 1)

        group = "control" if hash_float < assignment_ratio else "treatment"

        # Store assignment
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO ab_test_assignments (
                    test_id, user_id, group_name, assigned_at
                ) VALUES (?, ?, ?, ?)
                """,
                (test_id, user_id, group, datetime.now().isoformat()),
            )

        return group

    def record_outcome(
        self,
        test_id: int,
        user_id: str,
        outcome: TestOutcome,
    ) -> None:
        """Record outcome of a skill invocation.

        Args:
            test_id: Test identifier
            user_id: User identifier
            outcome: Test outcome data

        Raises:
            ValueError: If user not assigned to test or test not found
        """
        # Verify user is assigned to test
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT group_name FROM ab_test_assignments
                WHERE test_id = ? AND user_id = ?
                """,
                (test_id, user_id),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"User {user_id} not assigned to test {test_id}")

        # Record outcome
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO ab_test_outcomes (
                    test_id, user_id, skill_name,
                    completed, duration_seconds, user_rating, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_id,
                    user_id,
                    outcome.skill_name,
                    1 if outcome.completed else 0,
                    outcome.duration_seconds,
                    outcome.user_rating,
                    datetime.now().isoformat(),
                ),
            )

    def analyze_results(self, test_id: int) -> TestAnalysisResult:
        """Analyze A/B test results with statistical testing.

        Performs t-test comparing control vs treatment group metrics.

        Args:
            test_id: Test identifier

        Returns:
            TestAnalysisResult with metrics and recommendation

        Raises:
            ValueError: If test not found or insufficient data
        """
        # Get test configuration
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    test_name,
                    control_strategy,
                    treatment_strategy,
                    min_sample_size,
                    metrics
                FROM ab_test_configs
                WHERE test_id = ?
                """,
                (test_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"Test {test_id} not found")

            row["test_name"]
            row["control_strategy"]
            row["treatment_strategy"]
            min_sample_size = row["min_sample_size"]
            row["metrics"].split(",")

        # Get outcomes for each group
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Control group outcomes
            cursor.execute(
                """
                SELECT completed, duration_seconds, user_rating
                FROM ab_test_outcomes ao
                JOIN ab_test_assignments aa ON ao.test_id = aa.test_id AND ao.user_id = aa.user_id
                WHERE ao.test_id = ? AND aa.group_name = 'control'
                """,
                (test_id,),
            )
            control_outcomes = cursor.fetchall()

            # Treatment group outcomes
            cursor.execute(
                """
                SELECT completed, duration_seconds, user_rating
                FROM ab_test_outcomes ao
                JOIN ab_test_assignments aa ON ao.test_id = aa.test_id AND ao.user_id = aa.user_id
                WHERE ao.test_id = ? AND aa.group_name = 'treatment'
                """,
                (test_id,),
            )
            treatment_outcomes = cursor.fetchall()

        # Calculate metrics
        control_metrics = self._calculate_group_metrics(control_outcomes)
        treatment_metrics = self._calculate_group_metrics(treatment_outcomes)

        # Check minimum sample size
        if (
            control_metrics["sample_size"] < min_sample_size
            or treatment_metrics["sample_size"] < min_sample_size
        ):
            return TestAnalysisResult(
                control_metrics=control_metrics,
                treatment_metrics=treatment_metrics,
                statistical_significance=1.0,
                winner="inconclusive",
                recommendation=f"Insufficient data (need {min_sample_size} per group)",
            )

        # Perform statistical test (t-test for completion rate)
        control_completion = [1 if o["completed"] else 0 for o in control_outcomes]
        treatment_completion = [1 if o["completed"] else 0 for o in treatment_outcomes]

        t_stat, p_value = stats.ttest_ind(control_completion, treatment_completion)

        # Determine winner
        if p_value < 0.05:  # Statistically significant
            if (
                treatment_metrics["completion_rate"]
                > control_metrics["completion_rate"]
            ):
                winner = "treatment"
                recommendation = (
                    f"Ship treatment strategy (p={p_value:.4f}). "
                    f"Treatment improves completion rate by "
                    f"{(treatment_metrics['completion_rate'] - control_metrics['completion_rate']) * 100:.1f}pp."
                )
            else:
                winner = "control"
                recommendation = (
                    f"Keep control strategy (p={p_value:.4f}). "
                    f"Treatment does not improve over control."
                )
        else:
            winner = "inconclusive"
            recommendation = (
                f"No statistically significant difference (p={p_value:.4f}). "
                "Continue testing or increase sample size."
            )

        return TestAnalysisResult(
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
            statistical_significance=p_value,
            winner=winner,
            recommendation=recommendation,
        )

    def _calculate_group_metrics(
        self, outcomes: list[sqlite3.Row]
    ) -> dict[str, object]:
        """Calculate metrics for a group.

        Args:
            outcomes: List of outcome rows

        Returns:
            Dictionary with group metrics
        """
        if not outcomes:
            return {
                "sample_size": 0,
                "completion_rate": 0.0,
                "avg_duration_seconds": 0.0,
                "avg_user_rating": 0.0,
            }

        completed_count = sum(1 for o in outcomes if o["completed"])
        completion_rate = completed_count / len(outcomes)

        durations = [
            o["duration_seconds"] for o in outcomes if o["duration_seconds"] is not None
        ]
        avg_duration = np.mean(durations) if durations else 0.0

        ratings = [o["user_rating"] for o in outcomes if o["user_rating"] is not None]
        avg_rating = np.mean(ratings) if ratings else 0.0

        return {
            "sample_size": len(outcomes),
            "completion_rate": completion_rate,
            "avg_duration_seconds": float(avg_duration),
            "avg_user_rating": float(avg_rating),
        }

    def get_test_status(self, test_id: int) -> dict[str, object]:
        """Get current status of an A/B test.

        Args:
            test_id: Test identifier

        Returns:
            Dictionary with test status information
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    test_name,
                    control_strategy,
                    treatment_strategy,
                    start_date,
                    end_date,
                    status,
                    min_sample_size
                FROM ab_test_configs
                WHERE test_id = ?
                """,
                (test_id,),
            )
            config_row = cursor.fetchone()

            if config_row is None:
                raise ValueError(f"Test {test_id} not found")

            # Get sample sizes
            cursor.execute(
                """
                SELECT
                    group_name,
                    COUNT(*) as count
                FROM ab_test_assignments
                WHERE test_id = ?
                GROUP BY group_name
                """,
                (test_id,),
            )
            assignment_counts = {
                row["group_name"]: row["count"] for row in cursor.fetchall()
            }

            return {
                "test_name": config_row["test_name"],
                "control_strategy": config_row["control_strategy"],
                "treatment_strategy": config_row["treatment_strategy"],
                "start_date": config_row["start_date"],
                "end_date": config_row["end_date"],
                "status": config_row["status"],
                "min_sample_size": config_row["min_sample_size"],
                "control_sample_size": assignment_counts.get("control", 0),
                "treatment_sample_size": assignment_counts.get("treatment", 0),
            }

    def stop_test(self, test_id: int) -> None:
        """Stop an A/B test.

        Args:
            test_id: Test identifier

        Raises:
            ValueError: If test not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE ab_test_configs SET status = 'stopped', end_date = ? WHERE test_id = ?",
                (datetime.now().isoformat(), test_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Test {test_id} not found")


def get_ab_framework(db_path: Path | None = None) -> ABTestFramework:
    """Get or create A/B testing framework instance.

    Args:
        db_path: Path to database file. Defaults to
            `.session-buddy/skills.db` in current directory.

    Returns:
        ABTestFramework instance
    """
    if db_path is None:
        db_path = Path.cwd() / ".session-buddy" / "skills.db"

    return ABTestFramework(db_path=db_path)
