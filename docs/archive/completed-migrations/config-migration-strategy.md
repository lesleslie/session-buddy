# Configuration Migration Strategy: Custom Pydantic → ACB Settings

**Architecture Council Decision Request**
**Date:** 2025-10-10
**Requester:** Architecture Council Chair
**Status:** PENDING REVIEW

______________________________________________________________________

## Executive Summary

We're migrating session-buddy's configuration system from custom Pydantic config (657 lines) to ACB Settings framework. This document presents architectural options, trade-offs, and a recommended migration strategy.

**Key Decision Points:**

1. Flat vs. Nested config structure
1. TOML vs. YAML configuration format
1. Migration strategy (incremental vs. big bang)
1. Validation preservation approach
1. Environment variable patterns

**Estimated Impact:** -558 lines (-85% reduction), improved consistency with ACB ecosystem

______________________________________________________________________

## Current State Analysis

### Architecture Overview

**File:** `session_buddy/config.py` (657 lines)

**Structure:**

```text
# 9 Pydantic BaseModel config classes (nested hierarchy)
├── DatabaseConfig (62 lines)
│   ├── DuckDB settings (path, timeouts, connections)
│   ├── Multi-project features (3 bools)
│   └── Search settings (3 fields)
├── SearchConfig (55 lines)
│   ├── Semantic search (model, cache)
│   ├── Faceted search (4 fields)
│   └── Full-text search (3 fields)
├── TokenOptimizationConfig (55 lines)
│   ├── Token limits (2 fields)
│   ├── Optimization strategies (4 fields)
│   └── Usage tracking (2 fields)
├── SessionConfig (75 lines)
│   ├── Checkpointing (3 fields)
│   ├── Permissions (2 fields)
│   ├── Session cleanup (2 fields)
│   └── Auto-store reflections (5 fields)
├── IntegrationConfig (39 lines)
│   ├── Crackerjack integration (2 fields)
│   ├── Git integration (2 fields)
│   └── Global workspace (2 fields)
├── LoggingConfig (58 lines)
│   ├── Core logging (2 fields)
│   ├── File logging (4 fields)
│   └── Performance logging (3 fields)
├── SecurityConfig (58 lines)
│   ├── Data privacy (2 fields)
│   ├── Access control (2 fields)
│   └── Input validation (2 fields)
├── SessionMgmtConfig (67 lines) - Main container
│   ├── Nested configs (7 fields above)
│   ├── MCP server settings (3 fields)
│   └── Development settings (2 fields)
└── ConfigLoader (153 lines)
    ├── Project root detection
    ├── TOML parsing (pyproject.toml)
    └── Environment variable support (SESSION_MGMT_ prefix)
```

**Configuration Source:** `pyproject.toml` → `[tool.session-buddy]` section

**Environment Variables:**

- Prefix: `SESSION_MGMT_`
- Nested delimiter: `__` (e.g., `SESSION_MGMT_DATABASE__PATH`)

### Validation Features

**Complex Validators:**

1. **Path Expansion** (`@field_validator`)

   - `DatabaseConfig.path`: Expands `~/.claude/data/reflection.duckdb`
   - `IntegrationConfig.global_workspace_path`: Expands `~/Projects/claude`
   - `LoggingConfig.log_file_path`: Expands + creates parent directories

1. **Cross-Field Validation** (`@model_validator`)

   - `TokenOptimizationConfig.validate_chunk_size`: Ensures chunk_size < max_tokens

1. **Template Validation** (`@field_validator`)

   - `SessionConfig.commit_message_template`: Requires `{timestamp}` placeholder

1. **Pattern Validation** (`@field_validator`)

   - `SecurityConfig.exclude_sensitive_patterns`: Validates regex patterns compile

### Strengths of Current System

✅ **Type Safety:** Comprehensive type hints with validation
✅ **Nested Organization:** Logical grouping by domain (database, search, session, etc.)
✅ **Environment Overrides:** Full env var support with nested delimiters
✅ **TOML Integration:** Lives alongside project metadata in pyproject.toml
✅ **Documentation:** In-line field descriptions and defaults
✅ **Testing-Friendly:** Easy to mock and override for tests

### Pain Points

❌ **Verbosity:** 657 lines for what should be ~100 lines of config
❌ **Custom Loader:** 153 lines of boilerplate for TOML parsing
❌ **No Hot Reload:** Requires process restart for config changes
❌ **Limited Merging:** No layered config (base + env-specific + local)
❌ **Manual Path Creation:** Custom logic for log directory creation
❌ **Inconsistency:** Different from ACB/Crackerjack ecosystem patterns

______________________________________________________________________

## Reference Implementation: Crackerjack + ACB

### ACB Settings Architecture

**File:** `crackerjack/config/settings.py` (269 lines)

**Structure:**

```text
from acb.config import Settings


class CrackerjackSettings(Settings):
    """Single flat Settings class with ALL fields."""

    # === Workflow Settings === (flat structure)
    clean: bool = True
    update_docs: bool = False
    skip_hooks: bool = False
    run_tests: bool = False
    # ... 50+ more flat fields ...

    # === Orchestration Settings ===
    enable_orchestration: bool = False
    cache_backend: str = "memory"
    max_parallel_hooks: int = 4

    # === QA Framework Settings ===
    project_root: Path = Field(default_factory=Path.cwd)
    qa_max_parallel_checks: int = 4

    @classmethod
    def load(cls, settings_dir: Path | None = None) -> CrackerjackSettings:
        """Load from YAML with layered merging."""
        from .loader import load_settings

        return load_settings(cls, settings_dir)
```

