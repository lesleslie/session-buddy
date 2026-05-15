from __future__ import annotations

import importlib


def test_adapters_package_does_not_reexport_storage_facades():
    package = importlib.import_module("session_buddy.adapters")

    assert not hasattr(package, "SessionStorageAdapter")
    assert not hasattr(package, "get_default_storage_adapter")
    assert not hasattr(package, "KnowledgeGraphDatabaseAdapter")
    assert not hasattr(package, "ReflectionDatabaseAdapter")
    assert not hasattr(package, "get_storage_adapter")
    assert not hasattr(package, "register_storage_adapter")
