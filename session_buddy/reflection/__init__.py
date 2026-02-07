"""Reflection system for session conversations and insights.

This module provides the core reflection database functionality with:
- ReflectionDatabase: Main database interface
- Semantic search using local ONNX embeddings
- CRUD operations for conversations and reflections
- Thread-safe async operations

Module Structure:
    - database.py: Core ReflectionDatabase class
    - embeddings.py: Embedding generation (ONNX, local)
    - search.py: Semantic and text search operations
    - storage.py: CRUD operations
    - schema.py: Database schema definitions

Example:
    >>> from session_buddy.reflection import ReflectionDatabase
    >>>
    >>> async with ReflectionDatabase() as db:
    ...     # Store conversation
    ...     await db.store_conversation("Hello world")
    ...
    ...     # Search conversations
    ...     results = await db.search_conversations("hello")
"""

# Core database
from session_buddy.reflection.database import (
    ReflectionDatabase,
    get_reflection_database,
)

# Embeddings
from session_buddy.reflection.embeddings import (
    clear_embedding_cache,
    generate_embedding,
    initialize_embedding_system,
)

# Search
from session_buddy.reflection.search import (
    search_conversations,
    search_reflections,
)

# Storage
from session_buddy.reflection.storage import (
    store_conversation,
    store_reflection,
)

__all__ = [
    # Core database
    "ReflectionDatabase",
    "get_reflection_database",
    # Embeddings
    "generate_embedding",
    "clear_embedding_cache",
    "initialize_embedding_system",
    # Search
    "search_conversations",
    "search_reflections",
    # Storage
    "store_conversation",
    "store_reflection",
]