**Configuration Source:** YAML files in `settings/` directory

- `settings/crackerjack.yaml` (base configuration, committed)
- `settings/local.yaml` (local overrides, gitignored)

**Loader:** `crackerjack/config/loader.py` (194 lines)

```python
def load_settings[T: Settings](
    settings_class: type[T],
    settings_dir: Path | None = None,
) -> T:
    """Load with priority: local.yaml > crackerjack.yaml > defaults."""

    # Merge YAML files (priority order)
    config_files = [
        settings_dir / "crackerjack.yaml",
        settings_dir / "local.yaml",
    ]

    merged_data = {}
    for config_file in config_files:
        if config_file.exists():
            file_data = yaml.safe_load(f)
            merged_data.update(file_data)

    # Filter to only defined fields (ignore unknown YAML keys)
    relevant_data = {
        k: v for k, v in merged_data.items() if k in settings_class.model_fields
    }

    return settings_class(**relevant_data)
```

### ACB Settings Base Class Features

**From:** `acb/config.py` (943 lines - framework code)

**Key Capabilities:**

1. **Automatic YAML Loading**

   - Loads from `settings/` directory automatically
   - Priority: `local.yaml` > `{env}.yaml` > `app.yaml` > defaults

1. **Secret Management**

   - `SecretStr` fields with automatic masking
   - File-based secrets: `~/.acb/secrets/{field_name}`
   - Integration with cloud secret managers (AWS, GCP, Azure)

1. **Environment Variable Support**

   - Automatic mapping from settings fields
   - Nested delimiter support (configurable)

1. **Hot Reload Capability**

   - `ConfigHotReload` class monitors settings files
   - Automatic config refresh on file changes

1. **Validation via Pydantic**

   - Full Pydantic v2 validation support
   - `@field_validator` and `@model_validator` work as-is

1. **Library vs. Application Mode**

   - Detects when ACB is used as library (simplified init)
   - Testing mode with automatic test values

______________________________________________________________________

## Architectural Decision Matrix

### Decision 1: Flat vs. Nested Config Structure

#### Option A: Flat Structure (Crackerjack Pattern)

**Example:**

```text
from acb.config import Settings


class SessionMgmtSettings(Settings):
    # Database settings (flat namespace)
    database_path: str = "~/.claude/data/reflection.duckdb"
    database_connection_timeout: int = 30
    database_query_timeout: int = 120
    database_max_connections: int = 10
    database_enable_multi_project: bool = True

    # Search settings (flat namespace)
    search_enable_semantic: bool = True
    search_embedding_model: str = "all-MiniLM-L6-v2"
    search_embedding_cache_size: int = 1000

    # Session settings (flat namespace)
    session_auto_checkpoint_interval: int = 1800
    session_enable_auto_commit: bool = True
    # ... 50+ more fields ...
```

**Pros:**

- ✅ Simpler implementation (~100 lines total)
- ✅ Direct ACB compatibility (no custom logic)
- ✅ Matches Crackerjack ecosystem pattern
- ✅ Easier environment variable mapping (flat: `SESSION_MGMT_DATABASE_PATH`)
- ✅ No nested config class boilerplate

**Cons:**

- ❌ Long field names (`database_enable_multi_project` vs. `database.enable_multi_project`)
- ❌ Loses logical grouping in code navigation
- ❌ Harder to find related settings (must search by prefix)
- ❌ Namespace pollution (70+ fields in one class)

**Backwards Compatibility:** BREAKING

- Need migration guide for users accessing `config.database.path` → `config.database_path`

#### Option B: Nested Structure (Current Pattern)

**Example:**

```text
from acb.config import Settings
from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    path: str = "~/.claude/data/reflection.duckdb"
    connection_timeout: int = 30
    query_timeout: int = 120
    max_connections: int = 10
    enable_multi_project: bool = True


class SearchConfig(BaseModel):
    enable_semantic: bool = True
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_cache_size: int = 1000


class SessionMgmtSettings(Settings):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    # ... 7 nested configs ...
```

**Pros:**

- ✅ Logical grouping preserved (easier code navigation)
- ✅ Cleaner field names (shorter, grouped)
- ✅ Backwards compatible (no API changes)
- ✅ Better IntelliSense (IDE auto-completion by domain)
- ✅ Mirrors current mental model

**Cons:**

- ❌ More complex implementation (~250 lines)
- ❌ Requires custom YAML loading logic (nested dict merging)
- ❌ Environment variables more complex (`SESSION_MGMT_DATABASE__PATH`)
- ❌ ACB Settings not designed for nested configs (custom code needed)

**Backwards Compatibility:** MAINTAINED

- No code changes needed for users

#### Option C: Hybrid Approach (Flat Storage, Nested Access)

**Example:**

