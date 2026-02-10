# Prometheus Metrics for Session-Buddy

Session-Buddy provides comprehensive Prometheus metrics for monitoring session lifecycle, MCP event emission, and system performance. Metrics are exported in Prometheus text format for scraping by Prometheus server.

## Overview

Session-Buddy exposes metrics through three key components:

1. **SessionMetrics Class** - Core Prometheus metrics collectors
1. **SessionTracker Integration** - Automatic metric recording during session operations
1. **MCP Tools** - Query metrics via MCP protocol

## Available Metrics

### Session Lifecycle Metrics

#### `session_start_total`

**Type:** Counter

**Description:** Total number of session start events tracked

**Labels:**

- `component_name` - Component name (e.g., "mahavishnu", "session-buddy")
- `shell_type` - Shell type (e.g., "MahavishnuShell", "SessionBuddyShell")

**Example:**

```prometheus
session_start_total{component_name="mahavishnu",shell_type="MahavishnuShell"} 42
```

#### `session_end_total`

**Type:** Counter

**Description:** Total number of session end events tracked

**Labels:**

- `component_name` - Component name
- `status` - Session end status ("success", "error")

**Example:**

```prometheus
session_end_total{component_name="mahavishnu",status="success"} 40
session_end_total{component_name="mahavishnu",status="error"} 2
```

#### `session_duration_seconds`

**Type:** Histogram

**Description:** Session duration in seconds

**Labels:**

- `component_name` - Component name

**Buckets:** [60, 300, 900, 1800, 3600, 7200, 14400, 28800]
(1min, 5min, 15min, 30min, 1hr, 2hr, 4hr, 8hr)

**Example:**

```prometheus
session_duration_seconds_bucket{component_name="mahavishnu",le="60"} 5
session_duration_seconds_bucket{component_name="mahavishnu",le="3600"} 35
session_duration_seconds_sum{component_name="mahavishnu"} 125000
session_duration_seconds_count{component_name="mahavishnu"} 40
```

### MCP Event Metrics

#### `mcp_event_emit_success_total`

**Type:** Counter

**Description:** Total number of successful MCP event emissions

**Labels:**

- `component_name` - Component name
- `event_type` - Type of event emitted (e.g., "session_start", "session_end")

**Example:**

```prometheus
mcp_event_emit_success_total{component_name="mahavishnu",event_type="session_start"} 42
```

#### `mcp_event_emit_failure_total`

**Type:** Counter

**Description:** Total number of failed MCP event emissions

**Labels:**

- `component_name` - Component name
- `event_type` - Type of event being emitted
- `error_type` - Type of error (e.g., "ValidationError", "ConnectionError")

**Example:**

```prometheus
mcp_event_emit_failure_total{component_name="mahavishnu",event_type="session_start",error_type="ValidationError"} 2
```

#### `mcp_event_emit_duration_seconds`

**Type:** Histogram

**Description:** MCP event emission duration in seconds

**Labels:**

- `component_name` - Component name
- `event_type` - Type of event emitted

