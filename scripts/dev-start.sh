#!/usr/bin/env bash
# Session-Buddy Development Startup Script
#
# Usage:
#   ./scripts/dev-start.sh          # Start in standard mode
#   ./scripts/dev-start.sh lite     # Start in lite mode
#   ./scripts/dev-start.sh standard # Start in standard mode
#
# Environment Variables:
#   SESSION_BUDDY_MODE    Set mode (lite, standard)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default mode
MODE=${1:-${SESSION_BUDDY_MODE:-standard}}

# Normalize mode name
MODE=$(echo "$MODE" | tr '[:upper:]' '[:lower:]' | tr '-' '_')

# Validate mode
if [[ "$MODE" != "lite" && "$MODE" != "standard" ]]; then
    echo -e "${RED}Error: Invalid mode '$MODE'${NC}"
    echo "Valid modes: lite, standard"
    exit 1
fi

# Set environment variable
export SESSION_BUDDY_MODE=$MODE

# Print startup message
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          Session-Buddy Development Startup             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$MODE" == "lite" ]]; then
    echo -e "${GREEN}Mode: Lite${NC}"
    echo -e "${YELLOW}⚡  In-memory database (no persistence)${NC}"
    echo -e "${YELLOW}📦 Minimal dependencies${NC}"
    echo -e "${YELLOW}⏱️  Fast startup (< 2 seconds)${NC}"
    echo ""
    echo -e "${RED}⚠️  WARNING: Data will not persist across restarts!${NC}"
else
    echo -e "${GREEN}Mode: Standard${NC}"
    echo -e "${BLUE}💾 Persistent database (~/.claude/data/reflection.duckdb)${NC}"
    echo -e "${BLUE}📦 Full feature set${NC}"
    echo -e "${BLUE}🧠 Semantic search enabled${NC}"
fi

echo ""
echo -e "${BLUE}Starting Session-Buddy...${NC}"
echo ""

# Check if session-buddy is installed
if ! command -v session-buddy &> /dev/null; then
    echo -e "${RED}Error: session-buddy command not found${NC}"
    echo "Please install session-buddy:"
    echo "  uv pip install -e ."
    echo "  # or"
    echo "  pip install -e ."
    exit 1
fi

# Start session-buddy with the new CLI
if [[ -f "session_buddy/cli_with_modes.py" ]]; then
    # Use the new CLI with mode support
    python session_buddy/cli_with_modes.py "$@" start
else
    # Fall back to old CLI
    session-buddy start
fi
