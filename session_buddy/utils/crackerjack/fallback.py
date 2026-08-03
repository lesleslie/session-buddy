"""CLI fallback for missing quality-scoring metrics.

Invokes the Crackerjack CLI on-demand when the consumer chain has no
historical metrics or the producer subprocess failed. Returns the
requested metric keys (subset of parsed_data), or None on any failure.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Literal

from session_buddy.config import feature_flags

logger = logging.getLogger(__name__)


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
    # Disabled check (early)
    if not feature_flags.get_feature_flags().enable_crackerjack_fallback:
        # TODO: log DEBUG with outcome=disabled and emit counter (Task 7)
        return None

    # OTel span start (Task 7 fills in the span attributes; this scaffold is
    # intentionally minimal so the test at Task 7 can verify the span
    # wrapping works end-to-end)
    # TODO: with tracer.start_as_current_span("crackerjack.fallback", attributes={...}):

    # Lock
    async with _FALLBACK_LOCK:
        # Disabled re-check inside lock
        if not feature_flags.get_feature_flags().enable_crackerjack_fallback:
            # TODO: log DEBUG with outcome=disabled and emit counter (Task 7)
            return None

        # Pick the smallest crackerjack invocation that fills the gaps
        semantic_command, flag_args = _pick_invocation(missing_metrics)
        del semantic_command  # Used by Task 5's output parser.
        argv = [sys.executable, "-m", "crackerjack", "run", *flag_args]

        # Spawn subprocess (catch OS-level failures)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            # TODO: log ERROR + counter missing_executable (Task 7)
            return None
        except PermissionError:
            # TODO: log WARNING + counter permission_error (Task 7)
            return None
        except OSError:
            # TODO: log WARNING + counter os_error (Task 7)
            return None

        # Wait with timeout. Split handlers: TimeoutError -> None after
        # cleanup; CancelledError -> finalize observability THEN re-raise
        # after cleanup.
        try:
            _stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            # TODO: log WARNING + counter timeout (Task 7)
            return None
        except asyncio.CancelledError:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            # TODO: log WARNING + counter cancelled (Task 7)
            raise

        # Check exit code
        if proc.returncode != 0:
            # TODO: log WARNING + counter nonzero_exit (Task 7)
            return None

        # TODO: parse + extract (Task 5)
        return None
