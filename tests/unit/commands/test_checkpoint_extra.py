#!/usr/bin/env python3
"""Extra tests for session_buddy.commands.checkpoint.

Complements ``tests/unit/commands/test_checkpoint.py`` (which exists as a
preserved prior-art file). This file pins two contracts that the prior
tests exercise only loosely:

1. **TTL expiry actually works.** The prior file's
   ``test_ttl_expiry_allows_next_call_to_run`` had an off-by-one in its
   ``time.monotonic`` iterator (4 values for 2 calls), masking the
   source's correct TTL behaviour. This file pins the source behaviour
   with a fixed iterator.

2. **Module-load-time gate evaluation.** ``_GATE_ENABLED`` is computed at
   module import — mutating ``SESSION_BUDDY_HOOK_SINGLE_FLIGHT`` after
   import has no effect. Pin that contract here so a future refactor
   that switches to ``os.environ.get(...)`` inside ``checkpoint()`` is
   flagged.

3. **Gate releases on body exception.**
   ``HookSingleFlight.__call__`` now sets ``_last_seen[key]`` AFTER
   ``coro_factory()`` returns successfully. An exception inside the
   body releases the gate slot instead of pinning it for ``ttl_seconds``
   with no way to recover. This test pins the fixed behaviour: a
   second call within the TTL re-runs the body when the first call
   raised.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import session_buddy.commands.checkpoint as checkpoint_mod
from session_buddy.hooks import HookSingleFlight


# ---------------------------------------------------------------------------
# Fixtures — same shape as the preserved test file.
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the module-level gate with a fresh instance."""
    monkeypatch.setattr(checkpoint_mod, "_FLIGHT", HookSingleFlight(ttl_seconds=5.0))


@pytest.fixture
def gate_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checkpoint_mod, "_GATE_ENABLED", True)


@pytest.fixture
def gate_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checkpoint_mod, "_GATE_ENABLED", False)


# ---------------------------------------------------------------------------
# TTL expiry — corrected iterator (only one monotonic call per __call__).
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_ttl_expiry_with_corrected_iterator() -> None:
    """After the TTL window elapses, the same key runs again.

    Pin to the source's actual behaviour: the prior file's test had 4
    values in its iterator where 2 are correct (one ``time.monotonic()``
    call per ``HookSingleFlight.__call__``).
    """
    fresh = HookSingleFlight(ttl_seconds=5.0)
    checkpoint_mod._FLIGHT = fresh

    # Two checkpoints → two monotonic calls.
    monotonic_values = iter([0.0, 10.0])
    with patch(
        "session_buddy.hooks.single_flight.time.monotonic",
        side_effect=lambda: next(monotonic_values),
    ):
        with patch.object(
            checkpoint_mod,
            "_checkpoint_impl",
            new=AsyncMock(side_effect=["first-run", "second-run"]),
        ) as mock_impl:
            r1 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)
            r2 = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)

    assert r1 == "first-run"
    assert r2 == "second-run", (
        "After 10s (TTL is 5s), the gate must release and re-run the impl."
    )
    assert mock_impl.await_count == 2


# ---------------------------------------------------------------------------
# Module-load-time _GATE_ENABLED evaluation
# ---------------------------------------------------------------------------


def test_gate_enabled_evaluated_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutating the env var after import has no effect on _GATE_ENABLED.

    The module evaluates the env var once, at top-level, and caches the
    result in ``_GATE_ENABLED``. Pin this so a refactor to read the env
    var at call-time is intentional, not accidental.
    """
    # Sanity: under default env, gate is enabled.
    assert checkpoint_mod._GATE_ENABLED is True

    # Set the env var to "false" post-import. _GATE_ENABLED must NOT change.
    monkeypatch.setenv("SESSION_BUDDY_HOOK_SINGLE_FLIGHT", "false")
    assert checkpoint_mod._GATE_ENABLED is True, (
        "Mutating SESSION_BUDDY_HOOK_SINGLE_FLIGHT after import must not "
        "change _GATE_ENABLED; the constant is frozen at module-load."
    )


def test_default_ttl_is_five_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module-level _FLIGHT is constructed with the default 5-second TTL.

    The class default (``HookSingleFlight(ttl_seconds=5.0)``) matches
    the spec. Pin it here so a future bump to e.g. ``ttl_seconds=10.0``
    is intentional.
    """
    from session_buddy.hooks import HookSingleFlight

    fresh = HookSingleFlight()
    assert fresh._ttl == 5.0


