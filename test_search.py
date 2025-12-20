#!/usr/bin/env python3
"""Test the search functionality directly."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def test_search_functionality():
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

        # Test the get_embedding method
        embedding = await db.get_embedding("environment")
        print(f"Got embedding, length: {len(embedding)}")

        # Test the search functionality directly
        adapter = db._get_adapter()
        try:
            print("Calling adapter.search directly...")
            search_results = await adapter.search(
                collection=db.collection_name,
                query_vector=embedding,
                limit=10,
            )
            print(f"Search results: {search_results}")
            print(f"Search results type: {type(search_results)}")
        except Exception as e:
            print(f"adapter.search failed with error: {e}")
            print(f"Error type: {type(e)}")

        # Now test the full similarity_search method
        print("\nTesting similarity_search method...")
        search_results = await db.similarity_search("environment", limit=10)
        print(f"Method results: {search_results}")

        db.close()


if __name__ == "__main__":
    asyncio.run(test_search_functionality())
