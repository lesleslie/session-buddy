"""Lifespan tests for the MCP server — guard Finding C-7.

Finding C-7: ``mcp/server.py`` passed ``Path(os.getcwd())`` straight to
``_build_orchestrator`` without validation. A prompt-injection gadget
that ``cd /`` would let ``LockfileSignalSource`` create
``/.session-buddy/subagent.lock`` at filesystem root.

The fix extracted ``_validate_orchestrator_path`` to a module-level
``validate_orchestrator_working_dir`` and wired it into the lifespan
startup. This module exercises that wiring.

Test-environment note (NOT a defect of this fix):
``session_buddy.channel.state_writer`` imports ``from dhara.schema
import ChannelSessionState, validate`` (commit ``109b1d98``,
S-CHANNEL-DURABLE v1.1). The installed Bodai dhara in this venv
(0.13.2) does not yet ship the ``schema`` submodule — that release is
tracked as a dependency-bump follow-up, not in scope for Task 4. To
let this test exercise the lifespan wiring without touching
production code, we inject a stub ``dhara.schema`` into
``sys.modules`` BEFORE ``session_buddy.mcp.server`` is imported.
The stub's attributes are never called by anything we exercise here
(``record_channel_session_state`` is not invoked); only the
``import`` must succeed.
"""
from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _ensure_dhara_schema_stub() -> None:
    """Inject a stub ``dhara.schema`` module if it isn't importable.

    See module docstring for context. This is test-only — it does
    NOT alter any production code path.
    """
    if "dhara.schema" in sys.modules:
        return
    try:
        import dhara.schema  # noqa: F401  (probe only)
        return
    except ModuleNotFoundError:
        pass

    stub = types.ModuleType("dhara.schema")

    class _StubChannelSessionState:
        """No-op stand-in for the real ``ChannelSessionState`` class."""

        def __init__(self, *_a: object, **_kw: object) -> None:
            pass

    def _stub_validate(*_a: object, **_kw: object) -> None:
        """No-op stand-in for the real ``validate`` function."""
        return None

    stub.ChannelSessionState = _StubChannelSessionState  # type: ignore[attr-defined]
    stub.validate = _stub_validate  # type: ignore[attr-defined]
    sys.modules["dhara.schema"] = stub


_ensure_dhara_schema_stub()


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
    monkeypatch.setattr(
        "session_buddy.mcp.server.os.getcwd",
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
        "session_buddy.mcp.server.os.getcwd", lambda: str(tmp_path),
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
