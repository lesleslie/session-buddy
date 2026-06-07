"""Comprehensive pytest unit tests for session_buddy/worker.py.

This module provides 60+ tests covering:
- Task class: all methods, lifecycle, error handling, edge cases
- Worker class: all public methods, lifecycle, health monitoring, statistics
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Import the module under test
from session_buddy.worker import Task, Worker


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_task_id() -> str:
    """Provide a sample task ID."""
    return "test-task-123"


@pytest.fixture
def sample_prompt() -> str:
    """Provide a sample prompt."""
    return "Process this task"


@pytest.fixture
def sample_context() -> dict[str, Any]:
    """Provide a sample context dictionary."""
    return {"user_id": "user-456", "priority": "high"}


@pytest.fixture
def mock_queue() -> AsyncMock:
    """Provide a mock asyncio.Queue."""
    return AsyncMock(spec=asyncio.Queue)


@pytest.fixture
def worker_kwargs(sample_task_id: str, mock_queue: AsyncMock) -> dict[str, Any]:
    """Provide keyword arguments for Worker initialization."""
    return {
        "worker_id": sample_task_id,
        "queue": mock_queue,
        "pool_id": "pool-abc",
    }


# ============================================================================
# Task Class Tests
# ============================================================================


class TestTaskInit:
    """Tests for Task.__init__."""

    def test_init_with_all_args(self, sample_task_id: str, sample_prompt: str, sample_context: dict[str, Any]) -> None:
        """Test Task initialization with all arguments provided."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt, context=sample_context)

        assert task.task_id == sample_task_id
        assert task.prompt == sample_prompt
        assert task.context == sample_context
        assert task.status == "pending"
        assert task.created_at is not None
        assert task.started_at is None
        assert task.completed_at is None
        assert task.result is None
        assert task.error is None

    def test_init_with_minimal_args(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test Task initialization with only required arguments."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        assert task.task_id == sample_task_id
        assert task.prompt == sample_prompt
        assert task.context == {}
        assert task.status == "pending"

    def test_init_with_none_context(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test Task initialization with None context."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt, context=None)

        assert task.context == {}

    def test_init_default_status(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that default status is 'pending'."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        assert task.status == "pending"

    def test_init_result_event_exists(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that _result_event is created."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        assert isinstance(task._result_event, asyncio.Event)


class TestTaskWaitForResult:
    """Tests for Task.wait_for_result method."""

    @pytest.mark.asyncio
    async def test_wait_for_result_success(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test successful result retrieval."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.result = {"data": "success"}

        # Set the event so wait_for_result can proceed
        task._result_event.set()

        result = await task.wait_for_result(timeout=1.0)

        assert result == {"data": "success"}

    @pytest.mark.asyncio
    async def test_wait_for_result_with_none_timeout(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test wait with None timeout (wait indefinitely)."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.result = {"data": "success"}
        task._result_event.set()

        result = await task.wait_for_result(timeout=None)

        assert result == {"data": "success"}

    @pytest.mark.asyncio
    async def test_wait_for_result_raises_on_timeout(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that TimeoutError is raised when timeout exceeded."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        with pytest.raises(asyncio.TimeoutError):
            await task.wait_for_result(timeout=0.01)

    @pytest.mark.asyncio
    async def test_wait_for_result_raises_on_error(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that error is raised if task has error set."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.error = ValueError("Task failed")
        task._result_event.set()

        with pytest.raises(ValueError, match="Task failed"):
            await task.wait_for_result(timeout=1.0)

    @pytest.mark.asyncio
    async def test_wait_for_result_error_takes_precedence_over_result(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that error is raised even if result is also set."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.result = {"data": "success"}
        task.error = ValueError("Task failed")
        task._result_event.set()

        with pytest.raises(ValueError, match="Task failed"):
            await task.wait_for_result(timeout=1.0)


class TestTaskSetResult:
    """Tests for Task.set_result method."""

    @pytest.mark.asyncio
    async def test_set_result_updates_status(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_result updates status to completed."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await task.set_result({"data": "result"})

        assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_set_result_sets_result(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_result stores the result."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        expected_result = {"data": "result", "value": 42}

        await task.set_result(expected_result)

        assert task.result == expected_result

    @pytest.mark.asyncio
    async def test_set_result_sets_completed_at(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_result sets completed_at timestamp."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        before = datetime.now(UTC)

        await task.set_result({"data": "result"})

        after = datetime.now(UTC)
        assert task.completed_at is not None
        assert before <= task.completed_at <= after

    @pytest.mark.asyncio
    async def test_set_result_sets_event(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_result sets the _result_event."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await task.set_result({"data": "result"})

        assert task._result_event.is_set()

    @pytest.mark.asyncio
    async def test_set_result_with_none(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test set_result with None value."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await task.set_result(None)

        assert task.result is None
        assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_set_result_with_empty_string(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test set_result with empty string."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await task.set_result("")

        assert task.result == ""

    @pytest.mark.asyncio
    async def test_set_result_with_complex_object(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test set_result with complex nested object."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        complex_result = {
            "nested": {"data": [1, 2, 3]},
            "bool": True,
            "none": None,
        }

        await task.set_result(complex_result)

        assert task.result == complex_result


class TestTaskSetError:
    """Tests for Task.set_error method."""

    @pytest.mark.asyncio
    async def test_set_error_updates_status(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_error updates status to failed."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await task.set_error(ValueError("Test error"))

        assert task.status == "failed"

    @pytest.mark.asyncio
    async def test_set_error_sets_error(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_error stores the exception."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        error = ValueError("Test error")

        await task.set_error(error)

        assert task.error is error

    @pytest.mark.asyncio
    async def test_set_error_sets_completed_at(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_error sets completed_at timestamp."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        before = datetime.now(UTC)

        await task.set_error(RuntimeError("Test error"))

        after = datetime.now(UTC)
        assert task.completed_at is not None
        assert before <= task.completed_at <= after

    @pytest.mark.asyncio
    async def test_set_error_sets_event(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test that set_error sets the _result_event."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await task.set_error(Exception("Test error"))

        assert task._result_event.is_set()

    @pytest.mark.asyncio
    async def test_set_error_with_different_exception_types(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test set_error with various exception types."""
        exceptions = [
            ValueError("Value error"),
            RuntimeError("Runtime error"),
            TypeError("Type error"),
            KeyError("Key error"),
        ]

        for error in exceptions:
            task = Task(task_id=sample_task_id, prompt=sample_prompt)
            await task.set_error(error)
            assert task.error is error
            assert task.status == "failed"


class TestTaskToDict:
    """Tests for Task.to_dict method."""

    def test_to_dict_pending_task(self, sample_task_id: str, sample_prompt: str, sample_context: dict[str, Any]) -> None:
        """Test to_dict for pending task."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt, context=sample_context)

        result = task.to_dict()

        assert result["task_id"] == sample_task_id
        assert result["prompt"] == sample_prompt
        assert result["context"] == sample_context
        assert result["status"] == "pending"
        assert result["started_at"] is None
        assert result["completed_at"] is None
        assert result["result"] is None
        assert result["error"] is None

    def test_to_dict_completed_task(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test to_dict for completed task."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.status = "completed"
        task.result = {"data": "success"}
        task.completed_at = datetime.now(UTC)
        task.started_at = datetime.now(UTC)

        result = task.to_dict()

        assert result["status"] == "completed"
        assert result["result"] == str({"data": "success"})
        assert result["started_at"] is not None
        assert result["completed_at"] is not None

    def test_to_dict_failed_task(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test to_dict for failed task."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.status = "failed"
        task.error = ValueError("Task failed")
        task.completed_at = datetime.now(UTC)

        result = task.to_dict()

        assert result["status"] == "failed"
        assert result["error"] == str(ValueError("Task failed"))

    def test_to_dict_with_none_context(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test to_dict when context is None."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt, context=None)

        result = task.to_dict()

        assert result["context"] == {}

    def test_to_dict_result_none(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test to_dict when result is None."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = task.to_dict()

        assert result["result"] is None

    def test_to_dict_error_none(self, sample_task_id: str, sample_prompt: str) -> None:
        """Test to_dict when error is None."""
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = task.to_dict()

        assert result["error"] is None


# ============================================================================
# Worker Class Tests
# ============================================================================


class TestWorkerInit:
    """Tests for Worker.__init__."""

    def test_init_sets_worker_id(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that worker_id is set correctly."""
        worker = Worker(**worker_kwargs)

        assert worker.worker_id == worker_kwargs["worker_id"]

    def test_init_sets_queue(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that queue is set correctly."""
        worker = Worker(**worker_kwargs)

        assert worker.queue is worker_kwargs["queue"]

    def test_init_sets_pool_id(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that pool_id is set correctly."""
        worker = Worker(**worker_kwargs)

        assert worker.pool_id == worker_kwargs["pool_id"]

    def test_init_default_running_false(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that running defaults to False."""
        worker = Worker(**worker_kwargs)

        assert worker.running is False

    def test_init_default_task_none(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that _task defaults to None."""
        worker = Worker(**worker_kwargs)

        assert worker._task is None

    def test_init_statistics_initialized(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that statistics are initialized to zero."""
        worker = Worker(**worker_kwargs)

        assert worker.tasks_processed == 0
        assert worker.tasks_succeeded == 0
        assert worker.tasks_failed == 0
        assert worker.total_processing_time == 0.0
        assert worker.last_activity is None

    def test_init_health_initialized(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health is initialized correctly."""
        worker = Worker(**worker_kwargs)

        assert worker.healthy is True
        assert worker.health_check_failures == 0
        assert isinstance(worker._health_lock, asyncio.Lock)

    def test_init_logs_message(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __init__ logs an info message."""
        with patch("session_buddy.worker.logger") as mock_logger:
            worker = Worker(**worker_kwargs)
            mock_logger.info.assert_called_once()
            assert "initialized" in mock_logger.info.call_args[0][0]


class TestWorkerStart:
    """Tests for Worker.start method."""

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that start sets running to True."""
        worker = Worker(**worker_kwargs)

        await worker.start()

        assert worker.running is True

    @pytest.mark.asyncio
    async def test_start_creates_task(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that start creates an asyncio task."""
        worker = Worker(**worker_kwargs)

        await worker.start()

        assert worker._task is not None
        assert isinstance(worker._task, asyncio.Task)

    @pytest.mark.asyncio
    async def test_start_idempotent(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that starting an already running worker is idempotent."""
        worker = Worker(**worker_kwargs)
        await worker.start()
        first_task = worker._task

        await worker.start()

        assert worker._task is first_task  # Should not create new task

    @pytest.mark.asyncio
    async def test_start_logs_warning_when_already_running(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that starting already running worker logs warning."""
        worker = Worker(**worker_kwargs)
        await worker.start()

        with patch("session_buddy.worker.logger") as mock_logger:
            await worker.start()
            mock_logger.warning.assert_called_once()
            assert "already running" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_start_logs_info(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that start logs an info message."""
        with patch("session_buddy.worker.logger") as mock_logger:
            worker = Worker(**worker_kwargs)
            await worker.start()
            mock_logger.info.assert_called()
            assert any("started" in str(call) for call in mock_logger.info.call_args_list)


class TestWorkerStop:
    """Tests for Worker.stop method."""

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that stop sets running to False."""
        worker = Worker(**worker_kwargs)
        await worker.start()

        await worker.stop()

        assert worker.running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that stopping a non-running worker is a no-op."""
        worker = Worker(**worker_kwargs)

        # Should not raise
        await worker.stop()

        assert worker.running is False

    @pytest.mark.asyncio
    async def test_stop_waits_for_task(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that stop waits for the internal task to complete."""
        worker = Worker(**worker_kwargs)
        await worker.start()

        await worker.stop(timeout=5.0)

        # Task should have completed or been cancelled
        assert worker._task is None or worker._task.done()

    @pytest.mark.asyncio
    async def test_stop_timeout_cancels_task(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that stop cancels the task on timeout."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker._task = asyncio.create_task(asyncio.sleep(10))

        await worker.stop(timeout=0.01)

        # Task should be cancelled
        assert worker._task.cancelled() or worker._task.done()

    @pytest.mark.asyncio
    async def test_stop_logs_warning_on_timeout(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that stop logs warning when timeout occurs."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker._task = asyncio.create_task(asyncio.sleep(10))

        with patch("session_buddy.worker.logger") as mock_logger:
            await worker.stop(timeout=0.01)
            mock_logger.warning.assert_called()
            assert "did not stop within" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_stop_logs_info(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that stop logs an info message."""
        worker = Worker(**worker_kwargs)
        await worker.start()

        with patch("session_buddy.worker.logger") as mock_logger:
            await worker.stop()
            assert any("stopped" in str(call) or "Stopping" in str(call) for call in mock_logger.info.call_args_list)


class TestWorkerExecuteTask:
    """Tests for Worker._execute_task method."""

    @pytest.mark.asyncio
    async def test_execute_task_updates_task_status(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that _execute_task updates task status to running during execution."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        # Mock set_result to capture the status at the moment it's called
        original_set_result = task.set_result
        captured_status = None

        async def capture_status(*args: Any, **kwargs: Any) -> None:
            nonlocal captured_status
            captured_status = task.status
            await original_set_result(*args, **kwargs)

        task.set_result = capture_status

        await worker._execute_task(task)

        # Status was "running" when set_result was called
        assert captured_status == "running"
        # After completion, status is "completed"
        assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_task_sets_started_at(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that _execute_task sets started_at."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await worker._execute_task(task)

        assert task.started_at is not None

    @pytest.mark.asyncio
    async def test_execute_task_updates_last_activity(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that _execute_task updates last_activity."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await worker._execute_task(task)

        assert worker.last_activity is not None

    @pytest.mark.asyncio
    async def test_execute_task_calls_set_result_on_success(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that _execute_task calls set_result on success."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.set_result = AsyncMock()

        await worker._execute_task(task)

        task.set_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_task_increments_success_stats(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that successful execution increments tasks_succeeded."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await worker._execute_task(task)

        assert worker.tasks_succeeded == 1
        assert worker.tasks_failed == 0

    @pytest.mark.asyncio
    async def test_execute_task_increments_processed_count(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that execution increments tasks_processed."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await worker._execute_task(task)

        assert worker.tasks_processed == 1

    @pytest.mark.asyncio
    async def test_execute_task_calls_set_error_on_failure(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that _execute_task calls set_error on failure."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        task.set_error = AsyncMock()

        # Mock _execute_task_logic to raise an exception
        error = ValueError("Task failed")
        worker._execute_task_logic = AsyncMock(side_effect=error)

        await worker._execute_task(task)

        # Verify set_error was called once with any ValueError
        task.set_error.assert_called_once()
        # Verify the error type and message
        called_error = task.set_error.call_args[0][0]
        assert isinstance(called_error, ValueError)
        assert str(called_error) == "Task failed"

    @pytest.mark.asyncio
    async def test_execute_task_increments_failure_stats(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that failed execution increments tasks_failed."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        worker._execute_task_logic = AsyncMock(side_effect=ValueError("Task failed"))

        await worker._execute_task(task)

        assert worker.tasks_failed == 1
        assert worker.tasks_succeeded == 0

    @pytest.mark.asyncio
    async def test_execute_task_resets_health_on_success(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that health_check_failures is reset on success."""
        worker = Worker(**worker_kwargs)
        worker.health_check_failures = 2
        worker.healthy = False
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await worker._execute_task(task)

        assert worker.health_check_failures == 0
        assert worker.healthy is True

    @pytest.mark.asyncio
    async def test_execute_task_updates_processing_time(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that processing time is tracked."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        await worker._execute_task(task)

        assert worker.total_processing_time > 0


class TestWorkerExecuteTaskLogic:
    """Tests for Worker._execute_task_logic method."""

    @pytest.mark.asyncio
    async def test_execute_task_logic_returns_result(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that _execute_task_logic returns a result."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = await worker._execute_task_logic(task)

        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_task_logic_includes_worker_id(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that result includes worker_id."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = await worker._execute_task_logic(task)

        assert result["worker_id"] == worker.worker_id

    @pytest.mark.asyncio
    async def test_execute_task_logic_includes_pool_id(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that result includes pool_id."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = await worker._execute_task_logic(task)

        assert result["pool_id"] == worker.pool_id

    @pytest.mark.asyncio
    async def test_execute_task_logic_includes_task_id(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that result includes task_id."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = await worker._execute_task_logic(task)

        assert result["task_id"] == task.task_id

    @pytest.mark.asyncio
    async def test_execute_task_logic_includes_prompt(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that result includes prompt."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = await worker._execute_task_logic(task)

        assert result["prompt"] == task.prompt

    @pytest.mark.asyncio
    async def test_execute_task_logic_includes_context(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str, sample_context: dict[str, Any]) -> None:
        """Test that result includes context."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt, context=sample_context)

        result = await worker._execute_task_logic(task)

        assert result["context"] == sample_context

    @pytest.mark.asyncio
    async def test_execute_task_logic_includes_response(self, worker_kwargs: dict[str, Any], sample_task_id: str, sample_prompt: str) -> None:
        """Test that result includes response."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt=sample_prompt)

        result = await worker._execute_task_logic(task)

        assert "response" in result
        assert "Processed task" in result["response"]


class TestWorkerProcessTasks:
    """Tests for Worker._process_tasks method."""

    @pytest.mark.asyncio
    async def test_process_tasks_loop_terminates_when_not_running(self, worker_kwargs: dict[str, Any], mock_queue: AsyncMock) -> None:
        """Test that _process_tasks loop terminates when running is False."""
        worker = Worker(**worker_kwargs)
        worker.running = False  # Will exit immediately

        # Should not raise
        await worker._process_tasks()

    @pytest.mark.asyncio
    async def test_process_tasks_handles_timeout(self, worker_kwargs: dict[str, Any], mock_queue: AsyncMock) -> None:
        """Test that _process_tasks handles queue timeout gracefully."""
        worker = Worker(**worker_kwargs)
        worker.running = True

        # ``_process_tasks`` loops on TimeoutError until ``worker.running``
        # flips False. We use a side_effect that blocks once with an
        # ``asyncio.Event`` (so ``wait_for`` raises the real
        # ``TimeoutError``) then flips the running flag. This exercises
        # the genuine wait_for timeout path while still terminating the
        # loop.
        timeout_event = asyncio.Event()
        first_call = True

        async def block_then_stop(*args: Any, **kwargs: Any) -> None:
            nonlocal first_call
            if first_call:
                first_call = False
                # Block long enough for wait_for to time out (1.0s).
                # We set the event after 1.2s to also flip the loop flag.
                try:
                    await asyncio.wait_for(timeout_event.wait(), timeout=1.5)
                except asyncio.TimeoutError:
                    pass
            worker.running = False
            return None

        mock_queue.get.side_effect = block_then_stop

        await worker._process_tasks()

        # Should have called get at least once
        mock_queue.get.assert_called()

    @pytest.mark.asyncio
    async def test_process_tasks_handles_cancelled_error(self, worker_kwargs: dict[str, Any], mock_queue: AsyncMock) -> None:
        r"""Test that _process_tasks handles CancelledError gracefully.

        The production code intentionally swallows ``CancelledError`` and
        ``break``\s the loop so the worker shuts down cleanly; the
        exception should NOT propagate to the caller. This test verifies
        that the function returns without raising, and that the loop
        terminated (no hang).
        """
        worker = Worker(**worker_kwargs)
        worker.running = True

        mock_queue.get.side_effect = asyncio.CancelledError()

        # Should return without raising — CancelledError is caught and
        # converted to a graceful loop exit.
        result = await worker._process_tasks()
        assert result is None
        mock_queue.get.assert_called()

    @pytest.mark.asyncio
    async def test_process_tasks_handles_generic_exception(self, worker_kwargs: dict[str, Any], mock_queue: AsyncMock) -> None:
        """Test that _process_tasks handles generic exceptions and marks unhealthy."""
        worker = Worker(**worker_kwargs)
        worker.running = True

        # ``_process_tasks`` only exits when ``worker.running`` is False.
        # We flip the flag from a side_effect that fires the moment
        # the loop tries to grab the (non-existent) task. Using a
        # side_effect (rather than a separate ``asyncio.create_task``)
        # avoids the event-loop yield timing problem where a parallel
        # stopper task never gets to run.
        call_count = 0

        def fail_then_stop(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First iteration: exercise the failure path.
                raise ValueError("Queue error")
            # Subsequent iterations: stop the loop.
            worker.running = False
            return None

        mock_queue.get.side_effect = fail_then_stop

        with patch("session_buddy.worker.logger") as mock_logger:
            await worker._process_tasks()
            mock_logger.exception.assert_called()

        # Health check failures should increment
        assert worker.health_check_failures >= 1

    @pytest.mark.asyncio
    async def test_process_tasks_marks_unhealthy_after_3_failures(self, worker_kwargs: dict[str, Any], mock_queue: AsyncMock) -> None:
        """Test that worker is marked unhealthy after 3 consecutive failures."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.health_check_failures = 2  # Will become 3

        # Use a side_effect that flips ``running`` after a few failures
        # so the test exercises the unhealthy-after-3 path without
        # hanging the loop forever.
        call_count = 0

        def fail_then_stop(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise ValueError("Queue error")
            worker.running = False
            return None

        mock_queue.get.side_effect = fail_then_stop

        with patch("session_buddy.worker.logger"):
            await worker._process_tasks()

        assert worker.healthy is False

    @pytest.mark.asyncio
    async def test_process_tasks_executes_task(self, worker_kwargs: dict[str, Any], mock_queue: AsyncMock, sample_task_id: str, sample_prompt: str) -> None:
        """Test that _process_tasks executes a task from the queue."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        task = Task(task_id=sample_task_id, prompt=sample_prompt)
        # Return the task once, then flip ``running`` so the loop exits.
        # Returning the same task forever would cause the loop to
        # re-execute it indefinitely.
        call_count = 0

        def get_task_or_stop(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return task
            worker.running = False
            return task

        mock_queue.get.side_effect = get_task_or_stop

        await worker._process_tasks()

        # Task should have been executed
        assert task.status in ("completed", "failed")


class TestWorkerHealthCheck:
    """Tests for Worker.health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_healthy(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check returns True when worker is healthy."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.healthy = True
        worker.health_check_failures = 0

        result = await worker.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_too_many_failures(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check returns False when health_check_failures >= 3."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.health_check_failures = 3

        result = await worker.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_not_running(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check returns False when worker is not running."""
        worker = Worker(**worker_kwargs)
        worker.running = False

        result = await worker.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_idle_too_long(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check returns False when idle > 5 minutes."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.health_check_failures = 0
        worker.last_activity = datetime.now(UTC).replace(hour=datetime.now(UTC).hour - 1)  # 1 hour ago

        result = await worker.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_recent_activity(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check returns True when there was recent activity."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.health_check_failures = 0
        worker.last_activity = datetime.now(UTC)

        result = await worker.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_no_activity_yet(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check returns True when last_activity is None."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.health_check_failures = 0
        worker.last_activity = None

        result = await worker.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_uses_lock(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that health_check uses the health lock."""
        worker = Worker(**worker_kwargs)
        worker.running = True
        worker.health_check_failures = 0

        # Replace the lock with a fully-mocked async context manager so we
        # can verify the health_check() actually enters it. Patching
        # ``__aenter__``/``__aexit__`` on an ``asyncio.Lock`` instance does
        # not work because the C-level slot is bound and bypasses
        # instance attribute lookups — the original lock would still be
        # used. So we swap the whole attribute for an AsyncMock that
        # supports ``async with`` semantics.
        mock_lock = AsyncMock()
        mock_lock.__aenter__ = AsyncMock(return_value=None)
        mock_lock.__aexit__ = AsyncMock(return_value=None)
        with patch.object(worker, "_health_lock", mock_lock):
            await worker.health_check()
            mock_lock.__aenter__.assert_called_once()


class TestWorkerGetStatus:
    """Tests for Worker.get_status method."""

    def test_get_status_includes_worker_id(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes worker_id."""
        worker = Worker(**worker_kwargs)

        status = worker.get_status()

        assert status["worker_id"] == worker.worker_id

    def test_get_status_includes_pool_id(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes pool_id."""
        worker = Worker(**worker_kwargs)

        status = worker.get_status()

        assert status["pool_id"] == worker.pool_id

    def test_get_status_includes_running(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes running state."""
        worker = Worker(**worker_kwargs)

        status = worker.get_status()

        assert "running" in status
        assert isinstance(status["running"], bool)

    def test_get_status_includes_healthy(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes healthy state."""
        worker = Worker(**worker_kwargs)

        status = worker.get_status()

        assert "healthy" in status
        assert isinstance(status["healthy"], bool)

    def test_get_status_includes_tasks_processed(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes tasks_processed."""
        worker = Worker(**worker_kwargs)
        worker.tasks_processed = 10

        status = worker.get_status()

        assert status["tasks_processed"] == 10

    def test_get_status_includes_tasks_succeeded(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes tasks_succeeded."""
        worker = Worker(**worker_kwargs)
        worker.tasks_succeeded = 8

        status = worker.get_status()

        assert status["tasks_succeeded"] == 8

    def test_get_status_includes_tasks_failed(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes tasks_failed."""
        worker = Worker(**worker_kwargs)
        worker.tasks_failed = 2

        status = worker.get_status()

        assert status["tasks_failed"] == 2

    def test_get_status_success_rate_zero_tasks(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that success_rate is 1.0 when no tasks processed."""
        worker = Worker(**worker_kwargs)
        worker.tasks_processed = 0

        status = worker.get_status()

        assert status["success_rate"] == 1.0

    def test_get_status_success_rate_with_tasks(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that success_rate is calculated correctly."""
        worker = Worker(**worker_kwargs)
        worker.tasks_processed = 10
        worker.tasks_succeeded = 8
        worker.tasks_failed = 2

        status = worker.get_status()

        assert status["success_rate"] == 0.8

    def test_get_status_avg_processing_time_zero(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that avg_processing_time is 0 when no tasks processed."""
        worker = Worker(**worker_kwargs)
        worker.tasks_processed = 0

        status = worker.get_status()

        assert status["avg_processing_time"] == 0

    def test_get_status_avg_processing_time_with_tasks(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that avg_processing_time is calculated correctly."""
        worker = Worker(**worker_kwargs)
        worker.tasks_processed = 2
        worker.total_processing_time = 10.0

        status = worker.get_status()

        assert status["avg_processing_time"] == 5.0

    def test_get_status_includes_total_processing_time(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that get_status includes total_processing_time."""
        worker = Worker(**worker_kwargs)
        worker.total_processing_time = 15.5

        status = worker.get_status()

        assert status["total_processing_time"] == 15.5

    def test_get_status_last_activity_none(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that last_activity is None in status when not set."""
        worker = Worker(**worker_kwargs)
        worker.last_activity = None

        status = worker.get_status()

        assert status["last_activity"] is None

    def test_get_status_last_activity_set(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that last_activity is ISO formatted when set."""
        worker = Worker(**worker_kwargs)
        now = datetime.now(UTC)
        worker.last_activity = now

        status = worker.get_status()

        assert status["last_activity"] == now.isoformat()


class TestWorkerRepr:
    """Tests for Worker.__repr__ method."""

    def test_repr_includes_worker_id(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __repr__ includes worker_id."""
        worker = Worker(**worker_kwargs)

        repr_str = repr(worker)

        assert worker.worker_id in repr_str

    def test_repr_includes_pool_id(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __repr__ includes pool_id."""
        worker = Worker(**worker_kwargs)

        repr_str = repr(worker)

        assert worker.pool_id in repr_str

    def test_repr_includes_running_state(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __repr__ includes running state."""
        worker = Worker(**worker_kwargs)

        repr_str = repr(worker)

        assert "running" in repr_str

    def test_repr_includes_healthy_state(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __repr__ includes healthy state."""
        worker = Worker(**worker_kwargs)

        repr_str = repr(worker)

        assert "healthy" in repr_str

    def test_repr_includes_tasks_count(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __repr__ includes tasks count."""
        worker = Worker(**worker_kwargs)
        worker.tasks_processed = 5

        repr_str = repr(worker)

        assert "tasks" in repr_str
        assert "5" in repr_str


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestTaskEdgeCases:
    """Edge case tests for Task class."""

    def test_task_with_empty_prompt(self) -> None:
        """Test Task with empty prompt."""
        task = Task(task_id="test", prompt="")

        assert task.prompt == ""
        assert task.status == "pending"

    def test_task_with_unicode_prompt(self) -> None:
        """Test Task with unicode characters."""
        task = Task(task_id="test", prompt="Hello 世界 🌍")

        assert task.prompt == "Hello 世界 🌍"

    def test_task_with_very_long_task_id(self) -> None:
        """Test Task with very long task ID."""
        long_id = "x" * 10000
        task = Task(task_id=long_id, prompt="test")

        assert task.task_id == long_id

    def test_task_with_complex_context(self) -> None:
        """Test Task with complex nested context."""
        context = {
            "level1": {
                "level2": {
                    "level3": [1, 2, 3, {"nested": "value"}],
                }
            },
            "list": [1, 2, 3],
            "bool": True,
            "none": None,
        }
        task = Task(task_id="test", prompt="test", context=context)

        assert task.context == context


class TestWorkerEdgeCases:
    """Edge case tests for Worker class."""

    def test_worker_with_empty_worker_id(self, mock_queue: AsyncMock) -> None:
        """Test Worker with empty worker ID."""
        worker = Worker(worker_id="", queue=mock_queue, pool_id="pool")

        assert worker.worker_id == ""

    def test_worker_with_unicode_worker_id(self, mock_queue: AsyncMock) -> None:
        """Test Worker with unicode worker ID."""
        worker = Worker(worker_id="工作者-123", queue=mock_queue, pool_id="pool")

        assert worker.worker_id == "工作者-123"

    @pytest.mark.asyncio
    async def test_worker_execute_multiple_tasks(self, worker_kwargs: dict[str, Any]) -> None:
        """Test executing multiple tasks increments statistics correctly."""
        worker = Worker(**worker_kwargs)

        for i in range(5):
            task = Task(task_id=f"task-{i}", prompt=f"prompt-{i}")
            await worker._execute_task(task)

        assert worker.tasks_processed == 5
        assert worker.tasks_succeeded == 5
        assert worker.tasks_failed == 0

    @pytest.mark.asyncio
    async def test_worker_execute_mixed_success_failure(self, worker_kwargs: dict[str, Any]) -> None:
        """Test executing mixed success and failure updates stats correctly."""
        worker = Worker(**worker_kwargs)

        # Successful task
        task1 = Task(task_id="task-1", prompt="prompt-1")
        await worker._execute_task(task1)

        # Failed task
        task2 = Task(task_id="task-2", prompt="prompt-2")
        worker._execute_task_logic = AsyncMock(side_effect=ValueError("Error"))
        await worker._execute_task(task2)

        assert worker.tasks_processed == 2
        assert worker.tasks_succeeded == 1
        assert worker.tasks_failed == 1

    @pytest.mark.asyncio
    async def test_worker_health_check_with_many_failures(self, worker_kwargs: dict[str, Any]) -> None:
        """Test health check with multiple failures."""
        worker = Worker(**worker_kwargs)
        worker.health_check_failures = 5
        worker.running = True

        result = await worker.health_check()

        assert result is False

    def test_worker_get_status_all_zeros(self, worker_kwargs: dict[str, Any]) -> None:
        """Test get_status when all statistics are zero."""
        worker = Worker(**worker_kwargs)

        status = worker.get_status()

        assert status["tasks_processed"] == 0
        assert status["tasks_succeeded"] == 0
        assert status["tasks_failed"] == 0
        assert status["success_rate"] == 1.0
        assert status["avg_processing_time"] == 0
        assert status["total_processing_time"] == 0.0


# ============================================================================
# Integration-like Tests (But Still Isolated)
# ============================================================================


class TestWorkerLifecycle:
    """Tests for Worker lifecycle: start -> run -> stop."""

    @pytest.mark.asyncio
    async def test_start_stop_cycle(self, worker_kwargs: dict[str, Any]) -> None:
        """Test complete start-stop lifecycle."""
        worker = Worker(**worker_kwargs)

        assert worker.running is False

        await worker.start()
        assert worker.running is True
        assert worker._task is not None

        await worker.stop()
        assert worker.running is False

    @pytest.mark.asyncio
    async def test_double_start(self, worker_kwargs: dict[str, Any]) -> None:
        """Test double start doesn't create multiple tasks."""
        worker = Worker(**worker_kwargs)

        await worker.start()
        first_task = worker._task

        await worker.start()
        second_task = worker._task

        assert first_task is second_task

        await worker.stop()

    @pytest.mark.asyncio
    async def test_double_stop(self, worker_kwargs: dict[str, Any]) -> None:
        """Test double stop doesn't raise."""
        worker = Worker(**worker_kwargs)

        await worker.start()
        await worker.stop()

        # Should not raise
        await worker.stop()

    @pytest.mark.asyncio
    async def test_stop_then_start(self, worker_kwargs: dict[str, Any]) -> None:
        """Test stop then start works correctly."""
        worker = Worker(**worker_kwargs)

        await worker.start()
        await worker.stop()

        await worker.start()
        assert worker.running is True

        await worker.stop()


class TestTaskLifecycle:
    """Tests for Task lifecycle: create -> wait -> result/error."""

    @pytest.mark.asyncio
    async def test_task_completed_with_result(self) -> None:
        """Test task completed lifecycle with result."""
        task = Task(task_id="test", prompt="test")

        await task.set_result({"data": "success"})
        result = await task.wait_for_result(timeout=1.0)

        assert result == {"data": "success"}
        assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_task_completed_with_error(self) -> None:
        """Test task completed lifecycle with error."""
        task = Task(task_id="test", prompt="test")

        await task.set_error(ValueError("Failed"))
        task._result_event.set()

        with pytest.raises(ValueError, match="Failed"):
            await task.wait_for_result(timeout=1.0)

        assert task.status == "failed"

    @pytest.mark.asyncio
    async def test_task_to_dict_after_completion(self) -> None:
        """Test to_dict returns correct data after completion."""
        task = Task(task_id="test", prompt="test", context={"key": "value"})
        await task.set_result({"result": "success"})

        result = task.to_dict()

        assert result["task_id"] == "test"
        assert result["status"] == "completed"
        assert result["result"] == str({"result": "success"})


# ============================================================================
# Concurrent Tests
# ============================================================================


class TestConcurrentAccess:
    """Tests for concurrent access to worker state."""

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, worker_kwargs: dict[str, Any]) -> None:
        """Test concurrent health check calls don't conflict."""
        worker = Worker(**worker_kwargs)
        worker.running = True

        async def health_check_loop() -> None:
            for _ in range(10):
                await worker.health_check()
                await asyncio.sleep(0.001)

        await asyncio.gather(*[health_check_loop() for _ in range(5)])

        # Should complete without errors

    @pytest.mark.asyncio
    async def test_concurrent_get_status(self, worker_kwargs: dict[str, Any]) -> None:
        """Test concurrent get_status calls don't conflict."""
        worker = Worker(**worker_kwargs)

        async def status_loop() -> None:
            for _ in range(10):
                worker.get_status()
                await asyncio.sleep(0.001)

        await asyncio.gather(*[status_loop() for _ in range(5)])

        # Should complete without errors


# ============================================================================
# Logging Tests
# ============================================================================


class TestWorkerLogging:
    """Tests for Worker logging behavior."""

    def test_init_logs_at_info_level(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that __init__ logs at info level."""
        with patch("session_buddy.worker.logger") as mock_logger:
            Worker(**worker_kwargs)
            mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_logs_at_info_level(self, worker_kwargs: dict[str, Any]) -> None:
        """Test that start logs at info level."""
        worker = Worker(**worker_kwargs)
        with patch("session_buddy.worker.logger") as mock_logger:
            await worker.start()
            assert mock_logger.info.called

    @pytest.mark.asyncio
    async def test_execute_task_logs_success(self, worker_kwargs: dict[str, Any], sample_task_id: str) -> None:
        """Test that successful task execution is logged."""
        worker = Worker(**worker_kwargs)
        task = Task(task_id=sample_task_id, prompt="test")

        with patch("session_buddy.worker.logger") as mock_logger:
            await worker._execute_task(task)
            assert any("completed" in str(call).lower() or "executing" in str(call).lower()
                      for call in mock_logger.info.call_args_list)

    @pytest.mark.asyncio
    async def test_execute_task_logs_failure(self, worker_kwargs: dict[str, Any], sample_task_id: str) -> None:
        """Test that failed task execution is logged."""
        worker = Worker(**worker_kwargs)
        worker._execute_task_logic = AsyncMock(side_effect=ValueError("Error"))
        task = Task(task_id=sample_task_id, prompt="test")

        with patch("session_buddy.worker.logger") as mock_logger:
            await worker._execute_task(task)
            assert mock_logger.exception.called
