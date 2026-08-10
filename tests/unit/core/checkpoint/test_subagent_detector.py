from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from session_buddy.checkpoint.subagent_detector import (
    LockfileSignalSource,
    SubagentDetector,
)


@pytest.mark.unit
def test_lockfile_signal_source_read_returns_false_when_missing(tmp_path: Path) -> None:
    src = LockfileSignalSource(tmp_path / "subagent.lock")
    assert src.read() is False


@pytest.mark.unit
def test_lockfile_signal_source_read_returns_true_when_present(tmp_path: Path) -> None:
    lock = tmp_path / "subagent.lock"
    lock.touch()
    assert LockfileSignalSource(lock).read() is True


@pytest.mark.unit
def test_lockfile_signal_source_write_creates_and_removes_lockfile(tmp_path: Path) -> None:
    lock = tmp_path / "subagent.lock"
    src = LockfileSignalSource(lock)
    src.write(active=True)
    assert lock.exists()
    src.write(active=False)
    assert not lock.exists()


@pytest.mark.unit
def test_subagent_detector_is_active_false_when_signal_false(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    assert detector.is_active() is False


@pytest.mark.unit
def test_subagent_detector_is_active_true_when_signal_true(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    lock.touch()
    assert SubagentDetector(tmp_path, LockfileSignalSource(lock)).is_active() is True


@pytest.mark.unit
async def test_wait_until_idle_returns_true_when_already_idle(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    assert await detector.wait_until_idle(timeout=0.1) is True


@pytest.mark.unit
async def test_wait_until_idle_returns_false_on_timeout(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    lock.touch()
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    assert await detector.wait_until_idle(timeout=0.05) is False


@pytest.mark.unit
async def test_wait_until_idle_returns_true_after_signal_cleared(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    src = LockfileSignalSource(lock)
    src.write(active=True)
    detector = SubagentDetector(tmp_path, src)

    async def clear_after_delay() -> None:
        await asyncio.sleep(0.05)
        src.write(active=False)

    asyncio.create_task(clear_after_delay())
    assert await detector.wait_until_idle(timeout=1.0) is True


@pytest.mark.unit
def test_subagent_detector_fails_open_when_lockfile_unreadable(tmp_path: Path) -> None:
    """If read() raises (e.g., permission denied), fail open to 'active' — safer to defer."""
    lock = tmp_path / "x.lock"
    lock.touch()
    lock.chmod(0o000)
    try:
        detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
        assert detector.is_active() is True  # fail open per spec invariant
    finally:
        lock.chmod(0o644)
