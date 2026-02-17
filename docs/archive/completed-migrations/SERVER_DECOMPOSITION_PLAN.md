# Server.py Decomposition Architecture Plan

**Project:** session-buddy
**Current File:** `session_buddy/server.py` (3,962 lines, 148+ functions/classes)
**Goal:** Decompose into focused, maintainable modules following ACB patterns
**Target:** 4 modules (~1000 lines each) with clear boundaries

______________________________________________________________________

## Executive Summary

The current `server.py` is a monolithic file that handles everything from MCP initialization to quality scoring to tool registration. This decomposition plan restructures it into 4 focused modules with single responsibilities, clear interfaces, and improved testability. The migration will be gradual, reversible, and maintain 100% backwards compatibility.

**Key Outcomes:**

- Reduced cognitive complexity per module
- Improved testability through clear interfaces
- Better ACB integration opportunities
- Easier maintenance and feature additions
- Zero breaking changes during migration

______________________________________________________________________

## Current Architecture Analysis

### File Statistics

- **Total Lines:** 3,962
- **Functions/Classes:** 148+
- **MCP Tools:** 17 directly defined in server.py
- **Import Dependencies:** 50+ external modules
- **Global State:** 15+ global variables

### Major Functional Areas

#### 1. **Core Infrastructure (Lines 1-485)**

- `SessionLogger` class (100 lines)
- `SessionPermissionsManager` class (95 lines)
- MCP server detection and configuration
- Import management and availability flags
- Global initialization and state management

#### 2. **Session Lifecycle Management (Lines 486-903)**

- `session_lifecycle()` - FastMCP lifespan handler
- Session initialization (`auto_setup_git_working_directory`, `initialize_new_features`)
- Project context analysis
- UV dependency management
- Claude directory setup
- Session permissions and tools summary

#### 3. **Quality Scoring & Analysis (Lines 904-2857)**

- Quality score calculation (V2 algorithm)
- Context compaction logic
- Strategic compaction recommendations
- Conversation summarization
- Proactive quality monitoring
- Token usage analysis
- Memory pattern analysis
- Project workflow recommendations
- Session intelligence generation

#### 4. **Utility Functions & Helpers (Lines 2858-3850)**

- Natural language reminder tools (5 MCP tools)
- Interruption management tools (1 MCP tool)
- Multi-project coordination (4 MCP tools)
- Advanced search capabilities (3 MCP tools)
- Git worktree management (4 MCP tools)
- Session welcome tool
- Formatting and display helpers (50+ functions)

#### 5. **Main Entry Point (Lines 3851-3962)**

- `main()` function for server startup
- HTTP vs STDIO mode configuration
- Statistics formatting helpers

### Dependency Map

```
server.py
├── Core Dependencies (Internal)
│   ├── reflection_tools.py (memory & search)
│   ├── core/session_manager.py (lifecycle)
│   ├── tools/*.py (8 tool modules)
│   ├── utils/*.py (10+ utility modules)
│   └── crackerjack_integration.py
│
├── External Services (Optional)
│   ├── multi_project_coordinator.py
│   ├── advanced_search.py
│   ├── app_monitor.py
│   ├── llm_providers.py
│   ├── serverless_mode.py
│   ├── natural_scheduler.py
│   ├── interruption_manager.py
│   └── worktree_manager.py
│
└── Third-party Libraries
    ├── fastmcp (MCP protocol)
    ├── duckdb (reflection database)
    └── tomli (config parsing)
```

### Natural Module Boundaries

1. **MCP Server Core** - FastMCP initialization, lifespan, tool registration
1. **Quality & Analysis Engine** - Scoring, context compaction, intelligence
1. **Advanced Feature Tools** - Multi-project, worktree, scheduling, search
1. **Utility & Formatting** - Helper functions, display formatting, validation

______________________________________________________________________

## Proposed Module Structure

### Module 1: Core Server & Initialization

**File:** `session_buddy/server_core.py`
**Size:** ~900 lines
**Responsibility:** MCP server initialization, configuration, and core infrastructure

#### Key Components

```python
# Classes (300 lines)
class SessionLogger:
    """Structured logging with context - MOVE HERE"""


class SessionPermissionsManager:
    """Singleton permissions management - MOVE HERE"""


class MCPServerCore:
    """NEW: Core MCP server wrapper with lifecycle management"""

    def __init__(self):
        self.mcp = FastMCP("session-buddy", lifespan=self.session_lifecycle)
        self.logger: SessionLogger
        self.permissions: SessionPermissionsManager
        self.config: dict[str, Any]

    async def session_lifecycle(self, app: Any) -> AsyncGenerator[None]:
        """FastMCP lifespan handler for git repos"""

    def register_all_tools(self) -> None:
        """Register all tool modules"""

    def run(self, http_mode: bool = False, http_port: int | None = None) -> None:
        """Start server in STDIO or HTTP mode"""


# Functions (600 lines)
def _load_mcp_config() -> dict[str, Any]:
    """Load .mcp.json configuration"""


def _detect_other_mcp_servers() -> dict[str, bool]:
    """Detect available MCP servers"""


def _generate_server_guidance(detected: dict[str, bool]) -> list[str]:
    """Generate server-specific guidance"""


async def auto_setup_git_working_directory() -> None:
    """Auto-detect git repository"""


async def initialize_new_features() -> None:
    """Initialize multi-project, advanced search, etc."""


async def analyze_project_context(project_dir: Path) -> dict[str, bool]:
    """Analyze project structure"""


def main(http_mode: bool = False, http_port: int | None = None) -> None:
    """Entry point - delegates to MCPServerCore"""
```

#### Dependencies

- **Internal:** `tools/*`, `core/session_manager`, `reflection_tools`, `utils/git_operations`
- **External:** `fastmcp`, `tomli` (optional)

#### ACB Integration Points

- **Settings:** Use ACB settings for server configuration
- **Dependency Injection:** Inject logger, permissions, config into tools
- **Cache:** Use ACB cache for MCP config and server detection

______________________________________________________________________

### Module 2: Quality Engine & Analysis

**File:** `session_buddy/quality_engine.py`
**Size:** ~1100 lines
**Responsibility:** Quality scoring, context analysis, and intelligence generation

