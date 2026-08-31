"""Tests for the shared checkpoint exception-scrubbing utilities.

Closes C-5 from the multi-agent review: PII must NEVER reach upstream
observability (or ``result.error``) via ``str(exc)`` for exceptions that
might carry URL path, query, userinfo, or response body content.

These tests use sentinel PII assertions (not just mock-call assertions) —
they verify the redaction actually happens, not just that the helper was
called. A passing test must contain no substring of the sentinel.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx2 as httpx
import pytest

from session_buddy.checkpoint.scrubbing import (
    safe_error_message,
    safe_transient_info,
)

# Sentinel PII fragments. Tests assert that NONE of these substrings appear
# anywhere in the helper output for an exception that was constructed to
# carry them.
SENTINEL_PATH = "/users/jane.doe@secret.example.com"
SENTINEL_QUERY = "token=abc123"
# Userinfo is split as ``user:SECRET-PASS`` (no host) so the URL host is
# ``secret.example.com`` — otherwise httpx would parse ``user:SECRET-PASS``
# + ``@example.com`` as userinfo + host, leaving ``secret.example.com``
# only inside the path, which would defeat the redaction-by-host test.
SENTINEL_USERINFO = "user:SECRET-PASS"
SENTINEL_BODY = "RESPONSE-BODY-LEAK"
SENTINEL_FRAGMENTS = (
    SENTINEL_PATH, SENTINEL_QUERY, SENTINEL_USERINFO,
    SENTINEL_BODY, "SECRET-PASS", "abc123",
)


def _make_leaky_httpx_error() -> httpx.HTTPStatusError:
    """Build an HTTPStatusError whose str(exc) carries the sentinel PII."""
    request = httpx.Request(
        "POST",
        f"http://{SENTINEL_USERINFO}@secret.example.com"
        f"{SENTINEL_PATH}?{SENTINEL_QUERY}",
    )
    response = httpx.Response(
        503, request=request, content=SENTINEL_BODY.encode(),
    )
    leaky_msg = (
        f"Server error on {SENTINEL_PATH}?{SENTINEL_QUERY} "
        f"with {SENTINEL_USERINFO} and body {SENTINEL_BODY}"
    )
    return httpx.HTTPStatusError(leaky_msg, request=request, response=response)


# --- safe_transient_info -----------------------------------------------------


@pytest.mark.unit
def test_safe_transient_info_with_httpx_error_returns_status_and_host_only() -> None:
    """For HTTPStatusError, the dict must contain ONLY {type, status, host}
    and must contain NO substring of the sentinel URL/body."""
    exc = _make_leaky_httpx_error()
    info = safe_transient_info(exc)

    assert set(info.keys()) <= {"type", "status", "host"}, (
        f"unexpected keys in info dict: {set(info.keys())}"
    )
    assert info["type"] == "HTTPStatusError"
    assert info["status"] == 503
    assert info["host"] == "secret.example.com"

    serialized = repr(info)
    for fragment in SENTINEL_FRAGMENTS:
        assert fragment not in serialized, (
            f"safe_transient_info leaked PII: {fragment!r} in {serialized!r}"
        )


@pytest.mark.unit
def test_safe_transient_info_with_value_error_returns_type_only() -> None:
    """For non-HTTP exceptions, the dict must be EXACTLY {"type": <name>}.

    The sentinel message must not appear anywhere in the returned dict.
    """
    exc = ValueError(
        f"failed to parse token={SENTINEL_QUERY} for {SENTINEL_USERINFO}",
    )
    info = safe_transient_info(exc)

    assert info == {"type": "ValueError"}, f"unexpected info: {info!r}"

    serialized = repr(info)
    for fragment in SENTINEL_FRAGMENTS:
        assert fragment not in serialized, (
            f"safe_transient_info leaked PII for non-HTTP exc: "
            f"{fragment!r} in {serialized!r}"
        )


@pytest.mark.unit
def test_safe_transient_info_with_malformed_httpx_error_does_not_crash() -> None:
    """An HTTPStatusError with broken attributes must not raise.

    Covers the defensive try/except: AttributeError/ValueError/TypeError
    fall through to the bare {"type": "..."} shape.
    """
    exc = _make_leaky_httpx_error()
    exc.request = None  # type: ignore[assignment]

    info = safe_transient_info(exc)
    assert "type" in info
    assert info["type"] == "HTTPStatusError"
    serialized = repr(info)
    for fragment in SENTINEL_FRAGMENTS:
        assert fragment not in serialized


@pytest.mark.unit
def test_safe_transient_info_does_not_call_str_exc() -> None:
    """Helper must never invoke ``str(exc)``.

    A MagicMock(BaseException) whose __str__ raises on call proves the
    helper never asks for the stringified form.
    """
    exc = MagicMock(spec=BaseException)
    exc.__str__ = MagicMock(side_effect=AssertionError("str(exc) was called"))

    info = safe_transient_info(exc)
    assert isinstance(info, dict)
    assert "type" in info
    exc.__str__.assert_not_called()


# --- safe_error_message ------------------------------------------------------


@pytest.mark.unit
def test_safe_error_message_with_httpx_error_omits_url_body() -> None:
    """Format: ``{prefix} HTTPStatusError (HTTP {status})``.

    The result must contain NO substring of the sentinel URL/body, even
    though ``str(exc)`` carries them.
    """
    exc = _make_leaky_httpx_error()
    msg = safe_error_message("snapshot failed (transient):", exc)

    assert msg.startswith("snapshot failed (transient):"), f"msg={msg!r}"
    assert "HTTPStatusError" in msg
    assert "HTTP 503" in msg

    for fragment in SENTINEL_FRAGMENTS:
        assert fragment not in msg, (
            f"safe_error_message leaked PII: {fragment!r} in {msg!r}"
        )


@pytest.mark.unit
def test_safe_error_message_with_non_httpx_returns_type_only() -> None:
    """Non-HTTP exceptions get ``{prefix} {type}`` and nothing else."""
    exc = ValueError(f"connection refused for {SENTINEL_USERINFO}")
    msg = safe_error_message("snapshot failed (unexpected):", exc)

    assert msg == "snapshot failed (unexpected): ValueError", f"msg={msg!r}"
    for fragment in SENTINEL_FRAGMENTS:
        assert fragment not in msg


@pytest.mark.unit
def test_safe_error_message_handles_broken_response_attribute() -> None:
    """When ``exc.response.status_code`` raises, the helper must fall back
    gracefully without propagating the AttributeError."""
    exc = _make_leaky_httpx_error()

    class _BoomResponse:
        @property
        def status_code(self) -> int:
            raise RuntimeError("simulated property failure")

    exc.response = _BoomResponse()  # type: ignore[assignment]
    msg = safe_error_message("forward failed:", exc)
    assert msg.startswith("forward failed:")
    assert "HTTPStatusError" in msg


# --- 5 migrated log sites: str(exc) must not appear in extra= -----------------


# Shared sentinel message injected into the exception that the migrated
# log site will stringify. If the site still uses str(exc), the sentinel
# appears in the captured extra= payload; the helper call should redact.
SENTINEL_EXC_MSG = (
    f"forward_to failed POST {SENTINEL_PATH}?{SENTINEL_QUERY} "
    f"from {SENTINEL_USERINFO} with body {SENTINEL_BODY}"
)


class _CaptureLogger:
    """Minimal structlog-shaped stub that captures ``(event, extra)`` tuples.

    Mirrors the pattern in test_orchestrator.py::test_forward_http_error_does_not_leak_url_or_response_body
    (lines 180-196) — monkeypatch ``module._log`` with one of these so we
    see exactly what the migrated log sites pass via ``extra=`` without
    fighting structlog's stdlib-propagation quirks.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, *args: object, **kwargs: object) -> None:
        self._record(event, kwargs)

    def warning(self, event: str, *args: object, **kwargs: object) -> None:
        self._record(event, kwargs)

    def exception(self, event: str, *args: object, **kwargs: object) -> None:
        self._record(event, kwargs)

    def info(self, event: str, *args: object, **kwargs: object) -> None:
        self._record(event, kwargs)

    def debug(self, event: str, *args: object, **kwargs: object) -> None:
        self._record(event, kwargs)

    def _record(self, event: str, kwargs: dict[str, object]) -> None:
        extra = kwargs.get("extra")
        if extra is None:
            return
        self.calls.append((event, dict(extra)))


