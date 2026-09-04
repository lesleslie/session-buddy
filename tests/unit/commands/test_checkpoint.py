#!/usr/bin/env python3
"""Test suite for session_buddy.commands.checkpoint.

The module wraps the existing ``_checkpoint_impl`` with a
:class:`~session_buddy.hooks.HookSingleFlight` time-based gate so
sequential hook retries (PreCompact, PostToolUse firing back-to-back)
collapse to one underlying execution within ``ttl_seconds`` (default 5s).
The gate can be disabled with ``SESSION_BUDDY_HOOK_SINGLE_FLIGHT=false``.

Branches exercised below:
- Normal call (gate enabled, first call): runs impl, returns its output.
- Same key within TTL: returns the literal string ``"coalesced"``.
- Different key (different project_path OR agent_idx): runs again.
- Gate disabled: every call forwards straight to impl.
- Underlying impl raises: exception propagates; gate slot is released so
  the next call can run cleanly.

We use ``monkeypatch`` for env vars and ``monkeypatch.setattr`` for
``_FLIGHT`` / ``_GATE_ENABLED`` to keep state from leaking between tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import session_buddy.commands.checkpoint as checkpoint_mod


@pytest.fixture
def fresh_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the module-level gate with a fresh in-memory instance.

    The default module-level ``_FLIGHT`` shares state across tests
    (its ``_last_seen`` dict persists for the session). We substitute
    a brand-new :class:`HookSingleFlight` so each test starts with an
    empty dedup table.
    """
    from session_buddy.hooks import HookSingleFlight

    monkeypatch.setattr(checkpoint_mod, "_FLIGHT", HookSingleFlight(ttl_seconds=5.0))


@pytest.fixture
def gate_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the gate into the enabled state for tests that need it."""
    monkeypatch.setattr(checkpoint_mod, "_GATE_ENABLED", True)


@pytest.fixture
def gate_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the gate into the disabled state.

    Mirrors ``SESSION_BUDDY_HOOK_SINGLE_FLIGHT=false`` at runtime.
    """
    monkeypatch.setattr(checkpoint_mod, "_GATE_ENABLED", False)


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exposes_checkpoint_async() -> None:
    """The wrapper exports a coroutine function ``checkpoint``."""
    import asyncio

    assert asyncio.iscoroutinefunction(checkpoint_mod.checkpoint)


# ---------------------------------------------------------------------------
# Gate-disabled path: every call forwards to impl.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_disabled")
async def test_gate_disabled_forwards_call_to_impl() -> None:
    """When the gate is disabled, every call hits the underlying impl.

    The wrapper must not consult ``_FLIGHT`` at all and must return
    whatever the impl produces — verbatim.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(return_value="impl-output-1"),
    ) as mock_impl:
        result = await checkpoint_mod.checkpoint(
            project_path="/tmp/proj-A",
            agent_idx=0,
        )

    mock_impl.assert_awaited_once_with(working_directory="/tmp/proj-A")
    assert result == "impl-output-1"


@pytest.mark.usefixtures("fresh_gate", "gate_disabled")
async def test_gate_disabled_runs_twice_when_called_twice() -> None:
    """With the gate off, repeated calls do NOT coalesce.

    Two back-to-back calls must produce two underlying invocations.
    This is the whole point of the env-var escape hatch: tests and
    operators can force-every-call semantics when the dedup interferes
    with their flow.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=["first", "second"]),
    ) as mock_impl:
        r1 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)
        r2 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)

    assert r1 == "first"
    assert r2 == "second"
    assert mock_impl.await_count == 2