#### Key Components

```python
from dataclasses import dataclass


@dataclass
class QualityScoreResult:
    """Structured quality score result"""

    total_score: int
    version: str
    breakdown: dict[str, int]
    trust_score: dict[str, Any]
    recommendations: list[str]
    details: dict[str, Any]


class QualityEngine:
    """NEW: Centralized quality scoring and analysis"""

    def __init__(self, logger: SessionLogger):
        self.logger = logger
        self._quality_history: dict[str, list[int]] = {}

    async def calculate_quality_score(self) -> QualityScoreResult:
        """V2 quality scoring with actual code metrics"""

    async def should_suggest_compact() -> tuple[bool, str]:
        """Determine if context compaction is recommended"""

    async def perform_strategic_compaction() -> list[str]:
        """Execute context compaction with conversation summary"""

    async def capture_session_insights(quality_score: float) -> list[str]:
        """Capture session intelligence and patterns"""

    async def analyze_context_usage() -> list[str]:
        """Comprehensive context usage analysis"""

    async def generate_session_intelligence() -> dict[str, Any]:
        """Generate actionable session insights"""

    async def monitor_proactive_quality() -> dict[str, Any]:
        """Real-time quality monitoring"""


# Helper Functions (600+ lines)
async def _optimize_reflection_database() -> str:
    """Optimize reflection database performance"""


async def _analyze_context_compaction() -> list[str]:
    """Analyze context window usage patterns"""


async def _store_context_summary(summary: dict[str, Any]) -> None:
    """Store conversation summary as reflection"""


async def summarize_current_conversation() -> dict[str, Any]:
    """Summarize current conversation for compaction"""


async def analyze_token_usage_patterns() -> dict[str, Any]:
    """Analyze token usage across conversations"""


async def analyze_conversation_flow() -> dict[str, Any]:
    """Analyze conversation patterns and effectiveness"""


async def analyze_memory_patterns(db: Any, conv_count: int) -> dict[str, Any]:
    """Analyze memory usage and retention patterns"""


async def analyze_project_workflow_patterns(current_dir: Path) -> dict[str, Any]:
    """Analyze project-specific workflow patterns"""


# File Counting & Git Analysis (200 lines)
def _count_significant_files(current_dir: Path) -> int:
    """Count project files for complexity estimation"""


def _check_git_activity(current_dir: Path) -> tuple[int, int] | None:
    """Check git activity as development indicator"""
```

#### Dependencies

- **Internal:** `utils/quality_utils_v2`, `reflection_tools`, `utils/git_operations`
- **External:** None (self-contained analysis)

#### ACB Integration Points

- **Cache:** Cache quality scores, file counts, git activity
- **Settings:** Quality thresholds, compaction triggers from ACB config
- **Logging:** Structured logging via ACB patterns

______________________________________________________________________

### Module 3: Advanced Features Hub

**File:** `session_buddy/advanced_features.py`
**Size:** ~1000 lines
**Responsibility:** Multi-project coordination, worktree management, scheduling, advanced search

#### Key Components

```text
class AdvancedFeaturesHub:
    """NEW: Central hub for optional advanced features"""

    def __init__(self, logger: SessionLogger):
        self.logger = logger
        self.multi_project: MultiProjectCoordinator | None = None
        self.advanced_search: AdvancedSearchEngine | None = None
        self.app_monitor: ApplicationMonitor | None = None
        self.llm_manager: LLMManager | None = None
        self.serverless: ServerlessSessionManager | None = None

    async def initialize(self) -> None:
        """Lazy initialization of optional features"""

    async def get_multi_project_coordinator(self) -> MultiProjectCoordinator | None:
        """Get or initialize multi-project coordinator"""

    async def get_advanced_search_engine(self) -> AdvancedSearchEngine | None:
        """Get or initialize advanced search engine"""

# MCP Tool Functions (800 lines)
# Natural Language Scheduling (200 lines)
async def create_natural_reminder(...) -> str:
    """Create reminder from natural language"""

async def list_user_reminders(...) -> str:
    """List pending reminders"""

async def cancel_user_reminder(reminder_id: str) -> str:
    """Cancel specific reminder"""

async def start_reminder_service() -> str:
    """Start background reminder service"""

async def stop_reminder_service() -> str:
    """Stop background reminder service"""

# Interruption Management (100 lines)
async def get_interruption_statistics(user_id: str) -> str:
    """Get comprehensive interruption stats"""

# Multi-Project Coordination (200 lines)
async def create_project_group(...) -> str:
    """Create project group"""

async def add_project_dependency(...) -> str:
    """Add project dependency relationship"""

async def search_across_projects(...) -> str:
    """Search conversations across projects"""

async def get_project_insights(...) -> str:
    """Get cross-project insights"""

# Advanced Search (150 lines)
async def advanced_search(...) -> str:
    """Faceted search with filtering"""

async def search_suggestions(...) -> str:
    """Search completion suggestions"""

async def get_search_metrics(...) -> str:
    """Search and activity metrics"""

# Git Worktree Management (250 lines)
async def git_worktree_list(...) -> str:
    """List all worktrees"""

async def git_worktree_add(...) -> str:
    """Create new worktree"""

async def git_worktree_remove(...) -> str:
    """Remove worktree"""

async def git_worktree_status(...) -> str:
    """Get worktree status"""

async def git_worktree_switch(...) -> str:
    """Switch between worktrees"""

# Session Welcome (50 lines)
async def session_welcome() -> str:
    """Display connection and continuity info"""
```

#### Dependencies

- **Internal:** `multi_project_coordinator`, `advanced_search`, `natural_scheduler`, `interruption_manager`, `worktree_manager`, `app_monitor`, `llm_providers`, `serverless_mode`
- **External:** All optional - graceful fallback if unavailable

#### ACB Integration Points

- **Lazy Loading:** Initialize features on-demand via ACB patterns
- **Feature Flags:** Use ACB settings to enable/disable features
- **Cache:** Cache feature instances and results

______________________________________________________________________

### Module 4: Utilities & Formatting

**File:** `session_buddy/utils/server_helpers.py`
**Size:** ~900 lines
**Responsibility:** Display formatting, validation, helper functions

