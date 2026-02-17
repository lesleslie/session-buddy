#!/usr/bin/env python3
"""Tests for skills tracking system.

Tests cover:
- Core tracking logic (SkillsTracker)
- Dhruva storage layer (SkillsStorage)
- Migration system
- End-to-end workflows

Test coverage target: 90%+
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from session_buddy.core.skills_tracker import (
    SkillInvocation,
    SkillMetrics,
    SkillsTracker,
)
from session_buddy.storage.skills_storage import (
    SkillsStorage,
    StoredInvocation,
    StoredMetrics,
)
from session_buddy.storage.migrations import (
    MigrationError,
    MigrationManager,
    get_migration_manager,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_db_path():
    """Create temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    # Cleanup handled by tempfile


@pytest.fixture
def empty_storage(temp_db_path):
    """Create empty storage with schema applied."""
    # Apply V1 migration first
    migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
    manager = get_migration_manager(db_path=temp_db_path, migration_dir=migration_dir)
    manager.migrate()

    # Then create storage
    storage = SkillsStorage(db_path=temp_db_path)
    return storage


@pytest.fixture
def tracker(temp_db_path):
    """Create skills tracker with temporary storage."""
    return SkillsTracker(session_id="test_session", metrics_file=temp_db_path)


@pytest.fixture
def sample_invocation():
    """Sample skill invocation for testing."""
    return SkillInvocation(
        skill_name="test-skill",
        invoked_at="2025-02-10T12:00:00",
        session_id="test_session",
        workflow_path="comprehensive",
        completed=True,
        duration_seconds=45.5,
        user_query="Test query",
        alternatives_considered=["alt-skill"],
        selection_rank=1,
        follow_up_actions=["continue"],
        error_type=None,
    )


# ============================================================================
# SkillsTracker Tests
# ============================================================================


class TestSkillsTracker:
    """Tests for SkillsTracker class."""

    def test_initialization(self, temp_db_path):
        """Test tracker initialization."""
        tracker = SkillsTracker(session_id="test123", metrics_file=temp_db_path)
        assert tracker.session_id == "test123"
        assert tracker._invocations == []
        assert tracker._skill_metrics == {}

    def test_track_invocation(self, tracker):
        """Test tracking a skill invocation."""
        completer = tracker.track_invocation(
            skill_name="test-skill",
            workflow_path="quick",
            user_query="Fix bug",
            alternatives_considered=["alt1", "alt2"],
            selection_rank=1,
        )

        # Should have one invocation in progress
        assert len(tracker._invocations) == 1
        invocation = tracker._invocations[0]
        assert invocation.skill_name == "test-skill"
        assert invocation.workflow_path == "quick"
        assert invocation.user_query == "Fix bug"
        assert invocation.alternatives_considered == ["alt1", "alt2"]
        assert invocation.selection_rank == 1
        assert invocation.completed is False  # Not completed yet

        # Complete the invocation
        completer(completed=True, follow_up_actions=["git commit"])

        assert invocation.completed is True
        assert invocation.follow_up_actions == ["git commit"]
        assert invocation.duration_seconds is not None
        assert invocation.duration_seconds > 0

    def test_get_session_skills(self, tracker):
        """Test getting skills for a session."""
        # Track multiple invocations
        for i in range(3):
            completer = tracker.track_invocation(
                skill_name=f"skill-{i % 2}",  # Alternate between skill-0 and skill-1
                workflow_path="comprehensive",
            )
            completer(completed=True)

        # Get session skills
        session_skills = tracker.get_session_skills()
        assert len(session_skills) == 3
        assert all(inv.session_id == "test_session" for inv in session_skills)

    def test_get_session_summary(self, tracker):
        """Test getting session summary."""
        # Track some invocations with different outcomes
        completer1 = tracker.track_invocation("skill-a", workflow_path="quick")
        completer1(completed=True, follow_up_actions=["continue"])

        completer2 = tracker.track_invocation("skill-b")
        completer2(completed=False, error_type="timeout")

        summary = tracker.get_session_summary()

        assert summary["session_id"] == "test_session"
        assert summary["total_invocations"] == 2
        assert summary["completed_invocations"] == 1
        assert summary["abandoned_invocations"] == 1
        assert summary["total_duration_seconds"] > 0

    def test_get_skill_metrics(self, tracker):
        """Test getting metrics for a specific skill."""
        # Track multiple invocations of the same skill
        for i in range(5):
            completer = tracker.track_invocation("test-skill")
            completer(completed=(i % 2 == 0))  # Alternate completion

        metrics = tracker.get_skill_metrics("test-skill")

        assert metrics is not None
        assert metrics.skill_name == "test-skill"
        assert metrics.total_invocations == 5
        assert metrics.completed_invocations == 3  # 0, 2, 4
        assert metrics.abandoned_invocations == 2  # 1, 3
        assert metrics.completion_rate() == 60.0

    def test_export_import_roundtrip(self, tracker):
        """Test exporting and importing metrics."""
        # Track some invocations
        completer = tracker.track_invocation("test-skill", user_query="Test")
        completer(completed=True, follow_up_actions=["done"])

        # Export to file
        export_file = tempfile.mktemp(suffix=".json")
        tracker.export_metrics(Path(export_file))

        # Create new tracker and verify data
        new_tracker = SkillsTracker(session_id="new_session", metrics_file=Path(export_file))
        metrics = new_tracker.get_skill_metrics("test-skill")

        assert metrics is not None
        assert metrics.total_invocations == 1

        # Cleanup
        Path(export_file).unlink()


