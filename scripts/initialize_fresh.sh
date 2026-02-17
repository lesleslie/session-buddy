#!/bin/bash
# Session-Buddy Complete Initialization Script
# Initializes a fresh database with all migrations (V1 through V4)

set -e

echo "🚀 Session-Buddy Complete Initialization"
echo "======================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
DB_PATH="${DB_PATH:-.session-buddy/skills.db}"
SESSION_BUDDY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Create database directory
mkdir -p "$(dirname "$DB_PATH")"

# Step 1: Initialize V1 schema
echo -e "${YELLOW}Step 1: Initialize V1 Schema${NC}"
echo "-------------------------------"

cd "$SESSION_BUDDY_ROOT"

if [ ! -f "session_buddy/storage/migrations/V1__initial_schema__up.sql" ]; then
    echo "❌ V1 migration file not found"
    exit 1
fi

sqlite3 "$DB_PATH" < session_buddy/storage/migrations/V1__initial_schema__up.sql
echo -e "${GREEN}✓ V1 schema initialized${NC}"
echo ""

# Step 2: Apply V2 (Semantic Search)
echo -e "${YELLOW}Step 2: Apply V2 Migration (Semantic Search)${NC}"
echo "------------------------------------------------------"

if [ ! -f "session_buddy/storage/migrations/V2__add_semantic_search__up.sql" ]; then
    echo "❌ V2 migration file not found"
    exit 1
fi

sqlite3 "$DB_PATH" < session_buddy/storage/migrations/V2__add_semantic_search__up.sql
echo -e "${GREEN}✓ V2 migration applied (semantic search)${NC}"
echo ""

# Step 3: Apply V3 (Workflow Correlation)
echo -e "${YELLOW}Step 3: Apply V3 Migration (Workflow Correlation)${NC}"
echo "--------------------------------------------------------"

if [ ! -f "session_buddy/storage/migrations/V3__add_workflow_correlation__up.sql" ]; then
    echo "❌ V3 migration file not found"
    exit 1
fi

sqlite3 "$DB_PATH" < session_buddy/storage/migrations/V3__add_workflow_correlation__up.sql
echo -e "${GREEN}✓ V3 migration applied (workflow correlation)${NC}"
echo ""

# Step 4: Apply V4 (Phase 4 Analytics)
echo -e "${YELLOW}Step 4: Apply V4 Migration (Phase 4 Analytics)${NC}"
echo "------------------------------------------------------"

if [ ! -f "session_buddy/storage/migrations/V4__phase4_extensions__up.sql" ]; then
    echo "❌ V4 migration file not found"
    exit 1
fi

sqlite3 "$DB_PATH" < session_buddy/storage/migrations/V4__phase4_extensions__up.sql

# Verify V4
V4_TABLES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('skill_metrics_cache', 'skill_time_series', 'skill_anomalies', 'skill_community_baselines', 'skill_user_interactions');")
if [ "$V4_TABLES" -ne 5 ]; then
    echo "❌ V4 migration verification failed"
    exit 1
fi

echo -e "${GREEN}✓ V4 migration applied (Phase 4 analytics)${NC}"
echo ""

# Step 5: Initialize Taxonomy
echo -e "${YELLOW}Step 5: Initialize Skills Taxonomy${NC}"
echo "------------------------------------"

if [ ! -f "scripts/initialize_taxonomy.py" ]; then
    echo "❌ Taxonomy initialization script not found"
    exit 1
fi

python scripts/initialize_taxonomy.py

CATEGORY_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_categories;" 2>/dev/null || echo "0")
echo -e "${GREEN}✓ Taxonomy initialized: $CATEGORY_COUNT categories${NC}"
echo ""

# Step 6: Validation
echo -e "${YELLOW}Step 6: Validation${NC}"
echo "---------------------"

python3 << EOF
import sys
sys.path.insert(0, '$SESSION_BUDDY_ROOT')

from pathlib import Path
from session_buddy.storage.skills_storage import SkillsStorage

db_path = Path("$DB_PATH")
storage = SkillsStorage(db_path=db_path)

print("Testing V4 features...")

# Test basic operations
session_id = storage.create_session(project_path="/test/project")
print(f"✓ Session created: {session_id}")

# Test V4 query methods
metrics = storage.get_real_time_metrics(limit=5)
print(f"✓ Real-time metrics: {len(metrics)} skills")

anomalies = storage.detect_anomalies(threshold=2.0)
print(f"✓ Anomaly detection: {len(anomalies)} anomalies")

baselines = storage.get_community_baselines()
print(f"✓ Community baselines: {len(baselines)} skills")

print("\n✅ All features validated!")
EOF

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 Initialization Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Database: $DB_PATH"
echo ""
echo "What's been set up:"
echo "  • V1: Core schema (sessions, invocations, metrics)"
echo "  • V2: Semantic search (embeddings, similarity)"
echo "  • V3: Workflow correlation (phases, steps)"
echo "  • V4: Advanced analytics (real-time, predictions, collaborative filtering)"
echo "  • Taxonomy: 6 categories, 4 modalities, 4 dependencies"
echo ""
echo "Next steps:"
echo "  1. Start using Session-Buddy MCP tools"
echo "  2. Test Phase 4 features (real-time monitoring, analytics)"
echo "  3. Review documentation:"
echo "     - docs/migrations/V3_TO_V4_MIGRATION_GUIDE.md"
echo "     - PHASE4_COMPLETE.md"