```text
from acb.config import Settings
from functools import cached_property


class SessionMgmtSettings(Settings):
    # Flat storage for ACB compatibility
    database_path: str = "~/.claude/data/reflection.duckdb"
    database_connection_timeout: int = 30
    search_enable_semantic: bool = True
    search_embedding_model: str = "all-MiniLM-L6-v2"

    # Nested access via properties (backwards compatibility)
    @cached_property
    def database(self) -> DatabaseView:
        """Provide nested access to database settings."""
        return DatabaseView(
            path=self.database_path,
            connection_timeout=self.database_connection_timeout,
            # ...
        )

    @cached_property
    def search(self) -> SearchView:
        """Provide nested access to search settings."""
        return SearchView(
            enable_semantic=self.search_enable_semantic,
            embedding_model=self.search_embedding_model,
            # ...
        )
```

**Pros:**

- ✅ ACB compatibility (flat storage)
- ✅ Backwards compatible API (nested access via properties)
- ✅ Best of both worlds

**Cons:**

- ❌ Most complex implementation (~200 lines)
- ❌ Dual representation (flat fields + view objects)
- ❌ Maintenance burden (must keep in sync)

______________________________________________________________________

### Decision 2: TOML vs. YAML Configuration Format

#### Option A: Keep TOML (pyproject.toml)

**Current:**

```toml
# pyproject.toml
[tool.session-buddy]
debug = false
server_host = "localhost"

[tool.session-buddy.database]
path = "~/.claude/data/reflection.duckdb"
connection_timeout = 30
enable_multi_project = true
```

**Pros:**

- ✅ Single file (project metadata + config)
- ✅ Standard Python packaging format
- ✅ Backwards compatible (no user changes)
- ✅ Familiar to Python developers

**Cons:**

- ❌ ACB Settings expects YAML (custom loader needed)
- ❌ No layered config (no local overrides)
- ❌ Can't have `.gitignore`d local config
- ❌ Inconsistent with Crackerjack/ACB ecosystem

#### Option B: Switch to YAML (settings/ directory)

**New:**

```yaml
# settings/session-mgmt.yaml (committed)
debug: false
server_host: localhost

database_path: "~/.claude/data/reflection.duckdb"
database_connection_timeout: 30
database_enable_multi_project: true

# settings/local.yaml (gitignored - local overrides)
debug: true
logging_level: DEBUG
```

**Pros:**

- ✅ Native ACB Settings support (no custom loader)
- ✅ Layered config (base + local overrides)
- ✅ Hot reload capability (ACB ConfigHotReload)
- ✅ Consistent with Crackerjack ecosystem
- ✅ Better for environment-specific config

**Cons:**

- ❌ Requires migration (breaking change)
- ❌ Two files instead of one (settings/ + pyproject.toml)
- ❌ YAML less familiar to some Python devs

#### Option C: Support Both (Dual Mode)

**Implementation:**

```python
class SessionMgmtSettings(Settings):
    @classmethod
    def load(cls, config_path: Path | None = None) -> SessionMgmtSettings:
        """Load from YAML (preferred) or TOML (fallback)."""

        # Try YAML first (ACB pattern)
        if (Path("settings") / "session-mgmt.yaml").exists():
            return load_from_yaml(cls)

        # Fallback to TOML (backwards compatibility)
        if (Path("pyproject.toml")).exists():
            return load_from_toml(cls)

        # Use defaults
        return cls()
```

**Pros:**

- ✅ Backwards compatible (TOML still works)
- ✅ Future-proof (YAML recommended)
- ✅ Gradual migration path

**Cons:**

- ❌ Complex implementation (dual loaders)
- ❌ Confusion about which format to use
- ❌ Maintenance burden (support both forever?)

______________________________________________________________________

### Decision 3: Migration Strategy

#### Option A: Big Bang Replacement

**Timeline:** 1 week (3-4 days implementation + testing)

**Steps:**

1. **Day 1-2:** Implement new ACB Settings class

   - Create `SessionMgmtSettings(Settings)` with chosen structure
   - Implement loader (YAML or TOML)
   - Add all validation logic

1. **Day 3:** Update all imports

   - Replace `from session_buddy.config import get_config` globally
   - Update to `from session_buddy.config import settings`
   - Fix 50+ import sites across codebase

1. **Day 4:** Test and validate

   - Run full test suite (ensure 34.6% coverage maintained)
   - Manual testing of all config-dependent features
   - Update documentation

**Pros:**

- ✅ Fast completion (1 week)
- ✅ Clean cut (no hybrid state)
- ✅ Maximum LOC reduction (-558 lines immediately)

**Cons:**

- ❌ High risk (one big change)
- ❌ Hard to rollback (everything changes at once)
- ❌ Blocks other work (merge conflicts)
- ❌ Difficult to test incrementally

#### Option B: Incremental Migration (Phased)

**Timeline:** 3-4 weeks (gradual, low-risk)

**Phase 1 (Week 1): Foundation**

- Create new `SessionMgmtSettings` alongside old `SessionMgmtConfig`
- Implement dual loading: try new, fallback to old
- Add feature flag: `USE_ACB_CONFIG=true`

**Phase 2 (Week 2): Migrate Core Modules**

- Update `server.py` to use new config
- Update `reflection_tools.py` to use new config
- Keep old config available for other modules

**Phase 3 (Week 3): Migrate Tools & Utils**

- Update `tools/*.py` to use new config
- Update `utils/*.py` to use new config
- Remove fallback logic from core modules

**Phase 4 (Week 4): Complete & Cleanup**

- Remove old config system entirely
- Update all documentation
- Final testing and validation

**Pros:**

