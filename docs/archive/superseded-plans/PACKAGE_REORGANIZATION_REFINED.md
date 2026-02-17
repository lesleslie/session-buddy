# Package Reorganization Proposal (Refined with ACB Understanding)

## Executive Summary

After deep research into ACB, crackerjack, FastBlocks, and splashstand architectures, I now understand that **adapters in ACB are NOT about "data access"** - they are **external system integrations** with standardized interfaces. This document proposes a reorganization that correctly applies ACB architectural patterns.

______________________________________________________________________

## Critical ACB Understanding

### What Adapters Actually Are

**Adapters** = External System Integrations (ACB Layer 4)

- **Purpose**: Standardized interfaces to external systems/services
- **Examples in ACB**: Cache (Redis), SQL (PostgreSQL), Storage (S3), NoSQL (MongoDB)
- **Examples in crackerjack**: Type checkers (zuban), Security scanners (bandit), Formatters (ruff)
- **Examples in FastBlocks**: Templates (Jinja2), Icons (FontAwesome), Images (Cloudinary)
- **Pattern**: Protocol-based, configuration-driven, swappable implementations

**NOT Adapters in ACB sense**:

- ❌ Database access layers (these are adapter **implementations**)
- ❌ Internal data models
- ❌ Business logic services

### The ACB Architectural Layers

```
Application Layer (Your App)
    ↓
Services Layer (Business Logic with Lifecycle)
    ↓ uses
Orchestration Layer (Events, Tasks, Workflows, MCP)
    ↓ uses
Adapter Layer (External System Integrations)
    ↓ uses
Core Infrastructure (Config, DI, Logger, Context)
```

**Key Insight**: Each layer has distinct responsibilities. You don't nest adapters inside services - adapters ARE a separate layer that services **use**.

______________________________________________________________________

## Current Structure Problems (Revisited)

1. **Root Directory Clutter**: 31 Python files mixing concerns
1. **Missing Adapter Layer**: External integrations (DuckDB, Git, Crackerjack) not recognized as adapters
1. **Non-descriptive `utils/`**: Should be organized by infrastructure concern
1. **Tools/Services Confusion**: MCP tools mixed with service logic
1. **No Clear Orchestration Layer**: MCP server functionality not separated

______________________________________________________________________

## Solution: ACB-Compliant Architecture

### Proposed Structure

