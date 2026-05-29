"""Data models for LLM provider system.

This module provides standardized data models for LLM interactions including
messages, responses, streaming chunks, and generation options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StreamGenerationOptions:
    """Immutable streaming generation options."""

    provider: str | None = None
    model: str | None = None
    use_fallback: bool = True
    temperature: float = 0.7
    max_tokens: int | None = None


@dataclass
class StreamChunk:
    """Immutable streaming response chunk."""

    content: str = field(default="")
    is_error: bool = field(default=False)
    provider: str = field(default="")
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def content_chunk(cls, content: str, provider: str = "") -> StreamChunk:
        """Create content chunk."""
        return cls(content=content, provider=provider)

    @classmethod
    def error_chunk(cls, error: str) -> StreamChunk:
        """Create error chunk."""
        return cls(content="", is_error=True, metadata={"error": error})


@dataclass
class LLMMessage:
    """Standardized message format across LLM providers."""

    role: str  # 'system', 'user', 'assistant'
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class LLMResponse:
    """Standardized response format from LLM providers."""

    content: str
    model: str
    provider: str
    usage: dict[str, Any]
    finish_reason: str
    timestamp: str
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
