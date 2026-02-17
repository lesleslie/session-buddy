# Package Reorganization Proposals

## Current Structure Analysis

### Problems Identified

1. **Root Directory Clutter**: 31 Python files in the root `session_buddy/` directory
1. **Feature Fragmentation**: Related features split across multiple directories:
   - Memory/Reflection: `reflection_tools.py` (root), `memory_tools.py` (tools/), `knowledge_graph_db.py` (root), `knowledge_graph_tools.py` (tools/)
   - Search: `advanced_search.py` (root), `search_enhanced.py` (root), `search_tools.py` (tools/)
   - Server: `server.py`, `server_core.py`, `server_optimized.py` (all root)
   - Quality: `quality_engine.py` (root), `quality_metrics.py` (tools/), `quality_utils.py` (utils/), `quality_utils_v2.py` (utils/)
1. **Utils Directory**: 15 files with mixed concerns - not descriptive
1. **Tools Directory**: Mixes MCP tool implementations with utility code

### Current File Count

- **Total Python files**: 71
- **Root directory**: 31 files
- **Tools directory**: 19 files
- **Utils directory**: 15 files
- **Core directory**: 1 file
- **DI directory**: 3 files

______________________________________________________________________

## Solution 1: Feature-Based Organization (Domain-Driven Design)

### Philosophy

Organize by **feature domains** where each directory contains ALL code for that feature (models, tools, services, utilities).

### Structure

```
session_buddy/
├── __init__.py
├── __main__.py
├── cli.py                      # CLI entry point
├── types.py                    # Shared types
│
├── server/                     # MCP Server Domain
│   ├── __init__.py
│   ├── server.py              # Main MCP server (FastMCP)
│   ├── server_core.py         # Core server logic
│   ├── server_optimized.py    # Optimizations
│   └── settings.py            # Server settings
│
├── session/                    # Session Management Domain
│   ├── __init__.py
│   ├── manager.py             # Core session manager (from core/)
│   ├── commands.py            # Session commands
│   ├── tools.py               # MCP tools for sessions (from tools/)
│   ├── coordinator.py         # Multi-project coordinator
│   └── permissions.py         # Session permissions
│
├── memory/                     # Memory & Reflection Domain
│   ├── __init__.py
│   ├── reflection_db.py       # DuckDB reflection storage (reflection_tools.py)
│   ├── knowledge_graph.py     # Knowledge graph DB
│   ├── team_knowledge.py      # Team knowledge features
│   ├── tools.py               # MCP memory tools (from tools/)
│   ├── optimizer.py           # Memory optimization
│   └── validated_tools.py     # Validated memory tools (from tools/)
│
├── search/                     # Search Domain
│   ├── __init__.py
│   ├── advanced.py            # Advanced search (advanced_search.py)
│   ├── enhanced.py            # Enhanced search (search_enhanced.py)
│   ├── tools.py               # MCP search tools (from tools/)
│   └── token_optimizer.py     # Token optimization
│
├── quality/                    # Code Quality Domain
│   ├── __init__.py
│   ├── engine.py              # Quality engine (quality_engine.py)
│   ├── metrics.py             # Quality metrics (from tools/)
│   ├── assessment.py          # Quality utils v1 (from utils/)
│   └── assessment_v2.py       # Quality utils v2 (from utils/)
│
├── crackerjack/               # Crackerjack Integration Domain
│   ├── __init__.py
│   ├── integration.py         # Integration layer
│   └── tools.py               # MCP crackerjack tools (from tools/)
│
├── llm/                        # LLM Integration Domain
│   ├── __init__.py
│   ├── providers.py           # LLM provider management
│   └── tools.py               # MCP LLM tools (from tools/)
│
├── monitoring/                 # Monitoring & Health Domain
│   ├── __init__.py
│   ├── app_monitor.py         # Application monitoring
│   ├── health_checks.py       # Health checks
│   ├── tools.py               # MCP monitoring tools (from tools/)
│   └── interruption_manager.py
│
├── serverless/                 # Serverless Mode Domain
│   ├── __init__.py
│   ├── mode.py                # Serverless mode (serverless_mode.py)
│   └── tools.py               # MCP serverless tools (from tools/)
│
├── advanced/                   # Advanced Features Domain
│   ├── __init__.py
│   ├── features.py            # Advanced features
│   ├── scheduler.py           # Natural scheduler
│   ├── worktree_manager.py    # Git worktree management
│   └── context_manager.py     # Context management
│
├── infrastructure/             # Infrastructure & Utilities
│   ├── __init__.py
│   ├── git/
│   │   ├── __init__.py
│   │   ├── operations.py      # Git operations (from utils/)
│   │   └── utils.py           # Git utils (from utils/)
│   ├── logging/
│   │   ├── __init__.py
│   │   ├── session_logger.py  # SessionLogger (from utils/)
│   │   └── utils.py           # Logging utils (from utils/)
│   ├── database/
│   │   ├── __init__.py
│   │   └── pool.py            # Database pool (from utils/)
│   ├── file_utils.py          # File utilities
│   ├── format_utils.py        # Format utilities
│   ├── regex_patterns.py      # Regex patterns
│   └── reflection_utils.py    # Reflection utilities
│
├── models/                     # Data Models & Parameter Models
│   ├── __init__.py
│   └── parameters.py          # Parameter models
│
├── resources/                  # Resource Management
│   ├── __init__.py
│   ├── cleanup.py             # Resource cleanup
│   └── shutdown_manager.py    # Shutdown management
│
├── cache/                      # Cache Adapters
│   ├── __init__.py
│   └── adapter.py             # ACB cache adapter
│
└── di/                         # Dependency Injection (Keep as-is)
    ├── __init__.py
    ├── config.py
    └── constants.py
```

