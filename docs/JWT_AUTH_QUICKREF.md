# JWT Authentication Quick Reference

## Setup (30 seconds)

```bash
# 1. Generate secret
export SESSION_BUDDY_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

# 2. Verify
echo $SESSION_BUDDY_SECRET

# 3. Done! Authentication enabled
```

## Generate Token (Client Side)

```python
import jwt
from datetime import UTC, datetime, timedelta

SECRET = os.getenv("SESSION_BUDDY_SECRET")
token = jwt.encode({
    "user_id": "mahavishnu",
    "exp": datetime.now(tz=UTC) + timedelta(minutes=60),
    "iat": datetime.now(tz=UTC),
    "type": "access",
    "iss": "mahavishnu",
}, SECRET, algorithm="HS256")
```

## Protect MCP Tool

```python
from session_buddy.mcp.auth import require_auth

@mcp_server.tool()
@require_auth()  # Add this decorator
async def my_tool(
    project_path: str,
    token: str,  # Add token parameter
) -> str:
    """Protected tool."""
    # Token auto-validated, user_id added to kwargs
    return f"Authorized for {user_id}"
```

## Call Protected Tool

```python
result = await mcp.call_tool("my_tool", {
    "project_path": "/path/to/project",
    "token": jwt_token  # Include JWT token
})
```

## Validate Token Manually

```python
from session_buddy.mcp.auth import validate_token, get_auth_error

payload = validate_token(token)
if payload:
    print(f"✅ Authenticated as {payload['user_id']}")
else:
    print(f"❌ Auth failed: {get_auth_error()}")
```

## Check Auth Status

```python
from session_buddy.mcp.auth import is_authentication_enabled

if is_authentication_enabled():
    print("✅ Authentication enabled")
else:
    print("⚠️ Authentication disabled (no SESSION_BUDDY_SECRET)")
```

## Generate Test Token

```python
from session_buddy.mcp.auth import generate_test_token

token = generate_test_token("test_user")
print(f"Test token: {token[:50]}...")
```

## Common Patterns

### Optional Authentication

```python
@require_auth(optional=True)  # Works with or without auth
async def flexible_tool(token: str | None = None) -> str:
    return "Success"
```

### Cross-Project Auth (Mahavishnu → Session-Buddy)

```python
# Mahavishnu side
from mahavishnu.core.permissions import JWTManager
manager = JWTManager(config)
token = manager.create_token("mahavishnu")

# Call Session-Buddy
result = await session_buddy.start(
    working_directory="/path/to/project",
    token=token
)
```

### Handle Auth Errors

```python
result = await mcp.call_tool("protected_tool", {
    "project_path": "/path",
    "token": token
})

if "❌ Authentication failed" in result:
    from session_buddy.mcp.auth import get_auth_error
    error = get_auth_error()
    # Handle error (retry, refresh token, etc.)
    if "expired" in error.lower():
        token = refresh_token()
    elif "invalid" in error.lower():
        token = generate_new_token()
```

## Token Payload Structure

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

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SESSION_BUDDY_SECRET` | No | None | JWT secret key (32+ chars) |

## Security Checklist

- ✅ Secret is 32+ characters
- ✅ Token expiration ≤ 60 minutes
- ✅ HTTPS for token transmission
- ✅ Never commit secrets to git
- ✅ Different secrets for dev/staging/prod
- ✅ Rotate secrets every 90 days
- ✅ Log authentication failures
- ✅ Validate all tokens

## Troubleshooting

### Auth Disabled

```
⚠️ Authentication disabled
```

**Fix**: Set `SESSION_BUDDY_SECRET`

### Secret Too Short

```
❌ JWT secret must be at least 32 characters
```

**Fix**: Generate longer secret with `secrets.token_urlsafe(32)`

### Token Expired

```
❌ Authentication failed: Token has expired
```

**Fix**: Generate new token with updated expiration

### Invalid Token

```
❌ Authentication failed: Invalid token
```

**Fix**: Verify secret matches, check token format (HS256)

## Testing

```bash
# Quick test
python -c "
from session_buddy.mcp.auth import JWTManager
manager = JWTManager()
token = manager.create_token('test')
print('Token:', token[:50] + '...')
payload = manager.verify_token(token)
print('User:', payload['user_id'])
"

# Run demo
python examples/jwt_auth_demo.py

# Run tests
python -m pytest tests/unit/test_mcp_auth.py -v
```

## Documentation

- **Full Docs**: `docs/JWT_AUTHENTICATION.md`
- **Implementation**: `session_buddy/mcp/auth.py`
- **Demo**: `examples/jwt_auth_demo.py`
- **Tests**: `tests/unit/test_mcp_auth.py`
- **Summary**: `docs/JWT_AUTH_IMPLEMENTATION_SUMMARY.md`

## Support

For issues or questions:
1. Check `docs/JWT_AUTHENTICATION.md` for detailed docs
2. Run `python examples/jwt_auth_demo.py` for examples
3. Review `tests/unit/test_mcp_auth.py` for usage patterns
4. Open GitHub issue with error details

---

**Last Updated**: 2025-02-06
**Version**: 1.0.0
**Status**: ✅ Production Ready