#### Key Components

```text
# Session Initialization Helpers (300 lines)
def _setup_claude_directory(output: list[str]) -> dict[str, Any]:
    """Setup Claude directory structure"""

def _setup_uv_dependencies(output: list[str], current_dir: Path) -> None:
    """Setup UV dependencies"""

def _handle_uv_operations(...) -> None:
    """Handle UV package management"""

def _run_uv_sync_and_compile(output: list[str], current_dir: Path) -> None:
    """Run UV sync and compile"""

def _setup_session_management(output: list[str]) -> None:
    """Setup session management"""

async def _analyze_project_structure(...) -> tuple[dict[str, Any], int]:
    """Analyze project structure for maturity"""

def _add_final_summary(...) -> None:
    """Add final initialization summary"""

def _add_permissions_and_tools_summary(...) -> None:
    """Add permissions and tools info"""

# Quality Recommendation Helpers (200 lines)
def _generate_quality_recommendations(...) -> list[str]:
    """Generate quality improvement recommendations"""

def _generate_workflow_recommendations(...) -> list[str]:
    """Generate workflow optimization suggestions"""

def _ensure_default_recommendations(actions: list[str]) -> list[str]:
    """Ensure we have default recommendations"""

# Formatting Functions (400 lines)
# Reminder Formatting
def _format_no_reminders_message(...) -> list[str]:
def _format_reminders_header(...) -> list[str]:
def _format_single_reminder(...) -> list[str]:
def _format_reminders_list(...) -> list[str]:
def _format_reminder_basic_info(...) -> list[str]:
def _calculate_overdue_time(scheduled_for: str) -> str:

# Statistics Formatting
def _format_interruption_statistics(...) -> list[str]:
def _format_snapshot_statistics(...) -> list[str]:
def _has_statistics_data(...) -> bool:

# Project Insights Formatting
def _format_project_insights(...) -> str:
def _format_project_activity_section(...) -> list[str]:
def _format_common_patterns_section(...) -> list[str]:

# Search Results Formatting
def _build_advanced_search_filters(...) -> list[Any]:
def _format_advanced_search_results(...) -> str:

# Worktree Formatting
def _format_worktree_status(wt: dict[str, Any]) -> str:
def _format_worktree_list_header(...) -> list[str]:
def _get_worktree_indicators(...) -> tuple[str, str]:
def _format_single_worktree(...) -> list[str]:
def _format_session_summary(...) -> list[str]:
def _format_worktree_status_display(...) -> str:
def _format_basic_worktree_info(...) -> list[str]:
def _format_session_info(...) -> list[str]:

# Conversation Formatting
async def _format_conversation_summary() -> list[str]:
```

#### Dependencies

- **Internal:** `utils/format_utils`, `utils/quality_utils`, `reflection_tools`
- **External:** None (pure formatting)

#### ACB Integration Points

- **Templates:** Use ACB template system for output formatting
- **Localization:** Support i18n through ACB patterns
- **Theme Configuration:** Configurable output styling

______________________________________________________________________

## Migration Strategy

### Phase 1: Create Module Skeletons (Week 1)

**Risk:** Low | **Effort:** 2 hours | **Reversibility:** 100%

1. **Create new module files**

   ```bash
   touch session_buddy/server_core.py
   touch session_buddy/quality_engine.py
   touch session_buddy/advanced_features.py
   touch session_buddy/utils/server_helpers.py
   ```

1. **Add module docstrings and basic structure**

   - Import statements
   - Class definitions (empty)
   - Function signatures (raise NotImplementedError)

1. **Update `__init__.py` files**

   ```python
   # session_buddy/__init__.py
   from .server_core import MCPServerCore
   from .quality_engine import QualityEngine
   from .advanced_features import AdvancedFeaturesHub
   ```

1. **Run tests to ensure no imports break**

   ```bash
   pytest tests/ -v
   ```

**Success Criteria:** All existing tests pass, no import errors

______________________________________________________________________

### Phase 2: Extract Utility Functions (Week 1-2)

**Risk:** Low | **Effort:** 4 hours | **Reversibility:** 100%

1. **Move formatting functions to `utils/server_helpers.py`**

   - All `_format_*` functions (40+ functions)
   - Keep original functions as aliases pointing to new location
   - Example:
     ```text
     # server.py (temporary bridge)
     from session_buddy.utils.server_helpers import _format_worktree_status

     # Old code still works via import
     ```

1. **Move helper functions**

   - `_setup_*` functions (5 functions)
   - `_handle_*` functions (2 functions)
   - `_run_*` functions (2 functions)
   - `_add_*` functions (5 functions)

1. **Update imports in server.py**

   ```text
   from session_buddy.utils.server_helpers import (
       _format_worktree_status,
       _setup_claude_directory,
       # ... all moved functions
   )
   ```

1. **Run comprehensive tests**

   ```bash
   pytest tests/ -v --cov=session_buddy/utils/server_helpers.py
   ```

**Success Criteria:**

- All tests pass
- Coverage ≥85% for new module
- No duplicate code between server.py and server_helpers.py

______________________________________________________________________

### Phase 3: Extract Quality Engine (Week 2-3)

**Risk:** Medium | **Effort:** 8 hours | **Reversibility:** 90%

1. **Create `QualityEngine` class in `quality_engine.py`**

   ```python
   class QualityEngine:
       def __init__(self, logger: SessionLogger):
           self.logger = logger
           self._quality_history: dict[str, list[int]] = {}
   ```

1. **Move quality scoring functions**

   - `calculate_quality_score()` → `QualityEngine.calculate_quality_score()`
   - `should_suggest_compact()` → `QualityEngine.should_suggest_compact()`
   - `perform_strategic_compaction()` → `QualityEngine.perform_strategic_compaction()`
   - All helper functions (`_optimize_reflection_database`, `_analyze_context_compaction`, etc.)

1. **Update `server.py` to use `QualityEngine`**

   ```python
   # server.py
   from session_buddy.quality_engine import QualityEngine

   quality_engine = QualityEngine(session_logger)


   # Replace all direct calls
   async def calculate_quality_score() -> dict[str, Any]:
       return await quality_engine.calculate_quality_score()
   ```

