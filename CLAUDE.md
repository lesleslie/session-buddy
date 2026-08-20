# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

For a shorter, tool-neutral bootstrap document, start with `AGENTS.md`.

## Project Overview

Session Buddy is a Claude Session Management MCP (Model Context Protocol) server providing comprehensive session management for Claude Code across any project. It operates as a standalone MCP server with isolated environment to avoid dependency conflicts.

## Development Commands

### Installation & Setup

```bash
# Install all dependencies (development + production)
uv sync --group dev

# Install minimal dependencies (production)
uv sync

# Run server
python -m session_buddy.server

# Run with debug logging
PYTHONPATH=. python -m session_buddy.server --debug

# Verify installation
python -c "from session_buddy.server import mcp; print('✅ MCP server ready')"
python -c "from session_buddy.reflection import ReflectionDatabase; print('✅ Memory system ready')"
```

### Quick Start

```bash
# Complete development setup
uv sync --group dev && pytest -m "not slow" && crackerjack lint
```

### Code Quality

```bash
crackerjack lint          # Lint and format code
crackerjack typecheck     # Run type checking
crackerjack security      # Security scanning
crackerjack complexity    # Code complexity analysis
crackerjack analyze       # Full quality analysis
```

### Testing

```bash
pytest                               # Run all tests
pytest -m "not slow"                 # Quick smoke tests (dev recommended)
pytest tests/unit/                   # Unit tests only
pytest tests/integration/            # Integration tests only
pytest -m performance                # Performance tests
pytest -m security                   # Security tests
pytest -n auto                       # Parallel execution (faster)
pytest --cov=session_buddy --cov-report=term-missing  # Coverage
pytest --cov=session_buddy --cov-fail-under=85        # Enforce 85%+ coverage
```

### Workflows

```bash
# Pre-commit workflow
uv sync --group dev && crackerjack lint && pytest -m "not slow" && crackerjack typecheck

# Full quality gate (before PR)
pytest --cov=session_buddy --cov-fail-under=85 && crackerjack security && crackerjack complexity
```

## Architecture Overview

> **Note:** This section was removed during the 2026-08-12 audit because the
> "Recent Changes (January 2025)" header was 19 months stale. See `CHANGELOG.md`
> for the authoritative change log, and the `### Phase 2 Architecture Refactoring (February 2026)` section below for the current architecture summary.

### Oneiric Adapter Migration (COMPLETE)

Both database layers migrated to native DuckDB adapters (Oneiric):

**Phase 2-3**: Created `ReflectionDatabaseAdapter` and `KnowledgeGraphDatabaseAdapter` with hybrid sync/async pattern
**Phase 5**: Replaced external framework with direct DuckDB operations

```python
async def create_entity(self, name: str, ...) -> dict:
    """Async signature for API consistency, sync operation internally."""
    conn = self._get_conn()  # Sync DuckDB connection
    conn.execute("INSERT INTO kg_entities ...")  # Fast (<1ms)
    return {"id": entity_id, ...}
```

**Benefits**: Native DuckDB, improved connection pooling, better testability, zero breaking changes
**Details**: `docs/migrations/ONEIRIC_MIGRATION_PLAN.md`

### Phase 2 Architecture Refactoring (February 2026)

**Key Achievements**:

- Zero circular dependencies between core and MCP layers
- Core layer has ZERO MCP imports (verified programmatically)
- 908 lines of code reduction through deprecated code removal
- 18/18 architecture validation checks passed

**Details**: `docs/PHASE3_README.md`, `docs/PHASE3_ARCHITECTURE.md`, `docs/PHASE2_3_SINGLETON_CLEANUP_PLAN.md`

#### Layer Separation

```
MCP Layer (server.py)
    - FastMCP integration, Tool registration
    - Concrete implementations (MCPQualityScorer, MCPCodeFormatter)
         implements
    Core Layer Interfaces
    - QualityScorer (ABC), CodeFormatter (ABC)
         injected via DI
    Core Layer Components
    - SessionLifecycleManager, HooksManager
         uses
    Infrastructure Layer
    - Reflection database, Git operations, File system utilities
```

**Dependency Rules**:

1. **MCP Layer**: Implements Core interfaces, CAN import Core + Infrastructure
1. **Core Layer**: Contains interfaces/business logic, CAN import Infrastructure + ABC, CANNOT import MCP
1. **Infrastructure Layer**: Storage/utilities, CAN import stdlib + external deps, CANNOT import MCP/Core

