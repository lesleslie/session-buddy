# Session-Buddy WebSocket API

Real-time WebSocket API for streaming skill metrics and live updates.

## Overview

The WebSocket API provides real-time access to:
- Live skill invocation metrics
- Performance anomaly detection
- Session tracking updates
- Skill-specific monitoring

**WebSocket Endpoint**: `ws://localhost:8765`
**Default Update Interval**: 1 second
**Message Format**: JSON

---

## Connection

### Connecting to WebSocket Server

```javascript
const ws = new WebSocket('ws://localhost:8765');

ws.onopen = () => {
    console.log('Connected to Session-Buddy WebSocket');
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log('Received:', message);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('WebSocket connection closed');
};
```

### Python Client Example

```python
import asyncio
import websockets
import json

async def connect_to_websocket():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        # Subscribe to updates
        await websocket.send(json.dumps({
            "type": "subscribe",
            "skill_name": "pytest-run"  # Or null for all skills
        }))

        # Receive updates
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received: {data}")

asyncio.run(connect_to_websocket())
```

---

## Message Types

### 1. Metrics Update (Server → Client)

Automatic broadcast every 1 second with top skills and anomalies.

**Message Structure**:
```json
{
    "type": "metrics_update",
    "timestamp": "2026-02-10T12:00:00Z",
    "data": {
        "top_skills": [
            {
                "skill_name": "pytest-run",
                "invocation_count": 42,
                "completed_count": 38,
                "avg_duration": 5.2,
                "last_invocation_at": "2026-02-10T12:00:00Z"
            }
        ],
        "anomalies": [
            {
                "skill_name": "mypy",
                "anomaly_type": "performance_drop",
                "baseline_value": 0.85,
                "observed_value": 0.62,
                "deviation_score": 2.3
            }
        ]
    }
}
```

**Fields**:
- `type`: Always `"metrics_update"`
- `timestamp`: ISO 8601 timestamp
- `data.top_skills`: Array of top 10 most active skills
  - `skill_name`: Name of the skill
  - `invocation_count`: Number of invocations in time window
  - `completed_count`: Number of successful completions
  - `avg_duration`: Average execution time in seconds
  - `last_invocation_at`: Timestamp of last invocation
- `data.anomalies`: Array of detected anomalies
  - `skill_name`: Skill with anomaly
  - `anomaly_type`: `"performance_drop"` | `"performance_spike"` | `"pattern_shift"`
  - `baseline_value`: Expected value
  - `observed_value`: Actual value
  - `deviation_score`: Z-score deviation (≥2.0 = anomaly)

---

### 2. Subscribe (Client → Server)

Subscribe to updates for specific skill or all skills.

**Request**:
```json
{
    "type": "subscribe",
    "skill_name": "pytest-run"
}
```

**Fields**:
- `type`: Always `"subscribe"`
- `skill_name`: Skill name to monitor, or `null` for all skills

**Response**:
```json
{
    "type": "subscription_confirmed",
    "skill_name": "pytest-run",
    "message": "Subscribed to updates for pytest-run"
}
```

---

### 3. Get Metrics (Client → Server)

Request current metrics for a specific skill.

**Request**:
```json
{
    "type": "get_metrics",
    "skill_name": "pytest-run"
}
```

**Fields**:
- `type`: Always `"get_metrics"`
- `skill_name`: Skill to query

**Response**:
```json
{
    "type": "metrics_response",
    "data": {
        "skill_name": "pytest-run",
        "total_invocations": 1523,
        "completion_rate": 0.92,
        "avg_duration_seconds": 5.3,
        "last_invocation_at": "2026-02-10T12:00:00Z"
    }
}
```

---

### 4. Error (Server → Client)

Error responses for invalid requests.

**Structure**:
```json
{
    "type": "error",
    "message": "Invalid skill name: unknown_skill"
}
```

---

## Server Configuration

### Starting the WebSocket Server

**Python API**:
```python
from session_buddy.realtime.websocket_server import RealTimeMetricsServer

server = RealTimeMetricsServer(
    host="localhost",
    port=8765,
    db_path="/path/to/skills.db",
    update_interval=1.0  # seconds
)

# Start server (runs forever)
await server.start()
```

**Command Line**:
```bash
python -m session_buddy.websocket-server --port 8765
```

**Configuration Options**:
- `host`: Server host (default: `"localhost"`)
- `port`: Server port (default: `8765`)
- `db_path`: Path to SQLite database (default: from config)
- `update_interval`: Metrics broadcast interval in seconds (default: `1.0`)

---

## Anomaly Detection

### Detection Algorithm

Anomalies are detected using **Z-score analysis**:

```
z_score = (observed_value - baseline_value) / standard_deviation
```

**Threshold**: `|z_score| ≥ 2.0` (2 standard deviations from mean)

### Anomaly Types

| Type | Description | Example |
|------|-------------|---------|
| `performance_drop` | Completion rate significantly below baseline | 85% → 62% (z=-2.3) |
| `performance_spike` | Completion rate significantly above baseline | 80% → 95% (z=2.1) |
| `pattern_shift` | Execution time pattern changed | 5s → 15s average |

---

