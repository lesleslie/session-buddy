#!/usr/bin/env bash
# Security Audit Script for session-buddy
#
# This script runs pip-audit and documents all vulnerabilities.
# Any accepted vulnerabilities must be documented in SECURITY_AUDIT.md
# with justification.
#
# Usage: ./scripts/security_audit.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "======================================"
echo "Security Audit for session-buddy"
echo "======================================"
echo ""

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]] && [[ -f "$PROJECT_ROOT/.venv/bin/python" ]]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Run pip-audit
echo "Running pip-audit..."
echo ""

# Run without ignoring anything first to see current state
pip-audit --format json 2>&1 | tee "$PROJECT_ROOT/.cache/pip-audit-latest.json"

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "======================================"

# Check for the one known accepted vulnerability
if [ $EXIT_CODE -eq 1 ]; then
    VULN_COUNT=$(pip-audit 2>&1 | grep -c "Name.*Version.*ID" || true)
    echo "Found $VULN_COUNT vulnerability/vulnerabilities"

    # Check if it's the expected (accepted) CVE-2025-53000 in nbconvert
    if pip-audit 2>&1 | grep -q "CVE-2025-53000"; then
        echo ""
        echo "Note: CVE-2025-53000 (nbconvert) is a known, accepted vulnerability."
        echo "See docs/SECURITY_AUDIT_2025-12-31.md for justification."
        echo ""
        echo "Summary:"
        echo "  - Package: nbconvert 7.16.6"
        echo "  - Severity: Medium (Windows-only)"
        echo "  - Risk: ACCEPTED for macOS development"
        echo "  - Fix: None available"
    fi
elif [ $EXIT_CODE -eq 0 ]; then
    echo "No vulnerabilities found!"
else
    echo "Error running pip-audit"
    exit $EXIT_CODE
fi

echo ""
echo "Full report saved to: .cache/pip-audit-latest.json"
echo ""
echo "To re-audit with vulnerability ignored (for CI):"
echo "  pip-audit --ignore-vuln CVE-2025-53000"
