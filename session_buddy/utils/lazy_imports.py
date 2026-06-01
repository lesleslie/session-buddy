#!/usr/bin/env python3
"""Lazy loading utilities for optional dependencies.

This module provides lazy loading for heavy or optional dependencies to improve
startup performance and handle missing dependencies gracefully.
"""

import importlib
from collections.abc import Callable
from functools import wraps
from typing import Any, Never

from .logging import get_session_logger

# Lazy-load logger to avoid DI initialization issues during imports
_logger: Any = None


def _get_logger() -> Any:
    """Get logger instance, initializing on first use."""
    global _logger
    if _logger is None:
        try:
            _logger = get_session_logger()
        except Exception:
            # Fallback to basic logging if DI not initialized
            import logging

            _logger = logging.getLogger(__name__)
    return _logger


class LazyImport:
    """Lazy import wrapper that loads modules on first access."""

    def __init__(
        self,
        module_name: str,
        fallback_value: Any = None,
        import_error_msg: str | None = None,
    ) -> None:
        self.module_name = module_name
        self.fallback_value = fallback_value
        self.import_error_msg = import_error_msg
        self._module: Any = None
        self._import_attempted = False
        self._import_failed = False

    def __getattr__(self, name: str) -> Any:
        if not self._import_attempted:
            self._try_import()

        if self._import_failed:
            if self.fallback_value is not None:
                return getattr(self.fallback_value, name, None)
            raise ImportError(
                self.import_error_msg or f"Module {self.module_name} not available",
            )

        return getattr(self._module, name)

    def _try_import(self) -> None:
        """Attempt to import the module."""
        self._import_attempted = True
        try:
            self._module = importlib.import_module(self.module_name)
            _get_logger().debug(f"Successfully imported {self.module_name}")
        except ImportError as e:
            self._import_failed = True
            _get_logger().warning(f"Failed to import {self.module_name}: {e}")

    @property
    def available(self) -> bool:
        """Check if the module is available."""
        if not self._import_attempted:
            self._try_import()
        return not self._import_failed

    def __bool__(self) -> bool:
        if not self._import_attempted:
            self._try_import()
        return not self._import_failed


class LazyLoader:
    """Manages lazy loading of multiple optional dependencies."""

    def __init__(self) -> None:
        self._loaders: dict[str, LazyImport] = {}

    def add_import(
        self,
        name: str,
        module_name: str,
        fallback_value: Any = None,
        error_msg: str | None = None,
    ) -> LazyImport:
        """Add a lazy import."""
        loader = LazyImport(module_name, fallback_value, error_msg)
        self._loaders[name] = loader
        return loader

    def get_import(self, name: str) -> LazyImport | None:
        """Get a lazy import by name."""
        return self._loaders.get(name)

    def check_availability(self) -> dict[str, bool]:
        """Check availability of all registered imports."""
        return {name: loader.available for name, loader in self._loaders.items()}


# Global lazy loader instance
lazy_loader = LazyLoader()

# REMOVED: transformers and onnxruntime lazy imports
# These were used for local ONNX embedding models which have been replaced
# by HTTP-based embedding providers (llama-server/Ollama)
# Keeping tiktoken, duckdb, numpy which are still needed

tiktoken = lazy_loader.add_import(
    "tiktoken",
    "tiktoken",
    error_msg="tiktoken not available. Install with: uv sync --extra embeddings",
)

duckdb = lazy_loader.add_import(
    "duckdb",
    "duckdb",
    error_msg="DuckDB not available. Install with: uv add duckdb",
)

numpy = lazy_loader.add_import(
    "numpy",
    "numpy",
    error_msg="NumPy not available. Install with: uv sync --extra embeddings",
)


def require_dependency(
    dependency_name: str,
    install_hint: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to require a specific dependency for a function."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            loader = lazy_loader.get_import(dependency_name)
            if not loader or not loader.available:
                error_msg = f"Function {func.__name__} requires {dependency_name}"
                if install_hint:
                    error_msg += f". Install with: {install_hint}"
                raise ImportError(error_msg)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def optional_dependency(
    dependency_name: str,
    fallback_result: Any = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to handle optional dependencies gracefully."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            loader = lazy_loader.get_import(dependency_name)
            if not loader or not loader.available:
                _get_logger().info(
                    f"Function {func.__name__} skipped - {dependency_name} not available",
                )
                return fallback_result
            return func(*args, **kwargs)

        return wrapper

    return decorator


class MockModule:
    """Mock module that provides fallback implementations."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, name: str) -> Callable[..., Never]:
        def mock_function(*args: Any, **kwargs: Any) -> Never:
            msg = f"Mock function {name} called - {self.name} not available"
            raise ImportError(
                msg,
            )

        return mock_function


def create_embedding_mock() -> Any:
    """Create a mock for embedding functionality."""

    class MockEmbedding:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def encode(
            self,
            texts: str | list[str],
            *args: Any,
            **kwargs: Any,
        ) -> list[list[float]]:
            # Return random-like embeddings for testing (using secrets for security)
            import secrets

            def _random_float() -> float:
                """Generate a secure random float between 0 and 1."""
                return secrets.randbelow(1000000) / 1000000.0

            if isinstance(texts, str):
                return [[_random_float() for _ in range(384)]]
            return [[_random_float() for _ in range(384)] for _ in texts]

    return MockEmbedding


def get_dependency_status() -> dict[str, dict[str, Any]]:
    """Get comprehensive status of all dependencies."""
    status: dict[str, dict[str, Any]] = {}

    # Check core dependencies
    core_deps = ["duckdb"]
    for dep in core_deps:
        loader = lazy_loader.get_import(dep)
        status[dep] = {
            "available": loader.available if loader else False,
            "required": True,
            "category": "core",
        }

    # Check optional dependencies
    optional_deps = ["tiktoken", "numpy"]  # transformers/onnxruntime removed — using HTTP providers
    for dep in optional_deps:
        loader = lazy_loader.get_import(dep)
        status[dep] = {
            "available": loader.available if loader else False,
            "required": False,
            "category": "optimization",
        }

    # Overall status
    core_available = all(status[dep]["available"] for dep in core_deps)
    # embeddings now served via HTTP (llama-server/Ollama) — always "available"
    embeddings_available = True

    status["_summary"] = {
        "core_functionality": core_available,
        "embedding_functionality": embeddings_available,
        "optimization_functionality": status["tiktoken"]["available"],
        "overall_health": core_available,
    }

    return status


def log_dependency_status() -> None:
    """Log the current dependency status."""
    status = get_dependency_status()
    summary = status["_summary"]

    _get_logger().info(
        "Dependency status check completed",
        core_functionality=summary["core_functionality"],
        embedding_functionality=summary["embedding_functionality"],
        optimization_functionality=summary["optimization_functionality"],
    )

    # Log missing dependencies
    missing_core = [dep for dep in ("duckdb",) if not status[dep]["available"]]
    missing_optional = [
        dep
        for dep in ("tiktoken", "numpy")
        if not status[dep]["available"]
    ]

    if missing_core:
        _get_logger().warning("Missing core dependencies", missing=missing_core)

    if missing_optional:
        _get_logger().info(
            "Missing optional dependencies",
            missing=missing_optional,
            install_hint="uv sync --extra embeddings",
        )


# Note: Dependency status logging should be called explicitly
# to avoid import-time issues. Call log_dependency_status() when needed.
