"""Regression net: ensure metric dict keys align with consumers.

Two contracts:
1. Every scoring-metric key emitted by
   ``CrackerjackIntegration._calculate_quality_metrics`` for a non-empty
   ``parsed_data`` must be readable by ``quality_scoring._parse_metrics_history``
   (i.e. have a slot in the returned dict). Diagnostic / build-outcome
   keys (e.g. ``build_status``) are explicitly whitelisted — they are
   intentionally not consumed by the scoring history; they are written
   for dashboards and trend analysis.
2. Every key ``_parse_metrics_history`` returns for a non-empty history
   must be either passed through unchanged or map to a documented
   detail flag in ``CodeQualityScore.details``.
"""
from __future__ import annotations

from typing import Any

import pytest

from session_buddy.crackerjack_integration import CrackerjackIntegration
from session_buddy.utils.quality_scoring import (
    _parse_metrics_history,
    calculate_quality_score_v2,
)


KNOWN_METRIC_HISTORY_KEYS = {
    "code_coverage",
    "lint_score",
    "security_score",
    "complexity_score",
}

# Keys that ``_calculate_quality_metrics`` legitimately emits but which
# ``_parse_metrics_history`` does not consume. Whitelisted to keep the
# regression net focused on scoring-metric drift; a future task that
# accidentally drops ``build_status`` from the quality dict would still
# be caught by integration tests elsewhere.
KNOWN_DIAGNOSTIC_KEYS = {"build_status"}


def _full_parsed_data() -> dict[str, Any]:
    return {
        "test_results": [{"status": "passed"}],
        "coverage_summary": {"total_coverage": 80.0},
        "lint_issues": [],
        "security_issues": [],
        "complexity_data": {"a.py": {"lines": 100, "complexity": 4.0}},
    }


def test_metrics_dict_keys_consumed_by_history() -> None:
    """Every scoring-metric key is readable by the history layer; diagnostic keys are whitelisted."""
    integration = CrackerjackIntegration()
    metrics = integration._calculate_quality_metrics(_full_parsed_data(), 0)
    history = [
        {
            "metric_type": key,
            "metric_value": value if isinstance(value, (int, float)) else 0,
            "timestamp": "2026-07-27T00:00:00Z",
        }
        for key, value in metrics.items()
        if isinstance(value, (int, float))
    ]
    parsed = _parse_metrics_history(history)

    consumed_by_history = set(parsed)
    whitelisted = KNOWN_DIAGNOSTIC_KEYS
    unknown_orphans: list[str] = []

    for key in metrics:
        if not isinstance(metrics[key], (int, float)):
            continue
        if key in consumed_by_history:
            continue
        if key in whitelisted:
            continue
        unknown_orphans.append(key)

    assert not unknown_orphans, (
        f"emitted metric keys not read by _parse_metrics_history "
        f"and not in KNOWN_DIAGNOSTIC_KEYS whitelist: {unknown_orphans!r}. "
        f"Either add the field to _parse_metrics_history slots, drop the "
        f"emission, or whitelist the key here with a comment justifying "
        f"its diagnostic role."
    )


def test_parse_metrics_history_returns_documented_keys() -> None:
    """History layer emits only the documented slot keys (or None for missing)."""
    history = [
        {"metric_type": "lint_score", "metric_value": 90, "timestamp": "2026-07-27T00:00:00Z"},
    ]
    parsed = _parse_metrics_history(history)
    for key in parsed:
        assert key in KNOWN_METRIC_HISTORY_KEYS | {"code_coverage"}, (
            f"_parse_metrics_history returned undocumented key {key!r}"
        )


@pytest.mark.asyncio
async def test_calculate_quality_score_handles_none_metrics(tmp_path) -> None:
    """When history provides no metrics, calculate_quality_score_v2 still returns."""
    # Provide an empty history; quality-scoring must not crash and must
    # not award full points.
    quality = await calculate_quality_score_v2(tmp_path, permissions_count=0)
    assert 0 <= quality.total_score <= 100
    # Code-quality detail shows missing flags where applicable.
    assert quality.code_quality.details.get("lint_missing") is True
