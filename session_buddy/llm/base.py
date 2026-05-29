"""Abstract base class for LLM providers.

This module provides the base interface that all LLM provider implementations
must follow, ensuring consistent API across different providers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from session_buddy.llm.models import LLMMessage, LLMResponse


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = self.__class__.__name__.replace("Provider", "").lower()
        self.logger = logging.getLogger(f"llm_providers.{self.name}")

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response from the LLM."""

    @abstractmethod
    async def stream_generate(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Generate a streaming response from the LLM."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available and properly configured."""

    @abstractmethod
    def get_models(self) -> list[str]:
        """Get list of available models for this provider."""
