#!/bin/bash
# Session-Buddy Phase 4 Grafana Dashboard Setup
# Automatically imports the Phase 4 skills analytics dashboard

set -e

echo "🎨 Session-Buddy Phase 4 Grafana Dashboard Setup"
echo "================================================"
echo ""

# Configuration
GRAFANA_HOST="${GRAFANA_HOST:-localhost}"
GRAFANA_PORT="${GRAFANA_PORT:-3030}"
GRAFANA_URL="http://${GRAFANA_HOST}:${GRAFANA_PORT}"
DASHBOARD_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docs/grafana/phase4-skills-dashboard.json"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if Grafana is running
echo -e "${YELLOW}Checking Grafana installation...${NC}"
if ! command -v grafana-cli &> /dev/null; then
    echo "❌ grafana-cli not found. Please install Grafana:"
    echo "   brew install grafana"
    exit 1
fi
echo -e "${GREEN}✓ Grafana installed${NC}"
echo ""

# Check if Grafana server is running
echo -e "${YELLOW}Checking Grafana server...${NC}"
if ! curl -s "${GRAFANA_URL}/api/health" > /dev/null 2>&1; then
    echo "❌ Grafana server not accessible at ${GRAFANA_URL}"
    echo "   Start Grafana with: brew services start grafana"
    exit 1
fi
echo -e "${GREEN}✓ Grafana server running at ${GRAFANA_URL}${NC}"
echo ""

# Check if dashboard file exists
echo -e "${YELLOW}Checking dashboard file...${NC}"
if [ ! -f "$DASHBOARD_FILE" ]; then
    echo "❌ Dashboard file not found: $DASHBOARD_FILE"
    exit 1
fi
echo -e "${GREEN}✓ Dashboard file found${NC}"
echo ""

# Check if Prometheus datasource exists
echo -e "${YELLOW}Checking Prometheus datasource...${NC}"
DATASOURCE_CHECK=$(curl -s "${GRAFANA_URL}/api/datasources" | grep -c '"name":"Prometheus"' || true)
if [ "$DATASOURCE_CHECK" -eq 0 ]; then
    echo "⚠️  Prometheus datasource not found. Creating..."
    curl -s -X POST "${GRAFANA_URL}/api/datasources" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "Prometheus",
            "type": "prometheus",
            "url": "http://localhost:9090",
            "access": "proxy",
            "isDefault": true
        }' > /dev/null
    echo -e "${GREEN}✓ Prometheus datasource created${NC}"
else
    echo -e "${GREEN}✓ Prometheus datasource exists${NC}"
fi
echo ""

# Import dashboard
echo -e "${YELLOW}Importing Phase 4 dashboard...${NC}"
DASHBOARD_UID=$(jq -r '.uid' "$DASHBOARD_FILE")
DASHBOARD_TITLE=$(jq -r '.title' "$DASHBOARD_FILE")

# Check if dashboard already exists
EXISTING_DASH=$(curl -s "${GRAFANA_URL}/api/search?query=${DASHBOARD_UID}" | jq -r '.[0].uid // empty' 2>/dev/null || echo "empty")

if [ "$EXISTING_DASH"" != "$DASHBOARD_UID" ]; then
    # Create new dashboard
    echo "Creating new dashboard: $DASHBOARD_TITLE"
    TMP_JSON=$(mktemp)
    jq -n "{dashboard: ., overwrite: false, message: \"Imported via setup script\"}" "$DASHBOARD_FILE" > "$TMP_JSON"
    curl -s -X POST "${GRAFANA_URL}/api/dashboards/db" \
        -H "Content-Type: application/json" \
        -d @"$TMP_JSON" > /dev/null
    rm -f "$TMP_JSON"
    echo -e "${GREEN}✓ Dashboard created successfully${NC}"
else
    # Update existing dashboard
    echo "Dashboard already exists. Updating..."
    TMP_JSON=$(mktemp)
    jq -n "{dashboard: ., overwrite: true, message: \"Updated via setup script\"}" "$DASHBOARD_FILE" > "$TMP_JSON"
    curl -s -X POST "${GRAFANA_URL}/api/dashboards/db" \
        -H "Content-Type: application/json" \
        -d @"$TMP_JSON" > /dev/null
    rm -f "$TMP_JSON"
    echo -e "${GREEN}✓ Dashboard updated successfully${NC}"
fi
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 Grafana Dashboard Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Dashboard Details:"
echo "  Name: $DASHBOARD_TITLE"
echo "  UID: $DASHBOARD_UID"
echo "  URL: ${GRAFANA_URL}/d/${DASHBOARD_UID}"
echo ""
echo "What's included:"
echo "  • Skill invocation rates (per minute)"
echo "  • Completion rate gauges with thresholds"
echo "  • Duration percentiles (p50, p95, p99)"
echo "  • Anomaly detection monitoring"
echo "  • System health indicators"
echo ""
echo "🔗 Dashboard URL: ${GRAFANA_URL}/d/${DASHBOARD_UID}"
echo ""
echo "Next steps:"
echo "  1. Open Grafana: ${GRAFANA_URL}"
echo "  2. Navigate to: Search → \"Session-Buddy Phase 4\""
echo "  3. Set time range to \"Last 1 hour\" or \"Last 6 hours\""
echo "  4. Verify metrics are appearing"
echo ""
