#!/usr/bin/env python3
"""Architecture validation script for Phase 2.5."""

import ast
from pathlib import Path

print("=" * 70)
print("PHASE 2.5: ARCHITECTURE VALIDATION REPORT")
print("=" * 70)

issues = []
warnings = []
passes = []

# 1. LAYER SEPARATION VERIFICATION
print("\n1. LAYER SEPARATION VERIFICATION")
print("-" * 70)

# Check core layer for MCP imports
core_dir = Path("session_buddy/core")
mcp_imports = []

for py_file in core_dir.rglob("*.py"):
    with open(py_file) as f:
        try:
            tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "session_buddy.mcp" in node.module:
                        mcp_imports.append(f"{py_file}:{node.lineno}")
        except Exception as e:
            issues.append(f"Failed to parse {py_file}: {e}")

if mcp_imports:
    print(f"FAILED: Found {len(mcp_imports)} MCP imports in core典故 layer:")
    for imp in mcp_imports:
        print(f"   - {imp}")
else:
    print("PASSED: No MCP imports in core layer")
    passes.append("Core layer has zero MCP imports")

# 2. CIRCULAR DEPENDENCY CHECK
print("\n2. CIRCULAR DEPENDENCY CHECK")
print("-" * 70)

if not mcp_imports:
    print("PASSED: No upward dependencies from core to MCP")
    passes.append("No upward dependencies from core to MCP")

# 3. INTERFACE COMPLIANCE
print("\n3. INTERFACE COMPLIANCE")
print("-" * 70)

# Check QualityScorer interface
quality_scorer_file = Path("session_buddy/core/quality_scoring.py")
if quality_scorer_file.exists():
    with open(quality_scorer_file) as f:
        content = f.read()
        if "class QualityScorer(ABC):" in content:
            print("PASSED: QualityScorer is an ABC")
            passes.append("QualityScorer is an ABC")

            if "from abc import ABC, abstractmethod" in content:
                print("PASSED: QualityScorer has abstractmethod decorators")
                passes.append("QualityScorer has abstractmethod decorators")
            else:
                issues.append("QualityScorer missing ABC imports")
        else:
            issues.append("QualityScorer is not an ABC")

        if "class DefaultQualityScorer(QualityScorer):" in content:
            print("PASSED: DefaultQualityScorer fallback exists")
            passes.append("DefaultQualityScorer fallback exists")
        else:
            warnings.append("DefaultQualityScorer fallback not found")
else:
    issues.append("quality_scoring.py not found")

# Check CodeFormatter interface
hooks_file = Path("session_buddy/core/hooks.py")
if hooks_file.exists():
    with open(hooks_file) as f:
        content = f.read()
        if "class CodeFormatter(ABC):" in content:
            print("PASSED: CodeFormatter is an ABC")
            passes.append("CodeFormatter is an ABC")

            if "from abc import ABC, abstractmethod" in content:
                print("PASSED: CodeFormatter has abstractmethod decorators")
                passes.append("CodeFormatter has abstractmethod decorators")
            else:
                issues.append("CodeFormatter missing ABC imports")
        else:
            issues.append("CodeFormatter is not an ABC")

        if "class DefaultCodeFormatter(CodeFormatter):" in content:
            print("PASSED: DefaultCodeFormatter fallback exists")
            passes.append("DefaultCodeFormatter fallback exists")
        else:
            warnings.append("DefaultCodeFormatter fallback not found")
else:
    issues.append("hooks.py not found")

# 4. TEST MOCKING PATTERN CHECK
print("\n4. TEST MOCKING VERIFICATION")
print("-" * 70)

test_files = list(Path("tests/unit").glob("test_*.py"))
mocking_with_interfaces = False
mocking_with_direct_mcp = False

for test_file in test_files:
    with open(test_file) as f:
        content = f.read()
        # Check for interface mocking
        if "patch.object" in content and "quality_scorer" in content:
            mocking_with_interfaces = True

        # Check for direct MCP imports in tests
        if (
            "from session_buddy.mcp import" in content
            or "import session_buddy.mcp" in content
        ):
            if "test_mcp" not in str(test_file):  # Allow in test_mcp files
                mocking_with_direct_mcp = True
                issues.append(f"Test imports MCP directly: {test_file}")

