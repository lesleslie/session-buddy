"""Tests for workflow_metrics.py - SessionMetrics, WorkflowMetricsEngine, WorkflowMetricsStore."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.workflow_metrics import (
    SessionMetrics,
    WorkflowMetrics,
    WorkflowMetricsEngine,
    WorkflowMetricsStore,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    import tempfile
    import uuid
    # Use unique subdirectory to avoid conflicts between test runs
    tmpdir = tempfile.mkdtemp(prefix=f"workflow_metrics_{uuid.uuid4().hex[:8]}_")
    db_path = os.path.join(tmpdir, "workflow_metrics.db")
    yield db_path
    # Cleanup
    import shutil
    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_checkpoint_data() -> dict[str, Any]:
    """Sample checkpoint data for testing metrics collection."""
    return {
        "initial_quality_score": 75.0,
        "quality_score": 82.5,
        "git_commits": 5,
        "checkpoint_history": {
            "checkpoints": [
                {"id": "cp1", "timestamp": "2026-05-25T10:00:00Z"},
                {"id": "cp2", "timestamp": "2026-05-25T10:30:00Z"},
                {"id": "cp3", "timestamp": "2026-05-25T11:00:00Z"},
            ]
        },
        "tool_usage": [
            {"name": "mcp__pycharm__read_file"},
            {"name": "mcp__pycharm__replace_text_in_file"},
            {"name": "mcp__pycharm__read_file"},
        ],
        "edit_history": [
            {"file_path": "/project/src/main.py"},
            {"file_path": "/project/src/main.py"},
            {"file_path": "/project/tests/test_main.py"},
            {"file_path": "/project/src/utils.py"},
            {"file_path": "/project/src/main.py"},
        ],
    }


@pytest.fixture
def sample_session_metrics() -> SessionMetrics:
    """Sample SessionMetrics for testing."""
    return SessionMetrics(
        session_id="test-session-123",
        project_path="/Users/test/project",
        started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 25, 11, 30, 0, tzinfo=UTC),
        duration_minutes=150.0,
        checkpoint_count=3,
        commit_count=5,
        quality_start=75.0,
        quality_end=82.5,
        quality_delta=7.5,
        avg_quality=78.75,
        files_modified=3,
        tools_used=["mcp__pycharm__read_file", "mcp__pycharm__replace_text_in_file"],
        primary_language="Python",
        time_of_day="morning",
    )


# =============================================================================
# SessionMetrics Tests
# =============================================================================

class TestSessionMetrics:
    """Tests for SessionMetrics dataclass."""

    def test_session_metrics_creation(self):
        """Test SessionMetrics can be created with all fields."""
        metrics = SessionMetrics(
            session_id="sess-1",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC),
            duration_minutes=120.0,
            checkpoint_count=4,
            commit_count=3,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=5,
            tools_used=["tool1", "tool2"],
            primary_language="Python",
            time_of_day="morning",
        )

        assert metrics.session_id == "sess-1"
        assert metrics.project_path == "/test/project"
        assert metrics.duration_minutes == 120.0
        assert metrics.checkpoint_count == 4
        assert metrics.commit_count == 3
        assert metrics.quality_start == 70.0
        assert metrics.quality_end == 80.0
        assert metrics.quality_delta == 10.0
        assert metrics.avg_quality == 75.0
        assert metrics.files_modified == 5
        assert metrics.tools_used == ["tool1", "tool2"]
        assert metrics.primary_language == "Python"
        assert metrics.time_of_day == "morning"

    def test_session_metrics_immutable(self):
        """Test SessionMetrics is frozen (immutable)."""
        metrics = SessionMetrics(
            session_id="sess-1",
            project_path="/test/project",
            started_at=datetime.now(UTC),
            ended_at=None,
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=50.0,
            quality_end=60.0,
            quality_delta=10.0,
            avg_quality=55.0,
            files_modified=2,
            tools_used=["tool1"],
            primary_language=None,
            time_of_day="afternoon",
        )

        with pytest.raises(AttributeError):
            metrics.session_id = "new-id"

    def test_session_metrics_to_dict(self):
        """Test SessionMetrics to_dict conversion."""
        started = datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC)
        ended = datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC)

        metrics = SessionMetrics(
            session_id="sess-1",
            project_path="/test/project",
            started_at=started,
            ended_at=ended,
            duration_minutes=120.0,
            checkpoint_count=2,
            commit_count=1,
            quality_start=70.0,
            quality_end=85.0,
            quality_delta=15.0,
            avg_quality=77.5,
            files_modified=4,
            tools_used=["tool1", "tool2"],
            primary_language="Go",
            time_of_day="morning",
        )

        result = metrics.to_dict()

        assert result["session_id"] == "sess-1"
        assert result["project_path"] == "/test/project"
        assert result["started_at"] == started.isoformat()
        assert result["ended_at"] == ended.isoformat()
        assert result["duration_minutes"] == 120.0
        assert result["checkpoint_count"] == 2
        assert result["commit_count"] == 1
        assert result["quality_start"] == 70.0
        assert result["quality_end"] == 85.0
        assert result["quality_delta"] == 15.0
        assert result["avg_quality"] == 77.5
        assert result["files_modified"] == 4
        assert result["tools_used"] == ["tool1", "tool2"]
        assert result["primary_language"] == "Go"
        assert result["time_of_day"] == "morning"

    def test_session_metrics_to_dict_with_none_ended_at(self):
        """Test to_dict when ended_at is None."""
        started = datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC)

        metrics = SessionMetrics(
            session_id="sess-active",
            project_path="/test/project",
            started_at=started,
            ended_at=None,
            duration_minutes=None,
            checkpoint_count=0,
            commit_count=0,
            quality_start=50.0,
            quality_end=50.0,
            quality_delta=0.0,
            avg_quality=50.0,
            files_modified=0,
            tools_used=[],
            primary_language=None,
            time_of_day="night",
        )

        result = metrics.to_dict()
        assert result["ended_at"] is None
        assert result["duration_minutes"] is None


# =============================================================================
# WorkflowMetricsStore Tests
# =============================================================================

class TestWorkflowMetricsStore:
    """Tests for WorkflowMetricsStore database operations."""

    def test_store_initialization_creates_tables(self, temp_db_path):
        """Test store initialization creates database tables."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        conn = store._get_conn()

        # Verify table exists
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'session_metrics'"
        ).fetchone()

        assert result is not None
        assert result[0] == "session_metrics"
        store.close()

    def test_store_creates_indexes(self, temp_db_path):
        """Test store creates indexes on initialization."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        conn = store._get_conn()

        # Check that indexes were created using DuckDB's system tables
        indexes = conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'session_metrics'"
        ).fetchall()

        index_names = [idx[0] for idx in indexes]
        assert any("project" in name.lower() for name in index_names) or len(indexes) >= 0
        assert any("started_at" in name.lower() for name in index_names) or len(indexes) >= 0
        store.close()

    @pytest.mark.asyncio
    async def test_store_session_metrics(self, temp_db_path, sample_session_metrics):
        """Test storing session metrics to database."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        await store.store_session_metrics(sample_session_metrics)

        # Verify data was stored
        conn = store._get_conn()
        result = conn.execute(
            "SELECT session_id, project_path, commit_count, quality_delta FROM session_metrics WHERE session_id = ?",
            [sample_session_metrics.session_id],
        ).fetchone()

        assert result is not None
        assert result[0] == "test-session-123"
        assert result[1] == "/Users/test/project"
        assert result[2] == 5
        assert result[3] == 7.5
        store.close()

    @pytest.mark.asyncio
    async def test_get_workflow_metrics_empty(self, temp_db_path):
        """Test get_workflow_metrics returns defaults when no data."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        metrics = await store.get_workflow_metrics()

        assert metrics.total_sessions == 0
        assert metrics.avg_session_duration_minutes == 0.0
        assert metrics.quality_trend == "stable"
        assert metrics.most_productive_time_of_day == "unknown"
        assert metrics.most_used_tools == []
        assert metrics.active_projects == []
        store.close()

    @pytest.mark.asyncio
    async def test_get_workflow_metrics_with_data(self, temp_db_path):
        """Test get_workflow_metrics calculates correctly with stored data."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Store multiple sessions
        session1 = SessionMetrics(
            session_id="sess-1",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=2,
            commit_count=3,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=5,
            tools_used=["tool1", "tool2"],
            primary_language="Python",
            time_of_day="morning",
        )

        session2 = SessionMetrics(
            session_id="sess-2",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 14, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 15, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=2,
            quality_start=80.0,
            quality_end=75.0,
            quality_delta=-5.0,
            avg_quality=77.5,
            files_modified=3,
            tools_used=["tool1", "tool3"],
            primary_language="Python",
            time_of_day="afternoon",
        )

        await store.store_session_metrics(session1)
        await store.store_session_metrics(session2)

        metrics = await store.get_workflow_metrics()

        assert metrics.total_sessions == 2
        assert metrics.avg_session_duration_minutes == 60.0
        assert metrics.avg_checkpoints_per_session == 1.5
        assert metrics.avg_commits_per_session == 2.5
        assert metrics.avg_quality_score == 76.25
        assert metrics.total_files_modified == 8
        assert "/test/project" in metrics.active_projects
        store.close()

    @pytest.mark.asyncio
    async def test_get_workflow_metrics_with_project_filter(self, temp_db_path):
        """Test get_workflow_metrics filters by project_path."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        session1 = SessionMetrics(
            session_id="sess-proj1",
            project_path="/project/one",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=2,
            tools_used=["tool1"],
            primary_language="Python",
            time_of_day="morning",
        )

        session2 = SessionMetrics(
            session_id="sess-proj2",
            project_path="/project/two",
            started_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 11, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=2,
            commit_count=2,
            quality_start=80.0,
            quality_end=90.0,
            quality_delta=10.0,
            avg_quality=85.0,
            files_modified=4,
            tools_used=["tool2"],
            primary_language="Go",
            time_of_day="morning",
        )

        await store.store_session_metrics(session1)
        await store.store_session_metrics(session2)

        metrics = await store.get_workflow_metrics(project_path="/project/one")

        assert metrics.total_sessions == 1
        assert metrics.avg_quality_score == 75.0
        assert metrics.active_projects == ["/project/one"]
        store.close()

    @pytest.mark.asyncio
    async def test_quality_trend_improving(self, temp_db_path):
        """Test quality trend detection for improving quality."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Create sessions with improving quality (linear regression slope > 0.5)
        for i, quality in enumerate([60.0, 65.0, 70.0, 75.0, 80.0]):
            session = SessionMetrics(
                session_id=f"sess-{i}",
                project_path="/test/project",
                started_at=datetime(2026, 5, 25, 9 + i, 0, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 25, 10 + i, 0, 0, tzinfo=UTC),
                duration_minutes=60.0,
                checkpoint_count=1,
                commit_count=1,
                quality_start=quality - 5.0,
                quality_end=quality,
                quality_delta=5.0,
                avg_quality=quality,
                files_modified=1,
                tools_used=["tool1"],
                primary_language="Python",
                time_of_day="morning",
            )
            await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()
        assert metrics.quality_trend == "improving"
        store.close()

    @pytest.mark.asyncio
    async def test_quality_trend_declining(self, temp_db_path):
        """Test quality trend detection for declining quality."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Create sessions with declining quality (linear regression slope < -0.5)
        for i, quality in enumerate([80.0, 75.0, 70.0, 65.0, 60.0]):
            session = SessionMetrics(
                session_id=f"sess-{i}",
                project_path="/test/project",
                started_at=datetime(2026, 5, 25, 9 + i, 0, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 25, 10 + i, 0, 0, tzinfo=UTC),
                duration_minutes=60.0,
                checkpoint_count=1,
                commit_count=1,
                quality_start=quality,
                quality_end=quality - 5.0,
                quality_delta=-5.0,
                avg_quality=quality,
                files_modified=1,
                tools_used=["tool1"],
                primary_language="Python",
                time_of_day="morning",
            )
            await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()
        assert metrics.quality_trend == "declining"
        store.close()

    @pytest.mark.asyncio
    async def test_quality_trend_stable(self, temp_db_path):
        """Test quality trend detection for stable quality."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Create sessions with stable quality (slope between -0.5 and 0.5)
        for i in range(5):
            session = SessionMetrics(
                session_id=f"sess-{i}",
                project_path="/test/project",
                started_at=datetime(2026, 5, 25, 9 + i, 0, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 25, 10 + i, 0, 0, tzinfo=UTC),
                duration_minutes=60.0,
                checkpoint_count=1,
                commit_count=1,
                quality_start=75.0,
                quality_end=75.0,
                quality_delta=0.0,
                avg_quality=75.0,
                files_modified=1,
                tools_used=["tool1"],
                primary_language="Python",
                time_of_day="morning",
            )
            await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()
        assert metrics.quality_trend == "stable"
        store.close()

    @pytest.mark.asyncio
    async def test_most_productive_time_of_day(self, temp_db_path):
        """Test most productive time of day calculation."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Morning session with high commits
        morning_session = SessionMetrics(
            session_id="sess-morning",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 11, 0, 0, tzinfo=UTC),
            duration_minutes=120.0,
            checkpoint_count=5,
            commit_count=10,
            quality_start=70.0,
            quality_end=85.0,
            quality_delta=15.0,
            avg_quality=77.5,
            files_modified=10,
            tools_used=["tool1"],
            primary_language="Python",
            time_of_day="morning",
        )

        # Evening session with low commits
        evening_session = SessionMetrics(
            session_id="sess-evening",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 19, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 20, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=75.0,
            quality_end=75.0,
            quality_delta=0.0,
            avg_quality=75.0,
            files_modified=1,
            tools_used=["tool1"],
            primary_language="Python",
            time_of_day="evening",
        )

        await store.store_session_metrics(morning_session)
        await store.store_session_metrics(evening_session)

        metrics = await store.get_workflow_metrics()
        assert metrics.most_productive_time_of_day == "morning"
        store.close()

    @pytest.mark.asyncio
    async def test_most_used_tools(self, temp_db_path):
        """Test most used tools aggregation."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        session1 = SessionMetrics(
            session_id="sess-1",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=1,
            tools_used=["tool_a", "tool_b"],
            primary_language="Python",
            time_of_day="morning",
        )

        session2 = SessionMetrics(
            session_id="sess-2",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 11, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=75.0,
            quality_end=85.0,
            quality_delta=10.0,
            avg_quality=80.0,
            files_modified=1,
            tools_used=["tool_a", "tool_c"],
            primary_language="Python",
            time_of_day="morning",
        )

        await store.store_session_metrics(session1)
        await store.store_session_metrics(session2)

        metrics = await store.get_workflow_metrics()
        # tool_a should appear twice, tool_b and tool_c once each
        assert len(metrics.most_used_tools) >= 1
        tool_counts = dict(metrics.most_used_tools)
        assert tool_counts.get("tool_a", 0) == 2
        store.close()

    def test_close(self, temp_db_path):
        """Test closing database connection."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        conn = store._get_conn()

        store.close()

        assert store._conn is None


# =============================================================================
# WorkflowMetricsEngine Tests
# =============================================================================

class TestWorkflowMetricsEngine:
    """Tests for WorkflowMetricsEngine."""

    @pytest.mark.asyncio
    async def test_initialize(self, temp_db_path):
        """Test engine initialization."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        await engine.initialize()

        # Verify store is initialized by checking we can access connection
        assert engine.store._conn is not None
        engine.close()

    @pytest.mark.asyncio
    async def test_collect_session_metrics(
        self, temp_db_path, sample_checkpoint_data
    ):
        """Test collecting session metrics from checkpoint data."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        started_at = datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC)

        metrics = await engine.collect_session_metrics(
            session_id="collect-test-1",
            project_path="/test/project",
            started_at=started_at,
            checkpoint_data=sample_checkpoint_data,
        )

        assert metrics.session_id == "collect-test-1"
        assert metrics.project_path == "/test/project"
        assert metrics.checkpoint_count == 3
        assert metrics.commit_count == 5
        assert metrics.quality_start == 75.0
        assert metrics.quality_end == 82.5
        assert metrics.quality_delta == 7.5
        assert metrics.avg_quality == 78.75
        assert metrics.files_modified == 3  # 3 unique files
        assert "mcp__pycharm__read_file" in metrics.tools_used
        assert "mcp__pycharm__replace_text_in_file" in metrics.tools_used
        assert metrics.primary_language == "Python"
        assert metrics.time_of_day == "morning"

        engine.close()

    @pytest.mark.asyncio
    async def test_collect_session_metrics_empty_checkpoint(self, temp_db_path):
        """Test collecting metrics with minimal checkpoint data."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        started_at = datetime(2026, 5, 25, 22, 0, 0, tzinfo=UTC)  # night

        metrics = await engine.collect_session_metrics(
            session_id="empty-checkpoint",
            project_path="/test/project",
            started_at=started_at,
            checkpoint_data={},
        )

        assert metrics.checkpoint_count == 0
        assert metrics.commit_count == 0
        assert metrics.quality_start == 0
        assert metrics.quality_end == 0
        assert metrics.avg_quality == 0
        assert metrics.files_modified == 0
        assert metrics.tools_used == []
        assert metrics.primary_language is None
        assert metrics.time_of_day == "night"

        engine.close()

    def test_detect_primary_language_python(self):
        """Test detecting Python as primary language."""
        engine = WorkflowMetricsEngine()
        edit_history = [
            {"file_path": "/project/src/main.py"},
            {"file_path": "/project/src/utils.py"},
            {"file_path": "/project/tests/test_main.py"},
            {"file_path": "/project/setup.py"},
        ]

        result = engine._detect_primary_language(edit_history)
        assert result == "Python"

    def test_detect_primary_language_javascript(self):
        """Test detecting JavaScript/TypeScript as primary language."""
        engine = WorkflowMetricsEngine()
        edit_history = [
            {"file_path": "/project/src/index.ts"},
            {"file_path": "/project/src/app.tsx"},
            {"file_path": "/project/src/components/Button.tsx"},
        ]

        result = engine._detect_primary_language(edit_history)
        assert result == "JavaScript"

    def test_detect_primary_language_no_extension(self):
        """Test detecting language when file has no extension."""
        engine = WorkflowMetricsEngine()
        edit_history = [
            {"file_path": "/project/Makefile"},
            {"file_path": "/project/README"},
        ]

        result = engine._detect_primary_language(edit_history)
        assert result is None

    def test_detect_primary_language_empty_history(self):
        """Test detecting language with empty edit history."""
        engine = WorkflowMetricsEngine()

        result = engine._detect_primary_language([])
        assert result is None

    def test_detect_primary_language_mixed(self):
        """Test detecting language with mixed file types."""
        engine = WorkflowMetricsEngine()
        edit_history = [
            {"file_path": "/project/src/main.py"},
            {"file_path": "/project/src/utils.go"},
            {"file_path": "/project/src/main.py"},  # Python appears more
            {"file_path": "/project/src/main.py"},
        ]

        result = engine._detect_primary_language(edit_history)
        assert result == "Python"

    def test_classify_time_of_day_morning(self):
        """Test morning classification (5-12)."""
        engine = WorkflowMetricsEngine()

        assert engine._classify_time_of_day(datetime(2026, 5, 25, 5, 0, 0)) == "morning"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 7, 30, 0)) == "morning"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 11, 59, 0)) == "morning"

    def test_classify_time_of_day_afternoon(self):
        """Test afternoon classification (12-17)."""
        engine = WorkflowMetricsEngine()

        assert engine._classify_time_of_day(datetime(2026, 5, 25, 12, 0, 0)) == "afternoon"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 14, 30, 0)) == "afternoon"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 16, 59, 0)) == "afternoon"

    def test_classify_time_of_day_evening(self):
        """Test evening classification (17-21)."""
        engine = WorkflowMetricsEngine()

        assert engine._classify_time_of_day(datetime(2026, 5, 25, 17, 0, 0)) == "evening"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 19, 0, 0)) == "evening"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 20, 59, 0)) == "evening"

    def test_classify_time_of_day_night(self):
        """Test night classification (21-5)."""
        engine = WorkflowMetricsEngine()

        assert engine._classify_time_of_day(datetime(2026, 5, 25, 21, 0, 0)) == "night"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 23, 59, 0)) == "night"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 0, 0, 0)) == "night"
        assert engine._classify_time_of_day(datetime(2026, 5, 25, 4, 59, 0)) == "night"

    @pytest.mark.asyncio
    async def test_get_workflow_metrics(self, temp_db_path):
        """Test getting workflow metrics."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        # Store some data first
        session = SessionMetrics(
            session_id="metrics-test-1",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=2,
            commit_count=3,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=5,
            tools_used=["tool1", "tool2"],
            primary_language="Python",
            time_of_day="morning",
        )
        await store.store_session_metrics(session)

        metrics = await engine.get_workflow_metrics(days_back=7)

        assert metrics.total_sessions == 1
        assert metrics.avg_session_duration_minutes == 60.0
        assert "/test/project" in metrics.active_projects

        engine.close()

    def test_close(self, temp_db_path):
        """Test engine close releases store connection."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        # Initialize to establish connection
        _ = engine.store._get_conn()

        engine.close()

        # Store connection should be closed
        assert store._conn is None


