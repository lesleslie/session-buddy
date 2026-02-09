# Session-Buddy Service Dependencies

**Last Updated**: 2026-02-09
**Status**: Production Ready

______________________________________________________________________

## Overview

Session-Buddy is designed to be **fully standalone** in lite mode, requiring no external services. In standard mode, it integrates with optional Mahavishnu ecosystem services for enhanced capabilities.

______________________________________________________________________

## Required Services

### None (Session-Buddy is Standalone)

Session-Buddy operates independently with no required dependencies:

- **Lite Mode**: 100% self-contained, zero external services
- **Standard Mode**: Self-contained with optional integrations

**Minimum Requirements**:
- Python 3.11+
- 100MB disk space (lite mode)
- 512MB RAM (lite mode)

______________________________________________________________________

## Optional Integrations

### Mahavishnu (Orchestrator)

**Purpose**: Workflow orchestration and task execution coordination

**Protocol**: MCP (Model Context Protocol)

**Connection**:
- Mahavishna → Session-Buddy (client initiates)
- Session-Buddy acts as MCP server
- Mahavishna delegates session management

**Configuration**:

In Mahavishnu's `.mcp.json`:
```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "session-buddy",
      "args": ["start", "--mode=standard", "--mcp"],
      "env": {
        "SESSION_BUDDY_AUTH_ENABLED": "true",
        "SESSION_BUDDY_AUTH_SECRET": "${SESSION_BUDDY_AUTH_SECRET}"
      }
    }
  }
}
```

**Required For**:
- Session delegation from Mahavishnu
- Cross-project session tracking
- Workflow state persistence
- Checkpoint/resume functionality

**Not Required For**:
- Standalone session management
- Local development
- Testing and debugging

**Startup Order**:
1. Start Session-Buddy: `session-buddy start --mode=standard --mcp`
2. Start Mahavishnu: `mahavishnu start`
3. Mahavishnu auto-connects to Session-Buddy

**Health Check**:
```bash
# Check Session-Buddy is running
session-buddy health

# Check Mahavishnu can connect
mahavishnu health
```

**Troubleshooting**:

**Problem**: "Mahavishnu cannot connect to Session-Buddy"
**Solution**:
```bash
# Verify Session-Buddy MCP server is running
session-buddy health | grep "MCP Server"

# Check port is available
lsof -i :8678

# Restart Session-Buddy with MCP enabled
session-buddy start --mode=standard --mcp --port 8678
```

**Problem**: "Authentication failed"
**Solution**:
```bash
# Verify auth is enabled on both sides
export SESSION_BUDDY_AUTH_ENABLED=true
export SESSION_BUDDY_AUTH_SECRET="same-secret-on-both-sides"

# Restart both services
session-buddy start --mode=standard --mcp
mahavishnu start
```

---

### Akosha (Diviner)

**Purpose**: Advanced analytics and pattern recognition across projects

**Protocol**: MCP / HTTP API

**Connection**:
- Session-Buddy → Akosha (client initiates)
- Syncs analytics data periodically
- Aggregates cross-project insights

**Configuration**:

In `settings/session-buddy.yaml`:
```yaml
sync:
  akosha_enabled: true
  akosha_url: "http://localhost:8682/mcp"
  sync_interval: 300  # seconds (5 minutes)
```

Or via environment variables:
```bash
export SESSION_BUDDY_AKOSHA_ENABLED=true
export SESSION_BUDDY_AKOSHA_URL="http://localhost:8682/mcp"
```

**Required For**:
- Cross-project analytics
- Advanced pattern recognition
- Knowledge graph integration
- Multi-project insights

**Not Required For**:
- Single-project usage
- Basic analytics (DuckDB-powered)
- Local development

**Startup Order**:
1. Start Akosha: `akosha start --mcp`
2. Start Session-Buddy: `session-buddy start --mode=standard`
3. Session-Buddy syncs to Akosha automatically

**Health Check**:
```bash
# Check Akosha is running
curl http://localhost:8682/health

# Check sync status
session-buddy sync-status
```

**Troubleshooting**:

**Problem**: "Session-Buddy cannot connect to Akosha"
**Solution**:
```bash
# Verify Akosha is running
curl http://localhost:8682/health

# Check URL is correct
echo $SESSION_BUDDY_AKOSHA_URL

# Test connectivity
curl http://localhost:8682/mcp

# Restart Session-Buddy with debug logging
SESSION_BUDDY_LOG_LEVEL=DEBUG session-buddy start --mode=standard
```

