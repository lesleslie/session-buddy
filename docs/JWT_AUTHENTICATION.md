# JWT Authentication for Session-Buddy MCP Tools

## Overview

Session-Buddy MCP tools now support JWT-based authentication for secure cross-project communication, compatible with Mahavishnu's authentication system using the HS256 algorithm.

## Architecture

### Security Features

- **HS256 Algorithm**: Same algorithm as Mahavishnu for cross-project compatibility
- **Environment-based Secret**: JWT secret loaded from `SESSION_BUDDY_SECRET` environment variable
- **Token Validation**: Middleware for protected MCP tools
- **Flexible Authentication**: Optional authentication (backward compatible)
- **Cross-Project Auth**: HMAC-SHA256 signatures for inter-project communication

### Components

1. **AuthConfig**: Configuration management from environment variables
1. **JWTManager**: Token creation and validation
1. **require_auth()**: Decorator for protecting MCP tools
1. **CrossProjectAuth**: Shared authentication for cross-project messages

## Setup

### 1. Generate JWT Secret

```bash
# Generate a secure secret (32+ characters)
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### 2. Set Environment Variable

```bash
# Set the secret (add to .bashrc, .zshrc, or .env)
export SESSION_BUDDY_SECRET='<your-secret-here>'

# Verify it's set
echo $SESSION_BUDDY_SECRET
```

### 3. Restart Session-Buddy MCP Server

```bash
# Restart the server to pick up the environment variable
# (method depends on your setup)
```

## Usage

### Client-Side Token Generation

Clients (e.g., Mahavishnu) generate JWT tokens to authenticate with Session-Buddy:

```python
import jwt
from datetime import UTC, datetime, timedelta

# Generate token
SECRET = "your-session-buddy-secret"
payload = {
    "user_id": "mahavishnu",
    "exp": datetime.now(tz=UTC) + timedelta(minutes=60),
    "iat": datetime.now(tz=UTC),
    "type": "access",
    "iss": "mahavishnu",  # Issuer
}
token = jwt.encode(payload, SECRET, algorithm="HS256")
```

### Using Authenticated MCP Tools

When calling Session-Buddy MCP tools, include the `token` parameter:

```python
# Via MCP client
result = await mcp.call_tool(
    "start_session",
    {
        "working_directory": "/path/to/project",
        "token": token  # JWT token from Mahavishnu
    }
)

# Via direct Python call
from session_buddy.mcp.auth import validate_token

payload = validate_token(token)
if payload:
    print(f"Authenticated as {payload['user_id']}")
else:
    print(f"Authentication failed: {get_auth_error()}")
```

## MCP Tool Integration

### Creating Protected Tools

Use the `@require_auth()` decorator to protect MCP tools:

```python
from session_buddy.mcp.auth import require_auth

@mcp_server.tool()
@require_auth()  # Enable JWT authentication
async def protected_tool(
    project_path: str,
    token: str,  # Token parameter (validated by decorator)
) -> str:
    """Protected operation requiring authentication."""
    # If we reach here, token has been validated
    # user_id is automatically added to kwargs
    return f"Operation authorized for {user_id}"
```

### Optional Authentication

Allow tools to work with or without authentication:

```python
@mcp_server.tool()
@require_auth(optional=True)  # Auth optional
async def flexible_tool(
    project_path: str,
    token: str | None = None,
) -> str:
    """Tool that works with or without authentication."""
    # Works regardless of auth status
    return "Operation completed"
```

## Token Validation Flow

```
┌─────────────────┐
│ Client Request  │
│ (with token)    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ Check if auth enabled       │
│ (SESSION_BUDDY_SECRET set?) │
└────────┬────────────────────┘
         │
    ┌────┴────┐
    │         │
   No        Yes
    │         │
    ▼         ▼
┌────────┐ ┌──────────────────┐
│ Proceed│ │ Validate token   │
│ (no    │ │ (HS256 verify)   │
│ auth)  │ └──────┬───────────┘
└────────┘        │
             ┌────┴────┐
             │         │
           Valid    Invalid
             │         │
             ▼         ▼
        ┌────────┐ ┌────────────┐
        │Execute │ │ Return     │
        │tool    │ │error       │
        └────────┘ └────────────┘
```

## Configuration Reference

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `SESSION_BUDDY_SECRET` | No | JWT secret key for token validation | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |

### Token Payload Structure

```json
{
  "user_id": "mahavishnu",
  "exp": 1735862400,
  "iat": 1735858800,
  "type": "access",
  "iss": "mahavishnu",
  "role": "orchestrator"
}
```

### Standard Claims

- `user_id`: User or system identifier
- `exp`: Expiration timestamp (Unix epoch)
- `iat`: Issued at timestamp (Unix epoch)
- `type`: Token type (typically "access")
- `iss`: Issuer identifier (e.g., "mahavishnu")

## Cross-Project Integration

### Mahavishnu Integration

Mahavishnu can authenticate with Session-Buddy using shared secret:

```python
# Mahavishnu side
from mahavishnu.core.permissions import JWTManager

mahavishnu_manager = JWTManager(config)
token = mahavishnu_manager.create_token("mahavishnu")