## Real-Time Metrics Cache

The WebSocket server queries the `skill_metrics_cache` table for performance.

### Cache Table Structure

```sql
CREATE TABLE skill_metrics_cache (
    skill_name TEXT PRIMARY KEY,
    last_invocation_at TEXT NOT NULL,
    invocation_count_1h INTEGER DEFAULT 0,
    invocation_count_24h INTEGER DEFAULT 0,
    avg_completion_rate_24h REAL,
    is_anomalous BOOLEAN DEFAULT 0,
    anomaly_score REAL,
    updated_at TEXT NOT NULL
);
```

### Cache Update Frequency

- **Real-time**: Updated on every skill invocation (via trigger)
- **WebSocket broadcast**: Every 1 second
- **Anomaly detection**: Every broadcast cycle

---

## Usage Examples

### Example 1: Live Dashboard

```javascript
const ws = new WebSocket('ws://localhost:8765');

// Subscribe to all skills
ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'subscribe', skill_name: null }));
};

// Update dashboard every second
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'metrics_update') {
        updateTopSkillsTable(message.data.top_skills);
        highlightAnomalies(message.data.anomalies);
    }
};
```

### Example 2: Skill-Specific Monitoring

```python
import asyncio
import websockets
import json

async def monitor_skill(skill_name: str):
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        # Subscribe to specific skill
        await ws.send(json.dumps({
            "type": "subscribe",
            "skill_name": skill_name
        }))

        # Monitor for anomalies
        while True:
            message = await ws.recv()
            data = json.loads(message)

            if data.get("type") == "metrics_update":
                for anomaly in data["data"]["anomalies"]:
                    if anomaly["skill_name"] == skill_name:
                        print(f"⚠️  ANOMALY: {anomaly['anomaly_type']}")
                        print(f"   Baseline: {anomaly['baseline_value']}")
                        print(f"   Observed: {anomaly['observed_value']}")
                        print(f"   Deviation: {anomaly['deviation_score']}σ")

asyncio.run(monitor_skill("pytest-run"))
```

### Example 3: Alert Integration

```javascript
const ws = new WebSocket('ws://localhost:8765');

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'metrics_update') {
        message.data.anomalies.forEach(anomaly => {
            // Send alert to monitoring system
            sendAlert({
                severity: 'WARNING',
                skill: anomaly.skill_name,
                type: anomaly.anomaly_type,
                deviation: anomaly.deviation_score,
                timestamp: message.timestamp
            });
        });
    }
};
```

---

## Performance Considerations

### Connection Limits

- **Maximum concurrent clients**: 100 (default)
- **Memory per client**: ~1 KB for connection state
- **Broadcast overhead**: ~10 KB per update cycle

### Optimization Tips

1. **Subscribe to specific skills**: Reduces bandwidth vs. all skills
2. **Increase update interval**: Use 2-5 seconds for non-critical monitoring
3. **Filter anomalies on server-side**: Only broadcast anomalies above threshold

### Load Testing

```bash
# Install websockets
pip install websockets

# Run load test
python -m websockets ws://localhost:8765 --count 100 --duration 60
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | WebSocket server not running | Start server with `python -m session_buddy.websocket-server` |
| `Invalid JSON` | Malformed message | Validate JSON before sending |
| `Unknown skill` | Skill doesn't exist in database | Check `skill_metrics` table |

### Reconnection Logic

```javascript
let ws;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function connect() {
    ws = new WebSocket('ws://localhost:8765');

    ws.onclose = () => {
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            console.log(`Reconnecting... (${reconnectAttempts}/${maxReconnectAttempts})`);
            setTimeout(connect, 1000 * reconnectAttempts);
        } else {
            console.error('Max reconnection attempts reached');
        }
    };

    ws.onopen = () => {
        reconnectAttempts = 0;
        console.log('Connected');
    };
}

connect();
```

---

## Security Considerations

### Current Limitations

⚠️ **Production Use Requires**:
- TLS/SSL encryption (wss:// instead of ws://)
- Authentication token validation
- Origin header checking
- Rate limiting per connection

### Recommended Setup

```nginx
# nginx reverse proxy for WebSocket
location /ws {
    proxy_pass http://localhost:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_ssl_server_name on;
}
```

---

## Troubleshooting

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

server = RealTimeMetricsServer(...)
await server.start()
```

### Common Issues

**Issue**: Client not receiving updates
- **Cause**: Not subscribed to any skill
- **Fix**: Send `subscribe` message after connecting

**Issue**: Anomaly detection not working
- **Cause**: Insufficient data points (need ≥5 samples)
- **Fix**: Generate test data with multiple invocations

**Issue**: Server crashes under load
- **Cause**: Too many concurrent connections
- **Fix**: Implement connection pooling or load balancing

---

## API Versioning

**Current Version**: `v1.0`
**Compatibility**: Breaking changes will increment major version

---

## See Also

- [Prometheus Metrics Exporter](./PROMETHEUS.md) - HTTP metrics endpoint
- [V4 Schema Reference](../storage/V4_SCHEMA.md) - Database schema
- [Integration Guide](../integrations/CRACKERJACK.md) - Crackerjack integration
