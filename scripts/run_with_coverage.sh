#!/usr/bin/env bash
# Run tests with coverage analysis

set -e

# Run tests with coverage
echo "Running tests with coverage coverage.py (not pytest-cov)..."
coverage run -m pytest tests/ "$@"

# Generate coverage report
echo ""
echo "Coverage Statistics:"
coverage report

# Generate HTML coverage report
echo ""
echo "Generating HTML coverage report..."
coverage html --directory=htmlcov

echo ""
echo "Coverage complete! Open htmlcov/index.html in a browser to view."
