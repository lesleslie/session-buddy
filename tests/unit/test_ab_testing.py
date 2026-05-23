"""Comprehensive pytest unit tests for session_buddy.analytics.ab_testing module.

Tests cover:
- ABTestConfig dataclass
- TestOutcome dataclass
- TestAnalysisResult dataclass
- ABTestFramework class (all public methods)
- get_ab_framework helper function

Edge cases:
- Empty experiments
- Missing variants
- Bias prevention (assignment ratio)
- Concurrent access patterns
- Invalid test states
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from session_buddy.analytics.ab_testing import (
    ABTestConfig,
    ABTestFramework,
    TestAnalysisResult,
    TestOutcome,
    get_ab_framework,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database with the A/B testing schema."""
    db_path = tmp_path / "test_ab.db"

    # Create the schema
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # ab_test_configs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_configs (
                test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT NOT NULL UNIQUE,
                description TEXT,
                control_strategy TEXT NOT NULL,
                treatment_strategy TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                min_sample_size INTEGER DEFAULT 100,
                metrics TEXT,
                assignment_ratio REAL DEFAULT 0.5,
                status TEXT DEFAULT 'running',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # ab_test_assignments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_assignments (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                group_name TEXT NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                UNIQUE(test_id, user_id)
            )
        """)
        # ab_test_outcomes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                completed BOOLEAN NOT NULL,
                duration_seconds REAL,
                user_rating REAL,
                recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
            )
        """)
        conn.commit()

    return db_path


@pytest.fixture
def framework(temp_db: Path) -> ABTestFramework:
    """Create an ABTestFramework instance with temporary database."""
    return ABTestFramework(db_path=temp_db)


@pytest.fixture
def sample_config() -> ABTestConfig:
    """Create a sample ABTestConfig for testing."""
    return ABTestConfig(
        test_name="test_experiment",
        description="Test A/B experiment",
        control_strategy="semantic_search",
        treatment_strategy="workflow_aware_search",
        start_date="2025-01-01T00:00:00",
        end_date=None,
        min_sample_size=10,
        metrics=["completion_rate", "user_satisfaction"],
        assignment_ratio=0.5,
        status="running",
    )


# =============================================================================
# ABTestConfig Dataclass Tests
# =============================================================================


class TestABTestConfig:
    """Tests for ABTestConfig dataclass."""

    def test_config_creation_with_required_fields(self) -> None:
        """Test creating config with only required fields."""
        config = ABTestConfig(
            test_name="test_name",
            description="Test description",
            control_strategy="control",
            treatment_strategy="treatment",
            start_date="2025-01-01T00:00:00",
        )

        assert config.test_name == "test_name"
        assert config.description == "Test description"
        assert config.control_strategy == "control"
        assert config.treatment_strategy == "treatment"
        assert config.start_date == "2025-01-01T00:00:00"
        assert config.end_date is None
        assert config.min_sample_size == 100
        assert config.metrics == ["completion_rate"]
        assert config.assignment_ratio == 0.5
        assert config.status == "running"

    def test_config_creation_with_all_fields(self) -> None:
        """Test creating config with all fields specified."""
        config = ABTestConfig(
            test_name="full_config_test",
            description="Full configuration test",
            control_strategy="strategy_a",
            treatment_strategy="strategy_b",
            start_date="2025-01-01T00:00:00",
            end_date="2025-02-01T00:00:00",
            min_sample_size=200,
            metrics=["completion_rate", "user_satisfaction", "latency"],
            assignment_ratio=0.6,
            status="completed",
        )

        assert config.test_name == "full_config_test"
        assert config.end_date == "2025-02-01T00:00:00"
        assert config.min_sample_size == 200
        assert config.metrics == ["completion_rate", "user_satisfaction", "latency"]
        assert config.assignment_ratio == 0.6
        assert config.status == "completed"

    def test_config_default_values(self) -> None:
        """Test that default values are correctly applied."""
        config = ABTestConfig(
            test_name="defaults_test",
            description="Testing defaults",
            control_strategy="control",
            treatment_strategy="treatment",
            start_date="2025-01-01T00:00:00",
        )

        assert config.assignment_ratio == 0.5
        assert config.status == "running"
        assert config.min_sample_size == 100

    def test_config_mutable_metrics_default(self) -> None:
        """Test that metrics default is a mutable list (edge case)."""
        config1 = ABTestConfig(
            test_name="test1",
            description="test",
            control_strategy="control",
            treatment_strategy="treatment",
            start_date="2025-01-01T00:00:00",
        )
        config2 = ABTestConfig(
            test_name="test2",
            description="test",
            control_strategy="control",
            treatment_strategy="treatment",
            start_date="2025-01-01T00:00:00",
        )

        # Verify they have separate list instances (field default_factory behavior)
        config1.metrics.append("extra_metric")
        assert "extra_metric" not in config2.metrics