### Pros

✅ **Feature cohesion**: All code for a feature is together
✅ **Easy to understand**: Clear domain boundaries
✅ **Simple navigation**: Find memory code in `memory/`, search code in `search/`
✅ **Independent evolution**: Features can evolve separately
✅ **Clear ownership**: Each domain has a clear purpose

### Cons

❌ **Code duplication risk**: May duplicate infrastructure code
❌ **Cross-cutting concerns**: Logging, caching, DI span multiple domains
❌ **Large refactor**: Significant file movement required

### Migration Complexity

**Medium-High**: Requires moving ~60 files and updating ~200+ imports

______________________________________________________________________

## Solution 2: Layer-Based Organization (ACB-Inspired)

### Philosophy

Organize by **architectural layer** following ACB patterns: adapters, services, orchestration, tools.

### Structure

```
session_buddy/
├── __init__.py
├── __main__.py
├── cli.py
├── types.py
├── settings.py
│
├── adapters/                   # External System Integrations (ACB Pattern)
│   ├── __init__.py
│   ├── cache/
│   │   ├── __init__.py
│   │   └── acb_adapter.py     # ACB cache adapter
│   ├── database/
│   │   ├── __init__.py
│   │   ├── reflection_db.py   # DuckDB reflection storage
│   │   └── knowledge_graph.py # Knowledge graph DB
│   ├── git/
│   │   ├── __init__.py
│   │   ├── operations.py      # Git operations
│   │   └── utils.py           # Git utilities
│   ├── llm/
│   │   ├── __init__.py
│   │   └── providers.py       # LLM provider adapters
│   └── crackerjack/
│       ├── __init__.py
│       └── integration.py     # Crackerjack integration
│
├── services/                   # Business Logic Services (ACB Pattern)
│   ├── __init__.py
│   ├── session/
│   │   ├── __init__.py
│   │   ├── manager.py         # Session manager (from core/)
│   │   ├── coordinator.py     # Multi-project coordinator
│   │   └── permissions.py     # Session permissions
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── reflection.py      # Reflection service
│   │   ├── team_knowledge.py  # Team knowledge
│   │   └── optimizer.py       # Memory optimizer
│   ├── search/
│   │   ├── __init__.py
│   │   ├── advanced.py        # Advanced search
│   │   ├── enhanced.py        # Enhanced search
│   │   └── token_optimizer.py
│   ├── quality/
│   │   ├── __init__.py
│   │   ├── engine.py          # Quality engine
│   │   ├── assessment.py      # Quality assessment v1
│   │   └── assessment_v2.py   # Quality assessment v2
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── app_monitor.py
│   │   ├── health_checks.py
│   │   └── interruption_manager.py
│   └── serverless/
│       ├── __init__.py
│       └── mode.py            # Serverless mode service
│
├── orchestration/              # Workflow Orchestration
│   ├── __init__.py
│   ├── session_commands.py    # Session command orchestration
│   └── advanced_features.py   # Advanced feature orchestration
│
├── mcp/                        # MCP Server (Separate from tools)
│   ├── __init__.py
│   ├── server.py              # Main MCP server
│   ├── server_core.py         # Core server logic
│   └── server_optimized.py    # Optimizations
│
├── tools/                      # MCP Tool Implementations
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
├── models/                     # Data Models & Protocols
│   ├── __init__.py
│   └── parameters.py
│
├── utils/                      # Shared Utilities
│   ├── __init__.py
│   ├── logging.py             # Logging utilities
│   ├── logging_utils.py
│   ├── file_utils.py
│   ├── format_utils.py
│   ├── regex_patterns.py
│   ├── reflection_utils.py
│   ├── server_helpers.py
│   ├── lazy_imports.py
│   └── instance_managers.py
│
├── resources/                  # Resource Management
│   ├── __init__.py
│   ├── cleanup.py
│   └── shutdown_manager.py
│
├── advanced/                   # Advanced Features (Keep isolated)
│   ├── __init__.py
│   ├── scheduler.py           # Natural scheduler
│   ├── worktree_manager.py
│   └── context_manager.py
│
└── di/                         # Dependency Injection (Keep as-is)
    ├── __init__.py
    ├── config.py
    └── constants.py
```

