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
from typing import TYPE_CHECKING, Literal

from session_buddy.config import feature_flags

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer


logger = logging.getLogger(__name__)


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

        # Placeholder for the rest of the pipeline (filled in Task 4+)
        return None