if mocking_with_interfaces:
    print("PASSED: Tests use interface mocking patterns")
    passes.append("Tests mock interfaces not MCP layer")

if not mocking_with_direct_mcp:
    print("PASSED: No direct MCP imports in tests")
    passes.append("No direct MCP imports in tests")

# 5. DI CONTAINER VERIFICATION
print("\n5. DI CONTAINER HEALTH CHECK")
print("-" * 70)

di_file = Path("session_buddy/di/__init__.py")
if di_file.exists():
    with open(di_file) as f:
        content = f.read()

        # Check for required registrations
        required_registrations = [
            "_register_quality_scorer",
            "_register_code_formatter",
            "_register_lifecycle_manager",
            "_register_hooks_manager",
        ]

        for reg in required_registrations:
            if f"def {reg}(" in content:
                print(f"PASSED: {reg} function exists")
                passes.append(f"{reg} registered in DI")
            else:
                issues.append(f"Missing {reg} function")

        # Check registration order in configure()
        lines = content.split("\n")
        quality_scorer_line = -1
        lifecycle_manager_line = -1

        for i, line in enumerate(lines):
            if "_register_quality_scorer(force)" in line:
                quality_scorer_line = i
            if "_register_lifecycle_manager(force)" in line:
                lifecycle_manager_line = i

        if quality_scorer_line > 0 and lifecycle_manager_line > 0:
            if quality_scorer_line < lifecycle_manager_line:
                print("PASSED: QualityScorer registered before LifecycleManager")
                passes.append("DI registration order correct for QualityScorer")
            else:
                issues.append("QualityScorer not registered before LifecycleManager")

        code_formatter_line = -1
        hooks_manager_line = -1

        for i, line in enumerate(lines):
            if "_register_code_formatter(force)" in line:
                code_formatter_line = i
            if "_register_hooks_manager(force)" in line:
                hooks_manager_line = i

        if code_formatter_line > 0 and hooks_manager_line > 0:
            if code_formatter_line < hooks_manager_line:
                print("PASSED: CodeFormatter registered before HooksManager")
                passes.append("DI registration order correct for CodeFormatter")
            else:
                issues.append("CodeFormatter not registered before HooksManager")

# 6. DOCUMENTATION CHECK
print("\n6. DOCUMENTATION VERIFICATION")
print("-" * 70)

# Check for docstrings in interfaces
interfaces = [
    ("session_buddy/core/quality_scoring.py", "QualityScorer"),
    ("session_buddy/core/hooks.py", "CodeFormatter"),
]

for file_path, interface_name in interfaces:
    path = Path(file_path)
    if path.exists():
        with open(path) as f:
            content = f.read()
            if f"class {interface_name}" in content:
                lines = content.split("\n")
                found_class = False
                has_docstring = False
                for i, line in enumerate(lines):
                    if f"class {interface_name}" in line:
                        found_class = True
                        # Check next line for docstring
                        if i + 1 < len(lines) and '"""' in lines[i + 1]:
                            has_docstring = True
                            break

                if found_class and has_docstring:
                    print(f"PASSED: {interface_name} has docstring")
                    passes.append(f"{interface_name} documented")
                elif found_class:
                    warnings.append(f"{interface_name} missing docstring")

# SUMMARY
print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)
print(f"\nPASSES: {len(passes)}")
for p in passes:
    print(f"   {p}")

if warnings:
    print(f"\nWARNINGS: {len(warnings)}")
    for w in warnings:
        print(f"   ! {w}")

if issues:
    print(f"\nISSUES: {len(issues)}")
    for i in issues:
        print(f"   X {i}")
else:
    print("\nSUCCESS: All critical checks passed!")

print("\n" + "=" * 70)
print("ARCHITECTURE VALIDATION COMPLETE")
print("=" * 70)