**Problem**: "Sync is not working"
**Solution**:
```bash
# Check sync is enabled
session-buddy config | grep akosha

# Manually trigger sync
session-buddy sync-now

# Check sync logs
session-buddy logs | grep -i sync
```

---

### Crackerjack (Inspector)

**Purpose**: Quality control, testing, and code quality tracking

**Protocol**: MCP

**Connection**:
- Session-Buddy → Crackerjack (client initiates)
- Stores test results in sessions
- Tracks quality metrics over time

**Configuration**:

In `settings/session-buddy.yaml`:
```yaml
integrations:
  crackerjack_enabled: true
  crackerjack_url: "http://localhost:8676/mcp"
```

**Required For**:
- Test result storage in sessions
- Quality trend tracking
- Correlating code changes with test results
- Automated QC reporting

**Not Required For**:
- Basic session management
- Manual testing workflows
- Development without QC tracking

**Usage Example**:
```python
# Store test result in session
await mcp.call_tool("store_test_result", {
    "session_id": "abc123",
    "test_file": "test_auth.py",
    "result": "passed",
    "coverage": 95,
    "duration_ms": 1234
})
```

**Troubleshooting**:

**Problem**: "Cannot store test results"
**Solution**:
```bash
# Verify Crackerjack is running
crackerjack health

# Check MCP connection
session-buddy health | grep crackerjack

# Use manual testing if Crackerjack unavailable
session-buddy add-message --session "my-project" "Manual test passed"
```

---

### Ollama (LLM Service)

**Purpose**: Local LLM for embedding generation and intelligence features

**Protocol**: HTTP API

**Connection**:
- Session-Buddy → Ollama (client initiates)
- Generates embeddings for semantic search
- Powers AI insights

**Configuration**:

In `settings/session-buddy.yaml`:
```yaml
intelligence:
  enabled: true
  embedding_model: "nomic-embed-text"
  ollama_base_url: "http://localhost:11434"
```

**Required For**:
- Semantic search (vector similarity)
- AI-powered insights
- Pattern detection
- Intelligent recommendations

**Not Required For**:
- Basic session management
- Keyword search
- Manual tagging

**Setup**:
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull embedding model
ollama pull nomic-embed-text

# Verify Ollama is running
ollama list

# Test embedding generation
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "test"
}'
```

**Troubleshooting**:

**Problem**: "Cannot generate embeddings"
**Solution**:
```bash
# Check Ollama is running
ps aux | grep ollama

# Verify model is pulled
ollama list | grep nomic

# Pull model if missing
ollama pull nomic-embed-text

# Test Ollama API
curl http://localhost:11434/api/tags

# Disable intelligence features if Ollama unavailable
session-buddy start --mode=lite --no-intelligence
```

---

### PostgreSQL (Database)

**Purpose**: Persistent storage alternative to SQLite

**Protocol**: PostgreSQL wire protocol

**Connection**:
- Session-Buddy → PostgreSQL (client initiates)
- Persistent session storage
- Advanced JSON support
- Better concurrent access

**Configuration**:

In `settings/session-buddy.yaml`:
```yaml
database:
  type: "postgresql"
  host: "localhost"
  port: 5432
  database: "session_buddy"
  user: "session_buddy"
  password_env: "SESSION_BUDDY_DB_PASSWORD"
  sslmode: "verify-full"  # Required for production
  pool_size: 10
  max_overflow: 20
```

**Required For**:
- Production deployments
- High-concurrency scenarios
- Advanced JSON queries
- pgvector extension (vector similarity)

**Not Required For**:
- Development (use SQLite)
- Testing (use in-memory)
- Low-traffic deployments

**Setup**:
```bash
# Create database
createdb session_buddy

# Create user
psql -c "CREATE USER session_buddy WITH PASSWORD 'secure-password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE session_buddy TO session_buddy;"

# Run migrations
session-buddy migrate --database postgresql

# Verify connection
session-buddy health
```

**Troubleshooting**:

**Problem**: "Cannot connect to PostgreSQL"
**Solution**:
```bash
# Verify PostgreSQL is running
pg_isready

# Check connection details
psql -h localhost -U session_buddy -d session_buddy

# Test SSL connection
psql "postgres://session_buddy:password@localhost:5432/session_buddy?sslmode=verify-full"

# Fall back to SQLite if PostgreSQL unavailable
session-buddy start --mode=standard --database sqlite
```

**Problem**: "SSL connection failed"
**Solution**:
```bash
# Verify SSL mode is set correctly
session-buddy config | grep sslmode

