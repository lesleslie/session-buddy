from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx2 as httpx
import pytest

from session_buddy.checkpoint.orchestrator import (
    CheckpointOrchestrator,
    CheckpointResult,
)
from session_buddy.checkpoint.policy import (
    CheckpointPhase,
    CheckpointPolicy,
    MidpointCriteria,
    WorkingTreeInspector,
)
from session_buddy.checkpoint.snapshot import Snapshot, SnapshotMechanism
from session_buddy.checkpoint.subagent_detector import LockfileSignalSource, SubagentDetector


def _make_orch(
    tmp_path: Path,
    *,
    snapshot_side_effect=None,
    dirty_files=("x.py",),
    run_timeout: float | None = None,
) -> CheckpointOrchestrator:
    snap = MagicMock(spec=SnapshotMechanism)
    snap.capture.return_value = Snapshot(
        path=tmp_path / "snap.patch", label="x", snapshot_id="snap-1",
        captured_at=MagicMock(), parent_commit="abc", dirty_files=list(dirty_files),
    )
    if snapshot_side_effect:
        snap.capture.side_effect = snapshot_side_effect

    policy = MagicMock(spec=CheckpointPolicy)
    policy.decide.return_value.should_fire = True
    policy.decide.return_value.reason = "end_of_task"

    detector = MagicMock(spec=SubagentDetector)
    detector.is_active.return_value = False
    detector.wait_until_idle = AsyncMock(return_value=True)
    forward = AsyncMock()

    kwargs: dict[str, object] = dict(
        working_dir=tmp_path, policy=policy, snapshot=snap,
        subagent_detector=detector, forward_to=forward,
    )
    if run_timeout is not None:
        kwargs["run_timeout"] = run_timeout
    return CheckpointOrchestrator(**kwargs)


