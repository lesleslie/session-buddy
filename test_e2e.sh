#!/bin/bash
# Session Tracking End-to-End Integration Test Script

set -e

echo "========================================"
echo "Session Tracking E2E Integration Test"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Test Results
TESTS_PASSED=0
TESTS_FAILED=0

# ========================================================================
# Phase 1: Environment Setup
# ========================================================================

echo "Phase 1: Environment Setup"
echo "----------------------------"

print_info "Checking session-buddy installation..."
if pip show session-buddy &> /dev/null; then
    SESSION_BUDDY_VERSION=$(pip show session-buddy | grep Version | cut -d' ' -f2)
    print_success "session-buddy installed (v${SESSION_BUDDY_VERSION})"
    ((TESTS_PASSED++))
else
    print_error "session-buddy not installed"
    echo "  Run: cd /Users/les/Projects/session-buddy && pip install -e ."
    ((TESTS_FAILED++))
fi

print_info "Checking oneiric installation..."
if pip show oneiric &> /dev/null; then
    ONEIRIC_VERSION=$(pip show oneiric | grep Version | cut -d' ' -f2)
    print_success "oneiric installed (v${ONEIRIC_VERSION})"
    ((TESTS_PASSED++))
else
    print_error "oneiric not installed"
    echo "  Run: cd /Users/les/Projects/oneiric && pip install -e ."
    ((TESTS_FAILED++))
fi

print_info "Checking mahavishnu installation..."
if pip show mahavishnu &> /dev/null; then
    MAHAVISHNU_VERSION=$(pip show mahavishnu | grep Version | cut -d' ' -f2)
    print_success "mahavishnu installed (v${MAHAVISHNU_VERSION})"
    ((TESTS_PASSED++))
else
    print_error "mahavishnu not installed"
    echo "  Run: cd /Users/les/Projects/mahavishnu && pip install -e ."
    ((TESTS_FAILED++))
fi

echo ""

# ========================================================================
# Phase 2: Session-Buddy MCP Server
# ========================================================================

echo "Phase 2: Session-Buddy MCP Server"
echo "----------------------------------"

print_info "Checking if Session-Buddy MCP server is running..."
if lsof -i :8678 &> /dev/null; then
    print_success "Session-Buddy MCP server is running on port 8678"
    ((TESTS_PASSED++))
else
    print_error "Session-Buddy MCP server is NOT running"
    echo "  Starting Session-Buddy MCP server..."

    # Check if session-buddy command is available
    if command -v session-buddy &> /dev/null; then
        print_success "session-buddy command found"

        # Try to start the server
        print_info "Starting Session-Buddy MCP server..."
        cd /Users/les/Projects/session-buddy

        # Generate secret if not set
        if [ -z "$SESSION_BUDDY_SECRET" ]; then
            export SESSION_BUDDY_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
            print_success "Generated SESSION_BUDDY_SECRET"
        fi

        # Start server in background
        session-buddy mcp start > /tmp/session-buddy-mcp.log 2>&1 &
        SERVER_PID=$!

        # Wait for server to start
        sleep 3

        # Check if server started
        if lsof -i :8678 &> /dev/null; then
            print_success "Session-Buddy MCP server started (PID: ${SERVER_PID})"
            ((TESTS_PASSED++))
        else
            print_error "Failed to start Session-Buddy MCP server"
            echo "  Check logs: cat /tmp/session-buddy-mcp.log"
            ((TESTS_FAILED++))
        fi
    else
        print_error "session-buddy command not found"
        echo "  Run: cd /Users/les/Projects/session-buddy && pip install -e ."
        ((TESTS_FAILED++))
    fi
fi

echo ""

# ========================================================================
# Phase 3: Session-Buddy Health Check
# ========================================================================

echo "Phase 3: Session-Buddy Health Check"
echo "------------------------------------"

print_info "Checking Session-Buddy MCP health..."
if command -v session-buddy &> /dev/null; then
    if session-buddy mcp health &> /dev/null; then
        print_success "Session-Buddy MCP health check passed"
        ((TESTS_PASSED++))
    else
        print_error "Session-Buddy MCP health check failed"
        ((TESTS_FAILED++))
    fi
else
    print_error "session-buddy command not found"
    ((TESTS_FAILED++))
fi

echo ""

# ========================================================================
# Phase 4: Mahavishnu Shell Integration Test
# ========================================================================

echo "Phase 4: Mahavishnu Shell Integration"
echo "-------------------------------------"

print_info "Checking if mahavishnu command is available..."
if command -v mahavishnu &> /dev/null || python -m mahavishnu --help &> /dev/null; then
    print_success "mahavishnu command found"
    ((TESTS_PASSED++))

    # Note: We cannot automate the full shell test because it requires
    # interactive input. We'll provide manual test instructions here.
    echo ""
    print_info "Manual Test Required:"
    echo "  1. Run: cd /Users/les/Projects/mahavishnu"
    echo "  2. Run: python -m mahavishnu shell"
    echo "  3. Check banner for 'Session Tracking: ✓ Enabled'"
    echo "  4. Run: exit() to exit shell"
    echo "  5. Run: session-buddy list-sessions --type admin_shell"
    echo "  6. Verify session was recorded"
    echo ""
else
    print_error "mahavishnu command not found"
    echo "  Run: cd /Users/les/Projects/mahavishnu && pip install -e ."
    ((TESTS_FAILED++))
fi

echo ""

# ========================================================================
# Phase 5: Database Verification
# ========================================================================

echo "Phase 5: Database Verification"
echo "------------------------------"

print_info "Checking if sessions can be listed..."
if command -v session-buddy &> /dev/null; then
    # Try to list sessions (this will test database connection)
    if session-buddy list-sessions --type admin_shell &> /dev/null; then
        print_success "Session list query successful"
        ((TESTS_PASSED++))
    else
        print_error "Failed to list sessions"
        ((TESTS_FAILED++))
    fi
else
    print_error "session-buddy command not found"
    ((TESTS_FAILED++))
fi

echo ""

# ========================================================================
# Test Summary
# ========================================================================

echo "========================================"
echo "Test Summary"
echo "========================================"
echo ""
echo "Tests Passed: ${TESTS_PASSED}"
echo "Tests Failed: ${TESTS_FAILED}"
echo "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    print_success "All automated tests passed!"
    echo ""
    echo "Next Steps:"
    echo "  1. Run manual shell integration test (see Phase 4 above)"
    echo "  2. Verify session tracking in database"
    echo "  3. Check session metadata completeness"
    exit 0
else
    print_error "Some tests failed. Please fix and re-run."
    exit 1
fi