### Pros

✅ **ACB alignment**: Matches ACB framework patterns
✅ **Clear separation of concerns**: Adapters, services, tools clearly separated
✅ **Crackerjack compatibility**: Similar to crackerjack structure
✅ **Testability**: Easy to mock adapters, test services independently
✅ **Scalability**: Can add new adapters/services without affecting others

### Cons

❌ **Feature discovery**: Harder to find "all memory code" - spans adapters, services, tools
❌ **Cross-layer navigation**: Need to jump between layers for single feature
❌ **Tools directory still large**: 15+ files in tools/

### Migration Complexity

**Medium**: Requires moving ~50 files and updating ~150+ imports

______________________________________________________________________

## Solution 3: Hybrid Organization (Recommended) ⭐

### Philosophy

Combine **feature cohesion** with **architectural clarity**: Group by feature at top level, use ACB layers within each feature.

### Structure

```
session_buddy/
├── __init__.py
├── __main__.py
├── cli.py
├── types.py
├── settings.py
│
├── server/                     # MCP Server Module
│   ├── __init__.py
│   ├── server.py              # Main FastMCP server
│   ├── core.py                # Core server logic (server_core.py)
│   ├── optimized.py           # Optimizations (server_optimized.py)
│   └── parameter_models.py    # Server parameter models
│
├── session/                    # Session Management Module
│   ├── __init__.py
│   ├── manager.py             # SessionManager (from core/)
│   ├── coordinator.py         # Multi-project coordinator
│   ├── permissions.py         # Session permissions
│   ├── commands.py            # Session commands orchestration
│   └── tools/                 # MCP tools for sessions
│       ├── __init__.py
│       └── session_tools.py   # MCP session tools
│
├── memory/                     # Memory & Reflection Module
│   ├── __init__.py
│   ├── adapters/              # Data storage adapters
│   │   ├── __init__.py
│   │   ├── reflection_db.py   # DuckDB reflection storage
│   │   ├── knowledge_graph.py # Knowledge graph DB
│   │   └── team_knowledge.py  # Team knowledge store
│   ├── services/              # Memory business logic
│   │   ├── __init__.py
│   │   ├── reflection.py      # Reflection service
│   │   └── optimizer.py       # Memory optimization
│   └── tools/                 # MCP tools for memory
│       ├── __init__.py
│       ├── memory_tools.py
│       ├── knowledge_graph_tools.py
│       ├── validated_memory_tools.py
│       └── team_tools.py
│
├── search/                     # Search & Discovery Module
│   ├── __init__.py
│   ├── services/              # Search business logic
│   │   ├── __init__.py
│   │   ├── advanced.py        # Advanced search features
│   │   ├── enhanced.py        # Enhanced search capabilities
│   │   └── token_optimizer.py # Token optimization
│   └── tools/                 # MCP tools for search
│       ├── __init__.py
│       └── search_tools.py
│
├── quality/                    # Code Quality Module
│   ├── __init__.py
│   ├── engine.py              # Quality engine service
│   ├── adapters/              # Quality data adapters
│   │   ├── __init__.py
│   │   ├── assessment.py      # V1 assessment (from utils/)
│   │   └── assessment_v2.py   # V2 assessment (from utils/)
│   └── tools/                 # MCP tools for quality
│       ├── __init__.py
│       └── quality_metrics.py
│
├── crackerjack/               # Crackerjack Integration Module
│   ├── __init__.py
│   ├── adapter.py             # Crackerjack adapter
│   └── tools/                 # MCP tools for crackerjack
│       ├── __init__.py
│       └── crackerjack_tools.py
│
├── llm/                        # LLM Integration Module
│   ├── __init__.py
│   ├── adapters/              # LLM provider adapters
│   │   ├── __init__.py
│   │   └── providers.py
│   └── tools/                 # MCP tools for LLM
│       ├── __init__.py
│       └── llm_tools.py
│
├── monitoring/                 # Monitoring & Health Module
│   ├── __init__.py
│   ├── services/              # Monitoring services
│   │   ├── __init__.py
│   │   ├── app_monitor.py
│   │   ├── health_checks.py
│   │   └── interruption_manager.py
│   └── tools/                 # MCP tools for monitoring
│       ├── __init__.py
│       ├── monitoring_tools.py
│       └── health_tools.py
│
├── serverless/                 # Serverless Mode Module
│   ├── __init__.py
│   ├── mode.py                # Serverless mode service
│   └── tools/                 # MCP tools for serverless
│       ├── __init__.py
│       └── serverless_tools.py
│
├── advanced/                   # Advanced Features Module
│   ├── __init__.py
│   ├── features.py            # Advanced features orchestration
│   ├── scheduler.py           # Natural scheduler
│   ├── worktree_manager.py    # Git worktree management
│   └── context_manager.py     # Context management
│
├── infrastructure/             # Shared Infrastructure (ACB-style)
│   ├── __init__.py
│   ├── git/                   # Git infrastructure
│   │   ├── __init__.py
│   │   ├── operations.py      # Git operations
│   │   └── utils.py           # Git utilities
│   ├── logging/               # Logging infrastructure
│   │   ├── __init__.py
│   │   ├── session_logger.py  # SessionLogger
│   │   └── utils.py           # Logging utilities
│   ├── database/              # Database infrastructure
│   │   ├── __init__.py
│   │   └── pool.py            # Database pool
│   ├── cache/                 # Cache infrastructure
│   │   ├── __init__.py
│   │   └── adapter.py         # ACB cache adapter
│   ├── file_utils.py          # File utilities
│   ├── format_utils.py        # Format utilities
│   ├── regex_patterns.py      # Regex patterns
│   ├── reflection_utils.py    # Reflection utilities
│   ├── server_helpers.py      # Server helpers
│   ├── lazy_imports.py        # Lazy import utilities
│   └── instance_managers.py   # Instance managers
│
├── resources/                  # Resource Management
│   ├── __init__.py
│   ├── cleanup.py             # Resource cleanup
│   └── shutdown_manager.py    # Shutdown manager
│
├── models/                     # Data Models & Protocols
│   ├── __init__.py
│   └── parameters.py          # Parameter models
│
└── di/                         # Dependency Injection (Keep as-is)
    ├── __init__.py
    ├── config.py
    └── constants.py
```