1. **Update `SessionLifecycleManager` to use `QualityEngine`**

   ```python
   # core/session_manager.py
   from session_buddy.quality_engine import QualityEngine


   class SessionLifecycleManager:
       def __init__(self):
           self.quality_engine = QualityEngine(self.logger)

       async def calculate_quality_score(self) -> dict[str, Any]:
           return await self.quality_engine.calculate_quality_score()
   ```

1. **Add comprehensive tests for `QualityEngine`**

   ```bash
   pytest tests/unit/test_quality_engine.py -v
   pytest tests/integration/test_quality_scoring.py -v
   ```

**Success Criteria:**

- All existing quality tests pass
- New unit tests for QualityEngine pass
- No circular dependencies
- Coverage ≥85% for quality_engine.py

______________________________________________________________________

### Phase 4: Extract Advanced Features (Week 3-4)

**Risk:** Medium | **Effort:** 6 hours | **Reversibility:** 90%

1. **Create `AdvancedFeaturesHub` class in `advanced_features.py`**

   ```text
   class AdvancedFeaturesHub:
       def __init__(self, logger: SessionLogger):
           self.logger = logger
           self.multi_project: MultiProjectCoordinator | None = None
           self.advanced_search: AdvancedSearchEngine | None = None
           # ... other optional features
   ```

1. **Move MCP tool functions**

   - Natural language scheduling tools (5 functions)
   - Interruption management (1 function)
   - Multi-project coordination (4 functions)
   - Advanced search (3 functions)
   - Git worktree management (5 functions)
   - Session welcome (1 function)

1. **Update tool registration**

   ```text
   # tools/advanced_tools.py (NEW)
   def register_advanced_tools(mcp: FastMCP, features_hub: AdvancedFeaturesHub):
       @mcp.tool()
       async def create_natural_reminder(...) -> str:
           return await features_hub.create_natural_reminder(...)
   ```

1. **Update `server.py` initialization**

   ```python
   # server.py
   from session_buddy.advanced_features import AdvancedFeaturesHub

   features_hub = AdvancedFeaturesHub(session_logger)
   await features_hub.initialize()

   # Register advanced tools
   from session_buddy.tools.advanced_tools import register_advanced_tools

   register_advanced_tools(mcp, features_hub)
   ```

**Success Criteria:**

- All advanced feature tests pass
- Tool registration works correctly
- No breaking changes to MCP tool interface
- Coverage ≥80% for advanced_features.py

______________________________________________________________________

### Phase 5: Extract Core Server (Week 4-5)

**Risk:** High | **Effort:** 10 hours | **Reversibility:** 70%

1. **Create `MCPServerCore` class in `server_core.py`**

   ```text
   class MCPServerCore:
       def __init__(self):
           self.logger = SessionLogger(Path.home() / ".claude" / "logs")
           self.permissions = SessionPermissionsManager(Path.home() / ".claude")
           self.config = self._load_config()
           self.mcp = FastMCP("session-buddy", lifespan=self.session_lifecycle)

       async def session_lifecycle(self, app: Any) -> AsyncGenerator[None]:
           """FastMCP lifespan handler"""
           # Move session_lifecycle logic here

       def register_all_tools(self) -> None:
           """Register all tool modules"""
           from .tools import (
               register_crackerjack_tools,
               register_llm_tools,
               # ... all tool registrations
           )

           register_crackerjack_tools(self.mcp)
           # ... register all tools

       def run(self, http_mode: bool = False, http_port: int | None = None) -> None:
           """Start server"""
           # Move main() logic here
   ```

1. **Move classes to `server_core.py`**

   - `SessionLogger` (100 lines)
   - `SessionPermissionsManager` (95 lines)

1. **Move configuration functions**

   - `_load_mcp_config()`
   - `_detect_other_mcp_servers()`
   - `_generate_server_guidance()`

1. **Move initialization functions**

   - `auto_setup_git_working_directory()`
   - `initialize_new_features()`
   - `analyze_project_context()`

1. **Update `server.py` to become a thin wrapper**

   ```python
   # server.py (now ~200 lines)
   from session_buddy.server_core import MCPServerCore

   # Create server instance
   server_core = MCPServerCore()
   mcp = server_core.mcp  # Expose for backwards compatibility

   # Register all tools
   server_core.register_all_tools()


   def main(http_mode: bool = False, http_port: int | None = None) -> None:
       """Entry point delegates to core"""
       server_core.run(http_mode, http_port)


   if __name__ == "__main__":
       import sys

       http_mode = "--http" in sys.argv
       http_port = None
       if "--http-port" in sys.argv:
           port_idx = sys.argv.index("--http-port")
           if port_idx + 1 < len(sys.argv):
               http_port = int(sys.argv[port_idx + 1])
       main(http_mode, http_port)
   ```

1. **Update lifecycle manager**

   ```python
   # core/session_manager.py
   from session_buddy.server_core import MCPServerCore


   class SessionLifecycleManager:
       def __init__(self, server_core: MCPServerCore):
           self.server_core = server_core
           self.logger = server_core.logger
   ```

**Success Criteria:**

- Server starts successfully in both STDIO and HTTP modes
- All tools register correctly
- Lifespan hooks work (git repo auto-init)
- All integration tests pass
- Coverage ≥85% for server_core.py

______________________________________________________________________

### Phase 6: Final Cleanup & Validation (Week 5)

**Risk:** Low | **Effort:** 4 hours | **Reversibility:** 100%

1. **Remove duplicate code from `server.py`**

   - Remove moved functions (keep imports)
   - Remove moved classes (keep exports for backwards compatibility)

1. **Add deprecation warnings for direct imports**

