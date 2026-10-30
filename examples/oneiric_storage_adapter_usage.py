#!/usr/bin/env python3
"""Example demonstrating correct Oneiric storage adapter usage.

This example shows how to properly:
1. Register storage adapters for different backends
2. Configure storage settings
3. Use adapters for session persistence
4. Switch between backends dynamically

The registry lives in ``session_buddy/adapters/storage_oneiric.py``, which
replaced the former ACB storage registry. Its interface differs in two
places worth knowing about:

* objects are addressed by ``path`` within a bucket, not by ``key``
* there is no ``list_files``; the base adapter exposes
  ``upload`` / ``download`` / ``delete`` / ``exists`` only

Run:
    python examples/oneiric_storage_adapter_usage.py
"""

import asyncio

from session_buddy.adapters.storage_oneiric import (
    configure_storage_buckets,
    get_default_session_buckets,
    get_storage_adapter,
    register_storage_adapter,
)
from session_buddy.paths import data_dir as resolve_data_dir


async def example_file_storage():
    """Example: Using file-based storage."""
    print("\n" + "=" * 60)
    print("Example 1: File-based Storage")
    print("=" * 60)

    # Setup data directory
    data_dir = resolve_data_dir()

    # Configure buckets
    buckets = get_default_session_buckets()
    configure_storage_buckets(buckets)
    print(f"✅ Configured buckets: {list(buckets.keys())}")

    # Register file storage
    storage = register_storage_adapter(
        "file", {"local_path": str(data_dir / "sessions")}
    )
    print(f"✅ Registered file storage: {type(storage).__module__}")

    # Initialize storage (creates directories, etc.)
    await storage.init()
    print("✅ Initialized file storage")

    # Store session data
    session_data = b'{"session_id": "test_123", "user": "demo"}'
    await storage.upload(
        bucket="sessions", path="test_123/state.json", data=session_data
    )
    print("✅ Stored session data")

    # Retrieve session data
    retrieved = await storage.download(bucket="sessions", path="test_123/state.json")
    print(f"✅ Retrieved: {retrieved[:50]}...")

    # Check if file exists
    exists = await storage.exists(bucket="sessions", path="test_123/state.json")
    print(f"✅ File exists: {exists}")

    # A path that was never written is absent rather than an error
    missing = await storage.exists(
        bucket="sessions", path="test_123/never-written.json"
    )
    print(f"✅ Missing path reported as absent: {not missing}")

    # Cleanup
    await storage.delete(bucket="sessions", path="test_123/state.json")
    print("✅ Cleaned up test data")


async def example_memory_storage():
    """Example: Using in-memory storage for testing."""
    print("\n" + "=" * 60)
    print("Example 2: In-Memory Storage (Testing)")
    print("=" * 60)

    # Register memory storage
    storage = register_storage_adapter("memory", {"max_size_mb": 100})
    print(f"✅ Registered memory storage: {type(storage).__module__}")

    # Initialize
    await storage.init()
    print("✅ Initialized memory storage")

    # Store test data
    test_data = b'{"test": "data", "timestamp": "2025-01-12"}'
    await storage.upload(bucket="test", path="example.json", data=test_data)
    print("✅ Stored test data in memory")

    # Retrieve
    retrieved = await storage.download(bucket="test", path="example.json")
    print(f"✅ Retrieved: {retrieved}")

    # Memory storage is ephemeral - perfect for tests
    print("⚠️  Note: Memory storage is cleared when process exits")


async def example_backend_switching():
    """Example: Dynamically switching between backends."""
    print("\n" + "=" * 60)
    print("Example 3: Dynamic Backend Switching")
    print("=" * 60)

    # Register multiple backends
    backends = ["file", "memory"]

    for backend in backends:
        config = {}
        if backend == "file":
            config["local_path"] = str(resolve_data_dir() / "sessions")
        elif backend == "memory":
            config["max_size_mb"] = 50

        storage = register_storage_adapter(backend, config)
        await storage.init()
        print(f"✅ Registered and initialized {backend} storage")

    # Get specific backend
    file_storage = get_storage_adapter("file")
    memory_storage = get_storage_adapter("memory")

    print(f"✅ File storage: {type(file_storage).__module__}")
    print(f"✅ Memory storage: {type(memory_storage).__module__}")

    # Store in file backend
    await file_storage.upload(
        bucket="sessions", path="demo/config.json", data=b'{"backend": "file"}'
    )
    print("✅ Stored in file backend")

    # Store in memory backend
    await memory_storage.upload(
        bucket="test", path="demo/config.json", data=b'{"backend": "memory"}'
    )
    print("✅ Stored in memory backend")

    # Verify different backends
    file_data = await file_storage.download(bucket="sessions", path="demo/config.json")
    memory_data = await memory_storage.download(bucket="test", path="demo/config.json")

    print(f"✅ File backend data: {file_data}")
    print(f"✅ Memory backend data: {memory_data}")

    # Cleanup
    await file_storage.delete(bucket="sessions", path="demo/config.json")
    print("✅ Cleaned up file backend")


async def example_error_handling():
    """Example: Proper error handling with storage adapters."""
    print("\n" + "=" * 60)
    print("Example 4: Error Handling")
    print("=" * 60)

    # Try to register unsupported backend
    try:
        register_storage_adapter("invalid_backend")
        print("❌ Should have raised ValueError")
    except ValueError as e:
        print(f"✅ Caught expected error: {e}")

    # Try to get a backend whose name is not supported at all
    try:
        # Register file first
        register_storage_adapter("file")
        # "s3" is not in SUPPORTED_BACKENDS
        get_storage_adapter("s3")
        print("❌ Should have raised ValueError")
    except ValueError as e:
        print(f"✅ Caught expected error: {str(e)[:60]}...")

    # A supported backend that was never registered is NOT an error: the
    # registry auto-registers it on first use. That differs from the former
    # ACB registry, which raised for an unregistered backend.
    auto = get_storage_adapter("memory")
    print(f"✅ Unregistered 'memory' was auto-registered: {type(auto).__module__}")

    # Try to access non-existent file
    storage = get_storage_adapter("file")
    await storage.init()

    try:
        await storage.download(bucket="sessions", path="nonexistent.json")
        print("❌ Should have raised exception")
    except FileNotFoundError as e:
        print(f"✅ Caught expected error: {type(e).__name__}")


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Oneiric Storage Adapter Usage Examples")
    print("=" * 60)

    await example_file_storage()
    await example_memory_storage()
    await example_backend_switching()
    await example_error_handling()

    print("\n" + "=" * 60)
    print("✅ All examples completed successfully!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("1. Use register_storage_adapter() to setup backends")
    print("2. Use get_storage_adapter() to retrieve configured backends")
    print("3. Always call await storage.init() before using")
    print("4. File backend persists data, memory backend is ephemeral")
    print("5. Multiple backends can coexist for different use cases")
    print(
        "\nSee session_buddy/adapters/storage_oneiric.py for the adapter "
        "implementations, and docs/migrations/ONEIRIC_MIGRATION_PLAN.md for "
        "how the registry replaced the former ACB one."
    )


if __name__ == "__main__":
    asyncio.run(main())