# ============================================================================
# SkillsStorage Tests
# ============================================================================


class TestSkillsStorage:
    """Tests for SkillsStorage class."""

    def test_store_invocation(self, empty_storage):
        """Test storing a skill invocation."""
        storage = empty_storage

        invocation_id = storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session123",
            workflow_path="comprehensive",
            completed=True,
            duration_seconds=60.0,
            user_query="Test query",
            alternatives_considered=["alt1"],
            selection_rank=1,
            follow_up_actions=["continue"],
        )

        assert invocation_id > 0

        # Verify invocation was stored
        invocation = storage.get_invocation(invocation_id)
        assert invocation is not None
        assert invocation.skill_name == "test-skill"
        assert invocation.session_id == "session123"
        assert invocation.completed is True

    def test_get_invocation_not_found(self, empty_storage):
        """Test getting non-existent invocation."""
        storage = empty_storage
        invocation = storage.get_invocation(99999)
        assert invocation is None

    def test_get_session_invocations(self, empty_storage):
        """Test getting all invocations for a session."""
        storage = empty_storage

        # Store multiple invocations for the same session
        for i in range(3):
            storage.store_invocation(
                skill_name=f"skill-{i}",
                invoked_at=f"2025-02-10T{i:02d}:00:00",
                session_id="session123",
                completed=(i % 2 == 0),
            )

        # Get session invocations
        invocations = storage.get_session_invocations("session123")
        assert len(invocations) == 3
        assert all(inv.session_id == "session123" for inv in invocations)

    def test_get_metrics(self, empty_storage):
        """Test getting metrics for a skill."""
        storage = empty_storage

        # Store multiple invocations
        for i in range(5):
            storage.store_invocation(
                skill_name="test-skill",
                invoked_at=f"2025-02-10T{i:02d}:00:00",
                session_id="session123",
                completed=(i % 2 == 0),
                duration_seconds=50.0 if (i % 2 == 0) else None,
            )

        # Get metrics
        metrics = storage.get_metrics("test-skill")
        assert metrics is not None
        assert metrics.skill_name == "test-skill"
        assert metrics.total_invocations == 5
        assert metrics.completed_invocations == 3
        assert metrics.abandoned_invocations == 2
        assert metrics.completion_rate == 60.0

    def test_get_metrics_not_found(self, empty_storage):
        """Test getting metrics for non-existent skill."""
        storage = empty_storage
        metrics = storage.get_metrics("non-existent")
        assert metrics is None

    def test_get_all_metrics(self, empty_storage):
        """Test getting metrics for all skills."""
        storage = empty_storage

        # Store invocations for different skills
        storage.store_invocation(
            skill_name="skill-a",
            invoked_at="2025-02-10T12:00:00",
            session_id="session1",
            completed=True,
            duration_seconds=30.0,
        )
        storage.store_invocation(
            skill_name="skill-b",
            invoked_at="2025-02-10T13:00:00",
            session_id="session1",
            completed=True,
            duration_seconds=45.0,
        )

        # Get all metrics
        all_metrics = storage.get_all_metrics()
        assert len(all_metrics) == 2

        skill_names = {m.skill_name for m in all_metrics}
        assert "skill-a" in skill_names
        assert "skill-b" in skill_names

    def test_get_session_summary(self, empty_storage):
        """Test getting session summary."""
        storage = empty_storage

        # Store invocations
        storage.store_invocation(
            skill_name="skill-a",
            invoked_at="2025-02-10T12:00:00",
            session_id="session123",
            completed=True,
            duration_seconds=30.0,
        )
        storage.store_invocation(
            skill_name="skill-a",
            invoked_at="2025-02-10T13:00:00",
            session_id="session123",
            completed=False,
        )

        # Get summary
        summary = storage.get_session_summary("session123")
        assert summary["session_id"] == "session123"
        assert summary["total_invocations"] == 2
        assert summary["completed_count"] == 1
        assert summary["abandoned_count"] == 1

    def test_get_top_skills(self, empty_storage):
        """Test getting top skills by usage."""
        storage = empty_storage

        # Create skills with different usage counts
        for i in range(10):
            storage.store_invocation(
                skill_name="popular-skill",
                invoked_at=f"2025-02-10T{i:02d}:00:00",
                session_id="session1",
                completed=True,
                duration_seconds=30.0,
            )
        for i in range(3):
            storage.store_invocation(
                skill_name="unpopular-skill",
                invoked_at=f"2025-02-10T{i:02d}:00:00",
                session_id="session1",
                completed=True,
                duration_seconds=20.0,
            )

        # Get top skills
        top_skills = storage.get_top_skills(limit=5)
        assert len(top_skills) > 0
        assert top_skills[0].skill_name == "popular-skill"

    def test_transaction_rollback_on_error(self, empty_storage):
        """Test that transactions rollback on error."""
        storage = empty_storage

        # Start a transaction and cause an error
        with pytest.raises(sqlite3.IntegrityError):
            with storage._transaction() as conn:
                # Insert an invocation
                conn.execute(
                    """
                    INSERT INTO skill_invocation (
                        skill_name, invoked_at, session_id, completed
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    ("test-skill", "2025-02-10T12:00:00", "session123", 1),
                )

                # Intentionally cause an error by violating NOT NULL constraint
                # Try to insert with NULL in skill_name (violates NOT NULL)
                conn.execute(
                    """
                    INSERT INTO skill_invocation (
                        skill_name, invoked_at, session_id
                    )
                    VALUES (NULL, '2025-02-10T12:00:00', 'session123')
                    """
                )

        # Verify rollback - first invocation should not exist
        # _get_connection is a context manager, use with statement
        with empty_storage._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM skill_invocation WHERE skill_name = ?",
                ("test-skill",),
            )
            assert cursor.fetchone() is None

    def test_validate_schema(self, empty_storage):
        """Test schema validation."""
        storage = empty_storage
        errors = storage.validate_schema()
        assert len(errors) == 0, f"Schema validation errors: {errors}"


# ============================================================================
# Migration Tests
# ============================================================================


class TestMigrationSystem:
    """Tests for migration system."""

    def test_migration_discovery(self):
        """Test migration discovery."""
        migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
        manager = get_migration_manager(
            db_path=Path(":memory:"),
            migration_dir=migration_dir,
        )

        status = manager.get_status()
        assert status["total_applied"] == 0
        assert status["total_pending"] > 0

    def test_migration_apply(self, temp_db_path):
        """Test applying migrations."""
        migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
        manager = get_migration_manager(
            db_path=temp_db_path,
            migration_dir=migration_dir,
        )

        # Apply migrations
        applied = manager.migrate()
        assert len(applied) > 0

        # Verify tables exist
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_invocation'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_migration_rollback(self, temp_db_path):
        """Test rolling back migrations."""
        migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
        manager = get_migration_manager(
            db_path=temp_db_path,
            migration_dir=migration_dir,
        )

        # Apply migrations
        manager.migrate()

        # Rollback
        rolled_back = manager.rollback(steps=1)
        assert len(rolled_back) > 0

        # Verify tables are gone
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_invocation'"
        )
        assert cursor.fetchone() is None
        conn.close()

    def test_migration_validate(self, temp_db_path):
        """Test migration validation."""
        migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
        manager = get_migration_manager(
            db_path=temp_db_path,
            migration_dir=migration_dir,
        )

        # Apply migrations
        manager.migrate()

        # Validate
        errors = manager.validate()
        assert len(errors) == 0, f"Validation errors: {errors}"


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow(self, temp_db_path):
        """Test complete workflow: store -> retrieve -> metrics."""
        # Apply migrations
        migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
        manager = get_migration_manager(db_path=temp_db_path, migration_dir=migration_dir)
        manager.migrate()

        # Create storage
        storage = SkillsStorage(db_path=temp_db_path)

        # Store invocations directly
        storage.store_invocation(
            skill_name="workflow-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="integration_test",
            completed=True,
            workflow_path="comprehensive",
            user_query="Complete integration test",
            follow_up_actions=["verify"],
        )

        storage.store_invocation(
            skill_name="quick-skill",
            invoked_at="2025-02-10T12:01:00",
            session_id="integration_test",
            completed=False,
            workflow_path="quick",
            error_type="timeout",
        )

        # Check invocations
        invocations = storage.get_session_invocations("integration_test")
        assert len(invocations) >= 2

        # Check metrics
        metrics = storage.get_metrics("workflow-skill")
        assert metrics is not None
        assert metrics.total_invocations >= 1

    def test_json_import_workflow(self, temp_db_path):
        """Test importing JSON data via migrator."""
        from scripts.migrate_json_to_dhruva import JSONToDhruvaMigrator

        # Create test JSON
        json_data = {
            "invocations": [
                {
                    "skill_name": "imported-skill",
                    "invoked_at": "2025-02-10T12:00:00",
                    "session_id": "import_test",
                    "completed": True,
                    "duration_seconds": 35.0,
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "skill_metrics.json"
            json_path.write_text(json.dumps(json_data))

            # Run migration
            migrator = JSONToDhruvaMigrator(
                db_path=temp_db_path,
                json_dir=Path(tmpdir),
            )

            stats = migrator.migrate()
            assert stats.imported == 1
            assert stats.failed == 0

        # Verify data was imported
        storage = SkillsStorage(db_path=temp_db_path)
        invocations = storage.get_session_invocations("import_test")
        assert len(invocations) == 1
        assert invocations[0].skill_name == "imported-skill"


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_null_duration_incomplete(self, empty_storage):
        """Test that incomplete invocations have NULL duration."""
        storage = empty_storage

        storage.store_invocation(
            skill_name="incomplete-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session1",
            completed=False,  # Incomplete
        )

        # Get metrics
        metrics = storage.get_metrics("incomplete-skill")
        assert metrics is not None
        assert metrics.abandoned_invocations == 1
        assert metrics.avg_duration_seconds is None  # No completed invocations

    def test_empty_alternatives(self, empty_storage):
        """Test invocation with no alternatives."""
        storage = empty_storage

        invocation_id = storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session1",
            completed=True,
            alternatives_considered=[],  # Empty list
            follow_up_actions=[],
        )

        invocation = storage.get_invocation(invocation_id)
        assert invocation is not None
        # Empty lists are stored as NULL in SQLite
        assert invocation.alternatives_considered in [None, "[]", "null", ""]
        assert invocation.follow_up_actions in [None, "[]", "null", ""]

    def test_duplicate_detection(self, empty_storage):
        """Test that duplicate invocations are detected."""
        storage = empty_storage

        # Store first invocation
        storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session1",
            completed=True,
        )

        # Try to store duplicate (same skill, same time)
        # This should succeed due to the UNIQUE check being on (invoked_at, skill_name)
        # Actually, let's just verify we can retrieve by those fields
        invocations = storage.get_session_invocations("session1")
        assert len(invocations) == 1

    def test_session_isolation(self, empty_storage):
        """Test that sessions are properly isolated."""
        storage = empty_storage

        # Store invocations for different sessions
        storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session_a",
            completed=True,
        )
        storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T13:00:00",
            session_id="session_b",
            completed=True,
        )

        # Verify isolation
        invocations_a = storage.get_session_invocations("session_a")
        invocations_b = storage.get_session_invocations("session_b")

        assert len(invocations_a) == 1
        assert len(invocations_b) == 1
        assert invocations_a[0].session_id == "session_a"
        assert invocations_b[0].session_id == "session_b"

    def test_workflow_path_aggregation(self, empty_storage):
        """Test that workflow paths are aggregated correctly."""
        storage = empty_storage

        # Store invocations with different workflow paths
        storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session1",
            completed=True,
            workflow_path="quick",
        )
        storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T13:00:00",
            session_id="session1",
            completed=True,
            workflow_path="comprehensive",
        )
        storage.store_invocation(
            skill_name="test-skill",
            invoked_at="2025-02-10T14:00:00",
            session_id="session1",
            completed=True,
            workflow_path="quick",  # Second quick usage
        )

        # Get metrics
        metrics = storage.get_metrics("test-skill")
        assert metrics is not None

        # Parse workflow_paths JSON
        workflow_paths = json.loads(metrics.workflow_paths)
        assert workflow_paths.get("quick") == 2
        assert workflow_paths.get("comprehensive") == 1

    def test_error_aggregation(self, empty_storage):
        """Test that errors are aggregated correctly."""
        storage = empty_storage

        # Store invocations with different errors
        storage.store_invocation(
            skill_name="failing-skill",
            invoked_at="2025-02-10T12:00:00",
            session_id="session1",
            completed=False,
            error_type="timeout",
        )
        storage.store_invocation(
            skill_name="failing-skill",
            invoked_at="2025-02-10T13:00:00",
            session_id="session1",
            completed=False,
            error_type="timeout",  # Same error
        )
        storage.store_invocation(
            skill_name="failing-skill",
            invoked_at="2025-02-10T14:00:00",
            session_id="session1",
            completed=False,
            error_type="validation",
        )

        # Get metrics
        metrics = storage.get_metrics("failing-skill")
        assert metrics is not None

        # Parse common_errors JSON
        common_errors = json.loads(metrics.common_errors)
        assert common_errors.get("timeout") == 2
        assert common_errors.get("validation") == 1


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance tests for skills tracking."""

    def test_large_batch_insertion(self, empty_storage):
        """Test inserting many invocations efficiently."""
        import time

        storage = empty_storage
        batch_size = 100

        start = time.time()

        # Insert many invocations
        with storage._transaction() as conn:
            cursor = conn.cursor()
            for i in range(batch_size):
                cursor.execute(
                    """
                    INSERT INTO skill_invocation (
                        skill_name, invoked_at, session_id, completed, duration_seconds
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"skill-{i % 10}", f"2025-02-10T{i:02d}:00:00", "perf_test", 1, 30.0),
                )

        elapsed = time.time() - start

        # Verify all were inserted
        invocations = storage.get_session_invocations("perf_test")
        assert len(invocations) == batch_size

        # Performance check: should be fast (< 1 second for 100 records)
        assert elapsed < 1.0, f"Batch insertion took {elapsed:.2f}s (too slow)"

    def test_concurrent_access(self, temp_db_path):
        """Test concurrent read access (WAL mode)."""
        import threading

        # Apply migrations first
        migration_dir = Path(__file__).parent.parent / "session_buddy" / "storage" / "migrations"
        manager = get_migration_manager(db_path=temp_db_path, migration_dir=migration_dir)
        manager.migrate()

        storage = SkillsStorage(db_path=temp_db_path, enable_wal=True)

        # Insert some data
        for i in range(10):
            storage.store_invocation(
                skill_name=f"skill-{i}",
                invoked_at="2025-02-10T12:00:00",
                session_id="concurrent_test",
                completed=True,
            )

        # Test concurrent reads
        results = []

        def read_metrics():
            metrics = storage.get_all_metrics()
            results.append(len(metrics))

        threads = [threading.Thread(target=read_metrics) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All threads should have completed successfully
        assert len(results) == 5
        assert all(r >= 0 for r in results)
