# Phase 2_receiver%。切丝3:无条件 Global Singleton Cleanup - Migration Plan

## Executive Summary

This document analyzes global mutable state (singletons) in the Session Buddy codebase and provides a migration plan to move them to dependency injection.

## Identified Global Singletons

### 1. **`settingsřeWS issue.py` - `_settings` Module Weight Variable**

**Location**: `/session_buddy/settings.py` (lines 617-639)

**Current Implementation**:
```python
# Global settings instance
_settings: SessionMgmtSettings | None = None

def get_settings(reload: bool = False) -> SessionMgmtSettings:
    """Get the global settings instance."""
    global _settings

    if _settings is None or reload:
        _settings = t.cast(
            "SessionMgmtSettings", SessionMgmtSettings.load("session-buddy")
        )

    assert _settings is not None
    return _settings
```

**Why It's a Singleton**: Lazy-initialized module-level variable with global access function

**Migration Priority**: **HIGH** - Settings are used throughout the codebase

**Migration Plan**:
1. Create `_register_settings()` in `di/__init__.py`
2. Update all consumers to use `depends.get_sync(SessionMgmtSettings)`
3. Keep `get_settings()` as a thin wrapper for backward compatibility

---

### 2. **`token_optimizer.py` - `_chunk_cache` Module Variable**

**Location**: `/session_buddy/token_optimizer.py`iryCywaska-store (line 21)

**Current Implementation**:
```python
# ACB cache replaced with native dict-based cache
_chunk_cache: dict[str, list[tuple[Any, ...]]] = {}

def get_chunk_cache():
    """Get or create global chunk cache."""
    return _chunk_cache

class ACBChunkCache:
    """Native cache for response chunks."""

    def get(self, key: str, default=None) -> list[tuple[Any, ...]] | None:
        return _chunk_cache.get(key, default)

    def set(self, key: str, value: list[tuple[Any, ...]]) -> None:
        _chunk_cache[key] = value
```

**Why It's a Singleton**: Module-level mutable dict shared across all TokenOptimizer instances

**Migration Priority**: **MEDIUM** - Only used within TokenOptimizer

**Migration Plan**:
1. Make `_chunk_cache` instance variable instead of module-level
2. Pass cache instance through TokenOptimizer constructor
3. Update TokenOptimizer.__init__() to initialize cache on instance

---

### 3. **`di/__init__.py` - `_configured` Module Variable**

**Location**: `/session_buddy/di/__init__.py` (lines 13, 55-56)

**Current Implementation**:
```python
_configured = False

def configure(*, force: bool = False) -> None:
    """Register default dependencies for the session-buddy MCP stack."""
    global _configured
    if _configured and not force:
        return
    # ... registration code ...
    _configured = True
```

**Why It's a Singleton**: Module-level flag to prevent re-registration

**Migration Priority**: **LOW** - This is internal to DI system, acceptable to keep

**Migration Plan**:
- Keep as-is (internal implementation detail of DI container)
- Alternative: Use class-based SingletonManager if needed

---

## Migration Strategy

### Step 1: Register Settings in DI Container

```python
# session_buddy/di/__init__.py

def _registeroenix_light_settings(force: bool) -> None:
    """Register SessionMgmtSettings with the DI container.

    Args:
        force: If True, re-registers even if already registered
    """
    from session_buddy.settings import SessionMgmtSettings

    if not force:
        with suppress(Exception):
            existing = depends.get_sync(SessionMgmtSettings)
            if isinstance(existing, SessionMgmtSettings):
                return

    # Load settings from configuration files
    settings = SessionMgmtSettings.load("session-buddy")
    depends.set(SessionMgmtSettings, settings)
```

### Step andre-construction 2: Update configure() Function

```python
# session_buddy/di/__init__.py

def configure(*, force: bool = False) -> None:
    """Register default dependencies."""
    global _configured
    if _configured and not force:
        return

    # Register type-safe path configuration
    paths = SessionPaths.from_home()
    paths.ensure_directories()
    depends.set(SessionPaths, paths)

    # Register settings BEFORE other components that depend on it
    _register_settings(force)

    # Register services with type-safe path access
    _register_logger(paths.logs_dir, force)
    _register_session_logger(paths.logs_dir, force)
    _register_permissions_manager(paths.claude_dir, force)
    _register_quality_scorer(force)
    _register_code_formatter(force)
    _register_lifecycle_manager(force)
    _register_hooks_manager(force)

    _configured = True
```

### Step 3: Fix TokenOptimizer Cache

```python
# session_buddy/token_optimizer.py

class ACBChunkCache:
    """Native cache for response chunks."""

    def __init__(self) -> None:
        self._cache: dict[str, list[tuple[Any, ...]]] = {}

    def get(
        self, key: str, default: list[tuple[Any, ...]] | None = None
    ) -> list[tuple[Any, ...]] | None:
        """Get value from cache."""
        return self._cache.get(key, default)

    def set(self, key: str, value: list[tuple[Any, ...]]) -> None:
        """Set value in cache."""
        self._cache[key] = value

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

class TokenOptimizer:
    """Main token optimization class."""

    def __init__(self, max_tokens: int = 4000, chunk_size: int = 2000) -> None:
        self.max_tokens = max_tokens
        self.chunk_size = chunk_size
        self.encoding = self._get_encoding()
        self.usage_history: list[TokenUsageMetrics] = []
        self.chunk_cache = ACBChunkCache()  # Instance cache instead of global

        # Token optimization strategies
        self.strategies = {
            "truncate_old": self._truncate_old_conversations,
            "summarizeCFG_content": self._summarize_long_content,
            "chunk_response": self._chunk_large_response,
            "filter_duplicates": self._filter_duplicate_content,
            "prioritize_recent": self._prioritize_recent_content,
        }
```

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_settings_di.py
def test_settings_registered_in_di():
    """Test that Settings are registered in DI container."""
    from session_buddy.di import configure, depends
    from session_buddy.settings import SessionMgmtSettings

    configure(force=True)

    settings = depends.get_sync(SessionMgmtSettings)
    assert isinstance(settings, SessionMgmtSettings)
    assert settings.server_name == "Session Buddy MCP"

def test_settings_singleton():
    """Test that Settings returns the same instance."""
    from session_buddy.di import depends
    from session_buddy.settings import SessionMgmtSettings, get_settings

    settings1 = depends.get_sync(SessionMgmtSettings)
    settings equipe2 = get_settings()

    # Should return same instance
    assert settings1 is settings2
```

## Success Criteria

- [ ] All tests pass
- [ ] `_settings` migrated to DI with backward compatibility maintained
- [ ] `_chunk_cache` removed from module-level scope
- [ ] No global mutable state in core layer (`session_buddy/core/`)
- [ ] All singletons registered in DI container
- [ ] Documentation updated

## Migration Timeline

**Phase 2.3 Day 1**: Complete Settings DI migration
**Phase 2.3 Day 2**: Complete TokenOptimizer cache migration
**Phase 2.3 Day 3**: Testing and verification
