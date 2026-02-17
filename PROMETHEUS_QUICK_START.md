# Prometheus Metrics Exporter - Quick Start Guide

## Installation

No installation needed! The `prometheus-client` dependency is already in `pyproject.toml` (line 37).

## Basic Usage

### 1. Import and Start

```python
from session_buddy.realtime.metrics_exporter import PrometheusExporter

# Create exporter on port 9090
exporter = PrometheusExporter(port=9090)

# Start HTTP server
exporter.start()

# Metrics now available at http://localhost:9090/metrics
```

### 2. Record Metrics

```python
# Record a skill invocation
exporter.record_invocation(
    skill_name="pytest-run",
    workflow_phase="execution",  # or None for "unknown"
    completed=True,
    duration_seconds=45.2
)

# Update completion rate (0.0 to 1.0)
exporter.update_completion_rate("pytest-run", 0.92)

# Record an anomaly
exporter.record_anomaly("performance_drop", "pytest-run")

# Update active sessions count
exporter.update_active_sessions(5)
```

### 3. Verify Metrics

```bash
# Check metrics endpoint
curl http://localhost:9090/metrics

# Or visit in browser
open http://localhost:9090/metrics
```

## Metrics Reference

### Counter: skill_invocations_total
```python
# Automatically incremented by record_invocation()
exporter.record_invocation("pytest-run", "execution", True, 45.2)
```

**Labels:** `skill_name`, `workflow_phase`, `completed` ("true"/"false")

### Histogram: skill_duration_seconds
```python
# Automatically recorded by record_invocation()
exporter.record_invocation("pytest-run", "execution", True, 45.2)
```

**Labels:** `skill_name`, `workflow_phase`

**Buckets:** [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0] seconds

### Gauge: skill_completion_rate
```python
# Manually update completion rate
exporter.update_completion_rate("pytest-run", 0.92)
```

**Labels:** `skill_name`

**Range:** 0.0 to 1.0

### Gauge: active_sessions_total
```python
# Update active session count
exporter.update_active_sessions(5)
```

**Labels:** None (global counter)

### Counter: anomalies_detected_total
```python
# Record anomaly detection
exporter.record_anomaly("performance_drop", "pytest-run")
```

**Labels:** `anomaly_type` ("drop", "spike", "pattern_shift"), `skill_name`

## Testing

### Run Test Script

```bash
cd /Users/les/Projects/session-buddy
python test_prometheus_metrics.py
```

### Run Demo

```bash
cd /Users/les/Projects/session-buddy
python session_buddy/realtime/metrics_exporter.py
```

Visit http://localhost:9090/metrics to see live metrics.

## Prometheus Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'session-buddy'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:9090']
```

Restart Prometheus:

```bash
# Check config
promtool check config prometheus.yml

# Restart Prometheus
prometheus --config.file=prometheus.yml
```

## Grafana Dashboard Examples

### Panel 1: Skill Completion Rate
```
Metric: skill_completion_rate
Legend: {{skill_name}}
Type: Gauge
```

### Panel 2: Average Duration (p95)
```promql
histogram_quantile(0.95,
  sum(rate(skill_duration_seconds_bucket[5m])) by (skill_name, le)
)
```

### Panel 3: Invocation Rate
```promql
sum(rate(skill_invocations_total[5m])) by (skill_name)
```

### Panel 4: Active Sessions
```
Metric: active_sessions_total
Type: Stat
```

### Panel 5: Anomalies by Type
```promql
sum(anomalies_detected_total) by (anomaly_type)
```

## Common Patterns

### Track Skill Success Rate
```python
# In your skill execution code
try:
    start_time = time.time()
    result = execute_skill(skill_name)
    duration = time.time() - start_time

    exporter.record_invocation(
        skill_name=skill_name,
        workflow_phase="execution",
        completed=True,
        duration_seconds=duration
    )
except Exception as e:
    exporter.record_invocation(
        skill_name=skill_name,
        workflow_phase="execution",
        completed=False,
        duration_seconds=None
    )
```

### Periodic Completion Rate Update
```python
import asyncio

async def update_metrics_periodically():
    while True:
        # Get metrics from database
        skills = storage.get_top_skills(limit=10)

        for skill in skills:
            exporter.update_completion_rate(
                skill.skill_name,
                skill.completion_rate
            )

        await asyncio.sleep(60)  # Every minute
```

### Anomaly Detection Integration
```python
# In your anomaly detection logic
if deviation_score > 2.0:
    exporter.record_anomaly(
        anomaly_type="drop",
        skill_name=skill_name
    )
```

## Troubleshooting

### Port Already in Use
```python
# Use a different port
exporter = PrometheusExporter(port=9091)
```

### Metrics Not Appearing
```python
# Check if server is running
if exporter.is_running():
    print("Exporter is running")
else:
    exporter.start()
```

### Label Cardinality Issues
```python
# Keep label values limited (<100 unique values)
# Use "unknown" for missing values
exporter.record_invocation("skill", None, True, 1.0)  # phase="unknown"
```

## Best Practices

1. **Start exporter once** at application startup
2. **Record metrics synchronously** in your skill execution path
3. **Update gauges periodically** (e.g., every 60 seconds)
4. **Use consistent label values** (lowercase, underscores)
5. **Monitor metric cardinality** (keep <10k unique metric series)
6. **Test in development** before production deployment

## Files Reference

- **Implementation:** `session_buddy/realtime/metrics_exporter.py`
- **Test Script:** `test_prometheus_metrics.py`
- **Full Documentation:** `PROMETHEUS_EXPORTER_IMPLEMENTATION.md`

## Support

For issues or questions:
1. Check the test script: `python test_prometheus_metrics.py`
2. Verify Prometheus config: `promtool check config prometheus.yml`
3. Test endpoint manually: `curl http://localhost:9090/metrics`
4. Review logs for errors

---

**Status:** ✅ Production Ready
**Version:** 1.0.0
**Last Updated:** 2026-02-10
