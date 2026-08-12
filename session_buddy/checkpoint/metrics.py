"""Operator-visible in-process metrics for checkpoint failures.

Exposes the spec-required `checkpoint_failures_total{reason="..."}` counter
via a future Prometheus export hook. Today: dict counter, observable in tests.
"""

from __future__ import annotations

from collections import defaultdict


class CheckpointMetrics:
    def __init__(self) -> None:
        self.failures: dict[str, int] = defaultdict(int)

    def inc_failure(self, reason: str) -> None:
        self.failures[reason] += 1
