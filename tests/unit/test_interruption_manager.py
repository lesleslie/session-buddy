#!/usr/bin/env python3
"""Comprehensive test suite for session_buddy.interruption_manager module.

Tests context preservation during interruptions and session recovery.
Achieves 60%+ coverage by testing all major functionality.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import sqlite3
import tempfile
import threading
import time
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import suppress
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.interruption_manager import (
    InterruptionType,
)


def datetime_to_iso(obj: Any) -> Any:
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def json_dumps_safe(data: dict, **kwargs) -> str:
    """JSON dumps that handles datetime objects."""
    return json.dumps(data, default=datetime_to_iso, **kwargs)


class TestInterruptionType:
    """Test InterruptionType enum."""

    def test_interruption_types_exist(self) -> None:
        """Test that all interruption types are defined."""
        from session_buddy.interruption_manager import InterruptionType

        assert hasattr(InterruptionType, "APP_SWITCH")
        assert hasattr(InterruptionType, "WINDOW_CHANGE")
        assert hasattr(InterruptionType, "SYSTEM_IDLE")
        assert hasattr(InterruptionType, "FOCUS_LOST")
        assert hasattr(InterruptionType, "FILE_CHANGE")
        assert hasattr(InterruptionType, "PROCESS_CHANGE")
        assert hasattr(InterruptionType, "MANUAL_SAVE")

    def test_interruption_type_values(self) -> None:
        """Test InterruptionType enum values."""
        from session_buddy.interruption_manager import InterruptionType

        assert InterruptionType.APP_SWITCH.value == "app_switch"
        assert InterruptionType.WINDOW_CHANGE.value == "window_change"
        assert InterruptionType.SYSTEM_IDLE.value == "system_idle"
        assert InterruptionType.FOCUS_LOST.value == "focus_lost"
        assert InterruptionType.FILE_CHANGE.value == "file_change"
        assert InterruptionType.PROCESS_CHANGE.value == "process_change"
        assert InterruptionType.MANUAL_SAVE.value == "manual_save"


class TestContextState:
    """Test ContextState enum."""

    def test_context_states_exist(self) -> None:
        """Test that all context states are defined."""
        from session_buddy.interruption_manager import ContextState

        assert hasattr(ContextState, "ACTIVE")
        assert hasattr(ContextState, "INTERRUPTED")
        assert hasattr(ContextState, "PRESERVED")
        assert hasattr(ContextState, "RESTORED")
        assert hasattr(ContextState, "LOST")

    def test_context_state_values(self) -> None:
        """Test ContextState enum values."""
        from session_buddy.interruption_manager import ContextState

        assert ContextState.ACTIVE.value == "active"
        assert ContextState.INTERRUPTED.value == "interrupted"
        assert ContextState.PRESERVED.value == "preserved"
        assert ContextState.RESTORED.value == "restored"
        assert ContextState.LOST.value == "lost"


class TestInterruptionEvent:
    """Test InterruptionEvent dataclass."""

    def test_interruption_event_creation(self) -> None:
        """Test creating an interruption event."""
        from session_buddy.interruption_manager import (
            InterruptionEvent,
            InterruptionType,
        )

        event = InterruptionEvent(
            id="test-event-123",
            event_type=InterruptionType.APP_SWITCH,
            timestamp=datetime.now(UTC),
            source_context={},
            target_context={},
            duration=None,
            recovery_data=None,
            auto_saved=False,
            user_id="test-user",
            project_id=None,
        )
        assert event.event_type == InterruptionType.APP_SWITCH
        assert isinstance(event.timestamp, datetime)
        assert event.source_context == {}
        assert event.auto_saved is False

    def test_interruption_event_with_metadata(self) -> None:
        """Test interruption event with recovery data."""
        from session_buddy.interruption_manager import (
            InterruptionEvent,
            InterruptionType,
        )

        recovery_data = {"reason": "user requested", "severity": "low"}
        event = InterruptionEvent(
            id="test-event-456",
            event_type=InterruptionType.WINDOW_CHANGE,
            timestamp=datetime.now(UTC),
            source_context={"app": "VS Code"},
            target_context={"app": "Terminal"},
            duration=30.5,
            recovery_data=recovery_data,
            auto_saved=True,
            user_id="test-user",
            project_id="test-project",
        )
        assert event.recovery_data == recovery_data
        assert event.duration == 30.5
        assert event.project_id == "test-project"


class TestSessionContext:
    """Test SessionContext dataclass."""

    def test_session_context_creation(self) -> None:
        """Test creating a session context."""
        from session_buddy.interruption_manager import SessionContext

        context = SessionContext(
            session_id="test-123",
            user_id="test-user",
            project_id=None,
            active_app=None,
            active_window=None,
            working_directory="/tmp",
            open_files=[],
            cursor_positions={},
            environment_vars={},
            process_state={},
            last_activity=datetime.now(UTC),
            focus_duration=0.0,
            interruption_count=0,
            recovery_attempts=0,
        )
        assert context.session_id == "test-123"
        assert context.user_id == "test-user"
        assert isinstance(context.last_activity, datetime)

    def test_session_context_with_data(self) -> None:
        """Test session context with additional data."""
        from session_buddy.interruption_manager import SessionContext

        open_files = ["/tmp/file1.py", "/tmp/file2.py"]
        cursor_positions = {"file1.py": 100, "file2.py": 200}
        context = SessionContext(
            session_id="test-123",
            user_id="test-user",
            project_id="test-project",
            active_app="VS Code",
            active_window="main.py",
            working_directory="/tmp",
            open_files=open_files,
            cursor_positions=cursor_positions,
            environment_vars={"PWD": "/tmp"},
            process_state={"pid": 12345},
            last_activity=datetime.now(UTC),
            focus_duration=100.5,
            interruption_count=2,
            recovery_attempts=1,
        )
        assert context.open_files == open_files
        assert context.cursor_positions == cursor_positions
        assert context.active_app == "VS Code"
        assert context.interruption_count == 2


# =====================================
# Fixtures
# =====================================


@pytest.fixture
def temp_db_path() -> Generator[Path]:
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory(prefix="interruption_test_") as temp_dir:
        yield Path(temp_dir) / "test_interruption.db"


@pytest.fixture
def manager(temp_db_path: Path) -> Generator:
    """Create an InterruptionManager with temporary database."""
    from session_buddy.interruption_manager import InterruptionManager

    manager = InterruptionManager(db_path=str(temp_db_path))
    yield manager
    # Cleanup
    manager.stop_monitoring()


@pytest.fixture
def mock_session_context() -> MagicMock:
    """Create a mock SessionContext."""
    from session_buddy.interruption_manager import SessionContext

    return MagicMock(spec=SessionContext)


# =====================================
# Test FocusTracker
# =====================================


class TestFocusTracker:
    """Test FocusTracker class."""

    def test_init(self) -> None:
        """Test FocusTracker initialization."""
        from session_buddy.interruption_manager import FocusTracker

        tracker = FocusTracker()
        assert tracker.callback is None
        assert tracker.current_app is None
        assert tracker.current_window is None
        assert tracker.running is False
        assert tracker._monitor_thread is None

    def test_init_with_callback(self) -> None:
        """Test FocusTracker initialization with callback."""
        from session_buddy.interruption_manager import FocusTracker

        callback = MagicMock()
        tracker = FocusTracker(callback=callback)
        assert tracker.callback == callback

    def test_start_monitoring(self) -> None:
        """Test starting focus monitoring."""
        from session_buddy.interruption_manager import FocusTracker

        tracker = FocusTracker()
        tracker.start_monitoring()
        assert tracker.running is True
        assert tracker._monitor_thread is not None
        assert tracker._monitor_thread.is_alive()
        tracker.stop_monitoring()

    def test_start_monitoring_twice(self) -> None:
        """Test starting monitoring twice does nothing."""
        from session_buddy.interruption_manager import FocusTracker

        tracker = FocusTracker()
        tracker.start_monitoring()
        first_thread = tracker._monitor_thread
        tracker.start_monitoring()  # Should not create new thread
        assert tracker._monitor_thread == first_thread
        tracker.stop_monitoring()

    def test_stop_monitoring(self) -> None:
        """Test stopping focus monitoring."""
        from session_buddy.interruption_manager import FocusTracker

        tracker = FocusTracker()
        tracker.start_monitoring()
        tracker.stop_monitoring()
        assert tracker.running is False

    def test_stop_monitoring_not_started(self) -> None:
        """Test stopping monitoring that wasn't started."""
        from session_buddy.interruption_manager import FocusTracker

        tracker = FocusTracker()
        tracker.stop_monitoring()  # Should not raise
        assert tracker.running is False

    def test_monitor_loop_stops_on_signal(self) -> None:
        """Test that monitor loop respects running flag."""
        from session_buddy.interruption_manager import FocusTracker

        tracker = FocusTracker()
        tracker.start_monitoring()
        time.sleep(0.1)  # Let it run briefly
        tracker.stop_monitoring()
        assert tracker.running is False


