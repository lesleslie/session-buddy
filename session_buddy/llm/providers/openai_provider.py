"""OpenAI API provider implementation.

This module provides the OpenAI provider implementation using the official
OpenAI Python SDK for chat completions and streaming.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from session_buddy.llm.base import LLMProvider
from session_buddy.llm.models import LLMMessage, LLMResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.default_model = config.get("default_model", "gpt-4")
        self._client: Any = None

    async def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            try:
                import openai

                self._client = openai.AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                msg = "OpenAI package not installed. Install with: pip install openai"
                raise ImportError(
                    msg,
                )
        return self._client

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, str]]:
        """Convert LLMMessage objects to OpenAI format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate response using OpenAI API."""
        if not await self.is_available():
            msg = "OpenAI provider not available"
            raise RuntimeError(msg)

        client = await self._get_client()
        model_name = model or self.default_model

        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=self._convert_messages(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                model=model_name,
                provider="openai",
                usage={
                    "prompt_tokens": response.usage.prompt_tokens
                    if response.usage
                    else 0,
                    "completion_tokens": response.usage.completion_tokens
                    if response.usage
                    else 0,
                    "total_tokens": response.usage.total_tokens
                    if response.usage
                    else 0,
                },
                finish_reason=response.choices[0].finish_reason,
                timestamp=datetime.now().isoformat(),
                metadata={"response_id": response.id},
            )

        except Exception as e:
            self.logger.exception(f"OpenAI generation failed: {e}")
            raise

    async def stream_generate(  # type: ignore[override]
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Stream response using OpenAI API."""
        if not await self.is_available():
            msg = "OpenAI provider not available"
            raise RuntimeError(msg)

        client = await self._get_client()
        model_name = model or self.default_model

        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=self._convert_messages(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs,
            )

            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self.logger.exception(f"OpenAI streaming failed: {e}")
            raise

    async def is_available(self) -> bool:
        """Check if OpenAI API is available."""
        if not self.api_key:
            return False

        try:
            client = await self._get_client()
            # Test with a simple request
            await client.models.list()
            return True
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """Get available OpenAI models."""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
        ]