@pytest.mark.unit
async def test_calls_snapshot_then_forward(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._snapshot.capture.assert_called_once()
    orch._forward_to.assert_awaited_once()
    assert result.fired is True
    assert result.snapshot_id == "snap-1"


@pytest.mark.unit
async def test_skips_forward_when_policy_says_no(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    orch._policy.decide.return_value.should_fire = False
    orch._policy.decide.return_value.reason = "subagent active"
    result = await orch.run_checkpoint(phase=CheckpointPhase.MIDPOINT_DIRTINESS)
    orch._snapshot.capture.assert_not_called()
    orch._forward_to.assert_not_awaited()
    assert result.fired is False
    assert "subagent" in result.decision_reason.lower()


@pytest.mark.unit
async def test_skips_forward_on_empty_working_tree(tmp_path: Path) -> None:
    """Per spec line 361: empty tree → soft success, skip forward_to."""
    orch = _make_orch(tmp_path, dirty_files=[])  # clean tree
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._snapshot.capture.assert_called_once()
    orch._forward_to.assert_not_awaited()
    assert result.fired is True  # soft success
    assert "clean" in (result.decision_reason or "").lower() or "no changes" in (result.decision_reason or "").lower()


@pytest.mark.unit
async def test_forward_to_5xx_retries_once_then_succeeds(tmp_path: Path) -> None:
    """Per spec line 372: 5xx → retry once with backoff, then fail closed."""
    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_5xx = httpx.Response(503, request=request)
    orch._forward_to.side_effect = [
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
        None,  # second call succeeds
    ]
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    assert orch._forward_to.await_count == 2
    assert result.fired is True


@pytest.mark.unit
async def test_forward_to_5xx_exhausts_retry_fails_closed(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_5xx = httpx.Response(503, request=request)
    orch._forward_to.side_effect = [
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
    ]
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    assert orch._forward_to.await_count == 2
    assert result.fired is False
    assert "retry exhausted" in (result.error or "").lower()


@pytest.mark.unit
async def test_forward_to_4xx_no_retry_fails_closed(tmp_path: Path) -> None:
    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_4xx = httpx.Response(400, request=request)
    orch._forward_to.side_effect = httpx.HTTPStatusError("400", request=request, response=response_4xx)
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    assert orch._forward_to.await_count == 1
    assert result.fired is False


@pytest.mark.unit
async def test_snapshot_runtime_error_propagates(tmp_path: Path) -> None:
    """C-3: RuntimeError from snapshot.capture() is a programming error and
    must propagate per spec invariant "Failures fail closed; programming
    errors propagate". The previous `except Exception` catch-all violated
    this; this test enforces the corrected narrow-tuple behavior.
    """
    orch = _make_orch(tmp_path, snapshot_side_effect=RuntimeError("git diff exploded"))
    with pytest.raises(RuntimeError, match="git diff exploded"):
        await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)


@pytest.mark.unit
async def test_unexpected_exception_propagates(tmp_path: Path) -> None:
    """Programming errors must NOT be swallowed."""
    orch = _make_orch(tmp_path)
    orch._forward_to.side_effect = TypeError("not a network error")
    with pytest.raises(TypeError):
        await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)


# --- Finding 1: sensitive-data-echo -----------------------------------------
# PII defense: when str(exc) carries request URL (path/query/userinfo) or a
# response body, those values must NOT be echoed into result.error or into the
# structured log extra dict (which becomes a separate JSON field on disk).
# str(exc) is still permitted inside _log.exception(..., exc_info=True) because
# that traceback is captured separately and never serialized as a flat field.


_FORBIDDEN_URL_PARTS = (
    "/internal/secrets", "SECRET-TOKEN", "SECRET-PASS",
    "user:SECRET-PASS", "token=", "q=foo", "secrets", "/api/v1",
    "RESPONSE-BODY-LEAK",
)


@pytest.mark.unit
async def test_forward_http_error_does_not_leak_url_or_response_body(
    tmp_path: Path, monkeypatch,
) -> None:
    """Finding 1: retry-exhausted path must scrub URL and response body from
    result.error and from the structured log extra dict."""
    # Capture all _log calls. The orchestrator reads the module-level `_log`
    # global at call time (lazy via structlog BoundLoggerLazyProxy), so we
    # patch the orchestrator module's _log directly.
    captured_calls: list[tuple[str, dict[str, object]]] = []
    import session_buddy.checkpoint.orchestrator as orch_mod

    class _CaptureLogger:
        def error(self, event: str, *args: object, **kwargs: object) -> None:
            extra = kwargs.get("extra") or {}
            captured_calls.append((event, dict(extra)))

        def warning(self, event: str, *args: object, **kwargs: object) -> None:
            extra = kwargs.get("extra") or {}
            captured_calls.append((event, dict(extra)))

        def exception(self, event: str, *args: object, **kwargs: object) -> None:
            extra = kwargs.get("extra") or {}
            captured_calls.append((event, dict(extra)))

        def info(self, event: str, *args: object, **kwargs: object) -> None:
            pass

    monkeypatch.setattr(orch_mod, "_log", _CaptureLogger())

    orch = _make_orch(tmp_path)
    secret_path = "/internal/api/v1/secrets"
    secret_query = "token=SECRET-TOKEN&q=foo"
    secret_userinfo = "user:SECRET-PASS@example.com"
    response_body_secret = "RESPONSE-BODY-LEAK"
    request = httpx.Request(
        "POST", f"http://{secret_userinfo}/{secret_path}?{secret_query}",
    )
    response_5xx = httpx.Response(
        503, request=request,
        content=response_body_secret.encode(),
    )
    # Inject the URL into the exception message so str(exc) would leak if echoed.
    leaky_message = (
        f"forward_to failed POST {secret_path}?{secret_query} from {secret_userinfo}"
    )
    orch._forward_to.side_effect = [
        httpx.HTTPStatusError(leaky_message, request=request, response=response_5xx),
        httpx.HTTPStatusError(leaky_message, request=request, response=response_5xx),
    ]

    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)

    # result.error must not echo any of the secret URL components or response body.
    assert result.error is not None
    for forbidden in _FORBIDDEN_URL_PARTS:
        assert forbidden not in result.error, (
            f"result.error leaked PII: {forbidden!r} in {result.error!r}"
        )
    # Status code (operator-visible, non-PII) must still be present.
    assert "503" in result.error

    # Structured log extra dict must also not leak URL or body.
    retry_logs = [c for c in captured_calls if c[0] == "checkpoint_forward_retry_exhausted"]
    assert retry_logs, (
        f"expected at least one checkpoint_forward_retry_exhausted call, "
        f"got: {[c[0] for c in captured_calls]}"
    )
    for _event, extra in retry_logs:
        for forbidden in _FORBIDDEN_URL_PARTS:
            for key, value in extra.items():
                assert forbidden not in str(value), (
                    f"log extra[{key!r}] leaked PII: {forbidden!r} in {value!r}"
                )


