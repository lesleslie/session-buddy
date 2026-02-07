#!/usr/bin/env python3
"""Session Tracking End-to-End Integration Test.

This script tests the complete session tracking flow:
1. Session-Buddy MCP server startup
2. Mahavishnu shell initialization
3. Session start event emission
4. Session end event emission
5. Database verification
"""

import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


# Colors for output
class Colors:
    GREEN = "\033[0;32m"
    RED = "\033[0;31m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}✓ {msg}{Colors.NC}")


def print_error(msg: str) -> None:
    print(f"{Colors.RED}✗ {msg}{Colors.NC}")


def print_info(msg: str) -> None:
    print(f"{Colors.YELLOW}→ {msg}{Colors.NC}")


def print_header(msg: str) -> None:
    print(f"\n{Colors.BLUE}{msg}{Colors.NC}")
    print("=" * len(msg))


def run_command(cmd: list[str], capture: bool = True) -> tuple[bool, str, str]:
    """Run a shell command and return success status and output.

    Args:
        cmd: Command to run as list of strings
        capture: Whether to capture stdout/stderr

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=30,
        )

        success = result.returncode == 0
        return success, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


class SessionTrackingIntegrationTest:
    """Session tracking integration test suite."""

    def __init__(self) -> None:
        self.tests_passed = 0
        self.tests_failed = 0
        self.results: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "phases": {},
            "issues": [],
        }

    def run_all_tests(self) -> int:
        """Run all integration tests.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print_header("Session Tracking E2E Integration Test")
        print(f"Started: {self.results['timestamp']}")

        # Phase 1: Environment Setup
        self._test_environment_setup()

        # Phase 2: Session-Buddy MCP Server
        self._test_session_buddy_server()

        # Phase 3: Mahavishnu Shell
        self._test_mahavishnu_shell()

        # Phase 4: Database Verification
        self._test_database_verification()

        # Print summary
        self._print_summary()

        return 0 if self.tests_failed == 0 else 1

    def _test_environment_setup(self) -> None:
        """Phase 1: Test environment setup."""
        print_header("Phase 1: Environment Setup")

        phase_results = {"tests": []}

        # Check session-buddy
        print_info("Checking session-buddy installation...")
        success, stdout, _ = run_command(["pip", "show", "session-buddy"])
        if success:
            version = self._parse_version(stdout)
            print_success(f"session-buddy installed (v{version})")
            self.tests_passed += 1
            phase_results["tests"].append({"name": "session-buddy", "status": "pass", "version": version})
        else:
            print_error("session-buddy not installed")
            self.tests_failed += 1
            self.results["issues"].append({
                "phase": "environment_setup",
                "issue": "session-buddy not installed",
                "fix": "cd /Users/les/Projects/session-buddy && pip install -e .",
            })
            phase_results["tests"].append({"name": "session-buddy", "status": "fail"})

        # Check oneiric
        print_info("Checking oneiric installation...")
        success, stdout, _ = run_command(["pip", "show", "oneiric"])
        if success:
            version = self._parse_version(stdout)
            print_success(f"oneiric installed (v{version})")
            self.tests_passed += 1
            phase_results["tests"].append({"name": "oneiric", "status": "pass", "version": version})
        else:
            print_error("oneiric not installed")
            self.tests_failed += 1
            self.results["issues"].append({
                "phase": "environment_setup",
                "issue": "oneiric not installed",
                "fix": "cd /Users/les/Projects/oneiric && pip install -e .",
            })
            phase_results["tests"].append({"name": "oneiric", "status": "fail"})

        # Check mahavishnu
        print_info("Checking mahavishnu installation...")
        success, stdout, _ = run_command(["pip", "show", "mahavishnu"])
        if success:
            version = self._parse_version(stdout)
            print_success(f"mahavishnu installed (v{version})")
            self.tests_passed += 1
            phase_results["tests"].append({"name": "mahavishnu", "status": "pass", "version": version})
        else:
            print_error("mahavishnu not installed")
            self.tests_failed += 1
            self.results["issues"].append({
                "phase": "environment_setup",
                "issue": "mahavishnu not installed",
                "fix": "cd /Users/les/Projects/mahavishnu && pip install -e .",
            })
            phase_results["tests"].append({"name": "mahavishnu", "status": "fail"})

        self.results["phases"]["environment_setup"] = phase_results

    def _test_session_buddy_server(self) -> None:
        """Phase 2: Test Session-Buddy MCP server."""
        print_header("Phase 2: Session-Buddy MCP Server")

        phase_results = {"tests": []}

        # Check if server is running
        print_info("Checking if Session-Buddy MCP server is running...")
        success, stdout, _ = run_command(["lsof", "-i", ":8678"])

        if success:
            print_success("Session-Buddy MCP server is running on port 8678")
            self.tests_passed += 1
            phase_results["tests"].append({"name": "server_running", "status": "pass"})

            # Test health endpoint
            print_info("Testing Session-Buddy MCP health...")
            success, stdout, stderr = run_command(["session-buddy", "mcp", "health"])

            if success:
                print_success("Session-Buddy MCP health check passed")
                self.tests_passed += 1
                phase_results["tests"].append({"name": "health_check", "status": "pass"})
            else:
                print_error("Session-Buddy MCP health check failed")
                print(f"  Error: {stderr}")
                self.tests_failed += 1
                self.results["issues"].append({
                    "phase": "session_buddy_server",
                    "issue": "health check failed",
                    "error": stderr,
                })
                phase_results["tests"].append({"name": "health_check", "status": "fail"})

        else:
            print_error("Session-Buddy MCP server is NOT running")
            self.tests_failed += 1
            self.results["issues"].append({
                "phase": "session_buddy_server",
                "issue": "server not running",
                "fix": "session-buddy mcp start",
            })
            phase_results["tests"].append({"name": "server_running", "status": "fail"})

        self.results["phases"]["session_buddy_server"] = phase_results

    def _test_mahavishnu_shell(self) -> None:
        """Phase 3: Test Mahavishnu shell integration."""
        print_header("Phase 3: Mahavishnu Shell Integration")

        phase_results = {"tests": [], "manual_test_required": True}

        # Check if mahavishnu command is available
        print_info("Checking if mahavishnu command is available...")
        success, stdout, stderr = run_command(["python", "-m", "mahavishnu", "--help"])

        if success:
            print_success("mahavishnu command found")
            self.tests_passed += 1
            phase_results["tests"].append({"name": "command_available", "status": "pass"})

            # Note: We cannot automate the full shell test because it requires
            # interactive input. We'll provide manual test instructions.
            print_info("Manual Test Required:")
            print("  1. Run: cd /Users/les/Projects/mahavishnu")
            print("  2. Run: python -m mahavishnu shell")
            print("  3. Check banner for 'Session Tracking: ✓ Enabled'")
            print("  4. Run: exit() to exit shell")
            print("  5. Run: session-buddy list-sessions --type admin_shell")
            print("  6. Verify session was recorded")
            print()

        else:
            print_error("mahavishnu command not found")
            print(f"  Error: {stderr}")
            self.tests_failed += 1
            self.results["issues"].append({
                "phase": "mahavishnu_shell",
                "issue": "command not found",
                "fix": "cd /Users/les/Projects/mahavishnu && pip install -e .",
            })
            phase_results["tests"].append({"name": "command_available", "status": "fail"})
            phase_results["manual_test_required"] = False

        self.results["phases"]["mahavishnu_shell"] = phase_results

    def _test_database_verification(self) -> None:
        """Phase 4: Test database verification."""
        print_header("Phase 4: Database Verification")

        phase_results = {"tests": []}

        # Check if sessions can be listed
        print_info("Checking if sessions can be listed...")
        success, stdout, stderr = run_command(["session-buddy", "list-sessions", "--type", "admin_shell"])

        if success:
            print_success("Session list query successful")
            self.tests_passed += 1
            phase_results["tests"].append({"name": "list_sessions", "status": "pass"})

            # Parse output
            if "admin_shell" in stdout.lower() or "sessions" in stdout.lower():
                print_info(f"Session list output:\n{stdout[:500]}")

        else:
            print_error("Failed to list sessions")
            print(f"  Error: {stderr}")
            self.tests_failed += 1
            self.results["issues"].append({
                "phase": "database_verification",
                "issue": "failed to list sessions",
                "error": stderr,
            })
            phase_results["tests"].append({"name": "list_sessions", "status": "fail"})

        self.results["phases"]["database_verification"] = phase_results

    def _parse_version(self, pip_show_output: str) -> str:
        """Parse version from pip show output.

        Args:
            pip_show_output: Output from pip show command

        Returns:
            Version string or "unknown"
        """
        for line in pip_show_output.split("\n"):
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return "unknown"

    def _print_summary(self) -> None:
        """Print test summary."""
        print_header("Test Summary")
        print()
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_failed}")
        print(f"Total Tests: {self.tests_passed + self.tests_failed}")
        print()

        if self.tests_failed == 0:
            print_success("All automated tests passed!")
            print()
            print("Next Steps:")
            print("  1. Run manual shell integration test (see Phase 3 above)")
            print("  2. Verify session tracking in database")
            print("  3. Check session metadata completeness")
        else:
            print_error("Some tests failed. Please fix and re-run.")
            print()
            print("Issues Found:")
            for issue in self.results["issues"]:
                print(f"  - Phase: {issue['phase']}")
                print(f"    Issue: {issue['issue']}")
                if "fix" in issue:
                    print(f"    Fix: {issue['fix']}")
                if "error" in issue:
                    print(f"    Error: {issue['error']}")
                print()

        # Save results to file
        results_file = Path("/Users/les/Projects/session-buddy/test_results.json")
        results_file.write_text(json.dumps(self.results, indent=2))
        print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    test = SessionTrackingIntegrationTest()
    sys.exit(test.run_all_tests())
