#!/usr/bin/env python3
"""More detailed debug script to understand the execution flow."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def debug_execution_flow():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "debug_test.duckdb"
        db = ReflectionDatabaseAdapter(db_path=str(db_path))
        await db.initialize()

        print("Database initialized successfully")
        print(f"ONNX_AVAILABLE: {db.__class__.__module__}")

        # Import the constant
        try:
            from session_buddy.adapters.reflection_adapter import ONNX_AVAILABLE

            print(f"ONNX_AVAILABLE constant: {ONNX_AVAILABLE}")
        except ImportError:
            print("Could not import ONNX_AVAILABLE")

        print(f"self.onnx_session: {db.onnx_session}")

        # Store some content
        content = "Environment test content"
        tags = ["env", "test"]
        reflection_id = await db.store_reflection(content, tags)
        print(f"Stored reflection with ID: {reflection_id}")

        # Now test the similarity_search method step by step
        print("\nTesting similarity_search method...")

        # Check the condition manually
        condition_result = db.onnx_session is not None
        print(f"Condition (ONNX_AVAILABLE and self.onnx_session): {condition_result}")

        # Call the method and see what happens
        search_results = await db.similarity_search("environment", limit=10)
        print(f"Method results: {search_results}")
        print(f"Number of results: {len(search_results)}")

        # Now let's manually test the text search fallback
        print("\nTesting text search fallback manually...")
        text_results = await db._text_search_fallback("environment", 10)
        print(f"Text search results: {text_results}")
        print(f"Number of text results: {len(text_results)}")

        db.close()


if __name__ == "__main__":
    asyncio.run(debug_execution_flow())
