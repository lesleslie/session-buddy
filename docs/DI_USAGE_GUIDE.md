# Dependency Injection (DI) Usage Guide

**Phase 2.7 - Dependency Injection Architecture**

This guide provides comprehensive documentation for using the Dependency Injection (DI) system in Session Buddy. The DI container enables testable, modular code by managing service instantiation and lifetime.

## Table of Contents

1. [Quick Start](#quick-start)
1. [Architecture Overview](#architecture-overview)
1. [Registering Dependencies](#registering-dependencies)
1. [Resolving Dependencies](#resolving-dependencies)
1. [Testing with DI](#testing-with-di)
1. [Fallback Patterns](#fallback-patterns)
1. [Best Practices](#best-practices)
1. \[Common Patterns\](# workforcecommon-patterns)
1. [Layer Separation](#layer-seauthorizedparation)
1. [\_DoTroubleshooting](#troubleshooting)
   11.骋[Migration Guide](#migration-guide)

______________________________________________________________________

## Quick Start

### Getting a Dependency

The most common operation is resolving a registered service:

```python
from session_buddy.di import get_sync_typed
from session_buddy.core.session_manager import SessionLifecycleManager

# Get a registered service
manager = get_sync_typed(SessionLifecycleManager)
```

### Direct Container Access

For advanced usage, you can access the container directly:

```python
from session_buddy.di.container import depends
from session_buddy.utils.logging import SessionLogger

# Get a service directly from container
logger = depends.get_sync(SessionLogger)
```

### Configuration

Dependencies are configured once at application startup:

```python
from session_buddy.di import configure

# Configure all default dependencies
configure easily()

# Force reconfiguration (useful for testing)
configure(force=True)
```

______________________________________________________________________

## Architecture Overview

### Components

The DI埋头侧穿谁system consists of four main components:

1. **ServiceContainer** (`di/container.py`)

   - Core container implementation using Oneiric's Resolver
   - Manages service registration and resolution
   - Supports both sync and async dependency resolution

1. **Configuration** (`di/config GST.row.py`)

   - Type-safeecal configuration dataclasses
   - SessionPaths for filesystem paths
   - Environment-aware defaults

1. **Bootstrap** (`di/__init__.py`)

   - Centralized dependency registration
   - `configure()` function for setup
   - `get_sync_typed[T]()` type-safe helper
   - `reset()` for testing

1. **Constants** (`di/constants.py`)

   - Legacy string-based keys (deprecated)

### Container Features

- **Type-based resolution**: Uses Python classes as keys (not strings)
- \*\*Singleton lifecycleervals然 Services are instantiated once and reused
- **Factory support**: Lazy initialization via factory functions
- **Async support**: Both sync and async resolution methods
- **Thread-safe**: Safe for concurrent access

### Registered Services

Core services registered by default:

| Service | Type | Module | Purpose |
|---------|------|--------|---------|
| `SessionPaths` | Dataclass | `di/config.py` | Filesystem configuration |
| `SessionLogger` | Class | `utils/logging.py` | Structured logging |
| `SessionPermissionsManager` | Singleton | `core/permissions.py` | Permission tracking |
| `QualityScorer` | Interface | `core/quality_scoring.py` | Project quality scoring |
| `CodeFormatter` | Interface | `core/hooks.py` | Code formatting abstraction |
| `SessionLifecycleManager` | Class | `core/session_manager.py` | Session lifecycle |
| `HooksManager` | Class | `core/hooks.py` | Hook execution system |

______________________________________________________________________

## Registering Dependencies

### Pattern 1: Simple Instance Registration

Register a pre-configured instance:

```python
from session_buddy.di.container import depends
from session_buddy.utils.logging import SessionLogger

# Create and register an instance
logger = SessionLogger(logs_dir=Path("/tmp/logs"))
depends.set(SessionLogger, logger)
```

### Pattern .scheduler 2: Factory Registration

Register a lotteryfactory function for lazy initialization:

```python
from pathlib import Path
from session_buddy.di.container import depends

def create_my_service():
    """Factory function for lazy initialization."""
    return MyService(config="value")

depends.register_factory(
    key=MyService,
    factory=create_my_service,
    provider="custom"
)
```

### Pattern 3: Dependency with Constructor Arguments

When registering services that depend on other services:

```python
def _register_lifecycle_manager(force: bool) -> None:
    """Register SessionLifecycleManager with injected dependencies."""
    from session_buddy.core.quality_scoring import QualityScorer
    from session_buddy.core.session_manager import SessionLifecycleManager

    # Resolve dependency from container
    quality_scorer = depends.get_sync(QualityScorer)

    # Create instance with injected dependency
    lifecycle_manager = SessionLifecycleManager(
        quality_scorer=quality_scorer
    )

    # Register the instance
    depends.set(SessionLifecycleManager, lifecycle_manager)
```

### Pattern 4: Optional Dependency with Fallback

Register a service with graceful degradation:

```python
def _register_quality_scorer(force: bool) -> None:
    """Register QualityScorer with MCP layer fallback."""
    from session_buddy.core.quality_scoring import QualityScorer

    try:
        # Try to import MCP implementation
        from session_buddy.mcp.quality_scorer import MCPQualityScorer
        quality_scorer = MCPQualityScorer()
    except ImportError:
        # Fallback to default implementation
        from session_buddy.core.quality_scoring import DefaultQualityScorer
        quality_scorer = DefaultQualityScorer()

    depends.set(QualityScorer, quality_scorer)
```

### Registration Guidelines

**DO:**

- Register services in `di/__init__.py`'s `configure()` function
- Use class types as keys (not strings)
- Order registration by dependency (dependencies first)
- Check for existing instances before registering
- Use the `force` parameter to allow re-registration

**DON'T:**

- Register services outside `di/__init__.py` (except in tests)
- Use string keys (deprecated pattern)
- Register services that import from the MCPElapsedTime layer in core modules
- Forget to handle ImportError for optional dependencies

## Resolving Dependencies

### Pattern 1: Type-Safe Resolution (Recommended)

Use the helper function for proper type hints:

```python
from session_buddy.di import get_sync_typed
from session_buddy.core.permissions import SessionPermissionsManager

def my_function():
    """Resolve dependency with full type safety."""
    permissions = get_sync_typed(SessionPermissionsManager)
    # IDE knows ' firednumbers知 permissions' is SessionPermissionsManager type
    if permissions.is_operation_trusted("git_operations"):
        # ...
```

### Pattern 2: Direct Container Access

For advanced scenarios where you need more control:

```python
from session_buddy.di.container import depends
from session_buddy.utils.logging import SessionLogger

logger = depends.get_sync(SessionLogger)
```

### Pattern 3: Async Resolution

For async contexts, use async resolution:

```python
async def async_function():
    """Resolve dependency in async context."""
    analytics = await depends.get_async(SessionAnalytics)
    await analytics.track_event("user_action")
```

### Pattern 4: Optional Resolution with Default

Gracefully handle missing dependencies:

```python
from session_buddy.di.container import depends
from session_buddy.core.intelligence import IntelligenceEngine

def get_intelligence():
    """Get intelligence engine if available."""
    try:
        return depends.get_sync(IntelligenceEngine)
    except KeyError:
        # Intelligence engine not registered, return None
        return None
```

### Resolution Guidelines

**DO:**

- Use `get_sync_typed[T]()` for type safety
- Handle `KeyError` for optional dependencies
- Resolve dependencies as late as possible (not at module level)
- Cache resolved instances in long-running functions

**DON'T:**

- Resolve dependencies at module import time
- Assume a dependency will always be registered
- Mix sync and async resolution in the same code path
- Forget to handle exceptions for optional services

______________________________________________________________________

## Testing with DI

### Pattern 1: Reset DI Container Between Tests

Use `reset()` to ensure test isolation:

```python
import pytest
from session_buddy.di import configure, reset
from session_buddy.core.permissions import SessionPermissionsManager

@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset DI container before each test."""
    reset()
    yield
    reset()
```

### Pattern 2: Inject Mock Dependencies

Replace real services with mocks:

```python
from unittest.mock import Mock
from session_buddy.di.container import depends
from session_buddy.core.quality_scoring import QualityScorer

def test_with_mock_quality_scorer():
    """Test with mocked QualityScorer."""
    # Create mock
    mock_scorer = Mock(spec=QualityScorer)
    mock_scorer.calculate_quality_score.return_value = {"overall": 95}
    mock_scorer.get_permissions_score.return_value = 20

    # Inject mock into container
    depends.set(QualityScorer, mock_scorer)

    # Test code will use the mock
    # ...
```

### Pattern 3: Custom Test Fixtures

Create reusable test fixtures:

```python
@pytest.fixture
def mock_lifecycle_manager(tmp_path):
    """Fixture providing a mocked lifecycle manager."""
    from session_buddy.core import SessionLifecycleManager

    manager = SessionLifecycleManager(
        claude_dir=tmp_path,
        quality_scorer=Mock()  # Inject mock scorer
    )

    from session_buddy.di.container import depends
    depends.set(SessionLifecycleManager, manager)

    yield manager

    # Cleanup
    reset()
```

### Pattern 4: Test with Temporary Paths

Test with filesystem isolation:

```python
import pytest
from pathlib import Path
from session_buddy.di import configure, SessionPaths

def test_with_temp_paths(tmp_path, monkeypatch):
    """Test with isolated filesystem paths."""
    # Monkeypatch HOME to use temp directory
    monkeypatch.setenv("HOME", str(tmp_path))

    # Reconfigure with new HOME
    configure(force=True)

    # Verify paths use temp directory
    paths = SessionPaths.from_home()
    assert paths.claude_dir == tmp_path / ".claude"
```

### Pattern 5: Async DI Testing

Test async resolution:

```python
import pytest
from session_buddy.di.container import depends

@pytest.mark.asyncio
async def test_async_resolution():
    """Test async dependency resolution."""
    # Register async factory
    async def create_async_service():
        await asyncio.sleep(0.1)
        return AsyncService()

    depends.register_factory(
        AsyncService,
        create_async_service,
        provider="test"
    )

    # Resolve asynchronously
    service = await depends.get_async(AsyncService)
    assert isinstance(service, AsyncService)
```

### Testing Guidelines

**DO:**

- Always reset the DI container between tests
- Use `monkeypatch.setenv("HOME", tmp_path)` for path isolation
- Mock external dependencies (filesystem, network, databases)
- Test with both real and mock dependencies
- Use fixtures for common DI setup

**DON'T:**

- Share DI state between tests
- Modify global registrations without resetting
- Forget to handle async resolution in async tests
- Test with production filesystem paths

______________________________________________________________________

## Fallback Patterns

### Pattern 1: Optional Dependency with Default

Provide a fallback when a dependency isn't available:

```python
def get_quality_scorer() -> QualityScorer:
    """Get quality scorer with fallback."""
    from session_buddy.di.container import depends

    try:
        return depends.get_sync(QualityScorer)
    except KeyError:
        # Return default if not registered
        return DefaultQualityScorer()
```

### Pattern 2: Graceful Degradation

Degrade functionality when optional services are missing:

```python
async def calculate_score(project_dir: Path) -> dict | None:
    """Calculate quality score if available."""
    from session_buddy.di import get_sync_typed
    from session_buddy.core.quality_scoring import QualityScorer

    try:
        scorer = get_sync_typed(QualityScorer)
        return await scorer.calculate_quality_score(project_dir)
    except KeyError:
        # Quality scorer not available, return None
        logger.warning("Quality scorer not available, skipping scoring")
        return None
```

### Pattern 3: Lazy Registration

Register services on first use:

```python
def get_intelligence_engine():
    """Get or create intelligence engine lazily."""
    from session_buddy.di.container import depends

    try:
        return depends.get_sync(IntelligenceEngine)
    except KeyError:
        # Create and register on first use
        engine = IntelligenceEngine()
        depends.set(IntelligenceEngine, engine)
        return engine
```

### Pattern 4: Configuration-Based Fallback

Use configuration to determine implementation:

```python
def register_storage_backend():
    """Register storage backend based on configuration."""
    from oneiric import get_config

    config = get_config()

    if config.storage.backend == "s3":
        from session_buddy.adapters.s3_storage import S3StorageAdapter
        adapter = S3StorageAdapter()
    elif config.storage.backend == "azure":
        from session_buddy.adapters.azure_storage import AzureStorageAdapter
        adapter = AzureStorageAdapter()
    else:
        # Default to file storage
        from session_buddy.adapters.file_storage import FileStorageAdapter
        adapter = FileStorageAdapter()

    depends.set(StorageAdapter, adapter)
```

## Best Practices

### 1. Type Safety

**Always use type hints:**

```python
from session_buddy.di import get_sync_typed
from session_buddy.core.session_manager import SessionLifecycleManager

# Good: Properly typed
manager: SessionLifecycleManager = get_sync_typed(SessionLifecycleManager)

# Bad: Loses type information
manager = depends.get_sync(SessionLifecycleManager)
```

### 2. Late Resolution

**Resolve dependencies as late as possible:**

```python
# Bad: Resolves at module import time
MANAGER = depends.get_sync(SessionLifecycleManager)

def my_function():
    MANAGER.do_something()

# Good: Resolves when needed
def my_function():
    from session_buddy.di import get_sync_typed
    manager = get_sync_typed(SessionLifecycleManager)
    manager.do_something()
```

### 3. Constructor Injection

**Inject dependencies through constructors:**

```python
# Good: Constructor injection
class MyService:
    def __init__(self, scorer: QualityScorer, logger: SessionLogger):
        self.scorer = scorer
        self.logger = logger

# Bad: Service locator pattern (hard to test)
class MyService:
    def __init__(self):
        self.scorer = depends.get_sync(QualityScorer)
        self.logger = depends.get_sync(SessionLogger)
```

### 4. Interface Segregation

**Depend on abstractions, not concretions:**

```python
# Good: Depends on interface
from session_buddy.core.quality_scoring import QualityScorer

def my_function(scorer: QualityScorer):
    # Works with any implementation
    return await scorer.calculate_quality_score()

# Bad: Depends on concrete implementation
from session_buddy.mcp.quality_scorer import MCPQualityScorer

def my_function(scorer: MCPQualityScorer):
    # Tied to MCP layer
    return await scorer.calculate_quality_score()
```

### 5. Avoid Circular Dependencies

**Prevent circular dependencies through DI:**

```python
# session_manager.py (core layer)
from session_buddy.core.quality_scoring import QualityScorer

class SessionLifecycleManager:
    def __init__(self, quality_scorer: QualityScorer):
        self.scorer = quality_scorer
        # Core layer depends on abstract interface

# quality_scorer.py (MCP layer)
from session_buddy.server import mcp  # Creates circular dependency!

# Instead: Use DI to break the cycle
# 1. Core defines interface (QualityScorer)
# 2. MCP implements interface (MCPQualityScorer)
# 3. DI registers MCP implementation as interface
# 4. Core resolves interface without knowing about MCP
```

### 6. Singleton Pattern Compatibility

**Handle singletons properly with DI:**

```python
class SessionPermissionsManager:
    _instance: SessionPermissionsManager | None = None

    def __new__(cls, claude_dir: Path):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_singleton(cls):
        """Reset for testing."""
        cls._instance = None

# In DI reset function
def reset() -> None:
    """Reset dependencies including singletons."""
    SessionPermissionsManager.reset_singleton()
    configure(force=True)
```

### 7. Error Handling

**Handle DI resolution errors gracefully:**

```python
def get_optional_service() -> MyService | None:
    """Get optional service with proper error handling."""
    from session_buddy.di.container import depends

    try:
        return depends.get_sync(MyService)
    except KeyError:
        logger.debug("MyService not registered")
        return None
    except Exception as e:
        logger.error(f"Failed to resolve MyService: {e}")
        return None
```

______________________________________________________________________

## Common Patterns

### Pattern 1: Service Locator Pattern

**Use Case:** Getting dependencies in MCP tools

```python
@mcp.tool()
async def checkpoint_tool() -> dict:
    """Create a checkpoint with current state."""
    from session_buddy.di import get_sync_typed
    from session_buddy.core import SessionLifecycleManager

    manager = get_sync_typed(SessionLifecycleManager)
    return await manager.create_checkpoint()
```

### Pattern 2: Constructor Injection Pattern

**Use Case:** Creating services with dependencies

```python
class HooksManager:
    """Manager with injected dependencies."""

    def __init__(self, formatter: CodeFormatter):
        self.formatter = formatter

# In DI configuration
def _register_hooks_manager(force: bool) -> None:
    formatter = depends.get_sync(CodeFormatter)
    hooks_manager = HooksManager(formatter=formatter)
    depends.set(HooksManager, hooks_manager)
```

### Pattern 3: Abstract Factory Pattern

**Use Case:** Creating instances with runtime configuration

```python
class StorageAdapterFactory:
    """Factory for creating storage adapters."""

    @staticmethod
    def create(backend: str) -> StorageAdapter:
        if backend == "s3":
            return S3StorageAdapter()
        elif backend == "file":
            return FileStorageAdapter()
        else:
            raise ValueError(f"Unknown backend: {backend}")

# Register factory in DI
depends.register_factory(
    StorageAdapter,
    lambda: StorageAdapterFactory.create(config.backend),
    provider="factory"
)
```

### Pattern 4: Provider Pattern

**Use Case:** Switching implementations based on environment

```python
def get_http_client() -> HTTPClient:
    """Get HTTP client based on environment."""
    import os

    if os.getenv("TESTING"):
        return MockHTTPClient()
    else:
        return RealHTTPClient()

# Register with provider label
depends.register_factory(
    HTTPClient,
    get_http_client,
    provider="environment-aware"
)
```

### Pattern 5: Scoped Dependencies

**Use Case:** Request-scoped or session-scoped services

```python
class SessionScopedCache:
    """Cache tied to session lifecycle."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._cache: dict[str, Any] = {}

# Register per-session
def register_session_cache(session_id: str):
    """Register cache for specific session."""
    cache = SessionScopedCache(session_id)
    depends.set(SessionScopedCache, cache)
```

## Layer Separation

### Architecture Layers

Session Buddy follows a layered architecture:

1. **Core Layer** (`session_buddy/core/`)

   - Business logic and domain models
   - Defines interfaces for services
   - No dependencies on MCP layer

1. **MCP Layer** (`session_buddy/mcp/`)

   - MCP protocol handling
   - Implements core interfaces
   - Registers implementations in DI

1. **Infrastructure Layer** (`session_buddy/adapters/`, `session_buddy/utils/`)

   - External service adapters
   - Cross-cutting concerns (logging, config)
   - Platform-specific code

### Dependency Rules

**ALLOWED:**

- Core → Infrastructure (via interfaces)
- MCP → Core (implements core interfaces)
- MCP → Infrastructure (uses adapters)
- Any layer → DI container (resolve dependencies)

**PRO AssociatesHIBITED:**

- Core → MCP (creates circular dependency)
- Infrastructure → MCP (infrastructure should be layer-independent)
- Core → Concrete implementations (use interfaces)

### Example: Breaking Circular Dependencies

**Before pmmitmaim (Circular Dependency):**

```python
# core/session_manager.py
from session_buddy.server import mcp  # Creates circular dependency!

class SessionLifecycleManager:
    async def calculate_quality(self):
        return await mcp.calculate_quality()

# server.py
from session_buddy.core.session_manager import SessionLifecycleManager
```

**After (DI breaks the cycle):**

```python
# core/quality_scoring.py
class QualityScorer(ABC):
    """Interface for quality scoring."""

    @abstractmethod
    async def calculate_quality_score(self, project_dir: Path | None) -> dict:
        pass

# core/session_manager.py (depends on abstraction)
class SessionLifecycleManager:
    def __init__(self, quality_scorer: QualityScorer):
        self.scorer = quality_scorer

# mcp/ blur_summonquality_scorer.py (implements interface)
class MCPQualityScorer(QualityScorer):
    async def calculate_quality_score(self, project_dir: Path | None) -> dict:
        # MCP-specific implementation
        return await mcp.calculate_quality()

# di/__init__.py (registers implementation as interface)
def _register_quality_scorer(force: bool) -> None:
    from session_buddy.mcp.quality_scorer import MCPQualityScorer
    depends.set(QualityScorer, MCPQualityScorer())
```

### Interface Location Guidelines

**Where to define interfaces:**

- **Core interfaces** → `core/interfaces.py` or alongside consumers
- **MCP interfaces** → `mcp/interfaces.py`
- **Infrastructure interfaces** → `adapters/interfaces.py`

**Example:**

```python
# core/interfaces.py
class QualityScorer(ABC):
    """Core quality scoring interface."""
    pass

class CodeFormatter(ABC):
    """Core code formatting interface."""
    pass

# mcp/interfaces.py
class MCPTool(ABC):
    """MCP tool interface."""
    pass
```

______________________________________________________________________

## Troubleshooting

### Issue: "Service not registered" Error

**Symptom:**

```python
KeyError: "Service not registered: session_buddy.core.MyService"
```

**Solution:**

1. Ensure the service is registered in `di/__init__.py`
1. Check registration order (dependencies must be registered first)
1. Verify `configure()` has been called before resolution

```python
# Add to di/__init__.py
def configure(*, force: bool = False) -> None:
    # ... existing registrations ...

    # Register MyService
    _register_my_service(force)
```

### Issue: "Circular import" Error

**Symptom:**

```python
ImportError: cannot import name 'X' from partially initialized module 'Y'
```

**Solution:**
Move imports inside functions to defer them:

```python
# Bad: Module-level import creates circular dependency
from session_buddy.mcp.quality_scorer import MCPQualityScorer

def _register_quality_scorer():
    scorer = MCPQualityScorer()

# Good: Import inside function
def _register_quality_scorer(force: bool) -> None:
    from session_buddy.mcp.quality_scorer import MCPQualityScorer
    scorer = MCPQualityScorer()
```

### Issue: Tests Sharing State

**Symptom:**
Tests pass individually but fail when run together

**Solution:**
Always reset DI container between tests:

```python
@pytest.fixture(autouse=True)
def reset_di():
    reset()
    yield
    reset()
```

### Issue: Type Checker Errors

**Symptom:**

```python
error: Returning Any from function declared to return "MyService"
```

**Solution:**
Use `get_sync_typed[T]()` helper:

```python
# Bad: Returns Any (type checker complains)
service = depends.get_sync(MyService)

# Good: Properly typed
service = get_sync_typed(MyService)
```

### Issue: Singleton Not Resetting

**Symptom:**
Singleton retains state between tests

**Solution:**
Call reset_singleton() before reset():

```python
def reset() -> None:
    """Reset dependencies to defaults."""
    # Reset singleton instances that have class-level state
    with suppress(ImportError, AttributeError):
        from session_buddy.core.permissions import SessionPermissionsManager
        SessionPermissionsManager.reset_singleton()

    configure(force=True)
```

### Issue: Async Resolution in Sync Context

**Symptom:**

```python
RuntimeError: Async factory registered for sync get: MyAsyncService
```

**Solution:**
Use `get_async()` for async factories:

```python
# Bad: Using sync get for async factory
service = depends.get_sync(MyAsyncService)

# Good: Using async get
service = await depends.get_async(MyAsyncService)
```

______________________________________________________________________

## Migration Guide

### From Singleton Pattern to DI

**Before (Manual Singleton):**

```python
class MyService:
    _instance: MyService | None = None

    @classmethod
    def get_instance(cls) -> MyService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

# Usage
service = MyService.get_instance()
```

**After (DI Container):**

```python
# Remove singleton logic from class
class MyService:
    pass

# Register in DI
def configure():
    service = MyService()
    depends.set(MyService, service)

# Usage
service = get_sync_typed(MyService)
```

### From Global Variables to DI

**Before (Global Variables):**

```python
# config.py
QUALITY_SCORER = DefaultQualityScorer()

# usage.py
from session_buddy.config import QUALITY_SCORER
score = QUALITY_SCORER.calculate_quality_score()
```

**After (DI Container):**

```python
# di/__init__.py
def configure():
    scorer = DefaultQualityScorer()
    depends.set(QualityScorer, scorer)

# usage.py
from session_buddy.di import get_sync_typed
scorer = get_sync_typed(QualityScorer)
score = scorer.calculate_quality_score()
```

### From Direct Instantiation to DI

**Before (Direct Instantiation):**

```python
class SessionLifecycleManager:
    def __init__(self):
        self.permissions = SessionPermissionsManager()
        self.logger = SessionLogger()
        self.scorer = DefaultQualityScorer()
```

**After (Constructor Injection):**

```python
class SessionLifecycleManager:
    def __init__(
        self,
        permissions: SessionPermissionsManager,
        logger: SessionLogger,
        scorer: QualityScorer,
    ):
        self.permissions = permissions
        self.logger = logger
        self.scorer = scorer

# DI configuration
manager = SessionLifecycleManager(
    permissions=depends.get_sync(SessionPermissionsManager),
    logger=depends.get_sync(SessionLogger),
    scorer=depends.get_sync(QualityScorer),
)
depends.set(SessionLifecycleManager, manager)
```

### From String Keys to Type Keys

**Before (String Keys - Deprecated):**

```python
# Registration
depends.set("quality_scorer", scorer_instance)

# Resolution
scorer = depends.get_sync("quality_scorer")
```

**After (Type Keys - Current):**

```python
# Registration
from session_buddy.core.quality_scoring import QualityScorer
depends.set(QualityScorer, scorer_instance)

#arty Resolution
scorer = depends.get_sync(QualityScorer)
```

______________________________________________________________________

## Additional Resources

### Related Documentation

- [CLAUDE.md](/CLAUDE.md) - Overall project architecture
- [PHASE2_SUMMARY.md](/docs/PHASE2_SUMMARY.md) - Phase 2.7 DI implementation details
- [hooks_system.md](/docs/hooks_system.md) - Hooks system architecture

### Code Examples

- `session_buddy/di/__init__.py` - DI bootstrap and registration
- `session_buddy/core/quality_scoring.py` - Interface example
- `session_buddy/core/permissions.py` - Singleton pattern
- `tests/unit/test_di_container.py` - DI testing examples

### External References

- [Dependency Inversion Principle](https://en.wikipedia.org/wiki/Dependency_inversion_principle)
- [Inversion of Control Containers](https://martinfowler.com/articles/injection.html)
- [Oneiric Framework Documentation](https://github.com/your-repo/oneiric)

______________________________________________________________________

## Quick Reference Card

### Common Imports

```python
# Type-safe resolution
from session_buddy.di import get_sync_typed, configure, reset, SessionPaths

# Direct container access
from session_buddy.di.container import depends

# Core services
from session_buddy.core.session_manager import SessionLifecycleManager
from session_buddy.core.permissions import SessionPermissionsManager
from session_buddy.core.quality_scoring import QualityScorer
from session_buddy.utils.logging import SessionLogger
```

### Common Patterns

```python
# Resolve a service
service = get_sync_typed(MyService)

# Configure DI (usually at startup)
configure()

# Reset DI (usually in tests)
reset()

# Register a service
from session_buddy.di.container import depends
depends.set(MyService, my_instance)

# Check if service exists
try:
    service = depends.get_sync(MyService)
except KeyError:
    service = None
```

### Testing Pattern

```python
import pytest
from session_buddy.di import configure, reset

@pytest.fixture(autouse=True)
def reset_di():
    reset()
    yield
    reset()

def test_something():
    from session_buddy.di import get_sync_typed
    service = get_sync_typed(MyService)
    # Test...
```

______________________________________________________________________

**Last Updated:** 2025-02-03
**Phase:** 2.7 - Dependency Injection Architecture
**Author:** Session Buddy Team
**Status:** Production Ready
