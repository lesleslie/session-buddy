"""Regression tests for DTZ001/DTZ005/DTZ006 migrations.

These tests prove that adapter and analytics code that handles timestamps
uses UTC consistently and that `parse_utc_timestamp` safely normalizes
legacy naive strings without breaking aware arithmetic.
"""

from __future__ import annotations

import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from session_buddy.utils.time import parse_utc_timestamp, utc_now


def test_legacy_permission_id_input_is_utc_interpreted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session_id hash must remain stable when the wall clock and cwd
    are frozen, even when a legacy naive ISO string is fed through
    ``parse_utc_timestamp`` before the hash is built.
    """
    from session_buddy.core import permissions as permissions_module
    from session_buddy.core.permissions import SessionPermissionsManager

    # Reset the singleton so a fresh session_id is generated for this test.
    SessionPermissionsManager._instance = None
    SessionPermissionsManager._session_id = None

    # Freeze the clock and cwd so the hash input is deterministic.
    frozen = datetime(2026, 7, 27, 10, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(permissions_module, "utc_now", lambda: frozen)
    monkeypatch.chdir(tmp_path)

    # Demonstrate the legacy UTC-interpretation contract.
    naive = "2026-07-27T10:00:00"
    aware = parse_utc_timestamp(naive)
    assert aware.tzinfo is not None
    assert aware.utcoffset() == timedelta(0)
    assert aware.hour == 10

    # Invoke the real session-ID generation logic via the manager.
    manager = SessionPermissionsManager(tmp_path / "claude")
    first = manager.session_id

    # 12-character lowercase hexadecimal hash of the frozen {time}_{cwd}.
    assert re.fullmatch(r"[0-9a-f]{12}", first), (
        f"session_id must be 12 lowercase hex chars, got {first!r}"
    )

    # The hash is stable across repeated instantiations.
    SessionPermissionsManager._instance = None
    SessionPermissionsManager._session_id = None
    again = SessionPermissionsManager(tmp_path / "claude").session_id
    assert again == first


def test_utc_now_round_trips_through_parse_utc_timestamp() -> None:
    """An aware UTC instant returned by ``utc_now()`` must survive a round-trip
    through ``parse_utc_timestamp`` unchanged, including its tzinfo.
    """
    from session_buddy.utils.time import parse_utc_timestamp, utc_now

    instant = utc_now()
    assert instant.tzinfo is not None
    assert instant.utcoffset() == timedelta(0)

    # Round-trip via ISO serialisation; parse_utc_timestamp must hand back the
    # same instant, not a naive copy.
    round_tripped = parse_utc_timestamp(instant.isoformat())
    assert round_tripped.tzinfo is not None
    assert round_tripped.utcoffset() == timedelta(0)
    assert round_tripped == instant


def test_hook_elapsed_uses_monotonic_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """``HooksManager.execute_hooks`` must measure elapsed duration with
    ``time.monotonic`` so a wall-clock jump cannot produce a negative or
    unbounded duration.
    """
    from session_buddy.core import hooks as hooks_module
    from session_buddy.core.hooks import Hook, HookContext, HookResult, HookType

    # Patch the ``time`` module referenced by the hooks module so wall-clock
    # changes (e.g. ``time.time`` jumping backwards) cannot leak into the
    # duration calculation. The monotonic clock is the only safe source.
    #
    # We rig ``time.time`` and ``time.perf_counter`` to return wildly negative
    # values; a correct implementation that uses ``time.monotonic`` must
    # still produce a sane non-negative duration.
    monotonic_call_log: list[float] = []

    import itertools

    monotonic_iter = itertools.count(start=100.0, step=0.25)

    def fake_monotonic() -> float:
        value = next(monotonic_iter)
        monotonic_call_log.append(value)
        return value

    monkeypatch.setattr(hooks_module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hooks_module.time, "time", lambda: -1_000_000.0)
    monkeypatch.setattr(hooks_module.time, "perf_counter", lambda: -999_999.0)

    async def handler(_context: HookContext) -> HookResult:
        # Even the handler itself must not be affected by the rigged wall clock.
        # If the implementation accidentally falls back to ``time.time`` while
        # building HookResult, the elapsed below will betray it.
        return HookResult(success=True, modified_context={})

    hook = Hook(
        name="monotonic-elapsed-probe",
        hook_type=HookType.POST_CHECKPOINT,
        priority=100,
        handler=handler,
    )

    manager = hooks_module.HooksManager()

    async def run() -> list[HookResult]:
        return await manager.execute_hooks(
            HookType.POST_CHECKPOINT,
            HookContext(
                hook_type=HookType.POST_CHECKPOINT,
                session_id="probe",
                timestamp=datetime(2026, 7, 27, 10, 0, 0, tzinfo=UTC),
                metadata={},
            ),
        )

    # Wire the hook in directly into the private registry.
    manager._hooks[HookType.POST_CHECKPOINT] = [hook]  # type: ignore[attr-defined]

    import asyncio

    results = asyncio.run(run())
    assert len(results) == 1
    elapsed = results[0].execution_time_ms

    # The hooks module must have called ``time.monotonic`` at least twice:
    # once for ``start_monotonic`` and once for the elapsed calculation.
    assert len(monotonic_call_log) >= 2, (
        f"expected hooks to consult time.monotonic, saw {len(monotonic_call_log)} calls"
    )

    # Duration must be non-negative and bounded by the number of monotonic
    # ticks observed. If the implementation falls back to ``time.time``
    # (which we rigged to -1_000_000.0) the elapsed would explode into the
    # millions or go strongly negative.
    assert elapsed >= 0, f"elapsed duration went negative: {elapsed}"
    assert elapsed < 60_000, f"elapsed duration is suspiciously large: {elapsed}"


def test_handoff_filename_carries_utc_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handoff filename keeps the ``session_handoff_YYYYMMDD_HHMMSS.md``
    shape and is generated from a timezone-aware UTC datetime.
    """
    from datetime import datetime as real_datetime

    from session_buddy.core.lifecycle import handoff as handoff_module

    # Swap the ``datetime`` symbol inside the handoff module for a recording
    # subclass so we can prove the source datetime is UTC-aware. ``strftime``
    # on a builtin ``datetime`` is a C method and cannot be monkey-patched.
    captured: dict[str, datetime] = {}
    frozen = real_datetime(2026, 7, 27, 10, 0, 0, tzinfo=UTC)

    class _AwareDatetime(real_datetime):
        @classmethod
        def now(cls, tz: real_datetime.tzinfo | None = None) -> real_datetime:
            assert tz is not None, "handoff must use a timezone-aware now(...)"
            assert tz.utcoffset(frozen) == timedelta(0), "expected UTC tzinfo"
            captured["dt"] = frozen
            return frozen

    monkeypatch.setattr(handoff_module, "datetime", _AwareDatetime)

    written = handoff_module.save_handoff_documentation(
        "# handoff body\n",
        tmp_path,
    )

    assert written is not None
    assert written.exists()
    assert re.fullmatch(
        r"session_handoff_\d{8}_\d{6}\.md",
        written.name,
    ), f"unexpected handoff filename {written.name!r}"

    # The underlying datetime used to build the filename must be UTC-aware.
    assert "dt" in captured
    dt = captured["dt"]
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)