```
session_buddy/
├── __init__.py
├── __main__.py
├── cli.py
├── types.py
│
├── adapters/                   # ACB Layer 4: External System Integrations
│   ├── __init__.py
│   ├── database/              # Database integrations
│   │   ├── __init__.py
│   │   ├── _base.py          # DuckDB base protocol
│   │   ├── reflection_db.py  # DuckDB reflection storage (reflection_tools.py → here)
│   │   └── knowledge_graph_db.py  # Knowledge graph DB
│   ├── git/                   # Git system integration
│   │   ├── __init__.py
│   │   ├── _base.py          # Git protocol
│   │   └── operations.py     # Git operations (from utils/)
│   ├── crackerjack/          # Crackerjack integration
│   │   ├── __init__.py
│   │   ├── _base.py          # Crackerjack protocol
│   │   └── integration.py    # Crackerjack adapter
│   ├── llm/                   # LLM provider integrations
│   │   ├── __init__.py
│   │   ├── _base.py          # LLM protocol
│   │   └── providers.py      # LLM provider implementations
│   └── cache/                 # Cache integration (if needed)
│       ├── __init__.py
│       └── acb_adapter.py    # ACB cache adapter
│
├── services/                   # ACB Layer 2: Business Logic Services
│   ├── __init__.py
│   ├── session/               # Session management services
│   │   ├── __init__.py
│   │   ├── manager.py        # SessionManager (from core/)
│   │   ├── coordinator.py    # Multi-project coordinator
│   │   └── permissions.py    # Session permissions
│   ├── memory/                # Memory services
│   │   ├── __init__.py
│   │   ├── reflection.py     # Reflection service (uses reflection_db adapter)
│   │   ├── team_knowledge.py # Team knowledge service
│   │   └── optimizer.py      # Memory optimization service
│   ├── search/                # Search services
│   │   ├── __init__.py
│   │   ├── advanced.py       # Advanced search (advanced_search.py)
│   │   ├── enhanced.py       # Enhanced search (search_enhanced.py)
│   │   └── token_optimizer.py
│   ├── quality/               # Quality assessment services
│   │   ├── __init__.py
│   │   ├── engine.py         # Quality engine (quality_engine.py)
│   │   ├── v1.py             # V1 assessment (from utils/)
│   │   └── v2.py             # V2 assessment (from utils/)
│   ├── monitoring/            # Monitoring services
│   │   ├── __init__.py
│   │   ├── app_monitor.py
│   │   ├── health_checks.py
│   │   └── interruption_manager.py
│   └── serverless/            # Serverless services
│       ├── __init__.py
│       └── mode.py           # Serverless mode service
│
├── orchestration/              # ACB Layer 3: Communication & Process Management
│   ├── __init__.py
│   ├── mcp/                   # MCP Server orchestration
│   │   ├── __init__.py
│   │   ├── server.py         # Main MCP server (server.py)
│   │   ├── server_core.py    # Core server logic
│   │   └── server_optimized.py # Optimizations
│   └── advanced_features.py  # Advanced feature orchestration
│
├── tools/                      # MCP Tool Implementations (Domain Layer)
│   ├── __init__.py
│   ├── session_tools.py       # Session MCP tools
│   ├── memory_tools.py        # Memory MCP tools
│   ├── search_tools.py        # Search MCP tools
│   ├── quality_metrics.py     # Quality MCP tools
│   ├── crackerjack_tools.py   # Crackerjack MCP tools
│   ├── llm_tools.py           # LLM MCP tools
│   ├── monitoring_tools.py    # Monitoring MCP tools
│   ├── serverless_tools.py    # Serverless MCP tools
│   ├── knowledge_graph_tools.py
│   ├── validated_memory_tools.py
│   ├── team_tools.py
│   ├── health_tools.py
│   ├── prompt_tools.py
│   └── agent_analyzer.py
│
├── infrastructure/             # ACB Layer 5: Core Infrastructure
│   ├── __init__.py
│   ├── logging/
│   │   ├── __init__.py
│   │   ├── session_logger.py  # SessionLogger (from utils/)
│   │   └── utils.py           # Logging utilities
│   ├── patterns/              # Pattern management
│   │   ├── __init__.py
│   │   └── regex_patterns.py  # Regex patterns (from utils/)
│   ├── file_utils.py          # File utilities
│   ├── format_utils.py        # Format utilities
│   ├── reflection_utils.py    # Reflection utilities
│   ├── server_helpers.py      # Server helpers
│   ├── lazy_imports.py        # Lazy import utilities
│   └── instance_managers.py   # Instance managers
│
├── models/                     # Data Models & Protocols
│   ├── __init__.py
│   ├── parameters.py          # Parameter models
│   └── protocols.py           # Protocol definitions (NEW)
│
├── resources/                  # Resource Management
│   ├── __init__.py
│   ├── cleanup.py             # Resource cleanup
│   └── shutdown_manager.py    # Shutdown manager
│
├── advanced/                   # Advanced Features (Special Case)
│   ├── __init__.py
│   ├── scheduler.py           # Natural scheduler
│   ├── worktree_manager.py    # Git worktree management
│   └── context_manager.py     # Context management
│
└── di/                         # Dependency Injection (Keep as-is)
    ├── __init__.py
    ├── config.py
    └── constants.py
```

______________________________________________________________________

## Key Architectural Decisions

### 1. Adapters Are External System Integrations

**Correct ACB Pattern:**

```python
# session_buddy/adapters/database/reflection_db.py
import uuid
from contextlib import suppress
from acb.depends import depends
from acb.cleanup import CleanupMixin

# MODULE_ID at module level (ACB requirement)
MODULE_ID = uuid.UUID("01937d86-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
MODULE_STATUS = "stable"


class ReflectionDatabaseSettings(Settings):
    """Settings for DuckDB reflection database."""

    db_path: str = "~/.claude/data/reflection.duckdb"
    embedding_dim: int = 384
    connection_timeout: float = 3.0


class ReflectionDatabase(CleanupMixin):
    """DuckDB adapter for reflection storage.

    This is an ADAPTER because:
    - Integrates with external system (DuckDB)
    - Provides standardized interface
    - Swappable implementations possible (e.g., PostgreSQL, SQLite)
    - Configuration-driven
    """

    def __init__(self, settings: ReflectionDatabaseSettings | None = None):
        super().__init__()
        self.settings = settings or ReflectionDatabaseSettings()
        self._conn = None

    async def _ensure_connection(self):
        """Lazy connection initialization."""
        if self._conn is None:
            import duckdb

            self._conn = duckdb.connect(self.settings.db_path)
            self.register_resource(self._conn)
        return self._conn

    async def store_conversation(self, content: str, embedding: np.ndarray) -> str:
        """Store conversation with embedding."""
        conn = await self._ensure_connection()
        # Implementation...

    async def search_similar(self, query_embedding: np.ndarray, limit: int = 10):
        """Search for similar conversations."""
        conn = await self._ensure_connection()
        # Implementation...


# Register adapter with DI (ACB pattern)
with suppress(Exception):
    depends.set(ReflectionDatabase)
```

