"""Tests for session_buddy.realtime.metrics_exporter.

Targets the PrometheusExporter and the module-level metrics. Avoids
hitting real network endpoints by allocating an ephemeral port for the
brief lifetime of the WSGI server and tearing it down between tests.

The module's metric objects are registered against the global
``prometheus_client.REGISTRY`` at import time, so we use
``prometheus_client.values.MultiProcessValue``-style behavior — instead
we reset counter values via the public ``._value._value``/``._metrics``
attributes only when the test depends on it; the bulk of the assertions
compare current sample values via the public ``collect()`` API.
"""

from __future__ import annotations

import socket
import uuid
from typing import Iterator

import pytest
from prometheus_client import REGISTRY

from session_buddy.realtime import metrics_exporter as exporter_mod
from session_buddy.realtime.metrics_exporter import (
    PrometheusExporter,
    create_exporter,
)


# ============================================================================
# Helpers
# ============================================================================


def _free_port() -> int:
    """Allocate an ephemeral free port by binding then closing."""
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _sample_value(metric, **labels: str) -> float:
    """Read the current value of a labelled metric sample.

    Reads from the parent metric's collect() output because calling
    ``.collect()`` on a labelled child strips the labels from the
    returned samples, making it impossible to match a label set. The
    sample name is either the metric's own ``_name`` (Gauge) or
    ``<name>_total`` (Counter); ``_created`` samples carry timestamps
    and must be ignored.
    """
    metric_name = metric._name
    target_names = {metric_name, f"{metric_name}_total"}
    for sample in list(metric.collect())[0].samples:
        if sample.name in target_names and all(
            sample.labels.get(k) == v for k, v in labels.items()
        ):
            return sample.value
    return 0.0


def _histogram_count(metric, **labels: str) -> float:
    """Return the ``_count`` for a labelled histogram child.

    Reads from the parent metric's collect() output and matches the
    requested label set because the child's collect() strips labels.
    """
    metric_name = metric._name
    for sample in list(metric.collect())[0].samples:
        if sample.name == f"{metric_name}_count" and all(
            sample.labels.get(k) == v for k, v in labels.items()
        ):
            return sample.value
    return 0.0


@pytest.fixture
def fresh_exporter() -> Iterator[PrometheusExporter]:
    """Provide a PrometheusExporter that never starts an HTTP server."""
    yield PrometheusExporter(port=_free_port())


@pytest.fixture
def started_exporter() -> Iterator[PrometheusExporter]:
    """Start an exporter on a free port, tear it down on teardown."""
    server, thread, port = None, None, None
    exporter = PrometheusExporter(port=_free_port())
    try:
        exporter.start()
        yield exporter
    finally:
        # The WSGI server is a daemon thread; closing the exporter object
        # has no effect, but we ensure the running flag is reset.
        exporter._running = False


@pytest.fixture
def unique() -> Iterator[str]:
    """Yield a unique prefix so label values don't collide across tests.

    The module-level metric objects are singletons, so any test that
    records ``skill_name="x"`` will accumulate against earlier tests
    that used the same label. Prefixing every test's labels with a
    fresh UUID eliminates that cross-test pollution.
    """
    yield f"t{uuid.uuid4().hex[:8]}"


# ============================================================================
# Construction & validation
# ============================================================================


@pytest.mark.unit
def test_init_with_default_port() -> None:
    exporter = PrometheusExporter()

    assert exporter.port == 9090
    assert exporter.is_running() is False


@pytest.mark.unit
def test_init_with_custom_port() -> None:
    port = _free_port()
    exporter = PrometheusExporter(port=port)

    assert exporter.port == port
    assert exporter._running is False


@pytest.mark.unit
@pytest.mark.parametrize("bad_port", [0, -1, 65536, 100000, -1000])
def test_init_rejects_invalid_ports(bad_port: int) -> None:
    with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
        PrometheusExporter(port=bad_port)


@pytest.mark.unit
@pytest.mark.parametrize("edge_port", [1, 65535])
def test_init_accepts_edge_ports(edge_port: int) -> None:
    exporter = PrometheusExporter(port=edge_port)
    assert exporter.port == edge_port


# ============================================================================
# start() / is_running()
# ============================================================================


@pytest.mark.unit
def test_start_sets_running_flag(started_exporter: PrometheusExporter) -> None:
    assert started_exporter.is_running() is True


