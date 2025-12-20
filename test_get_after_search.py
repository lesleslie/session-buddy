#!/usr/bin/env python3
"""Test getting metadata after search."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def test_get_after_search():
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

        # Test the search functionality directly
        adapter = db._get_adapter()
        embedding = await db.get_embedding("environment")

        # Search and then get the full documents
        try:
            print("Calling adapter.search directly...")
            search_results = await adapter.search(
                collection=db.collection_name,
                query_vector=embedding,
                limit=10,
            )
            print(f"Search results: {search_results}")

            if search_results:
                result = search_results[0]
                print(f"First result ID: {result.id}")
                print(f"First result score: {result.score}")
                print(f"First result metadata: {result.metadata}")

                # Try to get the document with full metadata
                print("Getting document with full metadata...")
                docs = await adapter.get(
                    collection=db.collection_name,
                    ids=[result.id],
                    include_metadata=True,
                    include_vectors=False,
                )
                print(f"Get results: {docs}")

                if docs:
                    doc = docs[0]
                    print(f"Document ID: {doc.id}")
                    print(f"Document metadata: {doc.metadata}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()

        db.close()


if __name__ == "__main__":
    asyncio.run(test_get_after_search())