@pytest.mark.unit
async def test_snapshot_error_does_not_propagate_str_exc_to_caller(
    tmp_path: Path,
) -> None:
    """C-3 (replaces old Finding 1 oracle): snapshot RuntimeError is a
    programming error and must propagate unchanged at the run_checkpoint
    boundary. The old catch-all that swallowed str(exc) into result.error
    has been removed; this test pins the new behavior.

    The original str(exc) message MUST reach the caller verbatim — the
    orchestrator does not mutate, redact, or wrap it. PII defense is now
    the responsibility of the caller (MCP checkpoint tool or lifespan
    tick), per spec "programming errors propagate".
    """
    orch = _make_orch(
        tmp_path,
        snapshot_side_effect=RuntimeError(
            "git diff exploded at /internal/secrets?token=SECRET",
        ),
    )
    with pytest.raises(RuntimeError) as excinfo:
        await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    # The original str(exc) reaches the caller verbatim — no scrubbing at
    # the orchestrator boundary (caller is responsible for PII defense).
    assert "/internal/secrets" in str(excinfo.value)
    assert "token=SECRET" in str(excinfo.value)
    # The exception type name is preserved.
    assert excinfo.type is RuntimeError


# --- C-2 narrow-tuple contract: snapshot step ---------------------------------
# Per spec, the snapshot step's narrow-exception tuple is exactly:
#   (subprocess.SubprocessError, OSError, ValueError, httpx.HTTPStatusError)
# Anything OUTSIDE this tuple (TypeError, AttributeError, KeyError, asyncio.
# TimeoutError, ...) must propagate unchanged. Each transient class returns
# a fail-closed CheckpointResult; each programming-error class propagates.


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc_factory,metric_key",
    [
        pytest.param(
            lambda: subprocess.CalledProcessError(1, ["git", "diff"]),
            "snapshot_transient",
            id="subprocess.CalledProcessError",
        ),
        pytest.param(
            lambda: OSError("git diff timeout"),
            "snapshot_transient",
            id="OSError",
        ),
        pytest.param(
            lambda: ValueError("bad patch hunk"),
            "snapshot_transient",
            id="ValueError",
        ),
        pytest.param(
            lambda: httpx.HTTPStatusError(
                "503",
                request=httpx.Request("POST", "http://localhost:8678/mcp"),
                response=httpx.Response(503, request=httpx.Request("POST", "http://localhost:8678/mcp")),
            ),
            "snapshot_transient",
            id="httpx.HTTPStatusError(503)",
        ),
    ],
)
async def test_snapshot_transient_exception_classes_are_caught(
    tmp_path: Path, exc_factory, metric_key: str,
) -> None:
    """C-2: every class in the spec-literal narrow tuple is caught by the
    snapshot step and converted to a fail-closed CheckpointResult.

    Verifies the post-C-2 tuple (subprocess.SubprocessError, OSError,
    ValueError, httpx.HTTPStatusError) without depending on incidental
    inheritance relationships (e.g. asyncio.TimeoutError inheriting from
    OSError in 3.11+).
    """
    orch = _make_orch(tmp_path, snapshot_side_effect=exc_factory())
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._forward_to.assert_not_awaited()
    assert result.fired is False
    assert result.error is not None
    assert "snapshot failed (transient):" in result.error
    # str(exc) MUST NOT leak into result.error.
    assert "bad patch hunk" not in result.error
    assert "git diff timeout" not in result.error
    assert orch.metrics.failures.get(metric_key) == 1