- ✅ Low risk (incremental changes)
- ✅ Easy rollback (feature flag)
- ✅ Continuous testing (validate each phase)
- ✅ Parallel work (other features can continue)

**Cons:**

- ❌ Slower (3-4 weeks vs. 1 week)
- ❌ Dual config state (complexity during migration)
- ❌ More commits/PRs to review

#### Option C: Parallel Implementation (Compatibility Layer)

**Timeline:** 2 weeks (best of both worlds)

**Implementation:**

```text
# New ACB Settings (100 lines)
class SessionMgmtSettings(Settings):
    database_path: str = "~/.claude/data/reflection.duckdb"
    # ... flat structure ...


# Backwards compatibility layer (50 lines)
class ConfigCompatibilityLayer:
    """Provides old nested API on top of new flat config."""

    def __init__(self, settings: SessionMgmtSettings):
        self._settings = settings

    @cached_property
    def database(self) -> DatabaseConfig:
        """Legacy nested access."""
        return DatabaseConfig(
            path=self._settings.database_path,
            connection_timeout=self._settings.database_connection_timeout,
            # ...
        )

    # ... other nested views ...


# Usage: old code works unchanged
config = ConfigCompatibilityLayer(settings)
config.database.path  # Works!
config.session.auto_checkpoint_interval  # Works!
```

**Pros:**

- ✅ Fast migration (2 weeks)
- ✅ Zero breaking changes (full backwards compatibility)
- ✅ Gradual deprecation path (warn users to migrate)
- ✅ Can remove compat layer in v2.0

**Cons:**

- ❌ More code initially (+150 lines compat layer)
- ❌ Two APIs to maintain temporarily
- ❌ LOC reduction delayed (-558 lines eventually, not immediately)

______________________________________________________________________

## Validation Migration Strategy

### Current Validators (Must Preserve)

**1. Path Expansion (3 validators)**

```python
# Current
@field_validator("path")
@classmethod
def expand_path(cls, v: str) -> str:
    return os.path.expanduser(v)
```

**ACB Pattern:**

```python
# Option A: Keep validators (ACB Settings supports this)
class SessionMgmtSettings(Settings):
    database_path: str = "~/.claude/data/reflection.duckdb"

    @field_validator("database_path")
    @classmethod
    def expand_database_path(cls, v: str) -> str:
        return Path(v).expanduser().as_posix()


# Option B: Use ACB Path type (automatic expansion)
from acb.adapters import AsyncPath


class SessionMgmtSettings(Settings):
    database_path: AsyncPath = AsyncPath("~/.claude/data/reflection.duckdb")
    # Automatic expansion via AsyncPath.__init__
```

**Recommendation:** Option A (explicit validators, clear intent)

**2. Cross-Field Validation (1 validator)**

```python
# Current
@model_validator(mode="after")
def validate_chunk_size(self) -> "TokenOptimizationConfig":
    if self.default_chunk_size >= self.default_max_tokens:
        self.default_chunk_size = max(50, self.default_max_tokens // 2)
    return self
```

**ACB Pattern:**

```python
class SessionMgmtSettings(Settings):
    token_optimization_default_max_tokens: int = 4000
    token_optimization_default_chunk_size: int = 2000

    @model_validator(mode="after")
    def validate_token_optimization(self) -> "SessionMgmtSettings":
        """Ensure chunk size is not larger than max tokens."""
        max_tokens = self.token_optimization_default_max_tokens
        chunk_size = self.token_optimization_default_chunk_size

        if chunk_size >= max_tokens:
            self.token_optimization_default_chunk_size = max(50, max_tokens // 2)

        return self
```

**Recommendation:** Keep as-is (ACB Settings fully supports `@model_validator`)

**3. Template Validation (1 validator)**

```python
# Current
@field_validator("commit_message_template")
@classmethod
def validate_commit_template(cls, v: str) -> str:
    if "{timestamp}" not in v:
        raise ValueError("Must contain {timestamp} placeholder")
    return v
```

**ACB Pattern:** Same (no changes needed)

**4. Regex Pattern Validation (1 validator)**

```python
# Current
@field_validator("exclude_sensitive_patterns")
@classmethod
def validate_patterns(cls, v: list[str]) -> list[str]:
    import re

    for pattern in v:
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e
    return v
```

**ACB Pattern:** Same (no changes needed)

______________________________________________________________________

## Environment Variable Strategy

### Current Pattern (Nested Delimiter)

```bash
# Nested config access: config.database.path
SESSION_MGMT_DATABASE__PATH="/custom/path/reflection.duckdb"

# Nested config access: config.session.auto_checkpoint_interval
SESSION_MGMT_SESSION__AUTO_CHECKPOINT_INTERVAL=3600
```

**Pydantic Settings Config:**

```python
model_config = SettingsConfigDict(
    env_prefix="SESSION_MGMT_",
    env_nested_delimiter="__",  # Double underscore
    case_sensitive=False,
)
```

### Flat Structure Pattern

```bash
# Flat config access: config.database_path
SESSION_MGMT_DATABASE_PATH="/custom/path/reflection.duckdb"

# Flat config access: config.session_auto_checkpoint_interval
SESSION_MGMT_SESSION_AUTO_CHECKPOINT_INTERVAL=3600
```

**ACB Settings Config:**

```python
# ACB automatically maps env vars to fields
# PREFIX + FIELD_NAME (uppercase)
```

