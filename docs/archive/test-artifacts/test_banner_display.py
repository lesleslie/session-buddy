#!/usr/bin/env python3
"""Test script to verify shell banner display."""

import sys
from pathlib import Path

# Add session-buddy to path
sys.path.insert(0, str(Path(__file__).parent))

from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.shell.adapter import SessionBuddyShell
from oneiric.shell import ShellConfig


def test_session_buddy_banner():
    """Test SessionBuddyShell banner display."""
    print("=" * 80)
    print("Testing SessionBuddyShell Banner Display")
    print("=" * 80)

    # Create app with minimal config
    app = SessionLifecycleManager()

    # Create shell
    config = ShellConfig(cli_preprocessing_enabled=False)
    shell = SessionBuddyShell(app, config)

    # Get and display banner
    banner = shell._get_banner()
    print("\n" + banner)

    # Verify banner content
    print("\n" + "=" * 80)
    print("Banner Verification:")
    print("=" * 80)

    checks = [
        ("Session-Buddy Admin Shell" in banner, "Contains title"),
        ("v0.1.0" in banner or "vunknown" in banner, "Contains version"),
        ("Session Tracking:" in banner, "Contains session tracking status"),
        ("self-monitoring" in banner.lower(), "Indicates self-monitoring"),
        ("CLI Commands:" in banner, "Contains CLI commands section"),
        ("Convenience Functions:" in banner, "Contains convenience functions"),
    ]

    all_passed = True
    for check, description in checks:
        status = "✓" if check else "✗"
        print(f"{status} {description}")
        if not check:
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ All banner checks passed!")
    else:
        print("✗ Some banner checks failed!")
    print("=" * 80)


if __name__ == "__main__":
    test_session_buddy_banner()
