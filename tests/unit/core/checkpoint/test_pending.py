from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from session_buddy.checkpoint.pending import (
    MAX_MARKER_BYTES,
    PendingCheckpoint,
    consume_pending,
    consume_pending_marker,
    load_pending,
    save_pending,
)


# --- Round-trip and basic API -------------------------------------------------


@pytest.mark.unit
def test_save_then_load_round_trip(tmp_path: Path) -> None:
    pending = PendingCheckpoint(
        working_dir=tmp_path / "proj",
        reason="subagent_idle_timeout",
    )
    marker = save_pending(pending)
    assert marker.exists()

    loaded = load_pending(marker)
    assert loaded is not None
    assert loaded.reason == "subagent_idle_timeout"


@pytest.mark.unit
def test_load_pending_returns_none_for_missing_marker(tmp_path: Path) -> None:
    """C-4 coverage: load on a non-existent path returns None gracefully."""
    assert load_pending(tmp_path / "nonexistent.json") is None


@pytest.mark.unit
def test_load_pending_returns_pending_for_valid_marker(tmp_path: Path) -> None:
    """C-4 coverage: round-trip preserves working_dir, reason, created_at."""
    pending = PendingCheckpoint(
        working_dir=tmp_path / "proj",
        reason="subagent_idle_timeout",
    )
    marker = save_pending(pending)

    loaded = load_pending(marker)
    assert loaded is not None
    assert loaded.working_dir == pending.working_dir
    assert loaded.reason == pending.reason
    assert loaded.created_at == pending.created_at


@pytest.mark.unit
def test_consume_pending_removes_file(tmp_path: Path) -> None:
    pending = PendingCheckpoint(working_dir=tmp_path, reason="x")
    marker = save_pending(pending)
    consume_pending(marker)
    assert not marker.exists()


# --- C-6: atomic write --------------------------------------------------------


@pytest.mark.unit
def test_save_pending_writes_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """C-6: save_pending MUST use a .tmp + os.replace atomic rename.

    Verifies observable filesystem behavior: ``os.replace`` is called
    AFTER the tmp file is written, and no stray .tmp file is left behind
    on success.
    """
    pending = PendingCheckpoint(working_dir=tmp_path, reason="atomic")

    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def tracking_replace(src: str | bytes | os.PathLike[str], dst: str | bytes | os.PathLike[str]) -> None:
        replace_calls.append((Path(os.fspath(src)), Path(os.fspath(dst))))
        real_replace(src, dst)

    monkeypatch.setattr("session_buddy.checkpoint.pending.os.replace", tracking_replace)

    marker = save_pending(pending)

    # os.replace was called exactly once with a .tmp src → marker dst.
    assert len(replace_calls) == 1, f"expected 1 os.replace call, got {len(replace_calls)}"
    src, dst = replace_calls[0]
    assert src.suffix == ".tmp" or src.name.endswith(".tmp"), f"unexpected tmp suffix: {src}"
    assert dst == marker
    # Final marker exists, no stray .tmp file remains.
    assert marker.exists()
    assert not src.exists()


