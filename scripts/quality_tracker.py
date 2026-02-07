#!/usr/bin/env python3
"""Quality score tracker and automated monitoring script.

Tracks project quality metrics over time and provides recommendations
for maintaining high code quality standards.

Usage:
    python scripts/quality_tracker.py              # Full analysis
    python scripts/quality_tracker.py --quick      # Quick check
    python scripts/quality_tracker.py --history     # Show trends
"""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path


class QualityTracker:
    """Track and analyze project quality metrics."""

    def __init__(self, project_dir: Path = None):
        """Initialize quality tracker.

        Args:
            project_dir: Project directory to analyze
        """
        self.project_dir = project_dir or Path.cwd()
        self.metrics = {}

    def run_command(self, cmd: list[str]) -> tuple[int, str, str]:
        """Run command and return exit code, stdout, stderr."""
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_dir
        )
        return result.returncode, result.stdout, result.stderr

    def check_test_coverage(self) -> dict:
        """Check test coverage using pytest."""
        print("🔍 Checking test coverage...")

        returncode, stdout, stderr = self.run_command(
            [
                "python",
                "-m",
                "pytest",
                "--cov=session_buddy",
                "--cov-report=json",
                "--cov-report=term-missing",
                "-q",
            ]
        )

        if returncode != 0:
            return {"coverage_pct": 0, "error": stderr}

        # Parse coverage from JSON report
        try:
            cov_file = self.project_dir / ".coverage.json"
            if cov_file.exists():
                data = json.loads(cov_file.read_text())
                total_coverage = data.get("totals", {}).get("percent_covered", 0)
                return {"coverage_pct": round(total_coverage, 1)}
        except Exception as e:
            return {"coverage_pct": 0, "error": str(e)}

        # Fallback: parse from terminal output
        for line in stdout.split("\n"):
            if "TOTAL" in line and "%" in line:
                try:
                    pct = float(line.split()[-1].replace("%", ""))
                    return {"coverage_pct": pct}
                except ValueError:
                    pass

        return {"coverage_pct": 0}

    def check_code_quality(self) -> dict:
        """Check code quality using crackerjack."""
        print("🔍 Checking code quality...")

        returncode, stdout, stderr = self.run_command(
            ["python", "-m", "crackerjack", "lint"]
        )

        has_errors = returncode != 0

        # Count issues
        error_count = stdout.count("error") + stderr.count("error")
        warning_count = stdout.count("warning") + stderr.count("warning")

        return {
            "has_issues": has_errors,
            "error_count": error_count,
            "warning_count": warning_count,
        }

    def check_type_hints(self) -> dict:
        """Estimate type hint coverage."""
        print("🔍 Analyzing type hint coverage...")

        py_files = list(self.project_dir.rglob("session_buddy/*.py"))
        total_funcs = 0
        typed_funcs = 0

        for file in py_files:
            try:
                content = file.read_text()
                # Count function definitions
                import re

                funcs = len(re.findall(r"def \w+", content))
                # Count with return type hints
                hints = len(re.findall(r"def \w+\([^)]*\) ->", content))
                total_funcs += funcs
                typed_funcs += hints
            except Exception:
                pass

        coverage = (typed_funcs / total_funcs * 100) if total_funcs > 0 else 0

        return {
            "total_functions": total_funcs,
            "typed_functions": typed_funcs,
            "coverage_pct": round(coverage, 1),
        }

    def check_security_tests(self) -> dict:
        """Count security tests."""
        print("🔍 Counting security tests...")

        security_dir = self.project_dir / "tests" / "security"
        if not security_dir.exists():
            return {"test_count": 0}

        test_files = list(security_dir.glob("test_*.py"))
        total_tests = 0

        for test_file in test_files:
            try:
                content = test_file.read_text()
                total_tests += content.count("def test_")
            except Exception:
                pass

        return {"test_count": total_tests}

    def calculate_quality_score(self) -> dict:
        """Calculate overall quality score (0-100)."""
        print("\n📊 Calculating quality score...\n")

        # Gather metrics
        coverage = self.check_test_coverage()
        quality = self.check_code_quality()
        type_hints = self.check_type_hints()
        security = self.check_security_tests()

        # Calculate score components
        coverage_score = min(coverage["coverage_pct"], 100)
        type_hint_score = type_hints["coverage_pct"]
        quality_score = (
            100
            if not quality["has_issues"]
            else max(0, 100 - quality["error_count"] * 5 - quality["warning_count"])
        )
        security_score = min(security["test_count"] * 2, 100)  # 50+ tests = 100

        # Overall score (weighted average)
        weights = {
            "coverage": 0.30,
            "quality": 0.25,
            "type_hints": 0.25,
            "security": 0.20,
        }

        overall = (
            coverage_score * weights["coverage"]
            + quality_score * weights["quality"]
            + type_hint_score * weights["type_hints"]
            + security_score * weights["security"]
        )

        return {
            "overall": round(overall, 1),
            "coverage": round(coverage_score, 1),
            "quality": round(quality_score, 1),
            "type_hints": round(type_hint_score, 1),
            "security": round(security_score, 1),
            "metrics": {
                "coverage": coverage,
                "quality": quality,
                "type_hints": type_hints,
                "security": security,
            },
        }

    def print_score(self, score: dict):
        """Print quality score with visual indicators."""
        print("=" * 70)
        print("PROJECT QUALITY SCORE")
        print("=" * 70)

        overall = score["overall"]
        emoji = (
            "🌟"
            if overall >= 90
            else "✅"
            if overall >= 75
            else "⚠️"
            if overall >= 60
            else "❌"
        )

        print(f"\n{emoji} Overall Score: {overall}/100")
        print("-" * 70)

        components = [
            ("Test Coverage", score["coverage"], score["metrics"]["coverage"]),
            ("Code Quality", score["quality"], score["metrics"]["quality"]),
            ("Type Hints", score["type_hints"], score["metrics"]["type_hints"]),
            ("Security Tests", score["security"], score["metrics"]["security"]),
        ]

        for name, value, metrics in components:
            emoji = (
                "⭐"
                if value >= 90
                else "✓"
                if value >= 75
                else "~"
                if value >= 60
                else "✗"
            )
            print(f"{emoji} {name:<20} {value:>3}/100")

            # Add details
            if name == "Test Coverage":
                print(f"   └─ Coverage: {metrics.get('coverage_pct', 0):.1f}%")
            elif name == "Code Quality":
                if not metrics.get("has_issues"):
                    print("   └─ No issues detected")
                else:
                    print(
                        f"   └─ {metrics.get('error_count', 0)} errors, {metrics.get('warning_count', 0)} warnings"
                    )
            elif name == "Type Hints":
                print(
                    f"   └─ {metrics.get('typed_functions', 0)}/{metrics.get('total_functions', 0)} functions typed"
                )
            elif name == "Security Tests":
                print(f"   └─ {metrics.get('test_count', 0)} security tests")

        print("\n" + "=" * 70)

        # Recommendations
        if overall < 90:
            print("\n💡 Recommendations:")
            if score["coverage"] < 90:
                print("   • Add tests to increase coverage above 90%")
            if score["quality"] < 90:
                print("   • Fix crackerjack lint issues")
            if score["type_hints"] < 95:
                print("   • Add type hints to functions")
            if score["security"] < 80:
                print("   • Add more security tests")

        print()

    def save_score(self, score: dict):
        """Save score to history file."""
        history_file = self.project_dir / ".quality_history.json"

        try:
            if history_file.exists():
                history = json.loads(history_file.read_text())
            else:
                history = []

            entry = {"timestamp": datetime.now().isoformat(), "score": score}
            history.append(entry)

            # Keep last 100 entries
            history = history[-100:]

            history_file.write_text(json.dumps(history, indent=2))
        except Exception as e:
            print(f"⚠️  Could not save history: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Track project quality metrics")
    parser.add_argument(
        "--quick", action="store_true", help="Quick check without detailed output"
    )
    parser.add_argument(
        "--history", action="store_true", help="Show quality trends over time"
    )
    parser.add_argument(
        "--project-dir", type=Path, default=None, help="Project directory"
    )

    args = parser.parse_args()

    tracker = QualityTracker(args.project_dir)

    if args.history:
        # Show historical trends
        history_file = tracker.project_dir / ".quality_history.json"
        if history_file.exists():
            history = json.loads(history_file.read_text())
            print("\n📈 Quality Score History (last 10 entries):\n")
            for entry in history[-10:]:
                timestamp = entry["timestamp"][:19]
                score = entry["score"]["overall"]
                print(f"  {timestamp}: {score}/100")
        else:
            print("No history available yet")
        return

    # Calculate current score
    start = time.time()
    score = tracker.calculate_quality_score()
    elapsed = time.time() - start

    if not args.quick:
        tracker.print_score(score)
        tracker.save_score(score)
        print(f"⏱️  Analysis completed in {elapsed:.1f} seconds")
    else:
        print(f"Quality Score: {score['overall']}/100")


if __name__ == "__main__":
    main()
