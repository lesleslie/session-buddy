#!/bin/bash
# Session-Buddy Phase 4 Production Deployment Script
# Deploys all Phase 4 services for production use

set -e

echo "🚀 Session-Buddy Phase 4 Production Deployment"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SESSION_BUDDY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${DB_PATH:-$SESSION_BUDDY_ROOT/.session-buddy/skills.db}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
WEBSOCKET_PORT="${WEBSOCKET_PORT:-8765}"

# Virtual environment activation
VENV_PATH="${VENV_PATH:-$SESSION_BUDDY_ROOT/.venv}"
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo -e "${GREEN}✓ Virtual environment activated: $VENV_PATH${NC}"
else
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "   Please install session-buddy first: uv sync"
    exit 1
fi

# ============================================================================
# Step 1: Pre-deployment Checks
# ============================================================================

echo -e "${YELLOW}Step 1: Pre-deployment Checks${NC}"
echo "-------------------------------"

# Check database exists
if [ ! -f "$DB_PATH" ]; then
    echo -e "${YELLOW}⚠️  Database not found. Running fresh initialization...${NC}"
    bash "$SESSION_BUDDY_ROOT/scripts/initialize_fresh.sh"
    if [ $? -ne 0 ]; then
        echo "❌ Database initialization failed"
        exit 1
    fi
fi

# Verify V4 migration
V4_CHECK=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('skill_metrics_cache', 'skill_time_series', 'skill_anomalies');" 2>/dev/null || echo "0")
if [ "$V4_CHECK" -lt 3 ]; then
    echo "❌ V4 migration not applied. Please run deployment first."
    exit 1
fi

echo -e "${GREEN}✓ Pre-deployment checks passed${NC}"
echo ""

# ============================================================================
# Step 2: Start Prometheus Exporter
# ============================================================================

echo -e "${YELLOW}Step 2: Starting Prometheus Metrics Exporter${NC}"
echo "----------------------------------------------"

# Check if already running
if lsof -i :$PROMETHEUS_PORT > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Prometheus exporter already running on port $PROMETHEUS_PORT${NC}"
else
    echo "Starting Prometheus exporter in background..."
    cd "$SESSION_BUDDY_ROOT"
    nohup python examples/run_prometheus_exporter.py > /tmp/prometheus_exporter.log 2>&1 &
    PROM_PID=$!
    echo "Started Prometheus exporter (PID: $PROM_PID)"
    sleep 2

    if lsof -i :$PROMETHEUS_PORT > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Prometheus exporter running on port $PROMETHEUS_PORT${NC}"
    else
        echo "❌ Failed to start Prometheus exporter. Check /tmp/prometheus_exporter.log"
        exit 1
    fi
fi

echo ""
echo "Test metrics endpoint:"
curl -s http://localhost:$PROMETHEUS_PORT/metrics | grep -c "skill_invocations_total" || echo "Warning: No metrics found"
echo ""

# ============================================================================
# Step 3: Start WebSocket Server
# ============================================================================

echo -e "${YELLOW}Step 3: Starting WebSocket Server${NC}"
echo "---------------------------------------"

# Check if already running
if lsof -i :$WEBSOCKET_PORT > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  WebSocket server already running on port $WEBSOCKET_PORT${NC}"
else
    echo "Starting WebSocket server in background..."
    cd "$SESSION_BUDDY_ROOT"
    nohup python examples/run_websocket_server.py > /tmp/websocket_server.log 2>&1 &
    WS_PID=$!
    echo "Started WebSocket server (PID: $WS_PID)"
    sleep 2

    if lsof -i :$WEBSOCKET_PORT > /dev/null 2>&1; then
        echo -e "${GREEN}✓ WebSocket server running on port $WEBSOCKET_PORT${NC}"
    else
        echo "❌ Failed to start WebSocket server. Check /tmp/websocket_server.log"
        exit 1
    fi
fi

echo ""
echo "WebSocket endpoint: ws://localhost:$WEBSOCKET_PORT"
echo ""

# ============================================================================
# Step 4: Setup Grafana Dashboard
# ============================================================================

echo -e "${YELLOW}Step 4: Setting up Grafana Dashboard${NC}"
echo "--------------------------------------------"

bash "$SESSION_BUDDY_ROOT/scripts/setup_grafana_dashboard.sh"
echo ""

