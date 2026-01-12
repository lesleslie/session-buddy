"""Ollama local LLM provider implementation.

This module provides the Ollama provider implementation using the mcp-common
HTTPClientAdapter for connection pooling and aiohttp fallback for HTTP communications.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from session_buddy.llm.base import LLMProvider
from session_buddy.llm.models import LLMMessage, LLMResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from session_buddy.di.container import depends

# mcp-common HTTP client adapter (httpx based)
try:
    from mcp_common.adapters.http.client import HTTPClientAdapter

    from session_buddy.di.container import depends

    HTTP_ADAPTER_AVAILABLE = True
except Exception:
    HTTPClientAdapter = None  # type: ignore[assignment]
    HTTP_ADAPTER_AVAILABLE = False


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider using HTTPClientAdapter for connection pooling."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.default_model = config.get("default_model", "llama2")
        self._available_models: list[str] = []

        # Initialize HTTP client adapter if available
        self._http_adapter = None
        if HTTP_ADAPTER_AVAILABLE and HTTPClientAdapter is not None:
            try:
                self._http_adapter = depends.get_sync(HTTPClientAdapter)
            except Exception:
                self._http_adapter = None

    async def _make_api_request(
        self,
        endpoint: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Make API request to Ollama service with connection pooling."""
        url = f"{self.base_url}/{endpoint}"

        if self._http_adapter is not None:
            try:
                async with self._http_adapter as client:
                    resp = await client.post(url, json=data, timeout=300)
                    return resp.json()  # type: ignore[no-any-return]
            except Exception as e:
                self.logger.exception(f"HTTP request failed: {e}")
                raise
        # Fallback to aiohttp (legacy)
        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response,
            ):
                return await response.json()  # type: ignore[no-any-return]
        except ImportError:
            msg = (
                "aiohttp package not installed and HTTPClientAdapter not available. "
                "Install with: pip install aiohttp or configure mcp-common HTTPClientAdapter"
            )
            raise ImportError(msg)  # type: ignore[no-any-return]

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, str]]:
        """Convert LLMMessage objects to Ollama format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate response using Ollama API."""
        if not await self.is_available():
            msg = "Ollama provider not available"
            raise RuntimeError(msg)

        model_name = model or self.default_model

        try:
            data: dict[str, Any] = {
                "model": model_name,
                "messages": self._convert_messages(messages),
                "options": {"temperature": temperature},
            }

            if max_tokens:
                data["options"]["num_predict"] = max_tokens

            response = await self._make_api_request("api/chat", data)

            return LLMResponse(
                content=response.get("message", {}).get("content", ""),
                model=model_name,
                provider="ollama",
                usage={
                    "prompt_tokens": response.get("prompt_eval_count", 0),
                    "completion_tokens": response.get("eval_count", 0),
                    "total_tokens": response.get("prompt_eval_count", 0)
                    + response.get("eval_count", 0),
                },
                finish_reason=response.get("done_reason", "stop"),
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            self.logger.exception(f"Ollama generation failed: {e}")
            raise

    def _prepare_stream_data(
        self,
        model_name: str,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        """Prepare data payload for streaming request."""
        data: dict[str, Any] = {
            "model": model_name,
            "messages": self._convert_messages(messages),
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            data["options"]["num_predict"] = max_tokens
        return data

    def _extract_chunk_content(self, line: bytes) -> str | None:
        """Extract content from a streaming chunk line."""
        if not line:
            return None

        try:
            chunk_data = json.loads(line.decode("utf-8"))
            if isinstance(chunk_data, dict) and "message" in chunk_data:
                message = chunk_data["message"]
                if isinstance(message, dict) and "content" in message:
                    return str(message["content"])
        except json.JSONDecodeError:
            pass
        return None

    async def _stream_from_response_aiohttp(self, response: Any) -> AsyncGenerator[str]:
        """Process streaming response from aiohttp and yield content chunks."""
        async for line in response.content:
            content = self._extract_chunk_content(line)
            if content:
                yield content

    async def _stream_from_response_httpx(self, response: Any) -> AsyncGenerator[str]:
        """Process streaming response from httpx and yield content chunks."""
        async for line in response.aiter_bytes():
            content = self._extract_chunk_content(line)
            if content:
                yield content

    async def _stream_with_mcp_common(
        self,
        url: str,
        data: dict[str, Any],
    ) -> AsyncGenerator[str]:
        """Stream using MCP-common HTTP adapter."""
        # Note: http_adapter access requires mcp-common integration setup
        # This is a placeholder for future mcp-common integration
        if False:  # Disabled until http_adapter is properly initialized
            yield ""  # pragma: no cover
        else:
            # Fallback to aiohttp for now
            async for chunk in self._stream_with_aiohttp(url, data):
                yield chunk

    async def _stream_with_aiohttp(
        self,
        url: str,
        data: dict[str, Any],
    ) -> AsyncGenerator[str]:
        """Stream using aiohttp fallback."""
        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response,
            ):
                async for chunk in self._stream_from_response_aiohttp(response):
                    yield chunk
        except ImportError:
            msg = "aiohttp not installed and mcp-common not available"
            raise ImportError(msg)

    async def stream_generate(  # type: ignore[override]
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Stream response using Ollama API with connection pooling."""
        if not await self.is_available():
            msg = "Ollama provider not available"
            raise RuntimeError(msg)

        model_name = model or self.default_model
        data = self._prepare_stream_data(model_name, messages, temperature, max_tokens)
        url = f"{self.base_url}/api/chat"

        try:
            # Note: mcp-common integration deferred - using aiohttp fallback
            # if self._use_mcp_common and self.http_adapter:
            #     async for chunk in self._stream_with_mcp_common(url, data):
            #         yield chunk
            # else:
            async for chunk in self._stream_with_aiohttp(url, data):
                yield chunk
        except Exception as e:
            self.logger.exception(f"Ollama streaming failed: {e}")
            raise

    async def _check_with_mcp_common(self, url: str) -> bool:
        """Check availability using MCP-common HTTP adapter."""
        # Note: http_adapter access requires mcp-common integration setup
        # This is a placeholder for future mcp-common integration
        return False  # Disabled until http_adapter is properly initialized

    async def _check_with_aiohttp(self, url: str) -> bool:
        """Check availability using aiohttp fallback."""
        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    self._available_models = [
                        model["name"] for model in data.get("models", [])
                    ]
                    return True
            return False
        except Exception:
            return False

    async def is_available(self) -> bool:
        """Check if Ollama is available with connection pooling."""
        try:
            url = f"{self.base_url}/api/tags"

            # Note: mcp-common integration deferred - using aiohttp fallback
            # if self._use_mcp_common and self.http_adapter:
            #     return await self._check_with_mcp_common(url)
            return await self._check_with_aiohttp(url)
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """Get available Ollama models."""
        return self._available_models or [
            "llama2",
            "llama2:13b",
            "llama2:70b",
            "codellama",
            "mistral",
            "mixtral",
        ]
