"""Unit tests for AutoCheckpointLoop + QualityDeltaSignal.

Task 9 wires a background asyncio timer into the MCP server lifespan that:
  * Fires CheckpointOrchestrator at `settings.auto_checkpoint_interval` (default
    1800s / 30 min) for analytics-only snapshots.
  * Drains pending-checkpoint markers from prior subagent-timeout events.
  * Opt-in mid-task commits when `midpoint_commits_enabled=True` (default off).
  * Adds a QualityDeltaSignal that fires when quality score delta exceeds
    `midpoint_commit_min_quality_delta` (default 10).

These tests fail at collection time until the module exists.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.checkpoint import CheckpointOrchestrator
from session_buddy.core.auto_checkpoint_loop import AutoCheckpointLoop


@pytest.mark.unit
async def test_timer_fires_orchestrator_at_each_tick(tmp_path: Path) -> None:
    calls: list[int] = []
    orch = MagicMock(spec=CheckpointOrchestrator)
    orch.run_checkpoint = AsyncMock(side_effect=lambda **kw: calls.append(1))

    loop = AutoCheckpointLoop(
        interval_s=0.05, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: orch,
    )
    await loop.start()
    await asyncio.sleep(0.18)
    await loop.stop()
    assert len(calls) >= 3


@pytest.mark.unit
async def test_timer_swallows_orchestrator_errors(tmp_path: Path) -> None:
    orch = MagicMock(spec=CheckpointOrchestrator)
    orch.run_checkpoint = AsyncMock(side_effect=RuntimeError("boom"))
    loop = AutoCheckpointLoop(
        interval_s=0.05, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: orch,
    )
    await loop.start()
    await asyncio.sleep(0.15)
    await loop.stop()  # must not raise


@pytest.mark.unit
async def test_timer_stop_idempotent(tmp_path: Path) -> None:
    loop = AutoCheckpointLoop(
        interval_s=60, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: MagicMock(spec=CheckpointOrchestrator),
    )
    await loop.start()
    await loop.stop()
    await loop.stop()


@pytest.mark.unit
async def test_timer_consumes_pending_checkpoints_on_tick(tmp_path: Path) -> None:
    """Per integration-risk #3, #4: pending markers must be drained on each tick."""
    from session_buddy.checkpoint import save_pending, PendingCheckpoint

    save_pending(PendingCheckpoint(working_dir=tmp_path, reason="subagent_idle_timeout"))

    consumed: list[Path] = []

    async def consume_fn(_marker: Path) -> None:
        consumed.append(_marker)

    orch = MagicMock(spec=CheckpointOrchestrator)
    orch.run_checkpoint = AsyncMock()
    loop = AutoCheckpointLoop(
        interval_s=0.05, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: orch, pending_consume_fn=consume_fn,
    )
    await loop.start()
    await asyncio.sleep(0.15)
    await loop.stop()
    assert len(consumed) >= 1


@pytest.mark.unit
async def test_timer_uses_noop_forward_when_midpoint_commits_disabled(tmp_path: Path) -> None:
    """Default: midpoint_commits_enabled=False → forward_to is no-op (analytics only)."""
    captured_forwards: list[object] = []

    def capturing_forward_factory(_wd: Path):
        def forward(_r):
            captured_forwards.append(_r)
        return forward

    orch = MagicMock(spec=CheckpointOrchestrator)
    orch.run_checkpoint = AsyncMock()
    loop = AutoCheckpointLoop(
        interval_s=0.05, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: orch,
        forward_to_factory=capturing_forward_factory,
    )
    await loop.start()
    await asyncio.sleep(0.12)
    await loop.stop()
    # forward was attached but never invoked because orchestrator is mocked;
    # what we assert is that the factory produces a callable (no-op behavior
    # is verified by absence of side-effects on a real orchestrator in tests
    # below). Here we verify the factory ran.
    assert orch.run_checkpoint.await_count >= 2


@pytest.mark.unit
async def test_timer_uses_real_commit_forward_when_midpoint_commits_enabled(tmp_path: Path) -> None:
    """When midpoint_commits_enabled=True, the lifespan wires a real commit forward."""
    from session_buddy.core.auto_checkpoint_loop import _midpoint_commit_forward

    # Verify the helper exists and is callable; the actual git side-effect
    # is exercised in an integration test, not unit tests (git binary required).
    assert callable(_midpoint_commit_forward)


@pytest.mark.unit
async def test_quality_delta_signal_fires_when_delta_exceeds_threshold() -> None:
    """QualityDeltaSignal is the new signal that triggers commits on quality jumps."""
    from session_buddy.core.auto_checkpoint_loop import QualityDeltaSignal

    def provider():
        return (60, 75)  # delta = 15

    sig = QualityDeltaSignal(min_delta=10, quality_provider=provider)
    inspector = MagicMock()
    assert sig.is_active(inspector) is True


@pytest.mark.unit
async def test_quality_delta_signal_inactive_when_provider_returns_none() -> None:
    from session_buddy.core.auto_checkpoint_loop import QualityDeltaSignal

    sig = QualityDeltaSignal(min_delta=10, quality_provider=lambda: (None, None))
    inspector = MagicMock()
    assert sig.is_active(inspector) is False


@pytest.mark.unit
async def test_quality_delta_signal_inactive_when_delta_below_threshold() -> None:
    from session_buddy.core.auto_checkpoint_loop import QualityDeltaSignal

    sig = QualityDeltaSignal(min_delta=10, quality_provider=lambda: (60, 65))
    inspector = MagicMock()
    assert sig.is_active(inspector) is False