# Call Session-Buddy with token
result = await session_buddy.start(
    working_directory="/path/to/project",
    token=token
)
```

### Shared Secret Configuration

For cross-project authentication, use the same secret:

```bash
# In Mahavishnu environment
export MAHAVISHNU_AUTH_SECRET="shared-secret-here"

# In Session-Buddy environment
export SESSION_BUDDY_SECRET="shared-secret-here"
```

## API Reference

### AuthConfig

Configuration class for JWT authentication.

```python
from session_buddy.mcp.auth import AuthConfig

config = AuthConfig()
print(f"Enabled: {config.enabled}")
print(f"Algorithm: {config.algorithm}")
print(f"Expire minutes: {config.expire_minutes}")
```

### JWTManager

Token creation and validation.

```python
from session_buddy.mcp.auth import JWTManager

manager = JWTManager()

# Create token
token = manager.create_token(
    user_id="user123",
    additional_claims={"role": "admin"}
)

# Verify token
payload = manager.verify_token(token)

# Refresh token
new_token = manager.refresh_token(token)
```

### Utility Functions

```python
from session_buddy.mcp.auth import (
    validate_token,
    get_auth_error,
    is_authentication_enabled,
    generate_test_token,
)

# Validate token
payload = validate_token(token)
if payload is None:
    print(f"Error: {get_auth_error()}")

# Check if auth is enabled
if is_authentication_enabled():
    print("Authentication is enabled")

# Generate test token (dev only)
test_token = generate_test_token("test_user")
```

## Security Best Practices

### Secret Management

1. **Use strong secrets**: Minimum 32 characters, use `secrets.token_urlsafe(32)`
1. **Never commit secrets**: Add `.env` to `.gitignore`
1. **Rotate secrets regularly**: Every 90 days for production
1. **Use different secrets**: Different secrets for dev/staging/prod

### Token Security

1. **Short expiration**: Use 60 minutes or less for access tokens
1. **HTTPS only**: Transmit tokens only over encrypted connections
1. **Token refresh**: Implement refresh token rotation
1. **Revoke on logout**: Implement token revocation if needed

### Validation

1. **Always validate**: Never trust tokens without validation
1. **Check expiration**: Always verify token expiration
1. **Verify claims**: Validate all required claims
1. **Log failures**: Log authentication failures for security monitoring

## Troubleshooting

### Authentication Disabled

```
⚠️ JWT authentication disabled (SESSION_BUDDY_SECRET not set)
```

**Solution**: Set the `SESSION_BUDDY_SECRET` environment variable.

### Secret Too Short

```
❌ JWT secret must be at least 32 characters long
```

**Solution**: Generate a longer secret with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### Token Expired

```
❌ Authentication failed: Token has expired
```

**Solution**: Generate a new token with updated expiration.

### Invalid Token

```
❌ Authentication failed: Invalid token
```

**Solution**: Verify:

1. Token was generated with correct secret
1. Token hasn't been tampered with
1. Algorithm matches (HS256)

## Examples

See `examples/jwt_auth_demo.py` for comprehensive examples:

```bash
# Run the demo
python examples/jwt_auth_demo.py
```

## Backward Compatibility

Authentication is **optional** and **backward compatible**:

- **Without `SESSION_BUDDY_SECRET`**: Tools work normally without authentication
- **With `SESSION_BUDDY_SECRET`**: Tools validate tokens when provided
- **Existing clients**: Continue working without changes

## Migration Guide

### For Existing Clients

No changes required! Authentication is optional.

### For New Authenticated Clients

1. Generate JWT token with your system's user_id
1. Include token in MCP tool calls
1. Handle authentication errors gracefully

Example:

```python
from session_buddy.mcp.auth import validate_token, get_auth_error

# Call tool with token
result = await mcp.call_tool("start_session", {
    "working_directory": "/path/to/project",
    "token": jwt_token
})

# Handle errors
if "❌ Authentication failed" in result:
    error = get_auth_error()
    print(f"Auth error: {error}")
    # Handle error (retry, refresh token, etc.)
```

## Testing

### Generate Test Token

```python
from session_buddy.mcp.auth import generate_test_token

token = generate_test_token("test_user")
```

### Validate Test Token

```python
from session_buddy.mcp.auth import validate_token

payload = validate_token(token)
print(f"Valid: {payload is not None}")
```

### Run Demo

```bash
python examples/jwt_auth_demo.py
```

## Additional Resources

- **Implementation**: `session_buddy/mcp/auth.py`
- **Demo Script**: `examples/jwt_auth_demo.py`
- **Mahavishnu Auth**: `mahavishnu/core/permissions.py`
- **JWT Standards**: https://jwt.io/

## Security Audit

This implementation has been reviewed for:

- ✅ No hardcoded secrets
- ✅ Strong secret requirements (32+ characters)
- ✅ Token expiration enforcement
- ✅ HS256 algorithm compatibility
- ✅ Error handling without information leakage
- ✅ Cross-project compatibility
- ✅ Backward compatibility (optional auth)

For security questions or concerns, please open an issue on GitHub.
