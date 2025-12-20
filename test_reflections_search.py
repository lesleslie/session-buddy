#!/usr/bin/env python3
"""Test the search_reflections method to see if it works."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def test_search_reflections():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "debug_test.duckdb"
        db = ReflectionDatabaseAdapter(db_path=str(db_path))
        await db.initialize()

        print("Database initialized successfully")

        # Store some content
        content = "Environment test content"
        tags = ["env", "test"]
        reflection_id = await db.store_reflection(content, tags)
        print(f"Stored reflection with ID: {reflection_id}")

        # Test search_reflections method
        print("Testing search_reflections method...")
        reflection_results = await db.search_reflections("environment", limit=10)
        print(f"Reflection search results: {reflection_results}")
        print(f"Number of reflection results: {len(reflection_results)}")

        # Test search_conversations method (should return empty since we didn't store any)
        print("Testing search_conversations method...")
        conv_results = await db.search_conversations("environment", limit=10)
        print(f"Conversation search results: {conv_results}")
        print(f"Number of conversation results: {len(conv_results)}")

        db.close()


if __name__ == "__main__":
    asyncio.run(test_search_reflections())