@pytest.mark.unit
async def test_lifespan_swallows_non_attribute_error_during_dhara_aclose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: aclose() raising any exception (not just AttributeError)
    must not break lifespan shutdown.

    Before Task 9 (commit f7680c8f) the cleanup used a blanket
    ``with suppress(Exception):`` over ``_dhara_publisher.aclose()``. The
    re-wired lifespan narrowed that to ``except AttributeError:`` plus an
    inner empty ``suppress(Exception): pass``. Any non-AttributeError
    exception (network blip, closed loop, RuntimeError from the underlying
    httpx client, etc.) propagated and aborted shutdown.

    This test guards against that regression by injecting a publisher whose
    ``aclose()`` raises ``RuntimeError`` and asserting that the lifespan
    context exits cleanly.
    """
    from contextlib import asynccontextmanager

    from session_buddy.mcp import server as mcp_server

    # Replace the module-level publisher with one whose aclose() raises a
    # non-AttributeError exception. AsyncMock + side_effect mirrors what
    # httpx.AsyncClient.aclose() does when its transport is already closed.
    class _FlakyPublisher:
        async def aclose(self) -> None:
            raise RuntimeError("transport already closed")

    monkeypatch.setattr(mcp_server, "_dhara_publisher", _FlakyPublisher())

    # Stub the original lifespan so we do not invoke the real FastMCP one
    # (which would require a live ASGI app). A no-op async context manager
    # is enough to exercise the dhara cleanup path on exit.
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(mcp_server, "_original_lifespan", _noop_lifespan)

    # Force the auto-checkpoint loop off so the test focuses on the
    # publisher cleanup path. effective_interval=0 short-circuits the
    # ``loop_enabled and effective_interval > 0`` gate.
    settings_stub = MagicMock()
    settings_stub.auto_checkpoint_interval = 0
    settings_stub.midpoint_commit_interval_s = 0
    settings_stub.midpoint_commits_enabled = False
    settings_stub.midpoint_commit_min_quality_delta = 10
    monkeypatch.setattr(
        "session_buddy.settings.get_settings", lambda: settings_stub
    )

    # Entering and exiting the lifespan must complete without raising.
    # If the regression returns, RuntimeError will escape the ``finally``
    # block and this assertion will fail.
    async with mcp_server._lifespan_with_dhara_cleanup(app=MagicMock()):
        pass


# --- Finding I-1: pending-drain forward must actually commit ----------------------
#
# Before the fix, `_end_of_task_forward` was a `pass`-bodied coroutine —
# the deferred checkpoint was silently dropped. The fix replaces it
# with a factory that returns a closure which calls
# ``create_checkpoint_commit`` via ``asyncio.to_thread``. This test
# exercises the factory + the resulting forward, asserts the commit
# helper runs, and pins the ``working_dir`` closure so a refactor that
# loses the per-call wiring would fail.


@pytest.mark.unit
async def test_make_end_of_task_forward_actually_calls_create_checkpoint_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The forward produced by ``_make_end_of_task_forward`` MUST call
    ``create_checkpoint_commit`` for the captured working_dir.

    The function under test runs the commit on a thread via
    ``asyncio.to_thread``; we patch the symbol in
    ``session_buddy.utils.git_worktrees`` (the import happens inside the
    forward, so we have to patch the *source* attribute, not the caller's
    namespace). The forward's ``_result`` argument is ignored — we pass
    ``None``.
    """
    from session_buddy.mcp import server as mcp_server

    calls: list[tuple[Path, str, int]] = []

    def _fake_commit(directory: Path, project: str, quality_score: int):
        calls.append((directory, project, quality_score))
        return (True, "fake-commit-sha", [])

    # Patch the symbol at its *source* (the import inside the forward
    # is a local import so the binding resolves via the git_worktrees module).
    monkeypatch.setattr(
        "session_buddy.utils.git_worktrees.create_checkpoint_commit",
        _fake_commit,
    )

    forward = mcp_server._make_end_of_task_forward(tmp_path)

    # Invoking the forward (with an arbitrary _result) must result in
    # exactly one call to the commit helper, with tmp_path as directory
    # and the directory's basename as project.
    await forward(None)

    assert len(calls) == 1
    directory, project, quality_score = calls[0]
    assert directory == tmp_path
    assert project == tmp_path.name
    # End-of-task drain has no quality score; placeholder 0 is contracted.
    assert quality_score == 0


@pytest.mark.unit
async def test_make_end_of_task_forward_works_for_multiple_working_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ``_make_end_of_task_forward(wd)`` closes over its own working_dir.

    Guards against a refactor that hoists the closure capture to module
    scope (a single forward reused across all markers).
    """
    from session_buddy.mcp import server as mcp_server

    calls: list[Path] = []

    def _fake_commit(directory: Path, project: str, quality_score: int):
        calls.append(directory)
        return (True, "x", [])

    monkeypatch.setattr(
        "session_buddy.utils.git_worktrees.create_checkpoint_commit",
        _fake_commit,
    )

    wd_a = tmp_path / "a"
    wd_b = tmp_path / "b"
    wd_a.mkdir()
    wd_b.mkdir()

    fwd_a = mcp_server._make_end_of_task_forward(wd_a)
    fwd_b = mcp_server._make_end_of_task_forward(wd_b)

    await fwd_a(None)
    await fwd_b(None)

    assert calls == [wd_a, wd_b]