### 2. Services Use Adapters

**Correct Service Pattern:**

```python
# session_buddy/services/memory/reflection.py
from acb.depends import depends, Inject
from session_buddy.adapters.database import ReflectionDatabase


class ReflectionService:
    """Business logic service for reflections.

    This is a SERVICE because:
    - Contains business logic
    - Orchestrates multiple operations
    - May use multiple adapters
    - Has lifecycle management
    """

    def __init__(self):
        self._db: ReflectionDatabase | None = None

    @property
    def db(self) -> ReflectionDatabase:
        """Get database adapter via DI."""
        if self._db is None:
            self._db = depends.get_sync(ReflectionDatabase)
        return self._db

    async def store_reflection_with_tags(self, content: str, tags: list[str]) -> str:
        """Store reflection with semantic tagging (business logic)."""
        # Generate embedding
        embedding = await self._generate_embedding(content)

        # Store via adapter
        reflection_id = await self.db.store_conversation(content, embedding)

        # Add tags (business logic)
        await self._add_tags(reflection_id, tags)

        return reflection_id

    async def search_by_concept(
        self, concept: str, filters: dict | None = None
    ) -> list[dict]:
        """Conceptual search with filters (business logic)."""
        # Business logic to interpret concept
        query_embedding = await self._generate_embedding(concept)

        # Use adapter for search
        results = await self.db.search_similar(query_embedding, limit=20)

        # Apply business filters
        if filters:
            results = self._apply_filters(results, filters)

        return results
```

### 3. MCP Tools Are Domain Layer

**MCP tools live at the application/domain boundary** - they:

- Expose services to external callers (Claude)
- Provide thin wrappers around services
- Handle parameter validation
- Transform between external and internal representations

```text
# session_buddy/tools/memory_tools.py
from session_buddy.services.memory import ReflectionService
from acb.depends import depends

# Get service instance
_reflection_service = None


def _get_reflection_service() -> ReflectionService:
    global _reflection_service
    if _reflection_service is None:
        _reflection_service = depends.get_sync(ReflectionService)
    return _reflection_service


@mcp.tool()
async def store_reflection(content: str, tags: list[str] | None = None) -> dict:
    """MCP tool for storing reflections."""
    service = _get_reflection_service()
    reflection_id = await service.store_reflection_with_tags(content, tags or [])
    return {"success": True, "reflection_id": reflection_id}
```

______________________________________________________________________

## Layer Responsibilities (ACB-Compliant)

### Layer 5: Core Infrastructure

**Location**: `infrastructure/`
**Purpose**: Cross-cutting concerns
**Contents**: Logging, regex patterns, file utils, format utils
**Access Pattern**: Direct imports by all layers

### Layer 4: Adapters

**Location**: `adapters/`
**Purpose**: External system integrations
**Contents**: DuckDB, Git, Crackerjack, LLM providers
**Access Pattern**: Via dependency injection (`depends.get()`)
**Key Characteristic**: Swappable, configuration-driven

### Layer 3: Orchestration

**Location**: `orchestration/`
**Purpose**: Process management and communication
**Contents**: MCP server, event handling, workflows
**Access Pattern**: Background services, event-driven

### Layer 2: Services

**Location**: `services/`
**Purpose**: Business logic with lifecycle management
**Contents**: Session, memory, search, quality services
**Access Pattern**: Via dependency injection
**Key Characteristic**: Stateful, lifecycle-managed

### Layer 1: Tools (Domain/Application)

**Location**: `tools/`
**Purpose**: External interface (MCP protocol)
**Contents**: MCP tool implementations
**Access Pattern**: Called by MCP server
**Key Characteristic**: Thin wrappers around services

______________________________________________________________________

## Migration Strategy

### Phase 1: Create Adapter Layer (High Value, Low Risk)

**Goal**: Properly categorize external system integrations

1. Create `adapters/database/` structure
1. Move `reflection_tools.py` → `adapters/database/reflection_db.py`
1. Move `knowledge_graph_db.py` → `adapters/database/knowledge_graph_db.py`
1. Move `crackerjack_integration.py` → `adapters/crackerjack/integration.py`
1. Move git operations → `adapters/git/operations.py`
1. Add proper `_base.py` protocol files for each

**Validation**: DI container resolves all adapters correctly