@pytest.mark.unit
def test_start_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling start() a second time should be a no-op and not re-bind."""
    port = _free_port()
    exporter = PrometheusExporter(port=port)
    call_count = {"n": 0}

    def fake_start_http_server(p: int) -> None:
        call_count["n"] += 1

    monkeypatch.setattr(exporter_mod, "start_http_server", fake_start_http_server)

    exporter.start()
    exporter.start()
    exporter.start()

    assert call_count["n"] == 1
    assert exporter.is_running() is True


@pytest.mark.unit
def test_start_propagates_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_port: int) -> None:
        msg = "address in use"
        raise OSError(msg)

    monkeypatch.setattr(exporter_mod, "start_http_server", boom)

    exporter = PrometheusExporter(port=_free_port())

    with pytest.raises(OSError, match="address in use"):
        exporter.start()

    assert exporter.is_running() is False


@pytest.mark.unit
def test_start_does_not_set_running_when_bind_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_port: int) -> None:
        msg = "bind failed"
        raise OSError(msg)

    monkeypatch.setattr(exporter_mod, "start_http_server", boom)
    exporter = PrometheusExporter(port=_free_port())

    with pytest.raises(OSError):
        exporter.start()
    assert exporter._running is False
    assert exporter.is_running() is False


# ============================================================================
# record_invocation
# ============================================================================


@pytest.mark.unit
def test_record_invocation_increments_counter(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(
        skill_name=f"{unique}-pytest-run",
        workflow_phase="execution",
        completed=True,
        duration_seconds=12.5,
    )

    value = _sample_value(
        exporter_mod.skill_invocations_total,
        skill_name=f"{unique}-pytest-run",
        workflow_phase="execution",
        completed="true",
    )
    assert value == 1.0


@pytest.mark.unit
def test_record_invocation_normalises_none_phase(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(
        skill_name=f"{unique}-lint-check",
        workflow_phase=None,
        completed=False,
        duration_seconds=None,
    )

    value = _sample_value(
        exporter_mod.skill_invocations_total,
        skill_name=f"{unique}-lint-check",
        workflow_phase="unknown",
        completed="false",
    )
    assert value == 1.0


@pytest.mark.unit
def test_record_invocation_without_duration_skips_histogram(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(
        skill_name=f"{unique}-noop",
        workflow_phase="setup",
        completed=True,
        duration_seconds=None,
    )

    # Histogram should not have a child for these labels (we never observe).
    # _histogram_count is best-effort; the contract is: histogram count is 0.
    assert (
        _histogram_count(
            exporter_mod.skill_duration_seconds,
            skill_name=f"{unique}-noop",
            workflow_phase="setup",
        )
        == 0.0
    )


@pytest.mark.unit
def test_record_invocation_observes_histogram(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(
        skill_name=f"{unique}-pytest-run",
        workflow_phase="execution",
        completed=True,
        duration_seconds=42.0,
    )
    fresh_exporter.record_invocation(
        skill_name=f"{unique}-pytest-run",
        workflow_phase="execution",
        completed=False,
        duration_seconds=99.0,
    )

    count = _histogram_count(
        exporter_mod.skill_duration_seconds,
        skill_name=f"{unique}-pytest-run",
        workflow_phase="execution",
    )
    assert count == 2.0


@pytest.mark.unit
def test_record_invocation_distinguishes_completed_flag(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(
        f"{unique}-x", "execution", completed=True, duration_seconds=1.0
    )
    fresh_exporter.record_invocation(
        f"{unique}-x", "execution", completed=True, duration_seconds=1.0
    )
    fresh_exporter.record_invocation(
        f"{unique}-x", "execution", completed=False, duration_seconds=1.0
    )

    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=f"{unique}-x",
            workflow_phase="execution",
            completed="true",
        )
        == 2.0
    )
    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=f"{unique}-x",
            workflow_phase="execution",
            completed="false",
        )
        == 1.0
    )


@pytest.mark.unit
def test_record_invocation_isolates_per_skill(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(f"{unique}-a", "p", True, 1.0)
    fresh_exporter.record_invocation(f"{unique}-b", "p", True, 1.0)
    fresh_exporter.record_invocation(f"{unique}-b", "p", True, 1.0)

    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=f"{unique}-a",
            workflow_phase="p",
            completed="true",
        )
        == 1.0
    )
    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=f"{unique}-b",
            workflow_phase="p",
            completed="true",
        )
        == 2.0
    )


# ============================================================================
# update_completion_rate
# ============================================================================


@pytest.mark.unit
def test_update_completion_rate_sets_gauge(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.update_completion_rate(f"{unique}-pytest-run", 0.5)

    value = _sample_value(
        exporter_mod.skill_completion_rate, skill_name=f"{unique}-pytest-run"
    )
    assert value == 0.5


@pytest.mark.unit
@pytest.mark.parametrize("rate", [0.0, 1.0])
def test_update_completion_rate_accepts_edges(
    fresh_exporter: PrometheusExporter, unique: str, rate: float
) -> None:
    fresh_exporter.update_completion_rate(f"{unique}-x", rate)
    assert (
        _sample_value(exporter_mod.skill_completion_rate, skill_name=f"{unique}-x")
        == rate
    )


@pytest.mark.unit
@pytest.mark.parametrize("bad_rate", [-0.01, -1.0, 1.01, 2.0, 100.0])
def test_update_completion_rate_rejects_out_of_range(
    fresh_exporter: PrometheusExporter, unique: str, bad_rate: float
) -> None:
    with pytest.raises(ValueError, match="Completion rate must be between 0 and 1"):
        fresh_exporter.update_completion_rate(f"{unique}-x", bad_rate)


@pytest.mark.unit
def test_update_completion_rate_overwrites(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.update_completion_rate(f"{unique}-x", 0.1)
    fresh_exporter.update_completion_rate(f"{unique}-x", 0.9)

    assert (
        _sample_value(exporter_mod.skill_completion_rate, skill_name=f"{unique}-x")
        == 0.9
    )


# ============================================================================
# record_anomaly
# ============================================================================


@pytest.mark.unit
def test_record_anomaly_increments_counter(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_anomaly("drop", f"{unique}-pytest-run")
    fresh_exporter.record_anomaly("drop", f"{unique}-pytest-run")
    fresh_exporter.record_anomaly("spike", f"{unique}-ruff-check")

    assert (
        _sample_value(
            exporter_mod.anomalies_detected_total,
            anomaly_type="drop",
            skill_name=f"{unique}-pytest-run",
        )
        == 2.0
    )
    assert (
        _sample_value(
            exporter_mod.anomalies_detected_total,
            anomaly_type="spike",
            skill_name=f"{unique}-ruff-check",
        )
        == 1.0
    )


# ============================================================================
# update_active_sessions
# ============================================================================


@pytest.mark.unit
def test_update_active_sessions_sets_gauge(
    fresh_exporter: PrometheusExporter,
) -> None:
    fresh_exporter.update_active_sessions(7)
    # active_sessions_total is unlabelled — read its single sample value.
    samples = list(exporter_mod.active_sessions_total.collect())[0].samples
    total = next(
        s.value for s in samples if s.name == "active_sessions_total"
    )
    assert total == 7


@pytest.mark.unit
@pytest.mark.parametrize("count", [0, 1, 100, 10**9])
def test_update_active_sessions_accepts_valid(
    fresh_exporter: PrometheusExporter, count: int
) -> None:
    fresh_exporter.update_active_sessions(count)
    samples = list(exporter_mod.active_sessions_total.collect())[0].samples
    total = next(
        s.value for s in samples if s.name == "active_sessions_total"
    )
    assert total == count


@pytest.mark.unit
@pytest.mark.parametrize("count", [-1, -10, -10**6])
def test_update_active_sessions_rejects_negative(
    fresh_exporter: PrometheusExporter, count: int
) -> None:
    with pytest.raises(ValueError, match="Session count cannot be negative"):
        fresh_exporter.update_active_sessions(count)


@pytest.mark.unit
def test_update_active_sessions_overwrites(
    fresh_exporter: PrometheusExporter,
) -> None:
    fresh_exporter.update_active_sessions(2)
    fresh_exporter.update_active_sessions(5)

    samples = list(exporter_mod.active_sessions_total.collect())[0].samples
    total = next(
        s.value for s in samples if s.name == "active_sessions_total"
    )
    assert total == 5


# ============================================================================
# create_exporter convenience
# ============================================================================


@pytest.mark.unit
def test_create_exporter_returns_started_instance() -> None:
    port = _free_port()
    exporter = create_exporter(port=port)

    try:
        assert isinstance(exporter, PrometheusExporter)
        assert exporter.port == port
        assert exporter.is_running() is True
    finally:
        exporter._running = False


@pytest.mark.unit
def test_create_exporter_uses_default_port() -> None:
    exporter = create_exporter()
    try:
        assert exporter.port == 9090
        assert exporter.is_running() is True
    finally:
        exporter._running = False


# ============================================================================
# Module-level metric identity
# ============================================================================


@pytest.mark.unit
def test_module_metrics_are_registered_in_global_registry() -> None:
    """The module-level metrics must appear in the default REGISTRY."""
    collector_names = set(REGISTRY._collector_to_names.keys())  # type: ignore[attr-defined]
    expected_collectors = {
        exporter_mod.skill_invocations_total,
        exporter_mod.skill_duration_seconds,
        exporter_mod.skill_completion_rate,
        exporter_mod.active_sessions_total,
        exporter_mod.anomalies_detected_total,
    }
    assert expected_collectors.issubset(collector_names)


# ============================================================================
# Concurrent updates
# ============================================================================


@pytest.mark.unit
def test_record_invocation_is_thread_safe(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    import threading

    n_threads = 8
    per_thread = 25
    errors: list[BaseException] = []
    skill_name = f"{unique}-thread-test"

    def worker() -> None:
        try:
            for _ in range(per_thread):
                fresh_exporter.record_invocation(
                    skill_name, "execution", True, 0.5
                )
        except BaseException as exc:  # pragma: no cover - bubble up to list
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=skill_name,
            workflow_phase="execution",
            completed="true",
        )
        == float(n_threads * per_thread)
    )


# ============================================================================
# End-to-end workflow
# ============================================================================


@pytest.mark.unit
def test_full_workflow_updates_all_metrics(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    """Drive every public method once and confirm all metrics respond."""
    skill = f"{unique}-pytest"
    fresh_exporter.record_invocation(skill, "execution", True, 10.0)
    fresh_exporter.record_invocation(skill, "execution", False, 30.0)
    fresh_exporter.update_completion_rate(skill, 0.5)
    fresh_exporter.record_anomaly("drop", skill)
    fresh_exporter.update_active_sessions(3)

    # Counter has 2 observations (one true, one false).
    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=skill,
            workflow_phase="execution",
            completed="true",
        )
        == 1.0
    )
    assert (
        _sample_value(
            exporter_mod.skill_invocations_total,
            skill_name=skill,
            workflow_phase="execution",
            completed="false",
        )
        == 1.0
    )
    # Histogram saw 2 observations.
    assert (
        _histogram_count(
            exporter_mod.skill_duration_seconds,
            skill_name=skill,
            workflow_phase="execution",
        )
        == 2.0
    )
    # Gauge.
    assert (
        _sample_value(exporter_mod.skill_completion_rate, skill_name=skill)
        == 0.5
    )
    # Anomaly counter.
    assert (
        _sample_value(
            exporter_mod.anomalies_detected_total,
            anomaly_type="drop",
            skill_name=skill,
        )
        == 1.0
    )
    # Active sessions gauge.
    samples = list(exporter_mod.active_sessions_total.collect())[0].samples
    total = next(
        s.value for s in samples if s.name == "active_sessions_total"
    )
    assert total == 3


# ============================================================================
# Edge cases
# ============================================================================


@pytest.mark.unit
def test_zero_duration_records_into_lowest_bucket(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(f"{unique}-x", "p", True, 0.0)
    count = _histogram_count(
        exporter_mod.skill_duration_seconds,
        skill_name=f"{unique}-x",
        workflow_phase="p",
    )
    # 0.0 lands in the lowest bucket but always in +Inf; the total
    # observation count must be exactly 1.
    assert count == 1.0


@pytest.mark.unit
def test_very_large_duration_recorded(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    fresh_exporter.record_invocation(f"{unique}-x", "p", True, 10_000.0)
    count = _histogram_count(
        exporter_mod.skill_duration_seconds,
        skill_name=f"{unique}-x",
        workflow_phase="p",
    )
    assert count == 1.0


@pytest.mark.unit
def test_empty_string_labels_recorded(
    fresh_exporter: PrometheusExporter, unique: str
) -> None:
    """Empty string is a legal Prometheus label value; verify it works.

    ``record_invocation`` normalises a ``None`` workflow_phase to
    ``"unknown"`` *and* an empty string (which is also falsy) to
    ``"unknown"`` too — so we exercise the empty-string path through
    ``record_anomaly`` instead, where no normalisation happens.
    """
    fresh_exporter.record_anomaly("", f"{unique}-skill")
    assert (
        _sample_value(
            exporter_mod.anomalies_detected_total,
            anomaly_type="",
            skill_name=f"{unique}-skill",
        )
        == 1.0
    )
