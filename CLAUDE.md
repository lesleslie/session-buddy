# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is Session Buddy, a Claude Session Management MCP (Model Context Protocol) server that provides comprehensive session management functionality for Claude Code across any project. It operates as a standalone MCP server with its own isolated environment to avoid dependency conflicts.

## Development Commands

### Installation & Setup

```bash
# Install all dependencies (development + production)
uv sync --group dev

# Install minimal dependencies only (production)
uv sync

# Run server directly as a module
python -m session_buddy.server

# Run server with debug logging
PYTHONPATH=. python -m session_buddy.server --debug

# Verify installation
python -c "from session_buddy.server import mcp; print('✅ MCP server ready')"
python -c "from session_buddy.reflection_tools import ReflectionDatabase; print('✅ Memory system ready')"
```

### Quick Start Development

```bash
# Complete development setup in one command
uv sync --group dev && \
  pytest -m "not slow" && \
  crackerjack lint
```

### Code Quality & Linting

```bash
# Lint and format code (uses Ruff with strict settings)
crackerjack lint

# Run type checking
crackerjack typecheck

# Security scanning
crackerjack security

# Code complexity analysis
crackerjack complexity

# Full quality analysis
crackerjack analyze
```

### Testing & Development

```bash
# Run comprehensive test suite with coverage
pytest

# Quick smoke tests for development (recommended during coding)
pytest -m "not slow"

# Run specific test categories
pytest tests/unit/                    # Unit tests only
pytest tests/integration/             # Integration tests only
pytest -m performance                 # Performance tests only
pytest -m security                    # Security tests only

# Run single test file with verbose output
pytest tests/unit/test_session_permissions.py -v -s

# Run tests with parallel execution (faster)
pytest -n auto

# Coverage reporting
pytest --cov=session_buddy --cov-report=term-missing

# Development debugging mode (keeps test data)
pytest -v --tb=short

# Fail build if coverage below 85%
pytest --cov=session_buddy --cov-fail-under=85

# Run tests with custom timeout
pytest --timeout=300
```

### Development Workflow Commands

```bash
# Pre-commit workflow (run before any commit)
uv sync --group dev && \
  crackerjack lint && \
  pytest -m "not slow" && \
  crackerjack typecheck

# Full quality gate (run before PR)
pytest --cov=session_buddy --cov-fail-under=85 && \
  crackerjack security && \
  crackerjack complexity

# Debug server issues
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from session_buddy.server import mcp
print('Server debug check complete')
"
```

## Architecture Overview

### Recent Architecture Changes (Phases 2.7 & 3.0 - January 2025)

**Latest Updates** (December 2025):

- **Removed sitecustomize.py** - No longer needed with Codex AI workaround; eliminated 115 lines of brittle startup-time patches
- **Updated FastAPI to >=0.124.2** - Removed upper bound constraint; FastAPI 0.121.x bugs resolved in 0.124.2+
- **Documentation Reorganization** - Archived 80 historical docs to `docs/archive/` (91% reduction in top-level clutter)

**Oneiric Adapter Migration - COMPLETE** (**Phases 2-5** - January 2025)

Both database layers have been successfully migrated to native DuckDB adapters (Oneiric):

**✅ Phase 2-3: Initial Migration** (Conversations/Reflections + Knowledge Graph)

- Created `ReflectionDatabaseAdapter` using native DuckDB vector operations (566 lines)
- Implemented `KnowledgeGraphDatabaseAdapter` with hybrid sync/async pattern (700 lines)
- Migration scripts: `scripts/migrate_vector_database.py`, `scripts/migrate_graph_database.py`
- 100% API compatibility maintained throughout

**✅ Phase 5: Oneiric Conversion** (Native DuckDB Implementation)

- **Replaced external framework dependency** with direct DuckDB operations
- **No async driver required**: DuckDB operations are fast enough (\<1ms) to safely use sync code in async contexts
- Async method signatures for API consistency, sync DuckDB operations internally
- Maintained 100% backward compatibility while simplifying the stack

**Hybrid Pattern Key Insight**:

```text
async def create_entity(self, name: str, ...) -> dict:
    """Async signature for API consistency, sync operation internally."""
    conn = self._get_conn()  # Sync DuckDB connection
    conn.execute("INSERT INTO kg_entities ...")  # Fast local operation (<1ms)
    return {"id": entity_id, ...}
```

This pattern can be applied to other fast local databases (SQLite, in-memory caches) where operations complete in microseconds and don't block the event loop.