### Phase 2: Extract Services (Medium Value, Medium Risk)

**Goal**: Separate business logic from adapters

1. Create `services/` structure
1. Extract business logic from `reflection_tools.py` → `services/memory/reflection.py`
1. Move `core/session_manager.py` → `services/session/manager.py`
1. Create service classes that **use** adapters via DI
1. Update service imports

**Validation**: Services properly inject adapters

### Phase 3: Organize Orchestration (Medium Value, Low Risk)

**Goal**: Separate MCP server from application logic

1. Create `orchestration/mcp/` structure
1. Move `server.py` → `orchestration/mcp/server.py`
1. Move `server_core.py` → `orchestration/mcp/server_core.py`
1. Keep MCP server separate from business services

**Validation**: MCP server correctly orchestrates services

### Phase 4: Reorganize Infrastructure (Low Value, Low Risk)

**Goal**: Clean up utils/ directory

1. Create `infrastructure/` categories
1. Move utilities with clear categorization
1. Update imports

**Validation**: All utilities remain accessible

### Phase 5: Consolidate Tools (Low Value, Medium Risk)

**Goal**: Ensure MCP tools are thin wrappers

1. Review all MCP tool implementations
1. Extract business logic to services
1. Make tools call services via DI

**Validation**: Tools are simple, services are testable

______________________________________________________________________

## Comparison with Other Projects

### FastBlocks Pattern

- **Adapters**: Templates (Jinja2), Icons (FontAwesome), Images (Cloudinary)
- **Actions**: Utility functions (our `infrastructure/`)
- **MCP**: Adapter discovery and health monitoring

**Lesson**: FastBlocks extends ACB with web-specific adapters, but follows the same pattern

### Crackerjack Pattern

- **Adapters**: Type checkers (zuban), Formatters (ruff), Security scanners (bandit)
- **Services**: Not prominent (tool-focused architecture)
- **Tools**: CLI handlers

**Lesson**: Crackerjack focuses on adapters for QA tools, lighter on services

### Our Pattern

- **Adapters**: DuckDB, Git, Crackerjack, LLM providers
- **Services**: Session, memory, search, quality
- **Orchestration**: MCP server
- **Tools**: MCP tool implementations

______________________________________________________________________

## Benefits of ACB-Compliant Architecture

### 1. Testability

- **Mock adapters easily**: Swap DuckDB for in-memory store in tests
- **Test services in isolation**: Mock adapter dependencies
- **Test tools with mocked services**: Fast unit tests

### 2. Swappability

- **Replace DuckDB with PostgreSQL**: Just swap adapter, services unchanged
- **Switch Git implementations**: Services remain the same
- **Try different LLM providers**: Configuration change only

### 3. Clarity

- **Clear boundaries**: Each layer has distinct responsibility
- **Easy navigation**: "Where's the DuckDB code?" → `adapters/database/reflection_db.py`
- **Obvious patterns**: Follow ACB conventions everywhere

### 4. Scalability

- **Add new adapters**: Just implement protocol and register
- **Add new services**: Use existing adapters
- **Add new tools**: Expose existing services

### 5. ACB Compatibility

- **Upgrade path**: Aligned with ACB 0.19.0+ patterns
- **Community patterns**: Follows established conventions
- **Documentation**: Matches ACB/FastBlocks/crackerjack examples

______________________________________________________________________

## Example: Memory Module Transformation

### Before (Current - INCORRECT)

```
session_buddy/
├── reflection_tools.py         # 500 LOC - DuckDB + service + tools mixed
├── memory_optimizer.py         # Separate file
├── team_knowledge.py           # Another separate file
└── tools/
    └── memory_tools.py         # MCP tools calling reflection_tools directly
```

**Problems**:

- Adapter (DuckDB) mixed with service logic
- No clear separation of concerns
- Can't swap database implementation
- Hard to test (must mock DuckDB in every test)

### After (ACB-Compliant - CORRECT)

```
session_buddy/
├── adapters/database/
│   ├── _base.py               # Database protocol
│   ├── reflection_db.py       # DuckDB adapter (external integration)
│   └── knowledge_graph_db.py  # Graph DB adapter
│
├── services/memory/
│   ├── reflection.py          # Reflection service (business logic)
│   ├── team_knowledge.py      # Team knowledge service
│   └── optimizer.py           # Memory optimization service
│
└── tools/
    └── memory_tools.py        # MCP tools (thin wrappers)
```

**Benefits**:

- Adapter is swappable (DuckDB → PostgreSQL just configuration change)
- Services testable in isolation (mock the adapter)
- Tools are simple wrappers (call service methods)
- Clear ACB layer compliance