```text
# server.py
import warnings

   def __getattr__(name: str):
       if name in ["SessionLogger", "SessionPermissionsManager"]:
           warnings.warn(
               f"{name} moved to server_core, update imports",
               DeprecationWarning,
               stacklevel=2
           )
           from session_buddy.server_core import ...
           return ...
       raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

1. **Update all internal imports**

   ```bash
   # Find all imports of moved components
   grep -r "from session_buddy.server import" session_buddy/

   # Update to new module locations
   sed -i 's/from session_buddy.server import SessionLogger/from session_buddy.server_core import SessionLogger/g' session_buddy/**/*.py
   ```

1. **Run full test suite**

   ```bash
   pytest tests/ -v --cov=session_buddy --cov-report=term-missing --cov-fail-under=85
   ```

1. **Run quality checks**

   ```bash
   python -m crackerjack -t
   ```

1. **Update documentation**

   - Update CLAUDE.md with new module structure
   - Update README.md architecture section
   - Add migration guide for external consumers

**Success Criteria:**

- All tests pass (unit, integration, functional)
- Coverage ≥85% across all new modules
- No linting/type errors
- server.py reduced to \<300 lines
- All 4 new modules \<1200 lines each
- Zero breaking changes for external users

______________________________________________________________________

## ACB Integration Opportunities

### 1. Dependency Injection

**Current:** Global variables and singletons throughout server.py
**ACB Pattern:** Constructor injection with protocols

```python
# Before (server.py)
session_logger = SessionLogger(claude_dir / "logs")
permissions_manager = SessionPermissionsManager(claude_dir)

# After (server_core.py with ACB)
from acb import Container, injectable


@injectable
class MCPServerCore:
    def __init__(
        self,
        logger: SessionLogger = Depends(SessionLogger),
        permissions: SessionPermissionsManager = Depends(SessionPermissionsManager),
        config: ServerConfig = Depends(ServerConfig),
    ):
        self.logger = logger
        self.permissions = permissions
        self.config = config
```

### 2. Cache Integration

**Current:** No caching for expensive operations
**ACB Pattern:** Decorator-based caching with TTL

```python
# quality_engine.py with ACB cache
from acb.cache import cached


class QualityEngine:
    @cached(ttl=300, key="quality_score:{project_dir}")
    async def calculate_quality_score(self) -> QualityScoreResult:
        """Cache quality scores for 5 minutes"""

    @cached(ttl=60, key="file_count:{project_dir}")
    def _count_significant_files(self, current_dir: Path) -> int:
        """Cache file counts for 1 minute"""
```

### 3. Settings Management

**Current:** Hardcoded configuration and magic numbers
**ACB Pattern:** Typed settings with validation

```python
# server_core.py with ACB settings
from acb.settings import Settings
from pydantic import Field


class ServerSettings(Settings):
    http_enabled: bool = Field(False, description="Enable HTTP transport")
    http_host: str = Field("127.0.0.1", description="HTTP server host")
    http_port: int = Field(8678, description="HTTP server port")
    websocket_monitor_port: int = Field(8677, description="WebSocket monitor port")


class QualitySettings(Settings):
    compaction_file_threshold: int = Field(50, description="File count for compaction")
    compaction_commit_threshold: int = Field(5, description="Recent commits threshold")
    quality_score_cache_ttl: int = Field(
        300, description="Quality score cache TTL (seconds)"
    )
```

### 4. Logging Integration

**Current:** Custom `SessionLogger` class
**ACB Pattern:** Structured logging with context propagation

```text
# server_core.py with ACB logging
from acb.logging import get_logger, log_context


class MCPServerCore:
    def __init__(self):
        self.logger = get_logger(__name__)

    async def session_lifecycle(self, app: Any) -> AsyncGenerator[None]:
        with log_context(operation="session_init", git_root=str(git_root)):
            self.logger.info("Git repository detected")
            # ACB automatically adds context to all log entries
```

______________________________________________________________________

## Risk Assessment & Mitigation

### High-Risk Areas

#### 1. **Global State Management**

**Risk:** Breaking existing code that relies on global variables
**Severity:** High | **Probability:** Medium

**Mitigation:**

- Phase 5 defers global state changes to the end
- Keep compatibility layer in server.py during migration
- Add comprehensive integration tests before touching globals
- Use deprecation warnings rather than immediate removal

#### 2. **Circular Dependencies**

**Risk:** New modules creating import cycles
**Severity:** High | **Probability:** Low

**Mitigation:**

- Use protocols/interfaces for dependencies
- Late imports where necessary (inside functions)
- Dependency injection to break cycles
- Run import analysis after each phase:
  ```bash
  python -c "import session_buddy.server_core; print('✅ No circular deps')"
  ```

#### 3. **Test Coverage Regression**

**Risk:** Losing test coverage during code moves
**Severity:** Medium | **Probability:** Medium

**Mitigation:**

- Run coverage report after each phase
- Add new unit tests for extracted modules
- Keep coverage ≥85% requirement throughout
- Use `pytest --cov-fail-under=85` in CI

### Medium-Risk Areas

#### 4. **MCP Tool Registration**

**Risk:** Tools not registering correctly in new structure
**Severity:** Medium | **Probability:** Low

**Mitigation:**

- Phase 4 tests tool registration thoroughly
- Manual verification of each tool via MCP inspector
- Integration tests for every MCP tool
- Gradual migration (register some tools from new modules while keeping others in server.py)

#### 5. **Performance Regression**

**Risk:** Additional indirection slowing down operations
**Severity:** Low | **Probability:** Low

**Mitigation:**

- Benchmark quality scoring before/after migration
- Use ACB caching to offset any overhead
- Profile hot paths in new modules
- Target: \<5% performance regression

### Low-Risk Areas

#### 6. **Formatting Functions**

**Risk:** Breaking display output
**Severity:** Low | **Probability:** Very Low

**Mitigation:**

- Phase 2 is lowest risk (pure functions)
- Snapshot tests for formatted output
- Easy rollback if issues found

______________________________________________________________________

## Testing Strategy

### Unit Tests (New Tests Required)

#### `test_server_core.py` (15+ tests)

```python
def test_session_logger_initialization():
    """Test SessionLogger creates log files correctly"""


def test_permissions_manager_singleton():
    """Test SessionPermissionsManager singleton behavior"""


async def test_mcp_server_core_initialization():
    """Test MCPServerCore initializes all components"""


async def test_session_lifecycle_git_repo():
    """Test lifespan auto-initializes for git repos"""


async def test_session_lifecycle_non_git():
    """Test lifespan skips non-git directories"""


