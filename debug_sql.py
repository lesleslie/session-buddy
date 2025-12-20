#!/usr/bin/env python3
"""Debug script to test the SQL query directly."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def debug_sql_query():
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

        # Let's test the SQL query directly
        adapter = db._get_adapter()
        client = await adapter.get_client()
        table_name = f"vectors.{db.collection_name}"

        # Test different variations of the query
        query = "environment"
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        search_pattern = f"%{safe_query}%"

        print(f"Search pattern: {search_pattern}")

        # Query 1: Direct test with the search pattern
        sql_test1 = f"SELECT id, metadata FROM {table_name} WHERE CAST(metadata AS VARCHAR) ILIKE ? ESCAPE '\\'"
        try:
            results1 = client.execute(sql_test1, [search_pattern]).fetchall()
            print(f"Query 1 results: {results1}")
        except Exception as e:
            print(f"Query 1 error: {e}")

        # Query 2: Test without parameter binding to see if that's the issue
        sql_test2 = f"SELECT id, metadata FROM {table_name} WHERE CAST(metadata AS VARCHAR) ILIKE '%{query}%'"
        try:
            results2 = client.execute(sql_test2).fetchall()
            print(f"Query 2 results: {results2}")
        except Exception as e:
            print(f"Query 2 error: {e}")

        # Query 3: Check if the content "environment" exists anywhere in the metadata
        sql_test3 = f"SELECT id, metadata FROM {table_name} WHERE LOWER(CAST(metadata AS VARCHAR)) LIKE LOWER('%environment%')"
        try:
            results3 = client.execute(sql_test3).fetchall()
            print(f"Query 3 results: {results3}")
        except Exception as e:
            print(f"Query 3 error: {e}")

        # Query 4: Let's try a more direct approach with JSON functions
        sql_test4 = f"SELECT id, metadata FROM {table_name} WHERE LOWER(json_extract_string(metadata, '$.content')) LIKE LOWER('%environment%')"
        try:
            results4 = client.execute(sql_test4).fetchall()
            print(f"Query 4 results: {results4}")
        except Exception as e:
            print(f"Query 4 error: {e}")

        # Now test the actual similarity_search method
        print("\nTesting similarity_search method...")
        search_results = await db.similarity_search("environment", limit=10)
        print(f"Method results: {search_results}")

        db.close()


if __name__ == "__main__":
    asyncio.run(debug_sql_query())
