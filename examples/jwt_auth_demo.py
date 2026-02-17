#!/usr/bin/env python3
"""JWT Authentication Demo for Session-Buddy MCP Tools.

This script demonstrates how to use JWT authentication with Session-Buddy MCP tools.

Usage:
    # Set up environment
    export SESSION_BUDDY_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

    # Run this demo
    python examples/jwt_auth_demo.py
"""

from datetime import UTC, datetime, timedelta


def demo_generate_token():
    """Generate a JWT token for Session-Buddy MCP tools."""
    # Get the secret from environment
    import os

    import jwt

    secret = os.getenv("SESSION_BUDDY_SECRET")
    if not secret:
        print("❌ SESSION_BUDDY_SECRET environment variable not set")
        print("\nGenerate a secret with:")
        print("  python -c 'import secrets; print(secrets.token_urlsafe(32))'")
        print("\nThen set it:")
        print("  export SESSION_BUDDY_SECRET='<your-secret>'")
        return None

    # Create token payload
    payload = {
        "user_id": "demo_user",
        "exp": datetime.now(tz=UTC) + timedelta(minutes=60),
        "iat": datetime.now(tz=UTC),
        "type": "access",
        "iss": "session-buddy",
    }

    # Generate token
    token = jwt.encode(payload, secret, algorithm="HS256")

    print("✅ JWT Token Generated Successfully")
    print(f"\nToken: {token}")
    print(f"\nPayload: {payload}")
    print("\nAlgorithm: HS256")
    print(f"Expires: {payload['exp']}")

    return token


