#!/usr/bin/env python3
"""Test script for pattern injection and context optimization hooks.

Tests the three main hooks:
1. suggest_patterns.py - Pattern suggestion hook
2. capture_pattern_if_success.py - Pattern capture hook
3. optimize_context.py - Context optimization hook
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


async def test_pattern_suggestion_hook() -> bool:
    """Test the pattern suggestion hook."""
    print("Testing pattern suggestion hook...")

    try:
        # Import the hook module
        sys.path.insert(0, str(Path.home() / ".claude" / "scripts"))
        import suggest_patterns

        # Create test context
        test_context = {
            "problem": "Slow database queries",
            "database": "postgresql",
            "symptoms": ["Timeout errors", "High CPU usage"],
            "environment": "production",
        }

        # Test the suggest_patterns function
        # Note: The hook reads from stdin, so we'll simulate that
        import io

        original_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(test_context))

        try:
            # This should not raise an exception
            await suggest_patterns.suggest_patterns(test_context)
            print("✅ Pattern suggestion hook executed successfully")
            return True
        finally:
            sys.stdin = original_stdin

    except Exception as e:
        print(f"❌ Pattern suggestion hook failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_pattern_capture_hook() -> bool:
    """Test the pattern capture hook."""
    print("Testing pattern capture hook...")

    try:
        # Import the hook module
        sys.path.insert(0, str(Path.home() / ".claude" / "scripts"))
        import capture_pattern_if_success

        # Create test metadata
        test_metadata = {
            "tool_result": {"success": True},
            "project_id": "test-project",
            "context": {
                "pattern_type": "solution",
                "problem": "Database connection pool exhausted",
                "symptoms": ["Connection timeout", "Too many connections"],
                "constraints": ["Must handle 1000 concurrent users"],
                "environment": "production",
                "solution_approach": "Implement connection pooling with PgBouncer",
                "code_changes": "Added PgBouncer configuration",
                "configuration": "pool_mode = transaction",
                "files_modified": ["docker-compose.yml", "config/pgbouncer.ini"],
                "rationale": "PgBouncer provides efficient connection pooling",
                "outcome_score": 0.9,
                "tags": ["database", "performance", "postgresql"],
            },
        }

        # Test the capture_pattern_if_successful function
        await capture_pattern_if_success.capture_pattern_if_successful(
            tool_result=test_metadata["tool_result"],
            project_id=test_metadata["project_id"],
            context=test_metadata["context"],
        )

        print("✅ Pattern capture hook executed successfully")
        return True

    except Exception as e:
        print(f"❌ Pattern capture hook failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_context_optimization_hook() -> bool:
    """Test the context optimization hook."""
    print("Testing context optimization hook...")

    try:
        # Import the hook module
        sys.path.insert(0, str(Path.home() / ".claude" / "scripts"))
        import optimize_context

        # Create test context
        test_context = {
            "task": "Add caching layer to reduce database load",
            "project_type": "python",
            "constraints": ["Must be Redis-compatible", "TTL support"],
        }

        # Test the optimize_injected_context function
        await optimize_context.optimize_injected_context(test_context)

        print("✅ Context optimization hook executed successfully")
        return True

    except Exception as e:
        print(f"❌ Context optimization hook failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_intelligence_engine_integration() -> bool:
    """Test the intelligence engine integration."""
    print("Testing intelligence engine integration...")

    try:
        # Add session-buddy to path if needed
        import sys
        from pathlib import Path

        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from session_buddy.core.intelligence import IntelligenceEngine

        # Initialize engine
        engine = IntelligenceEngine()
        await engine.initialize()

        # Test pattern capture
        pattern_id = await engine.capture_successful_pattern(
            pattern_type="solution",
            project_id="test-project",
            context={
                "problem": "Test problem",
                "symptoms": ["Test symptom"],
                "constraints": [],
                "environment": "test",
            },
            solution={
                "approach": "Test solution",
                "code_changes": "Test changes",
                "configuration": "",
                "files_modified": [],
                "rationale": "Test rationale",
            },
            outcome_score=0.8,
            tags=["test"],
        )

        print(f"✅ Captured pattern: {pattern_id}")

        # Test pattern search
        patterns = await engine.search_similar_patterns(
            current_context={"problem": "Test problem"},
            threshold=0.75,
            limit=5,
        )

        print(f"✅ Found {len(patterns)} similar patterns")

        return True

    except Exception as e:
        print(f"❌ Intelligence engine integration failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_context_optimizer() -> bool:
    """Test the context optimizer."""
    print("Testing context optimizer...")

    try:
        # Add session-buddy to path if needed
        import sys
        from pathlib import Path

        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from session_buddy.context.optimizer import get_context_optimizer

        # Get optimizer instance
        optimizer = get_context_optimizer()

        # Test project type detection
        current_dir = Path.cwd()
        project_type = optimizer._detect_project_type(current_dir)
        print(f"✅ Detected project type: {project_type}")

        # Test project context loading
        project_context = optimizer.load_project_context(str(current_dir))
        print(f"✅ Loaded project context: {project_context['project_type']}")

        # Test context optimization
        optimized = optimizer.optimize_context_for_task(
            task_description="Test task",
            project_context=project_context,
            available_tokens=10000,
            relevant_patterns=None,
        )

        print(f"✅ Generated optimized context ({len(optimized)} chars)")

        return True

    except Exception as e:
        print(f"❌ Context optimizer test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main() -> int:
    """Run all tests."""
    print("=" * 80)
    print("PATTERN INJECTION AND CONTEXT OPTIMIZATION HOOK TESTS")
    print("=" * 80)
    print()

    results = []

    # Test each hook
    results.append(await test_pattern_suggestion_hook())
    print()

    results.append(await test_pattern_capture_hook())
    print()

    results.append(await test_context_optimization_hook())
    print()

    # Test integration components
    results.append(await test_intelligence_engine_integration())
    print()

    results.append(await test_context_optimizer())
    print()

    # Summary
    passed = sum(results)
    total = len(results)

    print("=" * 80)
    print(f"TEST RESULTS: {passed}/{total} tests passed")
    print("=" * 80)

    if passed == total:
        print("✅ All tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