def test_load_mcp_config_valid():
    """Test loading valid .mcp.json configuration"""


def test_load_mcp_config_missing():
    """Test fallback when .mcp.json missing"""


def test_detect_other_mcp_servers():
    """Test MCP server detection logic"""
```

#### `test_quality_engine.py` (20+ tests)

```python
async def test_calculate_quality_score_v2():
    """Test V2 quality scoring algorithm"""


async def test_quality_score_caching():
    """Test quality score caching behavior"""


async def test_should_suggest_compact_large_project():
    """Test compaction suggestion for large projects"""


async def test_should_suggest_compact_active_dev():
    """Test compaction suggestion for active development"""


async def test_perform_strategic_compaction():
    """Test context compaction execution"""


async def test_capture_session_insights():
    """Test session intelligence capture"""


async def test_analyze_token_usage_patterns():
    """Test token usage analysis"""


async def test_analyze_conversation_flow():
    """Test conversation flow analysis"""
```

#### `test_advanced_features.py` (15+ tests)

```python
async def test_features_hub_initialization():
    """Test AdvancedFeaturesHub lazy initialization"""


async def test_create_natural_reminder():
    """Test natural language reminder creation"""


async def test_multi_project_coordination():
    """Test multi-project search and insights"""


async def test_git_worktree_management():
    """Test worktree create/list/remove operations"""


async def test_advanced_search():
    """Test faceted search functionality"""
```

#### `test_server_helpers.py` (30+ tests)

```python
def test_format_worktree_status():
    """Test worktree status formatting"""


def test_format_reminders_list():
    """Test reminders list formatting"""


async def test_setup_claude_directory():
    """Test Claude directory setup"""


async def test_setup_uv_dependencies():
    """Test UV dependency management"""


def test_generate_quality_recommendations():
    """Test quality recommendation generation"""
```

### Integration Tests

#### `test_server_integration.py`

```python
async def test_full_server_startup():
    """Test complete server initialization"""


async def test_tool_registration():
    """Test all tools register correctly"""


async def test_session_lifecycle_flow():
    """Test complete session lifecycle (init → checkpoint → end)"""


async def test_quality_scoring_integration():
    """Test quality scoring with real project"""


async def test_advanced_features_integration():
    """Test advanced features work together"""
```

### Migration Validation Tests

#### `test_backwards_compatibility.py`

```python
def test_server_py_imports_still_work():
    """Test old imports from server.py still work"""
    from session_buddy.server import SessionLogger, SessionPermissionsManager

    assert SessionLogger is not None


def test_mcp_variable_accessible():
    """Test mcp variable accessible from server module"""
    from session_buddy.server import mcp

    assert mcp is not None


async def test_calculate_quality_score_callable():
    """Test calculate_quality_score function still callable"""
    from session_buddy.server import calculate_quality_score

    result = await calculate_quality_score()
    assert "total_score" in result
```

______________________________________________________________________

## Success Metrics

### Code Quality Metrics

- **Cognitive Complexity:** ≤15 per function (crackerjack standard)
- **Module Size:** All modules \<1200 lines
- **Test Coverage:** ≥85% across all modules
- **Type Coverage:** 100% type hints with pyright compliance
- **Linting:** Zero ruff/black/isort violations

### Functional Metrics

- **Zero Breaking Changes:** All existing tests pass
- **Performance:** \<5% regression in quality scoring
- **Startup Time:** \<10% increase in server startup
- **Memory Usage:** No increase in baseline memory

### Maintainability Metrics

- **Lines of Code:** `server.py` reduced from 3,962 to \<300 lines
- **Duplicate Code:** Zero duplication between modules
- **Import Complexity:** Reduced from 50+ to \<20 per module
- **Dependency Depth:** Max 3 levels between modules

### Migration Success Criteria

- ✅ All phases completed without rollback
- ✅ All tests passing (unit, integration, functional)
- ✅ Documentation updated (CLAUDE.md, README.md)
- ✅ No deprecation warnings in test suite
- ✅ ACB integration patterns applied to ≥2 modules

______________________________________________________________________

## Timeline & Effort Estimation

| Phase | Duration | Effort | Risk | Reversibility |
|-------|----------|--------|------|---------------|
| Phase 1: Skeletons | 2 hours | Low | Low | 100% |
| Phase 2: Utilities | 4 hours | Low | Low | 100% |
| Phase 3: Quality Engine | 8 hours | Medium | Medium | 90% |
| Phase 4: Advanced Features | 6 hours | Medium | Medium | 90% |
| Phase 5: Core Server | 10 hours | High | High | 70% |
| Phase 6: Cleanup | 4 hours | Low | Low | 100% |
| **Total** | **34 hours** | **~5 days** | **Medium** | **90% avg** |

### Weekly Breakdown

- **Week 1:** Phases 1-2 (Skeletons + Utilities) - Low risk foundation
- **Week 2:** Phase 3 (Quality Engine) - Medium risk, high value
- **Week 3-4:** Phase 4 (Advanced Features) - Medium risk, isolated changes
- **Week 4-5:** Phase 5 (Core Server) - High risk, careful execution
- **Week 5:** Phase 6 (Cleanup & Validation) - Final polish

______________________________________________________________________

## Rollback Strategy

### If Issues Arise in Phase 1-2

**Impact:** Minimal
**Rollback:** Delete new module files, restore server.py to original

```bash
git checkout HEAD -- session_buddy/server.py
rm session_buddy/server_core.py
rm session_buddy/quality_engine.py
rm session_buddy/advanced_features.py
rm session_buddy/utils/server_helpers.py
pytest tests/ -v  # Verify rollback success
```

### If Issues Arise in Phase 3-4

**Impact:** Medium
**Rollback:** Revert module, restore imports in server.py

```bash
git revert <commit-hash>  # Revert the problematic phase
# Update server.py to restore original function implementations
# Re-run tests to verify
```

### If Issues Arise in Phase 5

**Impact:** High
**Rollback:** Full git revert, keep utility/quality modules

```bash
git revert <phase-5-commits>
# Keep Phase 1-4 work (utilities, quality engine, advanced features)
# Restore original server.py core infrastructure
# Update imports to use new utilities while keeping core in server.py
```

### Emergency Full Rollback

**Impact:** Critical failure
**Rollback:** Complete revert to pre-migration state

```bash
git reset --hard <pre-migration-commit>
pytest tests/ -v --cov=session_buddy --cov-fail-under=85
# Verify full functionality restored
```

______________________________________________________________________

## Post-Migration Benefits

### Immediate Benefits

1. **Reduced Complexity:** 4 focused modules vs 1 monolith
1. **Improved Testability:** Isolated components, easier mocking
1. **Better Navigation:** Clear module boundaries, faster code comprehension
1. **Easier Debugging:** Smaller scope per module reduces bug surface area
1. **Faster Builds:** Incremental compilation benefits from module boundaries

### Long-term Benefits

1. **ACB Integration:** Clean interfaces enable dependency injection, caching, settings
1. **Feature Isolation:** Advanced features can be disabled/mocked independently
1. **Parallel Development:** Multiple developers can work on different modules
1. **Migration Preparation:** Modular structure simplifies future refactoring
1. **Technical Debt Reduction:** Clear responsibilities prevent code drift

### Maintenance Benefits

1. **Easier Onboarding:** New developers understand focused modules faster
1. **Safer Changes:** Module boundaries limit blast radius of changes
1. **Better Code Review:** Smaller, focused PRs for module changes
1. **Refactoring Confidence:** High test coverage enables fearless refactoring
1. **Documentation Clarity:** Module-level docs more maintainable than monolith

______________________________________________________________________

## Appendix A: Module Size Estimates

### Current Distribution (server.py: 3,962 lines)

```
Core Infrastructure:          485 lines (12%)
Session Lifecycle:            417 lines (11%)
Quality & Analysis:         1,953 lines (49%)
Advanced Features:            992 lines (25%)
Main Entry Point:             115 lines (3%)
```

### Post-Migration Distribution

```
server.py (thin wrapper):     ~250 lines (6%)
server_core.py:               ~900 lines (23%)
quality_engine.py:          ~1,100 lines (28%)
advanced_features.py:       ~1,000 lines (25%)
utils/server_helpers.py:      ~900 lines (23%)