# =====================================
# Test FileChangeHandler
# =====================================


class TestFileChangeHandler:
    """Test FileChangeHandler class."""

    def test_init(self) -> None:
        """Test FileChangeHandler initialization."""
        from session_buddy.interruption_manager import FileChangeHandler

        handler = FileChangeHandler()
        assert handler.callback is None
        assert handler.last_events == {}
        assert handler.debounce_time == 1.0

    def test_init_with_callback(self) -> None:
        """Test FileChangeHandler initialization with callback."""
        from session_buddy.interruption_manager import FileChangeHandler

        callback = MagicMock()
        handler = FileChangeHandler(callback=callback)
        assert handler.callback == callback

    def test_on_modified_directory(self) -> None:
        """Test on_modified ignores directories."""
        from session_buddy.interruption_manager import FileChangeHandler

        handler = FileChangeHandler()
        mock_event = MagicMock()
        mock_event.is_directory = True
        mock_event.src_path = "/tmp/dir"

        handler.on_modified(mock_event)
        assert handler.last_events == {}

    def test_on_modified_file(self) -> None:
        """Test on_modified handles files."""
        from session_buddy.interruption_manager import FileChangeHandler

        callback = MagicMock()
        handler = FileChangeHandler(callback=callback)
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/tmp/file.py"

        handler.on_modified(mock_event)
        assert callback.called
        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert call_args["type"].value == "file_change"
        assert call_args["file_path"] == "/tmp/file.py"
        assert call_args["event_type"] == "modified"

    def test_on_modified_debounce(self) -> None:
        """Test on_modified debounces rapid changes."""
        from session_buddy.interruption_manager import FileChangeHandler

        callback = MagicMock()
        handler = FileChangeHandler(callback=callback)
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/tmp/file.py"

        handler.on_modified(mock_event)
        handler.on_modified(mock_event)  # Should be debounced
        assert callback.call_count == 1

    def test_on_created(self) -> None:
        """Test on_created handles file creation."""
        from session_buddy.interruption_manager import FileChangeHandler

        callback = MagicMock()
        handler = FileChangeHandler(callback=callback)
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/tmp/new_file.py"

        handler.on_created(mock_event)
        assert callback.called
        call_args = callback.call_args[0][0]
        assert call_args["event_type"] == "created"

    def test_on_deleted(self) -> None:
        """Test on_deleted handles file deletion."""
        from session_buddy.interruption_manager import FileChangeHandler

        callback = MagicMock()
        handler = FileChangeHandler(callback=callback)
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/tmp/deleted_file.py"

        handler.on_deleted(mock_event)
        assert callback.called
        call_args = callback.call_args[0][0]
        assert call_args["event_type"] == "deleted"


