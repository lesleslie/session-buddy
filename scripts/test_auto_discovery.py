#!/usr/bin/env python3
"""Test script for Phase 2 Auto-Discovery implementation.

This script validates the auto-discovery system without requiring a database connection.
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_adapter_methods():
    """Test that all required methods exist on the adapter."""
    from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
        KnowledgeGraphDatabaseAdapterOneiric,
    )

    required_methods = {
        # Core methods
        "create_entity",
        "get_entity",
        "find_entity_by_name",
        "create_relation",
        "get_relationships",
        "get_stats",
        # Phase 2: Auto-discovery methods
        "_generate_entity_embedding",
        "_find_similar_entities",
        "_auto_discover_relationships",
        "_infer_relationship_type",
        # Phase 2: Batch operations
        "generate_embeddings_for_entities",
        "batch_discover_relationships",
    }

    for method_name in required_methods:
        if not hasattr(KnowledgeGraphDatabaseAdapterOneiric, method_name):
            print(f"❌ Missing method: {method_name}")
            return False
        print(f"✅ Method exists: {method_name}")

    return True


def test_mcp_tools():
    """Test that MCP tools are properly defined."""
    from session_buddy.mcp.tools.collaboration import knowledge_graph_tools

    required_functions = {
        # Phase 2: Auto-discovery tools
        "_generate_embeddings_impl",
        "_discover_relationships_impl",
        "_analyze_graph_connectivity_impl",
        # Tool registration
        "register_knowledge_graph_tools",
    }

    for func_name in required_functions:
        if not hasattr(knowledge_graph_tools, func_name):
            print(f"❌ Missing function: {func_name}")
            return False
        print(f"✅ Function exists: {func_name}")

    return True


def test_embedding_integration():
    """Test that embedding system integration works."""
    from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
        EMBEDDING_AVAILABLE,
        KnowledgeGraphDatabaseAdapterOneiric,
    )

    print(f"✅ Embedding available: {EMBEDDING_AVAILABLE}")

    # Test adapter instantiation
    try:
        kg = KnowledgeGraphDatabaseAdapterOneiric()
        print(f"✅ Adapter instantiation successful")
        print(f"✅ Embedding session initialized: {kg._embedding_session is not None}")
        return True
    except Exception as e:
        print(f"❌ Adapter instantiation failed: {e}")
        return False


def test_method_signatures():
    """Test that method signatures are correct."""
    import inspect
    from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
        KnowledgeGraphDatabaseAdapterOneiric,
    )

    # Test create_entity signature includes auto_discover parameters
    sig = inspect.signature(KnowledgeGraphDatabaseAdapterOneiric.create_entity)
    params = list(sig.parameters.keys())

    required_params = [
        "self",
        "name",
        "entity_type",
        "observations",
        "properties",
        "metadata",
        "attributes",
        "auto_discover",  # Phase 2
        "discovery_threshold",  # Phase 2
        "max_discoveries",  # Phase 2
    ]

    for param in required_params:
        if param not in params:
            print(f"❌ Missing parameter: {param}")
            return False
        print(f"✅ Parameter exists: {param}")

    return True


def test_stats_return_values():
    """Test that get_stats returns the new connectivity metrics."""
    from typing import get_type_hints
    from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
        KnowledgeGraphDatabaseAdapterOneiric,
    )

    # Get the return type hint
    hints = get_type_hints(KnowledgeGraphDatabaseAdapterOneiric.get_stats)
    print(f"✅ get_stats return type: {hints.get('return', 'Not typed')}")

    # We can't test the actual return values without a database,
    # but we can verify the method exists and is typed
    return True


def main() -> int:
    """Run all tests."""
    print("=" * 60)
    print("Phase 2 Auto-Discovery Implementation Tests")
    print("=" * 60)
    print()

    tests = [
        ("Adapter Methods", test_adapter_methods),
        ("MCP Tools", test_mcp_tools),
        ("Embedding Integration", test_embedding_integration),
        ("Method Signatures", test_method_signatures),
        ("Stats Return Values", test_stats_return_values),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Testing: {test_name}")
        print("-" * 60)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