Total: ~4,150 lines (includes new structure overhead)
```

### Size Comparison by Module

| Module | Current (in server.py) | Post-Migration | Change |
|--------|------------------------|----------------|--------|
| server.py | 3,962 lines | 250 lines | -94% |
| server_core.py | N/A | 900 lines | +900 |
| quality_engine.py | N/A | 1,100 lines | +1,100 |
| advanced_features.py | N/A | 1,000 lines | +1,000 |
| utils/server_helpers.py | N/A | 900 lines | +900 |

______________________________________________________________________

## Appendix B: Import Dependency Matrix

### Current (server.py imports)

```text
# Internal (20+ modules)
from session_buddy.reflection_tools import ...
from session_buddy.core.session_manager import ...
from session_buddy.tools import ...
from session_buddy.utils import ...
from session_buddy.multi_project_coordinator import ...
from session_buddy.advanced_search import ...
from session_buddy.app_monitor import ...
from session_buddy.llm_providers import ...
from session_buddy.serverless_mode import ...
from session_buddy.natural_scheduler import ...
from session_buddy.interruption_manager import ...
from session_buddy.worktree_manager import ...
from session_buddy.crackerjack_integration import ...

# External (10+ modules)
from fastmcp import FastMCP
import duckdb
import tomli
import asyncio
import logging
import subprocess
import shutil
```

### Post-Migration (per module)

#### server_core.py imports

```text
from fastmcp import FastMCP
from session_buddy.quality_engine import QualityEngine
from session_buddy.advanced_features import AdvancedFeaturesHub
from session_buddy.utils.git_operations import ...
from session_buddy.utils.server_helpers import ...
from session_buddy.reflection_tools import ...
import tomli
import logging
import asyncio
```

#### quality_engine.py imports

```text
from session_buddy.utils.quality_utils_v2 import ...
from session_buddy.reflection_tools import ...
from session_buddy.utils.git_operations import ...
import subprocess
from pathlib import Path
from dataclasses import dataclass
```

#### advanced_features.py imports

```text
from session_buddy.multi_project_coordinator import ...
from session_buddy.advanced_search import ...
from session_buddy.natural_scheduler import ...
from session_buddy.interruption_manager import ...
from session_buddy.worktree_manager import ...
from session_buddy.app_monitor import ...
from session_buddy.llm_providers import ...
from session_buddy.serverless_mode import ...
from typing import TYPE_CHECKING
```

#### utils/server_helpers.py imports

```text
from session_buddy.utils.format_utils import ...
from session_buddy.utils.quality_utils import ...
from session_buddy.reflection_tools import ...
from pathlib import Path
from datetime import datetime
```

______________________________________________________________________

## Appendix C: Function Migration Checklist

### Phase 2: Utilities (42 functions)

- [ ] `_setup_claude_directory`
- [ ] `_setup_uv_dependencies`
- [ ] `_handle_uv_operations`
- [ ] `_run_uv_sync_and_compile`
- [ ] `_setup_session_management`
- [ ] `_analyze_project_structure`
- [ ] `_add_final_summary`
- [ ] `_add_permissions_and_tools_summary`
- [ ] `_generate_quality_recommendations`
- [ ] `_format_no_reminders_message`
- [ ] `_format_reminders_header`
- [ ] `_format_single_reminder`
- [ ] `_format_reminders_list`
- [ ] `_format_reminder_basic_info`
- [ ] `_calculate_overdue_time`
- [ ] `_format_interruption_statistics`
- [ ] `_format_snapshot_statistics`
- [ ] `_has_statistics_data`
- [ ] `_format_project_insights`
- [ ] `_format_project_activity_section`
- [ ] `_format_common_patterns_section`
- [ ] `_build_advanced_search_filters`
- [ ] `_format_advanced_search_results`
- [ ] `_format_worktree_status`
- [ ] `_format_worktree_list_header`
- [ ] `_get_worktree_indicators`
- [ ] `_format_single_worktree`
- [ ] `_format_session_summary`
- [ ] `_format_worktree_status_display`
- [ ] `_format_basic_worktree_info`
- [ ] `_format_session_info`
- [ ] `_format_conversation_summary`
- [ ] `_ensure_default_recommendations`

### Phase 3: Quality Engine (30 functions)

- [ ] `calculate_quality_score`
- [ ] `should_suggest_compact`
- [ ] `perform_strategic_compaction`
- [ ] `capture_session_insights`
- [ ] `analyze_context_usage`
- [ ] `generate_session_intelligence`
- [ ] `monitor_proactive_quality`
- [ ] `_optimize_reflection_database`
- [ ] `_analyze_context_compaction`
- [ ] `_store_context_summary`
- [ ] `summarize_current_conversation`
- [ ] `analyze_token_usage_patterns`
- [ ] `analyze_conversation_flow`
- [ ] `analyze_memory_patterns`
- [ ] `analyze_project_workflow_patterns`
- [ ] `_count_significant_files`
- [ ] `_check_git_activity`
- [ ] `_evaluate_large_project_heuristic`
- [ ] `_evaluate_git_activity_heuristic`
- [ ] `_evaluate_python_project_heuristic`
- [ ] `_get_default_compaction_reason`
- [ ] `_get_fallback_compaction_reason`
- [ ] `_generate_basic_insights`
- [ ] `_add_project_context_insights`
- [ ] `_add_session_health_insights`
- [ ] `_generate_session_tags`
- [ ] `_capture_flow_analysis`
- [ ] `_capture_intelligence_insights`

### Phase 4: Advanced Features (19 MCP tools)

- [ ] `create_natural_reminder`
- [ ] `list_user_reminders`
- [ ] `cancel_user_reminder`
- [ ] `start_reminder_service`
- [ ] `stop_reminder_service`
- [ ] `get_interruption_statistics`
- [ ] `create_project_group`
- [ ] `add_project_dependency`
- [ ] `search_across_projects`
- [ ] `get_project_insights`
- [ ] `advanced_search`
- [ ] `search_suggestions`
- [ ] `get_search_metrics`
- [ ] `git_worktree_list`
- [ ] `git_worktree_add`
- [ ] `git_worktree_remove`
- [ ] `git_worktree_status`
- [ ] `git_worktree_switch`
- [ ] `session_welcome`

### Phase 5: Core Server (7 components)

- [ ] `SessionLogger` class
- [ ] `SessionPermissionsManager` class
- [ ] `session_lifecycle` function
- [ ] `_load_mcp_config`
- [ ] `_detect_other_mcp_servers`
- [ ] `_generate_server_guidance`
- [ ] `auto_setup_git_working_directory`
- [ ] `initialize_new_features`
- [ ] `analyze_project_context`
- [ ] `main` function

______________________________________________________________________

## Appendix D: ACB Integration Examples

### Example 1: Dependency Injection in QualityEngine

```text
# Before (server.py)
session_logger = SessionLogger(claude_dir / "logs")