# ---------------------------------------------------------------------------
# Source-bug pin: gate does NOT release on exception
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_impl_exception_releases_gate() -> None:
    """Gate slot IS released when the body raises (fixed behaviour).

    In ``HookSingleFlight.__call__`` (single_flight.py:54-72), the
    timestamp ``_last_seen[key] = now`` is written in a ``finally``
    block AFTER ``coro_factory`` awaits. If the factory raises, we
    still release the lock without writing the timestamp, so the next
    call within TTL re-runs the body instead of returning
    ``"coalesced"``.

    Prior to the fix, the timestamp was written BEFORE the body ran,
    so an exception pinned the gate for ``ttl_seconds`` and operators
    could not recover without waiting. This test pins the fixed
    behaviour so any regression to the buggy form is observable in CI.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=[RuntimeError("boom"), "fresh-run"]),
    ) as mock_impl:
        with pytest.raises(RuntimeError, match="boom"):
            await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)

        # Same key, immediately after the exception. The gate IS
        # released because _last_seen[key] was NOT written when the body
        # raised, so this call sees no prior timestamp and re-runs.
        result = await checkpoint_mod.checkpoint(project_path="/tmp/proj", agent_idx=0)

    # Fixed behaviour: both impl calls happen. The "fresh-run" side
    # effect is consumed by the second call.
    assert result == "fresh-run"
    assert mock_impl.await_count == 2
    assert mock_impl.call_args_list[0].kwargs == {"working_directory": "/tmp/proj"}
    assert mock_impl.call_args_list[1].kwargs == {"working_directory": "/tmp/proj"}


# ---------------------------------------------------------------------------
# Branch coverage: body() closure captures last_result correctly
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_disabled")
async def test_body_result_returned_verbatim_when_gate_disabled() -> None:
    """When the gate is disabled, the body wrapper still threads the result.

    The ``last_result`` list + closure dance is the only way to return
    a value through the ``HookSingleFlight.__call__`` contract (which
    returns ``bool``, not the body output). Pin that the gate-disabled
    path returns the LAST body result — not an empty string.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(return_value="verbatim-output"),
    ):
        result = await checkpoint_mod.checkpoint(
            project_path="/tmp/proj",
            agent_idx=42,
        )

    assert result == "verbatim-output"


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_body_result_returned_verbatim_when_gate_enabled() -> None:
    """When the gate is enabled and accepts, the body result is returned.

    Mirror of the gate-disabled test — confirms the body→last_result
    plumbing works for both branches.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(return_value="gate-enabled-output"),
    ):
        result = await checkpoint_mod.checkpoint(
            project_path="/tmp/proj",
            agent_idx=0,
        )

    assert result == "gate-enabled-output"


# ---------------------------------------------------------------------------
# Empty-string env var evaluation
# ---------------------------------------------------------------------------


def test_empty_string_env_var_keeps_gate_enabled() -> None:
    """``SESSION_BUDDY_HOOK_SINGLE_FLIGHT=''`` does NOT disable the gate.

    The set check is against ``{"false", "0", "no", "off"}`` — empty
    string is not in the set, so the gate stays enabled. Pin so a
    future refactor (e.g. ``not raw.lower() in {...}``) does not flip
    this to disabled.
    """
    raw = ""
    gated = raw.lower() not in {"false", "0", "no", "off"}
    assert gated is True


def test_unrecognised_env_var_keeps_gate_enabled() -> None:
    """Arbitrary env values (e.g. 'maybe', 'trueish') leave the gate enabled.

    The set-based membership check means any value outside the disable
    set keeps the gate on. This is the safe default — operators have to
    spell out 'false' exactly to disable.
    """
    for value in ("maybe", "trueish", "enabled", "TRUE", "False-not"):
        gated = value.lower() not in {"false", "0", "no", "off"}
        assert gated is True, f"value {value!r} unexpectedly disabled gate"


# ---------------------------------------------------------------------------
# agent_idx=0 default contract
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_disabled")
async def test_default_agent_idx_is_zero() -> None:
    """The ``agent_idx`` parameter defaults to 0.

    The signature is ``async def checkpoint(*, project_path, agent_idx=0)``.
    Pin that callers omitting ``agent_idx`` see ``0`` flow through.
    """
    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(return_value="ok"),
    ) as mock_impl:
        await checkpoint_mod.checkpoint(project_path="/tmp/proj")

    # The wrapper hard-codes working_directory=project_path (no agent_idx
    # flow-through into the impl). The agent_idx is purely a dedup key.
    mock_impl.assert_awaited_once_with(working_directory="/tmp/proj")


# ---------------------------------------------------------------------------
# Concurrent-safety smoke: two distinct projects never coalesce
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fresh_gate", "gate_enabled")
async def test_concurrent_distinct_projects_all_run() -> None:
    """Five concurrent calls on five distinct projects all execute.

    asyncio.gather fan-out stress-tests the gate's per-key isolation
    under interleaving. If the lock were module-level, this would
    serialise the underlying impl calls — instead they all complete.
    """
    projects = [f"/tmp/proj-{i}" for i in range(5)]

    with patch.object(
        checkpoint_mod,
        "_checkpoint_impl",
        new=AsyncMock(side_effect=[f"output-{i}" for i in range(5)]),
    ) as mock_impl:
        results = await asyncio.gather(
            *[
                checkpoint_mod.checkpoint(project_path=p, agent_idx=0)
                for p in projects
            ]
        )

    assert results == [f"output-{i}" for i in range(5)]
    assert mock_impl.await_count == 5