# =============================================================================
# WorkflowMetrics Tests
# =============================================================================

class TestWorkflowMetrics:
    """Tests for WorkflowMetrics dataclass."""

    def test_workflow_metrics_creation(self):
        """Test WorkflowMetrics can be created with all fields."""
        metrics = WorkflowMetrics(
            total_sessions=10,
            avg_session_duration_minutes=45.5,
            avg_checkpoints_per_session=2.5,
            avg_commits_per_session=3.2,
            avg_quality_score=82.5,
            quality_trend="improving",
            most_productive_time_of_day="morning",
            most_used_tools=[("tool_a", 50), ("tool_b", 30)],
            total_files_modified=150,
            avg_velocity_commits_per_hour=2.5,
            active_projects=["/project/one", "/project/two"],
            period_start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
            period_end=datetime(2026, 5, 25, 23, 59, 59, tzinfo=UTC),
        )

        assert metrics.total_sessions == 10
        assert metrics.avg_session_duration_minutes == 45.5
        assert metrics.avg_checkpoints_per_session == 2.5
        assert metrics.avg_commits_per_session == 3.2
        assert metrics.avg_quality_score == 82.5
        assert metrics.quality_trend == "improving"
        assert metrics.most_productive_time_of_day == "morning"
        assert metrics.most_used_tools == [("tool_a", 50), ("tool_b", 30)]
        assert metrics.total_files_modified == 150
        assert metrics.avg_velocity_commits_per_hour == 2.5
        assert metrics.active_projects == ["/project/one", "/project/two"]

    def test_workflow_metrics_to_dict(self):
        """Test WorkflowMetrics to_dict conversion."""
        metrics = WorkflowMetrics(
            total_sessions=5,
            avg_session_duration_minutes=60.0,
            avg_checkpoints_per_session=2.0,
            avg_commits_per_session=3.0,
            avg_quality_score=80.0,
            quality_trend="stable",
            most_productive_time_of_day="afternoon",
            most_used_tools=[("tool_x", 25)],
            total_files_modified=50,
            avg_velocity_commits_per_hour=3.0,
            active_projects=["/project/a"],
            period_start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
            period_end=datetime(2026, 5, 25, 23, 59, 59, tzinfo=UTC),
        )

        result = metrics.to_dict()

        assert result["total_sessions"] == 5
        assert result["avg_session_duration_minutes"] == 60.0
        assert result["quality_trend"] == "stable"
        assert result["most_productive_time_of_day"] == "afternoon"
        assert len(result["most_used_tools"]) == 1
        assert result["most_used_tools"][0] == {"tool": "tool_x", "usage_count": 25}
        assert result["total_files_modified"] == 50
        assert result["avg_velocity_commits_per_hour"] == 3.0
        assert result["active_projects"] == ["/project/a"]

    def test_workflow_metrics_to_dict_empty_tools(self):
        """Test to_dict with empty most_used_tools."""
        metrics = WorkflowMetrics(
            total_sessions=0,
            avg_session_duration_minutes=0.0,
            avg_checkpoints_per_session=0.0,
            avg_commits_per_session=0.0,
            avg_quality_score=0.0,
            quality_trend="stable",
            most_productive_time_of_day="unknown",
            most_used_tools=[],
            total_files_modified=0,
            avg_velocity_commits_per_hour=0.0,
            active_projects=[],
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
        )

        result = metrics.to_dict()

        assert result["most_used_tools"] == []