async def calculate_quality_score() -> dict[str, Any]:
    session_logger.info("Calculating quality score")
    # ... implementation


# After (quality_engine.py with ACB)
from acb import injectable, Depends
from session_buddy.server_core import SessionLogger


@injectable
class QualityEngine:
    def __init__(self, logger: SessionLogger = Depends(SessionLogger)):
        self.logger = logger

    async def calculate_quality_score(self) -> QualityScoreResult:
        self.logger.info("Calculating quality score")
        # ... implementation


# Usage
from acb import Container

container = Container()
quality_engine = container.resolve(QualityEngine)
result = await quality_engine.calculate_quality_score()
```

### Example 2: Caching in QualityEngine

```text
# Before (no caching)
def _count_significant_files(current_dir: Path) -> int:
    file_count = 0
    for file_path in current_dir.rglob("*"):
        # ... expensive file system traversal
    return file_count

# After (with ACB cache)
from acb.cache import cached, CacheConfig

class QualityEngine:
    @cached(
        ttl=60,  # Cache for 1 minute
        key="file_count:{current_dir}",
        config=CacheConfig(backend="memory")
    )
    def _count_significant_files(self, current_dir: Path) -> int:
        """Cache file counts - expensive operation"""
        file_count = 0
        for file_path in current_dir.rglob("*"):
            # ... expensive file system traversal
        return file_count
```

### Example 3: Settings Management

```python
# Before (hardcoded values)
if file_count > 50:
    return (True, "Large project detected")

if recent_commits > 5:
    return (True, "Active development detected")

# After (with ACB settings)
from acb.settings import Settings
from pydantic import Field


class QualitySettings(Settings):
    """Quality scoring configuration"""

    compaction_file_threshold: int = Field(
        50, description="File count threshold for compaction suggestion", ge=10, le=1000
    )
    compaction_commit_threshold: int = Field(
        5, description="Recent commits threshold for active development", ge=1, le=100
    )


class QualityEngine:
    def __init__(self, settings: QualitySettings = Depends(QualitySettings)):
        self.settings = settings

    def should_suggest_compact(self) -> tuple[bool, str]:
        if file_count > self.settings.compaction_file_threshold:
            return (True, "Large project detected")
        if recent_commits > self.settings.compaction_commit_threshold:
            return (True, "Active development detected")
```

### Example 4: Structured Logging

```text
# Before (custom SessionLogger)
session_logger.info(f"Processing quality score for {project}")
session_logger.error(f"Quality scoring failed: {error}")

# After (with ACB structured logging)
from acb.logging import get_logger, log_context


class QualityEngine:
    def __init__(self):
        self.logger = get_logger(__name__)

    async def calculate_quality_score(self) -> QualityScoreResult:
        with log_context(
            operation="quality_score", project=str(current_dir), version="2.0"
        ):
            self.logger.info("Starting quality score calculation")
            try:
                # ... calculation
                self.logger.info(
                    "Quality score calculated",
                    score=result.total_score,
                    breakdown=result.breakdown,
                )
            except Exception as e:
                self.logger.error(
                    "Quality scoring failed", error=str(e), error_type=type(e).__name__
                )
                raise
```

______________________________________________________________________

## Document Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-10 | Claude Code | Initial decomposition plan created |

______________________________________________________________________

**End of Document**