#### Dependency Injection

```python
# Configure DI container (server startup)
from session_buddy.di import configure, get_sync_typed, reset
configure()  # Registers all singletons

# Get typed instance
manager = get_sync_typed(SessionLifecycleManager)

# Reset (testing)
reset()
```

**Registration Order** (critical):

1. SessionPaths → 2. SessionLogger → 3. SessionPermissionsManager →
1. QualityScorer (MCPQualityScorer/DefaultQualityScorer) →
1. CodeFormatter (MCPCodeFormatter/DefaultCodeFormatter) →
1. SessionLifecycleManager → 7. HooksManager

**Usage Patterns**:

```python
# Pattern 1: Constructor injection (preferred)
class SessionLifecycleManager:
    def __init__(self, quality_scorer: QualityScorer | None = None):
        self.quality_scorer = quality_scorer or get_sync_typed(QualityScorer)

# Pattern 2: Direct DI lookup (utilities)
def some_function():
    manager = get_sync_typed(SessionLifecycleManager)

# Pattern 3: Testing with mocks
manager = SessionLifecycleManager(quality_scorer=Mock(spec=QualityScorer))
```

#### Interface-Based Design

**Core layer defines interface**:

```python
class QualityScorer(ABC):
    @abstractmethod
    async def calculate_quality_score(self, project_dir: Path | None = None) -> dict[str, Any]:
        pass
```

**MCP layer provides concrete implementation**:

```python
class MCPQualityScorer(QualityScorer):
    async def calculate_quality_score(self, project_dir: Path | None = None) -> dict[str, Any]:
        from session_buddy.mcp.server import calculate_quality_score
        return await calculate_quality_score(project_dir=project_dir)
```

**Core layer provides fallback**:

```python
class DefaultQualityScorer(QualityScorer):
    async def calculate_quality_score(self, project_dir: Path | None = None) -> dict[str, Any]:
        return {"overall": 75, "metrics": {}, "recommendations": []}
```

#### Reflection System Modularization

**Before**: `reflection_tools.py` (90 lines) - Compatibility wrapper around modular structure
**After**: Modular structure under `session_buddy/reflection/`

```
session_buddy/reflection/
|-- __init__.py - Public API
|-- database.py - Database class
|-- embeddings.py - Vector generation
|-- schema.py - Database structure
|-- search.py - Semantic/text search
|-- storage.py - CRUD operations
reflection_tools.py (90 lines) - Compatibility wrapper
```

**Benefits**: Clear separation, better testability, 100% backward compatibility

#### Architectural Benefits

- **Testability**: Core layer tested without MCP dependencies, DI supports test doubles
- **Maintainability**: Layer separation prevents circular dependencies, modular structure isolates changes
- **Extensibility**: Multiple implementations via DI, graceful degradation with fallbacks
- **Performance**: DI adds \<1ms overhead, singleton pattern prevents duplicates

### Core Components

**server.py** (~336 lines): Thin entrypoint that re-exports the FastMCP instance from `server_optimized.py` and runs `python -m session_buddy.server`. Bulk of the MCP wiring lives in `server_optimized.py` (761 lines) and `session_buddy/mcp/server.py` (~300 lines, profile-driven registrations). Verified via `wc -l session_buddy/server.py session_buddy/server_optimized.py` on 2026-08-19.

**reflection_tools.py**: DuckDB database with FLOAT[384] vector embeddings, local ONNX model (all-MiniLM-L6-v2), async architecture with executor threads, text search fallback

**crackerjack_integration.py**: Real-time parsing of Crackerjack output, quality metrics aggregation, test result analysis, command history learning

