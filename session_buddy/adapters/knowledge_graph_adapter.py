"""Compatibility shim for the Oneiric knowledge graph adapter.

This module preserves the historical import path while routing to the
Oneiric-native implementation.
"""

from __future__ import annotations

from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
    KnowledgeGraphDatabaseAdapterOneiric as KnowledgeGraphDatabaseAdapter,
)

__all__ = ["KnowledgeGraphDatabaseAdapter"]
