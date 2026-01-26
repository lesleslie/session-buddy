# Oneiric MCP Server Analysis & Recommendations

**Date**: 2025-01-25
**Status**: Investigation Complete
**Purpose**: Analyze Oneiric's current MCP capabilities and adapter discovery

## Executive Summary

**Key Finding**: Oneiric does **NOT** currently have an MCP server implementation. However, it has a rich adapter ecosystem (56 built-in adapters across 16 categories) and a powerful resolution system that could benefit from MCP tool exposure.

**Recommendation**: Create a Oneiric MCP server to enable:
1. Dynamic adapter discovery and querying
2. Runtime adapter management (hot-swapping, health checks)
3. Multi-project adapter coordination
4. AI agent access to Oneiric's resolution capabilities

---

## Current Oneiric Architecture

### 1. Adapter Ecosystem (56 Built-in Adapters)

**Storage (4 adapters)**:
- `local` - Local file system storage
- `s3` - AWS S3/MinIO storage
- `gcs` - Google Cloud Storage
- `azure-blob` - Azure Blob Storage

**Cache (2 adapters)**:
- `memory` - In-memory cache
- `redis` - Redis cache

**Database (4 adapters)**:
- `postgres` - PostgreSQL database
- `mysql` - MySQL database
- `sqlite` - SQLite database
- `duckdb` - DuckDB analytics database

**Vector (3 adapters)**:
- `pinecone` - Pinecone vector database
- `qdrant` - Qdrant vector database
- `agentdb` - AgentDB vector database

**Graph (3 adapters)**:
- `neo4j` - Neo4j graph database
- `arangodb` - ArangoDB graph database
- `duckdb-pgq` - DuckDB Property Graph

**Embedding (3 adapters)**:
- `openai` - OpenAI embeddings
- `sentence-transformers` - Sentence Transformers
- `onnx` - ONNX runtime embeddings

**LLM (2 adapters)**:
- `anthropic` - Anthropic Claude LLM
- `openai` - OpenAI GPT LLM

**Queue (4 adapters)**:
- `redis-streams` - Redis Streams
- `nats` - NATS messaging
- `cloud-tasks` - Google Cloud Tasks
- `pubsub` - Google Pub/Sub

**HTTP (2 adapters)**:
- `httpx` - HTTPX client
- `aiohttp` - Async HTTP client

**Messaging (9 adapters)**:
- `slack` - Slack messaging
- `twilio` - Twilio SMS/voice
- `sendgrid` - SendGrid email
- `mailgun` - Mailgun email
- `teams` - Microsoft Teams
- `webhook` - Webhook notifications
- `webpush` - Web Push notifications
- `apns` - Apple Push Notifications
- `fcm` - Firebase Cloud Messaging

**Secrets (5 adapters)**:
- `env` - Environment variables
- `file` - File-based secrets
- `aws` - AWS Secrets Manager
- `gcp` - GCP Secret Manager
- `infisical` - Infisical secrets

**Monitoring (3 adapters)**:
- `logfire` - Logfire monitoring
- `otlp` - OpenTelemetry protocols
- `sentry` - Sentry error tracking

**NoSQL (3 adapters)**:
- `mongodb` - MongoDB
- `dynamodb` - Amazon DynamoDB
- `firestore` - Google Firestore

**DNS (3 adapters)**:
- `cloudflare` - Cloudflare DNS
- `route53` - AWS Route53
- `gcdns` - Google Cloud DNS

**File Transfer (5 adapters)**:
- `ftp` - FTP file transfer
- `sftp` - SFTP file transfer
- `scp` - SCP file transfer
- `http-artifact` - HTTP artifact download
- `http-upload` - HTTP file upload

**Identity (1 adapter)**:
- `auth0` - Auth0 identity

### 2. Resolution System

**Core Class**: `oneiric.core.resolution.CandidateRegistry`

**Key Methods**:
- `register_candidate(candidate)` - Register new adapter
- `resolve(domain, key, provider, capabilities)` - Resolve adapter by precedence
- `list_active(domain)` - List active adapters for domain
- `list_shadowed(domain)` - List shadowed (inactive) adapters

**4-Tier Precedence System**:
1. Explicit override (config selections)
2. Inferred priority (ONEIRIC_STACK_ORDER env var)
3. Stack level (Z-index layering)
4. Registration order (last registered wins)