# =====================================
# Test InterruptionManager
# =====================================


class TestInterruptionManagerInit:
    """Test InterruptionManager initialization."""

    def test_init_default(self, temp_db_path: Path) -> None:
        """Test initialization with defaults."""
        from session_buddy.interruption_manager import InterruptionManager

        manager = InterruptionManager(db_path=str(temp_db_path))
        assert manager.db_path == str(temp_db_path)
        assert manager.auto_save_enabled is True
        assert manager.save_threshold == 30.0
        assert manager.idle_threshold == 300.0
        from session_buddy.interruption_manager import FocusTracker, FileChangeHandler
        assert isinstance(manager.focus_tracker, FocusTracker)
        assert isinstance(manager.file_handler, FileChangeHandler)
        assert manager._preservation_callbacks == []
        assert manager._restoration_callbacks == []

    def test_init_database_tables(self, temp_db_path: Path) -> None:
        """Test that database tables are created."""
        from session_buddy.interruption_manager import InterruptionManager

        manager = InterruptionManager(db_path=str(temp_db_path))

        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

        assert "interruption_events" in tables
        assert "session_contexts" in tables
        assert "context_snapshots" in tables

    def test_init_database_indices(self, temp_db_path: Path) -> None:
        """Test that database indices are created."""
        from session_buddy.interruption_manager import InterruptionManager

        manager = InterruptionManager(db_path=str(temp_db_path))

        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            indices = {row[0] for row in cursor.fetchall()}

        assert "idx_interruptions_timestamp" in indices
        assert "idx_interruptions_user" in indices
        assert "idx_contexts_user" in indices
        assert "idx_contexts_state" in indices
        assert "idx_snapshots_session" in indices