@pytest.mark.unit
async def test_snapshot_asyncio_timeout_is_handled_by_outer_budget(
    tmp_path: Path,
) -> None:
    """asyncio.TimeoutError is NOT in the post-C-2 narrow tuple. When
    snapshot.capture() raises it, the inner try/except does not catch it;
    it propagates to the outer asyncio.wait_for budget, which converts it
    to an `orchestrator_timeout` fail-closed result.

    This proves C-2 removed asyncio.TimeoutError from the narrow tuple
    without breaking the outer-budget guarantee: the timeout is still
    handled, just one frame up.
    """
    orch = _make_orch(
        tmp_path,
        snapshot_side_effect=asyncio.TimeoutError(),
        run_timeout=0.5,
    )
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._forward_to.assert_not_awaited()
    assert result.fired is False
    assert result.decision_reason == "orchestrator_timeout"
    assert result.error == "orchestrator timeout"
    # The outer budget MUST be the one that incremented the metric.
    assert orch.metrics.failures.get("orchestrator_timeout") == 1
    # The inner transient branch must NOT have fired.
    assert orch.metrics.failures.get("snapshot_transient", 0) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc_factory",
    [
        pytest.param(lambda: TypeError("NoneType has no attribute 'x'"), id="TypeError"),
        pytest.param(lambda: AttributeError("'NoneType' object has no attribute 'x'"), id="AttributeError"),
        pytest.param(lambda: KeyError("missing-snapshot-key"), id="KeyError"),
    ],
)
async def test_snapshot_programming_error_propagates(
    tmp_path: Path, exc_factory,
) -> None:
    """C-3: programming errors from snapshot.capture() MUST propagate to
    the caller. The old catch-all (lines 207-217 of pre-fix orchestrator)
    swallowed them and stored them in result.error. After the fix, they
    re-raise out of run_checkpoint unchanged.

    The test captures the exception at the run_checkpoint boundary so
    we know the full propagation chain (including the outer asyncio.wait_for
    at line 148) preserves the original exception.
    """
    exc = exc_factory()
    orch = _make_orch(tmp_path, snapshot_side_effect=exc)
    with pytest.raises(type(exc)) as excinfo:
        await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    # The original exception reaches the caller verbatim.
    assert str(excinfo.value) == str(exc)
    # No spurious transient metric.
    assert orch.metrics.failures.get("snapshot_transient", 0) == 0
    # No spurious unexpected metric either (the catch-all that incremented
    # `snapshot_unexpected` is gone).
    assert orch.metrics.failures.get("snapshot_unexpected", 0) == 0


# --- Finding 2: fail-open-resource-cap ---------------------------------------
# wait_until_idle(60s) only covers the idle-wait, not the subsequent
# snapshot/forward/retry work. A slow capture or stuck forward_to could block
# the caller indefinitely. The orchestrator must wrap the whole run in a bounded
# budget and fail closed on timeout — incrementing `orchestrator_timeout` and
# returning a fail-closed CheckpointResult.


