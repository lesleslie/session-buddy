#!/usr/bin/env python3
"""Example WebSocket client for testing real-time metrics.

This script demonstrates how to connect to the Session-Buddy WebSocket server
and receive real-time skill metrics updates.

Usage:
    python examples/websocket_client_example.py
"""

import asyncio
import json
import logging

import websockets

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def subscribe_to_all_skills() -> None:
    """Connect to server and receive all skill metrics."""
    uri = "ws://localhost:8765"

    logger.info(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected successfully")

            # Receive welcome message
            message = await websocket.recv()
            data = json.loads(message)
            logger.info(f"Server: {data.get('message', 'Welcome')}")

            # Subscribe to all skills (default)
            await websocket.send(json.dumps({"type": "subscribe", "skill": None}))

            # Receive confirmation
            message = await websocket.recv()
            data = json.loads(message)
            logger.info(f"Subscription confirmed: {data}")

            # Receive metrics updates
            logger.info("Listening for metrics updates (Ctrl+C to stop)...")
            logger.info("-" * 80)

            message_count = 0
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                message_count += 1

                if data["type"] == "metrics_update":
                    timestamp = data["timestamp"]
                    top_skills = data["data"]["top_skills"]
                    anomalies = data["data"]["anomalies"]

                    logger.info(f"[{timestamp}] Update #{message_count}")
                    logger.info(f"  Top Skills: {len(top_skills)}")

                    for skill in top_skills[:5]:  # Show top 5
                        logger.info(
                            f"    - {skill['skill_name']}: "
                            f"{skill['total_invocations']} invocations, "
                            f"{skill['completion_rate']:.1f}% completion"
                        )

                    if anomalies:
                        logger.info(f"  Anomalies: {len(anomalies)}")
                        for anomaly in anomalies[:3]:
                            logger.info(
                                f"    - {anomaly['skill_name']}: "
                                f"{anomaly['anomaly_type']} "
                                f"(score: {anomaly['deviation_score']:.2f})"
                            )

                    logger.info("-" * 80)

    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"Connection closed: {e}")
    except ConnectionRefusedError:
        logger.error("Connection refused - is the server running?")
        logger.info(
            "Start server with: python -m session_buddy.realtime.websocket_server"
        )


async def subscribe_to_specific_skill(skill_name: str) -> None:
    """Connect to server and receive metrics for a specific skill."""
    uri = "ws://localhost:8765"

    logger.info(f"Connecting to {uri}...")
    logger.info(f"Subscribing to skill: {skill_name}")

    try:
        async with websockets.connect(uri) as websocket:
            # Receive welcome message
            await websocket.recv()

            # Subscribe to specific skill
            await websocket.send(json.dumps({"type": "subscribe", "skill": skill_name}))

            # Receive confirmation
            message = await websocket.recv()
            data = json.loads(message)
            logger.info(f"Subscription confirmed: {data}")

            # Receive metrics updates
            logger.info("Listening for updates...")
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                if data["type"] == "metrics_update":
                    top_skills = data["data"]["top_skills"]
                    if top_skills:
                        skill = top_skills[0]
                        logger.info(
                            f"{skill['skill_name']}: "
                            f"{skill['total_invocations']} invocations, "
                            f"{skill['completion_rate']:.1f}% completion, "
                            f"{skill['avg_duration_seconds']:.2f}s avg duration"
                        )

    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"Connection closed: {e}")
    except ConnectionRefusedError:
        logger.error("Connection refused - is the server running?")


async def test_ping_pong() -> None:
    """Test ping/pong heartbeat."""
    uri = "ws://localhost:8765"

    logger.info(f"Connecting to {uri} for ping/pong test...")

    try:
        async with websockets.connect(uri) as websocket:
            # Receive welcome message
            await websocket.recv()

            # Send ping
            logger.info("Sending ping...")
            await websocket.send(json.dumps({"type": "ping"}))

            # Receive pong
            message = await websocket.recv()
            data = json.loads(message)
            logger.info(f"Received: {data}")

            if data["type"] == "pong":
                logger.info("Ping/pong test successful!")

    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"Connection closed: {e}")
    except ConnectionRefusedError:
        logger.error("Connection refused - is the server running?")


async def main() -> None:
    """Run example client."""
    import sys

    if len(sys.argv) > 1:
        skill_name = sys.argv[1]
        if skill_name == "--test-ping":
            await test_ping_pong()
        else:
            await subscribe_to_specific_skill(skill_name)
    else:
        await subscribe_to_all_skills()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
