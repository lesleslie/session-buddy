#!/usr/bin/env python3
"""Standalone WebSocket server runner for Session-Buddy.

This script starts the real-time metrics WebSocket server.

Usage:
    python examples/run_websocket_server.py

The server will:
- Listen on ws://localhost:8765
- Broadcast metrics every 1 second
- Support client subscriptions to specific skills
- Handle graceful shutdown on Ctrl+C
"""

import asyncio
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("websocket_server.log"),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Start and run the WebSocket server."""
    from session_buddy.realtime.websocket_server import RealTimeMetricsServer

    # Default database path
    db_path = Path.cwd() / ".session-buddy" / "skills.db"

    logger.info("=" * 80)
    logger.info("Session-Buddy Real-Time Metrics WebSocket Server")
    logger.info("=" * 80)
    logger.info(f"Database: {db_path}")
    logger.info("WebSocket URL: ws://localhost:8765")
    logger.info("Update Interval: 1.0 second")
    logger.info("")
    logger.info("Clients can connect and receive:")
    logger.info("  - Top 10 skills by invocation count")
    logger.info("  - Recent anomalies (last hour)")
    logger.info("  - Skill-specific metrics (via subscription)")
    logger.info("")
    logger.info("Example client usage:")
    logger.info("  python examples/websocket_client_example.py")
    logger.info("  python examples/websocket_client_example.py pytest-run")
    logger.info("  python examples/websocket_client_example.py --test-ping")
    logger.info("")
    logger.info("Press Ctrl+C to stop the server")
    logger.info("=" * 80)

    server = RealTimeMetricsServer(
        host="localhost",
        port=8765,
        db_path=db_path,
        update_interval=1.0,
    )

    try:
        await server.start()

        # Keep server running
        logger.info("Server started successfully")
        logger.info("Waiting for connections...")

        # Run forever until interrupted
        await asyncio.Future()

    except KeyboardInterrupt:
        logger.info("\nReceived interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        await server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")
