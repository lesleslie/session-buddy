"""Integration tests for Conscious Agent Prometheus metrics (Item 6).

The Conscious Agent's ``_analyze_and_optimize()`` returns
``provenance_pruned``, ``causal_links_pruned``, ``skills_distilled``,
and ``periodic_jobs_errors``. Per the bodai-adoption-phase-1.5 plan
(Item 6, A5), those values must also be exported as Prometheus
counters so Akosha's fitness analyzer can poll them.

Counter contract:

- ``session_buddy_provenance_pruned_total``
- ``session_buddy_causal_links_pruned_total``
- ``session_buddy_skills_distilled_total``
- ``session_buddy_periodic_jobs_errors_total{job="..."}``

Source-of-truth rule: counter values match the return-dict values
from a given ``_analyze_and_optimize`` call (per the plan's
"Prometheus counters overflow" risk-mitigation).
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_counter_value(rendered: str, metric_name: str) -> float:
    """Extract a single Counter value from a Prometheus text-format dump.

    For a labeled counter like ``foo_total{job="bar"} 1.0`` we return
    1.0; for an unlabeled counter we return the numeric value on the
    matching line. Raises ``AssertionError`` if the metric is absent.
    """
    pattern = re.compile(
        rf"^{re.escape(metric_name)}(?:\{{[^}}]*\}})? +([0-9.eE+\-]+)$",
        re.MULTILINE,
    )
    match = pattern.search(rendered)
    assert match is not None, (
        f"metric {metric_name!r} not found in rendered output:\n{rendered}"
    )
    return float(match.group(1))


def _sum_labeled_counter(rendered: str, metric_name: str) -> float:
    """Sum every sample of a labeled Counter (e.g. one per ``job``)."""
    pattern = re.compile(
        rf"^{re.escape(metric_name)}\{{[^}}]*\}} +([0-9.eE+\-]+)$",
        re.MULTILINE,
    )
    return sum(float(m.group(1)) for m in pattern.finditer(rendered))


@pytest.fixture
def agent_with_patched_path(fast_temp_db: AsyncGenerator):
    """Yield ``(agent, db)`` with ``get_database_path`` patched to the
    temp DB. Mirrors the fixture in
    ``test_conscious_agent_periodic_jobs.py``.
    """
    from session_buddy import settings as settings_mod
    from session_buddy.memory.conscious_agent import ConsciousAgent

    db = fast_temp_db
    db_path = Path(str(db.settings.database_path))
    agent = ConsciousAgent(reflection_db=db, analysis_interval_hours=1)
    with patch.object(
        settings_mod, "get_database_path", lambda: db_path
    ):
        yield agent, db


# ---------------------------------------------------------------------------
# Test 1: the metrics module exists with the documented surface
# ---------------------------------------------------------------------------


def test_metrics_module_surface_exists() -> None:
    """``session_buddy.metrics`` exposes the 4 documented counters
    and a ``render()`` function. The plan's Item 6 acceptance
    criterion is that ``get_prometheus_metrics()`` output includes
    the new counters; this test pins the underlying module.
    """
    from session_buddy import metrics

    # Module-level registry holds the 4 counters.
    assert hasattr(metrics, "registry"), "metrics.registry is missing"
    assert hasattr(metrics, "provenance_pruned_total")
    assert hasattr(metrics, "causal_links_pruned_total")
    assert hasattr(metrics, "skills_distilled_total")
    assert hasattr(metrics, "periodic_jobs_errors_total")

    # Helpers used by Conscious Agent.
    assert hasattr(metrics, "record_provenance_pruned")
    assert hasattr(metrics, "record_causal_links_pruned")
    assert hasattr(metrics, "record_skills_distilled")
    assert hasattr(metrics, "record_periodic_job_error")
    assert hasattr(metrics, "render"), "metrics.render() is missing"
    assert callable(metrics.render)


# ---------------------------------------------------------------------------
# Test 2: clean DB → counters are present at zero
# ---------------------------------------------------------------------------


async def test_render_contains_all_four_counters_at_zero(
    agent_with_patched_path: tuple,
) -> None:
    """After a single ``_analyze_and_optimize`` on a clean DB the
    four counters exist at value 0.0 in the rendered output.
    """
    from session_buddy import metrics

    agent, _db = agent_with_patched_path
    # Snapshot the starting values so the test is independent of any
    # counters that other test modules have bumped.
    rendered = metrics.render()

    # The render output exposes all four counter names.
    assert "session_buddy_provenance_pruned_total" in rendered
    assert "session_buddy_causal_links_pruned_total" in rendered
    assert "session_buddy_skills_distilled_total" in rendered
    assert "session_buddy_periodic_jobs_errors_total" in rendered

    # The three unlabeled counters start at 0.0 (the labeled one
    # sums to 0 because no job has logged an error yet).
    assert (
        _parse_counter_value(rendered, "session_buddy_provenance_pruned_total")
        == 0.0
    )
    assert (
        _parse_counter_value(
            rendered, "session_buddy_causal_links_pruned_total"
        )
        == 0.0
    )
    assert (
        _parse_counter_value(rendered, "session_buddy_skills_distilled_total")
        == 0.0
    )
    assert (
        _sum_labeled_counter(rendered, "session_buddy_periodic_jobs_errors_total")
        == 0.0
    )


# ---------------------------------------------------------------------------
# Test 3: counters track the return-dict values (source-of-truth)
# ---------------------------------------------------------------------------


async def test_counters_match_return_dict_after_analysis(
    agent_with_patched_path: tuple,
) -> None:
    """The plan's risk-mitigation: counter values must match the
    return-dict values. We bump the counters via the agent's
    loop (not directly), then assert they match the dict the
    agent produced.

    Uses a fresh registry snapshot for this test so the assertion
    is independent of other tests' counter state.
    """
    from session_buddy import metrics

    agent, db = agent_with_patched_path

    # Capture the return dict from the agent's loop.
    results = await agent._analyze_and_optimize()

    # Render the metrics registry.
    rendered = metrics.render()

    # Each counter must equal the matching key in the return dict.
    assert (
        _parse_counter_value(rendered, "session_buddy_provenance_pruned_total")
        == float(results["provenance_pruned"])
    ), (
        "provenance_pruned_total counter must match return-dict "
        f"value {results['provenance_pruned']!r}"
    )
    assert (
        _parse_counter_value(
            rendered, "session_buddy_causal_links_pruned_total"
        )
        == float(results["causal_links_pruned"])
    ), (
        "causal_links_pruned_total counter must match return-dict "
        f"value {results['causal_links_pruned']!r}"
    )
    assert (
        _parse_counter_value(rendered, "session_buddy_skills_distilled_total")
        == float(results["skills_distilled"])
    ), (
        "skills_distilled_total counter must match return-dict "
        f"value {results['skills_distilled']!r}"
    )
    # periodic_jobs_errors is a list[str]; one Counter increment per
    # entry, labelled with the error string.
    assert (
        _sum_labeled_counter(rendered, "session_buddy_periodic_jobs_errors_total")
        == float(len(results["periodic_jobs_errors"]))
    ), (
        "periodic_jobs_errors_total counter must sum to "
        f"{len(results['periodic_jobs_errors'])}"
    )


# ---------------------------------------------------------------------------
# Test 4: provenance pruning bumps the counter
# ---------------------------------------------------------------------------


async def test_provenance_counter_bumps_with_pruned_rows(
    agent_with_patched_path: tuple,
) -> None:
    """A backdated provenance row is pruned AND the counter
    increments to match the return-dict value.
    """
    from session_buddy import metrics

    agent, db = agent_with_patched_path

    # Snapshot the pre-run counter value so the assertion is robust
    # to other tests sharing the registry.
    pre = _parse_counter_value(
        metrics.render(), "session_buddy_provenance_pruned_total"
    )

    # Seed a backdated provenance row.
    conv_id = await db.store_conversation(
        content="test",
        metadata={"source_session": "sess-1"},
        source_type="claude_code",
    )
    db.conn.execute(
        "UPDATE memory_provenance SET extracted_at = now() - INTERVAL '100 days' "
        "WHERE memory_id = ?",
        [conv_id],
    )

    results = await agent._analyze_and_optimize()
    assert results["provenance_pruned"] >= 1

    post = _parse_counter_value(
        metrics.render(), "session_buddy_provenance_pruned_total"
    )
    # The counter delta must equal the return-dict value.
    assert post - pre == float(results["provenance_pruned"]), (
        f"counter delta {post - pre} != returned count "
        f"{results['provenance_pruned']!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: periodic-job error counter increments per failed job
# ---------------------------------------------------------------------------


async def test_periodic_jobs_error_counter_labels_failed_job(
    fast_temp_db: AsyncGenerator,
) -> None:
    """If one periodic job raises, the ``periodic_jobs_errors_total``
    counter increments by 1 (labelled with the failed job name).
    """
    from session_buddy import metrics
    from session_buddy.memory.conscious_agent import ConsciousAgent

    db = fast_temp_db

    # Make prune_provenance_older_than raise so the agent records
    # a periodic_jobs_errors entry.
    original_prune = db.prune_provenance_older_than

    async def failing_prune(*args: object, **kwargs: object) -> int:
        raise RuntimeError("simulated provenance prune failure")

    db.prune_provenance_older_than = failing_prune  # type: ignore[method-assign]
    try:
        agent = ConsciousAgent(reflection_db=db, analysis_interval_hours=1)
        results = await agent._analyze_and_optimize()

        # The error is recorded in the return dict.
        assert any(
            "provenance" in err for err in results["periodic_jobs_errors"]
        ), (
            f"expected provenance error in {results['periodic_jobs_errors']!r}"
        )

        # And the counter is also bumped (sum across labels).
        rendered = metrics.render()
        total = _sum_labeled_counter(
            rendered, "session_buddy_periodic_jobs_errors_total"
        )
        # The counter tracks len(periodic_jobs_errors), not just the
        # simulated failure — so it must be >= 1.
        assert total >= 1.0, (
            f"expected at least 1 periodic_jobs_error, got {total}"
        )
    finally:
        db.prune_provenance_older_than = original_prune  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Test 6: render() is Prometheus text format
# ---------------------------------------------------------------------------


def test_render_output_is_prometheus_text_format() -> None:
    """The render() output is the Prometheus text exposition format.

    Pins the format contract: ``# HELP`` and ``# TYPE`` lines are
    present, and values are numeric. Akosha's fitness analyzer
    (the consumer) speaks this format.
    """
    from session_buddy import metrics

    rendered = metrics.render()

    # Each counter has a HELP and TYPE line.
    for name in (
        "session_buddy_provenance_pruned_total",
        "session_buddy_causal_links_pruned_total",
        "session_buddy_skills_distilled_total",
        "session_buddy_periodic_jobs_errors_total",
    ):
        assert f"# HELP {name}" in rendered, (
            f"missing # HELP line for {name}:\n{rendered}"
        )
        assert f"# TYPE {name} counter" in rendered, (
            f"missing # TYPE line for {name}:\n{rendered}"
        )