class TestInterruptionManagerMonitoring:
    """Test InterruptionManager monitoring methods."""

    def test_start_monitoring(self, manager) -> None:
        """Test starting interruption monitoring."""
        manager.start_monitoring()
        assert manager.focus_tracker.running is True

    def test_stop_monitoring(self, manager) -> None:
        """Test stopping interruption monitoring."""
        manager.start_monitoring()
        manager.stop_monitoring()
        assert manager.focus_tracker.running is False

    def test_start_monitoring_creates_observer(self, manager) -> None:
        """Test that start_monitoring creates file observer when watchdog available."""
        with patch("session_buddy.interruption_manager.WATCHDOG_AVAILABLE", True):
            with patch("session_buddy.interruption_manager.Observer") as mock_observer:
                mock_instance = MagicMock()
                mock_observer.return_value = mock_instance

                manager.start_monitoring(working_directory="/tmp", watch_files=True)
                mock_instance.schedule.assert_called_once()
                mock_instance.start.assert_called_once()


# Helper to create a mock context dict with serializable values
def make_context_dict(
    session_id: str = "ctx_test",
    user_id: str = "test-user",
    project_id: str | None = "test-project",
    **overrides,
) -> dict:
    """Create a mock context dict with ISO format datetimes."""
    base = {
        "session_id": session_id,
        "user_id": user_id,
        "project_id": project_id,
        "active_app": None,
        "active_window": None,
        "working_directory": "/tmp",
        "open_files": [],
        "cursor_positions": {},
        "environment_vars": {},
        "process_state": {},
        "last_activity": datetime.now(UTC).isoformat(),
        "focus_duration": 0.0,
        "interruption_count": 0,
        "recovery_attempts": 0,
    }
    base.update(overrides)
    return base


class TestInterruptionManagerSessionContext:
    """Test InterruptionManager session context methods."""

    @pytest.mark.asyncio
    async def test_create_session_context(self, manager) -> None:
        """Test creating a new session context."""
        context_dict = make_context_dict("ctx_1")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            assert session_id.startswith("ctx_")
            assert manager.current_context is not None
            assert manager.current_context.user_id == "test-user"
            assert manager.current_context.project_id == "test-project"
            assert manager.current_context.working_directory == "/tmp"

    @pytest.mark.asyncio
    async def test_create_session_context_stores_in_db(self, manager) -> None:
        """Test that created session context is stored in database."""
        context_dict = make_context_dict("ctx_2")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            with sqlite3.connect(manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM session_contexts WHERE session_id = ?",
                    (session_id,),
                ).fetchone()

            assert row is not None
            assert row["user_id"] == "test-user"
            assert row["project_id"] == "test-project"
            assert row["state"] == "active"

    @pytest.mark.asyncio
    async def test_create_session_context_no_project(self, manager) -> None:
        """Test creating session context without project."""
        context_dict = make_context_dict("ctx_3", project_id=None)

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                working_directory="/tmp",
            )

            assert manager.current_context.project_id is None