def _assert_no_sentinel_in_extra(extra: dict[str, object]) -> None:
    """Check that NONE of the sentinel PII fragments appear in extra= field."""
    serialized = repr({k: str(v) for k, v in extra.items()})
    for fragment in SENTINEL_FRAGMENTS:
        assert fragment not in serialized, (
            f"log extra leaked PII: {fragment!r} in extra {extra!r}"
        )


@pytest.mark.unit
async def test_auto_checkpoint_loop_tick_error_does_not_leak_str_exc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migrated log site at auto_checkpoint_loop.py:80 must scrub str(exc)."""
    import asyncio

    from session_buddy.checkpoint import CheckpointOrchestrator
    from session_buddy.core import auto_checkpoint_loop as loop_mod

    cap = _CaptureLogger()
    monkeypatch.setattr(loop_mod, "_log", cap)

    orch = MagicMock(spec=CheckpointOrchestrator)
    orch.run_checkpoint = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(SENTINEL_EXC_MSG),
    )
    loop = loop_mod.AutoCheckpointLoop(
        interval_s=0.05, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: orch,
    )
    await loop.start()
    await asyncio.sleep(0.15)
    await loop.stop()

    tick_error = [c for c in cap.calls if c[0] == "auto_checkpoint_loop_tick_error"]
    assert tick_error, (
        f"expected an auto_checkpoint_loop_tick_error call; got: "
        f"{[c[0] for c in cap.calls]}"
    )
    for _event, extra in tick_error:
        _assert_no_sentinel_in_extra(extra)


@pytest.mark.unit
async def test_pending_consume_failed_does_not_leak_str_exc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migrated log site at auto_checkpoint_loop.py:102 must scrub str(exc)
    while keeping the marker field as a string."""
    import asyncio

    from session_buddy.checkpoint import (
        CheckpointOrchestrator, PendingCheckpoint, save_pending,
    )
    from session_buddy.core import auto_checkpoint_loop as loop_mod

    cap = _CaptureLogger()
    monkeypatch.setattr(loop_mod, "_log", cap)

    save_pending(PendingCheckpoint(working_dir=tmp_path, reason="subagent_idle_timeout"))

    async def failing_consume(_marker):  # type: ignore[no-untyped-def]
        raise RuntimeError(SENTINEL_EXC_MSG)

    orch = MagicMock(spec=CheckpointOrchestrator)
    orch.run_checkpoint = AsyncMock()  # type: ignore[method-assign]
    loop = loop_mod.AutoCheckpointLoop(
        interval_s=0.05, working_dir_resolver=lambda: tmp_path,
        orch_factory=lambda _d: orch, pending_consume_fn=failing_consume,
    )
    await loop.start()
    await asyncio.sleep(0.15)
    await loop.stop()

    pending = [c for c in cap.calls if c[0] == "pending_consume_failed"]
    assert pending, (
        f"expected a pending_consume_failed call; got: "
        f"{[c[0] for c in cap.calls]}"
    )
    for _event, extra in pending:
        _assert_no_sentinel_in_extra(extra)
        marker_val = extra.get("marker")
        assert marker_val is not None, (
            "pending_consume_failed must still carry the marker field"
        )


