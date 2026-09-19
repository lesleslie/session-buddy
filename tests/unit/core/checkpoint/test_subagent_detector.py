from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from session_buddy.checkpoint.subagent_detector import (
    DefaultSubagentLifecycleHook,
    LockfileSignalSource,
    SubagentDetector,
    SubagentMetadata,
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


@pytest.mark.unit
def test_lockfile_signal_source_read_oserror_returns_true(tmp_path: Path) -> None:
    """Coverage: lines 35-37 (read OSError fail-open path)."""

    class _BoomPath:
        def exists(self) -> bool:
            raise OSError("simulated stat failure")

    src = LockfileSignalSource(tmp_path / "x.lock")  # type: ignore[arg-type]
    src._path = _BoomPath()  # type: ignore[assignment]
    assert src.read() is True  # fail open


@pytest.mark.unit
def test_lockfile_signal_source_write_oserror_swallowed(tmp_path: Path) -> None:
    """Coverage: lines 46-47 (write OSError swallow)."""

    class _BoomPath:
        def __init__(self) -> None:
            self.parent = _BoomParent()

        def unlink(self, missing_ok: bool = False) -> None:
            raise OSError("simulated unlink failure")

    class _BoomParent:
        def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
            raise OSError("simulated mkdir failure")

    src = LockfileSignalSource(tmp_path / "x.lock")  # type: ignore[arg-type]
    src._path = _BoomPath()  # type: ignore[assignment]
    # Both branches must swallow the error (no raise).
    src.write(active=True)
    src.write(active=False)


@pytest.mark.unit
def test_subagent_detector_is_active_signal_raises_fails_open(tmp_path: Path) -> None:
    """Coverage: lines 58-63 (SubagentDetector.is_active signal-raises fail-open)."""

    class _ExplodingSignal:
        def read(self) -> bool:
            raise RuntimeError("simulated signal explosion")

        def write(self, active: bool) -> None:
            pass

    detector = SubagentDetector(tmp_path, _ExplodingSignal())  # type: ignore[arg-type]
    assert detector.is_active() is True  # fail open


# ---------------------------------------------------------------------------
# Producer-surface tests (SubagentDetector.write / SubagentLifecycleHook).
# These cover the producer half of the lockfile contract that was previously
# dormant (see docs/checkpoint/STASH_CLOBBER.md for the cross-repo story).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_subagent_detector_write_creates_lockfile(tmp_path: Path) -> None:
    """SubagentDetector.write(active=True) creates the lockfile."""
    lock = tmp_path / "x.lock"
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    detector.write(active=True)
    assert lock.exists()


@pytest.mark.unit
def test_subagent_detector_write_payload_is_json(tmp_path: Path) -> None:
    """SubagentDetector.write writes a JSON payload with all four metadata fields
    atomically (no .tmp.* sibling left behind after the write completes)."""
    lock = tmp_path / "x.lock"
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    meta = SubagentMetadata(
        pid=4242,
        started_at_ms=1_700_000_000_000,
        node_id="node-x",
        parent_agent_id="parent-y",
    )
    detector.write(active=True, metadata=meta)

    # The lockfile is a JSON document with all four fields.
    payload = json.loads(lock.read_text())
    assert payload == {
        "pid": 4242,
        "started_at_ms": 1_700_000_000_000,
        "node_id": "node-x",
        "parent_agent_id": "parent-y",
    }

    # Atomicity invariant: no leftover tmp sibling.
    siblings = list(tmp_path.glob("x.lock.*"))
    assert siblings == [], f"expected no tmp siblings, found {siblings!r}"


@pytest.mark.unit
def test_subagent_detector_write_default_metadata_uses_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When metadata is omitted, env vars + os.getpid fill the payload."""
    monkeypatch.setenv("SESSION_BUDDY_NODE_ID", "node-from-env")
    monkeypatch.setenv("SESSION_BUDDY_PARENT_AGENT_ID", "parent-from-env")

    lock = tmp_path / "x.lock"
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    detector.write(active=True)

    payload = json.loads(lock.read_text())
    assert payload["pid"] == os.getpid()
    assert payload["node_id"] == "node-from-env"
    assert payload["parent_agent_id"] == "parent-from-env"
    assert isinstance(payload["started_at_ms"], int)


@pytest.mark.unit
def test_subagent_detector_write_removes_lockfile_on_end(tmp_path: Path) -> None:
    """SubagentDetector.write(active=False) unlinks the lockfile."""
    lock = tmp_path / "x.lock"
    lock.touch()
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    detector.write(active=False)
    assert not lock.exists()


@pytest.mark.unit
def test_default_subagent_lifecycle_hook_on_start_writes_lockfile(
    tmp_path: Path,
) -> None:
    """DefaultSubagentLifecycleHook.on_subagent_start writes the lockfile."""
    hook = DefaultSubagentLifecycleHook()
    meta = SubagentMetadata(
        pid=9999,
        started_at_ms=1_700_000_001_000,
        node_id="hook-node",
        parent_agent_id="hook-parent",
    )
    hook.on_subagent_start(tmp_path, meta)

    lock = tmp_path / ".session-buddy" / "subagent.lock"
    assert lock.exists()
    payload = json.loads(lock.read_text())
    assert payload["pid"] == 9999
    assert payload["node_id"] == "hook-node"


@pytest.mark.unit
def test_default_subagent_lifecycle_hook_on_end_removes_lockfile(
    tmp_path: Path,
) -> None:
    """DefaultSubagentLifecycleHook.on_subagent_end removes the lockfile."""
    hook = DefaultSubagentLifecycleHook()
    meta = SubagentMetadata(
        pid=9999,
        started_at_ms=1_700_000_002_000,
        node_id="hook-node",
        parent_agent_id="hook-parent",
    )
    hook.on_subagent_start(tmp_path, meta)
    hook.on_subagent_end(tmp_path)

    lock = tmp_path / ".session-buddy" / "subagent.lock"
    assert not lock.exists()


@pytest.mark.unit
def test_default_subagent_lifecycle_hook_uses_injected_factory(tmp_path: Path) -> None:
    """The injected detector_factory controls which SubagentDetector the hook uses."""

    class _RecordingDetector:
        def __init__(self) -> None:
            self.started: SubagentMetadata | None = None
            self.ended = False

        def write(
            self, active: bool, metadata: SubagentMetadata | None = None
        ) -> None:
            if active and metadata is not None:
                self.started = metadata
            elif not active:
                self.ended = True

    rec = _RecordingDetector()
    hook = DefaultSubagentLifecycleHook(detector_factory=lambda _wd: rec)  # type: ignore[arg-type]
    meta = SubagentMetadata(
        pid=1234,
        started_at_ms=1_700_000_003_000,
        node_id="n",
        parent_agent_id="p",
    )
    hook.on_subagent_start(tmp_path, meta)
    hook.on_subagent_end(tmp_path)

    assert rec.started == meta
    assert rec.ended is True