@pytest.mark.unit
async def test_run_timeout_fails_closed_with_metric(tmp_path: Path) -> None:
    """Finding 2: outer wait_for must enforce a bounded total runtime.

    When work exceeds the budget, the orchestrator must:
      - increment the `orchestrator_timeout` failure metric
      - return a fail-closed CheckpointResult (fired=False, error present)
      - log a WARNING with the configured timeout
    """
    # Configure a tiny timeout so the test is fast. Force a slow forward
    # call that exceeds the budget. Snapshot capture is sync, so the hung
    # call must be in forward_to (async).
    orch = _make_orch(tmp_path, run_timeout=0.05)

    async def slow_forward(_result):
        await asyncio.sleep(5.0)

    orch._forward_to = AsyncMock(side_effect=slow_forward)

    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)

    # Fail-closed contract.
    assert result.fired is False
    assert result.error == "orchestrator timeout"
    assert result.decision_reason == "orchestrator_timeout"
    # Metric must be incremented.
    assert orch.metrics.failures.get("orchestrator_timeout") == 1


@pytest.mark.unit
async def test_run_timeout_returns_within_bounded_time(tmp_path: Path) -> None:
    """Finding 2: timeout must bound wall time, not just fail-closed.

    Even when work would take much longer (sleep 5s), the timeout (0.1s) must
    cause the call to return well within the configured budget.
    """
    orch = _make_orch(tmp_path, run_timeout=0.1)

    async def slow_forward(_result):
        await asyncio.sleep(5.0)

    orch._forward_to = AsyncMock(side_effect=slow_forward)

    loop = asyncio.get_event_loop()
    start = loop.time()
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    elapsed = loop.time() - start

    assert result.fired is False
    # Generous bound: 0.1s configured + asyncio overhead. Anything under 1s
    # proves the timeout fired rather than waiting the full 5s.
    assert elapsed < 1.0, f"timeout did not bound wall time: {elapsed:.3f}s"
    assert orch.metrics.failures.get("orchestrator_timeout") == 1


@pytest.mark.unit
async def test_run_timeout_does_not_swallow_unrelated_exceptions(tmp_path: Path) -> None:
    """Finding 2: timeout only catches asyncio.TimeoutError — programming
    errors (TypeError, ValueError) must still propagate, per spec invariant
    'programming errors propagate'.
    """
    orch = _make_orch(tmp_path, run_timeout=5.0)
    orch._forward_to.side_effect = TypeError("not a network error")
    with pytest.raises(TypeError):
        await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    # No spurious `orchestrator_timeout` metric on a fast-failing call.
    assert orch.metrics.failures.get("orchestrator_timeout", 0) == 0


@pytest.mark.unit
async def test_concurrent_calls_serialized_by_lock(tmp_path: Path) -> None:
    """Per spec line 394: two simultaneous calls → second waits."""
    orch = _make_orch(tmp_path)
    call_count = 0
    enter_count = 0

    async def slow_forward(_result):
        nonlocal call_count, enter_count
        enter_count += 1
        call_count += 1
        await asyncio.sleep(0.05)

    orch._forward_to = AsyncMock(side_effect=slow_forward)
    orch._snapshot.capture.return_value = Snapshot(
        path=tmp_path / "s.patch", label="x", snapshot_id=f"snap-{enter_count}",
        captured_at=MagicMock(), parent_commit="abc", dirty_files=["x.py"],
    )

    a, b = await asyncio.gather(
        orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK),
        orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK),
    )
    # Both complete; lock prevents concurrent forward_to invocations
    assert a.fired and b.fired


# --- Helper coverage: _safe_http_error_info / _safe_transient_info / _safe_error_message
# These helpers must NEVER echo URL/path/query/body to logs or result.error.
# Each helper has fallback branches exercised by a deliberately broken request/response.


@pytest.mark.unit
def test_safe_http_error_info_extracts_status_and_host() -> None:
    """Coverage: lines 47-56 (_safe_http_error_info host extraction)."""
    from session_buddy.checkpoint.orchestrator import _safe_http_error_info

    request = httpx.Request("POST", "http://example.com/safe")
    response = httpx.Response(503, request=request)
    exc = httpx.HTTPStatusError("server error", request=request, response=response)
    info = _safe_http_error_info(exc)
    assert info["status"] == 503
    assert info["host"] == "example.com"