@pytest.mark.unit
def test_subagent_signal_read_failed_does_not_leak_str_exc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migrated log site at subagent_detector.py:36 must scrub str(exc)."""
    from session_buddy.checkpoint import subagent_detector as det_mod
    from session_buddy.checkpoint.subagent_detector import LockfileSignalSource

    cap = _CaptureLogger()
    monkeypatch.setattr(det_mod, "_log", cap)

    src = LockfileSignalSource(tmp_path / "x.lock")  # type: ignore[arg-type]

    class _BoomPath:
        def exists(self) -> bool:
            raise OSError(SENTINEL_EXC_MSG)

    src._path = _BoomPath()  # type: ignore[assignment]
    assert src.read() is True  # fail open

    read_calls = [c for c in cap.calls if c[0] == "subagent_signal_read_failed"]
    assert read_calls, f"got: {[c[0] for c in cap.calls]}"
    for _event, extra in read_calls:
        _assert_no_sentinel_in_extra(extra)


@pytest.mark.unit
def test_subagent_signal_write_failed_does_not_leak_str_exc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migrated log site at subagent_detector.py:47 must scrub str(exc)."""
    from session_buddy.checkpoint import subagent_detector as det_mod
    from session_buddy.checkpoint.subagent_detector import LockfileSignalSource

    cap = _CaptureLogger()
    monkeypatch.setattr(det_mod, "_log", cap)

    src = LockfileSignalSource(tmp_path / "x.lock")  # type: ignore[arg-type]

    class _BoomParent:
        def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
            raise OSError(SENTINEL_EXC_MSG)

    class _BoomPath:
        parent: Any = None

        def unlink(self, missing_ok: bool = False) -> None:
            raise OSError(SENTINEL_EXC_MSG)

    boom = _BoomPath()
    boom.parent = _BoomParent()
    src._path = boom  # type: ignore[assignment]
    src.write(active=True)
    src.write(active=False)

    write_calls = [c for c in cap.calls if c[0] == "subagent_signal_write_failed"]
    assert write_calls, f"got: {[c[0] for c in cap.calls]}"
    for _event, extra in write_calls:
        _assert_no_sentinel_in_extra(extra)


