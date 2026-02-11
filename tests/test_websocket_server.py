#!/usr/bin/env python3
"""Tests for WebSocket server.

Tests real-time metrics broadcasting and WebSocket connectivity.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import websockets

from session_buddy.realtime.websocket_server import RealTimeMetricsServer
from session_buddy.storage.skills_storage import SkillsStorage


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_skills.db"


@pytest.fixture
async def populated_storage(temp_db_path: Path) -> SkillsStorage:
    """Create storage with test data."""
    # Initialize database using migration manager
    from session_buddy.storage.migrations.base import MigrationManager

    migration_dir = Path(__file__).parent.parent / "session_buddy/storage/migrations"
    manager = MigrationManager(db_path=temp_db_path, migration_dir=migration_dir)
    manager.migrate()  # Apply all migrations

    storage = SkillsStorage(db_path=temp_db_path)

    # Insert test invocations
    await asyncio.to_thread(
        storage.store_invocation,
        skill_name="pytest-run",
        invoked_at="2026-02-10T12:00:00Z",
        session_id="test-session-1",
        completed=True,
        duration_seconds=5.0,
    )

    await asyncio.to_thread(
        storage.store_invocation,
        skill_name="ruff-check",
        invoked_at="2026-02-10T12:01:00Z",
        session_id="test-session-1",
        completed=True,
        duration_seconds=2.0,
    )

    yield storage

    storage.close()


# ============================================================================
# Server Lifecycle Tests
# ============================================================================


@pytest.mark.asyncio
async def test_server_start_stop(temp_db_path: Path) -> None:
    """Test server starts and stops cleanly."""
    server = RealTimeMetricsServer(
        host="localhost", port=8766, db_path=temp_db_path
    )

    try:
        await server.start()
        assert server._running is True
        assert server._server is not None
        assert server._broadcast_task is not None
    finally:
        await server.stop()
        assert server._running is False


@pytest.mark.asyncio
async def test_server_context_manager(temp_db_path: Path) -> None:
    """Test server as async context manager."""
    async with RealTimeMetricsServer(
        host="localhost", port=8767, db_path=temp_db_path
    ) as server:
        assert server._running is True

    assert server._running is False


# ============================================================================
# Client Connection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_client_connection(populated_storage: SkillsStorage) -> None:
    """Test client can connect to server."""
    server = RealTimeMetricsServer(
        host="localhost", port=8768, db_path=populated_storage.db_path
    )

    try:
        await server.start()

        # Connect client
        async with websockets.connect(
            "ws://localhost:8768"
        ) as websocket:
            # Receive welcome message
            message = await websocket.recv()
            data = json.loads(message)
            assert data["type"] == "connected"
            assert "message" in data

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_client_receives_metrics(populated_storage: SkillsStorage) -> None:
    """Test client receives metrics updates."""
    server = RealTimeMetricsServer(
        host="localhost",
        port=8769,
        db_path=populated_storage.db_path,
        update_interval=0.5,  # Faster for testing
    )

    try:
        await server.start()

        async with websockets.connect(
            "ws://localhost:8769"
        ) as websocket:
            # Skip welcome message
            await websocket.recv()

            # Receive metrics update
            message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            data = json.loads(message)

            assert data["type"] == "metrics_update"
            assert "timestamp" in data
            assert "data" in data
            assert "top_skills" in data["data"]
            assert isinstance(data["data"]["top_skills"], list)

    finally:
        await server.stop()


# ============================================================================
# Client Registration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_client_registration(populated_storage: SkillsStorage) -> None:
    """Test client registration and unregistration."""
    server = RealTimeMetricsServer(
        host="localhost", port=8770, db_path=populated_storage.db_path
    )

    try:
        await server.start()

        # Mock websocket object
        class MockWebSocket:
            def __init__(self):
                self.remote_address = ("127.0.0.1", 12345)
                self.subscription_skill = None
                self.messages = []

            async def send(self, message):
                self.messages.append(message)

        mock_client = MockWebSocket()

        # Register client
        server.register_client(mock_client)
        assert len(server.clients) == 1
        assert mock_client in server.clients

        # Unregister client
        server.unregister_client(mock_client)
        assert len(server.clients) == 0
        assert mock_client not in server.clients

    finally:
        await server.stop()


# ============================================================================
# Subscription Tests
# ============================================================================


@pytest.mark.asyncio
async def test_skill_subscription(populated_storage: SkillsStorage) -> None:
    """Test client subscribes to specific skill."""
    server = RealTimeMetricsServer(
        host="localhost", port=8771, db_path=populated_storage.db_path
    )

    try:
        await server.start()

        async with websockets.connect(
            "ws://localhost:8771"
        ) as websocket:
            # Skip welcome message
            await websocket.recv()

            # Subscribe to specific skill
            await websocket.send(
                json.dumps({"type": "subscribe", "skill": "pytest-run"})
            )

            # Receive confirmation
            message = await websocket.recv()
            data = json.loads(message)
            assert data["type"] == "subscription_confirmed"
            assert data["skill"] == "pytest-run"

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_ping_pong(populated_storage: SkillsStorage) -> None:
    """Test ping/pong heartbeat."""
    server = RealTimeMetricsServer(
        host="localhost", port=8772, db_path=populated_storage.db_path
    )

    try:
        await server.start()

        async with websockets.connect(
            "ws://localhost:8772"
        ) as websocket:
            # Skip welcome message
            await websocket.recv()

            # Send ping
            await websocket.send(json.dumps({"type": "ping"}))

            # Receive pong
            message = await websocket.recv()
            data = json.loads(message)
            assert data["type"] == "pong"

    finally:
        await server.stop()


# ============================================================================
# Metrics Broadcasting Tests
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_metrics_multiple_clients(populated_storage: SkillsStorage) -> None:
    """Test broadcasting works with multiple clients."""
    server = RealTimeMetricsServer(
        host="localhost",
        port=8773,
        db_path=populated_storage.db_path,
        update_interval=0.5,
    )

    try:
        await server.start()

        # Connect multiple clients
        async def client_task(client_id: int) -> list[str]:
            messages = []
            async with websockets.connect(
                "ws://localhost:8773"
            ) as websocket:
                # Skip welcome
                await websocket.recv()

                # Receive metrics update
                msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                messages.append(msg)

            return messages

        # Run 3 clients concurrently
        results = await asyncio.gather(
            client_task(1),
            client_task(2),
            client_task(3),
        )

        # All clients should receive metrics
        for messages in results:
            assert len(messages) == 1
            data = json.loads(messages[0])
            assert data["type"] == "metrics_update"

    finally:
        await server.stop()


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_json_handling(populated_storage: SkillsStorage) -> None:
    """Test server handles invalid JSON gracefully."""
    server = RealTimeMetricsServer(
        host="localhost", port=8774, db_path=populated_storage.db_path
    )

    try:
        await server.start()

        async with websockets.connect(
            "ws://localhost:8774"
        ) as websocket:
            # Skip welcome
            await websocket.recv()

            # Send invalid JSON
            await websocket.send("invalid json {")

            # Server should not crash, should continue sending metrics
            message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            data = json.loads(message)
            assert data["type"] in ["metrics_update", "pong"]

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_unknown_message_type_handling(populated_storage: SkillsStorage) -> None:
    """Test server handles unknown message types gracefully."""
    server = RealTimeMetricsServer(
        host="localhost", port=8775, db_path=populated_storage.db_path
    )

    try:
        await server.start()

        async with websockets.connect(
            "ws://localhost:8775"
        ) as websocket:
            # Skip welcome
            await websocket.recv()

            # Send unknown message type
            await websocket.send(json.dumps({"type": "unknown_type"}))

            # Server should not crash
            message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            data = json.loads(message)
            assert data["type"] in ["metrics_update", "pong"]

    finally:
        await server.stop()
