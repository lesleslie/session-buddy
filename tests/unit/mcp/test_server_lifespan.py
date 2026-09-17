"""Lifespan tests for the MCP server — guard Finding C-7.

Finding C-7: ``mcp/server.py`` passed ``Path(os.getcwd())`` straight to
``_build_orchestrator`` without validation. A prompt-injection gadget
that ``cd /`` would let ``LockfileSignalSource`` create
``/.session-buddy/subagent.lock`` at filesystem root.

The fix extracted ``_validate_orchestrator_path`` to a module-level
``validate_orchestrator_working_dir`` and wired it into the lifespan
startup. This module exercises that wiring.

Phase 8 Task 7 update: the previous version of this module installed
a stub ``dhara.schema`` module into ``sys.modules`` at import time so
that ``session_buddy.channel.state_writer`` could `from dhara.schema
import ChannelSessionState, validate`. After the migration,
``state_writer`` imports its types from the local
``session_buddy.channel._models`` module — no ``dhara.schema``
dependency, no stub needed. The stub machinery is deleted here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def _clean_pending_dir() -> Iterator[None]:
    """Per-test cleanup of ``~/.session-buddy/pending/*.json``.

    The lifespan's ``_drain_pending`` path iterates every pending
    marker on disk. Stale markers from prior test runs would feed
    ``_consume_pending`` → ``_build_orchestrator`` even with an invalid
    ``os.getcwd()`` (the marker carries its own ``working_dir``, not
    derived from cwd). We snapshot the markers' content before each
    test, restore it after, and remove any markers the test created.

    This is test-isolation scaffolding, NOT production code.
    """
    from session_buddy.checkpoint.pending import PENDING_DIR

    if not PENDING_DIR.exists():
        yield
        return

    snapshot: dict[str, str] = {
        marker.name: marker.read_text() for marker in PENDING_DIR.glob("*.json")
    }
    for marker in PENDING_DIR.glob("*.json"):
        marker.unlink(missing_ok=True)
    try:
        yield
    finally:
        for marker in PENDING_DIR.glob("*.json"):
            marker.unlink(missing_ok=True)
        for name, content in snapshot.items():
            (PENDING_DIR / name).write_text(content)


@pytest.mark.unit
async def test_lifespan_skips_orchestrator_for_invalid_cwd(
    monkeypatch: pytest.MonkeyPatch,
    _clean_pending_dir: None,
) -> None:
    """When ``os.getcwd()`` returns a non-existent path, the lifespan
    must validate and skip orchestrator construction.

    Before the fix, ``Path(os.getcwd())`` flowed straight into
    ``_build_orchestrator`` which then created
    ``/<cwd>/.session-buddy/subagent.lock`` at filesystem root —
    a prompt-injection gadget any caller controlling cwd could
    weaponize. The fix invokes ``validate_orchestrator_working_dir``
    BEFORE constructing the orchestrator; on failure, the loop is
    never started and the orchestrator never runs.
    """
    from session_buddy.mcp import server as mcp_server

    # Force os.getcwd to return a path that does not exist.
    # Patch the call site where validation actually reads cwd:
    # ``validate_orchestrator_working_dir`` lives in
    # ``session_buddy.core.session_manager`` and calls ``os.getcwd``
    # via the module-level import there.
    monkeypatch.setattr(
        "session_buddy.core.session_manager.os.getcwd",
        lambda: "/nonexistent/xyz/lifespan-bogus-cwd-12345",
    )

    # Pin mode to standard (enable_auto_checkpoint=True) so the loop
    # is enabled by the lifespan gate and would have been started if
    # validation were absent.
    fake_mode_cfg = MagicMock()
    fake_mode_cfg.enable_auto_checkpoint = True

    class _FakeMode:
        def get_config(self):
            return fake_mode_cfg

    monkeypatch.setattr("session_buddy.modes.get_mode", lambda: _FakeMode())

    # Replace the original FastMCP lifespan with a no-op so we don't
    # need a real ASGI app.
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(mcp_server, "_original_lifespan", _noop_lifespan)

    # Enable the auto-checkpoint loop (interval > 0). Without the
    # fix, the loop would be started and would invoke
    # ``_build_orchestrator`` on its first tick.
    settings_stub = MagicMock()
    settings_stub.auto_checkpoint_interval = 60
    settings_stub.midpoint_commit_interval_s = 60
    settings_stub.midpoint_commits_enabled = False
    settings_stub.midpoint_commit_min_quality_delta = 10
    monkeypatch.setattr(
        "session_buddy.settings.get_settings", lambda: settings_stub,
    )

    # Track every call to _build_orchestrator — both from the
    # orch_factory inside AutoCheckpointLoop and from any pending
    # marker drain via _consume_pending.
    build_calls: list[Path] = []
    real_build = mcp_server._build_orchestrator

    def _tracking_build(wd, *args, **kwargs):
        build_calls.append(wd)
        return real_build(wd, *args, **kwargs)

    monkeypatch.setattr(mcp_server, "_build_orchestrator", _tracking_build)

    # Run the lifespan. Allow a brief window so any wrongly-started
    # loop could tick at least once. With stale markers removed by
    # the fixture, only ``_tick`` could plausibly construct the
    # orchestrator — and only if the resolver let an invalid cwd
    # through.
    async with mcp_server._lifespan_with_dhara_cleanup(app=MagicMock()):
        await asyncio.sleep(0.05)

    # The orchestrator must not have been constructed when cwd is
    # invalid. The lifespan must validate cwd first and skip on failure.
    assert build_calls == [], (
        "lifespan constructed the orchestrator with an invalid cwd "
        f"({len(build_calls)} call(s)) — Finding C-7 still present"
    )


@pytest.mark.unit
async def test_lifespan_starts_orchestrator_for_valid_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    _clean_pending_dir: None,
) -> None:
    """Positive control: a valid cwd lets the orchestrator fire.

    Pins the strong-form behavior so the invalid-cwd test cannot pass
    vacuously (e.g. via a typo in the patching target that masked the
    collaborator).
    """
    from session_buddy.mcp import server as mcp_server

    monkeypatch.setattr(
        "session_buddy.core.session_manager.os.getcwd", lambda: str(tmp_path),
    )

    fake_mode_cfg = MagicMock()
    fake_mode_cfg.enable_auto_checkpoint = True

    class _FakeMode:
        def get_config(self):
            return fake_mode_cfg

    monkeypatch.setattr("session_buddy.modes.get_mode", lambda: _FakeMode())

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(mcp_server, "_original_lifespan", _noop_lifespan)

    settings_stub = MagicMock()
    settings_stub.auto_checkpoint_interval = 60
    settings_stub.midpoint_commit_interval_s = 60
    settings_stub.midpoint_commits_enabled = False
    settings_stub.midpoint_commit_min_quality_delta = 10
    monkeypatch.setattr(
        "session_buddy.settings.get_settings", lambda: settings_stub,
    )

    build_calls: list[Path] = []
    real_build = mcp_server._build_orchestrator

    def _tracking_build(wd, *args, **kwargs):
        build_calls.append(wd)
        return real_build(wd, *args, **kwargs)

    monkeypatch.setattr(mcp_server, "_build_orchestrator", _tracking_build)

    async with mcp_server._lifespan_with_dhara_cleanup(app=MagicMock()):
        await asyncio.sleep(0.05)

    # The orchestrator was NOT constructed in this test because
    # ``AutoCheckpointLoop`` constructs the orchestrator lazily — the
    # ``orch_factory`` is invoked on each tick, not at start(). With a
    # 60-second interval, no tick fires during the 50ms sleep. So the
    # empty list here is expected; this test exists only to prove the
    # negative case (``test_lifespan_skips_orchestrator_for_invalid_cwd``)
    # is not a vacuous pass driven by the patching harness itself.
    #
    # Positive control — the FIRST ``_run`` iteration fires
    # ``_drain_pending`` then ``_tick`` IMMEDIATELY (no initial wait), so
    # the orchestrator IS constructed within the 50ms sleep above. The
    # invalid-cwd test's empty-list assertion would pass vacuously if the
    # patching harness never recorded calls; a non-empty list here proves
    # the harness is wired correctly so the negative case is trustworthy.
    assert build_calls == [tmp_path], (
        "valid-cwd lifespan failed to construct the orchestrator — "
        "the negative-case test cannot be trusted without this control. "
        f"build_calls={build_calls!r}"
    )
