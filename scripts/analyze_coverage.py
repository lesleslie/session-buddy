#!/usr/bin/env python3
"""Analyze coverage.json to produce a summary report."""

import json
from pathlib import Path


def analyze_coverage(coverage_file: Path) -> dict:
    """Analyze coverage.json file and produce summary."""
    with open(coverage_file) as f:
        data = json.load(f)

    # Get overall totals
    totals = data.get("totals", {})

    # Get file-level coverage
    files = data.get("files", {})

    # Calculate coverage by module
    module_coverage = {}

    for file_path, file_data in files.items():
        # Convert to Path to parse
        path = Path(file_path)

        # Get the module (first directory after session_buddy/)
        parts = path.parts
        if "session_buddy" in parts:
            idx = parts.index("session_buddy")
            if idx + 1 < len(parts):
                module = parts[idx + 1]
            else:
                module = "root"
        else:
            continue

        if module not in module_coverage:
            module_coverage[module] = {
                "files": [],
                "total_lines": 0,
                "covered_lines": 0,
            }

        summary = file_data.get("summary", {})
        total_lines = summary.get("num_statements", 0)
        covered_lines = summary.get("covered_lines", 0)

        module_coverage[module]["files"].append(file_path)
        module_coverage[module]["total_lines"] += total_lines
        module_coverage[module]["covered_lines"] += covered_lines

    # Calculate percentages
    for module, data in module_coverage.items():
        if data["total_lines"] > 0:
            data["percent_covered"] = data["covered_lines"] / data["total_lines"] * 100
        else:
            data["percent_covered"] = 0.0

    return {
        "totals": totals,
        "module_coverage": module_coverage,
        "num_files": len(files),
    }


def main():
    """Main function."""
    coverage_file = Path("coverage.json")

    if not coverage_file.exists():
        print(f"Coverage file not found: {coverage_file}")
        print("Run: pytest --cov=session_buddy --cov-report=json")
        return

    analysis = analyze_coverage(coverage_file)

    print("\n" + "=" * 80)
    print("SESSION-BUDDY TEST COVERAGE REPORT")
    print("=" * 80)

    # Overall coverage
    totals = analysis["totals"]
    print("\nOVERALL COVERAGE:")
    print(f"  Files: {analysis['num_files']}")
    print(f"  Statements: {totals.get('num_statements', 0)}")
    print(f"  Missing: {totals.get('missing_lines', 0)}")
    print(f"  Coverage: {totals.get('percent_covered', 0):.1f}%")

    # Module coverage
    print("\nMODULE COVERAGE:")
    print("-" * 80)

    # Sort by coverage (ascending to show lowest first)
    modules = sorted(
        analysis["module_coverage"].items(),
        key=lambda x: x[1]["percent_covered"],
    )

    for module, data in modules:
        coverage_str = f"{data['percent_covered']:.1f}%"
        files_count = len(data["files"])

        # Color code by coverage level
        if data["percent_covered"] < 40:
            status = "CRITICAL"
        elif data["percent_covered"] < 60:
            status = "LOW"
        elif data["percent_covered"] < 80:
            status = "MEDIUM"
        else:
            status = "GOOD"

        print(f"  {module:30s} {coverage_str:>8s}  ({files_count:2d} files) [{status}]")

    # Show lowest coverage modules
    print("\nLOWEST COVERAGE MODULES (Priority for testing):")
    print("-" * 80)

    low_coverage = [m for m in modules if m[1]["percent_covered"] < 60]
    for module, data in low_coverage[:10]:
        print(f"  {module:30s} {data['percent_covered']:>6.1f}%")

    # Show highest coverage modules
    print("\nHIGHEST COVERAGE MODULES:")
    print("-" * 80)

    high_coverage = sorted(
        analysis["module_coverage"].items(),
        key=lambda x: x[1]["percent_covered"],
        reverse=True,
    )

    for module, data in high_coverage[:5]:
        print(f"  {module:30s} {data['percent_covered']:>6.1f}%")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