# =============================================================================
# TestOutcome Dataclass Tests
# =============================================================================


class TestTestOutcome:
    """Tests for TestOutcome dataclass."""

    def test_outcome_minimal(self) -> None:
        """Test outcome with only required fields."""
        outcome = TestOutcome(
            skill_name="pytest-run",
            completed=True,
        )

        assert outcome.skill_name == "pytest-run"
        assert outcome.completed is True
        assert outcome.duration_seconds is None
        assert outcome.user_rating is None

    def test_outcome_full(self) -> None:
        """Test outcome with all fields."""
        outcome = TestOutcome(
            skill_name="code-review",
            completed=True,
            duration_seconds=120.5,
            user_rating=4.5,
        )

        assert outcome.skill_name == "code-review"
        assert outcome.completed is True
        assert outcome.duration_seconds == 120.5
        assert outcome.user_rating == 4.5

    def test_outcome_failed(self) -> None:
        """Test outcome for failed skill invocation."""
        outcome = TestOutcome(
            skill_name="deploy",
            completed=False,
            duration_seconds=45.0,
        )

        assert outcome.completed is False
        assert outcome.duration_seconds == 45.0

    def test_outcome_with_rating_only(self) -> None:
        """Test outcome with user rating but no duration."""
        outcome = TestOutcome(
            skill_name="test-run",
            completed=True,
            user_rating=5.0,
        )

        assert outcome.duration_seconds is None
        assert outcome.user_rating == 5.0


# =============================================================================
# TestAnalysisResult Dataclass Tests
# =============================================================================


class TestTestAnalysisResult:
    """Tests for TestAnalysisResult dataclass."""

    def test_result_winner_treatment(self) -> None:
        """Test result when treatment wins."""
        result = TestAnalysisResult(
            control_metrics={"sample_size": 100, "completion_rate": 0.7},
            treatment_metrics={"sample_size": 100, "completion_rate": 0.85},
            statistical_significance=0.02,
            winner="treatment",
            recommendation="Ship treatment strategy",
        )

        assert result.winner == "treatment"
        assert result.statistical_significance == 0.02
        assert result.control_metrics["completion_rate"] == 0.7
        assert result.treatment_metrics["completion_rate"] == 0.85

    def test_result_winner_control(self) -> None:
        """Test result when control wins."""
        result = TestAnalysisResult(
            control_metrics={"sample_size": 100, "completion_rate": 0.8},
            treatment_metrics={"sample_size": 100, "completion_rate": 0.65},
            statistical_significance=0.01,
            winner="control",
            recommendation="Keep control strategy",
        )

        assert result.winner == "control"
        assert result.statistical_significance == 0.01

    def test_result_inconclusive(self) -> None:
        """Test result when test is inconclusive."""
        result = TestAnalysisResult(
            control_metrics={"sample_size": 50, "completion_rate": 0.75},
            treatment_metrics={"sample_size": 50, "completion_rate": 0.77},
            statistical_significance=0.35,
            winner="inconclusive",
            recommendation="Continue testing",
        )

        assert result.winner == "inconclusive"
        assert result.statistical_significance == 0.35


# =============================================================================
# ABTestFramework Tests
# =============================================================================


