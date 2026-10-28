from __future__ import annotations

import json
import os
import stat
import threading
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
def test_save_pending_writes_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-6: save_pending MUST use a .tmp + os.replace atomic rename.

    Verifies observable filesystem behavior: ``os.replace`` is called
    AFTER the tmp file is written, and no stray .tmp file is left behind
    on success.
    """
    pending = PendingCheckpoint(working_dir=tmp_path, reason="atomic")

    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def tracking_replace(
        src: str | bytes | os.PathLike[str], dst: str | bytes | os.PathLike[str]
    ) -> None:
        replace_calls.append((Path(os.fspath(src)), Path(os.fspath(dst))))
        real_replace(src, dst)

    monkeypatch.setattr("session_buddy.utils.atomic_write.os.replace", tracking_replace)

    marker = save_pending(pending)

    # os.replace was called exactly once with a .tmp src → marker dst.
    assert len(replace_calls) == 1, (
        f"expected 1 os.replace call, got {len(replace_calls)}"
    )
    src, dst = replace_calls[0]
    assert src.suffix == ".tmp" or src.name.endswith(".tmp"), (
        f"unexpected tmp suffix: {src}"
    )
    assert dst == marker
    # The temp name is unique, not the old fixed "<marker>.json.tmp" that
    # every writer of a marker shared.
    assert src != marker.with_name(marker.name + ".tmp")
    # Final marker exists, no stray .tmp file remains.
    assert marker.exists()
    assert not src.exists()


@pytest.mark.unit
def test_save_pending_atomic_failure_does_not_leave_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pending_dir: Path,
) -> None:
    """If os.replace fails, the marker MUST NOT exist (atomic guarantee).

    The OSError propagates so callers can retry; only the partial .tmp
    file is cleaned up, never a half-written marker.
    """
    pending = PendingCheckpoint(working_dir=tmp_path, reason="atomic-fail")

    def boom_replace(
        src: str | bytes | os.PathLike[str], dst: str | bytes | os.PathLike[str]
    ) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("session_buddy.utils.atomic_write.os.replace", boom_replace)

    marker_path = pending.marker_path
    with pytest.raises(OSError, match="simulated replace failure"):
        save_pending(pending)
    # Marker does NOT exist at its final path (atomic guarantee).
    assert not marker_path.exists()
    # The orphaned temp file is cleaned up, not left behind.
    assert list(pending_dir.iterdir()) == []


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
    with (
        patch.object(pending_mod, "_log"),
        pytest.raises(RuntimeError, match="orchestrator failure"),
    ):
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


# --- atomic, owner-only marker publication -------------------------------------
#
# ``save_pending`` used to write through a *fixed-name* temp file
# (``<marker>.json.tmp``) and then ``os.replace`` it into place. That
# shares one temp file between every writer of the same marker, reuses
# whatever a crashed earlier write left behind, and follows a symlink
# planted at the predictable temp path.


@pytest.fixture
def pending_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the module-level PENDING_DIR into the test's tmp_path."""
    from session_buddy.checkpoint import pending as pending_mod

    target = tmp_path / "pending"
    monkeypatch.setattr(pending_mod, "PENDING_DIR", target)
    return target


@pytest.mark.unit
def test_save_pending_publishes_the_marker_owner_only(pending_dir: Path) -> None:
    pending = PendingCheckpoint(working_dir=Path("/tmp/proj"), reason="timeout")
    marker = save_pending(pending)

    assert stat.S_IMODE(marker.stat().st_mode) == 0o600


@pytest.mark.unit
def test_save_pending_leaves_no_temp_file_behind(pending_dir: Path) -> None:
    pending = PendingCheckpoint(working_dir=Path("/tmp/proj"), reason="timeout")
    marker = save_pending(pending)

    leftovers = [p.name for p in marker.parent.iterdir() if p != marker]
    assert not leftovers, f"the writer left files behind: {leftovers}"


@pytest.mark.unit
def test_a_stale_temp_file_cannot_leak_its_permissions(pending_dir: Path) -> None:
    """A leftover temp file from a crashed write must not be reused.

    ``Path.write_text`` truncates an existing file *in place* and keeps
    its mode, so a stale temp left at 0644 would publish the marker at
    0644 no matter what the writer intended.
    """
    pending = PendingCheckpoint(working_dir=Path("/tmp/proj"), reason="timeout")
    stale = pending.marker_path.with_name(pending.marker_path.name + ".tmp")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("poison")
    stale.chmod(0o644)

    marker = save_pending(pending)

    assert "poison" not in marker.read_text()
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600


@pytest.mark.unit
def test_a_symlinked_temp_path_is_not_written_through(pending_dir: Path) -> None:
    """The old temp name was ``<marker>.json.tmp``; it must not be reused.

    ``Path.write_text`` opens with ``O_CREAT | O_TRUNC``, which follows
    a symlink -- so a planted link would have its target overwritten.
    """
    pending = PendingCheckpoint(working_dir=Path("/tmp/proj"), reason="timeout")
    victim = pending_dir / "victim.txt"
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text("precious")
    pending.marker_path.with_name(pending.marker_path.name + ".tmp").symlink_to(victim)

    marker = save_pending(pending)

    assert victim.read_text() == "precious"
    assert json.loads(marker.read_text())["reason"] == "timeout"


@pytest.mark.unit
def test_concurrent_saves_all_succeed(pending_dir: Path) -> None:
    """Every writer of one marker must survive.

    With a fixed temp name the first writer to rename moves the file
    away from the others, whose rename then raises
    ``FileNotFoundError``.
    """
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def writer() -> None:
        try:
            barrier.wait()
            for _ in range(25):
                save_pending(
                    PendingCheckpoint(working_dir=Path("/tmp/proj"), reason="timeout")
                )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"concurrent saves raised: {errors[:3]}"
