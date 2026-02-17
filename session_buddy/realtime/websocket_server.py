"""WebSocket server for real-time skill metrics broadcasting.

This module implements a WebSocket server that broadcasts skill metrics
to connected clients for real-time dashboard monitoring.

Example:
    >>> from pathlib import Path
    >>> from session_buddy.realtime import RealTimeMetricsServer
    >>>
    >>> server = RealTimeMetricsServer(
    ...     host="localhost",
    ...     port=8765,
    ...     db_path=Path(".session-buddy/skills.db"),
    ...     update_interval=1.0
    ... )
    >>> await server.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import websockets
from websockets.exceptions import ConnectionClosed
from websockets.server import ServerConnection

from session_buddy.realtime.auth import (
    AUTH_ENABLED,
    get_authenticator,
)
from session_buddy.storage.skills_storage import SkillsStorage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class RealTimeMetricsServer:
    """WebSocket server for real-time skill metrics broadcasting.

    Broadcasts skill metrics every second to all connected clients.
    Supports subscription to all skills or specific skill monitoring.

    Attributes:
        host: Server host address
        port: Server port number
        db_path: Path to SQLite database
        update_interval: Seconds between metric broadcasts
        clients: Set of connected WebSocket clients
        storage: SkillsStorage instance for data access
        authenticator: JWT authenticator (optional)

    Example:
        >>> server = RealTimeMetricsServer(
        ...     host="localhost",
        ...     port=8765,
        ...     db_path=Path(".session-buddy/skills.db")
        ... )
        >>> await server.start()
        >>> # Later...
        >>> await server.stop()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        db_path: Path | None = None,
        update_interval: float = 1.0,
        require_auth: bool = False,
    ) -> None:
        """Initialize WebSocket server.

        Args:
            host: Server host address (default: "localhost")
            port: Server port number (default: 8765)
            db_path: Path to SQLite database (default: .session-buddy/skills.db)
            update_interval: Seconds between metric broadcasts (default: 1.0)
            require_auth: Require JWT authentication for connections
        """
        self.host = host
        self.port = port
        self.update_interval = update_interval
        self.require_auth = require_auth and AUTH_ENABLED

        # Set default database path
        if db_path is None:
            db_path = Path.cwd() / ".session-buddy" / "skills.db"
        self.db_path = db_path

        # Client management
        self.clients: set[ServerConnection] = set()

        # Storage backend
        self.storage = SkillsStorage(db_path=self.db_path)

        # JWT authenticator (optional)
        self.authenticator = get_authenticator()

        # Server state
        self._server: websockets.asyncio.server.Serve | None = None
        self._broadcast_task: asyncio.Task[None] | None = None
        self._running = False

        logger.info(
            f"RealTimeMetricsServer initialized: {host}:{port}, "
            f"db={db_path}, interval={update_interval}s, "
            f"auth={'enabled' if self.authenticator else 'disabled'}"
        )

    def register_client(self, websocket: ServerConnection) -> None:
        """Register a new WebSocket client.

        Args:
            websocket: WebSocket connection object

        Example:
            >>> server.register_client(websocket)
        """
        self.clients.add(websocket)
        # Initialize subscription to all skills
        websocket.subscription_skill = None  # None = all skills
        logger.info(
            f"Client registered: {websocket.remote_address}, "
            f"total clients: {len(self.clients)}"
        )

    def unregister_client(self, websocket: ServerConnection) -> None:
        """Remove a WebSocket client.

        Args:
            websocket: WebSocket connection object

        Example:
            >>> server.unregister_client(websocket)
        """
        self.clients.discard(websocket)
        logger.info(
            f"Client unregistered: {websocket.remote_address}, "
            f"remaining clients: {len(self.clients)}"
        )

    async def _authenticate_connection(
        self, websocket: ServerConnection
    ) -> dict[str, Any] | None:
        """Authenticate WebSocket connection using JWT.

        Args:
            websocket: WebSocket connection object

        Returns:
            User payload if authenticated, None otherwise
        """
        if not self.require_auth or self.authenticator is None:
            # Authentication not required
            return None

        try:
            # Wait for authentication message
            auth_message = await asyncio.wait_for(
                websocket.recv(),
                timeout=5.0,
            )

            data = json.loads(auth_message)
            token = data.get("token")

            if not token:
                logger.warning("Authentication failed: No token provided")
                return None

            # Verify token
            payload = self.authenticator.verify_token(token)

            if payload:
                logger.info(
                    f"Client authenticated: {websocket.remote_address}, "
                    f"user={payload.get('user_id')}"
                )
                return payload
            else:
                logger.warning(
                    f"Authentication failed: Invalid token from {websocket.remote_address}"
                )
                return None

        except TimeoutError:
            logger.warning(f"Authentication timeout: {websocket.remote_address}")
            return None
        except json.JSONDecodeError:
            logger.warning(
                f"Authentication failed: Invalid JSON from {websocket.remote_address}"
            )
            return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    async def broadcast_metrics(self) -> None:
        """Broadcast skill metrics to all connected clients.

        Runs in background task, sending metrics every update_interval seconds.
        Fetches top 10 skills and recent anomalies from database.

        Example:
            >>> await server.broadcast_metrics()
        """
        logger.info("Metrics broadcaster started")

        while self._running:
            try:
                # Fetch metrics from database
                top_skills = await asyncio.to_thread(
                    self.storage.get_top_skills, limit=10
                )

                anomalies = await asyncio.to_thread(
                    self._detect_anomalies, threshold=2.0
                )

                # Build message payload
                message = {
                    "type": "metrics_update",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "top_skills": [
                            {
                                "skill_name": skill.skill_name,
                                "total_invocations": skill.total_invocations,
                                "completion_rate": skill.completion_rate,
                                "avg_duration_seconds": skill.avg_duration_seconds,
                            }
                            for skill in top_skills
                        ],
                        "anomalies": anomalies,
                    },
                }

                # Broadcast to all clients
                if self.clients:
                    disconnected: set[ServerConnection] = set()
                    for client in self.clients:
                        try:
                            # Filter by subscription if set
                            if (
                                hasattr(client, "subscription_skill")
                                and client.subscription_skill
                            ):
                                # Client subscribed to specific skill
                                skill_data = [
                                    s
                                    for s in message["data"]["top_skills"]
                                    if s["skill_name"] == client.subscription_skill
                                ]
                                if skill_data:
                                    filtered_message = message.copy()
                                    filtered_message["data"] = {
                                        "top_skills": skill_data,
                                        "anomalies": [],
                                    }
                                    await client.send(json.dumps(filtered_message))
                            else:
                                # Client subscribed to all skills
                                await client.send(json.dumps(message))

                        except ConnectionClosed:
                            logger.debug(
                                f"Client disconnected: {client.remote_address}"
                            )
                            disconnected.add(client)
                        except Exception as e:
                            logger.error(f"Error sending to client: {e}")
                            disconnected.add(client)

                    # Clean up disconnected clients
                    for client in disconnected:
                        self.unregister_client(client)

                # Wait for next interval
                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Error in broadcast_metrics: {e}", exc_info=True)
                await asyncio.sleep(self.update_interval)

        logger.info("Metrics broadcaster stopped")

    def _detect_anomalies(self, threshold: float = 2.0) -> list[dict[str, object]]:
        """Detect skill performance anomalies.

        Queries skill_anomalies table for recent detections.

        Args:
            threshold: Z-score threshold for anomaly detection

        Returns:
            List of anomaly records:
                [
                    {
                        "skill_name": str,
                        "detected_at": str,
                        "anomaly_type": str,
                        "deviation_score": float
                    },
                    ...
                ]
        """
        try:
            with self.storage._get_connection() as conn:
                conn.row_factory = lambda cursor, row: {
                    col[0]: row[idx] for idx, col in enumerate(cursor.description)
                }
                cursor = conn.cursor()

                # Get recent anomalies (last hour)
                cursor.execute(
                    """
                    SELECT
                        skill_name,
                        detected_at,
                        anomaly_type,
                        deviation_score
                    FROM skill_anomalies
                    WHERE detected_at >= datetime('now', '-1 hour')
                    ORDER BY detected_at DESC
                    LIMIT 10
                    """
                )

                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.warning(f"Failed to detect anomalies: {e}")
            return []

    async def handle_client_message(
        self, websocket: ServerConnection, message: str
    ) -> None:
        """Handle incoming message from client.

        Args:
            websocket: WebSocket connection object
            message: JSON message from client

        Example:
            >>> await server.handle_client_message(websocket, '{"type": "subscribe", "skill": "pytest-run"}')
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "subscribe":
                skill_name = data.get("skill")
                await self.handle_subscription(websocket, skill_name)

            elif msg_type == "unsubscribe":
                websocket.subscription_skill = None
                logger.info(
                    f"Client {websocket.remote_address} unsubscribed from all skills"
                )

            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from client: {e}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")

    async def handle_subscription(
        self, websocket: ServerConnection, skill_name: str | None
    ) -> None:
        """Handle skill subscription request.

        Args:
            websocket: WebSocket connection object
            skill_name: Skill to monitor (None = all skills)

        Example:
            >>> await server.handle_subscription(websocket, "pytest-run")
        """
        websocket.subscription_skill = skill_name
        if skill_name:
            logger.info(
                f"Client {websocket.remote_address} subscribed to skill: {skill_name}"
            )
        else:
            logger.info(f"Client {websocket.remote_address} subscribed to all skills")

        # Send confirmation
        await websocket.send(
            json.dumps(
                {
                    "type": "subscription_confirmed",
                    "skill": skill_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )

    async def client_handler(self, websocket: ServerConnection) -> None:
        """Handle WebSocket client connection.

        Authenticates connection (if required), registers client,
        handles incoming messages, and cleans up on disconnect.

        Args:
            websocket: WebSocket connection object

        Example:
            >>> await server.client_handler(websocket)
        """
        # Authenticate connection (if required)
        user = None
        if self.require_auth:
            user = await self._authenticate_connection(websocket)
            if user is None:
                # Authentication failed
                await websocket.close(
                    code=4001,  # Custom close code for authentication failure
                    reason="Authentication failed",
                )
                return

            # Attach user to websocket for later reference
            websocket.user = user

        self.register_client(websocket)

        user_id = user.get("user_id") if user else "anonymous"
        logger.info(f"Client connected: {websocket.remote_address} (user: {user_id})")

        try:
            # Send welcome message
            await websocket.send(
                json.dumps(
                    {
                        "type": "connected",
                        "message": "Connected to Session-Buddy real-time metrics",
                        "authenticated": user is not None,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            )

            # Handle incoming messages
            async for message in websocket:
                await self.handle_client_message(websocket, message)

        except ConnectionClosed:
            logger.info(f"Client disconnected: {websocket.remote_address}")
        except Exception as e:
            logger.error(f"Error in client handler: {e}", exc_info=True)
        finally:
            self.unregister_client(websocket)

    async def start(self) -> None:
        """Start the WebSocket server.

        Begins listening for connections and starts metrics broadcaster.

        Example:
            >>> await server.start()
        """
        if self._running:
            logger.warning("Server already running")
            return

        self._running = True
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        # Start metrics broadcaster
        self._broadcast_task = asyncio.create_task(self.broadcast_metrics())

        # Start WebSocket server (websockets 16.0 API)
        self._server = await websockets.serve(
            self.client_handler,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
        )

        logger.info(f"WebSocket server started: ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the WebSocket server.

        Gracefully shuts down broadcaster and closes all connections.

        Example:
            >>> await server.stop()
        """
        if not self._running:
            logger.warning("Server not running")
            return

        logger.info("Stopping WebSocket server...")
        self._running = False

        # Stop broadcaster
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Close all client connections
        for client in list(self.clients):
            await client.close()
        self.clients.clear()

        # Close storage
        self.storage.close()

        logger.info("WebSocket server stopped")

    async def __aenter__(self) -> RealTimeMetricsServer:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()


# ============================================================================
# Convenience Functions
# ============================================================================


async def run_server(
    host: str = "localhost",
    port: int = 8765,
    db_path: Path | None = None,
    update_interval: float = 1.0,
    require_auth: bool = False,
) -> None:
    """Run the WebSocket server (blocking).

    Convenience function to start server and run until interrupted.

    Args:
        host: Server host address (default: "localhost")
        port: Server port number (default: 8765)
        db_path: Path to SQLite database (default: .session-buddy/skills.db)
        update_interval: Seconds between metric broadcasts (default: 1.0)
        require_auth: Require JWT authentication for connections

    Example:
        >>> import asyncio
        >>> from session_buddy.realtime.websocket_server import run_server
        >>>
        >>> asyncio.run(run_server(port=8765))
    """
    server = RealTimeMetricsServer(
        host=host,
        port=port,
        db_path=db_path,
        update_interval=update_interval,
        require_auth=require_auth,
    )

    try:
        await server.start()
        logger.info("Server running, press Ctrl+C to stop")
        # Run forever
        await asyncio.Future()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await server.stop()