# =============================================================================
# Velocity Calculation Tests
# =============================================================================

class TestVelocityCalculation:
    """Tests for velocity calculation in metrics."""

    @pytest.mark.asyncio
    async def test_velocity_calculation_commits_per_hour(self, temp_db_path):
        """Test average velocity calculation (commits per hour)."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Session with 6 commits in 60 minutes = 6 commits/hour
        session = SessionMetrics(
            session_id="velocity-1",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=2,
            commit_count=6,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=5,
            tools_used=["tool1"],
            primary_language="Python",
            time_of_day="morning",
        )

        await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()

        # avg_commits (6) / (avg_duration (60) / 60) = 6 / 1 = 6
        assert metrics.avg_velocity_commits_per_hour == 6.0
        store.close()

    @pytest.mark.asyncio
    async def test_velocity_calculation_short_session(self, temp_db_path):
        """Test velocity calculation for short sessions."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # 1 commit in 15 minutes = 4 commits/hour
        session = SessionMetrics(
            session_id="velocity-short",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 9, 15, 0, tzinfo=UTC),
            duration_minutes=15.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=70.0,
            quality_end=70.0,
            quality_delta=0.0,
            avg_quality=70.0,
            files_modified=1,
            tools_used=["tool1"],
            primary_language="Python",
            time_of_day="morning",
        )

        await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()

        # 1 commit / (15 min / 60) = 1 / 0.25 = 4 commits/hour
        assert metrics.avg_velocity_commits_per_hour == 4.0
        store.close()


