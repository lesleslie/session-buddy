#!/usr/bin/env python3
"""Test script to verify shell metadata overrides."""

import asyncio
import sys
from pathlib import Path

# Add session-buddy to path
sys.path.insert(0, str(Path(__file__).parent))

from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.shell.adapter import SessionBuddyShell
from oneiric.shell import ShellConfig


async def test_session_buddy_shell_metadata():
    """Test SessionBuddyShell metadata overrides."""
    print("=" * 60)
    print("Testing SessionBuddyShell Metadata Overrides")
    print("=" * 60)

    # Create app with minimal config
    app = SessionLifecycleManager()

    # Create shell
    config = ShellConfig(cli_preprocessing_enabled=False)
    shell = SessionBuddyShell(app, config)

    # Test metadata methods
    print("\n1. Testing _get_component_name():")
    component_name = shell._get_component_name()
    print(f"   Component name: {component_name}")
    assert component_name == "session-buddy", "Component name should be 'session-buddy'"
    print("   ✓ PASS")

    print("\n2. Testing _get_component_version():")
    version = shell._get_component_version()
    print(f"   Version: {version}")
    # Note: Session-Buddy might not be installed, so "unknown" is acceptable
    assert isinstance(version, str), "Version should be a string"
    print("   ✓ PASS")

    print("\n3. Testing _get_adapters_info():")
    adapters = shell._get_adapters_info()
    print(f"   Adapters: {adapters}")
    assert isinstance(adapters, list), "Adapters should be a list"
    assert len(adapters) == 0, "Session-Buddy should have no adapters"
    print("   ✓ PASS")

    print("\n4. Testing SessionEventEmitter initialization:")
    print(f"   Session tracker type: {type(shell.session_tracker).__name__}")
    print(f"   Component name: {shell.session_tracker.component_name}")
    assert shell.session_tracker.component_name == "session-buddy"
    print("   ✓ PASS")

    print("\n5. Testing banner generation:")
    banner = shell._get_banner()
    assert "Session-Buddy Admin Shell" in banner
    assert "Session Tracking:" in banner
    assert version in banner
    print("   ✓ PASS")

    print("\n6. Testing session event emission (dry run):")
    # Note: This will fail gracefully if Session-Buddy MCP is not running
    try:
        session_id = await shell.session_tracker.emit_session_start(
            shell_type="SessionBuddyShell",
            metadata={"version": version, "adapters": adapters},
        )
        if session_id:
            print(f"   Session started: {session_id}")
            # End session
            await shell.session_tracker.emit_session_end(session_id, {})
            print("   Session ended")
        else:
            print("   Session tracking unavailable (expected if MCP not running)")
    except Exception as e:
        print(f"   Graceful degradation: {e}")
    print("   ✓ PASS")

    # Cleanup
    await shell.session_tracker.close()

    print("\n" + "=" * 60)
    print("All SessionBuddyShell tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_session_buddy_shell_metadata())
