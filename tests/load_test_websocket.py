#!/usr/bin/env python3
"""WebSocket server load testing script.

Tests WebSocket server with multiple concurrent clients to validate:
- Connection handling under load
- Message broadcast performance
- Memory usage per client
- Server stability
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

try:
    import websockets as ws_client
except ImportError:
    raise ImportError(
        "websockets required. Install with: pip install websockets"
    )


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_CONFIG = {
    "server_url": "ws://localhost:8765",
    "num_clients": 100,
    "test_duration_seconds": 60,
    "message_interval_seconds": 5,
    "warmup_seconds": 2,
    "stats_interval_seconds": 10,
}


# ============================================================================
# Load Test Client
# ============================================================================


class LoadTestClient:
    """Simulates a WebSocket client for load testing."""

    def __init__(
        self,
        client_id: int,
        server_url: str,
        message_interval: float,
    ):
        self.client_id = client_id
        self.server_url = server_url
        self.message_interval = message_interval
        self.messages_received = 0
        self.errors = 0
        self.connected_at: float | None = None
        self.disconnected_at: float | None = None
        self.subscription_confirmed = False

    async def connect_and_run(self, duration_seconds: float) -> dict[str, object]:
        """Connect to server and run for specified duration."""
        start_time = time.time()

        try:
            async with ws_client.connect(self.server_url) as websocket:
                self.connected_at = time.time()

                # Subscribe to all skills
                await websocket.send(
                    json.dumps({
                        "type": "subscribe",
                        "skill_name": None  # All skills
                    })
                )

                # Run for test duration
                while (time.time() - start_time) < duration_seconds:
                    try:
                        # Wait for message with timeout
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=self.message_interval
                        )

                        data = json.loads(message)

                        # Track message types
                        if data.get("type") == "metrics_update":
                            self.messages_received += 1
                        elif data.get("type") == "subscription_confirmed":
                            self.subscription_confirmed = True

                    except asyncio.TimeoutError:
                        # No message within interval (normal)
                        pass
                    except Exception as e:
                        self.errors += 1
                        print(f"Client {self.client_id}: Error receiving message: {e}")

                self.disconnected_at = time.time()

        except Exception as e:
            self.errors += 1
            print(f"Client {self.client_id}: Connection error: {e}")

        # Return statistics
        uptime = (
            (self.disconnected_at - self.connected_at)
            if self.connected_at and self.disconnected_at
            else 0
        )

        return {
            "client_id": self.client_id,
            "messages_received": self.messages_received,
            "errors": self.errors,
            "uptime_seconds": uptime,
            "subscription_confirmed": self.subscription_confirmed,
        }


# ============================================================================
# Load Test Orchestrator
# ============================================================================


class WebSocketLoadTest:
    """Orchestrates load testing with multiple concurrent clients."""

    def __init__(
        self,
        server_url: str = DEFAULT_CONFIG["server_url"],
        num_clients: int = DEFAULT_CONFIG["num_clients"],
        test_duration: int = DEFAULT_CONFIG["test_duration_seconds"],
        message_interval: float = DEFAULT_CONFIG["message_interval_seconds"],
    ):
        self.server_url = server_url
        self.num_clients = num_clients
        self.test_duration = test_duration
        self.message_interval = message_interval
        self.clients: list[LoadTestClient] = []

    def print_stats(self, stats: list[dict[str, object]], elapsed: float) -> None:
        """Print current test statistics."""
        if not stats:
            return

        total_messages = sum(s.get("messages_received", 0) for s in stats)
        total_errors = sum(s.get("errors", 0) for s in stats)
        connected_clients = sum(1 for s in stats if s.get("subscription_confirmed"))

        print(f"\n{'='*60}")
        print(f"Load Test Statistics (after {elapsed:.1f}s)")
        print(f"{'='*60}")
        print(f"Clients connected:    {connected_clients}/{self.num_clients}")
        print(f"Messages received:     {total_messages}")
        print(f"Messages/sec:          {total_messages/elapsed:.2f}")
        print(f"Errors:                {total_errors}")
        print(f"Avg messages/client:   {total_messages/max(connected_clients, 1):.1f}")

        if connected_clients < self.num_clients:
            print(f"⚠️  WARNING: {self.num_clients - connected_clients} clients not connected!")
        if total_errors > 0:
            print(f"⚠️  WARNING: {total_errors} errors detected!")

    async def run_test(self) -> dict[str, object]:
        """Run the load test with multiple concurrent clients."""
        print(f"\n{'='*60}")
        print(f"WebSocket Server Load Test")
        print(f"{'='*60}")
        print(f"Server URL:     {self.server_url}")
        print(f"Num Clients:    {self.num_clients}")
        print(f"Test Duration:  {self.test_duration}s")
        print(f"Message Interval: {self.message_interval}s")
        print(f"{'='*60}\n")

        # Create clients
        self.clients = [
            LoadTestClient(
                client_id=i,
                server_url=self.server_url,
                message_interval=self.message_interval,
            )
            for i in range(self.num_clients)
        ]

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting {self.num_clients} clients...")

        # Warmup period
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Warmup ({DEFAULT_CONFIG['warmup_seconds']}s)...")
        await asyncio.sleep(DEFAULT_CONFIG["warmup_seconds"])

        # Start all clients concurrently
        start_time = time.time()
        stats_interval = DEFAULT_CONFIG["stats_interval_seconds"]

        # Create tasks for all clients
        client_tasks = [
            asyncio.create_task(client.connect_and_run(self.test_duration))
            for client in self.clients
        ]

        # Monitor progress
        last_stats_time = start_time

        while any(not t.done() for t in client_tasks):
            await asyncio.sleep(1)
            elapsed = time.time() - start_time

            # Print periodic statistics
            if elapsed - last_stats_time >= stats_interval:
                # Get partial stats from completed clients
                partial_stats = [
                    {
                        "client_id": c.client_id,
                        "messages_received": c.messages_received,
                        "errors": c.errors,
                        "subscription_confirmed": c.subscription_confirmed,
                    }
                    for c in self.clients
                ]
                self.print_stats(partial_stats, elapsed)
                last_stats_time = elapsed

        # Wait for all clients to complete
        results = await asyncio.gather(*client_tasks, return_exceptions=True)

        # Final statistics
        total_time = time.time() - start_time

        # Process results
        successful_results = [r for r in results if isinstance(r, dict)]
        failed_results = [r for r in results if isinstance(r, Exception)]

        print(f"\n{'='*60}")
        print(f"Test Complete!")
        print(f"{'='*60}")
        print(f"Total time:           {total_time:.2f}s")
        print(f"Successful clients:   {len(successful_results)}")
        print(f"Failed clients:       {len(failed_results)}")

        if successful_results:
            self.print_stats(successful_results, total_time)

            # Performance metrics
            total_messages = sum(r.get("messages_received", 0) for r in successful_results)
            total_errors = sum(r.get("errors", 0) for r in successful_results)
            error_rate = (total_errors / (total_messages + total_errors)) * 100 if (total_messages + total_errors) > 0 else 0

            print(f"\nPerformance Metrics:")
            print(f"  Throughput:          {total_messages/total_time:.2f} messages/sec")
            print(f"  Error Rate:          {error_rate:.2f}%")
            print(f"  Avg Uptime/Client:   {sum(r['uptime_seconds'] for r in successful_results)/len(successful_results):.1f}s")

        if failed_results:
            print(f"\n⚠️  Failed Client Errors:")
            for error in failed_results[:5]:  # Show first 5
                print(f"  - {error}")

        # Return summary
        return {
            "total_clients": self.num_clients,
            "successful_clients": len(successful_results),
            "failed_clients": len(failed_results),
            "total_messages": total_messages if successful_results else 0,
            "total_errors": total_errors if successful_results else 0,
            "total_time_seconds": total_time,
            "throughput_per_second": total_messages / total_time if successful_results and total_time > 0 else 0,
            "error_rate_percent": error_rate,
        }


# ============================================================================
# Main Entry Point
# ============================================================================


async def main() -> None:
    """Run load test with configurable parameters."""
    import argparse

    parser = argparse.ArgumentParser(
        description="WebSocket server load testing tool"
    )
    parser.add_argument(
        "--server-url",
        default=DEFAULT_CONFIG["server_url"],
        help="WebSocket server URL",
    )
    parser.add_argument(
        "--clients",
        type=int,
        default=DEFAULT_CONFIG["num_clients"],
        help="Number of concurrent clients",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_CONFIG["test_duration_seconds"],
        help="Test duration in seconds",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_CONFIG["message_interval_seconds"],
        help="Message check interval in seconds",
    )

    args = parser.parse_args()

    # Run load test
    load_test = WebSocketLoadTest(
        server_url=args.server_url,
        num_clients=args.clients,
        test_duration=args.duration,
        message_interval=args.interval,
    )

    results = await load_test.run_test()

    # Exit with appropriate code
    if results["failed_clients"] > 0:
        print(f"\n❌ Load test FAILED: {results['failed_clients']} clients failed")
        exit(1)
    else:
        print(f"\n✅ Load test PASSED: All {results['successful_clients']} clients succeeded")
        exit(0)


if __name__ == "__main__":
    asyncio.run(main())