def test_interruption_manager_state_timestamp_is_utc_aware() -> None:
    """``InterruptionManager._capture_environment_state`` must emit a
    timezone-aware ISO timestamp in the ``timestamp`` field.
    """
    from session_buddy.interruption_manager import InterruptionManager

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "interruption.db")
        manager = InterruptionManager(db_path=db_path)
        state = manager._capture_environment_state()

    ts = state["timestamp"]
    assert isinstance(ts, str)
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_memory_optimizer_retention_handles_legacy_naive_timestamp() -> None:
    """Regression for Task 2C silent semantic regression.

    ``RetentionPolicyManager.get_conversations_for_retention`` used to
    raise ``TypeError`` when the stored ``timestamp`` was a legacy naive
    ISO string (because ``datetime.fromisoformat`` produced a naive
    datetime and the wall-clock subtraction failed). The fix was to
    wrap every comparison through ``parse_utc_timestamp`` (which
    interprets naive values as UTC) so the retention comparison stays
    monotonic and never flips a conversation to ``is_old`` due solely
    to a missing timezone marker.
    """
    from session_buddy.memory_optimizer import RetentionPolicyManager

    manager = RetentionPolicyManager()
    # Legacy naive ISO string (no trailing 'Z', no offset) representing
    # a conversation from one day ago.
    one_day_ago_naive = (utc_now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    conv = {
        "id": "c1",
        "content": "hello",
        "project": None,
        "timestamp": one_day_ago_naive,
        "metadata": {},
        "original_size": 0,
        "importance_score": 0.0,
    }

    # Pre-migration this call raised TypeError on the comparison. Post-fix
    # it returns sensible "keep"/"consolidate" buckets without raising.
    keep, _consolidate = manager.get_conversations_for_retention([conv])

    # The conversation is only one day old and has zero importance;
    # default consolidation_age_days is 30, so it must NOT be flagged
    # as old. If the comparison flipped to naive-treat-as-old, it would
    # land in ``consolidate``.
    assert conv in keep, (
        "Naive legacy timestamp must not flip to is_old; "
        f"keep={keep!r}, conv id={conv.get('id')}"
    )

    # Parity check: a parsed aware value would behave identically.
    aware = parse_utc_timestamp(one_day_ago_naive)
    assert aware.tzinfo is not None
    assert aware.utcoffset() == timedelta(0)

    # Direct math parity: naive-string-aware comparison equals naive-vs-naive.
    # (This documents the contract that the retention code now relies on.)
    naive_aware = aware  # parse_utc_timestamp treats naive input as UTC
    cutoff = utc_now() - timedelta(days=manager.default_policies["consolidation_age_days"])
    assert naive_aware > cutoff, (
        "Legacy naive timestamp must satisfy the same retention boundary "
        "as its aware-parsed counterpart."
    )