### Recommendation: Maintain Backwards Compatibility

**Strategy:** Support both patterns during migration

```python
class SessionMgmtSettings(Settings):
    database_path: str = "~/.claude/data/reflection.duckdb"

    @field_validator("database_path", mode="before")
    @classmethod
    def handle_legacy_env_var(cls, v: str | None) -> str:
        """Support both new and old env var patterns."""
        import os

        # Check new pattern first: SESSION_MGMT_DATABASE_PATH
        if v is None:
            v = os.getenv("SESSION_MGMT_DATABASE_PATH")

        # Fall back to old pattern: SESSION_MGMT_DATABASE__PATH
        if v is None:
            v = os.getenv("SESSION_MGMT_DATABASE__PATH")

        # Use default if no env var
        return v or "~/.claude/data/reflection.duckdb"
```

______________________________________________________________________

## Architecture Council Recommendations

### Recommended Approach: Option C (Parallel Implementation + YAML)

**Structure:** Flat storage with backwards compatibility layer
**Format:** YAML (with TOML fallback for transition)
**Migration:** Incremental (2-3 weeks with compat layer)
**Validation:** Preserve all validators (ACB supports them)

### Implementation Plan

#### Week 1: Foundation & New Config

**Goals:**

- Create new ACB Settings class (flat structure)
- Implement YAML loader with layered merging
- Add TOML fallback for backwards compatibility
- Preserve all validation logic

**Deliverables:**

1. **New file:** `session_buddy/config_v2.py` (~150 lines)

   ```text
   from acb.config import Settings


   class SessionMgmtSettings(Settings):
       """Unified settings for session management MCP server.

       Configuration Loading:
           Settings are loaded from YAML files in the settings directory:
           - settings/session-mgmt.yaml (base config, committed)
           - settings/local.yaml (local overrides, gitignored)

           Fallback: [tool.session-buddy] in pyproject.toml

       Priority Order:
           1. settings/local.yaml (highest - local overrides)
           2. settings/session-mgmt.yaml (base configuration)
           3. pyproject.toml [tool.session-buddy] (fallback)
           4. Defaults from this class (lowest)
       """

       # Database settings (flat namespace)
       database_path: str = Field(
           default="~/.claude/data/reflection.duckdb",
           description="Path to DuckDB database file",
       )
       database_connection_timeout: int = Field(default=30, ge=1, le=300)
       database_query_timeout: int = Field(default=120, ge=1, le=3600)
       # ... ~70 more flat fields ...

       # Validators (preserved as-is)
       @field_validator(
           "database_path", "integration_global_workspace_path", "logging_log_file_path"
       )
       @classmethod
       def expand_paths(cls, v: str) -> str:
           """Expand user paths."""
           return Path(v).expanduser().as_posix()

       @model_validator(mode="after")
       def validate_token_optimization(self) -> "SessionMgmtSettings":
           """Ensure chunk size < max tokens."""
           if (
               self.token_optimization_default_chunk_size
               >= self.token_optimization_default_max_tokens
           ):
               self.token_optimization_default_chunk_size = max(
                   50, self.token_optimization_default_max_tokens // 2
               )
           return self

       @classmethod
       def load(cls, settings_dir: Path | None = None) -> SessionMgmtSettings:
           """Load from YAML (preferred) or TOML (fallback)."""
           from .loader import load_settings_with_fallback

           return load_settings_with_fallback(cls, settings_dir)
   ```

1. **New file:** `session_buddy/config_compat.py` (~100 lines)

```text
   from functools import cached_property
   from session_buddy.config_v2 import SessionMgmtSettings


   class DatabaseConfig:
       """Backwards compatible view of database settings."""

       def __init__(self, settings: SessionMgmtSettings):
           self._settings = settings

       @property
       def path(self) -> str:
           return self._settings.database_path

       @property
       def connection_timeout(self) -> int:
           return self._settings.database_connection_timeout

       # ... other properties ...


   class SessionMgmtConfig:
       """Backwards compatible config wrapper."""

       def __init__(self, settings: SessionMgmtSettings):
           self._settings = settings

       @cached_property
       def database(self) -> DatabaseConfig:
           return DatabaseConfig(self._settings)

       @cached_property
       def search(self) -> SearchConfig:
           return SearchConfig(self._settings)

       # ... other nested views ...
```

1. **New file:** `session_buddy/loader.py` (~150 lines)

   ```text
   from pathlib import Path
   import yaml
   from acb.config import Settings


   def load_settings_with_fallback[T: Settings](
       settings_class: type[T],
       settings_dir: Path | None = None,
   ) -> T:
       """Load from YAML (preferred) or TOML (fallback)."""

       # Try YAML first (ACB pattern)
       if settings_dir is None:
           settings_dir = Path.cwd() / "settings"

       yaml_data = {}
       config_files = [
           settings_dir / "session-mgmt.yaml",
           settings_dir / "local.yaml",
       ]

       yaml_loaded = False
       for config_file in config_files:
           if config_file.exists():
               with open(config_file) as f:
                   file_data = yaml.safe_load(f) or {}
                   yaml_data.update(file_data)
                   yaml_loaded = True

       # Fallback to TOML if no YAML found
       if not yaml_loaded:
           yaml_data = load_from_pyproject_toml()

       # Filter to defined fields
       relevant_data = {
           k: v for k, v in yaml_data.items() if k in settings_class.model_fields
       }

       return settings_class(**relevant_data)
   ```

