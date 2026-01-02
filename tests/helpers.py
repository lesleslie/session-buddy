#!/usr/bin/env python3
"""Shared test utilities and helpers for session-mgmt-mcp tests."""

import asyncio
import os
import tempfile
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import duckdb
import numpy as np
import pytest
from session_buddy.reflection_tools import ReflectionDatabase


class TestDataFactory:
    """Factory for generating test data with realistic patterns."""

    @staticmethod
    def conversation(
        content: str | None = None,
        project: str = "test-project",
        timestamp: datetime | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate test conversation data."""
        import uuid

        return {
            "id": conversation_id or str(uuid.uuid4()),
            "content": content or f"Test conversation at {datetime.now()}",
            "project": project,
            "timestamp": timestamp or datetime.now(UTC),
        }

    @staticmethod
    def reflection(
        content: str | None = None,
        tags: list[str] | None = None,
        reflection_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate test reflection data."""
        import uuid

        return {
            "id": reflection_id or str(uuid.uuid4()),
            "content": content or f"Test reflection at {datetime.now()}",
            "tags": tags if tags is not None else ["test", "example"],
        }

    @staticmethod
    def search_result(
        content: str = "Test search result",
        score: float = 0.85,
        project: str = "test-project",
    ) -> dict[str, Any]:
        """Generate test search result."""
        return {
            "content": content,
            "score": score,
            "project": project,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def bulk_conversations(
        count: int = 10,
        project: str = "test-project",
    ) -> list[dict[str, Any]]:
        """Generate bulk test conversations."""
        return [
            TestDataFactory.conversation(
                content=f"Bulk conversation {i}",
                project=project,
            )
            for i in range(count)
        ]

    @staticmethod
    def bulk_reflections(
        count: int = 10,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate bulk test reflections."""
        return [
            TestDataFactory.reflection(
                content=f"Bulk reflection {i}",
                tags=tags or [f"bulk-tag-{i % 3}", "test"],
            )
            for i in range(count)
        ]

    @staticmethod
    def realistic_reflections(
        count: int = 10,
        project: str = "realistic-project",
    ) -> list[dict[str, Any]]:
        """Generate realistic reflection data with varied content and structure."""
        realistic_contents = [
            "Implemented the new authentication system with JWT tokens",
            "Fixed memory leak in the database connection pool",
            "Optimized query performance by adding proper indexes",
            "Refactored the user service to use dependency injection",
            "Added comprehensive error handling for API endpoints",
            "Implemented caching layer using Redis for better performance",
            "Fixed race condition in the concurrent file processing",
            "Added unit tests for the payment processing module",
            "Integrated third-party analytics service successfully",
            "Migrated legacy code to use async/await pattern",
            "Implemented proper logging and monitoring for production",
            "Fixed security vulnerability in user input validation",
            "Optimized database schema for better query performance",
            "Added comprehensive API documentation using Swagger",
            "Implemented proper error handling for network operations",
        ]

        realistic_tags = [
            ["backend", "authentication", "security"],
            ["performance", "memory", "bugfix"],
            ["database", "optimization", "query"],
            ["refactoring", "architecture", "clean-code"],
            ["error-handling", "robustness", "api"],
            ["caching", "performance", "redis"],
            ["concurrency", "race-condition", "bugfix"],
            ["testing", "unit-tests", "quality"],
            ["integration", "third-party", "analytics"],
            ["modernization", "async", "legacy"],
            ["monitoring", "logging", "production"],
            ["security", "vulnerability", "input-validation"],
            ["database", "schema", "optimization"],
            ["documentation", "api", "swagger"],
            ["network", "error-handling", "robustness"],
        ]

        reflections = []
        for i in range(count):
            content = realistic_contents[i % len(realistic_contents)]
            tags = realistic_tags[i % len(realistic_tags)]

            # Add some variation to make content more realistic
            if i < len(realistic_contents):
                content = f"{content} - variation {i}"

            reflections.append(
                TestDataFactory.reflection(
                    content=content,
                    tags=[*tags, "realistic"],
                )
            )

        return reflections

    @staticmethod
    def project_based_reflections(
        projects: list[str],
        reflections_per_project: int = 5,
    ) -> list[dict[str, Any]]:
        """Generate reflections organized by projects."""
        reflections = []

        project_themes = {
            "backend": ["API", "database", "authentication", "performance"],
            "frontend": ["UI", "UX", "components", "responsive"],
            "mobile": ["iOS", "Android", "cross-platform", "performance"],
            "data-science": ["ML", "data-processing", "visualization", "statistics"],
            "devops": ["CI/CD", "infrastructure", "monitoring", "scaling"],
        }

        for project in projects:
            # Determine project type or use generic
            project_type = "generic"
            for theme, keywords in project_themes.items():
                if any(keyword.lower() in project.lower() for keyword in keywords):
                    project_type = theme
                    break

            for i in range(reflections_per_project):
                if project_type == "backend":
                    content = (
                        f"Backend work on {project}: implemented {i + 1} API endpoints"
                    )
                    tags = ["backend", "api", project.lower().replace(" ", "-")]
                elif project_type == "frontend":
                    content = (
                        f"Frontend work on {project}: created {i + 1} new components"
                    )
                    tags = ["frontend", "ui", project.lower().replace(" ", "-")]
                elif project_type == "mobile":
                    content = (
                        f"Mobile work on {project}: implemented {i + 1} new screens"
                    )
                    tags = ["mobile", "ui", project.lower().replace(" ", "-")]
                elif project_type == "data-science":
                    content = (
                        f"Data science work on {project}: processed {i + 1} datasets"
                    )
                    tags = ["data", "ml", project.lower().replace(" ", "-")]
                elif project_type == "devops":
                    content = (
                        f"DevOps work on {project}: configured {i + 1} CI/CD pipelines"
                    )
                    tags = ["devops", "ci-cd", project.lower().replace(" ", "-")]
                else:
                    content = f"Work on {project}: completed task {i + 1}"
                    tags = ["generic", project.lower().replace(" ", "-")]

                reflections.append(
                    TestDataFactory.reflection(
                        content=content,
                        tags=tags,
                    )
                )

        return reflections

    @staticmethod
    def time_based_reflections(
        count: int = 10,
        project: str = "time-based-project",
    ) -> list[dict[str, Any]]:
        """Generate reflections with time-based content and timestamps."""
        from datetime import datetime, timedelta

        reflections = []
        base_time = datetime.now()

        for i in range(count):
            # Generate time-based content
            hours_ago = count - i
            content = f"Completed task {i + 1} - {hours_ago} hours ago"

            # Create timestamp that decreases as we go back in time
            timestamp = base_time - timedelta(hours=hours_ago)

            reflections.append(
                TestDataFactory.reflection(
                    content=content,
                    tags=["time-based", "task", f"priority-{i % 3 + 1}"],
                    timestamp=timestamp,
                )
            )

        return reflections

    @staticmethod
    def error_scenario_reflections(
        count: int = 5,
        project: str = "error-scenario-project",
    ) -> list[dict[str, Any]]:
        """Generate reflections representing various error scenarios."""
        error_scenarios = [
            "Encountered NullPointerException in user service",
            "Database connection timeout during peak load",
            "Memory overflow when processing large files",
            "Race condition detected in concurrent operations",
            "Invalid input data causing parsing errors",
            "Network timeout when calling external API",
            "Permission denied when accessing restricted resources",
            "Configuration error in production environment",
            "Deadlock situation in multi-threaded processing",
            "Resource leak detected in file handling",
        ]

        error_tags = [
            ["error", "null-pointer", "critical"],
            ["error", "database", "timeout", "performance"],
            ["error", "memory", "overflow", "critical"],
            ["error", "concurrency", "race-condition", "bug"],
            ["error", "input-validation", "data", "bug"],
            ["error", "network", "timeout", "external"],
            ["error", "security", "permission", "access"],
            ["error", "configuration", "environment", "setup"],
            ["error", "concurrency", "deadlock", "critical"],
            ["error", "resource", "leak", "memory"],
        ]

        reflections = []
        for i in range(count):
            content = error_scenarios[i % len(error_scenarios)]
            tags = error_tags[i % len(error_tags)] + ["error-scenario"]

            reflections.append(
                TestDataFactory.reflection(
                    content=content,
                    tags=tags,
                )
            )

        return reflections

    @staticmethod
    def realistic_project_structure_with_content(base_path: Path) -> dict[str, Any]:
        """Create a realistic project structure with actual content for testing."""
        import json

        # Create basic structure
        project_files = TestDataFactory.realistic_project_structure(base_path)

        # Add more realistic content to files
        project_files["pyproject.toml"].write_text(
            """[project]
name = "advanced-test-project"
version = "1.2.3"
description = "A comprehensive test project for session management"
authors = [
    {name = "Test Developer", email = "test@example.com"}
]
dependencies = [
    "pytest>=7.0",
    "hypothesis>=6.0",
    "duckdb>=0.10"
]

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
python_files = "test_*.py"
"""
        )

        project_files["README.md"].write_text(
            """# Advanced Test Project

This is a comprehensive test project demonstrating various features and components.

## Features

- **Database Integration**: DuckDB for efficient data storage
- **Testing Framework**: Pytest with Hypothesis for property-based testing
- **Async Support**: Full async/await pattern implementation
- **Error Handling**: Comprehensive error handling and validation

## Installation

```bash
pip install advanced-test-project
```

## Usage

```python
from advanced_test_project import main
main()
```
"""
        )

        # Create more realistic source files
        (project_files["src"] / "database.py").write_text(
            '''"""Database module for advanced test project."""

import duckdb
from typing import Optional, List, Dict, Any

class Database:
    """Database connection and operations."""

    def __init__(self, path: str):
        self.path = path
        self.conn = None

    def connect(self) -> None:
        """Establish database connection."""
        self.conn = duckdb.connect(self.path)

    def disconnect(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute_query(self, query: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
        """Execute SQL query and return results."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        if params:
            result = self.conn.execute(query, params).fetchall()
        else:
            result = self.conn.execute(query).fetchall()

        return [dict(row) for row in result]
'''
        )

        # Create realistic test files
        (project_files["tests"] / "test_database.py").write_text(
            '''"""Tests for database module."""

import tempfile
from pathlib import Path
import pytest
from src.database import Database


class TestDatabase:
    """Test database operations."""

    def test_connect_disconnect(self):
        """Test database connection lifecycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(str(db_path))

            # Test connection
            db.connect()
            assert db.conn is not None

            # Test disconnection
            db.disconnect()
            assert db.conn is None

    def test_query_execution(self):
        """Test query execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(str(db_path))
            db.connect()

            try:
                # Create table
                db.execute_query("CREATE TABLE test (id INTEGER, name VARCHAR)")

                # Insert data
                db.execute_query("INSERT INTO test VALUES (1, 'test')")

                # Query data
                results = db.execute_query("SELECT * FROM test")
                assert len(results) == 1
                assert results[0]["name"] == "test"

            finally:
                db.disconnect()
'''
        )

        # Create configuration file
        (base_path / "config.json").write_text(
            json.dumps(
                {
                    "database": {
                        "path": "./data/database.db",
                        "timeout": 30,
                        "max_connections": 10,
                    },
                    "logging": {
                        "level": "INFO",
                        "file": "./logs/app.log",
                        "max_size": "10MB",
                        "backup_count": 5,
                    },
                    "features": {
                        "enable_caching": True,
                        "cache_ttl": 3600,
                        "enable_metrics": True,
                        "metrics_port": 8080,
                    },
                },
                indent=2,
            )
        )

        return {
            **project_files,
            "config.json": base_path / "config.json",
        }

    @staticmethod
    def realistic_project_structure(base_path: Path) -> dict[str, Path]:
        """Create a realistic project structure for testing."""
        project_files = {
            "pyproject.toml": base_path / "pyproject.toml",
            "README.md": base_path / "README.md",
            "src": base_path / "src",
            "tests": base_path / "tests",
            "docs": base_path / "docs",
        }

        # Create directories
        project_files["src"].mkdir(parents=True, exist_ok=True)
        project_files["tests"].mkdir(parents=True, exist_ok=True)
        project_files["docs"].mkdir(parents=True, exist_ok=True)

        # Create files with realistic content
        project_files["pyproject.toml"].write_text(
            '[project]\nname = "test-project"\nversion = "0.1.0"\n'
        )
        project_files["README.md"].write_text(
            "# Test Project\n\nThis is a test project."
        )

        # Create a source file
        (project_files["src"] / "main.py").write_text(
            'def main():\n    print("Hello, world!")\n'
        )

        # Create a test file
        (project_files["tests"] / "test_main.py").write_text(
            "def test_main():\n    assert True\n"
        )

        return project_files


class AsyncTestHelper:
    """Helper utilities for async testing."""

    @staticmethod
    async def wait_for_condition(
        condition_func,
        timeout: float = 5.0,
        interval: float = 0.1,
    ) -> bool:
        """Wait for a condition to become true with timeout."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            if (
                await condition_func()
                if asyncio.iscoroutinefunction(condition_func)
                else condition_func()
            ):
                return True
            await asyncio.sleep(interval)
        return False

    @staticmethod
    async def collect_async_results(async_gen, limit: int = 100) -> list[Any]:
        """Collect results from async generator with limit."""
        results = []
        async for item in async_gen:
            results.append(item)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def create_mock_coro(return_value: Any = None) -> AsyncMock:
        """Create a properly configured async mock."""
        mock = AsyncMock()
        mock.return_value = return_value
        return mock


class DatabaseTestHelper:
    """Helper utilities for database testing."""

    @staticmethod
    @asynccontextmanager
    async def temp_reflection_db() -> AsyncGenerator[ReflectionDatabase]:
        """Create temporary ReflectionDatabase for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.duckdb"

            db = ReflectionDatabase(db_path=str(db_path))
            try:
                await db.initialize()
                yield db
            finally:
                db.close()

    @staticmethod
    async def populate_test_data(
        db: ReflectionDatabase,
        num_conversations: int = 5,
        num_reflections: int = 3,
    ) -> dict[str, list[str]]:
        """Populate database with test data."""
        conversation_ids = []
        reflection_ids = []

        # Add conversations
        for i in range(num_conversations):
            conv_data = TestDataFactory.conversation(
                content=f"Test conversation {i}",
                project="test-project",
            )
            conv_id = await db.store_conversation(
                conv_data["content"],
                {"project": conv_data["project"]},
            )
            conversation_ids.append(conv_id)

        # Add reflections
        for i in range(num_reflections):
            refl_data = TestDataFactory.reflection(
                content=f"Test reflection {i}",
                tags=["test", f"tag{i}"],
            )
            refl_id = await db.store_reflection(
                refl_data["content"],
                refl_data["tags"],
            )
            reflection_ids.append(refl_id)

        return {
            "conversations": conversation_ids,
            "reflections": reflection_ids,
        }

    @staticmethod
    def verify_table_structure(
        conn: duckdb.DuckDBPyConnection, table_name: str
    ) -> dict[str, str]:
        """Verify table structure and return column info."""
        result = conn.execute(f"DESCRIBE {table_name}").fetchall()
        return {row[0]: row[1] for row in result}  # column_name: column_type

    @staticmethod
    async def measure_query_performance(
        db: ReflectionDatabase,
        query_func,
        *args,
        **kwargs,
    ) -> dict[str, float]:
        """Measure query performance."""
        start_time = time.perf_counter()
        result = await query_func(*args, **kwargs)
        end_time = time.perf_counter()

        return {
            "execution_time": end_time - start_time,
            "result_count": len(result) if isinstance(result, list) else 1,
        }


class MockingHelper:
    """Helper utilities for mocking in tests."""

    @staticmethod
    def mock_embedding_system():
        """Create comprehensive mock for embedding system."""
        mocks = {}

        # Mock ONNX session
        mock_onnx = Mock()
        rng = np.random.default_rng(42)
        mock_onnx.run.return_value = [rng.random((1, 384)).astype(np.float32)]
        mocks["onnx_session"] = mock_onnx

        # Mock tokenizer
        mock_tokenizer = Mock()
        mock_tokenizer.return_value = {
            "input_ids": [[1, 2, 3, 4, 5]],
            "attention_mask": [[1, 1, 1, 1, 1]],
        }
        mocks["tokenizer"] = mock_tokenizer

        return mocks

    @staticmethod
    def mock_onnx_session_with_specific_return(return_value: np.ndarray | None = None):
        """Create ONNX session mock with specific return value."""
        mock_onnx = Mock()
        if return_value is None:
            rng = np.random.default_rng(42)
            return_value = rng.random((1, 384)).astype(np.float32)
        mock_onnx.run.return_value = [return_value]
        return mock_onnx

    @staticmethod
    @asynccontextmanager
    async def mock_mcp_server():
        """Create mock MCP server context manager."""
        from fastmcp import FastMCP

        server = Mock(spec=FastMCP)
        server.tool = Mock()
        server.prompt = Mock()
        server.__aenter__ = AsyncMock(return_value=server)
        server.__aexit__ = AsyncMock(return_value=None)

        yield server

    @staticmethod
    def patch_environment(**env_vars) -> patch:
        """Create environment variable patch."""
        return patch.dict(os.environ, env_vars)

    @staticmethod
    def patch_file_operations():
        """Create comprehensive file operations patch."""
        return patch.multiple(
            "pathlib.Path",
            mkdir=Mock(),
            exists=Mock(return_value=True),
            unlink=Mock(),
        )

    @staticmethod
    def patch_system_dependencies():
        """Create patches for system dependencies that might not be available."""
        return patch.multiple(
            "session_buddy.reflection_tools",
            ONNX_AVAILABLE=True,  # Default to True for tests
        )


class ChaosTestHelper:
    """Helper utilities for chaos engineering tests."""

    @staticmethod
    async def simulate_network_failure():
        """Simulate network failure for testing resilience."""
        from unittest.mock import Mock

        import httpx

        mock_client = Mock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        return mock_client

    @staticmethod
    async def simulate_database_failure():
        """Simulate database failure for testing error handling."""
        from unittest.mock import MagicMock, Mock

        mock_db = Mock()
        mock_db.store_conversation = AsyncMock(
            side_effect=Exception("Database unavailable")
        )
        mock_db.search_conversations = AsyncMock(
            side_effect=Exception("Database unavailable")
        )

        return mock_db

    @staticmethod
    async def simulate_resource_exhaustion():
        """Simulate resource exhaustion (memory, CPU)."""
        # This would be used in context managers to temporarily trigger resource exhaustion
        return Mock()


class PropertyTestHelper:
    """Helper utilities for property-based testing with Hypothesis."""

    @staticmethod
    def validate_conversation_structure(conversation: dict[str, Any]) -> bool:
        """Validate conversation structure for property tests."""
        required_keys = {"id", "content", "project", "timestamp"}
        return (
            isinstance(conversation, dict)
            and required_keys.issubset(conversation.keys())
            and isinstance(conversation["id"], str)
            and len(conversation["id"]) > 10  # At least UUID length
            and isinstance(conversation["content"], str)
            and isinstance(conversation["project"], str)
        )

    @staticmethod
    def validate_reflection_structure(reflection: dict[str, Any]) -> bool:
        """Validate reflection structure for property tests."""
        required_keys = {"id", "content", "tags"}
        return (
            isinstance(reflection, dict)
            and required_keys.issubset(reflection.keys())
            and isinstance(reflection["id"], str)
            and isinstance(reflection["content"], str)
            and isinstance(reflection["tags"], list)
            and all(isinstance(tag, str) for tag in reflection["tags"])
        )

    @staticmethod
    def validate_similarity_range(score: float) -> bool:
        """Validate similarity score is in valid range [0, 1]."""
        return 0.0 <= score <= 1.0


class AssertionHelper:
    """Helper utilities for test assertions."""

    @staticmethod
    def assert_valid_uuid(value: str) -> None:
        """Assert that value is a valid UUID."""
        import uuid

        try:
            uuid.UUID(value)
        except ValueError as e:
            msg = f"Expected valid UUID, got: {value} - {e}"
            raise AssertionError(msg)

    @staticmethod
    def assert_valid_timestamp(value: str) -> None:
        """Assert that value is a valid ISO timestamp."""
        try:
            datetime.fromisoformat(value)
        except ValueError as e:
            msg = f"Expected valid timestamp, got: {value} - {e}"
            raise AssertionError(msg)

    @staticmethod
    def assert_embedding_shape(embedding: np.ndarray, expected_dim: int = 384) -> None:
        """Assert embedding has correct shape."""
        assert embedding.shape == (expected_dim,), (
            f"Expected shape ({expected_dim},), got {embedding.shape}"
        )
        assert embedding.dtype == np.float32, f"Expected float32, got {embedding.dtype}"

    @staticmethod
    def assert_similarity_score(score: float) -> None:
        """Assert similarity score is in valid range."""
        assert 0.0 <= score <= 1.0, f"Similarity score should be in [0,1], got {score}"

    @staticmethod
    def assert_database_record(
        record: dict[str, Any], expected_fields: list[str]
    ) -> None:
        """Assert database record has expected fields."""
        for field in expected_fields:
            assert field in record, f"Record missing field: {field}"
            assert record[field] is not None, f"Field {field} should not be None"


class PerformanceHelper:
    """Helper utilities for performance testing."""

    @staticmethod
    @asynccontextmanager
    async def measure_time():
        """Context manager to measure execution time."""
        start_time = time.perf_counter()
        measurements = {"start_time": start_time}

        yield measurements

        end_time = time.perf_counter()
        measurements.update(
            {
                "end_time": end_time,
                "duration": end_time - start_time,
            }
        )

    @staticmethod
    def assert_performance_threshold(
        actual_time: float,
        threshold: float,
        operation_name: str = "operation",
    ) -> None:
        """Assert operation completed within time threshold."""
        assert actual_time <= threshold, (
            f"{operation_name} took {actual_time:.3f}s, expected <= {threshold:.3f}s"
        )

    @staticmethod
    async def benchmark_async_operation(
        operation,
        iterations: int = 100,
        *args,
        **kwargs,
    ) -> dict[str, float]:
        """Benchmark async operation multiple times."""
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            await operation(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        return {
            "mean": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
            "total": sum(times),
        }

    @staticmethod
    def calculate_performance_stats(times: list[float]) -> dict[str, float]:
        """Calculate comprehensive performance statistics."""
        if not times:
            return {}

        return {
            "count": len(times),
            "mean": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
            "total": sum(times),
            "std_dev": (
                sum((t - sum(times) / len(times)) ** 2 for t in times) / len(times)
            )
            ** 0.5
            if len(times) > 1
            else 0.0,
            "p95": sorted(times)[int(0.95 * len(times))] if times else 0,
        }


class ValidationHelper:
    """Helper utilities for data validation testing."""

    @staticmethod
    def validate_json_serializable(obj: Any) -> bool:
        """Check if an object is JSON serializable."""
        import json

        try:
            json.loads(json.dumps(obj, default=str))
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def validate_uuid_format(uuid_str: str) -> bool:
        """Validate UUID format."""
        import uuid

        try:
            uuid.UUID(uuid_str)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_iso_datetime_format(datetime_str: str) -> bool:
        """Validate ISO datetime format."""
        from datetime import datetime

        try:
            datetime.fromisoformat(datetime_str)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_email_format(email: str) -> bool:
        """Basic email format validation."""
        import re

        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def validate_url_format(url: str) -> bool:
        """Basic URL format validation."""
        import re

        pattern = r"^https?://(?:[-\w.])+(?:\:[0-9]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:\#(?:[\w.])*)?)?$"
        return re.match(pattern, url) is not None


class TestCoverageHelper:
    """Helper utilities for improving test coverage."""

    @staticmethod
    def get_uncovered_methods(class_or_module) -> list[str]:
        """Get methods that might need more test coverage."""
        uncovered = []

        for name in dir(class_or_module):
            attr = getattr(class_or_module, name)
            if callable(attr) and not name.startswith("_"):
                # This is a simplified check - in practice, you'd use coverage data
                uncovered.append(name)

        return uncovered

    @staticmethod
    def generate_edge_case_inputs() -> list[Any]:
        """Generate common edge case inputs for testing."""
        return [
            None,
            "",
            0,
            [],
            {},
            -1,
            float("inf"),
            float("-inf"),
            float("nan"),
            "   ",  # whitespace only
            "a" * 10000,  # very long string
        ]


# Pytest fixtures using helpers
@pytest.fixture
def test_data_factory():
    """Provide TestDataFactory instance."""
    return TestDataFactory


@pytest.fixture
def validation_helper():
    """Provide ValidationHelper instance."""
    return ValidationHelper


@pytest.fixture
def chaos_helper():
    """Provide ChaosTestHelper instance."""
    return ChaosTestHelper


@pytest.fixture
def property_helper():
    """Provide PropertyTestHelper instance."""
    return PropertyTestHelper


@pytest.fixture
def coverage_helper():
    """Provide TestCoverageHelper instance."""
    return TestCoverageHelper


@pytest.fixture
def async_helper():
    """Provide AsyncTestHelper instance."""
    return AsyncTestHelper


@pytest.fixture
def db_helper():
    """Provide DatabaseTestHelper instance."""
    return DatabaseTestHelper


@pytest.fixture
def mock_helper():
    """Provide MockingHelper instance."""
    return MockingHelper


@pytest.fixture
def assert_helper():
    """Provide AssertionHelper instance."""
    return AssertionHelper


@pytest.fixture
def perf_helper():
    """Provide PerformanceHelper instance."""
    return PerformanceHelper


@pytest.fixture
def db_helper():
    """Provide DatabaseTestHelper instance."""
    return DatabaseTestHelper


@pytest.fixture
def mock_helper():
    """Provide MockingHelper instance."""
    return MockingHelper


@pytest.fixture
def assert_helper():
    """Provide AssertionHelper instance."""
    return AssertionHelper


@pytest.fixture
def perf_helper():
    """Provide PerformanceHelper instance."""
    return PerformanceHelper


# Common test decorators
def requires_embeddings(test_func):
    """Decorator to skip test if embeddings not available."""
    return pytest.mark.skipif(
        not hasattr(test_func, "__module__") or "ONNX_AVAILABLE" not in dir(),
        reason="Embeddings not available",
    )(test_func)


def async_timeout(seconds: float = 30.0):
    """Decorator to add timeout to async test."""

    def decorator(test_func):
        return pytest.mark.timeout(seconds)(test_func)

    return decorator


def performance_test(baseline_key: str):
    """Decorator to mark performance test with baseline."""

    def decorator(test_func):
        return pytest.mark.performance(
            pytest.mark.parametrize("baseline_key", [baseline_key])
        )(test_func)

    return decorator