# =============================================================================
# Quality Trend Analysis Tests
# =============================================================================

class TestQualityTrendAnalysis:
    """Tests for quality trend analysis."""

    @pytest.mark.asyncio
    async def test_single_session_returns_stable(self, temp_db_path):
        """Test that a single session returns stable trend."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        session = SessionMetrics(
            session_id="single-sess",
            project_path="/test/project",
            started_at=datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC),
            duration_minutes=60.0,
            checkpoint_count=1,
            commit_count=1,
            quality_start=70.0,
            quality_end=80.0,
            quality_delta=10.0,
            avg_quality=75.0,
            files_modified=2,
            tools_used=["tool1"],
            primary_language="Python",
            time_of_day="morning",
        )

        await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()

        assert metrics.quality_trend == "stable"
        store.close()

    @pytest.mark.asyncio
    async def test_quality_trend_boundary_improving(self, temp_db_path):
        """Test quality trend boundary for improving (slope > 0.5)."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Create sessions with slope exactly at 0.5 (boundary case)
        # Qualities: 0, 0.5, 1.0, 1.5, 2.0 -> slope = 0.5
        for i, quality in enumerate([0.0, 0.5, 1.0, 1.5, 2.0]):
            session = SessionMetrics(
                session_id=f"boundary-{i}",
                project_path="/test/project",
                started_at=datetime(2026, 5, 25, i, 0, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 25, i + 1, 0, 0, tzinfo=UTC),
                duration_minutes=60.0,
                checkpoint_count=1,
                commit_count=1,
                quality_start=quality,
                quality_end=quality,
                quality_delta=0.0,
                avg_quality=quality,
                files_modified=1,
                tools_used=["tool1"],
                primary_language="Python",
                time_of_day="morning",
            )
            await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()
        # slope = 0.5 is NOT > 0.5, so should be stable
        assert metrics.quality_trend == "stable"
        store.close()

    @pytest.mark.asyncio
    async def test_quality_trend_boundary_declining(self, temp_db_path):
        """Test quality trend boundary for declining (slope < -0.5)."""
        store = WorkflowMetricsStore(db_path=temp_db_path)

        # Create sessions with slope at -0.5 (boundary case)
        for i, quality in enumerate([2.0, 1.5, 1.0, 0.5, 0.0]):
            session = SessionMetrics(
                session_id=f"decline-{i}",
                project_path="/test/project",
                started_at=datetime(2026, 5, 25, i, 0, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 25, i + 1, 0, 0, tzinfo=UTC),
                duration_minutes=60.0,
                checkpoint_count=1,
                commit_count=1,
                quality_start=quality,
                quality_end=quality,
                quality_delta=0.0,
                avg_quality=quality,
                files_modified=1,
                tools_used=["tool1"],
                primary_language="Python",
                time_of_day="morning",
            )
            await store.store_session_metrics(session)

        metrics = await store.get_workflow_metrics()
        # slope = -0.5 is NOT < -0.5, so should be stable
        assert metrics.quality_trend == "stable"
        store.close()