1. **New files:** YAML configs

   ```yaml
   # settings/session-mgmt.yaml (committed)
   # Base configuration for session-buddy

   # Server settings
   debug: false
   server_host: localhost
   server_port: 3000
   enable_websockets: true

   # Database settings
   database_path: "~/.claude/data/reflection.duckdb"
   database_connection_timeout: 30
   database_query_timeout: 120
   database_max_connections: 10
   database_enable_multi_project: true

   # Search settings
   search_enable_semantic: true
   search_embedding_model: "all-MiniLM-L6-v2"
   search_embedding_cache_size: 1000

   # ... all other settings with defaults ...
   ```

   ```yaml
   # settings/local.yaml.example (committed as template)
   # Copy to settings/local.yaml and customize
   # This file is gitignored

   # Example local overrides:
   # debug: true
   # logging_level: DEBUG
   # database_path: "/custom/path/reflection.duckdb"
   ```

1. **Tests:** `tests/unit/test_config_v2.py` (~200 lines)

   - Test YAML loading with priority
   - Test TOML fallback
   - Test all validators work correctly
   - Test backwards compatibility layer
   - Test environment variable overrides

**Success Criteria:**

- ✅ New config loads from YAML with layered merging
- ✅ TOML fallback works (no breaking changes)
- ✅ All validators preserved and working
- ✅ Backwards compat layer passes old tests
- ✅ Zero test failures

#### Week 2: Migration & Integration

**Goals:**

- Migrate core modules to new config
- Update imports across codebase
- Add deprecation warnings for old config
- Update documentation

**Migration Strategy:**

```python
# Step 1: Update config.py to provide both APIs
from session_buddy.config_v2 import SessionMgmtSettings
from session_buddy.config_compat import SessionMgmtConfig

# New API (recommended)
settings = SessionMgmtSettings.load()


# Old API (backwards compatible, deprecated)
def get_config(reload: bool = False) -> SessionMgmtConfig:
    """DEPRECATED: Use SessionMgmtSettings.load() instead."""
    import warnings

    warnings.warn(
        "get_config() is deprecated. Use SessionMgmtSettings.load()",
        DeprecationWarning,
        stacklevel=2,
    )
    _settings = SessionMgmtSettings.load()
    return SessionMgmtConfig(_settings)
```

**Module Migration Order:**

1. `server.py` (highest impact)
1. `reflection_tools.py` (core functionality)
1. `tools/*.py` (50+ import sites)
1. `utils/*.py` (utility modules)
1. `core/*.py` (session management)

**Deliverables:**

- ✅ All modules using new config
- ✅ Deprecation warnings in place
- ✅ Documentation updated (CLAUDE.md, README.md)
- ✅ Migration guide for users

#### Week 3: Cleanup & Polish

**Goals:**

- Remove old config system (if no external dependents)
- Remove backwards compatibility layer (optional, can keep for v2.0)
- Performance optimization
- Final testing

**Cleanup Options:**

**Option A: Aggressive (Remove old config immediately)**

- Delete `config.py` (old system) entirely (-657 lines)
- Delete `config_compat.py` (-100 lines)
- Force all users to YAML config
- **Total savings: -558 lines**

**Option B: Conservative (Keep compat layer until v2.0)**

- Keep `config.py` as thin wrapper around new system (-400 lines)
- Keep `config_compat.py` for backwards compatibility
- Gradual deprecation path (warn users for 6 months)
- **Total savings: -400 lines (immediate), -558 lines (v2.0)**

**Recommendation:** Option B (Conservative)

- Gives users time to migrate
- Less risk of breaking downstream projects
- Remove in v2.0 major version

______________________________________________________________________

## Comparison with Improvement Plan Estimate

### Original Plan Estimate

**Target:** -558 lines (-85% reduction)

**Calculation:**

```
Current: 657 lines (config.py)
Target: 100 lines (ACB config)
Savings: -558 lines
```

### Revised Realistic Estimate

**Week 1 (New Config System):**

```
+ config_v2.py:         150 lines  (ACB Settings class)
+ config_compat.py:     100 lines  (backwards compat layer)
+ loader.py:            150 lines  (YAML + TOML loader)
+ settings/*.yaml:       50 lines  (config files)
+ tests:                200 lines  (config tests)
-----------------------------------------------
Total new code:         650 lines
```

**Week 2 (Migration):**

```
- config.py deletions: -400 lines  (keep thin wrapper)
  (Old: 657 lines, New: 257 lines wrapper)
```

**Week 3 (Future - v2.0):**

```
- config.py:           -257 lines  (remove wrapper entirely)
- config_compat.py:    -100 lines  (remove compat layer)
-----------------------------------------------
Total future deletion: -357 lines
```

**Net Line Change:**

**Phase 1 (Immediate - Week 1-2):**

```
New code:     +650 lines
Deleted:      -400 lines
-----------------------------
Net change:   +250 lines  (temporary increase!)
```

**Phase 2 (Future - v2.0):**

```
Additional deletions: -357 lines
-----------------------------
Final net change: -107 lines from baseline
```

**Revised Estimate vs. Original Plan:**

- **Original plan:** -558 lines (-85%)
- **Realistic phase 1:** +250 lines (temporary increase for backwards compatibility)
- **Realistic phase 2 (v2.0):** -107 lines (-16%)