# For development, can use sslmode=require (no cert verification)
# For production, MUST use sslmode=verify-full

export SESSION_BUDDY_DB_SSLMODE=verify-full
session-buddy start --mode=standard
```

______________________________________________________________________

## Deployment Scenarios

### Development Environment

**Mode**: Lite
**Services**: Session-Buddy only
**Database**: In-memory SQLite

**Startup**:
```bash
session-buddy start --mode=lite
```

**Dependencies**: None

---

### Local Development with Ecosystem

**Mode**: Standard
**Services**:
1. Session-Buddy (primary)
2. Mahavishnu (optional)
3. Ollama (optional, for embeddings)

**Startup**:
```bash
# Terminal 1: Session-Buddy
session-buddy start --mode=standard --mcp

# Terminal 2: Mahavishnu (optional)
mahavishnu start

# Terminal 3: Ollama (optional)
ollama serve
```

**Dependencies**:
- Session-Buddy (required)
- Mahavishnu (optional)
- Ollama (optional)

---

### Production Deployment

**Mode**: Standard
**Services**:
1. Session-Buddy (required)
2. PostgreSQL (required)
3. Mahavishnu (recommended)
4. Akosha (optional)
5. Ollama (optional)

**Startup** (via docker-compose):
```bash
docker-compose up -d
```

**Dependencies**:
- Session-Buddy (required)
- PostgreSQL (required)
- Mahavishnu (recommended)
- Akosha (optional)
- Ollama (optional)

---

### CI/CD Pipeline

**Mode**: Lite
**Services**: Session-Buddy only
**Database**: In-memory

**Startup**:
```bash
session-buddy start --mode=lite --no-auth
pytest tests/
```

**Dependencies**: None

______________________________________________________________________

## Dependency Graph

```mermaid
graph TB
    subgraph "Required"
        SB[Session-Buddy]
    end

    subgraph "Optional - Ecosystem"
        MV[Mahavishnu]
        AK[Akosha]
        CJ[Crackerjack]
    end

    subgraph "Optional - Infrastructure"
        PG[PostgreSQL]
        OL[Ollama]
    end

    MV --> SB
    SB --> AK
    SB --> CJ
    SB --> PG
    SB --> OL

    style SB fill:#90EE90,stroke:#2E7D32,stroke-width:3px
    style MV fill:#FFD700,stroke:#B8860B,stroke-width:2px
    style AK fill:#FFD700,stroke:#B8860B,stroke-width:2px
    style CJ fill:#FFD700,stroke:#B8860B,stroke-width:2px
    style PG fill:#87CEEB,stroke:#1565C0,stroke-width:2px
    style OL fill:#FFA500,stroke:#B8860B,stroke-width:2px
```

**Legend**:
- **Green**: Required (Session-Buddy itself)
- **Yellow**: Optional ecosystem services
- **Blue**: Optional infrastructure
- **Orange**: Optional AI/ML services

______________________________________________________________________

## Port Allocation

| Service | Default Port | Configurable | Required |
|---------|--------------|--------------|----------|
| Session-Buddy MCP | 8678 | Yes (CLI) | Yes (standard mode) |
| Mahavishna MCP | 8680 | Yes | No |
| Akosha MCP | 8682 | Yes | No |
| Crackerjack MCP | 8676 | Yes | No |
| PostgreSQL | 5432 | Yes | No (SQLite default) |
| Ollama | 11434 | No | No |

**Configure Ports**:

Session-Buddy:
```bash
session-buddy start --mode=standard --mcp --port 8679
```

Mahavishnu (in `.mcp.json`):
```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "session-buddy",
      "args": ["start", "--mode=standard", "--mcp", "--port", "8679"]
    }
  }
}
```

______________________________________________________________________

## Health Check Matrix

| Service | Health Check Command | Expected Output |
|---------|---------------------|-----------------|
| Session-Buddy | `session-buddy health` | `Status: healthy` |
| Mahavishna | `mahavishnu health` | `Status: healthy` |
| Akosha | `curl http://localhost:8682/health` | `{"status": "ok"}` |
| Crackerjack | `crackerjack health` | `Status: healthy` |
| PostgreSQL | `pg_isready` | `localhost:5432 - accepting connections` |
| Ollama | `curl http://localhost:11434/api/tags` | JSON with models list |

______________________________________________________________________

## Security Considerations

### Authentication