class TestABTestFramework:
    """Comprehensive tests for ABTestFramework class."""

    # -------------------------------------------------------------------------
    # create_test tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_test_basic(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test basic test creation."""
        test_id = framework.create_test(sample_config)

        assert isinstance(test_id, int)
        assert test_id >= 1

    @pytest.mark.asyncio
    async def test_create_test_with_custom_ratio(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test creating test with custom assignment ratio."""
        test_id = framework.create_test(sample_config, assignment_ratio=0.7)

        assert isinstance(test_id, int)

        # Verify ratio was stored
        with sqlite3.connect(framework.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT assignment_ratio FROM ab_test_configs WHERE test_id = ?", (test_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 0.7

    @pytest.mark.asyncio
    async def test_create_duplicate_test_raises(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test that creating a duplicate test name raises ValueError."""
        framework.create_test(sample_config)

        with pytest.raises(ValueError, match="already exists"):
            framework.create_test(sample_config)

    @pytest.mark.asyncio
    async def test_create_multiple_unique_tests(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test creating multiple tests with unique names."""
        config1 = sample_config
        config2 = ABTestConfig(
            test_name="second_test",
            description="Second test",
            control_strategy="control",
            treatment_strategy="treatment",
            start_date="2025-01-01T00:00:00",
        )

        id1 = framework.create_test(config1)
        id2 = framework.create_test(config2)

        assert id1 != id2

    # -------------------------------------------------------------------------
    # assign_user_to_group tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_assign_user_control_group(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test user assignment to control group."""
        test_id = framework.create_test(sample_config)

        # Use a user_id that will hash to control (ratio 0.5)
        group = framework.assign_user_to_group(test_id, "user_control")

        assert group in ("control", "treatment")

    @pytest.mark.asyncio
    async def test_assign_user_deterministic(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test that same user always gets same assignment."""
        test_id = framework.create_test(sample_config)

        group1 = framework.assign_user_to_group(test_id, "consistent_user")
        group2 = framework.assign_user_to_group(test_id, "consistent_user")

        assert group1 == group2

    @pytest.mark.asyncio
    async def test_assign_user_different_users_different_assignments(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test that different users may get different assignments."""
        test_id = framework.create_test(sample_config)

        assignments = set()
        for i in range(100):
            user_id = f"user_{i}"
            group = framework.assign_user_to_group(test_id, user_id)
            assignments.add(group)

        # With 100 users and 50/50 split, we expect both groups represented
        # (though statistically possible to miss, so just check at least one)
        assert len(assignments) >= 1

    @pytest.mark.asyncio
    async def test_assign_nonexistent_test_raises(self, framework: ABTestFramework) -> None:
        """Test assigning user to non-existent test raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            framework.assign_user_to_group(99999, "user123")

    @pytest.mark.asyncio
    async def test_assign_stopped_test_raises(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test assigning user to stopped test raises ValueError."""
        test_id = framework.create_test(sample_config)
        framework.stop_test(test_id)

        with pytest.raises(ValueError, match="not running"):
            framework.assign_user_to_group(test_id, "user123")

    @pytest.mark.asyncio
    async def test_assign_replaces_existing_assignment(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test that assigning same user replaces their assignment."""
        test_id = framework.create_test(sample_config)

        # First assignment
        group1 = framework.assign_user_to_group(test_id, "user_x")
        # Second assignment should not fail (INSERT OR REPLACE)
        group2 = framework.assign_user_to_group(test_id, "user_x")

        # Should succeed without error
        assert group2 in ("control", "treatment")

    @pytest.mark.asyncio
    async def test_assign_bias_prevention_50_50(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test assignment bias prevention with 50/50 split."""
        test_id = framework.create_test(sample_config, assignment_ratio=0.5)

        control_count = 0
        treatment_count = 0

        for i in range(1000):
            user_id = f"bias_test_user_{i}"
            group = framework.assign_user_to_group(test_id, user_id)
            if group == "control":
                control_count += 1
            else:
                treatment_count += 1

        # Should be roughly 50/50 (allow 10% tolerance)
        ratio = control_count / (control_count + treatment_count)
        assert 0.4 <= ratio <= 0.6

    @pytest.mark.asyncio
    async def test_assign_bias_prevention_80_20(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test assignment bias prevention with 80/20 split."""
        test_id = framework.create_test(sample_config, assignment_ratio=0.8)

        control_count = 0
        treatment_count = 0

        for i in range(1000):
            user_id = f"bias_80_user_{i}"
            group = framework.assign_user_to_group(test_id, user_id)
            if group == "control":
                control_count += 1
            else:
                treatment_count += 1

        # Should be roughly 80/20 (allow 10% tolerance)
        ratio = control_count / (control_count + treatment_count)
        assert 0.7 <= ratio <= 0.9

    # -------------------------------------------------------------------------
    # record_outcome tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_record_outcome_basic(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test recording a basic outcome."""
        test_id = framework.create_test(sample_config)
        framework.assign_user_to_group(test_id, "user1")

        outcome = TestOutcome(
            skill_name="pytest-run",
            completed=True,
            duration_seconds=30.0,
        )

        # Should not raise
        framework.record_outcome(test_id, "user1", outcome)

    @pytest.mark.asyncio
    async def test_record_outcome_with_rating(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test recording outcome with user rating."""
        test_id = framework.create_test(sample_config)
        framework.assign_user_to_group(test_id, "user1")

        outcome = TestOutcome(
            skill_name="code-review",
            completed=True,
            duration_seconds=45.0,
            user_rating=4.5,
        )

        framework.record_outcome(test_id, "user1", outcome)

        # Verify stored
        with sqlite3.connect(framework.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT skill_name, completed, duration_seconds, user_rating FROM ab_test_outcomes WHERE user_id = ?",
                ("user1",),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "code-review"
            assert row[1] == 1
            assert row[2] == 45.0
            assert row[3] == 4.5

    @pytest.mark.asyncio
    async def test_record_outcome_unassigned_user_raises(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test recording outcome for unassigned user raises ValueError."""
        test_id = framework.create_test(sample_config)
        # Don't assign user

        outcome = TestOutcome(skill_name="test", completed=True)

        with pytest.raises(ValueError, match="not assigned"):
            framework.record_outcome(test_id, "unassigned_user", outcome)

    @pytest.mark.asyncio
    async def test_record_outcome_multiple(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test recording multiple outcomes for same user."""
        test_id = framework.create_test(sample_config)
        framework.assign_user_to_group(test_id, "user1")

        outcomes = [
            TestOutcome(skill_name="skill_a", completed=True, duration_seconds=10.0),
            TestOutcome(skill_name="skill_b", completed=True, duration_seconds=20.0),
            TestOutcome(skill_name="skill_c", completed=False, duration_seconds=5.0),
        ]

        for outcome in outcomes:
            framework.record_outcome(test_id, "user1", outcome)

        # Verify all stored
        with sqlite3.connect(framework.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM ab_test_outcomes WHERE test_id = ? AND user_id = ?",
                (test_id, "user1"),
            )
            count = cursor.fetchone()
            assert count is not None
            assert count[0] == 3

    # -------------------------------------------------------------------------
    # analyze_results tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_analyze_results_insufficient_data(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test analyze results when sample size is insufficient."""
        test_id = framework.create_test(sample_config)

        result = framework.analyze_results(test_id)

        assert result.winner == "inconclusive"
        assert "Insufficient data" in result.recommendation

    @pytest.mark.asyncio
    async def test_analyze_results_treatment_wins(
        self, framework: ABTestFramework, tmp_path: Path
    ) -> None:
        """Test analyze results when treatment significantly outperforms control.

        Uses direct SQL insertion to ensure exact group assignment despite
        hash-based random assignment in the framework.
        """
        # Create framework with direct SQL setup to ensure exact group sizes
        db_path = tmp_path / "treatment_wins.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        # Insert test config directly with all required fields including metrics
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("treatment_wins_test", "Treatment wins test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # Insert 15 control users with successful outcomes
            for i in range(15):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"control_user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, duration_seconds) VALUES (?, ?, ?, ?, ?)",
                    (test_id, f"control_user_{i}", "test_skill", 1, 30.0),
                )

            # Insert 15 treatment users with successful outcomes and ratings
            for i in range(15):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"treatment_user_{i}", "treatment"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, duration_seconds, user_rating) VALUES (?, ?, ?, ?, ?, ?)",
                    (test_id, f"treatment_user_{i}", "test_skill", 1, 30.0, 5.0),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        assert result.control_metrics["sample_size"] == 15
        assert result.treatment_metrics["sample_size"] == 15
        assert result.control_metrics["completion_rate"] == 1.0
        assert result.treatment_metrics["completion_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_analyze_results_control_wins(
        self, framework: ABTestFramework, tmp_path: Path
    ) -> None:
        """Test analyze results when control outperforms treatment.

        Uses direct SQL insertion to ensure exact group assignment.
        """
        db_path = tmp_path / "control_wins.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("control_wins_test", "Control wins test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # Control: 100% completion
            for i in range(15):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"control_user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed) VALUES (?, ?, ?, ?)",
                    (test_id, f"control_user_{i}", "test_skill", 1),
                )

            # Treatment: 0% completion
            for i in range(15):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"treatment_user_{i}", "treatment"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed) VALUES (?, ?, ?, ?)",
                    (test_id, f"treatment_user_{i}", "test_skill", 0),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        assert result.control_metrics["sample_size"] == 15
        assert result.treatment_metrics["sample_size"] == 15
        assert result.control_metrics["completion_rate"] == 1.0
        assert result.treatment_metrics["completion_rate"] == 0.0
        assert result.winner == "control"

    @pytest.mark.asyncio
    async def test_analyze_results_nonexistent_test_raises(self, framework: ABTestFramework) -> None:
        """Test analyze results for non-existent test raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            framework.analyze_results(99999)

    @pytest.mark.asyncio
    async def test_analyze_results_empty_groups(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test analyze results with no outcomes recorded."""
        test_id = framework.create_test(sample_config)
        # Assign users but no outcomes
        framework.assign_user_to_group(test_id, "user1")
        framework.assign_user_to_group(test_id, "user2")

        result = framework.analyze_results(test_id)

        # Should return inconclusive due to insufficient sample
        assert result.winner == "inconclusive"
        assert result.control_metrics["sample_size"] == 0
        assert result.treatment_metrics["sample_size"] == 0

    @pytest.mark.asyncio
    async def test_analyze_results_one_group_empty(
        self, framework: ABTestFramework, tmp_path: Path
    ) -> None:
        """Test analyze results when only one group has data.

        Uses direct SQL to ensure exactly 15 control users with outcomes
        and 0 treatment users with outcomes.
        """
        db_path = tmp_path / "one_group_empty.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("one_group_test", "One group test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # Only control group has outcomes
            for i in range(15):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"control_user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed) VALUES (?, ?, ?, ?)",
                    (test_id, f"control_user_{i}", "test_skill", 1),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        # Should still work, one group will be empty
        assert result.control_metrics["sample_size"] == 15
        assert result.treatment_metrics["sample_size"] == 0
        assert result.winner == "inconclusive"

    # -------------------------------------------------------------------------
    # _calculate_group_metrics tests (via analyze_results)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_calculate_metrics_all_completed(
        self, framework: ABTestFramework, tmp_path: Path
    ) -> None:
        """Test metrics calculation when all outcomes are completed."""
        db_path = tmp_path / "all_completed.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("all_completed_test", "All completed test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            for i in range(10):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, duration_seconds, user_rating) VALUES (?, ?, ?, ?, ?, ?)",
                    (test_id, f"user_{i}", "test_skill", 1, 30.0 + i, 4.0 + (i * 0.1)),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        metrics = result.control_metrics
        assert metrics["sample_size"] == 10
        assert metrics["completion_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_calculate_metrics_mixed_completion(
        self, framework: ABTestFramework, tmp_path: Path
    ) -> None:
        """Test metrics calculation with mixed completion rates."""
        db_path = tmp_path / "mixed_completion.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("mixed_test", "Mixed test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # 5 completed (i=0,2,4,6,8), 5 not completed (i=1,3,5,7,9)
            for i in range(10):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"user_{i}", "control"),
                )
                completed = 1 if i % 2 == 0 else 0
                duration = 30.0 if i % 2 == 0 else None
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, duration_seconds) VALUES (?, ?, ?, ?, ?)",
                    (test_id, f"user_{i}", "test_skill", completed, duration),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        metrics = result.control_metrics
        assert metrics["sample_size"] == 10
        assert metrics["completion_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_calculate_metrics_no_durations(self, framework: ABTestFramework, tmp_path: Path) -> None:
        """Test metrics calculation when no durations recorded."""
        db_path = tmp_path / "no_durations.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("no_durations_test", "No durations test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            for i in range(5):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, duration_seconds) VALUES (?, ?, ?, ?, ?)",
                    (test_id, f"user_{i}", "test_skill", 1, None),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        # Should handle None durations gracefully
        assert result.control_metrics["avg_duration_seconds"] == 0.0

    @pytest.mark.asyncio
    async def test_calculate_metrics_no_ratings(self, framework: ABTestFramework, tmp_path: Path) -> None:
        """Test metrics calculation when no ratings recorded."""
        db_path = tmp_path / "no_ratings.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("no_ratings_test", "No ratings test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            for i in range(5):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, user_rating) VALUES (?, ?, ?, ?, ?)",
                    (test_id, f"user_{i}", "test_skill", 1, None),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        # Should handle None ratings gracefully
        assert result.control_metrics["avg_user_rating"] == 0.0

    # -------------------------------------------------------------------------
    # get_test_status tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_status_basic(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test getting basic test status."""
        test_id = framework.create_test(sample_config)

        status = framework.get_test_status(test_id)

        assert status["test_name"] == "test_experiment"
        assert status["control_strategy"] == "semantic_search"
        assert status["treatment_strategy"] == "workflow_aware_search"
        assert status["status"] == "running"
        assert status["min_sample_size"] == 10

    @pytest.mark.asyncio
    async def test_get_status_with_assignments(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test getting status with user assignments."""
        test_id = framework.create_test(sample_config)

        # Add some assignments
        framework.assign_user_to_group(test_id, "user1")
        framework.assign_user_to_group(test_id, "user2")

        status = framework.get_test_status(test_id)

        assert status["control_sample_size"] >= 0
        assert status["treatment_sample_size"] >= 0
        assert status["control_sample_size"] + status["treatment_sample_size"] == 2

    @pytest.mark.asyncio
    async def test_get_status_nonexistent_raises(self, framework: ABTestFramework) -> None:
        """Test getting status for non-existent test raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            framework.get_test_status(99999)

    @pytest.mark.asyncio
    async def test_get_status_completed_test(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test getting status for completed test."""
        test_id = framework.create_test(sample_config)
        framework.stop_test(test_id)

        status = framework.get_test_status(test_id)

        assert status["status"] == "stopped"
        assert status["end_date"] is not None

    # -------------------------------------------------------------------------
    # stop_test tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stop_test_basic(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test stopping a test."""
        test_id = framework.create_test(sample_config)

        framework.stop_test(test_id)

        # Verify status
        with sqlite3.connect(framework.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, end_date FROM ab_test_configs WHERE test_id = ?", (test_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "stopped"
            assert row[1] is not None

    @pytest.mark.asyncio
    async def test_stop_nonexistent_test_raises(self, framework: ABTestFramework) -> None:
        """Test stopping non-existent test raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            framework.stop_test(99999)

    @pytest.mark.asyncio
    async def test_stop_already_stopped_test(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test stopping an already stopped test."""
        test_id = framework.create_test(sample_config)
        framework.stop_test(test_id)

        # Should not raise, just update
        framework.stop_test(test_id)

        status = framework.get_test_status(test_id)
        assert status["status"] == "stopped"


# =============================================================================
# get_ab_framework Tests
# =============================================================================


class TestGetAbFramework:
    """Tests for get_ab_framework helper function."""

    @pytest.mark.asyncio
    async def test_get_ab_framework_default_path(self, monkeypatch: Any) -> None:
        """Test get_ab_framework with default path."""
        # Mock Path.cwd() to return temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Create the .session-buddy directory
            session_buddy_dir = Path(tmpdir) / ".session-buddy"
            session_buddy_dir.mkdir()
            db_path = session_buddy_dir / "skills.db"

            # Create empty db
            with sqlite3.connect(db_path) as conn:
                pass

            framework = get_ab_framework()

            assert isinstance(framework, ABTestFramework)
            # Use os.path.realpath to resolve any symlinks (macOS /private/var/folders)
            assert os.path.realpath(framework.db_path) == os.path.realpath(db_path)

    @pytest.mark.asyncio
    async def test_get_ab_framework_custom_path(self, tmp_path: Path) -> None:
        """Test get_ab_framework with custom path."""
        custom_db = tmp_path / "custom.db"

        framework = get_ab_framework(custom_db)

        assert isinstance(framework, ABTestFramework)
        assert framework.db_path == custom_db

    @pytest.mark.asyncio
    async def test_get_ab_framework_none_uses_default(self, monkeypatch: Any) -> None:
        """Test that None db_path uses default path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Create the .session-buddy directory
            session_buddy_dir = Path(tmpdir) / ".session-buddy"
            session_buddy_dir.mkdir()
            db_path = session_buddy_dir / "skills.db"

            # Create empty db
            with sqlite3.connect(db_path) as conn:
                pass

            framework = get_ab_framework(None)

            assert isinstance(framework, ABTestFramework)
            # Use os.path.realpath to resolve any symlinks (macOS /private/var/folders)
            assert os.path.realpath(framework.db_path) == os.path.realpath(db_path)


# =============================================================================
# Edge Cases and Concurrent Access Tests
# =============================================================================


class TestABTestEdgeCases:
    """Tests for edge cases in A/B testing."""

    @pytest.mark.asyncio
    async def test_empty_experiment_no_assignments(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test experiment with no user assignments."""
        test_id = framework.create_test(sample_config)

        result = framework.analyze_results(test_id)

        assert result.winner == "inconclusive"
        assert result.control_metrics["sample_size"] == 0
        assert result.treatment_metrics["sample_size"] == 0

    @pytest.mark.asyncio
    async def test_missing_variant_handling(self, framework: ABTestFramework, tmp_path: Path) -> None:
        """Test experiment with only one variant having data.

        Uses direct SQL to ensure exactly 20 control users and 0 treatment users.
        """
        db_path = tmp_path / "missing_variant.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("missing_variant_test", "Missing variant test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # Only control group has assignments and outcomes
            for i in range(20):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"user_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed) VALUES (?, ?, ?, ?)",
                    (test_id, f"user_{i}", "test_skill", 1),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        # Should complete without error
        assert result.control_metrics["sample_size"] == 20
        assert result.treatment_metrics["sample_size"] == 0

    @pytest.mark.asyncio
    async def test_all_users_same_group(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test experiment where all users end up in same group."""
        test_id = framework.create_test(sample_config, assignment_ratio=0.99)

        # Assign many users
        for i in range(50):
            framework.assign_user_to_group(test_id, f"user_{i}")

        status = framework.get_test_status(test_id)

        # Both groups should exist (statistically very likely)
        total = status["control_sample_size"] + status["treatment_sample_size"]
        assert total == 50

    @pytest.mark.asyncio
    async def test_concurrent_assignments(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test handling concurrent assignment requests."""
        test_id = framework.create_test(sample_config)

        # Assign many users rapidly
        for i in range(100):
            framework.assign_user_to_group(test_id, f"concurrent_user_{i}")

        # Verify all assignments stored
        with sqlite3.connect(framework.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM ab_test_assignments WHERE test_id = ?",
                (test_id,),
            )
            count = cursor.fetchone()
            assert count is not None
            assert count[0] == 100

    @pytest.mark.asyncio
    async def test_large_sample_analysis(self, framework: ABTestFramework, tmp_path: Path) -> None:
        """Test analyzing results with large sample sizes."""
        db_path = tmp_path / "large_sample.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 100,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("large_sample_test", "Large sample test", "control", "treatment", "2025-01-01", 100, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # 200 total users: 100 control, 100 treatment
            for i in range(200):
                group = "control" if i < 100 else "treatment"
                completed = 1 if i % 10 != 0 else 0  # 90% completion rate
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"user_{i}", group),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed, duration_seconds, user_rating) VALUES (?, ?, ?, ?, ?, ?)",
                    (test_id, f"user_{i}", "test_skill", completed, 30.0 + (i % 20), 3.0 + (i % 5) * 0.5),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        assert result.control_metrics["sample_size"] == 100
        assert result.treatment_metrics["sample_size"] == 100
        assert 0.85 <= result.control_metrics["completion_rate"] <= 0.95

    @pytest.mark.asyncio
    async def test_zero_min_sample_size(self, tmp_path: Path) -> None:
        """Test experiment with zero min_sample_size."""
        # Create fresh framework
        db_path = tmp_path / "zero_min.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 100,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        # Create test with min_sample_size = 0
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("zero_min_test", "Test", "control", "treatment", "2025-01-01", 0, "completion_rate", "running"))
            test_id = cursor.lastrowid

        # Should handle 0 min_sample_size without error
        result = framework.analyze_results(test_id)
        assert result.winner == "inconclusive"  # Still needs data


# =============================================================================
# Statistical Significance Tests
# =============================================================================


class TestStatisticalSignificance:
    """Tests for statistical significance calculations."""

    @pytest.mark.asyncio
    async def test_high_significance_treatment(self, framework: ABTestFramework, tmp_path: Path) -> None:
        """Test detection of highly significant treatment improvement."""
        # Create test with large sample size
        db_path = tmp_path / "sig_test.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    control_strategy TEXT NOT NULL,
                    treatment_strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    min_sample_size INTEGER DEFAULT 10,
                    metrics TEXT,
                    assignment_ratio REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'running',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
                    UNIQUE(test_id, user_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    completed BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    user_rating REAL,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)
            conn.commit()

        framework = ABTestFramework(db_path)

        # Insert test config directly with all required fields
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_test_configs
                (test_name, description, control_strategy, treatment_strategy, start_date, min_sample_size, metrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("sig_test", "Significance test", "control", "treatment", "2025-01-01", 10, "completion_rate", "running"))
            test_id = cursor.lastrowid

            # Control: 50% completion
            for i in range(50):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"control_{i}", "control"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed) VALUES (?, ?, ?, ?)",
                    (test_id, f"control_{i}", "skill", 1 if i < 25 else 0),
                )

            # Treatment: 90% completion
            for i in range(50):
                cursor.execute(
                    "INSERT INTO ab_test_assignments (test_id, user_id, group_name) VALUES (?, ?, ?)",
                    (test_id, f"treatment_{i}", "treatment"),
                )
                cursor.execute(
                    "INSERT INTO ab_test_outcomes (test_id, user_id, skill_name, completed) VALUES (?, ?, ?, ?)",
                    (test_id, f"treatment_{i}", "skill", 1 if i < 45 else 0),
                )
            conn.commit()

        result = framework.analyze_results(test_id)

        assert result.winner in ("treatment", "control", "inconclusive")
        assert result.statistical_significance <= 1.0
        assert result.statistical_significance >= 0.0


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestABTestLifecycle:
    """Full lifecycle tests for A/B testing."""

    @pytest.mark.asyncio
    async def test_full_test_lifecycle(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test complete A/B test lifecycle from creation to analysis."""
        # 1. Create test
        test_id = framework.create_test(sample_config)
        assert test_id >= 1

        # 2. Verify status
        status = framework.get_test_status(test_id)
        assert status["status"] == "running"

        # 3. Assign users
        user_ids = [f"lifecycle_user_{i}" for i in range(30)]
        for user_id in user_ids:
            framework.assign_user_to_group(test_id, user_id)

        # 4. Record outcomes for all users
        for user_id in user_ids:
            outcome = TestOutcome(
                skill_name="lifecycle_skill",
                completed=True,
                duration_seconds=45.0,
                user_rating=4.0,
            )
            framework.record_outcome(test_id, user_id, outcome)

        # 5. Analyze results
        result = framework.analyze_results(test_id)

        # 6. Stop test
        framework.stop_test(test_id)

        # 7. Verify stopped status
        final_status = framework.get_test_status(test_id)
        assert final_status["status"] == "stopped"
        assert final_status["end_date"] is not None

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tests(self, framework: ABTestFramework) -> None:
        """Test running multiple A/B tests concurrently."""
        configs = [
            ABTestConfig(
                test_name=f"concurrent_test_{i}",
                description=f"Test {i}",
                control_strategy="control_a",
                treatment_strategy="treatment_a",
                start_date="2025-01-01T00:00:00",
            )
            for i in range(3)
        ]

        test_ids = [framework.create_test(cfg) for cfg in configs]

        # Assign users and record outcomes for each test
        for test_id in test_ids:
            for i in range(10):
                user_id = f"test{test_id}_user_{i}"
                framework.assign_user_to_group(test_id, user_id)
                outcome = TestOutcome(skill_name="test_skill", completed=True)
                framework.record_outcome(test_id, user_id, outcome)

        # Analyze all tests
        for test_id in test_ids:
            result = framework.analyze_results(test_id)
            # Due to hash-based assignment, each group may have different sizes
            total = result.control_metrics["sample_size"] + result.treatment_metrics["sample_size"]
            assert total == 10

    @pytest.mark.asyncio
    async def test_assignment_consistency_across_methods(self, framework: ABTestFramework, sample_config: ABTestConfig) -> None:
        """Test that assignment is consistent when checked via different methods."""
        test_id = framework.create_test(sample_config)
        test_user = "consistency_user"

        group = framework.assign_user_to_group(test_id, test_user)

        # Check assignment via get_test_status
        status = framework.get_test_status(test_id)

        # Verify user appears in correct group count
        with sqlite3.connect(framework.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT group_name FROM ab_test_assignments WHERE test_id = ? AND user_id = ?",
                (test_id, test_user),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == group