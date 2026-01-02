"""Anthropic API provider implementation (Claude models).

Uses anthropic.AsyncAnthropic client. Kept optional; if the package or
API key is unavailable, the provider reports as unavailable.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from session_buddy.llm.base import LLMProvider
from session_buddy.llm.models import LLMMessage, LLMResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.default_model = config.get("default_model", "claude-3-5-haiku-20241022")
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except ImportError:  # pragma: no cover - optional dependency
                msg = "Anthropic package not installed. Install with: pip install anthropic"
                raise ImportError(msg)
        return self._client

    def _strip_thinking_blocks(self, content: str) -> str:
        """Remove thinking blocks from content before sending to API.

        Anthropic API does not accept thinking blocks in request messages.
        They can only appear in responses from the API.
        """
        import re

        # Remove all <thinking>...</thinking> blocks (with any attributes)
        pattern = r"<thinking[^>]*>.*?</thinking>"
        cleaned = re.sub(pattern, "", content, flags=re.DOTALL | re.IGNORECASE)
        return cleaned.strip()

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert to Anthropic messages format.

        - Maps 'system' into top-level system field (handled in generate)
        - Converts user/assistant into human/assistant messages
        - Strips thinking blocks from assistant messages (not allowed in API requests)
        """
        converted: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "user":
                converted.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                # Remove thinking blocks - they cannot be in API requests
                cleaned_content = self._strip_thinking_blocks(msg.content)
                if cleaned_content:  # Only add if there's content left after stripping
                    converted.append({"role": "assistant", "content": cleaned_content})
            # 'system' is handled separately
        return converted

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if not await self.is_available():
            msg = "Anthropic provider not available"
            raise RuntimeError(msg)

        client = await self._get_client()
        model_name = model or self.default_model

        # Extract a system prompt if present
        system_parts = [m.content for m in messages if m.role == "system"]
        system_prompt = "\n\n".join(system_parts) if system_parts else None
        converted = self._convert_messages(messages)

        try:
            resp = await client.messages.create(
                model=model_name,
                system=system_prompt,
                messages=converted,
                temperature=temperature,
                max_tokens=max_tokens or 1024,
            )

            text = "".join(
                [
                    block.text
                    for block in resp.content
                    if hasattr(block, "text") and isinstance(block.text, str)
                ]
            )
            usage = getattr(resp, "usage", None)
            return LLMResponse(
                content=text,
                model=model_name,
                provider="anthropic",
                usage={
                    "prompt_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
                    "completion_tokens": getattr(usage, "output_tokens", 0)
                    if usage
                    else 0,
                    "total_tokens": (
                        getattr(usage, "input_tokens", 0)
                        + getattr(usage, "output_tokens", 0)
                        if usage
                        else 0
                    ),
                },
                finish_reason="stop",
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            self.logger.exception(f"Anthropic generation failed: {e}")
            raise

    async def stream_generate(  # type: ignore[override]
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        # Streaming not essential for extraction; implement later as needed
        raise NotImplementedError

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            await self._get_client()
            return True
        except Exception:
            return False

    def get_models(self) -> list[str]:
        return [
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
        ]