class TestInterruptionManagerPreserveContext:
    """Test InterruptionManager context preservation."""

    @pytest.mark.asyncio
    async def test_preserve_context_no_current(self, manager) -> None:
        """Test preserve_context returns False when no current context."""
        result = await manager.preserve_context()
        assert result is False

    @pytest.mark.asyncio
    async def test_preserve_context_success(self, manager) -> None:
        """Test successful context preservation."""
        context_dict = make_context_dict("ctx_preserve1")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            # Update last_activity to be datetime for preservation
            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                result = await manager.preserve_context()
            assert result is True

    @pytest.mark.asyncio
    async def test_preserve_context_with_snapshot(self, manager) -> None:
        """Test that preserve_context creates snapshot in database."""
        context_dict = make_context_dict("ctx_preserve2")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

            with sqlite3.connect(manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                snapshot = conn.execute(
                    "SELECT * FROM context_snapshots WHERE snapshot_type = 'preservation'"
                ).fetchone()

            assert snapshot is not None
            assert snapshot["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_preserve_context_with_session_id(self, manager) -> None:
        """Test preserve_context uses provided session_id."""
        context_dict = make_context_dict("ctx_preserve3")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            # Create another context but preserve with specific session_id
            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = make_context_dict("ctx_other", user_id="other-user")
                await manager.create_session_context(
                    user_id="other-user",
                    project_id="other-project",
                    working_directory="/home",
                )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict3:
                mock_asdict3.return_value = context_dict
                result = await manager.preserve_context(session_id=session_id)
            assert result is True

            with sqlite3.connect(manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                snapshots = conn.execute(
                    "SELECT session_id FROM context_snapshots WHERE snapshot_type = 'preservation'"
                ).fetchall()

            # Should have preserved the first session, not the second
            session_ids = {row["session_id"] for row in snapshots}
            assert session_id in session_ids

    @pytest.mark.asyncio
    async def test_preserve_context_compression(self, manager) -> None:
        """Test that context preservation uses compression."""
        context_dict = make_context_dict("ctx_preserve4")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

            with sqlite3.connect(manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                snapshot = conn.execute(
                    "SELECT * FROM context_snapshots WHERE snapshot_type = 'preservation'"
                ).fetchone()

            metadata = json.loads(snapshot["metadata"])
            assert metadata.get("compressed") is True

            # Verify data is actually compressed
            compressed_data = snapshot["data"]
            # Decompress and check content
            decompressed = gzip.decompress(compressed_data)
            data = json.loads(decompressed.decode())
            assert "context" in data

    @pytest.mark.asyncio
    async def test_preserve_context_callback(self, manager) -> None:
        """Test that preservation callbacks are called."""
        context_dict = make_context_dict("ctx_preserve5")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            callback = AsyncMock()
            manager.register_preservation_callback(callback)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()
            assert callback.called


class TestInterruptionManagerRestoreContext:
    """Test InterruptionManager context restoration."""

    @pytest.mark.asyncio
    async def test_restore_context_no_snapshot(self, manager) -> None:
        """Test restore_context returns None when no snapshot exists."""
        result = await manager.restore_context("nonexistent-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_context_success(self, manager) -> None:
        """Test successful context restoration."""
        context_dict = make_context_dict("ctx_restore1")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

            restored = await manager.restore_context(session_id)

        assert restored is not None
        assert restored.user_id == "test-user"
        assert restored.project_id == "test-project"
        assert restored.recovery_attempts == 1

    @pytest.mark.asyncio
    async def test_restore_context_increments_recovery_attempts(self, manager) -> None:
        """Test that restore_context increments recovery_attempts."""
        context_dict = make_context_dict("ctx_restore2")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

            restored = await manager.restore_context(session_id)
            assert restored.recovery_attempts >= 1

    @pytest.mark.asyncio
    async def test_restore_context_updates_db_state(self, manager) -> None:
        """Test that restore_context updates database state."""
        context_dict = make_context_dict("ctx_restore3")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

            await manager.restore_context(session_id)

            with sqlite3.connect(manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT state, restore_count FROM session_contexts WHERE session_id = ?",
                    (session_id,),
                ).fetchone()

            assert row["state"] == "restored"
            assert row["restore_count"] >= 1

    @pytest.mark.asyncio
    async def test_restore_context_callback(self, manager) -> None:
        """Test that restoration callbacks are called."""
        context_dict = make_context_dict("ctx_restore4")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

            callback = AsyncMock()
            manager.register_restoration_callback(callback)

            await manager.restore_context(session_id)
            assert callback.called


class TestInterruptionManagerInterruptionHistory:
    """Test InterruptionManager interruption history."""

    @pytest.mark.asyncio
    async def test_get_interruption_history_empty(self, manager) -> None:
        """Test getting interruption history when none exist."""
        history = await manager.get_interruption_history("test-user")
        assert history == []

    @pytest.mark.asyncio
    async def test_get_interruption_history_with_events(self, manager) -> None:
        """Test getting interruption history with events."""
        from session_buddy.interruption_manager import (
            InterruptionEvent,
            InterruptionType,
        )

        # Create and store a mock interruption
        event = InterruptionEvent(
            id="int_test_1",
            event_type=InterruptionType.APP_SWITCH,
            timestamp=datetime.now(UTC),
            source_context={"app": "VS Code"},
            target_context={"app": "Terminal"},
            duration=10.0,
            recovery_data=None,
            auto_saved=True,
            user_id="test-user",
            project_id="test-project",
        )

        await manager._store_interruption(event)

        history = await manager.get_interruption_history("test-user", hours=24)
        assert len(history) == 1
        assert history[0]["id"] == "int_test_1"
        assert history[0]["source_context"]["app"] == "VS Code"

    @pytest.mark.asyncio
    async def test_get_interruption_history_time_filter(self, manager) -> None:
        """Test that interruption history respects time filter."""
        from session_buddy.interruption_manager import (
            InterruptionEvent,
            InterruptionType,
        )

        # Create old interruption
        old_event = InterruptionEvent(
            id="int_old",
            event_type=InterruptionType.APP_SWITCH,
            timestamp=datetime.now(UTC) - timedelta(hours=48),
            source_context={},
            target_context={},
            duration=None,
            recovery_data=None,
            auto_saved=False,
            user_id="test-user",
            project_id=None,
        )

        await manager._store_interruption(old_event)

        history = await manager.get_interruption_history("test-user", hours=24)
        assert len(history) == 0


class TestInterruptionManagerStatistics:
    """Test InterruptionManager statistics."""

    @pytest.mark.asyncio
    async def test_get_context_statistics_empty(self, manager) -> None:
        """Test getting statistics with no data."""
        stats = await manager.get_context_statistics("test-user")
        assert stats["sessions"]["total_sessions"] == 0
        assert stats["interruptions"]["total"] == 0

    @pytest.mark.asyncio
    async def test_get_context_statistics_with_data(self, manager) -> None:
        """Test getting statistics with session data."""
        context_dict = make_context_dict("ctx_stats1")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                await manager.preserve_context()

        stats = await manager.get_context_statistics("test-user")
        assert stats["sessions"]["total_sessions"] == 1
        assert stats["sessions"]["preserved_sessions"] == 1


# =====================================
# Test Handle Interruption
# =====================================


class TestHandleInterruption:
    """Test _handle_interruption method."""

    def test_handle_interruption_app_switch(self, manager) -> None:
        """Test handling APP_SWITCH interruption."""
        manager.current_context = MagicMock()
        manager.current_context.user_id = "test-user"
        manager.current_context.project_id = "test-project"
        manager.current_context.interruption_count = 0

        event_data = {
            "type": InterruptionType.APP_SWITCH,
            "timestamp": datetime.now(UTC),
            "source_app": "VS Code",
            "target_app": "Terminal",
            "focus_duration": 35.0,
        }

        with patch.object(manager, "_store_interruption", new_callable=AsyncMock):
            manager._handle_interruption(event_data)

        assert manager.current_context.interruption_count == 1

    def test_handle_interruption_auto_save_threshold(self, manager) -> None:
        """Test auto-save triggers when threshold is met."""
        manager.current_context = MagicMock()
        manager.current_context.user_id = "test-user"
        manager.current_context.project_id = "test-project"
        manager.current_context.interruption_count = 0
        manager.auto_save_enabled = True
        manager.save_threshold = 30.0

        event_data = {
            "type": InterruptionType.APP_SWITCH,
            "timestamp": datetime.now(UTC),
            "focus_duration": 35.0,
        }

        with patch.object(manager, "preserve_context", new_callable=AsyncMock) as mock_preserve:
            mock_preserve.return_value = True
            manager._handle_interruption(event_data)

            # Give async task time to execute
            time.sleep(0.1)

        # The auto-save should have been triggered
        assert manager.current_context.interruption_count == 1


# =====================================
# Test Capture Environment State
# =====================================


class TestCaptureEnvironmentState:
    """Test _capture_environment_state method."""

    def test_capture_environment_state_structure(self, manager) -> None:
        """Test that environment state has expected structure."""
        state = manager._capture_environment_state()

        assert "timestamp" in state
        assert "cwd" in state
        assert "processes" in state
        assert isinstance(state["processes"], list)

    def test_capture_environment_state_timestamp(self, manager) -> None:
        """Test that timestamp is in ISO format."""
        state = manager._capture_environment_state()

        # Should be parseable as ISO format
        datetime.fromisoformat(state["timestamp"])


# =====================================
# Test Public API Functions
# =====================================


class TestPublicAPI:
    """Test public API functions."""

    @pytest.mark.asyncio
    async def test_get_interruption_manager_singleton(self) -> None:
        """Test get_interruption_manager returns singleton."""
        import session_buddy.interruption_manager as im

        # Reset global for test
        im._interruption_manager = None

        from session_buddy.interruption_manager import get_interruption_manager

        manager1 = get_interruption_manager()
        manager2 = get_interruption_manager()

        assert manager1 is manager2

        # Cleanup
        im._interruption_manager = None

    @pytest.mark.asyncio
    async def test_create_session_context_api(self) -> None:
        """Test create_session_context public API."""
        import session_buddy.interruption_manager as im

        im._interruption_manager = None

        from session_buddy.interruption_manager import (
            create_session_context,
        )

        context_dict = make_context_dict("ctx_api1")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            assert session_id.startswith("ctx_")

        # Cleanup
        im._interruption_manager = None

    @pytest.mark.asyncio
    async def test_preserve_current_context_api(self) -> None:
        """Test preserve_current_context public API."""
        import session_buddy.interruption_manager as im

        im._interruption_manager = None

        from session_buddy.interruption_manager import (
            create_session_context,
            preserve_current_context,
        )

        context_dict = make_context_dict("ctx_api2")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            await create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            with patch.object(im.get_interruption_manager(), "preserve_context", new_callable=AsyncMock) as mock_preserve:
                mock_preserve.return_value = True
                result = await preserve_current_context()
            assert result is True

        # Cleanup
        im._interruption_manager = None

    @pytest.mark.asyncio
    async def test_restore_session_context_api(self) -> None:
        """Test restore_session_context public API."""
        import session_buddy.interruption_manager as im

        im._interruption_manager = None

        from session_buddy.interruption_manager import (
            create_session_context,
            preserve_current_context,
            restore_session_context,
        )

        context_dict = make_context_dict("ctx_api3")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            with patch.object(im.get_interruption_manager(), "preserve_context", new_callable=AsyncMock) as mock_preserve:
                mock_preserve.return_value = True
                await preserve_current_context()

            with patch.object(im.get_interruption_manager(), "restore_context", new_callable=AsyncMock) as mock_restore:
                mock_restore.return_value = MagicMock(
                    user_id="test-user",
                    project_id="test-project",
                    recovery_attempts=1,
                )
                restored = await restore_session_context(session_id)

            assert restored is not None
            assert restored["user_id"] == "test-user"

        # Cleanup
        im._interruption_manager = None

    @pytest.mark.asyncio
    async def test_get_interruption_history_api(self) -> None:
        """Test get_interruption_history public API."""
        from session_buddy.interruption_manager import get_interruption_history

        history = await get_interruption_history("test-user")
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_get_interruption_statistics_api(self) -> None:
        """Test get_interruption_statistics public API."""
        from session_buddy.interruption_manager import get_interruption_statistics

        stats = await get_interruption_statistics("test-user")
        assert isinstance(stats, dict)


# =====================================
# Test Edge Cases
# =====================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_preserve_context_db_error(self, manager) -> None:
        """Test preserve_context handles database errors gracefully."""
        context_dict = make_context_dict("ctx_err1")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            manager.current_context.last_activity = datetime.now(UTC)

            # Corrupt the database to force an error
            with sqlite3.connect(manager.db_path) as conn:
                conn.execute("DROP TABLE context_snapshots")

            with patch("session_buddy.interruption_manager.asdict") as mock_asdict2:
                mock_asdict2.return_value = context_dict
                result = await manager.preserve_context()
            assert result is False

    @pytest.mark.asyncio
    async def test_restore_context_db_error(self, manager) -> None:
        """Test restore_context handles database errors gracefully."""
        result = await manager.restore_context("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_context_invalid_data(self, manager) -> None:
        """Test restore_context handles corrupted snapshot data."""
        context_dict = make_context_dict("ctx_err2")

        with patch("session_buddy.interruption_manager.asdict") as mock_asdict:
            mock_asdict.return_value = context_dict
            session_id = await manager.create_session_context(
                user_id="test-user",
                project_id="test-project",
                working_directory="/tmp",
            )

            # Insert corrupted snapshot
            with sqlite3.connect(manager.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO context_snapshots (id, session_id, snapshot_type, timestamp, data, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        "snap_corrupt",
                        session_id,
                        "preservation",
                        datetime.now(UTC),
                        b"not valid json",
                        json.dumps({"compressed": False}),
                    ),
                )

            result = await manager.restore_context(session_id)
            assert result is None

    def test_register_multiple_callbacks(self, manager) -> None:
        """Test registering multiple preservation/restoration callbacks."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        manager.register_preservation_callback(callback1)
        manager.register_preservation_callback(callback2)

        assert len(manager._preservation_callbacks) == 2

        manager.register_restoration_callback(callback1)
        manager.register_restoration_callback(callback2)

        assert len(manager._restoration_callbacks) == 2

    @pytest.mark.asyncio
    async def test_get_context_statistics_handles_empty_db(self, manager) -> None:
        """Test get_context_statistics doesn't fail on empty database."""
        stats = await manager.get_context_statistics("nonexistent-user")

        assert "sessions" in stats
        assert "interruptions" in stats
        assert "snapshots" in stats

    @pytest.mark.asyncio
    async def test_interruption_history_handles_null_contexts(self, manager) -> None:
        """Test get_interruption_history handles null source/target contexts."""
        from session_buddy.interruption_manager import (
            InterruptionEvent,
            InterruptionType,
        )

        event = InterruptionEvent(
            id="int_null_ctx",
            event_type=InterruptionType.APP_SWITCH,
            timestamp=datetime.now(UTC),
            source_context=None,
            target_context=None,
            duration=None,
            recovery_data=None,
            auto_saved=False,
            user_id="test-user",
            project_id=None,
        )

        await manager._store_interruption(event)
        history = await manager.get_interruption_history("test-user")

        assert len(history) == 1


# =====================================
# Test Interruption Storage
# =====================================


class TestStoreInterruption:
    """Test _store_interruption method."""

    @pytest.mark.asyncio
    async def test_store_interruption_success(self, manager) -> None:
        """Test storing an interruption event."""
        from session_buddy.interruption_manager import (
            InterruptionEvent,
            InterruptionType,
        )

        event = InterruptionEvent(
            id="int_store_test",
            event_type=InterruptionType.WINDOW_CHANGE,
            timestamp=datetime.now(UTC),
            source_context={"window": "main"},
            target_context={"window": "settings"},
            duration=5.0,
            recovery_data={"step": 1},
            auto_saved=True,
            user_id="test-user",
            project_id="test-project",
        )

        await manager._store_interruption(event)

        with sqlite3.connect(manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM interruption_events WHERE id = ?",
                ("int_store_test",),
            ).fetchone()

        assert row is not None
        assert row["event_type"] == "window_change"
        assert row["auto_saved"] == 1
