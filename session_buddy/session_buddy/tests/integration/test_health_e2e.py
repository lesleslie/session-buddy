"""End-to-end health-enrichment contract for Session-Buddy.

Phase 1.3 of ``docs/plans/2026-10-09-mcp-health-check-enrichment.md``
(plan §5 task 6). The test pins three contracts:

1. The ``mcp__session-buddy__get_health()`` MCP tool returns the
   canonical ``HealthSnapshot`` envelope (status, checks, reason_codes)
   from ``mcp_common.health.aggregator``.
2. The MCP tool and the ``GET /health`` HTTP route agree on
   feed-state on every call (REQ-HC-003 — disagreement is a bug).
3. Both surfaces return 200 when every feed is healthy, 503 when
   any feed reports a degraded or failed state (REQ-HC-002).

The test lives at the *nested* path
``session_buddy/session_buddy/tests/integration/test_health_e2e.py``
(``M3 fix: nested layout`` per the plan). The existing flat-layout
test at ``tests/integration/test_health_aggregator_endpoint.py`` is
unaffected.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp_common.health.feed import HealthFeedState


def _json_body(response: object) -> dict[str, object]:
    """Decode a Starlette ``JSONResponse.body`` into a dict."""
    raw = response.body  # type: ignore[attr-defined]
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return json.loads(bytes(raw))
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    msg = f"unrecognised response body type: {type(raw)!r}"
    raise TypeError(msg)


def _install_signer_snapshot(
    *,
    cycles_total: int,
    errors_total: int,
    ingester_running: bool = True,
) -> MagicMock:
    """Install a synthetic SignerFeedState on the module singleton.

    Bypasses :func:`init_signer_feed_state` (which writes to disk)
    so the test stays hermetic.
    """
    import session_buddy.mcp.signer_feed as signer_feed_mod
    from session_buddy.mcp.signer_feed import SignerFeedState
    from session_buddy.skills_signer import (
        SkillsSigner,
        build_pubkey_manifest,
        generate_keypair,
    )

    keypair = generate_keypair()
    signer = SkillsSigner.from_keypair(keypair)
    state = SignerFeedState(
        manifest=build_pubkey_manifest(keypair),
        signer=signer,
    )
    state.cycles_total = cycles_total
    state.errors_total = errors_total
    state.last_updated_timestamp = 1_000_000.0
    state.last_error_at = None
    signer_feed_mod._signer_feed_state = state
    return state


def _install_publisher_snapshot(
    *,
    cycles_total: int,
    errors_total: int,
    enabled: bool = True,
    init_ok: bool = True,
    entities_count: int = 1,
) -> MagicMock:
    """Install a synthetic BodaiEventsPublisher-shaped mock on tasks_events._publisher.

    The mock is built with ``spec=BodaiEventsPublisher`` so attribute
    names that don't exist on the real class are rejected at setattr
    time. The two attributes the ``/health`` handler reads directly
    are ``enabled`` and ``_init_ok``; the four-feed ``entities_count``,
    ``last_updated_timestamp``, ``cycles_total``, ``errors_total``
    attributes are the wire-level data the snapshot surfaces.
    """
    import session_buddy.mcp.tools.tasks_events as tasks_events_mod
    from session_buddy.mcp.events.bodai_events_publisher import (
        BodaiEventsPublisher,
    )

    publisher = MagicMock(spec=BodaiEventsPublisher)
    publisher.entities_count = entities_count
    publisher.cycles_total = cycles_total
    publisher.errors_total = errors_total
    publisher.last_updated_timestamp = 1_000_000.0
    publisher.enabled = enabled
    publisher._init_ok = init_ok
    tasks_events_mod._publisher = publisher
    return publisher


def _clear_signer() -> None:
    """Reset the signer singleton (test cleanup)."""
    import session_buddy.mcp.signer_feed as signer_feed_mod

    signer_feed_mod._signer_feed_state = None


def _clear_publisher() -> None:
    """Reset the bodai_events publisher slot (test cleanup)."""
    import session_buddy.mcp.tools.tasks_events as tasks_events_mod

    tasks_events_mod._publisher = None


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    """Each test starts with both feed slots empty so the snapshot is deterministic."""
    _clear_signer()
    _clear_publisher()
    yield
    _clear_signer()
    _clear_publisher()


@pytest.fixture()
def halflife() -> int:
    """Pin the halflife to 60s for the test suite.

    The Phase 1.3 default is 60s; the env-var override
    (``HEALTH_FEED_HALFLIFE_SECONDS``) still wins if set. The test
    asserts the override path, not the default, because the
    contract is "per-adopter override to 60s per this plan".
    """
    prior = os.environ.pop("HEALTH_FEED_HALFLIFE_SECONDS", None)
    os.environ["HEALTH_FEED_HALFLIFE_SECONDS"] = "60"
    try:
        yield 60
    finally:
        if prior is None:
            os.environ.pop("HEALTH_FEED_HALFLIFE_SECONDS", None)
        else:
            os.environ["HEALTH_FEED_HALFLIFE_SECONDS"] = prior


class TestGetHealthTool:
    """The new ``mcp__session-buddy__get_health()`` tool.

    Routes through :func:`_build_health_snapshot` and returns the
    canonical ``HealthSnapshot`` envelope from
    ``mcp_common.health.aggregator``.
    """

    async def test_returns_canonical_envelope_when_all_feeds_healthy(
        self,
        halflife: int,
    ) -> None:
        from session_buddy import server_optimized as so

        _install_signer_snapshot(cycles_total=10, errors_total=0)
        _install_publisher_snapshot(cycles_total=10, errors_total=0)

        body = await so.get_health()  # type: ignore[attr-defined]
        assert body["status"] == "healthy"
        assert body["service"] == "session-buddy"
        assert body["status_code"] == 200

        checks = body["checks"]
        assert isinstance(checks, dict)
        assert "skills_signer" in checks
        assert "bodai_events" in checks

        # Per-feed check shape mirrors what the HTTP route emits.
        signer_check = checks["skills_signer"]
        assert signer_check["status"] == "healthy"
        assert signer_check["ok"] is True
        assert signer_check["cycles_total"] == 10
        assert signer_check["errors_total"] == 0

        publisher_check = checks["bodai_events"]
        assert publisher_check["status"] == "healthy"
        assert publisher_check["ok"] is True
        assert publisher_check["cycles_total"] == 10

    async def test_returns_503_on_degraded_when_publisher_failing(
        self,
        halflife: int,
    ) -> None:
        """Per plan §5 task 6: 503 when a stub feed reports broken state.

        A broken ingester is modelled by ``enabled=True`` but
        ``_init_ok=False`` (transport never came up) with
        ``entities_count=0``. The ``/health`` handler reads
        ``ingester_running = enabled and _init_ok``; that boolean
        drives the aggregator's ``is_healthy`` predicate, which
        returns FAILED for a dead producer with no data. The
        synthetic ``status_code`` on the body is 503.
        """
        from session_buddy import server_optimized as so

        _install_signer_snapshot(cycles_total=10, errors_total=0)
        # Transport never came up: _init_ok=False, no entities,
        # never cycled → FAILED via the "producer dead and no data"
        # branch in ``is_healthy`` (``mcp_common.health.feed``).
        _install_publisher_snapshot(
            cycles_total=0,
            errors_total=0,
            entities_count=0,
            enabled=True,
            init_ok=False,
        )

        body = await so.get_health()  # type: ignore[attr-defined]
        assert body["status"] in ("degraded", "failed")
        assert body["status_code"] == 503

        publisher_check = body["checks"]["bodai_events"]
        assert publisher_check["ok"] is False
        assert publisher_check["status"] in ("degraded", "failed")

    async def test_returns_failed_when_signer_lifespan_not_run(
        self,
        halflife: int,
    ) -> None:
        """When the signer singleton is None, the feed reports FAILED."""
        from session_buddy import server_optimized as so

        # _reset_singletons already cleared the signer; install a
        # healthy publisher so the only failing feed is the signer.
        _install_publisher_snapshot(cycles_total=10, errors_total=0)

        body = await so.get_health()  # type: ignore[attr-defined]
        assert body["status"] == "failed"
        assert body["status_code"] == 503
        assert body["checks"]["skills_signer"]["ok"] is False
        assert body["checks"]["skills_signer"].get("error") == (
            "not initialized; awaiting lifespan"
        )

    async def test_envelope_matches_canonical_health_snapshot(
        self,
        halflife: int,
    ) -> None:
        """The body shape matches the canonical HealthSnapshot from mcp-common.

        Per ``mcp-common/mcp_common/health/aggregator.py:33-46``, the
        canonical envelope is::

            {
                "status": StatusValue,
                "checks": {feed_name: {status, healthy, reason_codes}},
                "reason_codes": list[ReasonCode],
            }

        Session-Buddy extends the envelope with the legacy
        ``key_count``/``pubkeys`` manifest fields (Phase 1.5) and
        the ``_aggregate`` summary; both additions are documented
        in the plan and predate Phase 1.3.
        """
        from session_buddy import server_optimized as so

        _install_signer_snapshot(cycles_total=10, errors_total=0)
        _install_publisher_snapshot(cycles_total=10, errors_total=0)

        body = await so.get_health()  # type: ignore[attr-defined]
        assert body["status"] in ("healthy", "warming_up", "degraded", "failed")
        assert isinstance(body["checks"], dict)
        assert "skills_signer" in body["checks"]
        assert "bodai_events" in body["checks"]

        # Reason codes are always a list of strings (StatusValue
        # members are str-Enum so ``.value`` is the JSON string).
        aggregate = body["checks"]["_aggregate"]
        assert isinstance(aggregate["reason_codes"], list)
        for code in aggregate["reason_codes"]:
            assert isinstance(code, str)
        # The halflife round-trips through ``_aggregate`` so the
        # operator can see which window the verdict was computed
        # against.
        assert aggregate["halflife_seconds"] == halflife


class TestGetHealthMatchesHttpRoute:
    """REQ-HC-003: ``get_health()`` MCP tool and ``/health`` HTTP route agree.

    Both surfaces call :func:`_build_health_snapshot` and translate
    the canonical ``StatusValue`` to the same wire code. The two
    responses are byte-for-byte equal modulo the synthetic
    ``status_code`` field that the MCP tool appends.
    """

    async def test_agree_on_healthy_state(self, halflife: int) -> None:
        from starlette.responses import JSONResponse

        from session_buddy import server_optimized as so

        _install_signer_snapshot(cycles_total=10, errors_total=0)
        _install_publisher_snapshot(cycles_total=10, errors_total=0)

        tool_body = await so.get_health()  # type: ignore[attr-defined]
        tool_status_code = tool_body.pop("status_code")

        # Re-run the route handler in-process. We do not need the
        # request object (the handler ignores it) but the signature
        # requires one.
        route_response: JSONResponse = await so.health_check(request=None)  # type: ignore[arg-type]
        route_body = _json_body(route_response)

        # The HTTP body omits the synthetic status_code field; the
        # MCP body carries it. After popping, the dicts must match.
        assert tool_body == route_body
        assert tool_status_code == route_response.status_code
        assert tool_status_code == 200

    async def test_agree_on_failed_state(self, halflife: int) -> None:
        from session_buddy import server_optimized as so

        # Signer singleton stays None (autouse fixture clears it);
        # publisher is healthy so the only failure is the signer.
        _install_publisher_snapshot(cycles_total=10, errors_total=0)

        tool_body = await so.get_health()  # type: ignore[attr-defined]
        tool_status_code = tool_body.pop("status_code")

        route_response = await so.health_check(request=None)  # type: ignore[arg-type]
        route_body = _json_body(route_response)

        assert tool_body == route_body
        assert tool_status_code == route_response.status_code
        assert tool_status_code == 503
        assert tool_body["status"] == "failed"


class TestHealthFeedHalflifeOverride:
    """The halflife is operator-tunable via ``HEALTH_FEED_HALFLIFE_SECONDS``."""

    async def test_halflife_from_env_propagates_to_aggregate(
        self,
    ) -> None:
        prior = os.environ.pop("HEALTH_FEED_HALFLIFE_SECONDS", None)
        os.environ["HEALTH_FEED_HALFLIFE_SECONDS"] = "120"
        try:
            from session_buddy import server_optimized as so

            _install_signer_snapshot(cycles_total=10, errors_total=0)
            _install_publisher_snapshot(cycles_total=10, errors_total=0)

            body = await so.get_health()  # type: ignore[attr-defined]
            assert body["checks"]["_aggregate"]["halflife_seconds"] == 120
        finally:
            if prior is None:
                os.environ.pop("HEALTH_FEED_HALFLIFE_SECONDS", None)
            else:
                os.environ["HEALTH_FEED_HALFLIFE_SECONDS"] = prior

    async def test_default_halflife_is_60s(self) -> None:
        """The Phase 1.3 default is 60s (overrides mcp-common's 300s)."""
        prior = os.environ.pop("HEALTH_FEED_HALFLIFE_SECONDS", None)
        try:
            from session_buddy import server_optimized as so

            assert so.DEFAULT_HEALTH_FEED_HALFLIFE_SECONDS == 60

            _install_signer_snapshot(cycles_total=10, errors_total=0)
            _install_publisher_snapshot(cycles_total=10, errors_total=0)

            body = await so.get_health()  # type: ignore[attr-defined]
            assert body["checks"]["_aggregate"]["halflife_seconds"] == 60
        finally:
            if prior is not None:
                os.environ["HEALTH_FEED_HALFLIFE_SECONDS"] = prior
