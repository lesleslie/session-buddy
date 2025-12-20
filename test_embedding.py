#!/usr/bin/env python3
"""Test the get_embedding method directly."""

import asyncio
import tempfile
from pathlib import Path

from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def test_get_embedding():
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

        print(f"self.onnx_session: {db.onnx_session is not None}")

        # Test the get_embedding method directly
        try:
            print("Calling get_embedding...")
            embedding = await db.get_embedding("environment")
            print(
                f"Embedding result: {type(embedding)}, length: {len(embedding) if embedding else 'None'}"
            )
        except Exception as e:
            print(f"get_embedding failed with error: {e}")
            print(f"Error type: {type(e)}")

        db.close()


if __name__ == "__main__":
    asyncio.run(test_get_embedding())
