#!/usr/bin/env python3
"""Phase 3 Integration Helper Script.

This script helps integrate Phase 3 features into the knowledge graph adapter.
It performs the following tasks:
1. Checks current state of files
2. Applies necessary patches
3. Validates integration
4. Runs tests

Usage:
    python scripts/integrate_phase3.py --check
    python scripts/integrate_phase3.py --apply
    python scripts/integrate_phase3.py --validate
    python scripts/integrate_phase3.py --test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def check_integration_status() -> dict[str, bool]:
    """Check current integration status.

    Returns:
        Dictionary with integration status for each component
    """
    project_root = Path(__file__).parent.parent
    adapters_dir = project_root / "session_buddy" / "adapters"
    tools_dir = project_root / "session_buddy" / "mcp" / "tools" / "collaboration"
    tests_dir = project_root / "tests" / "unit"

    status = {
        "phase3_mixin_exists": (adapters_dir / "knowledge_graph_adapter_phase3.py").exists(),
        "phase3_patch_exists": (adapters_dir / "knowledge_graph_phase3_patch.py").exists(),
        "phase3_tools_exist": (tools_dir / "knowledge_graph_phase3_tools.py").exists(),
        "phase3_tests_exist": (tests_dir / "test_phase3_relationships.py").exists(),
        "main_adapter_exists": (adapters_dir / "knowledge_graph_adapter_oneiric.py").exists(),
        "base_tools_exist": (tools_dir / "knowledge_graph_tools.py").exists(),
    }

    return status


def print_status(status: dict[str, bool]) -> None:
    """Print integration status.

    Args:
        status: Dictionary with integration status
    """
    print("=" * 60)
    print("Phase 3 Integration Status")
    print("=" * 60)
    print()

    all_good = True

    for key, value in status.items():
        symbol = "✅" if value else "❌"
        print(f"{symbol} {key}: {value}")
        if not value:
            all_good = False

    print()
    if all_good:
        print("✅ All Phase 3 files are present!")
    else:
        print("❌ Some Phase 3 files are missing.")
    print()


def apply_integration_patch() -> bool:
    """Apply Phase 3 integration patches.

    Returns:
        True if successful, False otherwise
    """
    print("Applying Phase 3 integration patches...")
    print()

    project_root = Path(__file__).parent.parent

    # Check if all Phase 3 files exist
    status = check_integration_status()
    if not all(status.values()):
        print("❌ Cannot apply patches - some Phase 3 files are missing.")
        print("Please ensure all files are present first.")
        return False

    # Patch 1: Update settings to make DuckPGQ optional
    settings_file = project_root / "session_buddy" / "adapters" / "settings.py"
    print(f"📝 Patching {settings_file.relative_to(project_root)}...")

    try:
        content = settings_file.read_text()

        # Check if already patched
        if "# Phase 3: DuckPGQ optional" in content:
            print("   ℹ️ Already patched - skipping")
        else:
            # Make DuckPGQ optional
            old_line = 'install_extensions: tuple[str, ...] = ("duckpgq",)'
            new_line = """install_extensions: tuple[str, ...] = ()  # Phase 3: DuckPGQ not available in v1.4.4"""

            if old_line in content:
                content = content.replace(old_line, new_line)
                settings_file.write_text(content)
                print("   ✅ Made DuckPGQ optional")
            else:
                print("   ⚠️ Pattern not found - may already be patched")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

    print()
    print("⚠️ Manual integration steps required:")
    print()
    print("1. Add Phase3RelationshipMixin to KnowledgeGraphDatabaseAdapterOneiric:")
    print("   from session_buddy.adapters.knowledge_graph_adapter_phase3 import (")
    print("       Phase3RelationshipMixin,")
    print("   )")
    print()
    print("   class KnowledgeGraphDatabaseAdapterOneiric(Phase3RelationshipMixin):")
    print()
    print("2. Update _infer_relationship_type method (see PHASE3_INTEGRATION_GUIDE.md)")
    print()
    print("3. Register Phase 3 MCP tools (see PHASE3_INTEGRATION_GUIDE.md)")
    print()
    print("See docs/PHASE3_INTEGRATION_GUIDE.md for detailed instructions.")
    print()

    return True


def validate_integration() -> bool:
    """Validate Phase 3 integration.

    Returns:
        True if validation passes, False otherwise
    """
    print("Validating Phase 3 integration...")
    print()

    project_root = Path(__file__).parent.parent

    # Check if Phase 3 is imported
    adapter_file = project_root / "session_buddy" / "adapters" / "knowledge_graph_adapter_oneiric.py"

    try:
        content = adapter_file.read_text()

        checks = {
            "Phase3RelationshipMixin imported": "Phase3RelationshipMixin" in content,
            "Class inherits from mixin": "class KnowledgeGraphDatabaseAdapterOneiric(Phase3RelationshipMixin)" in content
            or "class KnowledgeGraphDatabaseAdapterOneiric(Phase3RelationshipMixin," in content,
            "_infer_relationship_type returns tuple": "-> tuple[str, str]:" in content,
            "discover_transitive_relationships exists": "async def discover_transitive_relationships" in content,
            "_extract_relationships_from_observations exists": "def _extract_relationships_from_observations" in content,
        }

        print("Validation Results:")
        print()
        all_pass = True
        for check, result in checks.items():
            symbol = "✅" if result else "❌"
            print(f"{symbol} {check}")
            if not result:
                all_pass = False

        print()
        if all_pass:
            print("✅ Integration looks good!")
        else:
            print("⚠️ Integration incomplete - see docs/PHASE3_INTEGRATION_GUIDE.md")

        return all_pass

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_tests() -> bool:
    """Run Phase 3 tests.

    Returns:
        True if tests pass, False otherwise
    """
    import subprocess

    print("Running Phase 3 tests...")
    print()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/test_phase3_relationships.py", "-v"],
        cwd=Path(__file__).parent.parent,
    )

    print()
    if result.returncode == 0:
        print("✅ Tests passed!")
        return True
    else:
        print("❌ Tests failed.")
        return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Phase 3 Integration Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --check       Check integration status
  %(prog)s --apply       Apply integration patches
  %(prog)s --validate    Validate integration
  %(prog)s --test        Run Phase 3 tests
  %(prog)s --all         Check, apply, validate, and test
        """,
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check integration status",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply integration patches",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate integration",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run Phase 3 tests",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all steps (check, apply, validate, test)",
    )

    args = parser.parse_args()

    if args.all:
        args.check = True
        args.apply = True
        args.validate = True
        args.test = True

    exit_code = 0

    if args.check:
        status = check_integration_status()
        print_status(status)

    if args.apply:
        if not apply_integration_patch():
            exit_code = 1

    if args.validate:
        if not validate_integration():
            exit_code = 1

    if args.test:
        if not run_tests():
            exit_code = 1

    if not any([args.check, args.apply, args.validate, args.test]):
        parser.print_help()
        return 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
