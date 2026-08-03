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
            if outcome not in ("success", "disabled"):
                # Lazy import to avoid a hard dep when OTel missing
                from opentelemetry.trace import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR, f"{outcome}: {caller}"))
        except Exception:
            pass


# Crackerjack v0.47+ uses 'run' subcommand with flag combinations. The
# semantic command name (lint, security, check, test) is what the
# parser's _get_applicable_parsers keys on. Mapping recorded in
# docs/superpowers/plans/2026-07-27-cli-flag-mapping.md (Task 0).
_METRIC_TO_FLAG: dict[str, tuple[str, tuple[str, ...]]] = {
    "code_coverage": ("check", ("--comp", "--skip-hooks")),
    "lint_score": ("check", ("--comp", "--skip-hooks")),
    "security_score": ("check", ("--comp", "--skip-hooks")),
    # complexity_score intentionally absent. _pick_invocation always routes
    # to the general check invocation before consulting this table.
}


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
    # Pick the semantic command up-front so the OTel span's `command`
    # attribute is populated even on the early disabled-return path.
    semantic_command, _flag_args = _pick_invocation(missing_metrics)

    # OTel span (Task 7). Use a real span when OTel is configured, fall
    # back to a no-op context manager so the `with` block works the same
    # way whether or not OTel is wired up.
    tracer = _get_tracer()
    span_cm = (
        tracer.start_as_current_span(
            "crackerjack.fallback",
            attributes={
                "command": semantic_command,
                "caller": caller,
                "missing_metrics": sorted(missing_metrics),
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

        # Lock
        async with _FALLBACK_LOCK:
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

            # Pick the smallest crackerjack invocation that fills the gaps
            semantic_command, flag_args = _pick_invocation(missing_metrics)
            argv = [sys.executable, "-m", "crackerjack", "run", *flag_args]

            # Spawn subprocess (catch OS-level failures)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(project_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                _finalize(
                    "missing_executable",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None
            except PermissionError:
                _finalize(
                    "permission_error",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None
            except OSError:
                _finalize(
                    "os_error",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None

            # Wait with timeout. Split handlers: TimeoutError -> None after
            # cleanup; CancelledError -> finalize observability THEN re-raise
            # after cleanup.
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                _finalize(
                    "timeout",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None
            except asyncio.CancelledError:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                # Observability v2 review C2: emit counter BEFORE raise so
                # the cancelled invocation shows up in metrics even though
                # the exception propagates to the caller.
                _finalize(
                    "cancelled",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                raise

            # Check exit code
            if proc.returncode != 0:
                _finalize(
                    "nonzero_exit",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None

            # Empty-stdout guard BEFORE parsing (a parse exception on empty
            # bytes would otherwise classify this as parse_error, not
            # empty_stdout)
            if not stdout:
                _finalize(
                    "empty_stdout",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None

            # Parse output (catch any exception from the parser). Note:
            # parse_output returns (parsed_data, memory_insights) — the
            # parsed_data dict is the first element; insights is the
            # memory-side artifact and does not feed back into the metric
            # filling. Verified in Task 0 (commit 54df5a4a).
            try:
                parsed_data, _memory_insights = CrackerjackOutputParser().parse_output(
                    semantic_command, stdout, stderr
                )
            except Exception:
                _finalize(
                    "parse_error",
                    semantic_command,
                    caller,
                    project_path,
                    missing_metrics,
                    time.monotonic() - start_time,
                    correlation_context,
                    span=span,
                )
                return None

            # Section keys for each scoring metric. An empty section means
            # the metric was not measured; do NOT synthesize a 100.
            SECTION_FOR_KEY = {
                "code_coverage": "coverage_summary",
                "lint_score": "lint_issues",
                "security_score": "security_issues",
                "complexity_score": "complexity_data",
            }
            # _calculate_*_metrics are @staticmethods on CrackerjackIntegration
            # (Task 2). Call them via the class — instantiating
            # CrackerjackIntegration() would write to SQLite on disk.
            def _get_crackerjack_integration_class():
                """Lazy import to avoid a hard dependency at module import time."""
                from session_buddy.crackerjack_integration import CrackerjackIntegration
                return CrackerjackIntegration

            cls = _get_crackerjack_integration_class()
            candidate: dict[str, float] = {}
            for key in missing_metrics:
                section_key = SECTION_FOR_KEY.get(key)
                if section_key is None:
                    continue
                section = parsed_data.get(section_key)
                # An empty section (None, [], {}, etc.) means the metric
                # was NOT measured — skip the candidate to avoid the
                # synthesize-100s antipattern.
                if not section:
                    continue
                if key == "code_coverage":
                    # _calculate_coverage_metrics expects parsed_data (with
                    # a `coverage_summary` key inside), unlike the other three
                    # helpers which take the section directly.
                    candidate.update(cls._calculate_coverage_metrics(parsed_data))
                elif key == "lint_score":
                    candidate.update(cls._calculate_lint_metrics(section))
                elif key == "security_score":
                    candidate.update(cls._calculate_security_metrics(section))
                elif key == "complexity_score":
                    candidate.update(cls._calculate_complexity_metrics(section))

            # Only return the keys the caller actually asked for.
            result = {k: v for k, v in candidate.items() if k in missing_metrics}
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
            return result
