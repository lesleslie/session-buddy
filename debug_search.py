#!/usr/bin/env python3
"""Debug script to understand how the similarity_search method works."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def debug_search():
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

        # Check if the reflection was stored
        retrieved = await db.get_reflection_by_id(reflection_id)
        print(f"Retrieved by ID: {retrieved}")

        # Try to perform a search using the same approach as the failing test
        print("\nAttempting similarity search...")
        results = await db.similarity_search("environment", limit=10)
        print(f"Search results: {results}")
        print(f"Number of results: {len(results)}")

        # Let's also check what's in the database directly
        try:
            adapter = db._get_adapter()
            client = await adapter.get_client()

            # Check if the table exists and what's in it
            table_name = f"vectors.{db.collection_name}"
            print(f"\nChecking table: {table_name}")

            # List all collections
            collections = await adapter.list_collections()
            print(f"Available collections: {collections}")

            # Check if our collection exists
            if db.collection_name in collections:
                # Count entries
                count_result = client.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()
                print(f"Total entries in table: {count_result[0]}")

                # Get all entries
                all_entries = client.execute(
                    f"SELECT id, metadata FROM {table_name}"
                ).fetchall()
                print(f"All entries: {all_entries}")

                for entry in all_entries:
                    print(f"Entry ID: {entry[0]}")
                    print(f"Entry metadata: {entry[1]}")
            else:
                print(f"Collection {db.collection_name} not found!")

        except Exception as e:
            print(f"Error accessing database directly: {e}")

        db.close()


if __name__ == "__main__":
    asyncio.run(debug_search())
