"""Anthropic API provider implementation (Claude models).

Uses anthropic.AsyncAnthropic client. Kept optional; if the package or
API key is unavailable, the provider reports as unavailable.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any

from session_buddy.llm.base import LLMProvider
from session_buddy.llm.models import LLMMessage, LLMResponse
from session_buddy.utils.time import utc_now

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _ensure_anthropic_module() -> ModuleType:
    """Ensure ``anthropic`` is importable even when the optional package
    is not installed.

    When the real ``anthropic`` package is missing, install a stub
    ``ModuleType`` in ``sys.modules`` with ``AsyncAnthropic = None`` so
    that ``unittest.mock.patch("anthropic.AsyncAnthropic", ...)`` can
    resolve the name. The stub's ``None`` attribute causes ``_get_client``
    to raise ``ImportError`` instead of attempting to call ``None(...)``.
    """
    if "anthropic" in sys.modules:
        return sys.modules["anthropic"]  # type: ignore[return-value]
    try:
        import anthropic as _real_anthropic  # noqa: F401 - side-effect: cache in sys.modules
    except ImportError:
        stub = ModuleType("anthropic")
        stub.AsyncAnthropic = None  # ty: ignore[unresolved-attribute]
        sys.modules["anthropic"] = stub
        return stub
    return sys.modules["anthropic"]  # type: ignore[return-value]


# Install the stub at import time so test patches can resolve the name.
_ensure_anthropic_module()


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url")
        self.default_model = config.get("default_model", "claude-3-5-haiku-20241022")
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError:  # pragma: no cover - stub prevents this in tests
                msg = "Anthropic package not installed. Install with: pip install anthropic"
                raise ImportError(msg)
            client_cls = getattr(anthropic, "AsyncAnthropic", None)
            if client_cls is None:
                msg = "Anthropic package not installed. Install with: pip install anthropic"
                raise ImportError(msg)
            self._client = client_cls(api_key=self.api_key, base_url=self.base_url)
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
                timestamp=utc_now().isoformat(),
            )
        except Exception:
            self.logger.exception("Anthropic generation failed")
            raise

    async def stream_generate(
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
        except Exception:  # noqa: BLE001 - is_available contract: any network/auth/SDK failure means "not available"
            return False

    def get_models(self) -> list[str]:
        return [
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
        ]
