#!/usr/bin/env python3
"""LLM provider management MCP tools.

This module provides tools for managing and interacting with LLM providers
following crackerjack architecture patterns.

Refactored to use utility modules for reduced code duplication.
"""

from __future__ import annotations

import typing as t
from typing import TYPE_CHECKING, Any

from session_buddy.utils.error_management import _get_logger
from session_buddy.utils.instance_managers import (
    get_llm_manager as resolve_llm_manager,
)
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from fastmcp import FastMCP


# Lazy loading flag for optional LLM dependencies
_llm_available: bool | None = None

LLM_NOT_AVAILABLE_MSG = "LLM providers not available. Install dependencies: pip install openai google-generativeai aiohttp"


# ============================================================================
# Service Resolution and Availability Checks
# ============================================================================


def _check_llm_available() -> bool:
    """Check if LLM providers are available."""
    global _llm_available

    if _llm_available is None:
        try:
            import importlib.util

            spec = importlib.util.find_spec("session_buddy.llm_providers")
            _llm_available = spec is not None
        except ImportError:
            _llm_available = False

    return _llm_available


async def _get_llm_manager() -> Any:
    """Get LLM manager instance with lazy loading."""
    global _llm_available

    if _llm_available is False:
        return None

    manager = await resolve_llm_manager()
    if manager is None:
        _get_logger().warning("LLM providers not available.")
        _llm_available = False
        return None

    _llm_available = True
    return manager


async def _require_llm_manager() -> Any:
    """Get LLM manager or raise with helpful error message."""
    if not _check_llm_available():
        raise RuntimeError(LLM_NOT_AVAILABLE_MSG)

    manager = await _get_llm_manager()
    if not manager:
        msg = "Failed to initialize LLM manager"
        raise RuntimeError(msg)

    return manager


async def _execute_llm_operation(
    operation_name: str,
    operation: t.Callable[[Any], t.Awaitable[str]],
) -> str:
    """Execute an LLM operation with error handling."""
    try:
        manager = await _require_llm_manager()
        return await operation(manager)
    except RuntimeError as e:
        return f"❌ {e!s}"
    except Exception as e:
        _get_logger().exception(f"Error in {operation_name}: {e}")
        return ToolMessages.operation_failed(operation_name, e)


# ============================================================================
# Output Formatting Helpers
# ============================================================================


def _add_provider_details(
    output: list[str],
    providers: dict[str, Any],
    available_providers: set[str],
) -> None:
    """Add provider details to the output list."""
    for provider_name, info in providers.items():
        status = "✅" if provider_name in available_providers else "❌"
        output.append(f"{status} {provider_name.title()}")

        if provider_name in available_providers:
            _add_model_list(output, info["models"])
        output.append("")


def _add_model_list(output: list[str], models: list[str]) -> None:
    """Add model list to the output with truncation."""
    displayed_models = models[:5]  # Show first 5 models
    for model in displayed_models:
        output.append(f"   • {model}")

    if len(models) > 5:
        output.append(f"   • ... and {len(models) - 5} more")


def _add_config_summary(output: list[str], config: dict[str, Any]) -> None:
    """Add configuration summary to the output."""
    output.extend(
        [
            f"🎯 Default Provider: {config['default_provider']}",
            f"🔄 Fallback Providers: {', '.join(config['fallback_providers'])}",
        ],
    )


def _format_provider_list(provider_data: dict[str, Any]) -> str:
    """Format provider information into a readable list."""
    available_providers = provider_data["available_providers"]
    provider_info = provider_data["provider_info"]

    output = ["🤖 Available LLM Providers", ""]
    _add_provider_details(output, provider_info["providers"], available_providers)
    _add_config_summary(output, provider_info["config"])

    return "\n".join(output)


def _format_generation_result(result: dict[str, Any]) -> str:
    """Format LLM generation result."""
    output = ["✨ LLM Generation Result", ""]
    output.extend(
        (
            f"🤖 Provider: {result['metadata']['provider']}",
            f"🎯 Model: {result['metadata']['model']}",
            f"⚡ Response time: {result['metadata']['response_time_ms']:.0f}ms",
            f"📊 Tokens: {result['metadata'].get('tokens_used', 'N/A')}",
            "",
            "💬 Generated text:",
            "─" * 40,
            result["text"],
        )
    )

    return "\n".join(output)