### Pros

✅ **Best of both worlds**: Feature cohesion + architectural clarity
✅ **Easy navigation**: "All memory code is in `memory/`"
✅ **Clear layers**: Within each feature: adapters → services → tools
✅ **ACB compatibility**: Follows ACB patterns within features
✅ **Scalability**: Easy to add new features or layers
✅ **Tool organization**: MCP tools co-located with their feature
✅ **Infrastructure clarity**: Shared code clearly separated

### Cons

⚠️ **More directories**: Deeper nesting (3-4 levels)
⚠️ **Import paths longer**: e.g., `from session_buddy.memory.adapters.reflection_db import ...`

### Migration Complexity

**Medium**: Requires moving ~60 files and updating ~180+ imports, but structure is intuitive

______________________________________________________________________

## Comparison Matrix

| Criteria | Solution 1: Feature-Based | Solution 2: Layer-Based | Solution 3: Hybrid (Recommended) |
|----------|---------------------------|-------------------------|----------------------------------|
| **Feature Cohesion** | ✅✅✅ Excellent | ⚠️ Moderate | ✅✅ Very Good |
| **ACB Alignment** | ⚠️ Partial | ✅✅✅ Excellent | ✅✅ Very Good |
| **Navigation Ease** | ✅✅✅ Excellent | ⚠️ Moderate | ✅✅ Very Good |
| **Testability** | ✅ Good | ✅✅✅ Excellent | ✅✅ Very Good |
| **Import Path Length** | ✅✅ Short | ✅✅ Short | ⚠️ Longer |
| **Tools Organization** | ✅✅ Good (per feature) | ⚠️ Large dir | ✅✅✅ Excellent |
| **Infrastructure Clarity** | ⚠️ May duplicate | ✅✅✅ Excellent | ✅✅ Very Good |
| **Migration Effort** | Medium-High | Medium | Medium |
| **Scalability** | ✅✅ Very Good | ✅✅✅ Excellent | ✅✅✅ Excellent |