**Complete Migration Benefits**:

- ✅ Both Vector and Graph databases use native DuckDB with Oneiric adapters
- ✅ Removed external framework dependency (simplified stack)
- ✅ Improved connection pooling and resource management
- ✅ Better testability through dependency injection
- ✅ Zero new dependencies (no `duckdb-engine` needed)
- ✅ 100% API compatibility for both adapters
- ✅ Zero breaking changes for users

**Full migration details**: `docs/migrations/ONEIRIC_MIGRATION_PLAN.md`

**Dependency Injection Migration** (**Phase 2.7 Days 1-4 completed**)

- Migrated from manual singleton management to dependency injection
- Centralized DI configuration in `session_buddy/di/` module with `configure()` function
- Provides container-based access via `depends.get_sync(ClassName)` for testable, modular code
- Benefits: Improved testability, reduced coupling, simplified lifecycle management

**Test Infrastructure Cleanup** (Phase 2.7 Day 5)

- Removed 6 unused test factories (65% code reduction in data_factories.py)
- Kept only actively-used factories: `ReflectionDataFactory`, `LargeDatasetFactory`, `SecurityTestDataFactory`
- Removed redundant pytest fixtures from conftest.py
- All 21 functional tests passing after cleanup

**Quality Scoring V2 Algorithm** (Phase 2.7 Day 4)

- New filesystem-based quality assessment in `utils/quality_utils_v2.py`
- Direct file inspection instead of abstracted context (more accurate, less mocking needed)
- Updated test expectations to match V2 scoring ranges

**Async/Await Chain Fixes** (Phase 2.7 Day 4)

- Fixed nested event loop bugs in session_manager.py
- Made `_get_previous_session_info()` and `_read_previous_session_info()` properly async
- Replaced `asyncio.run()` calls within async context with `await`

### Core Components

1. **server.py** (~3,500+ lines): Main MCP server implementation

   - **FastMCP Integration**: Uses FastMCP framework for MCP protocol handling
   - **Tool Registration**: Centralized registration of all MCP tools and prompts
   - **Session Lifecycle**: Complete session management (start, checkpoint, end, status)
   - **Permissions System**: Trusted operations management to reduce user prompts
   - **Project Analysis**: Context-aware project health monitoring and scoring
   - **Git Integration**: Automatic checkpoint commits with metadata tracking
   - **Structured Logging**: SessionLogger class with file and console output

1. **reflection_tools.py**: Memory & conversation search system

   - **DuckDB Database**: Conversation storage with FLOAT[384] vector embeddings
   - **Local ONNX Model**: all-MiniLM-L6-v2 for semantic search (no external API calls)
   - **Async Architecture**: Executor threads prevent blocking on embedding generation
   - **Fallback Strategy**: Text search when ONNX/transformers unavailable
   - **Performance**: Optimized for concurrent access with connection pooling

1. **crackerjack_integration.py**: Code quality integration layer

   - **Real-time Parsing**: Crackerjack tool output analysis and progress tracking
   - **Quality Metrics**: Aggregation and trend analysis of code quality scores
   - **Test Result Analysis**: Pattern detection and success rate tracking
   - **Command History**: Learning from effective Crackerjack command usage

### Modular Architecture Components

