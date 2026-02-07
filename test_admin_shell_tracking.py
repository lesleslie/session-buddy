#!/usr/bin/env python3
"""Test script for admin shell tracking MCP tools.

This script verifies that the admin shell tracking tools are properly
registered and functional.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_admin_shell_tracking_tools():
    """Test admin shell tracking tools registration and functionality."""

    print("=" * 60)
    print("Testing Admin Shell Tracking MCP Tools")
    print("=" * 60)

    # Import the registration function
    from session_buddy.mcp.tools.session.admin_shell_tracking_tools import (
        register_admin_shell_tracking_tools,
    )
    print("✓ Successfully imported register_admin_shell_tracking_tools")

    # Create a mock MCP server
    mock_mcp = Mock()
    mock_mcp.tool = Mock(return_value=lambda f: f)  # Pass-through decorator

    # Register tools
    register_admin_shell_tracking_tools(mock_mcp)
    print("✓ Successfully registered admin shell tracking tools")

    # Verify tools were registered
    # The decorator should have been called twice (once for each tool)
    assert mock_mcp.tool.call_count == 2, f"Expected 2 tool registrations, got {mock_mcp.tool.call_count}"
    print(f"✓ Registered {mock_mcp.tool.call_count} tools")

    # Import event models to test validation
    from session_buddy.mcp.event_models import (
        SessionStartEvent,
        SessionEndEvent,
        UserInfo,
        EnvironmentInfo,
    )
    print("✓ Successfully imported event models")

    # Test SessionStartEvent validation
    try:
        start_event = SessionStartEvent(
            event_version="1.0",
            event_id="550e8400-e29b-41d4-a716-446655440000",
            event_type="session_start",
            component_name="mahavishnu",
            shell_type="MahavishnuShell",
            timestamp="2026-02-06T12:34:56.789Z",
            pid=12345,
            user=UserInfo(username="john", home="/home/john"),
            hostname="server01",
            environment=EnvironmentInfo(
                python_version="3.13.0",
                platform="Linux-6.5.0-x86_64",
                cwd="/home/john/projects/mahavishnu"
            ),
            metadata={"test": "data"},
        )
        print("✓ SessionStartEvent validation successful")
        print(f"  - Event ID: {start_event.event_id}")
        print(f"  - Component: {start_event.component_name}")
        print(f"  - Shell Type: {start_event.shell_type}")
    except Exception as e:
        print(f"✗ SessionStartEvent validation failed: {e}")
        return False

    # Test SessionEndEvent validation
    try:
        end_event = SessionEndEvent(
            session_id="mahavishnu-20260206-123456",
            timestamp="2026-02-06T13:45:67.890Z",
            event_type="session_end",
            metadata={"exit_reason": "user_exit"},
        )
        print("✓ SessionEndEvent validation successful")
        print(f"  - Session ID: {end_event.session_id}")
        print(f"  - Status: {end_event.event_type}")
    except Exception as e:
        print(f"✗ SessionEndEvent validation failed: {e}")
        return False

    # Test SessionTracker
    from session_buddy.mcp.session_tracker import SessionTracker
    from session_buddy.core import SessionLifecycleManager

    # Create a mock lifecycle manager
    mock_lifecycle_mgr = Mock(spec=SessionLifecycleManager)
    mock_lifecycle_mgr.initialize_session = Mock(return_value={
        "success": True,
        "project": "test-project",
        "quality_score": 85,
        "quality_data": {
            "breakdown": {
                "code_quality": 30,
                "project_health": 25,
                "dev_velocity": 15,
                "security": 8,
            },
            "recommendations": [],
        },
    })
    mock_lifecycle_mgr.end_session = Mock(return_value={
        "success": True,
        "summary": {
            "project": "test-project",
            "final_quality_score": 85,
        },
    })

    # Create tracker
    tracker = SessionTracker(mock_lifecycle_mgr)
    print("✓ SessionTracker created successfully")

    # Test handle_session_start
    try:
        start_result = await tracker.handle_session_start(start_event)
        print("✓ SessionTracker.handle_session_start successful")
        print(f"  - Session ID: {start_result.session_id}")
        print(f"  - Status: {start_result.status}")
        assert start_result.status == "tracked", f"Expected 'tracked', got '{start_result.status}'"
        assert start_result.session_id is not None, "Session ID should not be None"
    except Exception as e:
        print(f"✗ SessionTracker.handle_session_start failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test handle_session_end
    try:
        end_result = await tracker.handle_session_end(end_event)
        print("✓ SessionTracker.handle_session_end successful")
        print(f"  - Session ID: {end_result.session_id}")
        print(f"  - Status: {end_result.status}")
        assert end_result.status == "ended", f"Expected 'ended', got '{end_result.status}'"
    except Exception as e:
        print(f"✗ SessionTracker.handle_session_end failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_admin_shell_tracking_tools())
    sys.exit(0 if success else 1)