**Why the difference?**

1. **Backwards compatibility layer:** +100 lines (not in original estimate)
1. **Dual loader (YAML + TOML):** +100 lines (not in original estimate)
1. **Comprehensive tests:** +200 lines (essential for reliability)
1. **Conservative migration:** Keep old config as wrapper (not immediate deletion)

**Is the original estimate achievable?**
YES, but only with aggressive approach (no compat layer, YAML-only, delete old config immediately). This is **NOT RECOMMENDED** due to high risk.

______________________________________________________________________

## Risk Assessment

### High Priority Risks

**1. Breaking Changes for Downstream Users**

- **Risk:** Other projects depend on nested config API (`config.database.path`)
- **Mitigation:** Backwards compatibility layer (keeps old API working)
- **Detection:** Check for importers: `git grep "from session_buddy.config import get_config"`

**2. Environment Variable Breakage**

- **Risk:** Users with `SESSION_MGMT_DATABASE__PATH` env vars fail
- **Mitigation:** Support both old (nested) and new (flat) env var patterns
- **Testing:** Comprehensive env var tests in `test_config_v2.py`

**3. Validation Logic Loss**

- **Risk:** Complex validators don't translate to ACB Settings
- **Mitigation:** All validators preserved exactly as-is (Pydantic works with ACB)
- **Testing:** Validator-specific tests for each edge case

**4. YAML Migration Confusion**

- **Risk:** Users don't know YAML is now preferred format
- **Mitigation:** TOML fallback works seamlessly (no user action required)
- **Documentation:** Migration guide with examples

### Medium Priority Risks

**5. Hot Reload Implementation**

- **Risk:** ACB ConfigHotReload doesn't work as expected
- **Mitigation:** Phase 2 feature (not critical path)
- **Testing:** Manual testing with file watching

**6. Test Coverage Decrease**

- **Risk:** New config system has lower coverage than old (34.6% → lower)
- **Mitigation:** Comprehensive test suite (+200 lines tests)
- **Success metric:** Coverage must remain ≥34.6%

**7. Performance Regression**

- **Risk:** YAML parsing slower than TOML
- **Mitigation:** Cache loaded config, profile loading time
- **Acceptable:** \<100ms load time (currently ~50ms)

______________________________________________________________________

## Testing Strategy

### Test Coverage Goals

**New config system must achieve:**

- ✅ Unit test coverage: ≥80% (config_v2.py, loader.py)
- ✅ Integration tests: Full round-trip (load → use → reload)
- ✅ Backwards compat tests: Old API must pass existing tests
- ✅ Environment variable tests: Both old and new patterns
- ✅ Validator tests: All edge cases covered

### Test Suite Structure

```python
# tests/unit/test_config_v2.py
class TestSessionMgmtSettings:
    """Test new ACB Settings class."""

    def test_load_from_yaml(self):
        """Test YAML loading with priority."""
        ...

    def test_load_from_toml_fallback(self):
        """Test TOML fallback when no YAML exists."""
        ...

    def test_path_expansion_validator(self):
        """Test path expansion for database_path, etc."""
        ...

    def test_token_optimization_validator(self):
        """Test chunk_size < max_tokens validation."""
        ...

    def test_environment_variable_override_new_pattern(self):
        """Test SESSION_MGMT_DATABASE_PATH env var."""
        ...

    def test_environment_variable_override_old_pattern(self):
        """Test SESSION_MGMT_DATABASE__PATH env var (legacy)."""
        ...


# tests/unit/test_config_compat.py
class TestBackwardsCompatibility:
    """Test backwards compatibility layer."""

    def test_nested_database_access(self):
        """Test config.database.path still works."""
        config = SessionMgmtConfig(settings)
        assert config.database.path == "~/.claude/data/reflection.duckdb"

    def test_old_get_config_function(self):
        """Test get_config() function still works (deprecated)."""
        with pytest.warns(DeprecationWarning):
            config = get_config()
        assert isinstance(config, SessionMgmtConfig)

    # ... test all old nested access patterns ...


# tests/integration/test_config_round_trip.py
class TestConfigIntegration:
    """Test full config lifecycle."""

    def test_load_use_reload(self):
        """Test load → use in app → reload on change."""
        ...

    def test_hot_reload_yaml_change(self):
        """Test ACB ConfigHotReload detects file changes."""
        ...
```

### Manual Testing Checklist

- [ ] Load config from YAML (priority merging works)
- [ ] Load config from TOML (fallback works)
- [ ] Override with env vars (both patterns work)
- [ ] Access via old nested API (`config.database.path`)
- [ ] Access via new flat API (`settings.database_path`)
- [ ] All validators trigger correctly
- [ ] Hot reload detects YAML file changes
- [ ] Server starts with new config
- [ ] All MCP tools work with new config
- [ ] Performance: config load time \<100ms

______________________________________________________________________

## Architecture Council Decision Matrix

### Questions for Council Review

1. **Structure: Flat vs. Nested vs. Hybrid?**

   - ☐ Option A: Flat structure (Crackerjack pattern) - Simple, ACB-native
   - ☐ Option B: Nested structure (current pattern) - Logical grouping, backwards compatible
   - ☐ Option C: Hybrid (flat storage + nested access) - Best of both worlds
   - **Recommendation:** Option C (Hybrid)