def _format_chat_result(result: dict[str, Any], message_count: int) -> str:
    """Format LLM chat result."""
    output = ["💬 LLM Chat Result", ""]
    output.extend(
        (
            f"🤖 Provider: {result['metadata']['provider']}",
            f"🎯 Model: {result['metadata']['model']}",
            f"⚡ Response time: {result['metadata']['response_time_ms']:.0f}ms",
            f"📊 Messages: {message_count} → 1",
            "",
            "🎭 Assistant response:",
            "─" * 40,
            result["response"],
        )
    )

    return "\n".join(output)


def _format_provider_config_output(
    provider: str,
    api_key: str | None = None,
    base_url: str | None = None,
    default_model: str | None = None,
) -> str:
    """Format the provider configuration output."""
    output = ["⚙️ Provider Configuration Updated", ""]
    output.append(f"🤖 Provider: {provider}")

    if api_key:
        # Don't show the full API key for security
        masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        output.append(f"🔑 API Key: {masked_key}")

    if base_url:
        output.append(f"🌐 Base URL: {base_url}")

    if default_model:
        output.append(f"🎯 Default Model: {default_model}")

    output.extend(
        (
            "",
            "✅ Configuration saved successfully!",
            "💡 Use `test_llm_providers` to verify the configuration",
        )
    )

    return "\n".join(output)


# ============================================================================
# LLM Operation Implementations
# ============================================================================


async def _list_llm_providers_operation(manager: Any) -> str:
    """List all available LLM providers and their models."""
    provider_data = {
        "available_providers": await manager.get_available_providers(),
        "provider_info": manager.get_provider_info(),
    }
    return _format_provider_list(provider_data)


async def _list_llm_providers_impl() -> str:
    """List all available LLM providers and their models."""
    return await _execute_llm_operation(
        "List LLM providers",
        _list_llm_providers_operation,
    )


async def _test_llm_providers_operation(manager: Any) -> str:
    """Test all LLM providers to check their availability and functionality."""
    test_results = await manager.test_all_providers()

    output = ["🧪 LLM Provider Test Results", ""]

    for provider, result in test_results.items():
        status = "✅" if result["success"] else "❌"
        output.append(f"{status} {provider.title()}")

        if result["success"]:
            output.extend(
                (
                    f"   ⚡ Response time: {result['response_time_ms']:.0f}ms",
                    f"   🎯 Model: {result['model']}",
                )
            )
        else:
            output.append(f"   ❌ Error: {result['error']}")
        output.append("")

    working_count = sum(1 for r in test_results.values() if r["success"])
    total_count = len(test_results)
    output.append(f"📊 Summary: {working_count}/{total_count} providers working")

    return "\n".join(output)


async def _test_llm_providers_impl() -> str:
    """Test all LLM providers to check their availability and functionality."""
    return await _execute_llm_operation(
        "Test LLM providers",
        _test_llm_providers_operation,
    )


async def _generate_with_llm_impl(
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    use_fallback: bool = True,
) -> str:
    """Generate text using specified LLM provider."""

    async def operation(manager: Any) -> str:
        result = await manager.generate_text(
            prompt=prompt,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_fallback=use_fallback,
        )

        if result["success"]:
            return _format_generation_result(result)
        return f"❌ Generation failed: {result['error']}"

    return await _execute_llm_operation("Generate with LLM", operation)


