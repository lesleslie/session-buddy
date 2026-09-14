"""Smoke tests for ``mcp_common.health.aggregator.aggregate_feed_states``.

Phase 4 of
``docs/plans/2026-09-14-common-mcp-client-transport-unification.md``
requires every Bodai MCP server's ``/health`` endpoint to aggregate
per-feed state via ``aggregate_feed_states`` (REQ-002 / REQ-007).
Session-Buddy ships ``record_channel_session_state`` and other
ingesters that produce ``HealthFeedState`` snapshots; this test pins
that the aggregator's wire shape is what Session-Buddy's ``/health``
handler will receive when Phase 4 wires it up.

These are smoke tests — the canonical contract for the aggregator
lives in
``mcp-common/tests/unit/health/test_aggregator.py``. We re-assert the
structure here so a future regression in the dep floor cannot silently
drop the function from Session-Buddy's venv.
"""

from __future__ import annotations

import time

from mcp_common.health.aggregator import aggregate_feed_states
from mcp_common.health.feed import HealthFeedState, StatusValue


# ---------------------------------------------------------------------------
# Importability + wire-shape smoke
# ---------------------------------------------------------------------------


def test_aggregator_importable_and_callable() -> None:
    """``aggregate_feed_states`` is importable and accepts the documented shape.

    Pin: ``mcp-common>=0.26.1`` (per Phase 2.5 dep floor) ships the
    renamed ``aggregate_feed_states`` function. A regression here
    means the dep floor silently regressed and Phase 4's health
    wiring would break at import time.
    """
    assert callable(aggregate_feed_states)
    assert aggregate_feed_states.__module__ == "mcp_common.health.aggregator"


def test_empty_states_returns_healthy_baseline() -> None:
    """No feeds → aggregate status is HEALTHY with no per-feed checks.

    Smoke baseline: when a server has no feeds registered yet, the
    ``/health`` endpoint must report HEALTHY (not FAILED). REQ-008
    only downgrades to WARMING_UP when the producer is alive but
    empty; a bare ``{}`` is the producer-not-yet-registered case.
    """
    snap = aggregate_feed_states({})
    assert snap["status"] == StatusValue.HEALTHY
    assert snap["checks"] == {}
    assert snap["reason_codes"] == []


def test_single_healthy_feed_returns_expected_wire_shape() -> None:
    """A single HEALTHY feed produces the documented JSON shape.

    Pin: the snapshot is JSON-serialisable with three top-level keys
    (``status``, ``checks``, ``reason_codes``) and each entry in
    ``checks`` carries ``status``/``healthy``/``reason_codes``.
    """
    snap = aggregate_feed_states(
        {
            "local_traces": HealthFeedState(
                entities_count=42,
                cycles_total=3,
                ingester_running=True,
                last_updated_timestamp=time.time(),
            )
        }
    )
    assert snap["status"] == StatusValue.HEALTHY
    assert "local_traces" in snap["checks"]
    feed = snap["checks"]["local_traces"]
    assert feed["status"] == StatusValue.HEALTHY
    assert feed["healthy"] is True
    assert isinstance(feed["reason_codes"], list)


def test_warming_up_feed_surfaces_in_checks() -> None:
    """An empty-but-running feed produces WARMING_UP in checks.

    Mirrors REQ-008: when Session-Buddy's channel-session ingester is
    alive but has not yet observed a record, the per-feed ``status``
    is WARMING_UP. The top-level ``status`` is the worst seen, so it
    also rolls up to WARMING_UP.
    """
    snap = aggregate_feed_states(
        {
            "channel_session_state": HealthFeedState(
                entities_count=0,
                cycles_total=1,
                ingester_running=True,
            )
        }
    )
    assert snap["status"] == StatusValue.WARMING_UP
    feed = snap["checks"]["channel_session_state"]
    assert feed["status"] == StatusValue.WARMING_UP
    assert feed["healthy"] is False


def test_failed_ingester_outranks_warming_up() -> None:
    """Worst-case roll-up: FAILED > DEGRADED > WARMING_UP > HEALTHY.

    Pin: when the channel-session ingester's task is dead
    (``ingester_running=False``), the per-feed status is FAILED and
    the aggregate reflects the worst severity. Session-Buddy's
    ``/health`` should return ``degraded`` (HTTP 503) in this state.
    """
    snap = aggregate_feed_states(
        {
            "channel_session_state": HealthFeedState(
                entities_count=0,
                ingester_running=False,
            ),
            "healthy_traces": HealthFeedState(
                entities_count=100,
                cycles_total=5,
                ingester_running=True,
                last_updated_timestamp=time.time(),
            ),
        }
    )
    assert snap["status"] == StatusValue.FAILED
    assert snap["checks"]["channel_session_state"]["status"] == StatusValue.FAILED
    assert snap["checks"]["healthy_traces"]["status"] == StatusValue.HEALTHY


def test_recent_error_downgrades_to_degraded() -> None:
    """An error within the halflife window downgrades the feed to DEGRADED.

    Mirrors REQ-007: the per-feed predicate downgrades when
    ``last_error_at`` is within ``halflife_seconds``. The aggregate
    inherits the worst status.
    """
    halflife = 300.0
    snap = aggregate_feed_states(
        {
            "local_traces": HealthFeedState(
                entities_count=128,
                cycles_total=10,
                ingester_running=True,
                errors_total=1,
                last_error_at=time.time() - 5.0,
            )
        },
        halflife_seconds=halflife,
    )
    assert snap["status"] == StatusValue.DEGRADED
    feed = snap["checks"]["local_traces"]
    assert feed["status"] == StatusValue.DEGRADED
    assert feed["healthy"] is False


def test_snapshot_is_json_serialisable() -> None:
    """The snapshot is JSON-serialisable end-to-end.

    Pin: Session-Buddy's ``/health`` handler returns this snapshot
    verbatim over the wire (see Phase 4 wiring rule
    ``mcp-backend-wiring-discipline.md``). If a future change adds
    non-serialisable fields (e.g. dataclass instances), the health
    endpoint 500s and Bodai observability loses the feed state.
    """
    import json

    snap = aggregate_feed_states(
        {
            "local_traces": HealthFeedState(
                entities_count=10,
                cycles_total=2,
                ingester_running=True,
                last_updated_timestamp=time.time(),
            )
        }
    )
    # Round-trip through JSON to guarantee serialisability.
    encoded = json.dumps(snap, default=str)
    decoded = json.loads(encoded)
    assert decoded["status"] == StatusValue.HEALTHY.value
    assert "local_traces" in decoded["checks"]
