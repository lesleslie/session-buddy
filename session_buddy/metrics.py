"""Prometheus metrics for Session-Buddy cross-component observability.

This module owns the Prometheus counters that Session-Buddy exposes
to the rest of the Bodai ecosystem. It is intentionally separate
from ``session_buddy.mcp.metrics`` (which tracks session lifecycle
metrics for the MCP server itself) and from
``session_buddy.mcp.tools.monitoring.prometheus_metrics_tools`` (the
MCP-tool wrapper).

The counters here surface Conscious Agent activity (Phase 1.5
follow-up — Item 6 of ``bodai-adoption-phase-1.5``):

- ``session_buddy_provenance_pruned_total`` — provenance rows
  pruned by the agent's periodic job
- ``session_buddy_causal_links_pruned_total`` — causal links
  pruned by the agent's periodic job
- ``session_buddy_skills_distilled_total`` — skills produced by
  the agent's distillation job
- ``session_buddy_periodic_jobs_errors_total{job="..."}`` —
  one increment per failed periodic job, labelled with the job
  name (e.g. ``provenance_prune``)

Akosha's fitness analyzer consumes these counters; they are
bumped from ``_analyze_and_optimize()`` after each run.

Source-of-truth rule (per the plan's risk-mitigation): counter
values match the return-dict values from a given
``_analyze_and_optimize`` call.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, CollectorRegistry, Counter, generate_latest


# Module-level registry. ``prometheus_client.REGISTRY`` is the
# default global registry, but we keep a reference here so tests
# (and any future custom registry callers) have a single import
# target. Helpers below use ``REGISTRY`` directly so the counters
# appear in the default ``generate_latest()`` output that the MCP
# ``get_prometheus_metrics`` tool returns.
registry: CollectorRegistry = REGISTRY


# Counter definitions. Names use the ``session_buddy_`` prefix to
# match the convention in ``session_buddy.mcp.metrics`` and to
# keep the metrics namespace unambiguous when Prometheus scrapes
# multiple components.
provenance_pruned_total: Counter = Counter(
    "session_buddy_provenance_pruned_total",
    "Number of provenance rows pruned by the Conscious Agent's periodic job.",
)

causal_links_pruned_total: Counter = Counter(
    "session_buddy_causal_links_pruned_total",
    "Number of causal links pruned by the Conscious Agent's periodic job.",
)

skills_distilled_total: Counter = Counter(
    "session_buddy_skills_distilled_total",
    "Number of skills distilled by the Conscious Agent's periodic job.",
)

periodic_jobs_errors_total: Counter = Counter(
    "session_buddy_periodic_jobs_errors_total",
    "Number of periodic-job errors raised by the Conscious Agent.",
    labelnames=("job",),
)


# ---------------------------------------------------------------------------
# Helpers — bump the counters from the Conscious Agent's return dict
# ---------------------------------------------------------------------------


def record_provenance_pruned(count: int) -> None:
    """Increment the provenance-pruned counter by ``count``."""
    if count > 0:
        provenance_pruned_total.inc(count)


def record_causal_links_pruned(count: int) -> None:
    """Increment the causal-links-pruned counter by ``count``."""
    if count > 0:
        causal_links_pruned_total.inc(count)


def record_skills_distilled(count: int) -> None:
    """Increment the skills-distilled counter by ``count``."""
    if count > 0:
        skills_distilled_total.inc(count)


def record_periodic_job_error(job: str) -> None:
    """Increment the periodic-jobs-error counter for ``job``.

    The ``job`` label is the short name of the failed job (e.g.
    ``provenance_prune``). Akosha can group by ``job`` to find
    which periodic job is the failure hotspot.
    """
    if not job:
        job = "unknown"
    periodic_jobs_errors_total.labels(job=job).inc()


def record_periodic_job_errors(errors: list[str]) -> None:
    """Increment the periodic-jobs-error counter for each error.

    Each ``errors`` entry has the form ``"<job_name>: <repr>"``
    (the same format Conscious Agent's ``_run_periodic_jobs``
    uses). We split off the leading ``"<job_name>:"`` token and
    use it as the ``job`` label so the counter is dimensional.
    Errors that don't match the expected prefix are recorded
    under ``"unknown"`` so the count still matches
    ``len(errors)``.
    """
    for entry in errors:
        job_label = "unknown"
        if isinstance(entry, str) and ":" in entry:
            job_label = entry.split(":", 1)[0].strip() or "unknown"
        record_periodic_job_error(job_label)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render() -> str:
    """Render the Session-Buddy metrics in Prometheus text format.

    Returns:
        The Prometheus exposition text format dump (the same
        output ``prometheus_client.generate_latest(REGISTRY)``
        produces). The MCP ``get_prometheus_metrics`` tool embeds
        this in its response.
    """
    return generate_latest(REGISTRY).decode("utf-8")


__all__ = [
    "registry",
    "provenance_pruned_total",
    "causal_links_pruned_total",
    "skills_distilled_total",
    "periodic_jobs_errors_total",
    "record_provenance_pruned",
    "record_causal_links_pruned",
    "record_skills_distilled",
    "record_periodic_job_error",
    "record_periodic_job_errors",
    "render",
]