**tools/**: Organized MCP tool implementations (session, memory, search, crackerjack, LLM, team)

**core/**: Session state and lifecycle coordination

**di/**: Dependency injection configuration (`configure()`, `get_sync_typed()`, benefits: testability, reduced coupling)

**utils/**: Git operations, logging, quality scoring (V1 + V2 filesystem-based)

### Advanced Components

**multi_project_coordinator.py**: Cross-project coordination with `ProjectGroup`/`ProjectDependency` dataclasses, relationship types (related/continuation/reference), dependency-aware result ranking

**token_optimizer.py**: tiktoken-based token counting, auto-split responses >4000 tokens with `ChunkResult` pagination

**search_enhanced.py**: Faceted search (project, time, author, content type), aggregations, FTS5 full-text indexing

**interruption_manager.py**: File system monitoring, automatic context snapshots, session restoration

**serverless_mode.py**: Oneiric storage adapters (File, S3, Azure, GCS, Memory), session serialization, multi-instance support

**app_monitor.py**: IDE activity tracking, development behavior insights, workflow efficiency metrics

**natural_scheduler.py**: Natural language time parsing, background reminder service

**worktree_manager.py**: Git worktree operations, session coordination, branch management

### Key Design Patterns

#### 1. Async-First Architecture

```python
# ✅ Correct: Use executor for blocking operations
async def generate_embedding(text: str) -> np.ndarray:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_embedding_generation, text)

# ❌ Avoid: Blocking the event loop
async def bad_embedding(text: str) -> np.ndarray:
    return onnx_session.run(None, {"input": text})  # Blocks!
```

#### 2. Graceful Degradation

- Optional dependencies fall back gracefully (ONNX → text search)
- Memory constraints trigger automatic chunking/compression
- Error recovery continues despite component failures

#### 3. Local-First Privacy

- No external APIs (embeddings generated locally via ONNX)
- Local DuckDB storage in `~/.claude/`
- Zero network dependencies for core features
- Complete user data control

#### 4. Selective Auto-Store (High Signal-to-Noise)

**Triggers**: Manual checkpoints (always), session end (always), quality delta ≥10, exceptional ≥90
**Skips**: Routine auto-checkpoints with minimal changes

**Configuration**:

```python
enable_auto_store_reflections: bool = True
auto_store_quality_delta_threshold: int = 10
auto_store_exceptional_quality_threshold: int = 90
auto_store_manual_checkpoints: bool = True
auto_store_session_end: bool = True
```

**Tags**: `manual_checkpoint`, `session_end`, `quality_improvement`, `quality_degradation`, `high-quality`, `good-quality`, `needs-improvement`, `user-initiated`, `quality-change`, `session-summary`

#### 5. Type-Safe Data Modeling

```python
@dataclass
class ProjectDependency:
    source_project: str
    target_project: str
    dependency_type: Literal["related", "continuation", "reference"]
    description: str | None = None
```

- Dataclass architecture, modern Python 3.13+ type hints, Pydantic runtime validation

#### 6. Performance-Optimized Vector Search

```sql
SELECT content, array_cosine_similarity(embedding, $1) as similarity
FROM conversations
WHERE similarity > 0.7
ORDER BY similarity DESC, timestamp DESC
LIMIT 20;
```

- FLOAT[384] vectors, cosine similarity, hybrid semantic + temporal ranking

### Session Management Workflow

**Git Repositories (Automatic)**:

1. Start Claude Code - Session auto-initializes
1. Work normally - Automatic quality tracking
1. Run `/checkpoint` - Manual checkpoints with auto-compaction
1. Exit any way - Session auto-cleanup

**Non-Git Projects (Manual)**:

1. Start with `/start` (if you want session management)
1. Checkpoint with `/checkpoint` as needed
1. End with `/end` before quitting

**Automatic Initialization** (Git repos): Sets up `~/.claude` directory, syncs UV dependencies, analyzes project context, calculates maturity score, sets up permissions, crash resilient

**Enhanced Quality Monitoring** (`checkpoint`): Multi-factor quality score, automatic context compaction, Git commits with metadata, workflow recommendations

**Automatic Session Cleanup** (Git repos): Any disconnect/quit/crash, generates handoff docs, final quality assessment, cleanup artifacts, zero manual intervention

### Memory System Architecture

**DuckDB Schema**:

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding FLOAT[384],  -- all-MiniLM-L6-v2
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

**Vector Search**: HTTP embedding via llama-server (preferred) or Ollama with graceful degradation; 384-dim vectors from all-MiniLM-L6-v2 or nomic-embed-text

**Multi-Project**: `ProjectGroup`/`ProjectDependency` tables, cross-project search with dependency-aware ranking, typed relationships (continuation/reference/related)

## Configuration & Integration

### MCP Configuration

Uses global `~/.claude/.mcp.json` (recommended). Project-level `.mcp.json` removed as redundant.

```json
{
  "mcpServers": {
    "session-buddy": {
      "command": "python",
      "args": ["-m", "session_buddy.server"],
      "cwd": "/path/to/session-buddy",
      "env": {"PYTHONPATH": "/path/to/session-buddy"}
    }
  }
}
```

### Bodai Baseline MCP Surface

Session-Buddy conforms to the Bodai core MCP baseline (`docs/plans/2026-08-20-bodai-mcp-surface-standardization.md`):

- `discover_tools(query)` — list registered tools, optionally filtered by name substring
- `get_liveness()` — `{status, service, version, uptime_seconds}` envelope
- `get_readiness()` — readiness probe over configured dependencies
- `health_check_all()` — dependency health summary

`ping` is preserved as a deprecated alias delegating to `get_liveness` (logs a WARN on every call). Removed in the next release — callers (Akosha, Mahavishnu, Crackerjack) should migrate to `get_liveness`.

### Directory Structure

- **~/.claude/logs/**: Session management logging
- **~/.claude/data/**: Reflection database storage

### Environment Variables

- `PWD`: Current working directory detection

### Oneiric Storage Adapters

**Backends**: `file` (default, dev), `s3` (AWS/MinIO), `azure`, `gcs`, `memory` (testing only)

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

**Benefits**: Multi-cloud support, environment variable support, native DuckDB, better connection pooling, 91% code reduction, 100% backward compatibility

**Migration**: `docs/migrations/ONEIRIC_MIGRATION_PLAN.md`

## Development Notes

### Dependencies

- **Core**: `fastmcp>=2`, `duckdb>=0.9`, `pydantic>=2.0`, `tiktoken>=0.5`, `crackerjack`
- **Embeddings**: `onnxruntime>=1.15`, `transformers>=4.21` (graceful fallback to text search)
- **Dev**: `pytest>=7`, `pytest-asyncio>=0.21`, `hypothesis>=6.70`, `coverage>=7`
- Isolated virtual environment prevents conflicts

### Testing Architecture

**Structure**:

- **Unit** (`tests/unit/`): Core functionality, session permissions, reflection DB operations, async/await patterns, mock fixtures
- **Integration** (`tests/integration/`): End-to-end MCP workflows, tool registration/execution, concurrent database operations
- **Functional** (`tests/functional/`): Cross-component integration, user workflows, performance/reliability

**Features**: Async/await support, temporary database fixtures, data factories, performance metrics, mock MCP server

## Available MCP Tools

**Total: 199 MCP tools** across 31 tool groups when `SESSION_BUDDY_TOOL_PROFILE=full` (verified 2026-08-19). See [README.md](README.md#available-mcp-tools) for complete list.

### Tool Profile System

Tools are gated by the `SESSION_BUDDY_TOOL_PROFILE` environment variable:

- `full` (default): All ~35 register fns from `REGISTRATION_MAP`
- `standard`: Session lifecycle + search + hooks + conversation + extraction + knowledge_graph + cache + intent + crackerjack + monitoring + access_log + channel_session_state + channel_tracking + cross_repo_work (~15 tools)
- `minimal`: Session lifecycle + search + hooks (~3 tools)

Health tools are always-on at every profile via `SESSION_BUDDY_MANDATORY_GROUPS`.
For detailed rationale (group choices, Dhara publisher build pattern, subagent
recovery history): see
[docs/architecture/tool-profile-rationale.md](docs/architecture/tool-profile-rationale.md).

### Core Session Management (8 tools)

`start`, `checkpoint`, `end`, `status`, `permissions`, `auto_compact`, `quality_monitor`, `session_welcome`

### Memory & Search (14 tools)

**Search**: `search_reflections`/`reflect_on_past`, `quick_search`, `search_summary`, `get_more_results`, `search_by_file`, `search_by_concept`, `search_code`, `search_errors`, `search_temporal`
**Storage**: `store_reflection`, `reflection_stats`, `reset_reflection_database`

### Advanced Categories

- **Crackerjack integration**: `crackerjack_integration.py` parses real-time Crackerjack output but no Crackerjack-specific MCP tools ship in the default profile.
- **LLM Management** (6): `list_llm_providers`, `test_llm_providers`, `generate_with_llm`, `chat_with_llm`, `configure_llm_provider`, `sync_claude_qwen_config`
- **Git Worktree** (3): Available via `session_buddy.mcp.server` when `SESSION_BUDDY_TOOL_PROFILE=full`; not in the default profile.

> **Removed in 2026-08-12 audit:** Serverless, Team, Multi-Project, App Monitoring,
> Interruption Management, and Natural Scheduling categories were documented
> but their `register_*` functions (`register_serverless_tools`,
> `register_team_tools`, `register_multi_project_tools` (does not exist),
> `register_app_monitoring_tools` (does not exist), `register_interruption_tools`
> (does not exist), `register_natural_scheduling_tools` (does not exist)) are
> not called by `server_optimized.py:301-318`. They are reachable only via
> the alternative profile-driven entrypoint.

## Operational Notes

### LLM Provider Configuration

Session-Buddy uses MiniMax as the primary cloud LLM provider:

- **Primary provider**: `minimax` (OpenAI-compatible API at `https://api.minimax.io/v1`)
- **Fallback provider**: `ollama` (local at

# lychee: ignore

`http://localhost:11434`)

- **Default model (ecosystem-wide)**: `MiniMax-M3` (general), `MiniMax-M3-highspeed` (quick/background tasks) — see Mahavishnu `settings/models.yaml:5`.
- **Local override (this repo)**: `MiniMax-M2.7` — `settings/session-buddy.yaml:16` pins the older model for backward compatibility. Align with the ecosystem default by changing `minimax_default_model` in `settings/session-buddy.yaml`.
- **Provider chain**: `minimax -> ollama`

**Configuration** (in `settings/session-buddy.yaml` or environment variables):

- `minimax_api_key` / `MINIMAX_API_KEY` — MiniMax API key
- `minimax_base_url` — API endpoint (default: `https://api.minimax.io/v1`)
- `minimax_default_model` — Default model. Ecosystem default `MiniMax-M3`; this repo's `settings/session-buddy.yaml` overrides to `MiniMax-M2.7`.
- `zai_api_key` / `ZAI_API_KEY` — optional ZAI compatibility key
- `zai_base_url` — optional compatibility endpoint (default: `https://api.z.ai/api/coding/paas/v4`)
- `zai_default_model` — optional compatibility model (default: `glm-4.7`)
- `default_llm_provider` — Primary provider (default: `minimax`)
- `llm_fallback_chain` — Fallback order (default: `["minimax", "ollama"]`)

**Key files**:

- `session_buddy/llm_providers.py` — LLMManager with multi-provider support
- `session_buddy/llm/security.py` — API key validation and masking
- `session_buddy/settings.py` — MiniMax and ZAI settings fields in SessionMgmtSettings
- `tests/integration/test_zai_fallback_chain.py` — Integration tests for provider fallback chain

### Token Optimization

Large MCP responses are chunked through `TokenOptimizer`; if a tool reports chunked output, retrieve subsequent chunks rather than expanding the tool response shape ad hoc.

### Crackerjack Integration

Session Buddy uses Crackerjack for linting, type checks, security, and test execution, and includes `crackerjack_integration.py` for parsing and reporting quality results.

Recommended workflow:

```bash
crackerjack lint
pytest -m "not slow"
pytest --cov=session_buddy --cov-fail-under=85
```

### Extending the System

For new MCP tools:

1. Add the tool in the appropriate `tools/` module.
1. Register it through the server wiring.
1. Add unit and integration coverage.
1. Update any relevant status or statistics surfaces.

For memory-system changes:

1. Update schema and storage behavior together.
1. Cover both embedding and fallback modes.
1. Verify local performance before expanding the feature surface.

### Troubleshooting

Use focused smoke checks before deeper debugging:

```bash
python -c "import session_buddy; print('ok')"
python -c "from session_buddy.server import mcp; print('mcp ok')"
python -c "import duckdb; print(duckdb.__version__)"
PYTHONPATH=. python -m session_buddy.server --debug
```

If search or embeddings fail, confirm the fallback path still works and avoid blocking core session features on optional semantic components.

### Coding Standards

- Keep the code async-first for I/O-heavy paths.
- Prefer graceful degradation over hard failure when optional components are unavailable.
- Maintain comprehensive type hints and structured responses for MCP tools.
- Follow the test progression: unit, integration, then functional coverage where needed.
- Use Crackerjack before landing non-trivial changes.