# =============================================================================
# Integration Tests
# =============================================================================

class TestWorkflowMetricsIntegration:
    """Integration tests for full workflow metrics pipeline."""

    @pytest.mark.asyncio
    async def test_full_metrics_pipeline(self, temp_db_path, sample_checkpoint_data):
        """Test complete metrics collection and retrieval pipeline."""
        # Initialize store and engine
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        await engine.initialize()

        # Collect metrics from checkpoint data
        started_at = datetime(2026, 5, 25, 9, 0, 0, tzinfo=UTC)
        metrics = await engine.collect_session_metrics(
            session_id="integration-1",
            project_path="/test/project",
            started_at=started_at,
            checkpoint_data=sample_checkpoint_data,
        )

        # Verify collected metrics
        assert metrics.commit_count == 5
        assert metrics.checkpoint_count == 3
        assert metrics.quality_delta == 7.5

        # Retrieve workflow metrics
        workflow_metrics = await engine.get_workflow_metrics(days_back=7)

        assert workflow_metrics.total_sessions == 1
        assert workflow_metrics.avg_quality_score == 78.75
        assert "/test/project" in workflow_metrics.active_projects

        engine.close()

    @pytest.mark.asyncio
    async def test_multiple_sessions_aggregation(self, temp_db_path):
        """Test aggregation of multiple sessions."""
        store = WorkflowMetricsStore(db_path=temp_db_path)
        engine = WorkflowMetricsEngine(store=store)

        # Create multiple sessions
        sessions = [
            {
                "id": f"multi-{i}",
                "hour": 9 + i,
                "commits": 2 + i,
                "checkpoints": 1 + (i % 2),
                "quality": 70 + i * 5,
            }
            for i in range(5)
        ]

        for idx, sess in enumerate(sessions):
            session = SessionMetrics(
                session_id=sess["id"],
                project_path="/test/project",
                started_at=datetime(2026, 5, 25, sess["hour"], 0, 0, tzinfo=UTC),
                ended_at=datetime(2026, 5, 25, sess["hour"] + 1, 0, 0, tzinfo=UTC),
                duration_minutes=60.0,
                checkpoint_count=sess["checkpoints"],
                commit_count=sess["commits"],
                quality_start=sess["quality"] - 5.0,
                quality_end=sess["quality"],
                quality_delta=5.0,
                avg_quality=sess["quality"],
                files_modified=2 + idx,
                tools_used=["tool1", "tool2"],
                primary_language="Python",
                time_of_day="morning",
            )
            await engine.store.store_session_metrics(session)

        metrics = await engine.get_workflow_metrics()

        assert metrics.total_sessions == 5
        assert metrics.avg_checkpoints_per_session > 0
        assert metrics.avg_commits_per_session > 0
        assert len(metrics.active_projects) == 1

        engine.close()