@pytest.mark.unit
def test_subagent_detector_is_active_failed_does_not_leak_str_exc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migrated log site at subagent_detector.py:61 must scrub str(exc)."""
    from session_buddy.checkpoint import subagent_detector as det_mod
    from session_buddy.checkpoint.subagent_detector import SubagentDetector

    cap = _CaptureLogger()
    monkeypatch.setattr(det_mod, "_log", cap)

    class _ExplodingSignal:
        def read(self) -> bool:
            raise RuntimeError(SENTINEL_EXC_MSG)

        def write(self, active: bool) -> None:
            pass

    detector = SubagentDetector(tmp_path, _ExplodingSignal())  # type: ignore[arg-type]
    assert detector.is_active() is True

    is_active = [
        c for c in cap.calls if c[0] == "subagent_detector_is_active_failed"
    ]
    assert is_active, f"got: {[c[0] for c in cap.calls]}"
    for _event, extra in is_active:
        _assert_no_sentinel_in_extra(extra)
        wd_val = extra.get("working_dir")
        assert wd_val is not None, (
            "is_active_failed must still carry the working_dir field"
        )


# --- End-to-end: NO str(exc) remains in the migrated source files ----------


@pytest.mark.unit
def test_no_str_exc_remains_in_migrated_source_files() -> None:
    """Grep-level guarantee: ``str(exc)`` is gone from the 5 sites."""
    import subprocess

    result = subprocess.run(
        [
            "grep", "-rn", "str(exc)",
            "session_buddy/core/auto_checkpoint_loop.py",
            "session_buddy/checkpoint/subagent_detector.py",
            "session_buddy/checkpoint/scrubbing.py",
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0 or not result.stdout.strip(), (
        f"str(exc) still present at: {result.stdout}"
    )