______________________________________________________________________

## Recommendation: Solution 3 (Hybrid) ⭐

### Why Hybrid is Best

1. **Feature Discoverability**: All memory code lives in `memory/`, all search code in `search/`
1. **Architectural Clarity**: Within each feature, clear separation: `adapters/` → `services/` → `tools/`
1. **ACB Compatibility**: Follows ACB patterns while maintaining feature boundaries
1. **MCP Tool Co-location**: MCP tools live with their feature, not in giant `tools/` directory
1. **Infrastructure Separation**: Shared infrastructure clearly separated in `infrastructure/`
1. **Scalability**: Easy to add new features (new top-level dir) or layers (new subdir)

### Key Benefits Over Current Structure

1. **Reduces root clutter**: From 31 files to ~5 files
1. **Feature coherence**: No more memory code split across 4 locations
1. **Tool organization**: From 19-file tools/ to organized per-feature tools/
1. **Utils clarity**: From generic utils/ to specific infrastructure/ categories
1. **Import clarity**: `from session_buddy.memory.tools import ...` is clear

### Migration Path

**Phase 1: Infrastructure** (Low risk)

- Move utils/ → infrastructure/ with categorization
- Update imports (mostly internal)

**Phase 2: Feature modules** (Medium risk)

- Create feature directories (session/, memory/, search/, quality/)
- Move core logic first (adapters, services)
- Update DI registrations

**Phase 3: MCP tools** (Medium risk)

- Move tools/ files to feature-specific tools/ subdirectories
- Update MCP tool registrations in server.py

**Phase 4: Testing & validation** (Critical)

- Run full test suite after each phase
- Verify DI container resolves correctly
- Test MCP tool discovery

______________________________________________________________________

