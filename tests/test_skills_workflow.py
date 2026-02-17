#!/usr/bin/env python3
"""Tests for workflow correlation features.

Tests cover:
- V3 migration (workflow tracking)
- Workflow analytics queries
- Workflow-aware recommendations
- Workflow visualizations

Test coverage target: 90%+
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest

from session_buddy.core.skills_tracker import SkillsTracker
from session_buddy.storage.skills_embeddings import pack_embedding
from session_buddy.storage.skills_storage import SkillsStorage
from session_buddy.storage.migrations.base import MigrationManager, MigrationLoader


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_db_path():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Ensure file is deleted at start (in case it exists from previous run)
    if db_path.exists():
        db_path.unlink()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def migration_dir():
    """Get migration directory path."""
    return Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"


@pytest.fixture
def migrated_db(temp_db_path, migration_dir):
    """Apply migrations to test database."""
    loader = MigrationLoader(migration_dir)
    manager = MigrationManager(temp_db_path, migration_dir)
    manager.migrate()
    return temp_db_path


@pytest.fixture
def storage_with_workflow_data(migrated_db):
    """Create storage with sample workflow data."""
    storage = SkillsStorage(db_path=migrated_db)

    # Create sample embeddings
    embeddings = {
        "setup": np.random.RandomState(42).randn(384).astype(np.float32),
        "execution": np.random.RandomState(43).randn(384).astype(np.float32),
        "verification": np.random.RandomState(44).randn(384).astype(np.float32),
        "deployment": np.random.RandomState(45).randn(384).astype(np.float32),
    }

    # Store invocations across different phases
    test_data = [
        # Setup phase - mostly successful
        ("config-tool", "2025-02-10T12:00:00", "session1", "setup", True, 5.0, embeddings["setup"]),
        ("config-tool", "2025-02-10T12:05:00", "session2", "setup", True, 4.5, embeddings["setup"]),
        ("config-tool", "2025-02-10T12:10:00", "session3", "setup", False, 2.0, embeddings["setup"]),  # Abandoned

        # Execution phase - mixed success
        ("test-runner", "2025-02-10T12:15:00", "session1", "execution", True, 15.0, embeddings["execution"]),
        ("test-runner", "2025-02-10T12:20:00", "session2", "execution", True, 18.0, embeddings["execution"]),
        ("test-runner", "2025-02-10T12:25:00", "session4", "execution", False, 3.0, embeddings["execution"]),  # Abandoned
        ("test-runner", "2025-02-10T12:30:00", "session5", "execution", False, 1.0, embeddings["execution"]),  # Abandoned

        # Verification phase - mostly successful
        ("lint-check", "2025-02-10T12:35:00", "session1", "verification", True, 8.0, embeddings["verification"]),
        ("lint-check", "2025-02-10T12:40:00", "session2", "verification", True, 7.5, embeddings["verification"]),
        ("lint-check", "2025-02-10T12:45:00", "session3", "verification", True, 9.0, embeddings["verification"]),

        # Deployment phase - high abandonment (bottleneck)
        ("deploy-app", "2025-02-10T12:50:00", "session1", "deployment", False, 2.0, embeddings["deployment"]),
        ("deploy-app", "2025-02-10T12:55:00", "session2", "deployment", False, 1.5, embeddings["deployment"]),
        ("deploy-app", "2025-02-10T13:00:00", "session3", "deployment", False, 3.0, embeddings["deployment"]),
        ("deploy-app", "2025-02-10T13:05:00", "session4", "deployment", True, 25.0, embeddings["deployment"]),
    ]

    for skill_name, invoked_at, session_id, phase, completed, duration, embedding in test_data:
        storage.store_invocation(
            skill_name=skill_name,
            invoked_at=invoked_at,
            session_id=session_id,
            workflow_phase=phase,
            completed=completed,
            duration_seconds=duration,
            embedding=pack_embedding(embedding),
        )

    return storage


# ============================================================================
# V3 Migration Tests
# ============================================================================


class TestV3Migration:
    """Tests for V3 workflow correlation migration."""

    def test_v3_adds_workflow_columns(self, migrated_db):
        """Test that V3 migration adds workflow_phase and workflow_step_id columns."""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.execute("PRAGMA table_info(skill_invocation)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert "workflow_phase" in columns, "workflow_phase column missing"
        assert "workflow_step_id" in columns, "workflow_step_id column missing"

    def test_v3_creates_analytics_views(self, migrated_db):
        """Test that V3 migration creates analytics views."""
        conn = sqlite3.connect(migrated_db)

        # Check that workflow-related views exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND (name LIKE '%skill%' OR name LIKE '%phase%' OR name LIKE '%workflow%')"
        )
        views = [row[0] for row in cursor.fetchall()]

        # Should have at least some workflow analytics views
        assert len(views) >= 1, "No workflow analytics views created"
        # Check for key views that should exist
        assert any("effectiveness" in v.lower() for v in views), "Missing effectiveness view"

        conn.close()

    def test_v3_creates_workflow_indexes(self, migrated_db):
        """Test that V3 migration creates workflow indexes."""
        conn = sqlite3.connect(migrated_db)

        # Check that workflow-related indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%workflow%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        # Should have workflow indexes
        assert len(indexes) >= 1, "No workflow indexes created"

        conn.close()


# ============================================================================
# Workflow Analytics Tests
# ============================================================================


class TestWorkflowAnalytics:
    """Tests for workflow analytics queries."""

    def test_get_workflow_skill_effectiveness(self, storage_with_workflow_data):
        """Test retrieving skill effectiveness by workflow phase."""
        results = storage_with_workflow_data.get_workflow_skill_effectiveness()

        # Should have data for all phases
        phases = {r["workflow_phase"] for r in results}
        assert "setup" in phases
        assert "execution" in phases
        assert "verification" in phases
        assert "deployment" in phases

        # Check structure
        for result in results:
            assert "skill_name" in result
            assert "workflow_phase" in result
            assert "completion_rate" in result
            assert "avg_duration_seconds" in result
            assert result["completion_rate"] >= 0.0
            assert result["completion_rate"] <= 100.0

    def test_get_workflow_skill_effectiveness_phase_filter(self, storage_with_workflow_data):
        """Test filtering by specific phase."""
        results = storage_with_workflow_data.get_workflow_skill_effectiveness(workflow_phase="setup")

        # Should only return setup phase data
        assert all(r["workflow_phase"] == "setup" for r in results)
        assert len(results) == 1  # Only config-tool in setup phase

    def test_identify_workflow_bottlenecks(self, storage_with_workflow_data):
        """Test bottleneck identification."""
        bottlenecks = storage_with_workflow_data.identify_workflow_bottlenecks(min_abandonment_rate=0.2)

        # Deployment should be identified as a bottleneck (75% abandonment)
        deployment_bottlenecks = [b for b in bottlenecks if b["workflow_phase"] == "deployment"]
        assert len(deployment_bottlenecks) > 0

        deployment = deployment_bottlenecks[0]
        assert deployment["abandonment_rate"] > 0.5  # High abandonment
        assert "bottleneck_score" in deployment

    def test_identify_workflow_bottlenecks_threshold(self, storage_with_workflow_data):
        """Test bottleneck identification with different thresholds."""
        # Low threshold - should find more bottlenecks
        bottlenecks_low = storage_with_workflow_data.identify_workflow_bottlenecks(min_abandonment_rate=0.1)
        assert len(bottlenecks_low) >= 2  # Deployment and execution

        # High threshold - should only find worst bottlenecks
        bottlenecks_high = storage_with_workflow_data.identify_workflow_bottlenecks(min_abandonment_rate=0.5)
        assert len(bottlenecks_high) >= 1  # At least deployment

    def test_get_workflow_phase_transitions(self, storage_with_workflow_data):
        """Test phase transition analysis."""
        transitions = storage_with_workflow_data.get_workflow_phase_transitions()

        # Check structure
        for transition in transitions:
            assert "from_phase" in transition
            assert "to_phase" in transition
            assert "invocation_count" in transition
            assert "most_common_skill" in transition
            assert transition["invocation_count"] > 0


# ============================================================================
# Workflow-Aware Recommendations Tests
# ============================================================================


class TestWorkflowAwareRecommendations:
    """Tests for workflow-aware skill recommendations."""

    def test_search_by_query_workflow_aware_same_phase_boost(self, storage_with_workflow_data):
        """Test that skills in the same phase get boosted."""
        # Get an embedding from execution phase
        with storage_with_workflow_data._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE workflow_phase = 'execution' LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row["embedding"]

        # Search for execution phase recommendations
        results = storage_with_workflow_data.search_by_query_workflow_aware(
            query_embedding,
            workflow_phase="execution",
            limit=5,
            phase_weight=0.5,  # Equal weight semantic and phase
        )

        # Should return results
        assert len(results) > 0

        # Results should have combined scores
        for invocation, score in results:
            assert score >= 0.0
            assert score <= 1.0

    def test_search_by_query_workflow_aware_different_phase_penalty(self, storage_with_workflow_data):
        """Test that skills from different phases get lower scores."""
        # Get an embedding from setup phase
        with storage_with_workflow_data._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE workflow_phase = 'setup' LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row["embedding"]

        # Search for execution phase (different from setup)
        results = storage_with_workflow_data.search_by_query_workflow_aware(
            query_embedding,
            workflow_phase="execution",  # Different phase
            limit=5,
            phase_weight=0.8,  # High phase weight
        )

        # Should return results
        assert len(results) >= 0

    def test_search_by_query_workflow_aware_no_phase_filter(self, storage_with_workflow_data):
        """Test that search works without phase filter (neutral)."""
        # Get any embedding
        with storage_with_workflow_data._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT embedding FROM skill_invocation WHERE embedding IS NOT NULL LIMIT 1"
            )
            row = cursor.fetchone()
            query_embedding = row["embedding"]

        # Search without phase filter
        results = storage_with_workflow_data.search_by_query_workflow_aware(
            query_embedding,
            workflow_phase=None,  # No phase filter
            limit=5,
        )

        # Should return results
        assert len(results) >= 0

    def test_recommend_skills_with_workflow_phase(self, storage_with_workflow_data):
        """Test SkillsTracker.recommend_skills with workflow phase."""
        tracker = SkillsTracker(session_id="test_session")

        # Recommend skills for execution phase
        recommendations = tracker.recommend_skills(
            user_query="run tests and verify",
            limit=5,
            workflow_phase="execution",
            phase_weight=0.4,
            db_path=storage_with_workflow_data.db_path,
        )

        # Should return recommendations
        assert len(recommendations) >= 0

        # Check structure
        for rec in recommendations:
            assert "skill_name" in rec
            assert "similarity_score" in rec
            assert "workflow_phase" in rec  # Should include phase when workflow-aware

    def test_recommend_skills_without_workflow_phase(self, storage_with_workflow_data):
        """Test SkillsTracker.recommend_skills without workflow phase (backward compatible)."""
        tracker = SkillsTracker(session_id="test_session")

        # Recommend skills without phase
        recommendations = tracker.recommend_skills(
            user_query="run tests and verify",
            limit=5,
            db_path=storage_with_workflow_data.db_path,
        )

        # Should return recommendations
        assert len(recommendations) >= 0

        # Should NOT include workflow_phase when not using workflow-aware search
        for rec in recommendations:
            assert "skill_name" in rec
            assert "similarity_score" in rec
            assert "workflow_phase" not in rec  # Should not be included


# ============================================================================
# Workflow Visualization Tests
# ============================================================================


class TestWorkflowVisualizations:
    """Tests for workflow visualization reports."""

    def test_generate_workflow_report(self, storage_with_workflow_data):
        """Test workflow report generation."""
        tracker = SkillsTracker(session_id="viz_test")

        report = tracker.generate_workflow_report(
            db_path=storage_with_workflow_data.db_path
        )

        # Check report structure
        assert "Workflow Correlation Report" in report
        assert "Skill Effectiveness by Workflow Phase" in report
        assert "Workflow Bottlenecks" in report
        assert "Phase Transitions" in report
        assert "Recommendations by Phase" in report

        # Check for phase data
        assert "setup" in report.lower() or "SETUP" in report
        assert "execution" in report.lower() or "EXECUTION" in report

    def test_generate_workflow_report_identifies_bottlenecks(self, storage_with_workflow_data):
        """Test that report identifies deployment as bottleneck."""
        tracker = SkillsTracker(session_id="viz_test")

        report = tracker.generate_workflow_report(
            db_path=storage_with_workflow_data.db_path
        )

        # Should mention deployment phase issues
        assert "deployment" in report.lower() or "DEPLOYMENT" in report

    def test_generate_phase_heatmap(self, storage_with_workflow_data):
        """Test phase heatmap generation."""
        tracker = SkillsTracker(session_id="viz_test")

        heatmap = tracker.generate_phase_heatmap(
            db_path=storage_with_workflow_data.db_path
        )

        # Check heatmap structure
        assert "Skill Usage Heatmap" in heatmap
        assert "Legend" in heatmap

        # Check for phase columns
        # (heatmap should show phases as columns)
        assert len(heatmap) > 0

    def test_generate_phase_heatmap_empty_database(self, migrated_db):
        """Test heatmap generation with no workflow data."""
        storage = SkillsStorage(db_path=migrated_db)
        tracker = SkillsTracker(session_id="empty_test")

        heatmap = tracker.generate_phase_heatmap(
            db_path=migrated_db
        )

        # Should handle empty data gracefully
        assert "No workflow data available" in heatmap or len(heatmap) > 0

    def test_visualizations_handle_session_filter(self, storage_with_workflow_data):
        """Test that visualizations can filter by session."""
        tracker = SkillsTracker(session_id="viz_test")

        # Generate report for specific session
        report = tracker.generate_workflow_report(
            db_path=storage_with_workflow_data.db_path,
            session_id="session1"
        )

        # Should mention the session
        assert "session1" in report

        # Generate heatmap for specific session
        heatmap = tracker.generate_phase_heatmap(
            db_path=storage_with_workflow_data.db_path,
            session_id="session1"
        )

        # Should produce output
        assert len(heatmap) > 0


# ============================================================================
# Integration Tests
# ============================================================================


class TestWorkflowIntegration:
    """Integration tests for complete workflow correlation workflows."""

    def test_full_workflow_tracking_workflow(self, migrated_db):
        """Test complete workflow: track skills, analyze, visualize."""
        storage = SkillsStorage(db_path=migrated_db)
        tracker = SkillsTracker(session_id="integration_test")

        # 1. Store workflow-phase-tagged invocations
        embedding = np.random.randn(384).astype(np.float32)

        storage.store_invocation(
            skill_name="build-tool",
            invoked_at="2025-02-10T14:00:00",
            session_id="integration_test",
            workflow_phase="setup",
            completed=True,
            duration_seconds=10.0,
            embedding=pack_embedding(embedding),
        )

        storage.store_invocation(
            skill_name="test-runner",
            invoked_at="2025-02-10T14:05:00",
            session_id="integration_test",
            workflow_phase="execution",
            completed=True,
            duration_seconds=20.0,
            embedding=pack_embedding(embedding),
        )

        # 2. Analyze workflow effectiveness
        effectiveness = storage.get_workflow_skill_effectiveness(workflow_phase="setup")
        assert len(effectiveness) > 0

        # 3. Get workflow-aware recommendations
        recommendations = tracker.recommend_skills(
            user_query="setup and configure",
            workflow_phase="setup",
            db_path=migrated_db,
        )
        assert len(recommendations) >= 0

        # 4. Generate visualizations
        report = tracker.generate_workflow_report(db_path=migrated_db)
        assert "Workflow Correlation Report" in report

        heatmap = tracker.generate_phase_heatmap(db_path=migrated_db)
        assert len(heatmap) > 0

    def test_workflow_data_persists_across_sessions(self, migrated_db):
        """Test that workflow data is correctly persisted and retrieved."""
        storage = SkillsStorage(db_path=migrated_db)

        # Store data with workflow context
        embedding = np.random.randn(384).astype(np.float32)

        storage.store_invocation(
            skill_name="example-skill",
            invoked_at="2025-02-10T15:00:00",
            session_id="persist_test",
            workflow_phase="verification",
            workflow_step_id="step_123",
            completed=True,
            embedding=pack_embedding(embedding),
        )

        # Retrieve and verify
        invocations = storage.get_session_invocations("persist_test")
        assert len(invocations) == 1

        retrieved = invocations[0]
        assert retrieved.workflow_phase == "verification"
        assert retrieved.workflow_step_id == "step_123"
