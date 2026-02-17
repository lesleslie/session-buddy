# Week 5 ACB Refactoring Guide

**Purpose:** Step-by-step guide to refactor Week 5 tested modules to use ACB patterns
**Target Audience:** Developers implementing architectural improvements
**Estimated Time:** 1-2 days for all 4 modules

______________________________________________________________________

## Table of Contents

1. [Overview](#overview)
1. [Module 1: multi_project_coordinator.py](#module-1-multi_project_coordinatorpy)
1. [Module 2: app_monitor.py](#module-2-app_monitorpy)
1. [Module 3: memory_optimizer.py](#module-3-memory_optimizerpy)
1. [Module 4: serverless_mode.py](#module-4-serverless_modepy)
1. [Test Updates](#test-updates)
1. [Verification Steps](#verification-steps)

______________________________________________________________________

## Overview

### What We're Changing

**From:** Manual instantiation with constructor injection

```python
class MyComponent:
    def __init__(self, db: Database):
        self.db = db


component = MyComponent(database_instance)
```

**To:** ACB dependency injection with adapter pattern

```python
from acb.depends import depends
from acb.config import AdapterBase, Settings


class MyComponentSettings(Settings):
    config_value: str = "default"


class MyComponent(AdapterBase):
    settings: MyComponentSettings | None = None

    async def init(self) -> None:
        self.db = depends.get_sync(Database)


# Auto-injected via DI
component = depends.get_sync(MyComponent)
```

### Benefits of ACB Pattern

1. **Testability:** Easy to swap implementations via `depends.set()`
1. **Configuration:** Type-safe settings with Pydantic validation
1. **Lifecycle:** Automatic initialization and cleanup via `init()`
1. **Consistency:** Same pattern across entire codebase

______________________________________________________________________

## Module 1: multi_project_coordinator.py

### Current Code (BEFORE)

```text
#!/usr/bin/env python3
"""Multi-Project Session Coordination."""

from pydantic import BaseModel
from .reflection_tools import ReflectionDatabase


class ProjectGroup(BaseModel):
    """Pydantic model - keep as is"""

    id: str
    name: str
    projects: list[str]
    # ... rest of model


class MultiProjectCoordinator:
    """Manages relationships between projects."""

    def __init__(self, db: ReflectionDatabase):
        """❌ Constructor injection - remove this"""
        self.db = db
        self.active_project_groups: dict[str, ProjectGroup] = {}
        self.cache: dict[str, Any] = {}

    async def create_project_group(
        self,
        name: str,
        projects: list[str],
        description: str = "",
    ) -> ProjectGroup:
        """Create new project group."""
        # Implementation uses self.db
        pass
```

### Refactored Code (AFTER)

```python
#!/usr/bin/env python3
"""Multi-Project Session Coordination."""

from acb.depends import depends
from acb.config import AdapterBase, Settings
from pydantic import BaseModel, Field


# Step 1: Add Settings class
class CoordinatorSettings(Settings):
    """Configuration for multi-project coordination."""

    cache_ttl: int = Field(
        default=3600, description="Cache TTL in seconds", ge=60, le=86400
    )
    max_projects: int = Field(
        default=100, description="Maximum projects per group", ge=1, le=1000
    )
    enable_clustering: bool = Field(
        default=True, description="Enable automatic project clustering"
    )
    search_timeout: int = Field(
        default=30, description="Search timeout in seconds", ge=5, le=300
    )


# Keep Pydantic models unchanged
class ProjectGroup(BaseModel):
    """Pydantic model - unchanged"""

    id: str
    name: str
    projects: list[str]
    # ... rest of model


# Step 2: Convert to AdapterBase
class MultiProjectCoordinator(AdapterBase):
    """Manages relationships between projects."""

    # ACB pattern: Settings declaration
    settings: CoordinatorSettings | None = None

    # Step 3: Move initialization to init()
    async def init(self) -> None:
        """Initialize coordinator with DI."""
        # Get dependencies via DI
        self.db = depends.get_sync("ReflectionDatabase")

        # Use settings for configuration
        if not self.settings:
            self.settings = CoordinatorSettings()

        # Initialize state
        self.active_project_groups: dict[str, ProjectGroup] = {}
        self.cache: dict[str, Any] = {}
        self._cache_ttl = self.settings.cache_ttl

        # Setup database tables
        await self._ensure_tables()

    # Step 4: Add DI-based method injection (optional)
    @depends.inject
    async def create_project_group(
        self,
        name: str,
        projects: list[str],
        description: str = "",
        cache: "Cache" = depends(),  # Auto-injected ACB cache
    ) -> ProjectGroup:
        """Create new project group with DI."""
        # Validate against settings
        if len(projects) > self.settings.max_projects:
            raise ValueError(f"Too many projects (max: {self.settings.max_projects})")

        # Implementation (mostly unchanged)
        group_id = str(uuid.uuid4())
        group = ProjectGroup(
            id=group_id,
            name=name,
            projects=projects,
            description=description,
            created_at=datetime.now(UTC),
        )

        # Use injected cache adapter
        await cache.set(f"group:{group_id}", group.model_dump(), ttl=self._cache_ttl)

        # Store in database
        await self.db.store_project_group(group)

        return group

    # Rest of methods follow same pattern...
```

### Step-by-Step Migration

1. **Add imports**

   ```python
   from acb.depends import depends
   from acb.config import AdapterBase, Settings
   ```

1. **Create Settings class**

   - Extract all configuration values
   - Add Pydantic Field validators
   - Document each setting

1. **Convert to AdapterBase**

   ```python
   class MultiProjectCoordinator(AdapterBase):
       settings: CoordinatorSettings | None = None
   ```

1. **Replace `__init__` with `async def init()`**

   - Move all initialization logic
   - Use `depends.get_sync()` for dependencies
   - Initialize settings if not provided

1. **Update method signatures (optional)**

   - Add `@depends.inject` decorator
   - Use `parameter: Type = depends()` for auto-injection
   - Maintains backward compatibility

### Testing the Refactored Code

```python
# tests/unit/test_multi_project_coordinator.py

import pytest
from acb.depends import depends
from session_buddy.multi_project_coordinator import (
    MultiProjectCoordinator,
    CoordinatorSettings,
)


@pytest.fixture
def mock_reflection_db():
    """Mock ReflectionDatabase for testing."""

    class MockDB:
        async def store_project_group(self, group):
            return True

        async def get_project_groups(self):
            return []

    return MockDB()


@pytest.fixture
def coordinator_settings():
    """Custom settings for testing."""
    return CoordinatorSettings(
        cache_ttl=60,  # Short TTL for tests
        max_projects=10,  # Lower limit for tests
        enable_clustering=True,
    )


@pytest.fixture
async def coordinator(mock_reflection_db, coordinator_settings):
    """Create coordinator with DI."""
    # Register dependencies
    depends.set("ReflectionDatabase", mock_reflection_db)

    # Create coordinator (will use DI in init())
    coord = MultiProjectCoordinator()
    coord.settings = coordinator_settings
    await coord.init()

    yield coord

    # Cleanup
    depends.clear()


@pytest.mark.asyncio
async def test_create_project_group(coordinator):
    """Test project group creation with DI."""
    group = await coordinator.create_project_group(
        name="Test Group", projects=["proj-a", "proj-b"], description="Test description"
    )

    assert group.name == "Test Group"
    assert len(group.projects) == 2
    assert "proj-a" in group.projects


@pytest.mark.asyncio
async def test_max_projects_validation(coordinator):
    """Test settings validation."""
    with pytest.raises(ValueError, match="Too many projects"):
        await coordinator.create_project_group(
            name="Too Large",
            projects=[f"proj-{i}" for i in range(20)],  # Exceeds limit of 10
        )
```

______________________________________________________________________

## Module 2: app_monitor.py

### Current Code (BEFORE)

```python
class ProjectActivityMonitor:
    """Monitors project file activity."""

    def __init__(self, project_paths: list[str] | None = None):
        """❌ Simple constructor - replace with DI"""
        self.project_paths = project_paths or []
        self.activity_buffer: list[ActivityEvent] = []
        self.observers: list[Any] = []
        self.ide_extensions = {".py", ".js", ".ts", ...}

    def add_activity(self, event: ActivityEvent) -> None:
        """Add activity event to buffer."""
        # Implementation
        pass
```

### Refactored Code (AFTER)

```python
from acb.depends import depends
from acb.config import AdapterBase, Settings
from acb.actions.base import ActionBase


# Step 1: Create Settings
class ActivityMonitorSettings(Settings):
    """Configuration for activity monitoring."""

    buffer_size: int = Field(
        default=1000, description="Maximum events in buffer", ge=100, le=10000
    )
    default_relevance: float = Field(
        default=0.5, description="Default relevance score", ge=0.0, le=1.0
    )
    watchdog_enabled: bool = Field(
        default=True, description="Enable file system watching"
    )
    min_file_size: int = Field(
        default=1, description="Minimum file size to track (bytes)", ge=0
    )


# Step 2: Create ACB Actions for reusable logic
class ActivityActions(ActionBase):
    """Custom actions for activity monitoring."""

    @staticmethod
    def calculate_relevance(
        event: ActivityEvent, settings: ActivityMonitorSettings
    ) -> float:
        """Calculate relevance score for an event."""
        score = settings.default_relevance

        # Boost for code files
        if any(
            event.details.get("file_path", "").endswith(ext)
            for ext in [".py", ".js", ".ts", ".go", ".rs"]
        ):
            score += 0.3

        # Boost for recent events
        event_time = datetime.fromisoformat(event.timestamp)
        age_minutes = (datetime.now() - event_time).total_seconds() / 60
        if age_minutes < 5:
            score += 0.2

        return min(score, 1.0)


# Register action globally
activity = ActivityActions()


# Step 3: Convert to AdapterBase
class ProjectActivityMonitor(AdapterBase):
    """Monitors project file activity."""

    settings: ActivityMonitorSettings | None = None

    async def init(self) -> None:
        """Initialize with DI."""
        if not self.settings:
            self.settings = ActivityMonitorSettings()

        # Get project paths from DI (if registered)
        try:
            self.project_paths = depends.get_sync("ProjectPaths")
        except (KeyError, AttributeError):
            self.project_paths = []

        self.activity_buffer: list[ActivityEvent] = []
        self.observers: list[Any] = []
        self.ide_extensions = {".py", ".js", ".ts", ".tsx", ".go", ".rs"}

    def add_activity(self, event: ActivityEvent) -> None:
        """Add activity event with automatic relevance calculation."""
        # Use ACB action for relevance scoring
        event.relevance_score = activity.calculate_relevance(event, self.settings)

        self.activity_buffer.append(event)

        # Trim buffer based on settings
        if len(self.activity_buffer) > self.settings.buffer_size:
            self.activity_buffer = self.activity_buffer[
                -self.settings.buffer_size // 2 :
            ]

    # Rest of implementation...
```

### Testing with ACB Actions

```python
@pytest.fixture
def monitor_settings():
    return ActivityMonitorSettings(
        buffer_size=100,
        default_relevance=0.5,
        watchdog_enabled=False,  # Disable for testing
    )


@pytest.fixture
async def activity_monitor(monitor_settings):
    monitor = ProjectActivityMonitor()
    monitor.settings = monitor_settings
    await monitor.init()
    return monitor


def test_relevance_calculation():
    """Test ACB action for relevance scoring."""
    from session_buddy.app_monitor import activity, ActivityEvent

    settings = ActivityMonitorSettings(default_relevance=0.5)

    event = ActivityEvent(
        timestamp=datetime.now().isoformat(),
        event_type="file_change",
        application="VSCode",
        details={"file_path": "/test/file.py"},
    )

    relevance = activity.calculate_relevance(event, settings)

    assert 0.0 <= relevance <= 1.0
    assert relevance > 0.5  # Should be boosted for .py file
```

______________________________________________________________________

## Module 3: memory_optimizer.py

### Current Code (BEFORE)

```python
class MemoryOptimizer:
    """Optimizes memory usage via compression."""

    def __init__(self, db: ReflectionDatabase):
        """❌ Constructor injection"""
        self.db = db
        self.summarizer = ConversationSummarizer()
        self.clusterer = ConversationClusterer()
        self.retention_manager = RetentionPolicyManager()
        self.compression_stats: dict[str, int] = {}
```

### Refactored Code (AFTER)

```python
from acb.depends import depends
from acb.config import AdapterBase, Settings
from acb.actions.compress import compress  # Use ACB compression


class OptimizerSettings(Settings):
    """Configuration for memory optimization."""

    compression_level: int = Field(
        default=4, description="Brotli compression level", ge=1, le=11
    )
    max_age_days: int = Field(
        default=90, description="Maximum age for conversations", ge=1, le=365
    )
    max_conversations: int = Field(
        default=1000, description="Maximum conversations to keep", ge=100, le=100000
    )
    dry_run_default: bool = Field(default=True, description="Default to dry-run mode")


class MemoryOptimizer(AdapterBase):
    """Optimizes memory usage via compression."""

    settings: OptimizerSettings | None = None

    async def init(self) -> None:
        """Initialize with DI."""
        if not self.settings:
            self.settings = OptimizerSettings()

        # Get dependencies via DI
        self.db = depends.get_sync("ReflectionDatabase")

        # Initialize components
        self.summarizer = ConversationSummarizer()
        self.clusterer = ConversationClusterer()
        self.retention_manager = RetentionPolicyManager()
        self.retention_manager.default_policies = {
            "max_age_days": self.settings.max_age_days,
            "max_conversations": self.settings.max_conversations,
        }

        self.compression_stats: dict[str, int] = {}

    async def compress_memory(self, dry_run: bool | None = None) -> dict[str, Any]:
        """Compress conversations using ACB compression."""
        if dry_run is None:
            dry_run = self.settings.dry_run_default

        # Get conversations
        conversations = await self._get_conversations()

        if not conversations:
            return {"status": "no_conversations"}

        # Use retention policy
        keep, consolidate = self.retention_manager.get_conversations_for_retention(
            conversations
        )

        # Use ACB's compression action
        total_saved = 0
        for conv in consolidate:
            original = conv["content"].encode("utf-8")

            # ACB provides optimized Brotli compression
            compressed = compress.brotli(
                original, level=self.settings.compression_level
            )

            total_saved += len(original) - len(compressed)

        return {
            "status": "success",
            "dry_run": dry_run,
            "total_conversations": len(conversations),
            "conversations_to_keep": len(keep),
            "conversations_to_consolidate": len(consolidate),
            "space_saved_estimate": total_saved,
            "compression_ratio": total_saved
            / sum(len(c["content"]) for c in conversations),
        }
```

### Testing with ACB Compression

```python
@pytest.mark.asyncio
async def test_compression_uses_acb():
    """Verify ACB compression is used."""
    from session_buddy.memory_optimizer import MemoryOptimizer
    from acb.actions.compress import compress

    settings = OptimizerSettings(compression_level=4)
    optimizer = MemoryOptimizer()
    optimizer.settings = settings

    # Mock database
    depends.set("ReflectionDatabase", MockDB())

    await optimizer.init()

    # Verify compression works
    test_data = b"test data" * 100
    compressed = compress.brotli(test_data, level=settings.compression_level)
    assert len(compressed) < len(test_data)
```

______________________________________________________________________

## Module 4: serverless_mode.py

### Current Code (BEFORE)

```python
class ACBCacheStorage(SessionStorage):
    """✅ Already uses ACB cache adapter"""

    def __init__(
        self,
        cache: Any,  # ❌ Manual injection
        namespace: str = "session",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config or {})
        self.cache = cache
        self.namespace = namespace
```

### Refactored Code (AFTER)

```python
from acb.depends import depends
from acb.adapters import import_adapter  # ACB adapter discovery


class ServerlessSettings(Settings):
    """Configuration for serverless sessions."""

    cache_backend: str = Field(
        default="memory", description="Cache backend type", pattern="^(memory|redis)$"
    )
    namespace: str = Field(
        default="session", description="Cache namespace", min_length=1, max_length=50
    )
    default_ttl: int = Field(
        default=86400,
        description="Default session TTL (seconds)",
        ge=60,
        le=604800,  # 1 week max
    )


class ACBCacheStorage(SessionStorage):
    """ACB cache adapter for session storage."""

    # Add settings support
    settings: ServerlessSettings | None = None

    @classmethod
    def from_settings(cls, settings: ServerlessSettings) -> "ACBCacheStorage":
        """Create from settings using ACB adapter discovery."""
        # Use ACB's adapter import
        Cache = import_adapter("cache")

        # Get or create cache instance
        try:
            cache = depends.get_sync(Cache)
        except (KeyError, AttributeError):
            # Create with settings
            cache = Cache(backend=settings.cache_backend)
            depends.set(Cache, cache)

        return cls(cache=cache, namespace=settings.namespace)

    def __init__(
        self,
        cache: Any,
        namespace: str = "session",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config or {})
        self.cache = cache
        self.namespace = namespace
        self._index_key = f"{namespace}:index"

        # Load settings if available
        if not self.settings:
            self.settings = ServerlessSettings(namespace=namespace)

    # Rest of implementation unchanged...
```

### Improved Factory with ACB

```python
class ServerlessConfigManager:
    """Factory for creating storage backends."""

    @staticmethod
    def create_storage_backend(config: dict[str, Any]) -> SessionStorage:
        """Create storage backend with ACB adapter discovery."""
        backend = config.get("storage_backend", "acb")

        if backend == "acb":
            # Extract settings
            backend_config = config.get("backends", {}).get("acb", {})
            settings = ServerlessSettings(
                cache_backend=backend_config.get("cache_type", "memory"),
                namespace=backend_config.get("namespace", "session"),
                default_ttl=backend_config.get("ttl_seconds", 86400),
            )

            # Create via ACB pattern
            return ACBCacheStorage.from_settings(settings)

        else:
            # Legacy backends with deprecation
            logger.warning(
                f"Storage backend '{backend}' is deprecated. "
                f"Use 'acb' with cache_type configuration instead."
            )
            return _create_legacy_backend(backend, config)
```

______________________________________________________________________

## Test Updates

### Unified conftest.py Fixtures

```python
# tests/conftest.py additions

import pytest
from acb.depends import depends
from pathlib import Path


@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset DI container between tests."""
    yield
    # Cleanup after each test
    depends.clear()


@pytest.fixture
def mock_reflection_db():
    """Mock ReflectionDatabase for all tests."""

    class MockDB:
        def __init__(self):
            self.data = {}

        async def store_project_group(self, group):
            self.data[group.id] = group
            return True

        async def get_project_groups(self):
            return list(self.data.values())

        async def store_conversation(self, content, project):
            conv_id = str(uuid.uuid4())
            self.data[conv_id] = {"content": content, "project": project}
            return conv_id

        async def get_conversations(self, project=None, limit=100):
            convs = list(self.data.values())
            if project:
                convs = [c for c in convs if c.get("project") == project]
            return convs[:limit]

    db = MockDB()
    depends.set("ReflectionDatabase", db)
    return db


@pytest.fixture
def mock_cache():
    """Mock ACB cache adapter."""
    from unittest.mock import AsyncMock

    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)

    # Register with DI
    depends.set("Cache", cache)
    return cache


@pytest.fixture
def project_paths(tmp_path):
    """Create temporary project paths."""
    paths = [tmp_path / "project1", tmp_path / "project2"]
    for p in paths:
        p.mkdir(parents=True)

    depends.set("ProjectPaths", [str(p) for p in paths])
    return paths


# Module-specific fixtures


@pytest.fixture
async def coordinator(mock_reflection_db):
    """MultiProjectCoordinator with DI."""
    from session_buddy.multi_project_coordinator import MultiProjectCoordinator

    coord = MultiProjectCoordinator()
    await coord.init()
    return coord


@pytest.fixture
async def activity_monitor(project_paths):
    """ProjectActivityMonitor with DI."""
    from session_buddy.app_monitor import ProjectActivityMonitor

    monitor = ProjectActivityMonitor()
    await monitor.init()
    return monitor


@pytest.fixture
async def memory_optimizer(mock_reflection_db):
    """MemoryOptimizer with DI."""
    from session_buddy.memory_optimizer import MemoryOptimizer

    optimizer = MemoryOptimizer()
    await optimizer.init()
    return optimizer


@pytest.fixture
def serverless_storage(mock_cache):
    """ACBCacheStorage with DI."""
    from session_buddy.serverless_mode import ACBCacheStorage, ServerlessSettings

    settings = ServerlessSettings(cache_backend="memory", namespace="test")
    storage = ACBCacheStorage.from_settings(settings)
    return storage
```

### Updated Test Examples

```text
# tests/unit/test_multi_project_coordinator.py


@pytest.mark.asyncio
async def test_create_project_group_with_di(coordinator):
    """Test with DI fixture - much cleaner!"""
    group = await coordinator.create_project_group(
        name="Test Group", projects=["proj-a", "proj-b"], description="Test description"
    )

    assert group.name == "Test Group"
    assert len(group.projects) == 2


@pytest.mark.asyncio
async def test_settings_validation(coordinator):
    """Test that settings are enforced."""
    # Coordinator has max_projects=100 by default
    with pytest.raises(ValueError):
        await coordinator.create_project_group(
            name="Too Large", projects=[f"proj-{i}" for i in range(200)]
        )
```

______________________________________________________________________

## Verification Steps

### Step 1: Run Tests

```bash
# Run all Week 5 tests
pytest tests/unit/test_multi_project_coordinator.py \
       tests/unit/test_app_monitor.py \
       tests/unit/test_memory_optimizer.py \
       tests/unit/test_serverless_mode.py \
       -v

# Expected: All 79 tests should still pass
```

### Step 2: Verify DI Usage

```bash
# Check that depends.get_sync() is used
grep -r "depends.get_sync" session_buddy/*.py

# Expected: Should find usage in all 4 modules
```

### Step 3: Check Coverage

```bash
# Coverage should remain similar or improve
pytest tests/unit/test_multi_project_coordinator.py \
       --cov=session_buddy/multi_project_coordinator \
       --cov-report=term-missing

# Expected: 86%+ coverage maintained
```

### Step 4: Integration Test

```python
# test_acb_integration.py
@pytest.mark.integration
async def test_full_acb_stack():
    """Verify all modules work together with ACB DI."""
    from acb.depends import depends

    # Initialize all components via DI
    coordinator = depends.get_sync(MultiProjectCoordinator)
    await coordinator.init()

    monitor = depends.get_sync(ProjectActivityMonitor)
    await monitor.init()

    optimizer = depends.get_sync(MemoryOptimizer)
    await optimizer.init()

    # Verify they all work
    group = await coordinator.create_project_group("test", ["proj-a"])
    assert group is not None

    # Cleanup
    depends.clear()
```

______________________________________________________________________

## Common Pitfalls to Avoid

### ❌ Pitfall 1: Forgetting to call init()

```text
# WRONG
coordinator = MultiProjectCoordinator()
await coordinator.create_project_group(...)  # Will fail, db is None

# RIGHT
coordinator = MultiProjectCoordinator()
await coordinator.init()  # Initializes dependencies
await coordinator.create_project_group(...)  # Works
```

### ❌ Pitfall 2: Not clearing DI container in tests

```python
# WRONG - Tests interfere with each other
def test_one():
    depends.set("Cache", mock_cache)
    # Test runs

def test_two():
    # Still has mock_cache from test_one!

# RIGHT - Use autouse fixture
@pytest.fixture(autouse=True)
def cleanup():
    yield
    depends.clear()
```

### ❌ Pitfall 3: Mixing manual and DI instantiation

```python
# WRONG - Inconsistent patterns
coordinator1 = MultiProjectCoordinator()  # DI
coordinator2 = MultiProjectCoordinator(db=my_db)  # Manual

# RIGHT - Always use DI
coordinator1 = depends.get_sync(MultiProjectCoordinator)
coordinator2 = depends.get_sync(MultiProjectCoordinator)  # Same instance
```

______________________________________________________________________

## Rollout Strategy

### Phase 1: Core Module (Day 1, 4 hours)

1. Refactor `multi_project_coordinator.py` first
1. Update its tests
1. Verify all tests pass
1. Document learnings

**Rationale:** Highest coverage (86%), good reference for others

### Phase 2: Remaining Modules (Day 1-2, 8 hours)

1. Refactor `app_monitor.py`
1. Refactor `memory_optimizer.py`
1. Refactor `serverless_mode.py`
1. Update all tests together

### Phase 3: Verification (Day 2, 2 hours)

1. Run full test suite
1. Check coverage metrics
1. Integration testing
1. Update documentation

______________________________________________________________________

## Success Criteria

✅ **All tests passing** (79/79)
✅ **Coverage maintained** (41-86% range)
✅ **DI used consistently** (all 4 modules)
✅ **Settings classes created** (4 new classes)
✅ **AdapterBase inheritance** (4 modules converted)
✅ **No constructor injection** (all removed)
✅ **Tests use fixtures** (no manual mocking)

______________________________________________________________________

## Questions & Answers

**Q: Do I need to change all tests at once?**
A: No, refactor one module at a time. Tests will fail until both implementation and tests are updated.

**Q: What if I have existing DI dependencies?**
A: Great! Use `depends.get_sync()` for all new dependencies. Be consistent.

**Q: Can I keep some manual instantiation for testing?**
A: Yes, but use DI fixtures as the default pattern for consistency.

**Q: How do I handle async initialization?**
A: Use `async def init()` method. Call it after creating instance via DI.

**Q: What about backward compatibility?**
A: Keep constructor for now (deprecated), add class methods for DI creation.

______________________________________________________________________

## Additional Resources

- **ACB Documentation:** See agent instructions in `.claude/agents/acb-specialist.md`
- **Pattern Examples:** Look at `session_buddy/server.py` and `tools/session_tools.py`
- **DI Configuration:** Review `session_buddy/di/__init__.py`
- **Settings Patterns:** Check ACB Settings documentation in agent instructions

______________________________________________________________________

**Document Version:** 1.0
**Last Updated:** 2025-10-29
**Status:** Ready for implementation
**Estimated Effort:** 1-2 days
