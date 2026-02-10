#!/usr/bin/env python3
"""Analyze existing test structure and identify gaps."""

from pathlib import Path


def analyze_test_structure():
    """Analyze test directory structure."""
    tests_dir = Path("/Users/les/Projects/session-buddy/tests")
    source_dir = Path("/Users/les/Projects/session-buddy/session_buddy")

    # Find all test files
    test_files = list(tests_dir.rglob("test_*.py"))

    # Find all source files
    source_files = list(source_dir.rglob("*.py"))
    source_files = [f for f in source_files if f.name != "__init__.py"]

    print("\n" + "=" * 80)
    print("SESSION-BUDDY TEST STRUCTURE ANALYSIS")
    print("=" * 80)

    # Categorize tests
    print("\nEXISTING TEST FILES:")
    print("-" * 80)

    test_categories = {}
    for test_file in test_files:
        # Determine category
        relative = test_file.relative_to(tests_dir)
        parts = relative.parts

        if len(parts) > 1:
            category = parts[0]  # unit, integration, etc.
            subcategory = parts[1] if len(parts) > 2 else ""
        else:
            category = "root"
            subcategory = ""

        if category not in test_categories:
            test_categories[category] = []

        test_categories[category].append((subcategory, test_file))

    # Print by category
    for category, files in sorted(test_categories.items()):
        print(f"\n{category.upper()}:")

        for subcategory, file_path in sorted(files):
            indent = "  " if subcategory else ""
            name = file_path.stem
            print(f"{indent}- {name}")

    # Analyze source modules
    print("\n" + "\nSOURCE MODULES:")
    print("-" * 80)

    source_modules = {}
    for source_file in source_files:
        relative = source_file.relative_to(source_dir)
        parts = relative.parts

        if len(parts) > 1:
            module = parts[0]  # core, mcp, utils, etc.
            subcategory = parts[1] if len(parts) > 2 else ""
        else:
            module = "root"
            subcategory = ""

        if module not in source_modules:
            source_modules[module] = []

        source_modules[module].append((subcategory, source_file))

    # Print by module
    for module, files in sorted(source_modules.items()):
        print(f"\n{module.upper()}:")

        for subcategory, file_path in sorted(files):
            indent = "  " if subcategory else ""
            name = file_path.stem
            print(f"{indent}- {name}")

    # Identify gaps
    print("\n" + "\nTEST GAPS (Source files without corresponding tests):")
    print("-" * 80)

    # Map test files to source files
    tested_sources = set()
    for test_file in test_files:
        # Try to find corresponding source file
        test_name = test_file.stem
        if test_name.startswith("test_"):
            source_name = test_name[5:]  # Remove 'test_' prefix

            # Search for matching source
            for source_file in source_files:
                if source_file.stem == source_name:
                    tested_sources.add(source_file)
                    break

    # Find untested sources
    untested = []
    for source_file in source_files:
        if source_file not in tested_sources:
            relative = source_file.relative_to(source_dir)
            untested.append(relative)

    if untested:
        # Group by module
        untested_by_module = {}
        for path in untested:
            module = path.parts[0] if len(path.parts) > 1 else "root"
            if module not in untested_by_module:
                untested_by_module[module] = []
            untested_by_module[module].append(path)

        for module, files in sorted(untested_by_module.items()):
            print(f"\n{module.upper()}:")
            for file_path in sorted(files)[:10]:  # Show first 10
                print(f"  - {file_path}")

            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more")
    else:
        print("  All source files have corresponding tests!")

    # Statistics
    print("\n" + "\nSTATISTICS:")
    print("-" * 80)
    print(f"  Test files: {len(test_files)}")
    print(f"  Source files: {len(source_files)}")
    print(f"  Tested sources: {len(tested_sources)}")
    print(f"  Untested sources: {len(untested)}")
    print(f"  Test coverage: {len(tested_sources) / len(source_files) * 100:.1f}%")


if __name__ == "__main__":
    analyze_test_structure()
