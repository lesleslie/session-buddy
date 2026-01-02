"""Google Gemini API provider implementation.

This module provides the Gemini provider implementation using the Google
Generative AI SDK for chat completions and streaming.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from session_buddy.llm.base import LLMProvider
from session_buddy.llm.models import LLMMessage, LLMResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class GeminiProvider(LLMProvider):
    """Google Gemini API provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.default_model = config.get("default_model", "gemini-pro")
        self._client = None

    async def _get_client(self) -> Any:
        """Get or create Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self.api_key)
                self._client = genai
            except ImportError:
                msg = "Google Generative AI package not installed. Install with: pip install google-generativeai"
                raise ImportError(
                    msg,
                )
        return self._client

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert LLMMessage objects to Gemini format using modern pattern matching."""
        converted: list[dict[str, Any]] = []

        for msg in messages:
            match msg.role:
                case "system":
                    # Gemini doesn't have system role, prepend to first user message
                    if converted and converted[-1]["role"] == "user":
                        converted[-1]["parts"] = [
                            f"System: {msg.content}\n\nUser: {converted[-1]['parts'][0]}",
                        ]
                    else:
                        converted.append(
                            {"role": "user", "parts": [f"System: {msg.content}"]},
                        )
                case "user":
                    converted.append({"role": "user", "parts": [msg.content]})
                case "assistant":
                    converted.append({"role": "model", "parts": [msg.content]})
                case _:
                    # Unknown role - default to user for safety
                    converted.append({"role": "user", "parts": [msg.content]})

        return converted

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate response using Gemini API."""
        if not await self.is_available():
            msg = "Gemini provider not available"
            raise RuntimeError(msg)

        genai = await self._get_client()
        model_name = model or self.default_model

        try:
            model_instance = genai.GenerativeModel(model_name)

            # Convert messages to Gemini chat format
            chat_messages = self._convert_messages(messages)

            # Create chat or generate single response
            if len(chat_messages) > 1:
                chat = model_instance.start_chat(history=chat_messages[:-1])
                response = await chat.send_message_async(
                    chat_messages[-1]["parts"][0],
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                )
            else:
                response = await model_instance.generate_content_async(
                    chat_messages[0]["parts"][0],
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                )

            return LLMResponse(
                content=response.text,
                model=model_name,
                provider="gemini",
                usage={
                    "prompt_tokens": response.usage_metadata.prompt_token_count
                    if hasattr(response, "usage_metadata")
                    else 0,
                    "completion_tokens": response.usage_metadata.candidates_token_count
                    if hasattr(response, "usage_metadata")
                    else 0,
                    "total_tokens": response.usage_metadata.total_token_count
                    if hasattr(response, "usage_metadata")
                    else 0,
                },
                finish_reason="stop",  # Gemini doesn't provide detailed finish reasons
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            self.logger.exception(f"Gemini generation failed: {e}")
            raise

    async def stream_generate(  # type: ignore[override]
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Stream response using Gemini API."""
        if not await self.is_available():
            msg = "Gemini provider not available"
            raise RuntimeError(msg)

        genai = await self._get_client()
        model_name = model or self.default_model

        try:
            model_instance = genai.GenerativeModel(model_name)
            chat_messages = self._convert_messages(messages)

            if len(chat_messages) > 1:
                chat = model_instance.start_chat(history=chat_messages[:-1])
                response = chat.send_message(
                    chat_messages[-1]["parts"][0],
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                    stream=True,
                )
            else:
                response = model_instance.generate_content(
                    chat_messages[0]["parts"][0],
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                    stream=True,
                )

            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            self.logger.exception(f"Gemini streaming failed: {e}")
            raise

    async def is_available(self) -> bool:
        """Check if Gemini API is available."""
        if not self.api_key:
            return False

        try:
            genai = await self._get_client()
            # Test with a simple model list request
            list(genai.list_models())
            return True
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """Get available Gemini models."""
        return [
            "gemini-pro",
            "gemini-pro-vision",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro",
        ]