1. **Format: TOML vs. YAML vs. Both?**

   - ☐ Option A: Keep TOML only - Backwards compatible, single file
   - ☐ Option B: Switch to YAML only - ACB-native, layered config
   - ☐ Option C: Support both (YAML preferred, TOML fallback) - Gradual migration
   - **Recommendation:** Option C (Both, YAML preferred)

1. **Migration: Big Bang vs. Incremental vs. Parallel?**

   - ☐ Option A: Big bang (1 week) - Fast, risky
   - ☐ Option B: Incremental (3-4 weeks) - Safe, gradual
   - ☐ Option C: Parallel with compat layer (2 weeks) - Balanced
   - **Recommendation:** Option C (Parallel implementation)

1. **LOC Reduction: Aggressive vs. Conservative?**

   - ☐ Option A: Aggressive (-558 lines immediate) - Remove old config now
   - ☐ Option B: Conservative (-400 lines now, -558 lines v2.0) - Keep compat layer
   - **Recommendation:** Option B (Conservative, gradual deprecation)

1. **Environment Variables: New Pattern Only vs. Dual Support?**

   - ☐ Option A: New pattern only (`DATABASE_PATH`) - Simple, breaking change
   - ☐ Option B: Dual support (old `DATABASE__PATH` + new) - Backwards compatible
   - **Recommendation:** Option B (Dual support during transition)

### Approval Request

**Proposed Approach:**

- **Structure:** Hybrid (flat storage, nested access via properties)
- **Format:** YAML preferred, TOML fallback (dual support)
- **Migration:** Parallel implementation with compat layer (2-3 weeks)
- **LOC Reduction:** Conservative (-400 lines immediate, -558 lines v2.0)
- **Env Vars:** Dual support (old pattern + new pattern)

**Timeline:**

- **Week 1:** New ACB Settings + loader + compat layer + tests
- **Week 2:** Migrate core modules + deprecation warnings + docs
- **Week 3:** Polish + performance + final testing
- **v2.0 (future):** Remove compat layer (-558 lines total)

**Success Criteria:**

- ✅ Zero breaking changes (backwards compatibility maintained)
- ✅ Test coverage ≥34.6% (no decrease)
- ✅ Config load time \<100ms (no performance regression)
- ✅ All validators preserved and working
- ✅ Layered YAML config (base + local overrides)
- ✅ ACB ecosystem alignment

**Risk Level:** LOW (conservative approach with compat layer)

**Approval Needed From:**

- [ ] Architecture Council Chair
- [ ] Tech Lead (Backend)
- [ ] QA Lead (Test coverage requirements)
- [ ] DevOps Lead (Environment variable patterns)

______________________________________________________________________

## Appendix: Code Examples

### Example 1: Old Config Usage (Current)

```python
# Current usage in server.py
from session_buddy.config import get_config

config = get_config()

# Nested access
db_path = config.database.path
checkpoint_interval = config.session.auto_checkpoint_interval
log_level = config.logging.level
```

### Example 2: New Config Usage (Recommended)

```python
# New usage with ACB Settings
from session_buddy.config import SessionMgmtSettings

settings = SessionMgmtSettings.load()

# Flat access (new pattern)
db_path = settings.database_path
checkpoint_interval = settings.session_auto_checkpoint_interval
log_level = settings.logging_level
```

### Example 3: Backwards Compatible Usage

```python
# Backwards compatible (uses compat layer)
from session_buddy.config import get_config

config = get_config()  # DeprecationWarning

# Old nested API still works!
db_path = config.database.path
checkpoint_interval = config.session.auto_checkpoint_interval
```

### Example 4: YAML Configuration

```yaml
# settings/session-mgmt.yaml (base config, committed)
database_path: "~/.claude/data/reflection.duckdb"
database_connection_timeout: 30
database_enable_multi_project: true

session_auto_checkpoint_interval: 1800
session_enable_auto_commit: true

logging_level: INFO
logging_enable_file_logging: true
```

```yaml
# settings/local.yaml (local overrides, gitignored)
debug: true
logging_level: DEBUG
database_path: "/tmp/test.duckdb"
```

### Example 5: Environment Variable Override

```bash
# New flat pattern (recommended)
export SESSION_MGMT_DATABASE_PATH="/custom/path/reflection.duckdb"
export SESSION_MGMT_LOGGING_LEVEL="DEBUG"

# Old nested pattern (backwards compatible)
export SESSION_MGMT_DATABASE__PATH="/custom/path/reflection.duckdb"
export SESSION_MGMT_LOGGING__LEVEL="DEBUG"

# Both work! Loader tries both patterns.
```

______________________________________________________________________

## References

- **Current Config:** `session_buddy/config.py` (657 lines)
- **ACB Settings:** `acb/config.py` (943 lines framework)
- **Crackerjack Reference:** `crackerjack/config/settings.py` (269 lines)
- **Crackerjack Loader:** `crackerjack/config/loader.py` (194 lines)
- **Improvement Plan:** `docs/SESSION-MGMT-MCP-COMPREHENSIVE-IMPROVEMENT-PLAN.md`

______________________________________________________________________

**Next Steps:**

1. Architecture Council review and approval
1. Finalize structure decision (flat vs. hybrid)
1. Begin Week 1 implementation (new config system)
1. Create migration guide for users
1. Update project documentation