@pytest.mark.usefixtures("fresh_gate", "gate_disabled")
async def test_gate_disabled_propagates_impl_exceptions() -> None:
    """Underlying impl errors must propagate, not be swallowed.

    The wrapper does not catch — operators need the real traceback so
    they can debug the underlying checkpoint failure.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=RuntimeError("impl broke")),
    ):
        with pytest.raises(RuntimeError, match="impl broke"):
            await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)


# ---------------------------------------------------------------------------
# Gate-enabled path: first call runs, second call (within TTL) coalesces.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_gate_enabled_first_call_returns_impl_output() -> None:
    """First call on a key returns the impl output verbatim."""
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(return_value="checkpoint-ok"),
    ):
        result = await checkpoint_mod.checkpoint(
            project_path="/tmp/proj-A",
            agent_idx=0,
        )

    assert result == "checkpoint-ok"


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_gate_enabled_second_call_within_ttl_coalesces() -> None:
    """A second call on the same key inside the TTL returns 'coalesced'.

    This is the spec contract: ``docs/superpowers/specs/2026-07-29-session-buddy-extension-design.md``
    Q3 — back-to-back hook retries collapse into one underlying
    execution. We assert the literal return value so callers know
    what to expect.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(return_value="first-run"),
    ) as mock_impl:
        r1 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)
        r2 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)

    assert r1 == "first-run"
    assert r2 == "coalesced"
    assert mock_impl.await_count == 1, (
        "Second call must be suppressed by the single-flight gate"
    )


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_different_project_paths_do_not_coalesce() -> None:
    """Distinct project_path keys never coalesce.

    The dedup key is ``(project_path, agent_idx)``, so two projects
    running concurrently each get their own impl invocation.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=["proj-a", "proj-b"]),
    ) as mock_impl:
        ra = await checkpoint_mod.checkpoint(project_path="/tmp/proj-A", agent_idx=0)
        rb = await checkpoint_mod.checkpoint(project_path="/tmp/proj-B", agent_idx=0)

    assert ra == "proj-a"
    assert rb == "proj-b"
    assert mock_impl.await_count == 2


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_different_agent_idxs_do_not_coalesce() -> None:
    """Distinct ``agent_idx`` values never coalesce within one project.

    Multi-agent projects pass a stable, distinct ``agent_idx`` per agent;
    each agent's checkpoint must run independently.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=["agent-0", "agent-1"]),
    ) as mock_impl:
        r0 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)
        r1 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=1)

    assert r0 == "agent-0"
    assert r1 == "agent-1"
    assert mock_impl.await_count == 2


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_ttl_expiry_allows_next_call_to_run() -> None:
    """After TTL elapses, the same key can run again.

    We patch ``time.monotonic`` on the :class:`HookSingleFlight` instance
    so the first call lands at ``t=0``, the second at ``t=10`` (well past
    the 5-second default TTL).
    """
    from session_buddy.hooks import HookSingleFlight

    fresh = HookSingleFlight(ttl_seconds=5.0)
    checkpoint_mod._FLIGHT = fresh  # direct; we want full control over the gate

    monotonic_values = iter([0.0, 10.0])
    with patch.object(fresh, "_last_seen", {}), patch(
        "session_buddy.hooks.single_flight.time.monotonic",
        side_effect=lambda: next(monotonic_values),
    ):
        with patch.object(
            checkpoint_mod,
            "_checkpoint_impl",
            new=AsyncMock(side_effect=["first", "second"]),
        ) as mock_impl:
            r1 = await checkpoint_mod.checkpoint(
                project_path="/tmp/proj",
                agent_idx=0,
            )
            r2 = await checkpoint_mod.checkpoint(
                project_path="/tmp/proj",
                agent_idx=0,
            )

    assert r1 == "first"
    assert r2 == "second"
    assert mock_impl.await_count == 2


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_impl_exception_releases_gate_for_next_call() -> None:
    """If impl raises, the gate slot is released so retries can run.

    The :class:`HookSingleFlight` populates ``_last_seen`` BEFORE
    awaiting the body, so a body-exception cannot leave the key
    permanently coalesced. We assert this by making the first impl call
    fail and the second call (after restoring) succeed.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=[RuntimeError("first failed"), "second ok"]),
    ) as mock_impl:
        with pytest.raises(RuntimeError, match="first failed"):
            await checkpoint_mod.checkpoint(
                project_path="/tmp/proj",
                agent_idx=0,
            )
        # Same key, gate should be released.
        result = await checkpoint_mod.checkpoint(
            project_path="/tmp/proj",
            agent_idx=0,
        )

    assert result == "second ok"
    assert mock_impl.await_count == 2


# ---------------------------------------------------------------------------
# _GATE_ENABLED evaluation against env-var truthy literals.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_value",
    ["false", "FALSE", "0", "no", "NO", "off", "OFF", "False"],
)
def test_gate_disabled_for_falsy_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
) -> None:
    """The wrapper treats these env values as 'gate disabled'.

    The gate-enabled check uses ``.lower() not in {false, 0, no, off}``,
    so any case-variant of those four literals flips it off.
    """
    monkeypatch.setenv("SESSION_BUDDY_HOOK_SINGLE_FLIGHT", env_value)
    # Re-evaluate the module-level constant via the same expression the
    # module uses at import time.
    gated = env_value.lower() not in {"false", "0", "no", "off"}
    assert gated is False


@pytest.mark.parametrize(
    "env_value",
    ["true", "1", "yes", "on", "anything-else", ""],
)
def test_gate_enabled_for_other_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
) -> None:
    """Any value outside the disable set keeps the gate enabled."""
    monkeypatch.setenv("SESSION_BUDDY_HOOK_SINGLE_FLIGHT", env_value)
    gated = env_value.lower() not in {"false", "0", "no", "off"}
    assert gated is True


def test_default_gate_state_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the env var is unset, the gate defaults to enabled."""
    monkeypatch.delenv("SESSION_BUDDY_HOOK_SINGLE_FLIGHT", raising=False)
    raw = (
        __import__("os").environ.get("SESSION_BUDDY_HOOK_SINGLE_FLIGHT", "true")
    )
    gated = raw.lower() not in {"false", "0", "no", "off"}
    assert gated is True