4. **tools/** directory: Organized MCP tool implementations

   - **session_tools.py**: Core session management (start, checkpoint, end, status)
   - **memory_tools.py**: Reflection and search functionality
   - **search_tools.py**: Advanced search capabilities and pagination
   - **crackerjack_tools.py**: Quality integration and progress tracking
   - **llm_tools.py**: LLM provider management and configuration
   - **team_tools.py**: Collaborative features and knowledge sharing

1. **core/** directory: Core system management

   - **session_manager.py**: Session state and lifecycle coordination

1. **di/** directory: Dependency Injection configuration (Phase 2.7)

   - **__init__.py**: Centralized DI configuration with `configure()` function
   - **constants.py**: Component identifiers and DI-related constants
   - Provides: `depends.get_sync(ClassName)` for container-based dependency resolution
   - Benefits: Testable components, reduced coupling, simplified lifecycle management

1. **utils/** directory: Shared utilities and helper functions

   - **git_operations.py**: Git commit functions and repository management
   - **logging.py**: SessionLogger implementation and structured logging
   - **quality_utils.py**: Legacy quality assessment (V1)
   - **quality_utils_v2.py**: Filesystem-based quality scoring V2 algorithm (Phase 2.7)

### Advanced Components

7. **multi_project_coordinator.py**: Cross-project session coordination

   - **Data Models**: `ProjectGroup` and `ProjectDependency` dataclasses with type safety
   - **Relationship Types**: `related`, `continuation`, `reference` with semantic meaning
   - **Cross-Project Search**: Dependency-aware result ranking across related projects
   - **Use Case**: Coordinate microservices, monorepo modules, or related repositories

1. **token_optimizer.py**: Context window and response management

   - **TokenOptimizer**: tiktoken-based accurate token counting for GPT models
   - **Response Chunking**: Auto-split responses >4000 tokens with cache keys
   - **ChunkResult**: Structured pagination with metadata and continuation support
   - **Metrics Collection**: TokenUsageMetrics for optimization insights

1. **search_enhanced.py**: Advanced search capabilities

   - **Faceted Search**: Filter by project, time, author, content type
   - **Aggregations**: Statistical analysis of search results
   - **Full-Text Indexing**: FTS5 support in DuckDB for complex queries

1. **interruption_manager.py**: Context preservation during interruptions

   - **Smart Detection**: File system monitoring and activity pattern analysis
   - **Context Snapshots**: Automatic state preservation during interruptions
   - **Recovery**: Session restoration with minimal context loss

1. **serverless_mode.py**: External storage integration

   - **Oneiric Storage Adapters**: File, S3, Azure, GCS, Memory backends using native DuckDB
   - **Session Serialization**: Stateless operation with external persistence
   - **Multi-Instance**: Support for distributed Claude Code deployments
   - **See**: `docs/migrations/ONEIRIC_MIGRATION_PLAN.md` for migration details

1. **app_monitor.py**: IDE activity and browser documentation monitoring

   - **Activity Tracking**: Monitor IDE usage and documentation patterns
   - **Context Insights**: Generate insights from development behavior
   - **Performance Metrics**: Track development workflow efficiency

1. **natural_scheduler.py**: Natural language scheduling and reminders

   - **Time Parsing**: Convert natural language to scheduled tasks
   - **Reminder System**: Background service for task notifications
   - **Integration**: Works with session management for deadline tracking

1. **worktree_manager.py**: Git worktree management and coordination

   - **Worktree Operations**: Create, remove, and manage Git worktrees
   - **Session Coordination**: Context switching between worktrees
   - **Branch Management**: Coordinate development across multiple branches

### Key Design Patterns & Architectural Decisions

#### 1. **Async-First Architecture**

```text
# Database operations use executor threads to prevent blocking
async def generate_embedding(text: str) -> np.ndarray:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_embedding_generation, text)


# MCP tools handle async/await automatically
@mcp.tool()
async def example_tool(param: str) -> dict[str, Any]:
    result = await async_operation(param)
    return {"success": True, "data": result}
```

#### 2. **Graceful Degradation Strategy**

- **Optional Dependencies**: Falls back gracefully when `onnxruntime`/`transformers` unavailable
- **Search Fallback**: Text search when embeddings fail, maintaining functionality
- **Memory Constraints**: Automatic chunking and compression for resource-limited environments
- **Error Recovery**: Continues operation despite individual component failures

#### 3. **Local-First Privacy Design**

- **No External APIs**: All embeddings generated locally via ONNX
- **Local Storage**: DuckDB file-based storage in `~/.claude/` directory
- **Zero Network Dependencies**: Functions without internet for core features
- **User Data Control**: Complete data sovereignty with local processing

#### 4. **Selective Auto-Store for High Signal-to-Noise Ratio**

The system intelligently decides when to auto-store checkpoint reflections to maintain high-quality memory:

**Auto-Store Triggers:**

- **Manual Checkpoints**: Always stored (user explicitly requested)
- **Session End**: Always stored (final state capture)
- **Significant Quality Changes**: Delta ≥10 points (configurable)
- **Exceptional Quality**: Score ≥90/100 (configurable)

**Skipped Checkpoints:**

- Routine automatic checkpoints with minimal changes
- Quality changes below threshold (default: \<10 points)

**Configuration Options** (config.py):

```python
enable_auto_store_reflections: bool = True  # Global toggle
auto_store_quality_delta_threshold: int = 10  # Minimum delta to trigger
auto_store_exceptional_quality_threshold: int = 90  # Exceptional quality
auto_store_manual_checkpoints: bool = True  # Store manual checkpoints
auto_store_session_end: bool = True  # Store session end
```

**Semantic Tagging**: Auto-stored reflections get meaningful tags:

- `manual_checkpoint`, `session_end`, `quality_improvement`, `quality_degradation`
- `high-quality`, `good-quality`, `needs-improvement`
- `user-initiated`, `quality-change`, `session-summary`

This approach ensures the reflection database contains only meaningful insights, making searches more effective and preventing storage bloat.

#### 5. **Type-Safe Data Modeling**

```python
@dataclass
class ProjectDependency:
    source_project: str
    target_project: str
    dependency_type: Literal["related", "continuation", "reference"]
    description: str | None = None
```

- **Dataclass Architecture**: Immutable, type-safe data structures throughout
- **Modern Type Hints**: Uses Python 3.13+ syntax with pipe unions
- **Runtime Validation**: Pydantic integration with automatic serialization

#### 6. **Performance-Optimized Vector Search**

```sql
-- DuckDB vector similarity with index support
SELECT content, array_cosine_similarity(embedding, $1) as similarity
FROM conversations
WHERE similarity > 0.7
ORDER BY similarity DESC, timestamp DESC
LIMIT 20;
```

- **Vector Indexing**: FLOAT[384] arrays with similarity search optimization
- **Hybrid Search**: Combines semantic similarity with temporal relevance
- **Result Ranking**: Time-decay weighting favors recent conversations

### Session Management Workflow

## Recommended Session Workflow

### Git Repositories (Automatic)

1. **Start Claude Code** - Session auto-initializes
1. **Work normally** - Automatic quality tracking
1. **Run `/checkpoint`** - Manual checkpoints with auto-compaction
1. **Exit any way** - Session auto-cleanup on disconnect

### Non-Git Projects (Manual)

1. **Start with**: `/start` (if you want session management)
1. **Checkpoint**: `/checkpoint` as needed
1. **End with**: `/end` before quitting

### Detailed Tool Functions

1. **Automatic Initialization** (Git repos only):

   - **Triggers**: Claude Code connection in git repository
   - Sets up ~/.claude directory structure
   - Syncs UV dependencies and generates requirements.txt
   - Analyzes project context and calculates maturity score
   - Sets up session permissions and auto-checkpoints
   - **Crash resilient**: Works even after network/system failures

1. **Enhanced Quality Monitoring** (`checkpoint` tool):

   - Calculates multi-factor quality score (project health, permissions, tools)
   - **NEW: Automatic context compaction when needed**
   - Creates automatic Git commits with checkpoint metadata
   - Provides workflow optimization recommendations
   - Intelligent analysis of development patterns

1. **Automatic Session Cleanup** (Git repos only):

   - **Triggers**: Any disconnect, quit, crash, or network failure
   - Generates session handoff documentation
   - Performs final quality assessment
   - Cleans up session artifacts
   - **Zero manual intervention** required

### Memory System Architecture

**DuckDB Schema**: Core tables with vector support:

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],  -- all-MiniLM-L6-v2 vectors
    project TEXT,
    timestamp TIMESTAMP
);

CREATE TABLE reflections (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],
    tags TEXT[]
);
```

**Vector Search Implementation**:

- **Local ONNX Model**: all-MiniLM-L6-v2 with 384-dimensional vectors
- **Cosine Similarity**: `array_cosine_similarity(embedding, query_vector)` in DuckDB
- **Fallback Strategy**: Text search when embeddings unavailable or ONNX missing
- **Async Execution**: Embedding generation runs in executor threads to avoid blocking

**Multi-Project Coordination**:

- `ProjectGroup` and `ProjectDependency` tables for relationship modeling
- Cross-project search with dependency-aware result ranking
- Session linking with typed relationships (`continuation`, `reference`, `related`)

## Configuration & Integration

### MCP Configuration

**Note:** This project uses the global MCP configuration in `~/.claude/.mcp.json` (recommended). The project-level `.mcp.json` has been removed as redundant.

Example configuration for `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "python",
      "args": ["-m", "session_buddy.server"],
      "cwd": "/path/to/session-buddy",
      "env": {
        "PYTHONPATH": "/path/to/session-buddy"
      }
    }
  }
}
```

### Directory Structure

The server uses the ~/.claude directory for data storage:

- **~/.claude/logs/**: Session management logging
- **~/.claude/data/**: Reflection database storage

### Environment Variables

- `PWD`: Used to detect current working directory

### Oneiric Storage Adapters

Session Buddy uses Oneiric adapters with native DuckDB for improved reliability and multi-cloud support.

**Recommended Backends**:

- `file` - Local file storage (default, best for development)
- `s3` - AWS S3/MinIO (production cloud storage)
- `azure` - Azure Blob Storage (Azure deployments)
- `gcs` - Google Cloud Storage (GCP deployments)
- `memory` - In-memory storage (testing only)

**Configuration** (`settings/session-buddy.yaml`):

```yaml
storage:
  default_backend: "file"

  file:
    local_path: "${SESSION_STORAGE_PATH:~/.claude/data/sessions}"
    auto_mkdir: true

  s3:
    bucket_name: "${S3_BUCKET:session-buddy}"
    endpoint_url: "${S3_ENDPOINT:}"
    region: "${S3_REGION:us-east-1}"
```

**Benefits**:

- ✅ Multiple cloud providers (S3, Azure, GCS)
- ✅ Environment variable support
- ✅ Native DuckDB operations (no external framework)
- ✅ Better connection pooling & error handling
- ✅ 91% code reduction in storage layer
- ✅ 100% backward compatibility

**Migration**: See `docs/migrations/ONEIRIC_MIGRATION_PLAN.md` for detailed migration instructions.

## Development Notes

### Dependencies & Isolation

- Uses isolated virtual environment to prevent conflicts
- **Core Dependencies**: `fastmcp>=2`, `duckdb>=0.9`, `pydantic>=2.0`, `tiktoken>=0.5`, `crackerjack`
- **Embedding System**: `onnxruntime>=1.15`, `transformers>=4.21` (included in core)
- **Development Tools**: `pytest>=7`, `pytest-asyncio>=0.21`, `hypothesis>=6.70`, `coverage>=7`
- Falls back gracefully when embedding system unavailable (text search mode)

### Testing Architecture

The project uses a comprehensive pytest-based testing framework with multiple test categories:

**Test Structure:**

- **Unit Tests** (`tests/unit/`): Core functionality testing

  - Session permissions and lifecycle management
  - Reflection database operations with async/await patterns
  - Mock fixtures for isolated component testing

- **Integration Tests** (`tests/integration/`): Complete MCP workflow validation

  - End-to-end session management workflows
  - MCP tool registration and execution
  - Database integrity with concurrent operations

- **Functional Tests** (`tests/functional/`): Feature-level testing

  - Cross-component integration testing
  - User workflow simulation
  - Performance and reliability validation

**Key Testing Features:**

- **Async/await support** for MCP server testing
- **Temporary database fixtures** with automatic cleanup
- **Data factories** for realistic test data generation
- **Performance metrics** collection and baseline comparison
- **Mock MCP server** creation for isolated testing

**Testing Commands:**

```bash
# Run all tests
pytest

# Run specific test types
pytest tests/unit/
pytest tests/integration/
pytest -m performance

# Run with coverage
pytest --cov=session_buddy --cov-report=term-missing

# Quick development tests (exclude slow tests)
pytest -m "not slow"
```

## Available MCP Tools

**Total: 70+ specialized tools** across 10 functional categories. See [README.md](README.md#available-mcp-tools) for complete list.

### Core Session Management (8 tools)

- **`start`** - Comprehensive session initialization with project analysis, UV sync, and memory setup
- **`checkpoint`** - Mid-session quality assessment with V2 scoring and automatic context compaction
- **`end`** - Complete session cleanup with learning capture and handoff documentation
- **`status`** - Current session overview with health checks and diagnostics
- **`permissions`** - Manage trusted operations to reduce permission prompts
- **`auto_compact`** - Automatic context window compaction when needed
- **`quality_monitor`** - Real-time quality monitoring and tracking
- **`session_welcome`** - Session connection information and continuity

### Memory & Conversation Search (14 tools)

**Search & Retrieval**:

- **`search_reflections`** / **`reflect_on_past`** - Semantic search using local AI embeddings
- **`quick_search`** - Fast overview with count and top results
- **`search_summary`** - Aggregated insights without individual results
- **`get_more_results`** - Pagination for large result sets
- **`search_by_file`**, **`search_by_concept`**, **`search_code`**, **`search_errors`**, **`search_temporal`** - Targeted searches

**Storage**:

- **`store_reflection`** - Store insights with tagging
- **`reflection_stats`** - Memory system statistics
- **`reset_reflection_database`** - Reset/rebuild memory

### Advanced Tool Categories

**Crackerjack Integration (11 tools)**:

- Command execution (`crackerjack_run`, `execute_crackerjack_command`)
- Quality metrics (`crackerjack_metrics`, `crackerjack_quality_trends`)
- Pattern detection (`crackerjack_patterns`, `analyze_crackerjack_test_patterns`)
- Health monitoring (`crackerjack_health_check`, `crackerjack_help`)

**LLM Provider Management (5 tools)**:

- `list_llm_providers`, `test_llm_providers`, `generate_with_llm`, `chat_with_llm`, `configure_llm_provider`

**Serverless Sessions (8 tools)**:

- External storage integration (Redis, S3, local) for stateless operation

**Team Collaboration (4 tools)**:

- `create_team`, `search_team_knowledge`, `get_team_statistics`, `vote_on_reflection`

**Multi-Project Coordination (4 tools)**:

- `create_project_group`, `add_project_dependency`, `search_across_projects`, `get_project_insights`

**Plus**: App Monitoring (5), Interruption Management (7), Natural Scheduling (5), Git Worktree (3), Advanced Search (3)

## Token Optimization and Response Chunking

The server includes sophisticated token management to handle large responses:

**Token Management Architecture**:

- **TokenOptimizer** class with tiktoken integration for accurate token counting
- **Response Chunking**: Automatically splits responses >4000 tokens into paginated chunks
- **ChunkResult** dataclass structure:
  ```python
  @dataclass
  class ChunkResult:
      chunks: list[str]  # Paginated content chunks
      total_chunks: int  # Total number of chunks
      current_chunk: int  # Current chunk index
      cache_key: str  # Unique cache identifier
      metadata: dict[str, Any]  # Additional context
  ```

**Usage Pattern for Large Responses**:

```python
# Large response automatically chunked
result = await some_large_operation()
if result.get("chunked"):
    print(f"Response chunked: {result['current_chunk']}/{result['total_chunks']}")
    # Use get_cached_chunk tool to retrieve additional chunks
```

## Integration with Crackerjack

This project integrates deeply with [Crackerjack](https://github.com/lesleslie/crackerjack) for code quality and development workflow automation:

- **Quality Commands**: Use `crackerjack lint`, `crackerjack typecheck`, etc. for code quality
- **MCP Integration**: Crackerjack is configured as an MCP server in .mcp.json
- **Progress Tracking**: `crackerjack_integration.py` provides real-time analysis parsing
- **Test Integration**: Crackerjack handles test execution, this project handles results analysis

## Development Guidelines

### Adding New MCP Tools

1. Define function with `@mcp.tool()` decorator in appropriate tools/ module
1. Add corresponding prompt with `@mcp.prompt()` for slash command support
1. Import and register in main server.py
1. Update status() tool to report new functionality
1. Add tests in appropriate test category

### Extending Memory System

1. Add new table schemas in reflection_tools.py:\_ensure_tables()
1. Implement storage/retrieval methods in ReflectionDatabase class
1. Add corresponding MCP tools in tools/memory_tools.py
1. Update reflection_stats() to include new metrics
1. Add performance tests for new operations

### Testing New Features

1. Add unit tests for individual functions in `tests/unit/`
1. Add integration tests for MCP tool workflows in `tests/integration/`
1. Add functional tests for complete features in `tests/functional/`
1. Use `tests/fixtures/` for test data factories and mock fixtures
1. Ensure coverage is maintained via `pytest --cov=session_buddy`

## Configuration Files

### pyproject.toml Configuration

The project uses modern Python tooling with strict quality settings:

- **Python 3.13+** required with latest language features
- **Ruff**: Code formatting and linting with complexity limits (max 15)
- **Pytest**: Comprehensive testing with async/await, coverage, and benchmarking
- **Optional Dependencies**: `[embeddings]` for semantic search, `[dev]` for development tools

### MCP Server Configuration

The global `~/.claude/.mcp.json` includes integration with multiple MCP servers:

- **session-buddy**: This server (local development mode)
- **crackerjack**: Code quality tools and workflow automation
- Plus additional servers for GitHub, GitLab, memory, etc.

### Testing Configuration (conftest.py)

- Async/await support for MCP server testing
- Temporary database fixtures with automatic cleanup
- Mock MCP server creation for isolated testing
- Performance baseline comparisons

## Modern Development Patterns

### 1. **Async/Await Best Practices**

```text
# ✅ Correct: Use executor for blocking operations
async def generate_embedding(text: str) -> np.ndarray:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_embedding_generation, text)


# ❌ Avoid: Blocking the event loop
async def bad_embedding(text: str) -> np.ndarray:
    return onnx_session.run(None, {"input": text})  # Blocks event loop
```

### 2. **Database Connection Management**

```text
# ✅ Correct: Context manager with connection pooling
async def store_conversation(content: str) -> str:
    async with ReflectionDatabase() as db:
        return await db.store_conversation(content)


# ✅ Correct: Batch operations for efficiency
async def bulk_store(conversations: list[str]) -> list[str]:
    async with ReflectionDatabase() as db:
        return await db.bulk_store_conversations(conversations)
```

### 3. **Error Handling Strategy**

```text
# ✅ Correct: Graceful degradation with logging
async def search_with_fallback(query: str) -> list[SearchResult]:
    try:
        # Try semantic search first
        return await semantic_search(query)
    except (ImportError, RuntimeError) as e:
        logger.info(f"Semantic search unavailable: {e}. Using text search.")
        return await text_search(query)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []
```

### 4. **MCP Tool Development Pattern**

```text
@mcp.tool()
async def example_tool(param1: str, param2: int | None = None) -> dict[str, Any]:
    """
    Tool description for Claude Code.

    Args:
        param1: Required parameter with clear description
        param2: Optional parameter with default value

    Returns:
        Structured response with success/error handling
    """
    try:
        # Validate inputs
        if not param1.strip():
            return {"success": False, "error": "param1 cannot be empty"}

        # Perform operation with proper async handling
        result = await perform_async_operation(param1, param2)

        return {
            "success": True,
            "data": result,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "execution_time_ms": 42,
            },
        }

    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return {"success": False, "error": str(e)}
```

## Troubleshooting Guide

### Common Issues & Solutions

#### 1. **MCP Server Not Loading**

```bash
# Check imports
python -c "import session_buddy; print('✅ Package imports successfully')"

# Verify FastMCP setup
python -c "from session_buddy.server import mcp; print('✅ MCP server configured')"

# Check for missing dependencies
python -c "
try:
    import duckdb, numpy, tiktoken
    print('✅ Core dependencies available')
except ImportError as e:
    print(f'❌ Missing dependency: {e}')
"
```

#### 2. **Memory/Embedding Issues**

```bash
# Test embedding system
python -c "
from session_buddy.reflection_tools import ReflectionDatabase
import asyncio

async def test():
    try:
        async with ReflectionDatabase() as db:
            result = await db.test_embedding_system()
            print(f'✅ Embedding system: {result}')
    except Exception as e:
        print(f'⚠️ Embedding fallback mode: {e}')

asyncio.run(test())
"

# Reinstall all dependencies if needed
uv sync
```

#### 3. **Database Connection Problems**

```bash
# Check DuckDB installation
python -c "import duckdb; print(f'✅ DuckDB version: {duckdb.__version__}')"

# Test database connection
python -c "
import duckdb
conn = duckdb.connect(':memory:')
print('✅ DuckDB connection successful')
conn.close()
"

# Check file permissions
ls -la ~/.claude/data/ 2>/dev/null || echo "Creating ~/.claude/data/" && mkdir -p ~/.claude/data/
```

#### 4. **Performance Issues**

```bash
# Run performance diagnostics
pytest -m performance --verbose

# Check memory usage patterns
python -c "
import psutil
import os
print(f'Memory usage: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB')
"

# Enable detailed logging
PYTHONPATH=. python -m session_buddy.server --debug
```

### Development Environment Setup Issues

#### **UV Package Manager**

```bash
# Verify UV installation
uv --version || curl -LsSf https://astral.sh/uv/install.sh | sh

# Reset environment if corrupted
rm -rf .venv && uv sync --group dev

# Check for conflicting dependencies
uv pip check
```

#### **Python Version Compatibility**

```bash
# Verify Python 3.13+ requirement
python --version  # Should be 3.13+

# Check for async/await compatibility
python -c "
import sys
print(f'Python {sys.version}')
assert sys.version_info >= (3, 13), 'Python 3.13+ required'
print('✅ Python version compatible')
"
```

### Coding Standards & Best Practices

#### Core Philosophy (from RULES.md)

- **EVERY LINE OF CODE IS A LIABILITY**: The best code is no code
- **DRY (Don't Repeat Yourself)**: If you write it twice, you're doing it wrong
- **YAGNI (You Ain't Gonna Need It)**: Build only what's needed NOW
- **KISS (Keep It Simple, Stupid)**: Complexity is the enemy of maintainability

#### Type Safety Requirements

- **Always use comprehensive type hints** with modern Python 3.13+ syntax
- **Import typing as `import typing as t`** and prefix all typing references
- **Use built-in collection types**: `list[str]` instead of `t.List[str]`
- **Use pipe operator for unions**: `str | None` instead of `Optional[str]`

#### Development Practices

1. **Always use async/await** for database and file operations
1. **Test with both embedding and fallback modes** during development
1. **Include comprehensive error handling** with graceful degradation
1. **Use type hints and dataclasses** for data modeling
1. **Follow the testing pattern**: unit → integration → functional
1. **Run pre-commit workflow** before any commits
1. **Monitor token usage** and response chunking during development
1. **Test cross-project coordination** features with multiple repositories

### Key Architecture Insights for Development

When working with this codebase, remember these architectural patterns:

1. **FastMCP Integration**: All tools use `@mcp.tool()` decorators and return structured responses
1. **Async-First Design**: Database operations run in executor threads to avoid blocking
1. **Local Privacy**: No external API calls required - embeddings generated locally
1. **Graceful Fallback**: System continues working even when optional features fail
1. **Modular Structure**: Tools are organized by functionality in separate modules
1. **Session Lifecycle**: Init → Work → Checkpoint → End workflow with persistent memory

<!-- CRACKERJACK INTEGRATION START -->

This project uses crackerjack for Python project management and quality assurance.

For optimal development experience with this crackerjack - enabled project, use these specialized agents:

- **🏗️ crackerjack-architect**: Expert in crackerjack's modular architecture and Python project management patterns. **Use PROACTIVELY** for all feature development, architectural decisions, and ensuring code follows crackerjack standards from the start.

- **🐍 python-pro**: Modern Python development with type hints, async/await patterns, and clean architecture

- **🧪 pytest-hypothesis-specialist**: Advanced testing patterns, property-based testing, and test optimization

- **🧪 crackerjack-test-specialist**: Advanced testing specialist for complex testing scenarios and coverage optimization

- **🏗️ backend-architect**: System design, API architecture, and service integration patterns

- **🔒 security-auditor**: Security analysis, vulnerability detection, and secure coding practices

```bash

Task tool with subagent_type ="crackerjack-architect" for feature planning


Task tool with subagent_type ="python-pro" for code implementation


Task tool with subagent_type ="pytest-hypothesis-specialist" for test development


Task tool with subagent_type ="security-auditor" for security analysis
```

**💡 Pro Tip**: The crackerjack-architect agent automatically ensures code follows crackerjack patterns from the start, eliminating the need for retrofitting and quality fixes.

This project follows crackerjack's clean code philosophy:

- **EVERY LINE OF CODE IS A LIABILITY**: The best code is no code

- **DRY (Don't Repeat Yourself)**: If you write it twice, you're doing it wrong

- **YAGNI (You Ain't Gonna Need It)**: Build only what's needed NOW

- **KISS (Keep It Simple, Stupid)**: Complexity is the enemy of maintainability

- \*\*Cognitive complexity ≤15 \*\*per function (automatically enforced)

- **Coverage ratchet system**: Never decrease coverage, always improve toward 100%

- **Type annotations required**: All functions must have return type hints

- **Security patterns**: No hardcoded paths, proper temp file handling

- **Python 3.13+ modern patterns**: Use `|` unions, pathlib over os.path

```bash

python -m crackerjack


python -m crackerjack - t


python -m crackerjack - - ai - agent - t


python -m crackerjack - a patch
```

1. **Plan with crackerjack-architect**: Ensure proper architecture from the start
1. **Implement with python-pro**: Follow modern Python patterns
1. **Test comprehensively**: Use pytest-hypothesis-specialist for robust testing
1. **Run quality checks**: `python -m crackerjack -t` before committing
1. **Security review**: Use security-auditor for final validation

- **Use crackerjack-architect agent proactively** for all significant code changes
- **Never reduce test coverage** - the ratchet system only allows improvements
- **Follow crackerjack patterns** - the tools will enforce quality automatically
- **Leverage AI agent auto-fixing** - `python -m crackerjack --ai-agent -t` for autonomous quality fixes

______________________________________________________________________

- This project is enhanced by crackerjack's intelligent Python project management.\*

<!-- CRACKERJACK INTEGRATION END -->
