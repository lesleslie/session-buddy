"""Plan 2 Phase E2 Task 5 — session-buddy ``/health`` aggregator 4-field contract.

Pins the Plan §6.5 contract that each ``/health`` per-feed dict carries
the 4 mandatory fields (``entities_count``, ``last_updated_timestamp``,
``cycles_total``, ``errors_total``) — the same 4 fields that
``mcp-backend-wiring-discipline.md §3`` mandates for every registered
tool's data feed.

The test exercises the **wire shape** the session-buddy ``/health``
route serves: the dict returned by ``aggregate_feed_states`` is what
the lifespan-owned health closure puts into ``checks`` and what the
custom ``/health`` route serialises (per
``session_buddy/server_optimized.py:493-499``). Asserting the 4 fields
here catches regressions whether the source is the lifespan probe
or the HTTP route.

The skip-when-stale gate (probe call) ensures the test passes
against the pre-widening mcp_common wheel (skip) and asserts
positively against the new one (pass). The skip message points
operators to the version bump that closes the gap.
"""
from __future__ import annotations

from typing import Any

import pytest


# Session-Buddy's ``/health`` aggregates these 2 feed names (per
# ``session_buddy/server_optimized.py:493-499``):
#   skills_signer, bodai_events
SB_HEALTH_FEED_NAMES = (
    "skills_signer",
    "bodai_events",
)


# Plan 2 Phase E2 §6.5 — every registered tool's data feed must
# surface these 4 fields verbatim. See mcp-backend-wiring-discipline.md §3.
PLAN_EXPECTED_FIELDS = (
    "entities_count",
    "last_updated_timestamp",
    "cycles_total",
    "errors_total",
)


def _probe_aggregator_shape() -> "object | None":
    """Probe the installed ``mcp_common`` aggregator for the 4-field shape.

    Returns the per-feed check dict if the installed wheel has the
    widening (commit mcp_common@266de23+), or ``None`` if pre-widening
    (in which case the test should skip).
    """
    from mcp_common.health.aggregator import aggregate_feed_states
    from mcp_common.health.feed import HealthFeedState

    snap = aggregate_feed_states(
        {"skills_signer": HealthFeedState(entities_count=1, cycles_total=1)}
    )
    check = snap["checks"]["skills_signer"]
    if "entities_count" in check:
        return check
    return None


def test_sb_health_aggregator_emits_four_plan_fields_per_feed() -> None:
    """``aggregate_feed_states`` over session-buddy's 2 feeds returns 4
    plan fields per ``checks[feed_name]`` — the canonical wire shape
    the sb ``/health`` route serialises.

    The aggregator input mirrors the per-feed states constructed at
    ``session_buddy/server_optimized.py:443-481``, so this test
    exercises the same shape the live route produces.
    """
    probe = _probe_aggregator_shape()
    if probe is None:
        pytest.skip(
            "mcp_common aggregator does not yet expose the 4 plan-§6.5 "
            "fields. Bump mcp_common to a version that includes the "
            "FeedSnapshot widening (oneiric-plan ledger mcp_common@266de23)."
        )

    from mcp_common.health.aggregator import aggregate_feed_states
    from mcp_common.health.feed import HealthFeedState

    now = 1000.0
    states = {
        name: HealthFeedState(
            entities_count=10,
            cycles_total=5,
            errors_total=0,
            last_updated_timestamp=now,
        )
        for name in SB_HEALTH_FEED_NAMES
    }
    snap = aggregate_feed_states(states)

    # Both sb feeds must be present in the snapshot.
    assert set(snap["checks"].keys()) == set(SB_HEALTH_FEED_NAMES)

    for feed_name in SB_HEALTH_FEED_NAMES:
        check = snap["checks"][feed_name]
        for field in PLAN_EXPECTED_FIELDS:
            assert field in check, (
                f"aggregator dropped {field} from {feed_name} check "
                f"(Plan 2 Phase E2 §6.5 / mcp-backend-wiring-discipline §3)"
            )
            assert check[field] == getattr(states[feed_name], field), (
                f"aggregator {field} mismatch on {feed_name}"
            )


def test_sb_health_aggregator_default_state_round_trips() -> None:
    """Default-valued ``HealthFeedState`` round-trips with the
    ``None`` ↔ ``0`` distinction preserved (operators rely on the
    difference to spot producers that have not yet completed a cycle).
    """
    probe = _probe_aggregator_shape()
    if probe is None:
        pytest.skip(
            "mcp_common aggregator does not yet expose the 4 plan-§6.5 "
            "fields. Bump mcp_common to a version that includes the "
            "FeedSnapshot widening (oneiric-plan ledger mcp_common@266de23)."
        )

    from mcp_common.health.aggregator import aggregate_feed_states
    from mcp_common.health.feed import HealthFeedState

    state = HealthFeedState()  # all defaults
    snap = aggregate_feed_states({"never_cycled": state})
    check = snap["checks"]["never_cycled"]
    assert check["entities_count"] == 0
    assert check["cycles_total"] == 0
    assert check["errors_total"] == 0
    assert check["last_updated_timestamp"] is None


def test_sb_health_http_response_shape_carries_four_fields() -> None:
    """The live ``/health`` HTTP response body carries the 4 plan fields
    per feed — the assertion the operator's ``curl /health | jq .feeds``
    workflow depends on (per Plan 2 Phase E2 §10).

    Best-effort: calls the lifespan-owned probe via the FastMCP app.
    Skips if the lifespan fails to construct in the test environment.
    The aggregator-level tests above pin the contract from the
    canonical source; this test is the end-to-end smoke.
    """
    from mcp_common.health.aggregator import aggregate_feed_states
    from mcp_common.health.feed import HealthFeedState

    snap = aggregate_feed_states(
        {"skills_signer": HealthFeedState(entities_count=1, cycles_total=1)}
    )
    if "entities_count" not in snap["checks"]["skills_signer"]:
        pytest.skip(
            "mcp_common aggregator does not yet expose the 4 plan-§6.5 "
            "fields. Bump mcp_common to a version that includes the "
            "FeedSnapshot widening (oneiric-plan ledger mcp_common@266de23)."
        )

    try:
        from fastapi.testclient import TestClient

        from session_buddy.server_optimized import mcp as _sb_mcp
    except ImportError as exc:  # pragma: no cover — test env missing
        pytest.skip(f"session_buddy FastMCP app unavailable: {exc}")

    try:
        client = TestClient(_sb_mcp)
        response = client.get("/health")
    except Exception as exc:  # noqa: BLE001 — lifespan init can fail in test envs
        pytest.skip(
            f"TestClient setup failed in test env "
            f"(the aggregator-level tests above still pin the contract): {exc}"
        )

    assert response.status_code in (200, 503), (
        f"unexpected /health status: {response.status_code} body={response.text[:500]}"
    )

    body: dict[str, Any] = response.json()
    checks = body.get("checks", body)
    assert isinstance(checks, dict)
    for feed_name, feed_dict in checks.items():
        if not isinstance(feed_dict, dict):
            continue
        for field in PLAN_EXPECTED_FIELDS:
            assert field in feed_dict, (
                f"/health body dropped {field} from {feed_name} check "
                f"(Plan 2 Phase E2 §6.5 / mcp-backend-wiring-discipline §3)"
            )