async def _chat_with_llm_impl(
    messages: list[dict[str, str]],
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """Have a conversation with an LLM provider."""

    async def operation(manager: Any) -> str:
        result = await manager.chat(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if result["success"]:
            return _format_chat_result(result, len(messages))
        return f"❌ Chat failed: {result['error']}"

    return await _execute_llm_operation("Chat with LLM", operation)


async def _configure_llm_provider_impl(
    provider: str,
    api_key: str | None = None,
    base_url: str | None = None,
    default_model: str | None = None,
) -> str:
    """Configure an LLM provider with API credentials and settings."""

    async def operation(manager: Any) -> str:
        config_data = {}
        if api_key:
            config_data["api_key"] = api_key
        if base_url:
            config_data["base_url"] = base_url
        if default_model:
            config_data["default_model"] = default_model

        result = await manager.configure_provider(provider, config_data)

        if result["success"]:
            return _format_provider_config_output(
                provider,
                api_key,
                base_url,
                default_model,
            )
        return f"❌ Configuration failed: {result['error']}"

    return await _execute_llm_operation("Configure LLM provider", operation)


# ============================================================================
# MCP Tool Registration
# ============================================================================


def register_llm_tools(mcp: FastMCP) -> None:
    """Register all LLM provider management MCP tools.

    Args:
        mcp: FastMCP server instance

    """

    @mcp.tool()
    async def list_llm_providers() -> str:
        """List all available LLM providers and their models."""
        return await _list_llm_providers_impl()

    @mcp.tool()
    async def test_llm_providers() -> str:
        """Test all LLM providers to check their availability and functionality."""
        return await _test_llm_providers_impl()

    @mcp.tool()
    async def generate_with_llm(
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        use_fallback: bool = True,
    ) -> str:
        """Generate text using specified LLM provider.

        Args:
            prompt: The text prompt to generate from
            provider: LLM provider to use (openai, gemini, ollama)
            model: Specific model to use
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            use_fallback: Whether to use fallback providers if primary fails

        """
        return await _generate_with_llm_impl(
            prompt,
            provider,
            model,
            temperature,
            max_tokens,
            use_fallback,
        )

    @mcp.tool()
    async def chat_with_llm(
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Have a conversation with an LLM provider.

        Args:
            messages: List of messages in format [{"role": "user/assistant/system", "content": "text"}]
            provider: LLM provider to use (openai, gemini, ollama)
            model: Specific model to use
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

        """
        return await _chat_with_llm_impl(
            messages,
            provider,
            model,
            temperature,
            max_tokens,
        )

    @mcp.tool()
    async def configure_llm_provider(
        provider: str,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> str:
        """Configure an LLM provider with API credentials and settings.

        Args:
            provider: Provider name (openai, gemini, ollama)
            api_key: API key for the provider
            base_url: Base URL for the provider API
            default_model: Default model to use

        """
        return await _configure_llm_provider_impl(
            provider,
            api_key,
            base_url,
            default_model,
        )

    @mcp.tool()
    async def sync_claude_qwen_config(
        source: str = "claude",
        destination: str = "qwen",
        sync_types: list[str] | None = None,
        skip_servers: list[str] | None = None,
    ) -> str:
        """Sync Claude and Qwen provider configurations.

        Provides bidirectional synchronization between Claude Code and Qwen Code:
        - MCP servers (JSON dict merge)
        - Extensions/plugins (tracking only, manual install required)
        - File-based resources (commands)

        Args:
            source: Source config ("claude" or "qwen")
            destination: Destination config ("claude" or "qwen")
            sync_types: Types to sync (mcp, commands, extensions, all)
            skip_servers: MCP servers to skip during sync (default: homebrew, pycharm)

        Example:
            result = await sync_claude_qwen_config(
                source="claude",
                destination="qwen",
                sync_types=["mcp", "commands"],
                skip_servers=["homebrew", "pycharm"]
            )

        """
        async def operation(manager: Any) -> str:
            result = await manager.sync_provider_configs(
                source=source,
                destination=destination,
                sync_types=sync_types,
                skip_servers=skip_servers,
            )

            # Format result
            output = [
                "🔄 Config Sync Complete",
                "",
                f"📊 Source: {source} → {destination}",
                "",
            ]

            if result.get("mcp_servers", 0) > 0:
                output.extend(
                    [
                        f"✅ MCP Servers: {result['mcp_servers']} synced",
                        f"⏭️  Skipped: {result['mcp_servers_skipped']} ({', '.join(skip_servers or ['homebrew', 'pycharm'])})",
                        "",
                    ]
                )

            if result.get("commands_synced", 0) > 0:
                output.append(f"✅ Commands: {result['commands_synced']} converted")
                output.append("")

            if result.get("plugins_found", 0) > 0:
                output.extend(
                    [
                        f"📦 Plugins: {result['plugins_found']} found (tracking only)",
                        "💡 Install manually in destination with: qwen extensions install",
                        "",
                    ]
                )

            if result.get("errors"):
                output.extend(
                    [
                        "⚠️  Errors:",
                        "",
                    ]
                )
                for error in result["errors"]:
                    output.append(f"   ❌ {error}")
                output.append("")

            output.append("✨ Sync completed successfully!")

            return "\n".join(output)

        return await _execute_llm_operation("Sync Claude/Qwen config", operation)
