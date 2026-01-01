#!/usr/bin/env python3
"""Flexible test runner with optional coverage.

Usage:
    # Run tests without coverage (fast)
    uv run run-tests

    # Run tests with coverage
    uv run run-tests --coverage

    # Run specific test with verbose output
    uv run run-tests tests/unit/test_cli.py -v

    # Run specific test with coverage and HTML report
    uv run run-tests tests/functional/ --coverage --html

    # Pass through any pytest options
    uv run run-tests tests/unit/ --tb=short -x
"""

from __future__ import annotations

import sys


def main() -> int:
    """Run tests with optional coverage."""
    # Parse command line arguments
    argv = sys.argv[1:]

    # Check for our custom flags
    use_coverage = "--coverage" in argv or "-c" in argv
    use_html = "--html" in argv

    # Remove our custom flags from argv
    pytest_args = []
    for arg in argv:
        if arg not in ["--coverage", "-c", "--html"]:
            pytest_args.append(arg)

    # Default test path if none provided
    if not pytest_args:
        pytest_args = ["tests/"]

    # Build pytest command
    if use_coverage:
        # Use coverage.py directly to avoid pytest-cov hanging issue
        import subprocess

        cmd = ["coverage", "run", "-m", "pytest", *pytest_args]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)

        # Show coverage report
        print("\n" + "=" * 60)
        print("Coverage Report:")
        print("=" * 60)
        subprocess.run(["coverage", "report"], check=False)

        # Generate HTML report if requested
        if use_html:
            print("\nGenerating HTML coverage report...")
            subprocess.run(["coverage", "html", "--directory=htmlcov"], check=False)
            print("HTML report generated: htmlcov/index.html")

        return result.returncode

    # Run pytest without coverage (fast)
    import pytest

    return pytest.main(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