**Buckets:** [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
(1ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s)

**Example:**

```prometheus
mcp_event_emit_duration_seconds_bucket{component_name="mahavishnu",event_type="session_start",le="0.1"} 40
```

### System Health Metrics

#### `active_sessions`

**Type:** Gauge

**Description:** Number of currently active sessions

**Labels:**

- `component_name` - Component name

**Example:**

```prometheus
active_sessions{component_name="mahavishnu"} 3
```

#### `session_quality_score`

**Type:** Gauge

**Description:** Session quality score (0-100)

**Labels:**

- `component_name` - Component name

**Example:**

```prometheus
session_quality_score{component_name="mahavishnu"} 85.5
```

## Configuration

Prometheus metrics are enabled by default. Configuration is managed through `SessionMgmtSettings`:

### Enable/Disable Metrics

**Environment Variable:**

```bash
export SESSION_BUDDY_ENABLE_PROMETHEUS_METRICS=true
```

**Configuration File (`settings/session-buddy.yaml`):**

```yaml
enable_prometheus_metrics: true
```

**Disable Metrics:**

```yaml
enable_prometheus_metrics: false
```

### Metrics Endpoint Configuration

```yaml
prometheus_metrics_port: 9090
prometheus_metrics_path: "/metrics"
```

## MCP Tools

Session-Buddy provides three MCP tools for querying metrics:

### 1. `get_prometheus_metrics`

Export all Session-Buddy metrics in Prometheus text format.

**Returns:** Metrics in Prometheus text format (CONTENT_TYPE_LATEST)

**Example:**

```python
metrics = await get_prometheus_metrics()
print(metrics)
# Output:
# HELP session_start_total Total number of session start events tracked
# TYPE session_start_total counter
session_start_total{component_name="mahavishnu",shell_type="MahavishnuShell"} 42
```

### 2. `list_session_metrics`

List all available session metrics with descriptions.

**Returns:** Dictionary with metric metadata

**Example:**

```python
metrics_info = await list_session_metrics()
print(metrics_info["session_start_total"]["description"])
# Output: "Total number of session start events tracked"
```

**Response Structure:**

```json
{
  "session_lifecycle_metrics": {
    "session_start_total": {
      "type": "Counter",
      "description": "Total number of session start events tracked",
      "labels": ["component_name", "shell_type"]
    }
  },
  "mcp_event_metrics": {
    "mcp_event_emit_success_total": {
      "type": "Counter",
      "description": "Total number of successful MCP event emissions",
      "labels": ["component_name", "event_type"]
    }
  },
  "system_health_metrics": {
    "active_sessions": {
      "type": "Gauge",
      "description": "Number of currently active sessions",
      "labels": ["component_name"]
    }
  }
}
```

### 3. `get_metrics_summary`

Get summary statistics of session metrics.

**Returns:** Dictionary with metrics summary

**Example:**

```python
summary = await get_metrics_summary()
print(summary["total_sessions_started"])
# Output: 42

print(summary["active_sessions"])
# Output: {"mahavishnu": 3, "session-buddy": 1}
```

**Response Structure:**

```json
{
  "total_sessions_started": 42,
  "total_sessions_ended": 40,
  "active_sessions": {
    "mahavishnu": 3,
    "session-buddy": 1
  },
  "quality_scores": {
    "mahavishnu": 85.5
  },
  "mcp_events_success": 85,
  "mcp_events_failure": 2
}
```

## Prometheus Configuration

### Scrape Configuration

Add Session-Buddy to your Prometheus scrape configuration (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'session-buddy'
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: '/metrics'
    static_configs:
      - targets: ['localhost:9090']
```

### Example Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Session-Buddy Metrics",
    "panels": [
      {
        "title": "Session Starts",
        "targets": [
          {
            "expr": "rate(session_start_total[5m])",
            "legendFormat": "{{component_name}} - {{shell_type}}"
          }
        ]
      },
      {
        "title": "Active Sessions",
        "targets": [
          {
            "expr": "active_sessions",
            "legendFormat": "{{component_name}}"
          }
        ]
      },
      {
        "title": "Session Duration",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(session_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile - {{component_name}}"
          }
        ]
      },
      {
        "title": "Session Quality Score",
        "targets": [
          {
            "expr": "session_quality_score",
            "legendFormat": "{{component_name}}"
          }
        ]
      }
    ]
  }
}
```

## Common Prometheus Queries

### Session Rate

Calculate the rate of session starts per minute:

```prometheus
rate(session_start_total[1m])
```

### Error Rate

Calculate the percentage of failed sessions:

```prometheus
sum(rate(session_end_total{status="error"}[5m])) / sum(rate(session_end_total[5m])) * 100
```

### Average Session Duration

Calculate the average session duration:

```prometheus
rate(session_duration_seconds_sum[5m]) / rate(session_duration_seconds_count[5m])
```

### Percentile Duration

Calculate the 95th percentile session duration:

```prometheus
histogram_quantile(0.95, rate(session_duration_seconds_bucket[5m]))
```

### Active Sessions by Component

Show current active sessions grouped by component:

```prometheus
active_sessions
```

## Testing

### Unit Testing

```python
import pytest
from prometheus_client import CollectorRegistry
from session_buddy.mcp.metrics import SessionMetrics

def test_session_metrics():
    registry = CollectorRegistry()
    metrics = SessionMetrics(registry=registry)

    # Record session start
    metrics.record_session_start("mahavishnu", "MahavishnuShell")

    # Verify metric was recorded
    assert metrics.session_start_total.labels(
        component_name="mahavishnu",
        shell_type="MahavishnuShell"
    )._value._value == 1

    # Record session end
    metrics.record_session_end("mahavishnu", "success", duration_seconds=3600.5)

    # Verify metrics
    assert metrics.session_end_total.labels(
        component_name="mahavishnu",
        status="success"
    )._value._value == 1
```

### Integration Testing

```python
from session_buddy.core import SessionLifecycleManager
from session_buddy.mcp.session_tracker import SessionTracker
from session_buddy.mcp.event_models import SessionStartEvent

@pytest.mark.asyncio
async def test_session_tracker_metrics():
    lifecycle_mgr = SessionLifecycleManager()
    tracker = SessionTracker(lifecycle_mgr, enable_metrics=True)

    event = SessionStartEvent(
        event_version="1.0",
        event_id="550e8400-e29b-41d4-a716-446655440000",
        component_name="mahavishnu",
        shell_type="MahavishnuShell",
        timestamp="2026-02-06T12:34:56.789Z",
        pid=12345,
        user=UserInfo(username="john", home="/home/john"),
        hostname="server01",
        environment=EnvironmentInfo(
            python_version="3.13.0",
            platform="Linux-6.5.0-x86_64",
            cwd="/home/john/projects/mahavishnu"
        )
    )

    result = await tracker.handle_session_start(event)
    assert result.status == "tracked"

    # Verify metrics were recorded
    metrics = tracker.metrics
    assert metrics is not None
    assert metrics.session_start_total._value._value > 0
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Session-Buddy MCP                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────┐      ┌─────────────────────┐     │
│  │   SessionTracker     │──────│  SessionMetrics      │     │
│  │                      │      │                      │     │
│  │ • handle_start()     │      │ • Counters           │     │
│  │ • handle_end()       │      │ • Histograms         │     │
│  │ • track events       │      │ • Gauges             │     │
│  └──────────────────────┘      └─────────────────────┘     │
│           │                            │                     │
│           │                            │                     │
│           ▼                            ▼                     │
│  ┌───────────────────────────────────────────────────┐   │
│  │           Prometheus Collectors                    │   │
│  │  ┌─────────────────┐  ┌──────────────────────┐   │   │
│  │  │ session_start   │  │ mcp_event_success    │   │   │
│  │  │ session_end     │  │ mcp_event_failure    │   │   │
│  │  │ duration        │  │ emit_duration        │   │   │
│  │  │ active_sessions │  │ quality_score         │   │   │
│  │  └─────────────────┘  └──────────────────────┘   │   │
│  └───────────────────────────────────────────────────┘   │
│                           │                                │
│                           ▼                                │
│  ┌───────────────────────────────────────────────────┐   │
│  │              MCP Tools                             │   │
│  │  • get_prometheus_metrics()                       │   │
│  │  • list_session_metrics()                         │   │
│  │  • get_metrics_summary()                          │   │
│  └───────────────────────────────────────────────────┘   │
│                           │                                │
└───────────────────────────┼────────────────────────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   Prometheus    │
                   │   Scraper       │
                   │   :9090/metrics │
                   └─────────────────┘
```

## Best Practices

### 1. Label Selection

Use consistent label values:

- `component_name`: Use lowercase, hyphen-separated names (e.g., "mahavishnu", "session-buddy")
- `shell_type`: Use PascalCase class names (e.g., "MahavishnuShell", "SessionBuddyShell")
- `status`: Use lowercase status values (e.g., "success", "error")

### 2. Metric Cardinality

Avoid high cardinality labels:

- Don't include user-specific labels (e.g., username, hostname)
- Don't include session IDs as labels
- Keep label values to a bounded set

### 3. Scrape Interval

Recommended scrape intervals:

- Development: 15 seconds
- Production: 30-60 seconds
- Large deployments: 2-5 minutes

### 4. Retention Policy

Configure Prometheus retention based on your needs:

```yaml
# prometheus.yml
global:
  scrape_interval: 30s
  retention.time: 90d
```

## Troubleshooting

### Metrics Not Appearing

1. Check if metrics are enabled:

   ```python
   from session_buddy.settings import get_settings
   settings = get_settings()
   print(settings.enable_prometheus_metrics)
   ```

1. Check for import errors:

   ```python
   from session_buddy.mcp.metrics import METRICS_AVAILABLE
   print(METRICS_AVAILABLE)
   ```

1. Verify prometheus_client is installed:

   ```bash
   pip show prometheus-client
   ```

### High Memory Usage

If Prometheus metrics are causing high memory usage:

1. Reduce metric cardinality by limiting label values

1. Disable metrics if not needed:

   ```yaml
   enable_prometheus_metrics: false
   ```

1. Adjust histogram bucket ranges in `SessionMetrics.__init__()`

## Dependencies

```toml
[project.dependencies]
prometheus-client = ">=0.21.0"
```

## Related Documentation

- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Prometheus Data Types](https://prometheus.io/docs/concepts/metric_types/)
- [Session Tracker Documentation](./SESSION_TRACKING.md)
- [Settings Reference](./SETTINGS.md)