## Context7 ACB Patterns to Consider

From ACB documentation analysis:

### 1. Adapter Pattern (from ACB)

```text
# Each feature can have adapters/ for external integrations
memory/
├── adapters/
│   ├── reflection_db.py    # DuckDB adapter
│   └── knowledge_graph.py  # Graph DB adapter
```

### 2. Service Pattern (from ACB)

```text
# Business logic in services/
memory/
├── services/
│   ├── reflection.py       # Reflection service
│   └── optimizer.py        # Memory optimization service
```

### 3. Protocol-Based DI (from ACB 0.20.0+)

```text
# Use Protocol interfaces for services
from typing import Protocol


class ReflectionServiceProtocol(Protocol):
    async def store_reflection(self, content: str) -> str: ...
    async def search_reflections(self, query: str) -> list[dict]: ...
```

### 4. Tool Registration (from ACB MCP)

```text
# MCP tools registered per feature
@mcp.tool()
async def store_reflection(content: str) -> dict:
    service = depends.get_sync(ReflectionServiceProtocol)
    return await service.store_reflection(content)
```

______________________________________________________________________

## Implementation Example: Memory Module

### Before (Current)

```
session_buddy/
├── reflection_tools.py         # 500 LOC - DuckDB + tools mixed
├── knowledge_graph_db.py       # 300 LOC - Graph DB logic
├── team_knowledge.py           # 200 LOC - Team features
├── memory_optimizer.py         # 150 LOC - Optimization
├── tools/
│   ├── memory_tools.py         # 400 LOC - MCP tools
│   ├── knowledge_graph_tools.py # 300 LOC - MCP tools
│   ├── validated_memory_tools.py # 250 LOC - MCP tools
│   └── team_tools.py           # 200 LOC - MCP tools
└── utils/
    └── reflection_utils.py     # 100 LOC - Utilities
```

### After (Hybrid Solution 3)

```
session_buddy/
└── memory/                     # All memory code together
    ├── __init__.py
    ├── adapters/               # Data storage adapters
    │   ├── __init__.py
    │   ├── reflection_db.py    # DuckDB adapter (clean)
    │   ├── knowledge_graph.py  # Graph DB adapter (clean)
    │   └── team_knowledge.py   # Team knowledge storage
    ├── services/               # Business logic services
    │   ├── __init__.py
    │   ├── reflection.py       # Reflection service
    │   └── optimizer.py        # Memory optimization
    └── tools/                  # MCP tools for memory
        ├── __init__.py
        ├── memory_tools.py
        ├── knowledge_graph_tools.py
        ├── validated_memory_tools.py
        └── team_tools.py
```

**Benefits:**

- All memory code in one place
- Clear separation: adapters (data) → services (logic) → tools (MCP)
- Easy to find: "Where's the reflection DB?" → `memory/adapters/reflection_db.py`
- Easy to test: Mock adapters, test services, verify tools
- ACB-compatible: Follows adapter/service pattern

______________________________________________________________________

## Next Steps

1. **Review and Approve**: Choose Solution 3 (Hybrid) or propose modifications
1. **Create Migration Script**: Write automated script to move files and update imports
1. **Phase 1 Pilot**: Test migration with one module (e.g., `memory/`)
1. **Comprehensive Migration**: Apply to all modules
1. **Update Documentation**: Update CLAUDE.md, README.md with new structure
1. **CI/CD Validation**: Ensure all tests pass after migration

______________________________________________________________________

## Questions for Discussion

1. **Import path length**: Are longer paths like `from session_buddy.memory.adapters.reflection_db` acceptable?
1. **Tools organization**: Should MCP tools be co-located with features or in central `tools/`?
1. **Infrastructure naming**: Is `infrastructure/` better than `utils/` or `shared/`?
1. **Migration timing**: Should we migrate all at once or incrementally?
1. **Backward compatibility**: Do we need import aliases for external users?

______________________________________________________________________

*Generated: 2025-01-30*
*Purpose: Propose package reorganization for better maintainability and ACB alignment*