**Candidate Metadata**:
```python
class Candidate:
    domain: str  # "adapter", "service", "task", etc.
    key: str  # "cache", "storage", "database", etc.
    provider: str  # "redis", "s3", "postgres", etc.
    stack_level: int  # Higher = higher priority
    priority: int  # Explicit priority override
    factory: Callable  # Factory function
    metadata: dict  # Version, description, capabilities, owner
    source: CandidateSource  # LOCAL_PKG, REMOTE_MANIFEST, ENTRY_POINT, MANUAL
    health: Callable  # Health check function
```

### 3. Adapter Metadata

**Helper Function**: `oneiric.adapters.metadata.register_adapter_metadata()`

**Metadata Structure**:
```python
class AdapterMetadata:
    category: str  # Same as Candidate.key
    provider: str  # Adapter provider name
    factory: Callable | str  # Factory or import string
    version: str | None  # Adapter version
    description: str | None  # Human-readable description
    capabilities: list[str]  # Supported capabilities
    stack_level: int  # Precedence level
    priority: int  # Explicit priority
    requires_secrets: bool  # Whether adapter needs secrets
    settings_model: str  # Pydantic settings model
    health: Callable  # Health check function
    owner: str  # Adapter owner/maintainer
```

**Example Usage**:
```python
from oneiric.adapters.metadata import register_adapter_metadata
from oneiric.core.resolution import Resolver

resolver = Resolver()
register_adapter_metadata(
    resolver,
    package_name="myapp",
    package_path=__file__,
    adapters=[
        AdapterMetadata(
            category="storage",
            provider="s3",
            stack_level=10,
            factory=lambda: S3StorageAdapter(),
            description="Production S3 storage",
            capabilities=["read", "write", "delete", "list"],
            requires_secrets=True,
            settings_model="oneiric.adapters.storage.S3StorageSettings",
        )
    ]
)
```

### 4. Built-in Adapter Registration

**Function**: `oneiric.adapters.bootstrap.register_builtin_adapters(resolver)`

**Usage**:
```python
from oneiric.core.resolution import Resolver
from oneiric.adapters import register_builtin_adapters

resolver = Resolver()
register_builtin_adapters(resolver)  # Registers all 56 adapters

# Resolve adapter
candidate = resolver.resolve("adapter", "storage")
# Returns highest priority storage adapter
```

---

## Current MCP Status

### Oneiric MCP Server: ❌ DOES NOT EXIST

**Evidence**:
- No `server.py` or `mcp*.py` files in Oneiric package
- No references to "mcp" or "MCP" in source code
- No MCP tool decorators (`@mcp.tool()`)
- No FastMCP integration

**What Oneiric HAS**:
- CLI interface (`oneiric.cli` with Typer commands)
- Resolution system (adapter discovery)
- Lifecycle management (hot-swapping, health checks)
- Remote manifest loading (component distribution)
- Config watchers (auto-swap on config changes)

### Session Buddy MCP Server: ✅ EXISTS

**File**: `/Users/les/Projects/session-buddy/session_buddy/server.py`

**Framework**: FastMCP

**Pattern**:
```python
from fastmcp import FastMCP

mcp = FastMCP("session-buddy", lifespan=session_lifecycle)

@mcp.tool()
async def start(project_path: str | None = None) -> dict[str, Any]:
    """Start a new session."""
    ...

@mcp.tool()
async def checkpoint() -> dict[str, Any]:
    """Create session checkpoint."""
    ...
```

---

## Recommendations

### Option 1: Create Oneiric MCP Server (Recommended)

**Purpose**: Enable dynamic adapter discovery and management via MCP

**Benefits**:
- AI agents can discover available adapters at runtime
- Cross-project adapter coordination
- Hot-swapping with health checks via MCP tools
- Integration with Session Buddy for storage adapter selection

**Proposed MCP Tools**:

```python
from fastmcp import FastMCP
from oneiric.core.resolution import Resolver
from oneiric.adapters import register_builtin_adapters

mcp = FastMCP("oneiric", lifespan=lifecycle_manager)

resolver = Resolver()
register_builtin_adapters(resolver)

@mcp.tool()
async def list_adapters(
    domain: str = "adapter",
    category: str | None = None,
) -> list[dict[str, Any]]:
    """List all registered adapters.

    Args:
        domain: Component domain (adapter, service, task, etc.)
        category: Filter by category (cache, storage, database, etc.)

    Returns:
        List of adapter metadata including provider, description,
        capabilities, and active status
    """
    active = resolver.list_active(domain)
    shadowed = resolver.list_shadowed(domain)

    adapters = []
    for candidate in active + shadowed:
        if category and candidate.key != category:
            continue
        adapters.append({
            "provider": candidate.provider,
            "category": candidate.key,
            "description": candidate.metadata.get("description"),
            "capabilities": candidate.metadata.get("capabilities", []),
            "version": candidate.metadata.get("version"),
            "active": candidate in active,
            "stack_level": candidate.stack_level,
            "source": candidate.source.value,
        })

    return adapters


@mcp.tool()
async def resolve_adapter(
    category: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Resolve adapter for a category.

    Args:
        category: Adapter category (cache, storage, database, etc.)
        provider: Optional provider filter

    Returns:
        Resolved adapter metadata with factory and health check
    """
    candidate = resolver.resolve("adapter", category, provider)

    if not candidate:
        return {"error": "No adapter found"}

    return {
        "provider": candidate.provider,
        "category": candidate.key,
        "factory": str(candidate.factory),
        "description": candidate.metadata.get("description"),
        "capabilities": candidate.metadata.get("capabilities", []),
        "requires_secrets": candidate.metadata.get("requires_secrets", False),
        "settings_model": candidate.metadata.get("settings_model"),
    }


@mcp.tool()
async def get_adapter_health(
    category: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Check health of an adapter.

    Args:
        category: Adapter category
        provider: Optional provider filter

    Returns:
        Health status with True/False and optional error details
    """
    candidate = resolver.resolve("adapter", category, provider)

    if not candidate or not candidate.health:
        return {"health": "unknown", "message": "No health check available"}

    try:
        is_healthy = candidate.health()
        return {
            "health": "healthy" if is_healthy else "unhealthy",
            "provider": candidate.provider,
        }
    except Exception as e:
        return {"health": "error", "error": str(e)}


@mcp.tool()
async def list_adapter_categories() -> list[str]:
    """List all adapter categories.

    Returns:
        Sorted list of unique adapter categories
    """
    active = resolver.list_active("adapter")
    shadowed = resolver.list_shadowed("adapter")

    categories = set(c.key for c in active + shadowed)
    return sorted(categories)


@mcp.tool()
async def explain_resolution(
    category: str,
) -> dict[str, Any]:
    """Explain why a specific adapter was selected.

    Args:
        category: Adapter category to explain

    Returns:
        Detailed explanation with all candidates and scoring
    """
    # Access internal registry (requires implementation detail access)
    explanation = resolver.explain("adapter", category)

    return {
        "winner": {
            "provider": explanation.winner.provider,
            "score": explanation.winner_priority,
        } if explanation.winner else None,
        "candidates": [
            {
                "provider": entry.candidate.provider,
                "score": entry.score,
                "selected": entry.selected,
                "reasons": entry.reasons,
            }
            for entry in explanation.ordered
        ],
    }
```

**Proposed MCP Configuration** (`~/.claude/.mcp.json`):
```json
{
  "mcpServers": {
    "oneiric": {
      "command": "python",
      "args": ["-m", "oneiric.server"],
      "cwd": "/path/to/oneiric",
      "env": {
        "PYTHONPATH": "/path/to/oneiric"
      }
    }
  }
}
```

### Option 2: Add Adapter Discovery Tools to Session Buddy

**Purpose**: Enable Session Buddy to discover Oneiric storage adapters

**Benefits**:
- Tighter integration with Session Buddy's serverless mode
- No need for separate Oneiric MCP server
- Leverages existing Session Buddy MCP infrastructure