______________________________________________________________________

## Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: Adapters Inside Services

```text
# WRONG: Don't put adapters as subdirectories of services
services/
└── memory/
    └── adapters/  # ❌ NO! Adapters are a separate layer
        └── duckdb.py
```

**Correct**:

```text
# RIGHT: Adapters are a separate layer
adapters/database/
└── reflection_db.py

services/memory/
└── reflection.py  # Uses adapter via DI
```

### ❌ Anti-Pattern 2: Business Logic in Adapters

```python
# WRONG: Business logic in adapter
class ReflectionDatabase:
    async def store_with_semantic_analysis(self, content: str):
        # ❌ NO! This is business logic
        tags = self._analyze_semantics(content)
        embedding = self._generate_embedding(content)
        ...
```

**Correct**:

```text
# RIGHT: Adapter only does I/O
class ReflectionDatabase:
    async def store(self, content: str, embedding: np.ndarray) -> str:
        # ✅ Simple I/O operation
        ...


# Service handles business logic
class ReflectionService:
    async def store_with_analysis(self, content: str):
        # ✅ Business logic in service
        tags = await self._analyze(content)
        embedding = await self._embed(content)
        return await self.db.store(content, embedding)
```

### ❌ Anti-Pattern 3: Deep Nesting

```text
# WRONG: Too many levels
services/
└── memory/
    ├── adapters/
    │   └── database/
    │       └── implementations/
    │           └── duckdb.py  # ❌ Too deep!
```

**Correct**:

```text
# RIGHT: Flat structure
adapters/database/
└── reflection_db.py  # ✅ Easy to find
```

______________________________________________________________________

## Migration Checklist

- [ ] Phase 1: Create adapter structure and move external integrations

  - [ ] Create `adapters/database/` with `_base.py`, `reflection_db.py`, `knowledge_graph_db.py`
  - [ ] Create `adapters/git/` with `_base.py`, `operations.py`
  - [ ] Create `adapters/crackerjack/` with `_base.py`, `integration.py`
  - [ ] Create `adapters/llm/` with `_base.py`, `providers.py`
  - [ ] Add MODULE_ID and depends.set() to all adapters
  - [ ] Test: `depends.get_sync(ReflectionDatabase)` works

- [ ] Phase 2: Extract services

  - [ ] Create `services/` structure with subdirectories
  - [ ] Extract business logic from reflection_tools.py → services/memory/reflection.py
  - [ ] Move session_manager.py → services/session/manager.py
  - [ ] Update services to use adapters via DI
  - [ ] Test: Services properly inject adapters

- [ ] Phase 3: Organize orchestration

  - [ ] Create `orchestration/mcp/` structure
  - [ ] Move server files to orchestration/
  - [ ] Test: MCP server starts and registers tools

- [ ] Phase 4: Reorganize infrastructure

  - [ ] Create `infrastructure/` with subdirectories
  - [ ] Move utilities from utils/ to infrastructure/
  - [ ] Test: All imports still work

- [ ] Phase 5: Validate tools

  - [ ] Review all MCP tool implementations
  - [ ] Ensure tools call services (not adapters directly)
  - [ ] Test: All MCP tools function correctly

- [ ] Final Validation

  - [ ] Run full test suite: `pytest`
  - [ ] Verify DI container: All depends.get() calls work
  - [ ] Check MCP tool registration: All tools discoverable
  - [ ] Update documentation: README.md, CLAUDE.md

______________________________________________________________________

## Conclusion

This refined proposal correctly applies ACB architectural patterns:

1. **Adapters are external system integrations** (Layer 4) - not data access layers
1. **Services contain business logic** (Layer 2) - and use adapters via DI
1. **MCP tools are thin wrappers** (Domain layer) - exposing services
1. **Infrastructure is cross-cutting** (Layer 5) - used by all layers
1. **Orchestration manages processes** (Layer 3) - like the MCP server

The result is:

- ✅ ACB 0.19.0+ compliant
- ✅ Testable (mock adapters, test services)
- ✅ Swappable (replace implementations via configuration)
- ✅ Clear navigation (each layer has obvious location)
- ✅ Scalable (easy to add new adapters/services/tools)
- ✅ Follows FastBlocks, crackerjack, splashstand patterns

**Recommended Next Step**: Start with Phase 1 (Adapter Layer) as a pilot, validate the pattern works, then proceed with remaining phases.

______________________________________________________________________

*Generated: 2025-01-30 (Refined)*
*Purpose: ACB-compliant package reorganization with correct adapter understanding*