def demo_validate_token(token: str):
    """Validate a JWT token."""
    import os

    import jwt

    secret = os.getenv("SESSION_BUDDY_SECRET")
    if not secret:
        print("❌ SESSION_BUDDY_SECRET environment variable not set")
        return None

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        print("\n✅ Token Validated Successfully")
        print(f"User ID: {payload['user_id']}")
        print(f"Issuer: {payload['iss']}")
        print(f"Type: {payload['type']}")
        print(f"Expires: {payload['exp']}")
        return payload
    except jwt.ExpiredSignatureError:
        print("\n❌ Token Validation Failed: Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"\n❌ Token Validation Failed: {e}")
        return None


def demo_session_buddy_auth():
    """Demonstrate Session-Buddy authentication module."""
    print("\n" + "=" * 60)
    print("Session-Buddy JWT Authentication Demo")
    print("=" * 60)

    # Import Session-Buddy auth module
    try:
        from session_buddy.mcp.auth import (
            JWTManager,
            generate_test_token,
            is_authentication_enabled,
            validate_token,
        )
    except ImportError as e:
        print(f"❌ Failed to import session_buddy.mcp.auth: {e}")
        print(
            "\nMake sure you're running this from the Session-Buddy project directory"
        )
        return

    # Check if authentication is enabled
    print("\n1. Checking Authentication Status")
    print("-" * 40)
    if is_authentication_enabled():
        print("✅ Authentication is ENABLED (SESSION_BUDDY_SECRET is set)")
    else:
        print("⚠️  Authentication is DISABLED (SESSION_BUDDY_SECRET not set)")
        print("\nTo enable authentication:")
        print(
            "  export SESSION_BUDDY_SECRET='$(python -c \"import secrets; print(secrets.token_urlsafe(32))\")'"
        )
        return

    # Create JWT manager
    print("\n2. Creating JWT Manager")
    print("-" * 40)
    try:
        manager = JWTManager()
        print("✅ JWT Manager initialized")
        print(f"   Algorithm: {manager.algorithm}")
        print(f"   Expiration: {manager.expire_minutes} minutes")
    except Exception as e:
        print(f"❌ Failed to create JWT Manager: {e}")
        return

    # Generate a token
    print("\n3. Generating Token")
    print("-" * 40)
    try:
        token = manager.create_token(
            user_id="demo_user",
            additional_claims={"role": "developer", "projects": ["mahavishnu"]},
        )
        print("✅ Token created successfully")
        print(f"   Token (first 50 chars): {token[:50]}...")
    except Exception as e:
        print(f"❌ Failed to generate token: {e}")
        return

    # Verify the token
    print("\n4. Verifying Token")
    print("-" * 40)
    try:
        payload = manager.verify_token(token)
        print("✅ Token verified successfully")
        print(f"   User ID: {payload['user_id']}")
        print(f"   Role: {payload.get('role', 'N/A')}")
        print(f"   Projects: {payload.get('projects', 'N/A')}")
        print(f"   Issuer: {payload['iss']}")
    except Exception as e:
        print(f"❌ Failed to verify token: {e}")
        return

    # Test validation function
    print("\n5. Testing Validation Function")
    print("-" * 40)
    payload = validate_token(token)
    if payload:
        print("✅ Token validated via validate_token()")
        print(f"   User ID: {payload['user_id']}")
    else:
        print("❌ Token validation failed")

    # Test invalid token
    print("\n6. Testing Invalid Token")
    print("-" * 40)
    invalid_token = "invalid.token.here"
    payload = validate_token(invalid_token)
    if payload is None:
        print("✅ Invalid token correctly rejected")
        from session_buddy.mcp.auth import get_auth_error

        print(f"   Error: {get_auth_error()}")
    else:
        print("❌ Invalid token was not rejected")

    # Refresh token
    print("\n7. Refreshing Token")
    print("-" * 40)
    try:
        new_token = manager.refresh_token(token)
        print("✅ Token refreshed successfully")
        print(f"   New token (first 50 chars): {new_token[:50]}...")

        # Verify refreshed token has extended expiration
        new_payload = manager.verify_token(new_token)
        print(f"   Refreshed at: {new_payload.get('refreshed_at', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed to refresh token: {e}")

    # Test generate_test_token utility
    print("\n8. Testing generate_test_token() Utility")
    print("-" * 40)
    try:
        test_token = generate_test_token("test_user")
        print("✅ Test token generated")
        print(f"   Token (first 50 chars): {test_token[:50]}...")
    except Exception as e:
        print(f"❌ Failed to generate test token: {e}")

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


def demo_mcp_tool_integration():
    """Demonstrate how to use JWT auth with MCP tools."""
    print("\n" + "=" * 60)
    print("MCP Tool Integration Example")
    print("=" * 60)

    print("\nTo use JWT authentication with MCP tools:")
    print("-" * 40)

    print("""
# 1. Generate a token (as shown above)
token = "<your-jwt-token>"

# 2. Call MCP tools with the token parameter
result = await mcp.call_tool(
    "start_session",
    {
        "working_directory": "/path/to/project",
        "token": token  # Include JWT token
    }
)

# 3. If authentication is enabled and token is valid:
#    - Tool executes normally
#    - User ID from token is available in the tool

# 4. If authentication is enabled but token is invalid:
#    - Tool returns error message
#    - Error details available via get_auth_error()

# 5. If authentication is disabled (no SESSION_BUDDY_SECRET):
#    - Tools work normally without token validation
#    - Backward compatible with existing clients
    """)

    print("\nExample protected tool definition:")
    print("-" * 40)

    print("""
from session_buddy.mcp.auth import require_auth

@mcp_server.tool()
@require_auth()  # Enable JWT authentication
async def protected_operation(
    project_path: str,
    token: str,  # Token parameter required by decorator
) -> str:
    '''Protected operation requiring authentication.'''
    # If we reach here, token has been validated
    # user_id is automatically added to kwargs
    return f"Operation authorized for {user_id}"
    """)


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("JWT Authentication Demo for Session-Buddy")
    print("=" * 60)

    # Check environment
    import os

    if not os.getenv("SESSION_BUDDY_SECRET"):
        print("\n⚠️  SESSION_BUDDY_SECRET not set")
        print("\nGenerate a secret with:")
        print("  python -c 'import secrets; print(secrets.token_urlsafe(32))'")
        print("\nThen set it:")
        print("  export SESSION_BUDDY_SECRET='<your-secret>'")
        print("\nContinuing with demo (will fail without secret)...")

    # Run demos
    demo_session_buddy_auth()
    demo_mcp_tool_integration()

    print("\n✅ For more information, see:")
    print("   - session_buddy/mcp/auth.py (implementation)")
    print("   - Session-Buddy CLAUDE.md (documentation)")


if __name__ == "__main__":
    main()
