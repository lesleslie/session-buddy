"""CLI fallback for missing quality-scoring metrics.

Invokes the Crackerjack CLI on-demand when the consumer chain has no
historical metrics or the producer subprocess failed. Returns the
requested metric keys (subset of parsed_data), or None on any failure.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Literal

from session_buddy.config import feature_flags
from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Observability helpers (Task 7)
#
# These helpers are the single point of metric + log + span emission for
# every invocation. The body of `try_crackerjack_cli` calls `_finalize`
# at each return path with the right outcome label.
# ---------------------------------------------------------------------------


# OTel tracer (lazy import; no-op when not configured)
_TRACER = None


class _NoOpSpan:
    """No-op context manager used when OTel isn't configured.

    `tracer.start_as_current_span(...)` returns a
    `contextlib.AbstractContextManager[Span]`. When the tracer is
    `None` we substitute this class so the `with span_cm as span:`
    block in `try_crackerjack_cli` works without an `if`-sentinel
    on every operation. `set_status` / `set_attribute` are no-ops
    because there is no underlying span to mutate.
    """

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False  # do not swallow exceptions

    def set_status(self, status_code, description: str | None = None) -> None:
        pass

    def set_attribute(self, key: str, value: object) -> None:
        pass


def _get_tracer():
    """Lazy-init the OpenTelemetry tracer. Returns None when not configured."""
    global _TRACER
    if _TRACER is not None:
        return _TRACER
    try:
        from opentelemetry import trace

        _TRACER = trace.get_tracer(__name__)
    except Exception:
        _TRACER = None
    return _TRACER


def _emit_counter(command: str, outcome: str, caller: str) -> None:
    """Increment the unified invocation counter with command+outcome+caller labels."""
    try:
        from session_buddy.metrics import CRACKERJACK_FALLBACK_INVOCATIONS

        CRACKERJACK_FALLBACK_INVOCATIONS.labels(
            command=command, outcome=outcome, caller=caller
        ).inc()
    except Exception:
        pass  # metrics are best-effort


def _observe_duration(command: str, caller: str, duration_seconds: float) -> None:
    """Record the invocation duration in the histogram."""
    try:
        from session_buddy.metrics import CRACKERJACK_FALLBACK_DURATION_SECONDS

        CRACKERJACK_FALLBACK_DURATION_SECONDS.labels(
            command=command, caller=caller
        ).observe(duration_seconds)
    except Exception:
        pass


def _finalize(
    outcome: str,
    command: str,
    caller: str,
    project_dir: Path,
    missing_metrics: frozenset[str],
    duration_seconds: float,
    correlation_context: dict[str, str] | None,
    span: object | None = None,
) -> None:
    """Single point of observability emission. Exactly one log + one counter + one histogram observation per invocation.

    Also writes the outcome onto the OTel span (if provided) and
    marks failure outcomes with `set_status(StatusCode.ERROR)` so
    error rates in the tracing UI surface them correctly.
    """
    level_map = {
        "success": logging.INFO,
        "disabled": logging.DEBUG,
        "missing_executable": logging.ERROR,
    }
    level = level_map.get(outcome, logging.WARNING)
    logger.log(
        level,
        "crackerjack fallback invoked",
        extra={
            "command": command,
            "project_dir": str(project_dir),
            "project_name": project_dir.name,
            "missing_metrics": sorted(missing_metrics),
            "duration_seconds": round(duration_seconds, 3),
            "outcome": outcome,
            "caller": caller,
            "session_id": (correlation_context or {}).get("session_id"),
            "workflow_id": (correlation_context or {}).get("workflow_id"),
        },
    )
    _emit_counter(command, outcome, caller)
    _observe_duration(command, caller, duration_seconds)
    # OTel: tag the span with outcome + mark failures as errors
    if span is not None:
        try:
            span.set_attribute("outcome", outcome)
            span.set_attribute("project_dir", str(project_dir))
            if outcome not in ("success", "disabled"):
                # Lazy import to avoid a hard dep when OTel missing
                from opentelemetry.trace import Status, StatusCode

                span.set_status(Status(StatusCode.ERROR, f"{outcome}: {caller}"))
        except Exception:
            pass


# All-four convenience: pick the most general semantic command that
# produces every requested key.
def _pick_invocation(missing: frozenset[str]) -> tuple[str, tuple[str, ...]]:
    """Select the crackerjack invocation that fills the requested gaps.

    The only viable invocation for a 30-second-budgeted CLI fallback is
    ``run --comp --skip-hooks`` with the ``check`` semantic command. It
    produces all four scoring keys within the timeout.
    """
    del missing  # unused — check --comp --skip-hooks covers all keys
    return ("check", ("--comp", "--skip-hooks"))


# Module-level lock serializes fallback invocations to prevent N parallel
# subprocesses from concurrent consumer reads. The fallback is on the cold
# path (only fires when prior tiers failed) so contention is rare.
_FALLBACK_LOCK: asyncio.Lock = asyncio.Lock()


def _classify_proc_failure(returncode: int | None, stderr_text: str) -> str:
    """Map a non-zero subprocess outcome to an outcome label.

    The producer path can spawn a healthy Python interpreter but still
    hit ``ModuleNotFoundError`` when the crackerjack distribution is not
    installed in the active environment. Python emits an exit-code-2 with
    a ``No module named 'crackerjack'`` line on stderr; classify that as
    ``missing_executable`` rather than the generic ``nonzero_exit`` so the
    alert routing can split "install the package" from "crackerjack
    itself returned an error".
    """
    if returncode == 2 and "No module named 'crackerjack'" in stderr_text:
        return "missing_executable"
    return "nonzero_exit"


async def _acquire_fallback_lock(span: object | None = None) -> None:
    """Acquire the module-level serialization lock.

    Wraps ``_FALLBACK_LOCK.acquire()`` so a ``CancelledError`` raised
    while waiting (typically by ``asyncio.wait_for`` consuming the outer
    budget) is observed before propagating. Without this wrapper the
    lock-cancel falls outside the ``except CancelledError`` block that
    records the "cancelled" outcome on the subprocess path, so the
    counter / span / log trio would silently undercount cancellations.
    """
    try:
        await _FALLBACK_LOCK.acquire()
    except asyncio.CancelledError:
        # Observability is best-effort here — the lock is already in its
        # own micro-task; emitting a counter increment without the
        # other finalize fields would understate severity. Just log.
        try:
            logger.warning(
                "crackerjack fallback cancelled while waiting for serialization lock",
                extra={"outcome": "cancelled_lock_wait"},
            )
            _emit_counter("check", "cancelled_lock_wait", "consumer_chain")
        except Exception:
            pass
        raise


async def _spawn_subprocess(
    argv: list[str],
    project_path: Path,
) -> tuple[object | None, str | None]:
    """Spawn the crackerjack subprocess.

    Returns ``(proc, None)`` on success or ``(None, outcome_label)`` when
    the spawn itself fails. Higher-level code maps ``outcome_label`` to a
    finalize call so the caller keeps the single-emit invariant.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(project_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return proc, None
    except FileNotFoundError:
        return None, "missing_executable"
    except PermissionError:
        return None, "permission_error"
    except OSError:
        return None, "os_error"


async def _wait_for_proc(
    proc: object,
    timeout: float,
    span: object | None = None,
) -> tuple[bytes | None, bytes | None, str | None]:
    """Wait for the subprocess to finish.

    Returns ``(stdout_bytes, stderr_bytes, None)`` on success,
    ``(None, None, outcome_label)`` when the wait terminates via timeout
    or cancellation. The caller is responsible for cleaning up the
    process when ``outcome_label`` is not None. Returning decoupled
    bytes (not pre-decoded str) lets the caller decode once at the
    parser boundary so the ``CrackerjackOutputParser.parse_output`` call
    shape matches the parser's documented str signature.
    """
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return stdout, stderr, None
    except TimeoutError:
        if proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
        return None, None, "timeout"
    except asyncio.CancelledError:
        if proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
        return None, None, "cancelled"


def _extract_sections(parsed_data: dict, missing: frozenset[str]) -> dict[str, float]:
    """Project ``parsed_data`` onto the ``missing`` scoring keys.

    An empty section (``None``, ``[]``, ``{}``) means the metric was not
    measured by crackerjack; skip it to avoid the synthesize-perfect-score
    antipattern. Coverage uses the full ``parsed_data`` because its section
    helper expects that shape; the other three consume their own section.
    """
    SECTION_FOR_KEY = {
        "code_coverage": "coverage_summary",
        "lint_score": "lint_issues",
        "security_score": "security_issues",
        "complexity_score": "complexity_data",
    }
    # Lazy import helper: avoid pulling CrackerjackIntegration at module
    # import (its constructor reaches for SQLite).
    from session_buddy.crackerjack_integration import CrackerjackIntegration

    cls = CrackerjackIntegration
    candidate: dict[str, float] = {}
    for key in missing:
        section_key = SECTION_FOR_KEY.get(key)
        if section_key is None:
            continue
        section = parsed_data.get(section_key)
        if not section:
            continue
        if key == "code_coverage":
            candidate.update(cls._calculate_coverage_metrics(parsed_data))
        elif key == "lint_score":
            candidate.update(cls._calculate_lint_metrics(section))
        elif key == "security_score":
            candidate.update(cls._calculate_security_metrics(section))
        elif key == "complexity_score":
            candidate.update(cls._calculate_complexity_metrics(section))
    return {k: v for k, v in candidate.items() if k in missing}


def _build_argv(flag_args: tuple[str, ...]) -> list[str]:
    """Compose the crackerjack subprocess argv.

    The CLI subcommand is hard-pinned to ``run`` because every flag the
    fallback wants (--comp, --skip-hooks) is a ``run`` subcommand flag,
    not a semantic check-lint-test-security alias. The semantic_command
    is only used by the parser + label fields, not by the actual argv.
    """
    return [sys.executable, "-m", "crackerjack", "run", *flag_args]


async def _dispatch(
    semantic_command: str,
    flag_args: tuple[str, ...],
    project_path: Path,
    timeout: float,
    missing: frozenset[str],
    caller: str,
    start_time: float,
    span: object | None,
    correlation_context: dict[str, str] | None,
) -> dict[str, float] | None:
    """Run the crackerjack subprocess end-to-end and return parsed metrics.

    Implementation steps kept as a separate function so ``try_crackerjack_cli``
    stays under the C901 complexity ceiling. Returns ``None`` on any
    failure path; each failure path emits a ``_finalize`` call before
    returning so observability never gets dropped.
    """
    argv = _build_argv(flag_args)

    proc, spawn_outcome = await _spawn_subprocess(argv, project_path)
    if proc is None:
        _finalize(
            spawn_outcome or "os_error",
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        return None

    stdout_bytes, stderr_bytes, wait_outcome = await _wait_for_proc(
        proc, timeout, span=span
    )
    if wait_outcome == "cancelled":
        # Emit "cancelled" before re-raise so the counter still records
        # the cancellation without swallowing it.
        _finalize(
            "cancelled",
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        raise asyncio.CancelledError
    if wait_outcome == "timeout":
        _finalize(
            "timeout",
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        return None
    if stdout_bytes is None or stderr_bytes is None:
        # Defensive: _wait_for_proc only returns Nones alongside a label
        # but guard anyway so an unexpected control flow surfaces as a
        # generic os_error instead of TypeError'ing on decode.
        _finalize(
            "os_error",
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        return None

    if proc.returncode != 0:
        # Decode stderr now so the missing_module detection can scan it.
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        outcome = _classify_proc_failure(proc.returncode, stderr_text)
        _finalize(
            outcome,
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        return None

    # Decode once at the parser boundary — CrackerjackOutputParser expects
    # ``str`` for both stdout and stderr. Empty stdout guard goes BEFORE
    # parsing so we don't classify an empty-shell-of-a-success run as
    # ``parse_error``.
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    if not stdout_text.strip():
        _finalize(
            "empty_stdout",
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        return None

    try:
        parsed_data, _memory_insights = CrackerjackOutputParser().parse_output(
            semantic_command, stdout_text, stderr_text
        )
    except Exception:
        _finalize(
            "parse_error",
            semantic_command,
            caller,
            project_path,
            missing,
            time.monotonic() - start_time,
            correlation_context,
            span=span,
        )
        return None

    candidate = _extract_sections(parsed_data, missing)
    if span is not None:
        try:
            span.set_attribute("metrics_returned", sorted(candidate.keys()))
        except Exception:
            pass
    return candidate


async def try_crackerjack_cli(
    project_dir: str | Path,
    missing_metrics: frozenset[str],
    timeout: float = 30.0,
    caller: Literal["producer_retry", "consumer_chain"] = "consumer_chain",
    correlation_context: dict[str, str] | None = None,
) -> dict[str, float] | None:
    """Return the requested metric keys via crackerjack CLI, or None on any failure.

    Args:
        project_dir: project root; the crackerjack subprocess runs with cwd=project_dir.
        missing_metrics: the scoring keys the caller still needs. frozenset to enforce
            immutability.
        timeout: subprocess timeout in seconds. Default 30.0 (distinct from the producer's 300s).
        caller: identifies which integration point invoked the helper. Used in logs and metrics
            so an operator can tell whether the timeout came from a user MCP call or a
            background quality-trends job.
        correlation_context: optional session_id / workflow_id for cross-system triage.

    Returns:
        dict with the requested metric keys (subset), or None on any failure.
        Returns {} (not None) when the subprocess succeeded but produced none of
        the requested keys.
    """
    # Normalize project_dir to a Path so the log + span attributes have a
    # stable type (avoids the str-vs-Path divergence that previously caused
    # log "extra" serialization to differ between callers).
    project_path = project_dir if isinstance(project_dir, Path) else Path(project_dir)
    start_time = time.monotonic()
    semantic_command, flag_args = _pick_invocation(missing_metrics)

    tracer = _get_tracer()
    span_cm = (
        tracer.start_as_current_span(
            "crackerjack.fallback",
            attributes={
                "command": semantic_command,
                "caller": caller,
                "missing_metrics": sorted(missing_metrics),
                "project_dir": str(project_path),
            },
        )
        if tracer is not None
        else _NoOpSpan()
    )
    span: object
    with span_cm as span:
        # Disabled check (early)
        if not feature_flags.get_feature_flags().enable_crackerjack_fallback:
            _finalize(
                "disabled",
                semantic_command,
                caller,
                project_path,
                missing_metrics,
                time.monotonic() - start_time,
                correlation_context,
                span=span,
            )
            return None

        await _acquire_fallback_lock(span=span)
        try:
            # Disabled re-check inside lock
            if not feature_flags.get_feature_flags().enable_crackerjack_fallback:
                _finalize(
                    "disabled",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None

            result = await _dispatch(
                semantic_command,
                flag_args,
                project_path,
                timeout,
                missing_metrics,
                caller,
                start_time,
                span,
                correlation_context,
            )

            if result is None:
                # _dispatch already finalized the failure path; the only
                # "result is None but not a failure" case is the success
                # path returning no metrics (handled here).
                return None
            _finalize(
                "success",
                semantic_command,
                caller,
                project_path,
                missing_metrics,
                time.monotonic() - start_time,
                correlation_context,
                span=span,
            )
            if span is not None:
                try:
                    span.set_attribute("metrics_returned", sorted(result.keys()))
                except Exception:
                    pass
            return result
        finally:
            _FALLBACK_LOCK.release()