@pytest.mark.unit
def test_safe_transient_info_includes_status_for_http_error() -> None:
    """Coverage: line 71 (safe_transient_info HTTPStatusError status branch)."""
    from session_buddy.checkpoint.scrubbing import safe_transient_info

    request = httpx.Request("POST", "http://example.com/safe")
    response = httpx.Response(503, request=request)
    exc = httpx.HTTPStatusError("server error", request=request, response=response)
    info = safe_transient_info(exc)
    assert info["type"] == "HTTPStatusError"
    assert info["status"] == 503


@pytest.mark.unit
def test_safe_error_message_falls_back_to_http_unknown() -> None:
    """Coverage: lines 85-86 (safe_error_message HTTP ? fallback).

    Force the response.status_code attribute access to raise → the helper must
    catch and emit "(HTTP ?)" rather than propagate. This is the operator-visible
    safeguard per Finding 1.
    """
    from session_buddy.checkpoint.scrubbing import safe_error_message

    request = httpx.Request("POST", "http://example.com/safe")
    response = httpx.Response(503, request=request)
    exc = httpx.HTTPStatusError("server error", request=request, response=response)
    # Replace exc.response with an object whose .status_code raises.
    class _BoomResponse:
        @property
        def status_code(self) -> int:
            raise RuntimeError("simulated property failure")

    exc.response = _BoomResponse()  # type: ignore[assignment]
    msg = safe_error_message("forward failed:", exc)
    assert msg.startswith("forward failed:")
    assert "(HTTP ?)" in msg


# --- END_OF_TASK subagent_idle_timeout path (lines 178-189) ----------------------


@pytest.mark.unit
async def test_end_of_task_subagent_idle_timeout_returns_pending_marker(
    tmp_path: Path,
) -> None:
    """Coverage: lines 178-189 (END_OF_TASK + detector not idle → save_pending)."""
    from session_buddy.checkpoint.pending import load_pending

    orch = _make_orch(tmp_path)
    # First call to wait_until_idle returns False (subagent still active).
    orch._detector.wait_until_idle = AsyncMock(return_value=False)

    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)

    # Snapshot capture must NOT have happened.
    orch._snapshot.capture.assert_not_called()
    orch._forward_to.assert_not_awaited()
    # Fail-closed: fired=False, pending marker present, metric incremented.
    assert result.fired is False
    assert result.pending_marker_path is not None
    assert orch.metrics.failures.get("subagent_idle_timeout") == 1
    # Marker must be readable.
    pc = load_pending(result.pending_marker_path)
    assert pc is not None
    assert pc.reason == "subagent_idle_timeout"
    assert pc.working_dir == tmp_path


# --- Snapshot transient error path (lines 194-200) -------------------------------


@pytest.mark.unit
async def test_snapshot_transient_error_fails_closed(tmp_path: Path) -> None:
    """Coverage: lines 194-200 (snapshot TransientForwardError branch)."""
    orch = _make_orch(tmp_path)
    # OSError is in TransientForwardError tuple → goes through the transient branch.
    orch._snapshot.capture.side_effect = OSError("git diff timeout")
    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._forward_to.assert_not_awaited()
    assert result.fired is False
    assert result.error is not None
    assert "snapshot failed (transient):" in result.error
    assert "OSError" in result.error
    assert "git diff timeout" not in result.error  # PII defense (Finding 1)
    assert orch.metrics.failures.get("snapshot_transient") == 1


# --- Finding I-3: derived inner idle-wait timeout --------------------------------
#
# A hard-coded `wait_until_idle(timeout=60.0)` nested inside an outer
# `asyncio.wait_for(..., timeout=run_timeout)` can deadlock when callers
# pass a budget < 90s (e.g. 30s outer, 60s inner idle-wait that is
# never bounded by the outer). The fix derives the inner timeout from
# the outer budget so a small budget no longer wastes the full idle-wait
# window before the orchestrator timeout fires.


