#!/usr/bin/env python3
"""Compare dead code detection tools: Vulture, deadcode, and Skylos.

This script runs all three tools and provides a side-by-side comparison
of their findings, performance, and recommendations.
"""

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass
class ToolResult:
    """Results from a dead code detection tool."""

    tool_name: str
    duration_ms: float
    exit_code: int
    issues_found: int
    issues: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""
    error_message: str = ""


@dataclass
class ComparisonSummary:
    """Summary comparison of all tools."""

    tools: list[ToolResult] = field(default_factory=list)
    fastest_tool: str = ""
    most_issues: str = ""
    common_findings: list[str] = field(default_factory=list)


def run_vulture(package_path: Path, min_confidence: int = 80) -> ToolResult:
    """Run Vulture dead code detection."""
    console.print("[cyan]🦅 Running Vulture...[/cyan]")

    cmd = [
        "vulture",
        str(package_path),
        "--min-confidence",
        str(min_confidence),
        "--sort-by-size",
    ]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration_ms = (time.time() - start_time) * 1000

        # Parse vulture output
        issues = []
        for line in result.stdout.split("\n"):
            if ":" in line and "unused" in line and "%" in line:
                parts = line.split(":")
                if len(parts) >= 3:
                    try:
                        file_path = parts[0].strip()
                        line_num = parts[1].strip()
                        message = ":".join(parts[2:]).strip()

                        # Extract confidence
                        confidence = 80
                        if "(" in message and "%" in message:
                            conf_str = message.split("(")[1].split("%")[0].strip()
                            confidence = int(conf_str)

                        issues.append(
                            {
                                "file": file_path,
                                "line": line_num,
                                "message": message,
                                "confidence": confidence,
                            }
                        )
                    except (ValueError, IndexError):
                        pass

        return ToolResult(
            tool_name="Vulture",
            duration_ms=duration_ms,
            exit_code=result.returncode,
            issues_found=len(issues),
            issues=issues,
            raw_output=result.stdout,
        )

    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="Vulture",
            duration_ms=duration_ms,
            exit_code=-1,
            issues_found=0,
            error_message="Timeout after 120s",
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="Vulture",
            duration_ms=duration_ms,
            exit_code=-1,
            issues_found=0,
            error_message=str(e),
        )


def run_deadcode(package_path: Path) -> ToolResult:
    """Run deadcode tool."""
    console.print("[cyan]💀 Running deadcode...[/cyan]")

    # First run with --dry-run to see what would be deleted
    cmd = [
        "deadcode",
        str(package_path),
        "--fix",
        "--dry-run",
        "--exclude",
        "tests/",
    ]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration_ms = (time.time() - start_time) * 1000

        # Parse deadcode output
        issues = []
        for line in result.stdout.split("\n"):
            if "Found" in line or "unused" in line:
                issues.append({"message": line.strip()})

        return ToolResult(
            tool_name="deadcode",
            duration_ms=duration_ms,
            exit_code=result.returncode,
            issues_found=len(issues),
            issues=issues,
            raw_output=result.stdout,
        )

    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="deadcode",
            duration_ms=duration_ms,
            exit_code=-1,
            issues_found=0,
            error_message="Timeout after 120s",
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="deadcode",
            duration_ms=duration_ms,
            exit_code=-1,
            issues_found=0,
            error_message=str(e),
        )


def run_skylos(package_path: Path) -> ToolResult:
    """Run Skylos if available via crackerjack."""
    console.print("[cyan]🛡️ Running Skylos...[/cyan]")

    # Try to run skylos directly if installed
    cmd = ["skylos", str(package_path)]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration_ms = (time.time() - start_time) * 1000

        # Parse skylos output
        issues = []
        for line in result.stdout.split("\n"):
            if ":" in line and ("unused" in line or "dead" in line.lower()):
                issues.append({"message": line.strip()})

        return ToolResult(
            tool_name="Skylos",
            duration_ms=duration_ms,
            exit_code=result.returncode,
            issues_found=len(issues),
            issues=issues,
            raw_output=result.stdout,
        )

    except FileNotFoundError:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="Skylos",
            duration_ms=duration_ms,
            exit_code=-2,
            issues_found=0,
            error_message="Skylos not found (install via: pip install skylos)",
        )
    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="Skylos",
            duration_ms=duration_ms,
            exit_code=-1,
            issues_found=0,
            error_message="Timeout after 120s",
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            tool_name="Skylos",
            duration_ms=duration_ms,
            exit_code=-1,
            issues_found=0,
            error_message=str(e),
        )