**Session-Buddy**:
- Enable JWT auth in production
- Use strong secret (32+ characters)
- Set appropriate expiration

**Mahavishnu Integration**:
- Use same auth secret on both sides
- Enable TLS for remote connections
- Rotate secrets regularly

**PostgreSQL**:
- Always use SSL (`sslmode=verify-full`)
- Use strong passwords
- Restrict network access
- Enable connection auditing

### Network Security

**Local Development**:
- Use `127.0.0.1` (localhost only)
- No external exposure
- No authentication required

**Production**:
- Restrict to specific interfaces
- Enable authentication
- Use TLS for all connections
- Firewall rules to restrict access

**Example Production Config**:
```yaml
# settings/session-buddy.yaml
server:
  host: "10.0.1.10"  # Specific interface, not 0.0.0.0
  port: 8678

auth:
  enabled: true
  algorithm: "HS256"
  expire_minutes: 60

database:
  sslmode: "verify-full"  # Always SSL for PostgreSQL
```

______________________________________________________________________

## Troubleshooting Guide

### General Issues

**"Service won't start"**:
```bash
# Check what's blocking the port
lsof -i :8678

# Use a different port
session-buddy start --port 8679

# Check logs
session-buddy logs --tail 50
```

**"Cannot connect to service"**:
```bash
# Verify service is running
curl http://localhost:8678/health

# Check firewall rules
sudo iptables -L -n | grep 8678

# Test connectivity
telnet localhost 8678
```

**"Authentication failed"**:
```bash
# Verify auth is enabled
session-buddy config | grep auth

# Check secret is set
echo $SESSION_BUDDY_AUTH_SECRET

# Generate new secret
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### Service-Specific Issues

**Mahavishnu**:
- Problem: "Mahavishnu cannot find Session-Buddy"
- Solution: Check `.mcp.json` configuration, verify Session-Buddy is running

**Akosha**:
- Problem: "Sync is not working"
- Solution: Check `sync_interval`, manually trigger sync with `session-buddy sync-now`

**PostgreSQL**:
- Problem: "SSL connection failed"
- Solution: Verify `sslmode=verify-full`, check certificates

**Ollama**:
- Problem: "Cannot generate embeddings"
- Solution: Verify Ollama is running, pull model with `ollama pull nomic-embed-text`

______________________________________________________________________

## Best Practices

### Development

1. **Use lite mode** for fastest startup
2. **No external services** required
3. **In-memory database** for testing
4. **Disable authentication** locally

### Production

1. **Use standard mode** with PostgreSQL
2. **Enable authentication** with JWT
3. **Use SSL** for all connections
4. **Monitor service health** regularly
5. **Set up alerts** for service failures
6. **Backup database** daily
7. **Rotate secrets** every 90 days

### Integration

1. **Start services in order**: Dependencies first
2. **Verify health** before proceeding
3. **Use environment variables** for configuration
4. **Document custom ports** and settings
5. **Test connectivity** before production

______________________________________________________________________

## Quick Reference

### Start Commands

```bash
# Lite mode (standalone)
session-buddy start --mode=lite

# Standard mode with PostgreSQL
session-buddy start --mode=standard --database postgresql

# Standard mode with MCP (for Mahavishnu)
session-buddy start --mode=standard --mcp

# Full production setup
session-buddy start --mode=standard --mcp --analytics --database postgresql
```

### Health Checks

```bash
# Session-Buddy
session-buddy health

# Mahavishnu
mahavishnu health

# Akosha
curl http://localhost:8682/health

# PostgreSQL
pg_isready

# Ollama
curl http://localhost:11434/api/tags
```

### Configuration Files

```bash
# Session-Buddy config
settings/session-buddy.yaml

# Mahavishnu MCP config
.mcp.json

# Environment variables
.env  # or export SESSION_BUDDY_*
```

______________________________________________________________________

## Summary

Session-Buddy is designed to be **fully standalone** with no required dependencies. It integrates optionally with Mahavishnu ecosystem services for enhanced capabilities:

**Required**: None (Session-Buddy is standalone)

**Optional Integrations**:
- Mahavishnu (orchestration)
- Akosha (analytics)
- Crackerjack (quality control)
- PostgreSQL (persistent storage)
- Ollama (LLM embeddings)

**For most development**: Use lite mode with no external services

**For production**: Use standard mode with PostgreSQL, Mahavishnu, and optional integrations

______________________________________________________________________

**Last Updated**: 2026-02-09
**Status**: Production Ready