# ============================================================================
# Step 5: Verify Services
# ============================================================================

echo -e "${YELLOW}Step 5: Verifying Services${NC}"
echo "---------------------------"

echo "Checking all services..."
SERVICES_OK=true

# Check Prometheus exporter
if curl -s http://localhost:$PROMETHEUS_PORT/metrics | grep -q "skill_invocations_total"; then
    echo -e "${GREEN}✓ Prometheus exporter: OK${NC}"
else
    echo -e "${YELLOW}⚠️  Prometheus exporter: No metrics available${NC}"
    SERVICES_OK=false
fi

# Check WebSocket server
if lsof -i :$WEBSOCKET_PORT > /dev/null 2>&1; then
    echo -e "${GREEN}✓ WebSocket server: Running${NC}"
else
    echo -e "${RED}✗ WebSocket server: NOT RUNNING${NC}"
    SERVICES_OK=false
fi

# Check Session-Buddy MCP server
if pgrep -f "session-buddy" > /dev/null; then
    echo -e "${GREEN}✓ Session-Buddy MCP: Running${NC}"
else
    echo -e "${RED}✗ Session-Buddy MCP: NOT RUNNING${NC}"
    SERVICES_OK=false
fi

echo ""

# ============================================================================
# Step 6: Test Phase 4 MCP Tools
# ============================================================================

echo -e "${YELLOW}Step 6: Testing Phase 4 MCP Tools${NC}"
echo "-----------------------------------"

cd "$SESSION_BUDDY_ROOT"
python3 << 'EOF'
import asyncio
import sys
sys.path.insert(0, '.')

from session_buddy.mcp.tools.skills.phase4_tools import (
    get_real_time_metrics,
    detect_anomalies,
    get_community_baselines
)

async def test_tools():
    print("Testing Phase 4 MCP tools...")

    # Test 1: Real-time metrics
    result = await get_real_time_metrics(limit=5)
    if result.get("success"):
        print(f"✓ Real-time metrics: OK (found {len(result.get('top_skills', []))} skills)")
    else:
        print(f"✗ Real-time metrics: FAILED ({result.get('message')})")

    # Test 2: Anomaly detection
    result = await detect_anomalies(threshold=2.0)
    if result.get("success"):
        print(f"✓ Anomaly detection: OK (found {len(result.get('anomalies', []))} anomalies)")
    else:
        print(f"✗ Anomaly detection: FAILED ({result.get('message')})")

    # Test 3: Community baselines
    result = await get_community_baselines(limit=5)
    if result.get("success"):
        print(f"✓ Community baselines: OK (found {len(result.get('baselines', []))} baselines)")
    else:
        print(f"✗ Community baselines: FAILED ({result.get('message')})")

    print("\n✅ All Phase 4 MCP tools tested")

asyncio.run(test_tools())
EOF

echo ""

# ============================================================================
# Summary
# ============================================================================

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 Production Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo "Services Running:"
echo "  • Prometheus Metrics: http://localhost:$PROMETHEUS_PORT/metrics"
echo "  • WebSocket Server: ws://localhost:$WEBSOCKET_PORT"
echo "  • Session-Buddy MCP: Running (check your MCP client)"
echo ""

echo "Grafana Dashboard:"
echo "  • Open: http://localhost:3000"
echo "  • Navigate to: Search → \"Session-Buddy Phase 4\""
echo "  • Set time range: Last 1 hour / Last 6 hours"
echo ""

echo "Logs:"
echo "  • Prometheus: tail -f /tmp/prometheus_exporter.log"
echo "  • WebSocket: tail -f /tmp/websocket_server.log"
echo ""

echo "Service Management:"
echo "  • Stop Prometheus: kill $(lsof -ti :$PROMETHEUS_PORT)"
echo "  • Stop WebSocket: kill $(lsof -ti :$WEBSOCKET_PORT)"
echo "  • Restart all: Re-run this script"
echo ""

echo "Monitoring Quick Start:"
echo "  1. Open Grafana dashboard"
echo "  2. Monitor skill invocations in real-time"
echo "  3. Check anomaly detection alerts"
echo "  4. Review system health indicators"
echo ""

if [ "$SERVICES_OK" = true ]; then
    echo -e "${GREEN}✅ All services operational!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some services need attention${NC}"
    exit 1
fi
