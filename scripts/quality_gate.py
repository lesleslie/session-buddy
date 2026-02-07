#!/usr/bin/env python3
"""Quality gate enforcement for CI/CD.

Enforces quality thresholds before allowing commits or merges.
Use in pre-commit hooks, CI/CD pipelines, or manual checks.

Usage:
    python scripts/quality_gate.py              # Full check
    python scripts/quality_gate.py --ci         # CI mode (machine-readable)
    python scripts/quality_gate.py --minimal    # Quick check only
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Quality thresholds (configurable)
THRESHOLDS = {
    "overall_score": 75,  # Minimum overall quality score (0-100)
    "test_coverage": 85,  # Minimum test coverage percentage
    "type_hints": 95,  # Minimum type hint coverage percentage
    "security_tests": 50,  # Minimum number of security tests
    "max_lint_errors": 10,  # Maximum allowed lint errors
    "max_warnings": 20,  # Maximum allowed warnings
}


class QualityGate:
    """Enforce quality gate thresholds."""

    def __init__(self, project_dir: Path = None, thresholds: dict = None):
        """Initialize quality gate.

        Args:
            project_dir: Project directory to check
            thresholds: Custom thresholds (uses defaults if None)
        """
        self.project_dir = project_dir or Path.cwd()
        self.thresholds = thresholds or THRESHOLDS
        self.failures = []
        self.warnings = []
        self.metrics = {}

    def check_thresholds(self, metrics: dict) -> bool:
        """Check if metrics meet all thresholds.

        Args:
            metrics: Quality metrics dictionary

        Returns:
            True if all thresholds pass
        """
        passed = True

        # Overall score
        overall = metrics.get("overall", 0)
        if overall < self.thresholds["overall_score"]:
            self.failures.append(
                f"Overall score {overall}/100 < {self.thresholds['overall_score']}/100"
            )
            passed = False

        # Test coverage
        coverage = metrics.get("metrics", {}).get("coverage", {}).get("coverage_pct", 0)
        if coverage < self.thresholds["test_coverage"]:
            self.failures.append(
                f"Test coverage {coverage:.1f}% < {self.thresholds['test_coverage']}%"
            )
            passed = False

        # Type hints
        type_hints = (
            metrics.get("metrics", {}).get("type_hints", {}).get("coverage_pct", 0)
        )
        if type_hints < self.thresholds["type_hints"]:
            self.failures.append(
                f"Type hints {type_hints:.1f}% < {self.thresholds['type_hints']}%"
            )
            passed = False

        # Security tests
        security_tests = (
            metrics.get("metrics", {}).get("security", {}).get("test_count", 0)
        )
        if security_tests < self.thresholds["security_tests"]:
            self.warnings.append(
                f"Security tests {security_tests} < {self.thresholds['security_tests']} (recommended)"
            )

        return passed

    def run_quality_check(self) -> dict:
        """Run quality check using quality_tracker.

        Returns:
            Quality metrics dictionary
        """
        # Import quality tracker
        sys.path.insert(0, str(self.project_dir))
        from scripts.quality_tracker import QualityTracker

        tracker = QualityTracker(self.project_dir)
        return tracker.calculate_quality_score()

    def enforce(self) -> bool:
        """Enforce quality gate.

        Returns:
            True if gate passes, False otherwise
        """
        print("🔍 Running quality gate...\n")

        # Run quality check
        self.metrics = self.run_quality_check()

        # Check thresholds
        passed = self.check_thresholds(self.metrics)

        # Print results
        self.print_results()

        # Save to history
        self.save_results()

        return passed

    def print_results(self):
        """Print quality gate results."""
        overall = self.metrics.get("overall", 0)
        emoji = "✅" if overall >= 90 else "⚠️" if overall >= 75 else "❌"

        print(f"{emoji} Quality Score: {overall}/100")
        print("-" * 50)

        if self.failures:
            print("\n❌ Quality Gate Failed:")
            for failure in self.failures:
                print(f"  ✗ {failure}")

        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")

        if not self.failures:
            print("\n✅ All quality gates passed!")

    def save_results(self):
        """Save quality gate results to file."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "passed": len(self.failures) == 0,
            "score": self.metrics,
            "thresholds": self.thresholds,
            "failures": self.failures,
            "warnings": self.warnings,
        }

        results_file = self.project_dir / ".quality_gate_results.json"
        results_file.write_text(json.dumps(results, indent=2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Enforce quality thresholds for CI/CD")
    parser.add_argument(
        "--ci", action="store_true", help="CI mode (machine-readable output)"
    )
    parser.add_argument(
        "--minimal", action="store_true", help="Quick check (skip detailed output)"
    )
    parser.add_argument(
        "--project-dir", type=Path, default=None, help="Project directory"
    )

    args = parser.parse_args()

    gate = QualityGate(args.project_dir)
    passed = gate.enforce()

    if args.ci:
        # Machine-readable output for CI
        print(json.dumps({"passed": passed, "score": gate.metrics["overall"]}))

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