**Implementation**:
```python
# In session_buddy/tools/oneiric_tools.py

from oneiric.core.resolution import Resolver
from oneiric.adapters import register_builtin_adapters

_resolver: Resolver | None = None

def _get_resolver() -> Resolver:
    """Lazy-load Oneiric resolver."""
    global _resolver
    if _resolver is None:
        _resolver = Resolver()
        register_builtin_adapters(_resolver)
    return _resolver


@mcp.tool()
async def list_storage_adapters() -> list[dict[str, Any]]:
    """List all available Oneiric storage adapters.

    Returns:
        List of storage adapters with provider, description, and capabilities
    """
    resolver = _get_resolver()
    active = resolver.list_active("adapter")
    shadowed = resolver.list_shadowed("adapter")

    storage_adapters = []
    for candidate in active + shadowed:
        if candidate.key != "storage":
            continue

        storage_adapters.append({
            "provider": candidate.provider,
            "active": candidate in active,
            "capabilities": candidate.metadata.get("capabilities", []),
            "requires_secrets": candidate.metadata.get("requires_secrets", False),
            "settings_model": candidate.metadata.get("settings_model"),
        })

    return storage_adapters


@mcp.tool()
async def resolve_storage_adapter(
    provider: str | None = None,
) -> dict[str, Any]:
    """Resolve storage adapter by provider.

    Args:
        provider: Storage provider (local, s3, gcs, azure-blob)
            If None, returns highest priority adapter

    Returns:
        Resolved adapter metadata
    """
    resolver = _get_resolver()
    candidate = resolver.resolve("adapter", "storage", provider)

    if not candidate:
        return {"error": "No storage adapter found"}

    return {
        "provider": candidate.provider,
        "active": True,
        "factory": str(candidate.factory),
        "settings_model": candidate.metadata.get("settings_model"),
    }
```

### Option 3: Hybrid Approach (Best for Session Buddy)

**Combine Options 1 and 2**:

1. **Create Oneiric MCP Server** (Option 1) for general adapter discovery
2. **Add Session Buddy Tools** (Option 2) for storage-specific convenience

**Benefits**:
- Session Buddy gets fast, convenient access to storage adapters
- Oneiric remains reusable for other projects
- Clean separation of concerns

**Usage Example**:
```python
# In Session Buddy serverless mode
from session_buddy.tools.oneiric_tools import resolve_storage_adapter

# Auto-discover best storage adapter
adapter_info = await resolve_storage_adapter()
backend = adapter_info["provider"]  # "s3", "local", etc.

# Initialize SessionStorageAdapter with discovered backend
storage = SessionStorageAdapter(backend=backend)
```

---

## Implementation Plan

### Phase 1: Oneiric MCP Server Foundation (1-2 days)

1. **Create `oneiric/server.py`**:
   - FastMCP integration
   - Resolver initialization
   - Basic lifecycle management

2. **Implement core MCP tools**:
   - `list_adapters()` - List all adapters
   - `resolve_adapter()` - Resolve adapter by category
   - `list_adapter_categories()` - List categories

3. **Add MCP configuration**:
   - `~/.claude/.mcp.json` template
   - Documentation for setup

### Phase 2: Health & Safety Features (1 day)

1. **Add health check tools**:
   - `get_adapter_health()` - Check adapter health
   - `explain_resolution()` - Explain adapter selection

2. **Add lifecycle tools** (optional, complex):
   - `swap_adapter()` - Hot-swap adapter
   - `list_active_adapters()` - List active instances

### Phase 3: Session Buddy Integration (1 day)

1. **Create `session_buddy/tools/oneiric_tools.py`**:
   - Storage adapter discovery
   - Convenience functions for serverless mode

2. **Update `session_buddy/serverless_mode.py`**:
   - Auto-discover storage adapters
   - Remove hard-coded backend list

### Phase 4: Testing & Documentation (1 day)

1. **Add integration tests**:
   - MCP tool functionality
   - Adapter resolution accuracy
   - Health check reliability

2. **Write documentation**:
   - Oneiric MCP server setup guide
   - Session Buddy integration guide
   - Example usage patterns

**Total Time**: 4-5 days

---

## Conclusion

Oneiric has a powerful adapter ecosystem (56 adapters across 16 categories) but **no MCP server** to expose them. Creating an MCP server would enable:

1. **Dynamic Adapter Discovery**: AI agents can query available adapters at runtime
2. **Multi-Project Coordination**: Share adapter configurations across projects
3. **Hot-Swapping**: Safe adapter changes with health checks via MCP tools
4. **Session Buddy Integration**: Auto-discover storage adapters for serverless mode

**Recommended Approach**: Hybrid (Option 3)
- Create Oneiric MCP server for general adapter discovery
- Add Session Buddy-specific tools for storage adapter convenience
- Maintain clean separation while enabling tight integration

**Next Steps**:
1. Confirm interest in Oneiric MCP server
2. Decide on implementation approach (Option 1, 2, or 3)
3. Begin Phase 1 implementation if approved
