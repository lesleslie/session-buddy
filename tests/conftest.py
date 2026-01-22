#!/usr/bin/env python3
"""Global test configuration and fixtures for session-mgmt-mcp tests."""

pytest_plugins = ["tests.helpers"]

import asyncio
import os
import shutil
import tempfile
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import suppress
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import duckdb
import numpy as np
import pytest
from fastmcp import FastMCP
# Migration Phase 2.7: Use ReflectionDatabaseAdapter (ACB-based)
from session_buddy.adapters.reflection_adapter import (
    ReflectionDatabaseAdapter as ReflectionDatabase,
)

# Configure DI container BEFORE any other imports
# This ensures SessionLogger and other dependencies are available
from session_buddy.di import configure as configure_di
from session_buddy.di.container import depends

# Initialize DI container for tests - force registration to bypass async checks
try:
    configure_di(force=True)
except Exception as e:
    # If DI configuration fails during import, we'll retry in the fixture
    import warnings

    warnings.warn(f"DI configuration failed during conftest import: {e}", stacklevel=2)


# =====================================
# MockFastMCP for Testing (Phase 2.6)
# =====================================


class MockFastMCP:
    """Minimal mock FastMCP for testing environments.

    Extracted from server.py Phase 2.6 to consolidate test infrastructure.
    """

    def __init__(self, name: str, lifespan: Any = None, **kwargs: Any) -> None:
        """Initialize mock FastMCP server."""
        self.name = name
        self.tools: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}
        self.lifespan = lifespan
        self.http_app = None  # Mock http_app attribute

    def tool(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Mock tool decorator."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator

    def prompt(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Mock prompt decorator."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator

    def run(self, *args: Any, **kwargs: Any) -> None:
        """Mock run method."""


# Import test factories for enhanced test data generation
# Note: After Phase 2.7 cleanup, only actively-used factories are imported
try:
    from tests.fixtures.data_factories import (
        LargeDatasetFactory,
        ReflectionDataFactory,
        SecurityTestDataFactory,
    )
except ImportError:
    # Create minimal mocks when factories aren't available
    class ReflectionDataFactory:
        @staticmethod
        def create():
            return {"content": "Test reflection", "tags": ["test"]}

    class LargeDatasetFactory:
        @staticmethod
        def generate_large_reflection_dataset(count: int = 1000):
            return [ReflectionDataFactory.create() for _ in range(count)]

    class SecurityTestDataFactory:
        @staticmethod
        def create():
            return {"valid_token": "test-token", "operation": "read"}


# =====================================
# OPTIMIZED FIXTURES (Performance)
# =====================================


@pytest.fixture(scope="session")
def temp_base_dir() -> Generator[Path]:
    """Session-scoped base directory for all tests (reduces filesystem operations)."""
    with tempfile.TemporaryDirectory(prefix="session_mgmt_test_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_test_dir(temp_base_dir: Path) -> Generator[Path]:
    """Function-scoped test directory within session temp dir."""
    test_dir = temp_base_dir / f"test_{id(temp_base_dir)}"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


@pytest.fixture
async def fast_async_context():
    """Optimized async context with minimal overhead."""
    loop = asyncio.get_event_loop()

    context = {
        "loop": loop,
        "tasks": [],
    }

    yield context

    for task in context["tasks"]:
        if not task.done():
            task.cancel()

    if context["tasks"]:
        await asyncio.gather(*context["tasks"], return_exceptions=True)


class ResourcePool:
    """Pool expensive test resources for reuse across tests."""

    def __init__(self):
        self._resources: dict[str, Any] = {}

    def get_or_create(self, key: str, factory):
        """Get existing resource or create new one."""
        if key not in self._resources:
            self._resources[key] = factory()
        return self._resources[key]

    def cleanup(self):
        """Clean up all pooled resources."""
        self._resources.clear()


@pytest.fixture(scope="session")
def resource_pool():
    """Session-wide resource pool."""
    pool = ResourcePool()
    yield pool
    pool.cleanup()


class TestPerformanceTracker:
    """Track test performance metrics for optimization analysis."""

    def __init__(self):
        self.timings: dict[str, float] = {}
        self.slow_threshold = 1.0  # seconds

    def record(self, test_name: str, duration: float):
        """Record test duration."""
        self.timings[test_name] = duration

    def get_slow_tests(self) -> list[tuple[str, float]]:
        """Get tests exceeding slow threshold."""
        return [
            (name, duration)
            for name, duration in self.timings.items()
            if duration > self.slow_threshold
        ]


@pytest.fixture(scope="session")
def performance_tracker():
    """Session-wide performance tracker."""
    return TestPerformanceTracker()


@pytest.fixture(scope="session")
def mock_logger_factory():
    """Factory for creating mock loggers - session scoped for reuse."""

    def create_mock_logger(**kwargs) -> Mock:
        logger = Mock()
        logger.info = Mock()
        logger.debug = Mock()
        logger.warning = Mock()
        logger.error = Mock()
        logger.critical = Mock()
        for key, value in kwargs.items():
            setattr(logger, key, value)
        return logger

    return create_mock_logger


@pytest.fixture
async def fast_temp_db(tmp_path) -> AsyncGenerator[ReflectionDatabase]:
    """Optimized temporary file database for faster tests."""
    # For tests, we'll create a custom settings object with a temporary file
    from pathlib import Path

    from session_buddy.adapters.settings import ReflectionAdapterSettings

    # Use a temporary file instead of in-memory for compatibility with the new adapter
    temp_db_path = tmp_path / "test.duckdb"

    # Create settings with temporary database path
    settings = ReflectionAdapterSettings(
        database_path=temp_db_path,
        collection_name="default",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,  # Disable vector similarity search for tests
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,  # Disable embeddings for faster tests
    )

    db = ReflectionDatabase(settings=settings)
    await db.initialize()
    yield db
    with suppress(Exception):
        close = getattr(db, "aclose", None)
        if callable(close):
            await close()
        else:
            db.close()


@pytest.fixture
async def db_with_sample_data(fast_temp_db: ReflectionDatabase) -> ReflectionDatabase:
    """Database pre-populated with minimal sample data."""
    await fast_temp_db.store_conversation("Sample conversation", {"project": "test"})
    await fast_temp_db.store_reflection("Sample reflection", ["test"])
    return fast_temp_db


@pytest.fixture(scope="session")
def mock_git_repo_factory():
    """Factory for creating mock git repository structures."""

    def create_mock_git_repo(path: Path, **kwargs):
        git_dir = path / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        refs_dir = git_dir / "refs" / "heads"
        refs_dir.mkdir(parents=True, exist_ok=True)
        (refs_dir / "main").write_text("0" * 40 + "\n")
        return git_dir

    return create_mock_git_repo


@pytest.fixture(scope="session")
def mock_project_factory():
    """Factory for creating mock project structures."""

    def create_mock_project(path: Path, features: dict[str, bool]):
        cleanup_files = [
            path / "pyproject.toml",
            path / "uv.lock",
            path / "README.md",
            path / "coverage.json",
            path / ".gitignore",
        ]
        cleanup_dirs = [
            path / ".git",
            path / "tests",
            path / "src",
            path / "docs",
        ]
        for cleanup_file in cleanup_files:
            with suppress(FileNotFoundError):
                cleanup_file.unlink()
        for cleanup_dir in cleanup_dirs:
            if cleanup_dir.exists():
                shutil.rmtree(cleanup_dir, ignore_errors=True)

        from session_buddy.utils import quality_utils_v2

        quality_utils_v2._metrics_cache.pop(str(path.resolve()), None)

        if features.get("has_pyproject_toml"):
            (path / "pyproject.toml").write_text('[project]\nname = "test"\n')
            (path / "uv.lock").write_text("version = 1\n")
        if features.get("has_git_repo"):
            git_dir = path / ".git"
            git_dir.mkdir(parents=True, exist_ok=True)
            (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
            refs_dir = git_dir / "refs" / "heads"
            refs_dir.mkdir(parents=True, exist_ok=True)
            (refs_dir / "main").write_text("0" * 40 + "\n")
            (path / ".gitignore").write_text(".env\n")
        if features.get("has_readme"):
            (path / "README.md").write_text("# Test Project\n")
        if features.get("has_tests"):
            tests_dir = path / "tests"
            tests_dir.mkdir(exist_ok=True)
            for index in range(5):
                (tests_dir / f"test_example_{index}.py").write_text(
                    "def test_x(): pass\n"
                )
            (path / "coverage.json").write_text('{"totals": {"percent_covered": 80}}')
        if features.get("has_src"):
            src_dir = path / "src"
            src_dir.mkdir(exist_ok=True)
            (src_dir / "__init__.py").touch()
        if features.get("has_docs"):
            docs_dir = path / "docs"
            docs_dir.mkdir(exist_ok=True)
            (docs_dir / "index.md").write_text("# Docs\n")
        return path

    return create_mock_project


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create session-scoped event loop for async tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    yield loop

    # Clean up pending tasks
    if not loop.is_closed():
        # Cancel all pending tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        # Wait for tasks to be cancelled
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.close()


@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset DI container between tests to ensure clean state.

    This fixture runs automatically for every test to prevent DI state
    leakage between tests. It cleans up all singleton instances from the
    bevy container, including:
    - SessionPaths, SessionLogger, SessionPermissionsManager, SessionLifecycleManager
    - ApplicationMonitor, LLMManager, ServerlessSessionManager
    - ReflectionDatabase, InterruptionManager

    Week 8 Day 1: Enhanced to fix test isolation issues by directly
    cleaning the bevy container instances dictionary. Reset happens both
    before and after test to ensure clean state for monkeypatching.
    """

    def _cleanup_container():
        """Helper function to clean up the DI container."""
        try:
            from bevy import get_container
            from session_buddy.di import SessionPaths

            container = get_container()

            # List of all singleton classes to clean up
            singleton_classes = [
                SessionPaths,
                # Core DI singletons
                "SessionLogger",
                "SessionPermissionsManager",
                "SessionLifecycleManager",
                # Instance manager singletons
                "ApplicationMonitor",
                "LLMManager",
                "ServerlessSessionManager",
                "ReflectionDatabase",
                "InterruptionManager",
            ]

            # Clean up each singleton from container
            for cls in singleton_classes:
                # Handle both direct class and string class names
                if isinstance(cls, str):
                    # Import the class dynamically
                    try:
                        if cls == "SessionLogger":
                            from session_buddy.utils.logging import SessionLogger

                            cls = SessionLogger
                        elif cls == "SessionPermissionsManager":
                            from session_buddy.core.permissions import (
                                SessionPermissionsManager,
                            )

                            cls = SessionPermissionsManager
                        elif cls == "SessionLifecycleManager":
                            from session_buddy.core import SessionLifecycleManager

                            cls = SessionLifecycleManager
                        elif cls == "ApplicationMonitor":
                            from session_buddy.app_monitor import ApplicationMonitor

                            cls = ApplicationMonitor
                        elif cls == "LLMManager":
                            from session_buddy.llm_providers import LLMManager

                            cls = LLMManager
                        elif cls == "ServerlessSessionManager":
                            from session_buddy.serverless_mode import (
                                ServerlessSessionManager,
                            )

                            cls = ServerlessSessionManager
                        elif cls == "ReflectionDatabase":
                            # Migration Phase 2.7: Use ReflectionDatabaseAdapter (ACB-based)
                            from session_buddy.adapters.reflection_adapter import (
                                ReflectionDatabaseAdapter as ReflectionDatabase,
                            )

                            cls = ReflectionDatabase
                        elif cls == "InterruptionManager":
                            from session_buddy.interruption_manager import (
                                InterruptionManager,
                            )

                            cls = InterruptionManager
                    except ImportError:
                        continue

                # Remove from container if present
                try:
                    container.instances.pop(cls, None)
                except (KeyError, TypeError):
                    pass

            # Reset configuration flag
            import session_buddy.di as di_module

            di_module._configured = False

        except Exception:
            # If cleanup fails, we'll try again on next test
            pass

    # Clean up BEFORE test to ensure monkeypatch can take effect
    _cleanup_container()

    # Test runs here
    yield

    # Clean up AFTER test as well for consistency
    _cleanup_container()


@pytest.fixture
async def temp_db_path() -> AsyncGenerator[str]:
    """Provide temporary database path that's cleaned up after test."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
        db_path = tmp.name

    yield db_path

    # Cleanup
    try:
        db_path_obj = Path(db_path)
        if db_path_obj.exists():
            db_path_obj.unlink()
    except (OSError, PermissionError):
        # On Windows, file might still be locked
        pass


@pytest.fixture
async def temp_claude_dir() -> AsyncGenerator[Path]:
    """Provide temporary ~/.claude directory structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        claude_dir = Path(temp_dir) / ".claude"
        claude_dir.mkdir()

        # Create expected subdirectories
        (claude_dir / "data").mkdir()
        (claude_dir / "logs").mkdir()

        # Patch the home directory
        with patch.dict(os.environ, {"HOME": str(Path(temp_dir))}):
            with patch(
                "os.path.expanduser",
                lambda path: path.replace("~", str(Path(temp_dir))),
            ):
                yield claude_dir


@pytest.fixture(scope="session")
async def shared_temp_db_path() -> AsyncGenerator[str]:
    """Session-scoped temporary database path to reduce file operations."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
        db_path = tmp.name

    yield db_path

    # Cleanup
    try:
        db_path_obj = Path(db_path)
        if db_path_obj.exists():
            db_path_obj.unlink()
    except (OSError, PermissionError):
        # On Windows, file might still be locked
        pass


@pytest.fixture
async def reflection_db(temp_db_path: str) -> AsyncGenerator[ReflectionDatabase]:
    """Provide initialized ReflectionDatabase instance."""
    from pathlib import Path

    from session_buddy.adapters.settings import ReflectionAdapterSettings

    # Create settings with database path
    settings = ReflectionAdapterSettings(
        database_path=Path(temp_db_path),
        collection_name="default",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,  # Disable vector similarity search for tests
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,  # Disable embeddings for faster tests
    )

    db = ReflectionDatabase(settings=settings)

    try:
        await db.initialize()
        yield db
    finally:
        close = getattr(db, "aclose", None)
        if callable(close):
            await close()
        else:
            db.close()


@pytest.fixture
async def reflection_db_with_data(
    reflection_db: ReflectionDatabase,
) -> AsyncGenerator[ReflectionDatabase]:
    """Provide ReflectionDatabase with test data."""
    # Add some test conversations
    test_conversations = [
        "How do I implement async/await patterns in Python?",
        "Setting up pytest fixtures for database testing",
        "Best practices for MCP server development",
        "DuckDB vector operations and similarity search",
        "FastMCP tool registration and async handlers",
    ]

    conversation_ids = []
    for content in test_conversations:
        conv_id = await reflection_db.store_conversation(
            content, {"project": "test-project"}
        )
        conversation_ids.append(conv_id)

    # Add some test reflections
    test_reflections = [
        (
            "Always use context managers for database connections",
            ["database", "patterns"],
        ),
        (
            "Async fixtures require careful setup in pytest",
            ["testing", "async", "pytest"],
        ),
        ("MCP tools should handle errors gracefully", ["mcp", "error-handling"]),
    ]

    reflection_ids = []
    for content, tags in test_reflections:
        refl_id = await reflection_db.store_reflection(content, tags)
        reflection_ids.append(refl_id)

    # Store IDs for test reference
    reflection_db._test_conversation_ids = conversation_ids
    reflection_db._test_reflection_ids = reflection_ids

    return reflection_db


@pytest.fixture(scope="session")
async def shared_reflection_db() -> AsyncGenerator[ReflectionDatabase]:
    """Session-scoped ReflectionDatabase for tests that can share data."""
    import tempfile
    from pathlib import Path

    from session_buddy.adapters.settings import ReflectionAdapterSettings

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
        db_path = tmp.name

    # Create settings with database path
    settings = ReflectionAdapterSettings(
        database_path=Path(db_path),
        collection_name="default",
        embedding_dim=384,
        distance_metric="cosine",
        enable_vss=False,  # Disable vector similarity search for tests
        threads=1,
        memory_limit="512MB",
        enable_embeddings=False,  # Disable embeddings for faster tests
    )

    db = ReflectionDatabase(settings=settings)
    await db.initialize()

    try:
        # Pre-populate with common test data
        test_conversations = [
            "Shared test conversation 1",
            "Shared test conversation 2",
            "Shared test conversation 3",
        ]

        for content in test_conversations:
            await db.store_conversation(content, {"project": "shared-test"})

        yield db
    finally:
        close = getattr(db, "aclose", None)
        if callable(close):
            await close()
        else:
            db.close()
        # Cleanup
        try:
            db_path_obj = Path(db_path)
            if db_path_obj.exists():
                db_path_obj.unlink()
        except (OSError, PermissionError):
            pass


@pytest.fixture
def mock_onnx_session() -> Mock:
    """Provide mock ONNX session for embedding tests."""
    mock_session = Mock()
    # Mock returns a 384-dimensional vector
    rng = np.random.default_rng(42)
    mock_session.run.return_value = [rng.random((1, 384)).astype(np.float32)]
    return mock_session


@pytest.fixture
def mock_tokenizer() -> Mock:
    """Provide mock tokenizer for embedding tests."""
    mock_tokenizer = Mock()
    mock_tokenizer.return_value = {
        "input_ids": [[1, 2, 3, 4, 5]],
        "attention_mask": [[1, 1, 1, 1, 1]],
    }
    return mock_tokenizer


@pytest.fixture
async def mock_mcp_server() -> AsyncGenerator[Mock]:
    """Provide mock MCP server for testing."""
    mock_server = Mock()
    mock_server.tool = Mock()
    mock_server.prompt = Mock()

    # Mock async context manager behavior - assign directly to the mock object
    mock_server.__aenter__ = AsyncMock(return_value=mock_server)
    mock_server.__aexit__ = AsyncMock(return_value=None)

    return mock_server


@pytest.fixture
def clean_environment(tmp_path) -> Generator[dict[str, Any]]:
    """Provide clean environment with common patches."""
    original_env = os.environ.copy()

    # Set up test environment
    test_env = {
        "TESTING": "1",
        "LOG_LEVEL": "DEBUG",
    }

    # Remove potentially problematic env vars
    env_to_remove = ["OLDPWD", "VIRTUAL_ENV"]

    try:
        # Update environment
        os.environ.update(test_env)
        for key in env_to_remove:
            os.environ.pop(key, None)

        # Change to a safe temporary directory to avoid cwd issues
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        yield test_env

    finally:
        # Restore original environment and working directory
        os.environ.clear()
        os.environ.update(original_env)
        os.chdir(original_cwd)


@pytest.fixture
async def async_client() -> AsyncGenerator[Mock]:
    """Provide async client for MCP communication testing."""
    client = Mock()

    # Mock async methods
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.call_tool = AsyncMock()
    client.list_tools = AsyncMock(return_value=[])

    return client


@pytest.fixture
def sample_embedding() -> np.ndarray:
    """Provide sample embedding vector for testing."""
    # Create a consistent sample embedding
    rng = np.random.default_rng(42)
    return rng.random((384,)).astype(np.float32)


@pytest.fixture
def mock_embeddings_disabled():
    """Fixture to disable embeddings for testing fallback behavior."""
    with patch("session_buddy.reflection_tools.ONNX_AVAILABLE", False):
        yield


@pytest.fixture
async def duckdb_connection() -> AsyncGenerator[duckdb.DuckDBPyConnection]:
    """Provide in-memory DuckDB connection for testing."""
    conn = duckdb.connect(":memory:")

    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def mock_file_operations():
    """Mock file system operations for testing."""
    mocks = {}

    with (
        patch("pathlib.Path.mkdir") as mock_mkdir,
        patch("pathlib.Path.exists") as mock_exists,
        patch("pathlib.Path.unlink") as mock_unlink,
        patch("os.path.exists") as mock_os_exists,
    ):
        mock_exists.return_value = True
        mock_os_exists.return_value = True

        mocks["mkdir"] = mock_mkdir
        mocks["exists"] = mock_exists
        mocks["unlink"] = mock_unlink
        mocks["os_exists"] = mock_os_exists

        yield mocks


# Async test markers and utilities
@pytest.fixture(autouse=True)
def detect_asyncio_leaks():
    """Automatically detect asyncio task leaks in tests."""
    # Only check for leaks if there's a running event loop
    try:
        initial_tasks = len(asyncio.all_tasks())
    except RuntimeError:
        # No event loop running, skip leak detection
        yield
        return

    yield

    # Check for task leaks after test
    try:
        final_tasks = asyncio.all_tasks()
        if len(final_tasks) > initial_tasks:
            # Allow a small buffer for cleanup tasks
            if len(final_tasks) > initial_tasks + 2:
                task_names = [task.get_name() for task in final_tasks]
                pytest.fail(f"Potential task leak detected. Active tasks: {task_names}")
    except RuntimeError:
        # Event loop closed, no need to check
        pass


@pytest.fixture
def performance_baseline() -> dict[str, float]:
    """Provide performance baselines for benchmark tests."""
    return {
        "db_insert_time": 0.1,  # 100ms per insert
        "embedding_generation": 0.5,  # 500ms per embedding
        "search_query": 0.2,  # 200ms per search
        "bulk_operation": 1.0,  # 1s for bulk operations
    }


# Helper functions for test data generation
def generate_test_conversation(
    content: str = "Test conversation content",
    project: str = "test-project",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Generate test conversation data."""
    return {
        "content": content,
        "project": project,
        "timestamp": timestamp or "2024-01-01T12:00:00Z",
    }


def generate_test_reflection(
    content: str = "Test reflection content",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Generate test reflection data."""
    return {
        "content": content,
        "tags": tags or ["test"],
    }


# Pytest configuration hooks
def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "async_test: mark test as requiring async event loop"
    )
    config.addinivalue_line("markers", "db_test: mark test as requiring database")
    config.addinivalue_line(
        "markers", "embedding_test: mark test as requiring embeddings"
    )
    config.addinivalue_line("markers", "mcp_test: mark test as MCP server test")


# Performance Testing Fixtures
@pytest.fixture
def performance_monitor():
    """Monitor for performance testing with memory and timing metrics."""
    import time

    try:
        import psutil
    except ImportError:
        # Fallback monitor when psutil unavailable
        class SimplePerformanceMonitor:
            def __init__(self):
                self.start_time = None
                self.execution_times = {}

            def start_monitoring(self):
                self.start_time = time.time()

            def stop_monitoring(self):
                return {
                    "duration": time.time() - self.start_time if self.start_time else 0,
                    "memory_delta": 0,
                    "peak_memory": 0,
                }

            def record_execution_time(self, operation_name, execution_time):
                """Record the time taken for a specific operation."""
                self.execution_times[operation_name] = execution_time

        return SimplePerformanceMonitor()

    class PerformanceMonitor:
        def __init__(self):
            self.process = psutil.Process()
            self.start_time = None
            self.start_memory = None
            self.execution_times = {}

        def start_monitoring(self):
            self.start_time = time.time()
            self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB

        def stop_monitoring(self):
            end_time = time.time()
            end_memory = self.process.memory_info().rss / 1024 / 1024  # MB

            return {
                "duration": end_time - self.start_time,
                "memory_delta": end_memory - self.start_memory,
                "peak_memory": end_memory,
            }

        def record_execution_time(self, operation_name, execution_time):
            """Record the time taken for a specific operation."""
            self.execution_times[operation_name] = execution_time

    return PerformanceMonitor()


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on markers and environment."""
    run_performance = os.environ.get("RUN_PERFORMANCE_TESTS") == "1"
    skip_performance = pytest.mark.skip(
        reason="performance tests disabled; set RUN_PERFORMANCE_TESTS=1 to run"
    )

    # Add async marker to all async tests
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.async_test)

        # Add markers based on test file location
        if "integration" in str(item.fspath):
            item.add_marker("integration")
        elif "unit" in str(item.fspath):
            item.add_marker("unit")
        elif "functional" in str(item.fspath):
            item.add_marker("functional")
        elif "performance" in str(item.fspath):
            item.add_marker("performance")
        elif "security" in str(item.fspath):
            item.add_marker("security")

        if "performance" in item.keywords and not run_performance:
            item.add_marker(skip_performance)


# Session management specific fixtures
@pytest.fixture
async def session_permissions():
    """Provide mock session permissions for testing."""

    class MockSessionPermissions:
        def __init__(self):
            self.trusted_operations = set()

        def add_trusted_operation(self, operation: str):
            self.trusted_operations.add(operation)

        def is_trusted(self, operation: str) -> bool:
            return operation in self.trusted_operations

    return MockSessionPermissions()


@pytest.fixture
async def temp_database(temp_db_path: str):
    """Provide temporary database for testing."""
    return temp_db_path


@pytest.fixture
async def temp_working_dir():
    """Provide temporary working directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


# Settings mock fixture to avoid configuration loading issues
@pytest.fixture(autouse=True)
def mock_settings(tmp_path):
    """Mock settings to avoid loading actual configuration.

    Uses pytest's tmp_path fixture to ensure each test gets a unique
    database path, avoiding DuckDB file lock conflicts between tests.
    """
    from pathlib import Path
    from unittest.mock import Mock, patch

    # Use pytest's tmp_path for unique per-test database path
    test_data_dir = tmp_path / "session-buddy-data"
    test_data_dir.mkdir(exist_ok=True)
    test_log_dir = tmp_path / "session-buddy-logs"
    test_log_dir.mkdir(exist_ok=True)

    with patch("session_buddy.settings.SessionMgmtSettings") as mock_settings_class:
        mock_settings_instance = Mock()
        mock_settings_instance.server_name = "Test Session Buddy MCP"
        mock_settings_instance.server_description = "Test configuration for Session Buddy MCP server"
        mock_settings_instance.log_level = "INFO"
        mock_settings_instance.enable_debug_mode = False
        mock_settings_instance.data_dir = test_data_dir
        mock_settings_instance.log_dir = test_log_dir
        mock_settings_instance.database_path = test_data_dir / "reflection.duckdb"
        mock_settings_instance.database_connection_timeout = 30
        mock_settings_instance.database_query_timeout = 120
        mock_settings_instance.database_max_connections = 10
        mock_settings_instance.enable_multi_project = True
        mock_settings_instance.auto_detect_projects = True
        mock_settings_instance.project_groups_enabled = True
        mock_settings_instance.enable_full_text_search = True
        mock_settings_instance.search_index_update_interval = 3600
        mock_settings_instance.max_search_results = 100
        mock_settings_instance.enable_semantic_search = True
        mock_settings_instance.embedding_model = "all-MiniLM-L6-v2"
        mock_settings_instance.embedding_cache_size = 1000
        mock_settings_instance.enable_faceted_search = True
        mock_settings_instance.max_facet_values = 50
        mock_settings_instance.enable_search_suggestions = True
        mock_settings_instance.suggestion_limit = 10
        mock_settings_instance.enable_stemming = True
        mock_settings_instance.enable_fuzzy_matching = True
        mock_settings_instance.fuzzy_threshold = 0.8
        mock_settings_instance.enable_token_optimization = True
        mock_settings_instance.default_max_tokens = 4000
        mock_settings_instance.default_chunk_size = 2000
        mock_settings_instance.optimization_strategy = "auto"
        mock_settings_instance.enable_response_chunking = True
        mock_settings_instance.enable_duplicate_filtering = True
        mock_settings_instance.track_token_usage = True
        mock_settings_instance.usage_retention_days = 90
        mock_settings_instance.auto_checkpoint_interval = 1800
        mock_settings_instance.enable_auto_commit = True
        mock_settings_instance.commit_message_template = "checkpoint: Session checkpoint - {timestamp}"
        mock_settings_instance.enable_permission_system = True
        mock_settings_instance.default_trusted_operations = ["git_commit", "uv_sync", "file_operations"]
        mock_settings_instance.auto_cleanup_old_sessions = True
        mock_settings_instance.session_retention_days = 365
        mock_settings_instance.enable_auto_store_reflections = True
        mock_settings_instance.auto_store_quality_delta_threshold = 10
        mock_settings_instance.auto_store_exceptional_quality_threshold = 90
        mock_settings_instance.auto_store_manual_checkpoints = True
        mock_settings_instance.auto_store_session_end = True
        mock_settings_instance.enable_crackerjack = True
        mock_settings_instance.crackerjack_command = "crackerjack"
        mock_settings_instance.enable_git_integration = True
        mock_settings_instance.git_auto_stage = False
        mock_settings_instance.global_workspace_path = Path("~/Projects/claude")
        mock_settings_instance.enable_global_toolkits = True
        mock_settings_instance.openai_api_key = None
        mock_settings_instance.anthropic_api_key = None
        mock_settings_instance.gemini_api_key = None
        mock_settings_instance.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        mock_settings_instance.enable_file_logging = True
        mock_settings_instance.log_file_path = Path("/tmp/test-session-buddy-logs/session-buddy.log")
        mock_settings_instance.log_file_max_size = 10 * 1024 * 1024
        mock_settings_instance.log_file_backup_count = 5
        mock_settings_instance.enable_performance_logging = False
        mock_settings_instance.log_slow_queries = True
        mock_settings_instance.slow_query_threshold = 1.0
        mock_settings_instance.anonymize_paths = False
        mock_settings_instance.enable_rate_limiting = True
        mock_settings_instance.max_requests_per_minute = 100
        mock_settings_instance.max_query_length = 10000
        mock_settings_instance.max_content_length = 1000000
        mock_settings_instance.server_host = "localhost"
        mock_settings_instance.server_port = 3000
        mock_settings_instance.enable_hot_reload = False
        mock_settings_instance.use_schema_v2 = True
        mock_settings_instance.enable_llm_entity_extraction = True
        mock_settings_instance.enable_anthropic = True
        mock_settings_instance.enable_ollama = False
        mock_settings_instance.enable_conscious_agent = True
        mock_settings_instance.enable_filesystem_extraction = True
        mock_settings_instance.llm_extraction_timeout = 10
        mock_settings_instance.llm_extraction_retries = 1
        mock_settings_instance.filesystem_dedupe_ttl_seconds = 120
        mock_settings_instance.filesystem_max_file_size_bytes = 1000000
        mock_settings_instance.filesystem_ignore_dirs = [
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "dist",
            "build",
            ".DS_Store",
            ".idea",
            ".vscode",
        ]
        # Insight extraction settings
        mock_settings_instance.enable_insight_extraction = True
        mock_settings_instance.insight_extraction_confidence_threshold = 0.3
        mock_settings_instance.insight_extraction_max_per_checkpoint = 10
        # Set up the mock to return the instance when load is called OR directly instantiated
        mock_settings_class.return_value = mock_settings_instance  # For SessionMgmtSettings()
        mock_settings_class.load.return_value = mock_settings_instance  # For SessionMgmtSettings.load()
        # Also mock model_validate to return the instance when called with test data
        def mock_model_validate(data, **kwargs):
            result = Mock()
            for attr, value in mock_settings_instance.__dict__.items():
                setattr(result, attr, value)
            # Handle special case for debug flag mapping
            if isinstance(data, dict) and "debug" in data and "enable_debug_mode" not in data:
                result.enable_debug_mode = bool(data["debug"])
            return result
        mock_settings_class.model_validate = mock_model_validate
        yield mock_settings_instance


# Async test timeout configuration
pytestmark = pytest.mark.asyncio(scope="function")