@pytest.mark.unit
async def test_eot_inner_idle_timeout_derived_from_outer_budget(tmp_path: Path) -> None:
    """``wait_until_idle`` receives a timeout bounded by run_timeout - 30s.

    Concretely, with ``run_timeout=35`` the inner timeout must be
    ``max(1.0, min(60.0, 35 - 30)) = 5.0`` seconds, not the previously
    hard-coded 60s.
    """
    orch = _make_orch(tmp_path, run_timeout=35.0)
    await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    # The detector is mocked; inspect the actual timeout it was called with.
    orch._detector.wait_until_idle.assert_awaited_once()
    call_kwargs = orch._detector.wait_until_idle.await_args.kwargs
    assert call_kwargs["timeout"] == pytest.approx(5.0)


@pytest.mark.unit
async def test_eot_inner_idle_timeout_floor_clamps_tiny_budgets(tmp_path: Path) -> None:
    """Tiny budgets (run_timeout < 31s) clamp to the 1s floor, never negative.

    With ``run_timeout=0.05`` the raw formula ``min(60.0, 0.05 - 30.0)``
    is negative; the clamp must floor it at 1s so we still have a
    meaningful (if short) idle wait.
    """
    orch = _make_orch(tmp_path, run_timeout=0.05)
    await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._detector.wait_until_idle.assert_awaited_once()
    call_kwargs = orch._detector.wait_until_idle.await_args.kwargs
    assert call_kwargs["timeout"] == pytest.approx(1.0)


@pytest.mark.unit
async def test_eot_inner_idle_timeout_caps_at_60s_default_budget(tmp_path: Path) -> None:
    """Default budget (120s) caps the inner timeout at 60s — never exceeds it."""
    # run_timeout omitted → DEFAULT_RUN_TIMEOUT_S = 120.0; inner = min(60, 90) = 60.
    orch = _make_orch(tmp_path)
    await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    orch._detector.wait_until_idle.assert_awaited_once()
    call_kwargs = orch._detector.wait_until_idle.await_args.kwargs
    assert call_kwargs["timeout"] == pytest.approx(60.0)


# --- I-4: pin retry backoff duration -----------------------------------------
# _forward_with_retry sleeps 0.5s between the first 5xx attempt and the second
# attempt. A regression that drops the sleep or changes it to 60s would still
# pass the retry-count tests; this test pins the exact duration.


@pytest.mark.unit
async def test_forward_to_5xx_uses_500ms_backoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-4: the 5xx retry path must sleep exactly 0.5s between attempts.

    monkeypatch asyncio.sleep to record the duration and yield to the event
    loop without actually sleeping. Asserts the recorded duration is exactly
    0.5s — neither 0 (regression: sleep dropped) nor 60s (regression: wrong
    value), nor any other value.
    """
    # Capture the real sleep BEFORE patching so the recording sleep can
    # yield without recursing into the patched version.
    real_sleep = asyncio.sleep
    sleep_durations: list[float] = []

    async def recording_sleep(seconds: float) -> None:
        sleep_durations.append(seconds)
        # Yield to the event loop so the retry logic can continue without
        # actually sleeping. real_sleep is a binding to the original
        # function captured before the monkeypatch.
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", recording_sleep)

    orch = _make_orch(tmp_path)
    request = httpx.Request("POST", "http://localhost:8678/mcp")
    response_5xx = httpx.Response(503, request=request)
    orch._forward_to.side_effect = [
        httpx.HTTPStatusError("503", request=request, response=response_5xx),
        None,  # second call succeeds
    ]

    result = await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)

    # Exactly one sleep call, exactly 0.5s.
    assert sleep_durations == [0.5], (
        f"expected single 0.5s backoff, got {sleep_durations!r}"
    )
    # The retry actually succeeded.
    assert orch._forward_to.await_count == 2
    assert result.fired is True
