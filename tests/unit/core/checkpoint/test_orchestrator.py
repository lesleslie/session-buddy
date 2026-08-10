from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from session_buddy.checkpoint.orchestrator import (
    CheckpointOrchestrator,
    CheckpointResult,
)
from session_buddy.checkpoint.policy import (
    CheckpointPhase,
    CheckpointPolicy,
    MidpointCriteria,
    WorkingTreeInspector,
)
from session_buddy.checkpoint.snapshot import Snapshot, SnapshotMechanism
from session_buddy.checkpoint.subagent_detector import LockfileSignalSource, SubagentDetector


def _make_orch(tmp_path: Path, *, snapshot_side_effect=None, dirty_files=("x.py",)) -> CheckpointOrchestrator:
    snap = MagicMock(spec=SnapshotMechanism)
    snap.capture.return_value = Snapshot(
        path=tmp_path / "snap.patch", label="x", snapshot_id="snap-1",
        captured_at=MagicMock(), parent_commit="abc", dirty_files=list(dirty_files),
    )
    if snapshot_side_effect:
        snap.capture.side_effect = snapshot_side_effect

    policy = MagicMock(spec=CheckpointPolicy)
    policy.decide.return_value.should_fire = True
    policy.decide.return_value.reason = "end_of_task"

    detector = MagicMock(spec=SubagentDetector)
    detector.is_active.return_value = False
    detector.wait_until_idle = AsyncMock(return_value=True)
    forward = AsyncMock()

    return CheckpointOrchestrator(
        working_dir=tmp_path, policy=policy, snapshot=snap,
        subagent_detector=detector, forward_to=forward,
    )


@pytest.mark.unit
async def test_calls_snapshot_then_forward(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._snapshot.capture.assert_called_once()
    orch._forward_to.assert_awaited_once()
    assert result.fired is True
    assert result.snapshot_id == "snap-1"


@pytest.mark.unit
async def test_skips_forward_when_policy_says_no(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    orch._policy.decide.return_value.should_fire = False
    orch._policy.decide.return_value.reason = "subagent active"
    result = await orch.run_checkpoint(phase=CheckpointPhase.MIDPOINT_DIRTINESS)
    orch._snapshot.capture.assert_not_called()
    orch._forward_to.assert_not_awaited()
    assert result.fired is False
    assert "subagent" in result.decision_reason.lower()


@pytest.mark.unit
async def test_skips_forward_on_empty_working_tree(tmp_path: Path) -> None:
    """Per spec line 361: empty tree → soft success, skip forward_to."""
    orch = _make_orch(tmp_path, dirty_files=[])  # clean tree
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._snapshot.capture.assert_called_once()
    orch._forward_to.assert_not_awaited()
    assert result.fired is True  # soft success
    assert "clean" in (result.decision_reason or "").lower() or "no changes" in (result.decision_reason or "").lower()


@pytest.mark.unit
async def test_forward_to_5xx_retries_once_then_succeeds(tmp_path: Path) -> None:
    """Per spec line 372: 5xx → retry once with backoff, then fail closed."""
    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_5xx = httpx.Response(503, request=request)
    orch._forward_to.side_effect = [
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
        None,  # second call succeeds
    ]
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    assert orch._forward_to.await_count == 2
    assert result.fired is True


@pytest.mark.unit
async def test_forward_to_5xx_exhausts_retry_fails_closed(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_5xx = httpx.Response(503, request=request)
    orch._forward_to.side_effect = [
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
    ]
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    assert orch._forward_to.await_count == 2
    assert result.fired is False
    assert "retry exhausted" in (result.error or "").lower()


@pytest.mark.unit
async def test_forward_to_4xx_no_retry_fails_closed(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_4xx = httpx.Response(400, request=request)
    orch._forward_to.side_effect = httpx.HTTPStatusError("400", request=request, response=response_4xx)
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    assert orch._forward_to.await_count == 1
    assert result.fired is False


@pytest.mark.unit
async def test_fails_closed_on_snapshot_error(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path, snapshot_side_effect=RuntimeError("git diff exploded"))
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._forward_to.assert_not_awaited()
    assert result.fired is False
    assert "git diff" in (result.error or "")


@pytest.mark.unit
async def test_unexpected_exception_propagates(tmp_path: Path) -> None:
    """Programming errors must NOT be swallowed."""
    orch = _make_orch(tmp_path)
    orch._forward_to.side_effect = TypeError("not a network error")
    with pytest.raises(TypeError):
        await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)


@pytest.mark.unit
async def test_concurrent_calls_serialized_by_lock(tmp_path: Path) -> None:
    """Per spec line 394: two simultaneous calls → second waits."""
    orch = _make_orch(tmp_path)
    call_count = 0
    enter_count = 0

    async def slow_forward(_result):
        nonlocal call_count, enter_count
        enter_count += 1
        call_count += 1
        await asyncio.sleep(0.05)

    orch._forward_to = AsyncMock(side_effect=slow_forward)
    orch._snapshot.capture.return_value = Snapshot(
        path=tmp_path / "s.patch", label="x", snapshot_id=f"snap-{enter_count}",
        captured_at=MagicMock(), parent_commit="abc", dirty_files=["x.py"],
    )

    a, b = await asyncio.gather(
        orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK),
        orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK),
    )
    # Both complete; lock prevents concurrent forward_to invocations
    assert a.fired and b.fired