@pytest.mark.unit
def test_save_pending_atomic_failure_does_not_leave_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If os.replace fails, the marker MUST NOT exist (atomic guarantee).

    The OSError propagates so callers can retry; only the partial .tmp
    file is cleaned up, never a half-written marker.
    """
    pending = PendingCheckpoint(working_dir=tmp_path, reason="atomic-fail")

    def boom_replace(src: str | bytes | os.PathLike[str], dst: str | bytes | os.PathLike[str]) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("session_buddy.checkpoint.pending.os.replace", boom_replace)

    marker_path = pending.marker_path
    with pytest.raises(OSError, match="simulated replace failure"):
        save_pending(pending)
    # Marker does NOT exist at its final path (atomic guarantee).
    assert not marker_path.exists()


# --- C-6: oversize marker cap -------------------------------------------------


@pytest.mark.unit
def test_load_pending_raises_on_oversize_marker(tmp_path: Path) -> None:
    """C-6: a marker > MAX_MARKER_BYTES MUST raise to prevent OOM.

    The marker is malformed-by-size: even if it parses as valid JSON, we
    refuse to deserialize it before reading the whole file.
    """
    pending = PendingCheckpoint(working_dir=tmp_path, reason="oversize")
    marker = save_pending(pending)

    # Reserialize valid JSON but pad the reason so the file exceeds the cap.
    large_reason = "x" * (MAX_MARKER_BYTES + 1024)
    payload = (
        '{"working_dir": "'
        + str(pending.working_dir)
        + '", "reason": "'
        + large_reason
        + '", "created_at": "'
        + pending.created_at.isoformat()
        + '"}'
    )
    marker.write_text(payload, encoding="utf-8")

    assert marker.stat().st_size > MAX_MARKER_BYTES

    with pytest.raises(ValueError, match="too large"):
        load_pending(marker)


@pytest.mark.unit
def test_load_pending_accepts_marker_at_or_below_max(tmp_path: Path) -> None:
    """A marker at or below MAX_MARKER_BYTES is accepted (boundary sanity)."""
    pending = PendingCheckpoint(working_dir=tmp_path, reason="boundary")
    marker = save_pending(pending)
    size = marker.stat().st_size
    assert size <= MAX_MARKER_BYTES
    loaded = load_pending(marker)
    assert loaded is not None


# --- C-6: malformed marker handling -------------------------------------------


@pytest.mark.unit
async def test_consume_pending_marker_deletes_malformed_marker(tmp_path: Path) -> None:
    """C-6: malformed marker MUST be logged + deleted, NOT looped forever.

    Observable: orchestrator is NOT awaited, marker is deleted, warning
    is logged. A poison marker that fails to parse must not survive.
    """
    from session_buddy.checkpoint import pending as pending_mod
    from session_buddy.checkpoint.pending import PENDING_DIR

    # Write a malformed marker directly to disk.
    marker = PENDING_DIR / f"{tmp_path.name.replace('/', '_').replace('.', '_')}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{not valid json", encoding="utf-8")
    assert marker.exists()

    build_orchestrator = AsyncMock()

    with patch.object(pending_mod, "_log") as mock_log:
        await consume_pending_marker(marker, build_orchestrator=build_orchestrator)

    # Orchestrator was NEVER awaited.
    build_orchestrator.assert_not_awaited()
    # Marker file was removed (best-effort).
    assert not marker.exists()
    # Warning was logged with the marker path and exception type.
    assert mock_log.warning.called
    call_kwargs = mock_log.warning.call_args.kwargs
    assert call_kwargs["extra"]["marker"] == str(marker)


@pytest.mark.unit
async def test_consume_pending_marker_handles_missing_marker(tmp_path: Path) -> None:
    """Marker deleted between glob and load (race): return gracefully, no await."""
    from session_buddy.checkpoint import pending as pending_mod

    marker = tmp_path / "vanished.json"
    # Don't create the file — simulates a race where another worker
    # consumed the marker before we got to it.
    build_orchestrator = AsyncMock()

    with patch.object(pending_mod, "_log") as mock_log:
        await consume_pending_marker(marker, build_orchestrator=build_orchestrator)

    build_orchestrator.assert_not_awaited()
    # No warning logged — missing is the normal race case, not an error.


# --- C-4: behavioral coverage of consume_pending_marker ----------------------


@pytest.mark.unit
async def test_consume_pending_marker_runs_orchestrator_on_valid_marker(
    tmp_path: Path,
) -> None:
    """C-4: behavioral coverage for the happy path of consume_pending_marker.

    A valid marker MUST be loaded, the orchestrator MUST be awaited at
    END_OF_TASK, and the marker MUST be removed after a successful run.
    """
    from session_buddy.checkpoint import pending as pending_mod

    pending = PendingCheckpoint(working_dir=tmp_path, reason="happy")
    marker = save_pending(pending)
    assert marker.exists()

    build_calls: list[Path] = []
    run_calls: list[dict[str, str]] = []

    class _FakeOrch:
        def __init__(self, *_a: object, **_kw: object) -> None:
            pass

        async def run_checkpoint(self, *, phase: str) -> None:
            run_calls.append({"phase": phase})

    async def _build(wd: Path) -> _FakeOrch:
        build_calls.append(wd)
        return _FakeOrch()

    with patch.object(pending_mod, "_log"):
        await consume_pending_marker(marker, build_orchestrator=_build)

    # Builder was called with the pending working_dir.
    assert build_calls == [tmp_path]
    # Orchestrator was run at END_OF_TASK.
    assert run_calls and run_calls[0]["phase"] == "end_of_task"
    # Marker is removed AFTER the orchestrator fires.
    assert not marker.exists()


@pytest.mark.unit
async def test_consume_pending_marker_unlinks_after_success(tmp_path: Path) -> None:
    """C-4: marker MUST be removed after orchestrator succeeds."""
    from session_buddy.checkpoint import pending as pending_mod

    pending = PendingCheckpoint(working_dir=tmp_path, reason="unlink")
    marker = save_pending(pending)

    class _FakeOrch:
        async def run_checkpoint(self, *, phase: str) -> None:
            return None

    async def _build(_wd: Path) -> _FakeOrch:
        return _FakeOrch()

    with patch.object(pending_mod, "_log"):
        await consume_pending_marker(marker, build_orchestrator=_build)

    assert not marker.exists()


@pytest.mark.unit
async def test_consume_pending_marker_keeps_marker_on_failure(tmp_path: Path) -> None:
    """C-4: marker MUST stay on disk if the orchestrator raises.

    Retries from the next tick depend on the marker surviving; otherwise
    a transient failure silently drops the deferred checkpoint.
    """
    from session_buddy.checkpoint import pending as pending_mod

    pending = PendingCheckpoint(working_dir=tmp_path, reason="retry")
    marker = save_pending(pending)

    class _FlakyOrch:
        async def run_checkpoint(self, *, phase: str) -> None:
            raise RuntimeError("orchestrator failure")

    async def _build(_wd: Path) -> _FlakyOrch:
        return _FlakyOrch()

    # The exception bubbles up — caller (auto_checkpoint_loop / end_session)
    # is responsible for catching it. The marker MUST remain for retry.
    with patch.object(pending_mod, "_log"), pytest.raises(RuntimeError, match="orchestrator failure"):
        await consume_pending_marker(marker, build_orchestrator=_build)

    assert marker.exists(), "marker must remain on disk for next tick to retry"


# --- metrics sanity (existing) ------------------------------------------------


@pytest.mark.unit
def test_metrics_inc_failure_counts_by_reason() -> None:
    from session_buddy.checkpoint.metrics import CheckpointMetrics

    m = CheckpointMetrics()
    m.inc_failure("subagent_idle_timeout")
    m.inc_failure("subagent_idle_timeout")
    m.inc_failure("forward_transient_retry_exhausted")
    assert m.failures["subagent_idle_timeout"] == 2
    assert m.failures["forward_transient_retry_exhausted"] == 1