def display_comparison_table(results: list[ToolResult]) -> None:
    """Display comparison table."""
    table = Table(
        title="🔍 Dead Code Detection Tool Comparison",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Tool", style="cyan", width=12)
    table.add_column("Duration", justify="right", style="green")
    table.add_column("Issues", justify="right", style="yellow")
    table.add_column("Exit Code", justify="right", style="blue")
    table.add_column("Status", style="bold")

    fastest = min(results, key=lambda r: r.duration_ms)
    most_issues = max(results, key=lambda r: r.issues_found)

    for result in results:
        # Status indicator
        if result.error_message:
            status = f"[red]❌ {result.error_message[:40]}[/red]"
        elif result.exit_code == 0:
            status = "[green]✅ Success (no dead code)[/green]"
        else:
            status = f"[yellow]⚠️  Found {result.issues_found} issues[/yellow]"

        # Highlight fastest and most thorough
        tool_name = result.tool_name
        if result == fastest:
            tool_name = f"⚡ {tool_name} (fastest)"
        if result == most_issues and result.issues_found > 0:
            tool_name = f"🎯 {tool_name} (most issues)"

        table.add_row(
            tool_name,
            f"{result.duration_ms:.1f}ms",
            str(result.issues_found),
            str(result.exit_code),
            status,
        )

    console.print(table)
    console.print()


def display_sample_issues(results: list[ToolResult]) -> None:
    """Display sample issues from each tool."""
    for result in results:
        if result.issues and result.issues_found > 0:
            console.print(
                Panel.fit(
                    f"[bold cyan]{result.tool_name}[/bold cyan]\n\n"
                    + "\n".join(
                        f"  • {issue.get('file', '')}:{issue.get('line', '')} {issue.get('message', '')}"
                        for issue in result.issues[:5]
                    ),
                    title=f"Sample Issues (showing 5 of {result.issues_found})",
                    border_style="cyan",
                )
            )
            console.print()


def display_recommendations(results: list[ToolResult]) -> None:
    """Display recommendations based on results."""
    console.print(
        Panel.fit(
            """
[bold green]✨ Recommendations[/bold green]

1. [cyan]Pre-commit (Fast)[/cyan]: Use Vulture with 90% confidence
   → Fast, reliable, catches definite dead code

2. [yellow]Automated Cleanup[/yellow]: Use deadcode with --fix
   → Auto-removes unused code (use with caution!)

3. [blue]Comprehensive Analysis[/blue]: Use Skylos for security + quality
   → Most accurate, includes security scanning

4. [magenta]Workflow[/magenta]:
   • Daily: Vulture (fast check)
   • Weekly: deadcode (cleanup)
   • Monthly: Skylos (comprehensive review)
        """,
            title="💡 Usage Recommendations",
            border_style="green",
        )
    )


def main() -> int:
    """Main comparison function."""
    package_path = Path.cwd() / "session_buddy"

    if not package_path.exists():
        console.print(f"[red]❌ Package path not found: {package_path}[/red]")
        return 1

    console.print(
        Panel.fit(
            f"[bold cyan]Comparing Dead Code Detection Tools[/bold cyan]\n\n"
            f"Package: [yellow]{package_path}[/yellow]\n"
            f"Tools: Vulture, deadcode, Skylos",
            title="🔬 Dead Code Detection Comparison",
            border_style="cyan",
        )
    )
    console.print()

    # Run all tools
    results = [
        run_vulture(package_path, min_confidence=80),
        run_deadcode(package_path),
        run_skylos(package_path),
    ]

    # Display results
    display_comparison_table(results)
    display_sample_issues(results)
    display_recommendations(results)

    # Save detailed results to JSON
    output_file = Path.cwd() / "dead_code_comparison.json"
    comparison_data = {
        "timestamp": time.time(),
        "package_path": str(package_path),
        "results": [
            {
                "tool": r.tool_name,
                "duration_ms": r.duration_ms,
                "exit_code": r.exit_code,
                "issues_found": r.issues_found,
                "issues": r.issues[:20],  # Limit to first 20
                "error": r.error_message,
            }
            for r in results
        ],
    }

    with open(output_file, "w") as f:
        json.dump(comparison_data, f, indent=2)

    console.print(f"[green]✅ Detailed results saved to: {output_file}[/green]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
