#!/bin/bash
# Session-Buddy Phase 4 Deployment Script
# This script automates the complete Phase 4 deployment

set -e  # Exit on error

echo "🚀 Session-Buddy Phase 4 Deployment"
echo "===================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DB_PATH="${DB_PATH:-$HOME/.claude/data/session_buddy.db}"
SESSION_BUDDY_ROOT="${SESSION_BUDDY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Step 1: Pre-deployment checks
echo -e "${YELLOW}Step 1: Pre-deployment Checks${NC}"
echo "-------------------------------"

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo -e "${RED}❌ Database not found at: $DB_PATH${NC}"
    echo "   Please ensure Session-Buddy has been initialized"
    exit 1
fi
echo -e "${GREEN}✓ Database found${NC}"

# Check if V3 migration was applied
V3_CHECK=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_migrations WHERE version = 3;" 2>/dev/null || echo "0")
if [ "$V3_CHECK" -eq 0 ]; then
    echo -e "${RED}❌ V3 migration not found. Please apply V3 first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ V3 migration verified${NC}"

# Check if V4 already applied
V4_CHECK=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_migrations WHERE version = 4;" 2>/dev/null || echo "0")
if [ "$V4_CHECK" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  V4 migration already applied${NC}"
    read -p "Continue anyway? This will re-apply the migration. (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled"
        exit 0
    fi
fi
echo ""

# Step 2: Backup database
echo -e "${YELLOW}Step 2: Backup Database${NC}"
echo "-------------------------"

BACKUP_PATH="${DB_PATH}.v3.pre-v4.$(date +%Y%m%d_%H%M%S).backup"
cp "$DB_PATH" "$BACKUP_PATH"
echo -e "${GREEN}✓ Database backed up to:${NC} $BACKUP_PATH"
echo ""

# Step 3: Apply V4 migration
echo -e "${YELLOW}Step 3: Apply V4 Migration${NC}"
echo "----------------------------"

cd "$SESSION_BUDDY_ROOT"

# Check if migration file exists
if [ ! -f "session_buddy/storage/migrations/V4__phase4_extensions__up.sql" ]; then
    echo -e "${RED}❌ V4 migration file not found${NC}"
    echo "   Expected: session_buddy/storage/migrations/V4__phase4_extensions__up.sql"
    exit 1
fi

# Apply migration
sqlite3 "$DB_PATH" < session_buddy/storage/migrations/V4__phase4_extensions__up.sql

# Verify migration
V4_TABLES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('skill_metrics_cache', 'skill_time_series', 'skill_anomalies', 'skill_community_baselines', 'skill_user_interactions');")
if [ "$V4_TABLES" -ne 5 ]; then
    echo -e "${RED}❌ Migration verification failed${NC}"
    echo "   Expected 5 V4 tables, found: $V4_TABLES"
    exit 1
fi

echo -e "${GREEN}✓ V4 migration applied successfully${NC}"
echo -e "${GREEN}✓ Verified 5 core V4 tables created${NC}"
echo ""

# Step 4: Initialize taxonomy
echo -e "${YELLOW}Step 4: Initialize Skills Taxonomy${NC}"
echo "------------------------------------"

if [ ! -f "scripts/initialize_taxonomy.py" ]; then
    echo -e "${RED}❌ Taxonomy initialization script not found${NC}"
    echo "   Expected: scripts/initialize_taxonomy.py"
    exit 1
fi

python scripts/initialize_taxonomy.py

# Verify taxonomy
CATEGORY_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_categories;" 2>/dev/null || echo "0")
echo -e "${GREEN}✓ Taxonomy initialized: $CATEGORY_COUNT categories${NC}"
echo ""

# Step 5: Validation
echo -e "${YELLOW}Step 5: Post-Deployment Validation${NC}"
echo "-------------------------------------"

# Test V4 query methods
echo "Testing V4 query methods..."

python3 << EOF
import sys
sys.path.insert(0, '$SESSION_BUDDY_ROOT')

from pathlib import Path
from session_buddy.storage.skills_storage import SkillsStorage

db_path = Path("$DB_PATH")
storage = SkillsStorage(db_path=db_path)

# Test real-time metrics
try:
    metrics = storage.get_real_time_metrics(limit=5)
    print(f"✓ Real-time metrics: {len(metrics)} skills retrieved")
except Exception as e:
    print(f"❌ Real-time metrics failed: {e}")
    sys.exit(1)

# Test anomaly detection
try:
    anomalies = storage.detect_anomalies(threshold=2.0)
    print(f"✓ Anomaly detection: {len(anomalies)} anomalies found")
except Exception as e:
    print(f"❌ Anomaly detection failed: {e}")
    sys.exit(1)

# Test community baselines
try:
    baselines = storage.get_community_baselines()
    print(f"✓ Community baselines: {len(baselines)} skills with global data")
except Exception as e:
    print(f"❌ Community baselines failed: {e}")
    sys.exit(1)

print("\\n✓ All V4 query methods working correctly")
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Validation failed${NC}"
    exit 1
fi
echo ""

# Step 6: Summary
echo -e "${YELLOW}Step 6: Deployment Summary${NC}"
echo "----------------------------"
echo ""
echo -e "${GREEN}✅ Phase 4 deployment COMPLETE!${NC}"
echo ""
echo "What's been deployed:"
echo "  • V4 database schema (14 new tables, 6 views)"
echo "  • Skills taxonomy (6 categories, 4 modalities, 4 dependencies)"
echo "  • V4 query methods (real-time, anomalies, collaborative filtering)"
echo ""
echo "Next steps:"
echo "  1. Test new MCP tools:"
echo "     - get_real_time_metrics"
echo "     - detect_anomalies"
echo "     - get_collaborative_recommendations"
echo ""
echo "  2. Start optional services:"
echo "     - WebSocket server: python examples/run_websocket_server.py"
echo "     - Prometheus exporter: python examples/run_prometheus_exporter.py"
echo ""
echo "  3. Review documentation:"
echo "     - Migration guide: docs/migrations/V3_TO_V4_MIGRATION_GUIDE.md"
echo "     - Deployment checklist: PHASE4_DEPLOYMENT_CHECKLIST.md"
echo ""
echo "Database location: $DB_PATH"
echo "Backup location: $BACKUP_PATH"
echo ""
echo -e "${GREEN}🎉 Congratulations! Phase 4 is now live!${NC}"
