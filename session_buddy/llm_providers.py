#!/usr/bin/env python3
"""Cross-LLM Compatibility for Session Management MCP Server.

Provides unified interface for multiple LLM providers including OpenAI, Google Gemini, and Ollama.
"""

import contextlib
import json
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from session_buddy.llm import (
    GeminiProvider,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    OllamaProvider,
    OpenAIProvider,
    StreamChunk,
    StreamGenerationOptions,
)
from session_buddy.settings import get_llm_api_key, get_settings

# Security utilities for API key validation/masking
try:
    from mcp_common.security import APIKeyValidator

    SECURITY_AVAILABLE = True
except ImportError:
    APIKeyValidator = None  # type: ignore[no-redef]
    SECURITY_AVAILABLE = False

# Re-export for backwards compatibility
__all__ = [
    "SECURITY_AVAILABLE",
    "LLMManager",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "StreamChunk",
    "StreamGenerationOptions",
]


def _get_provider_api_key_and_env(
    provider: str,
) -> tuple[str | None, str | None]:
    """Return the provider API key and its environment variable name."""
    configured_key = get_llm_api_key(provider)
    if configured_key:
        return configured_key, f"settings.{provider}_api_key"
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY"
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY"
    if provider == "gemini":
        if os.getenv("GEMINI_API_KEY"):
            return os.getenv("GEMINI_API_KEY"), "GEMINI_API_KEY"
        if os.getenv("GOOGLE_API_KEY"):
            return os.getenv("GOOGLE_API_KEY"), "GOOGLE_API_KEY"
        return None, "GEMINI_API_KEY"
    if provider == "qwen":
        return os.getenv("QWEN_API_KEY"), "QWEN_API_KEY"
    if provider == "ollama":
        return None, None
    return None, None


def _get_configured_providers() -> list[str]:
    """Get list of configured providers based on environment variables."""
    providers: set[str] = set()
    if get_llm_api_key("openai"):
        providers.add("openai")
    if get_llm_api_key("gemini"):
        providers.add("gemini")
    if get_llm_api_key("anthropic"):
        providers.add("anthropic")
    if get_llm_api_key("qwen"):
        providers.add("qwen")
    if os.getenv("OPENAI_API_KEY"):
        providers.add("openai")
    if os.getenv("ANTHROPIC_API_KEY"):
        providers.add("anthropic")
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        providers.add("gemini")
    if os.getenv("QWEN_API_KEY"):
        providers.add("qwen")
    return sorted(providers)


def _validate_provider_basic(provider: str, api_key: str) -> str:
    """Basic API key validation without security module."""
    import sys

    if len(api_key.strip()) < 16:
        print(
            f"API Key Warning: {provider} API key appears very short",
            file=sys.stderr,
        )
    return "basic_check"


def _validate_provider_with_security(provider: str, api_key: str) -> tuple[bool, str]:
    """Validate API key with security module."""
    import sys

    validator = APIKeyValidator(provider=provider) if APIKeyValidator else None
    try:
        if validator is None:
            return False, "unavailable"
        validator.validate(api_key, raise_on_invalid=True)
        print(f"✅ API Key validated for {provider}", file=sys.stderr)
        return True, "valid"
    except ValueError as exc:
        print(f"❌ API Key validation failed: {exc}", file=sys.stderr)
        sys.exit(1)


def validate_llm_api_keys_at_startup() -> dict[str, str]:
    """Validate configured LLM API keys and return status by provider."""
    import sys

    configured = _get_configured_providers()
    if not configured:
        print("No LLM Provider API Keys Configured", file=sys.stderr)
        return {}

    results: dict[str, str] = {}
    for provider in configured:
        api_key, env_var = _get_provider_api_key_and_env(provider)
        if api_key is None:
            continue
        if not api_key.strip():
            print(f"❌ {env_var} is empty", file=sys.stderr)
            sys.exit(1)

        if SECURITY_AVAILABLE:
            _, status = _validate_provider_with_security(provider, api_key)
        else:
            status = _validate_provider_basic(provider, api_key)
        results[provider] = status

    return results


def get_masked_api_key(provider: str = "openai") -> str:
    """Return masked API key for safe logging."""
    settings = get_settings()
    key_field_map = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "qwen": "qwen_api_key",
    }
    key_field = key_field_map.get(provider)
    if key_field:
        configured = getattr(settings, key_field, None)
        if isinstance(configured, str) and configured.strip():
            return settings.get_masked_key(key_name=key_field, visible_chars=4)

    api_key, _ = _get_provider_api_key_and_env(provider)

    if provider == "ollama":
        return "N/A (local service)"

    if not api_key:
        return "***"

    if SECURITY_AVAILABLE and APIKeyValidator:
        return APIKeyValidator.mask_key(api_key, visible_chars=4)

    if len(api_key) <= 4:
        return "***"
    return f"...{api_key[-4:]}"


class LLMManager:
    """Manager for multiple LLM providers with fallback support."""

    def __init__(self, config_path: str | None = None) -> None:
        self.providers: dict[str, LLMProvider] = {}
        self.config = self._load_config(config_path)
        self.logger = logging.getLogger("llm_providers.manager")
        self._initialize_providers()

    def _load_config(self, config_path: str | None) -> dict[str, Any]:
        """Load configuration from file or environment."""
        config: dict[str, Any] = {
            "providers": {},
            "default_provider": "openai",
            # Plan cascade: openai -> anthropic -> gemini (-> ollama future)
            "fallback_providers": ["anthropic", "gemini", "ollama"],
        }

        if config_path and Path(config_path).exists():
            with contextlib.suppress(OSError, json.JSONDecodeError):
                with open(config_path, encoding="utf-8") as f:
                    file_config = json.load(f)
                    config.update(file_config)

        # Add environment-based provider configs
        if not config["providers"].get("openai"):
            config["providers"]["openai"] = {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "default_model": "gpt-4",
            }

        if not config["providers"].get("anthropic"):
            config["providers"]["anthropic"] = {
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "default_model": "claude-3-5-haiku-20241022",
            }

        if not config["providers"].get("gemini"):
            config["providers"]["gemini"] = {
                "api_key": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
                "default_model": "gemini-pro",
            }

        if not config["providers"].get("ollama"):
            config["providers"]["ollama"] = {
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                "default_model": "llama2",
            }

        if not config["providers"].get("qwen"):
            config["providers"]["qwen"] = {
                "api_key": os.getenv("QWEN_API_KEY"),
                "base_url": os.getenv(
                    "QWEN_BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
                "default_model": os.getenv("QWEN_DEFAULT_MODEL", "qwen-coder-plus"),
            }

        return config

    def _initialize_providers(self) -> None:
        """Initialize all configured providers."""
        provider_classes = {
            "openai": OpenAIProvider,
            "anthropic": __import__(
                "session_buddy.llm.providers.anthropic_provider",
                fromlist=["AnthropicProvider"],
            ).AnthropicProvider,
            "gemini": GeminiProvider,
            "qwen": OpenAIProvider,
            "ollama": OllamaProvider,
        }

        for provider_name, provider_config in self.config["providers"].items():
            if provider_name in provider_classes:
                try:
                    self.providers[provider_name] = provider_classes[provider_name](
                        provider_config,
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to initialize {provider_name} provider: {e}",
                    )

    async def get_available_providers(self) -> list[str]:
        """Get list of available providers."""
        return [
            name
            for name, provider in self.providers.items()
            if await provider.is_available()
        ]

    async def generate(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate response with optional fallback."""
        target_provider = provider or self.config["default_provider"]

        # Try primary provider
        result = await self._try_primary_provider_generate(
            target_provider,
            messages,
            model,
            **kwargs,
        )
        if result is not None:
            return result

        # Try fallback providers if enabled
        if use_fallback:
            result = await self._try_fallback_providers_generate(
                target_provider,
                messages,
                model,
                **kwargs,
            )
            if result is not None:
                return result

        msg = "No available LLM providers"
        raise RuntimeError(msg)

    async def _try_primary_provider_generate(
        self,
        target_provider: str,
        messages: list[LLMMessage],
        model: str | None,
        **kwargs: Any,
    ) -> LLMResponse | None:
        """Try generating with primary provider."""
        if target_provider not in self.providers:
            return None

        try:
            provider_instance = self.providers[target_provider]
            if await provider_instance.is_available():
                return await provider_instance.generate(messages, model, **kwargs)
        except Exception as e:
            self.logger.warning(f"Provider {target_provider} failed: {e}")
        return None

    async def _try_fallback_providers_generate(
        self,
        target_provider: str,
        messages: list[LLMMessage],
        model: str | None,
        **kwargs: Any,
    ) -> LLMResponse | None:
        """Try generating with fallback providers."""
        for fallback_name in self.config.get("fallback_providers", []):
            if fallback_name in self.providers and fallback_name != target_provider:
                try:
                    provider_instance = self.providers[fallback_name]
                    if await provider_instance.is_available():
                        self.logger.info(f"Falling back to {fallback_name}")
                        return await provider_instance.generate(
                            messages,
                            model,
                            **kwargs,
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Fallback provider {fallback_name} failed: {e}",
                    )
        return None

    def _get_fallback_providers(self, target_provider: str) -> list[str]:
        """Get list of fallback providers excluding the target provider."""
        return [
            name
            for name in self.config.get("fallback_providers", [])
            if name in self.providers and name != target_provider
        ]

    def _is_valid_provider(self, provider_name: str) -> bool:
        """Check if a provider is valid and available."""
        return provider_name in self.providers

    async def _get_provider_stream(
        self,
        provider_name: str,
        messages: list[LLMMessage],
        model: str | None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Get stream from provider (assumes provider is available)."""
        provider_instance = self.providers[provider_name]
        async for chunk in provider_instance.stream_generate(  # type: ignore[attr-defined]
            messages,
            model,
            **kwargs,
        ):
            yield chunk

    async def _try_provider_streaming(
        self,
        provider_name: str,
        messages: list[LLMMessage],
        model: str | None,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Try streaming from a provider with error handling."""
        try:
            provider_instance = self.providers[provider_name]
            if await provider_instance.is_available():
                async for chunk in self._get_provider_stream(
                    provider_name,
                    messages,
                    model,
                    **kwargs,
                ):
                    yield chunk
        except Exception as e:
            self.logger.warning(f"Provider {provider_name} failed: {e}")

    async def _select_primary_provider(self, options: StreamGenerationOptions) -> str:
        """Select primary provider. Target complexity: ≤3."""
        target_provider = options.provider or self.config["default_provider"]
        if not self._is_valid_provider(target_provider):
            msg = f"Invalid provider: {target_provider}"
            raise RuntimeError(msg)
        return target_provider

    async def _try_streaming_from_provider(
        self,
        provider_name: str,
        messages: list[LLMMessage],
        options: StreamGenerationOptions,
    ) -> AsyncGenerator[StreamChunk]:
        """Try streaming from a specific provider. Target complexity: ≤6."""
        try:
            stream_started = False
            async for chunk_content in self._try_provider_streaming(
                provider_name,
                messages,
                options.model,
                temperature=options.temperature,
                max_tokens=options.max_tokens,
            ):
                stream_started = True
                yield StreamChunk.content_chunk(chunk_content, provider_name)

            if not stream_started:
                yield StreamChunk.error_chunk(f"No response from {provider_name}")

        except Exception as e:
            self.logger.warning(f"Provider {provider_name} failed: {e}")
            yield StreamChunk.error_chunk(str(e))

    async def _stream_from_primary_provider(
        self,
        primary_provider: str,
        messages: list[LLMMessage],
        options: StreamGenerationOptions,
    ) -> AsyncGenerator[str]:
        """Stream from primary provider. Target complexity: ≤4."""
        has_content = False
        async for chunk in self._try_streaming_from_provider(
            primary_provider,
            messages,
            options,
        ):
            if chunk.is_error:
                if not has_content:  # Log errors only if no content received
                    self.logger.warning(
                        f"Primary provider error: {chunk.metadata.get('error', 'Unknown')}",
                    )
                continue

            has_content = True
            yield chunk.content

        if not has_content:
            self.logger.debug(
                f"Primary provider {primary_provider} produced no content",
            )

    async def _stream_from_fallback_providers(
        self,
        primary_provider: str,
        messages: list[LLMMessage],
        options: StreamGenerationOptions,
    ) -> AsyncGenerator[str]:
        """Stream from fallback providers. Target complexity: ≤5."""
        if not options.use_fallback:
            return

        fallback_providers = self._get_fallback_providers(primary_provider)
        for fallback_name in fallback_providers:
            self.logger.info(f"Falling back to {fallback_name}")
            has_content = False
            async for chunk in self._try_streaming_from_provider(
                fallback_name,
                messages,
                options,
            ):
                if chunk.is_error:
                    continue
                has_content = True
                yield chunk.content
            if has_content:
                return

    async def stream_generate(  # type: ignore[override]
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> AsyncGenerator[str]:
        """Stream generate response with optional fallback. Target complexity: ≤8."""
        options = StreamGenerationOptions(
            provider=provider,
            model=model,
            use_fallback=use_fallback,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
        )

        try:
            # Try primary provider first
            primary_provider = await self._select_primary_provider(options)
            async for chunk_content in self._stream_from_primary_provider(
                primary_provider,
                messages,
                options,
            ):
                yield chunk_content
                return  # Success - exit early

            # Try fallback providers if primary failed
            async for chunk_content in self._stream_from_fallback_providers(
                primary_provider,
                messages,
                options,
            ):
                yield chunk_content
                return  # Success - exit early

            # All providers failed
            msg = "No available LLM providers"
            raise RuntimeError(msg)

        except Exception as e:
            self.logger.exception(f"Stream generation failed: {e}")
            raise

    def get_provider_info(self) -> dict[str, Any]:
        """Get information about all providers."""
        info: dict[str, Any] = {
            "providers": {},
            "config": {
                "default_provider": self.config["default_provider"],
                "fallback_providers": self.config.get("fallback_providers", []),
            },
        }

        for name, provider in self.providers.items():
            info["providers"][name] = {
                "models": provider.get_models(),
                "config": {
                    k: v for k, v in provider.config.items() if "key" not in k.lower()
                },
            }

        return info

    async def test_providers(self) -> dict[str, Any]:
        """Test all providers and return status."""
        test_message = [
            LLMMessage(role="user", content='Hello, respond with just "OK"'),
        ]
        results = {}

        for name, provider in self.providers.items():
            try:
                available = await provider.is_available()
                if available:
                    # Quick test generation
                    response = await provider.generate(test_message, max_tokens=10)
                    results[name] = {
                        "available": True,
                        "test_successful": True,
                        "response_length": len(response.content),
                        "model": response.model,
                    }
                else:
                    results[name] = {
                        "available": False,
                        "test_successful": False,
                        "error": "Provider not available",
                    }
            except Exception as e:
                results[name] = {
                    "available": False,
                    "test_successful": False,
                    "error": str(e),
                }

        return results

    # ========================================================================
    # Claude/Qwen Config Sync
    # ========================================================================

    async def sync_provider_configs(
        self,
        source: str = "claude",
        destination: str = "qwen",
        sync_types: list[str] | None = None,
        skip_servers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Sync provider configurations between Claude and Qwen.

        Provides bidirectional synchronization between Claude Code and Qwen Code:
        - MCP servers (JSON dict merge)
        - Extensions/plugins (JSON dict merge)
        - File-based resources (agents, commands, skills)

        Args:
            source: Source config ("claude" or "qwen")
            destination: Destination config ("claude" or "qwen")
            sync_types: Types to sync (mcp, commands, extensions, all)
            skip_servers: MCP servers to skip during sync

        Returns:
            Sync result with stats and any errors

        Example:
            >>> manager = LLMManager()
            >>> result = await manager.sync_provider_configs(
            ...     source="claude",
            ...     destination="qwen",
            ...     sync_types=["mcp", "commands"],
            ...     skip_servers=["homebrew", "pycharm"]
            ... )
        """
        from pathlib import Path
        import hashlib

        # Configuration paths
        CLAUDE_CONFIG = Path.home() / ".claude.json"
        QWEN_CONFIG = Path.home() / ".qwen" / "settings.json"
        CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
        CLAUDE_COMMANDS_DIR = Path.home() / ".claude" / "commands"
        QWEN_COMMANDS_DIR = Path.home() / ".qwen" / "commands"
        CLAUDE_PLUGINS_FILE = Path.home() / ".claude" / "plugins" / "installed_plugins.json"

        # Default skip servers
        DEFAULT_SKIP_SERVERS = ["homebrew", "pycharm"]

        if skip_servers is None:
            skip_servers = DEFAULT_SKIP_SERVERS

        # Helper functions
        def load_json_safely(path: Path) -> dict[str, Any]:
            """Load JSON file safely, returning empty dict if not exists."""
            try:
                if path.exists():
                    return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(f"Failed to load {path}: {e}")
            return {}

        def save_json_atomically(path: Path, data: dict[str, Any]) -> None:
            """Save JSON file atomically to prevent corruption."""
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, indent=2))
            temp_path.replace(path)
            self.logger.debug(f"Saved {path} atomically")

        def merge_mcp_servers(
            claude: dict[str, Any],
            qwen: dict[str, Any],
            skip_servers_list: list[str] | None = None,
        ) -> dict[str, Any]:
            """Merge MCP servers from both configs.

            Strategy:
            - Servers unique to one side: add to other
            - Servers on both sides: Source takes precedence (last-write-wins)
            - Preserve server metadata (type, url, command, args)
            - Skip servers in skip_servers list
            """
            if skip_servers_list is None:
                skip_servers_list = skip_servers

            claude_mcp = claude.get("mcpServers", {})
            qwen_mcp = qwen.get("mcpServers", {})

            # Filter out skipped servers from source config
            if source == "claude":
                filtered_source_mcp = {
                    name: config
                    for name, config in claude_mcp.items()
                    if name not in skip_servers_list
                }
                merged = {**qwen_mcp}
                merged.update(filtered_source_mcp)
            else:  # qwen
                filtered_source_mcp = {
                    name: config
                    for name, config in qwen_mcp.items()
                    if name not in skip_servers_list
                }
                merged = {**claude_mcp}
                merged.update(filtered_source_mcp)

            skipped_count = len(claude_mcp if source == "claude" else qwen_mcp) - len(
                filtered_source_mcp
            )
            self.logger.debug(
                f"Merged {len(filtered_source_mcp)} {source} + "
                f"{len(qwen_mcp if source == 'claude' else claude_mcp)} "
                f"{destination} MCP servers (skipped {skipped_count})"
            )
            return merged

        def markdown_to_qwen_markdown(md_content: str, command_name: str) -> str:
            """Convert Claude command markdown to Qwen markdown format."""
            import re

            lines = md_content.strip().split("\n")
            description = command_name
            prompt_start = 0

            # Look for description line
            for i, line in enumerate(lines):
                if "description:" in line.lower():
                    match = re.search(r"description:\s*(.+?)(?:\s+id:)?$", line, re.IGNORECASE)
                    if match:
                        description = match.group(1).strip()
                        prompt_start = i + 1
                        break
                elif line.strip().startswith("#"):
                    description = line.strip("#").strip()
                    prompt_start = i + 1
                    break

            # Extract the main prompt content
            prompt_lines = []
            for line in lines[prompt_start:]:
                prompt_lines.append(line)

            prompt_content = "\n".join(prompt_lines).strip()

            # Format as Qwen markdown with YAML frontmatter
            qwen_md = f"""---
description: {description}
---

# Command synced from Claude Code
# Original location: ~/.claude/commands/{command_name}.md

{prompt_content}
"""
            return qwen_md

        def sync_commands_source_to_dest() -> dict[str, Any]:
            """Sync commands from source to destination."""
            stats = {"commands_synced": 0, "commands_skipped": 0, "errors": []}

            try:
                # Determine source and destination directories
                if source == "claude":
                    src_dir = CLAUDE_COMMANDS_DIR
                    dst_dir = QWEN_COMMANDS_DIR
                else:
                    src_dir = QWEN_COMMANDS_DIR
                    dst_dir = CLAUDE_COMMANDS_DIR

                # Create destination directory if it doesn't exist
                dst_dir.mkdir(parents=True, exist_ok=True)

                # Find all markdown command files in source
                md_files = list(src_dir.glob("**/*.md"))
                self.logger.debug(f"Found {len(md_files)} command files in {source}")

                for md_file in md_files:
                    try:
                        rel_path = md_file.relative_to(src_dir)
                        md_name = rel_path.with_suffix(".md")

                        # Create subdirectories if needed
                        dst_md_file = dst_dir / md_name
                        dst_md_file.parent.mkdir(parents=True, exist_ok=True)

                        # Convert if syncing from Claude to Qwen
                        if source == "claude":
                            src_md = md_file.read_text()
                            dst_md = markdown_to_qwen_markdown(src_md, md_file.stem)
                        else:
                            dst_md = md_file.read_text()

                        # Write markdown file
                        dst_md_file.write_text(dst_md)
                        stats["commands_synced"] += 1

                        self.logger.debug(f"Converted: {rel_path} → {md_name}")

                    except Exception as e:
                        error_msg = f"Failed to convert {md_file}: {e}"
                        self.logger.warning(error_msg)
                        stats["errors"].append(error_msg)
                        stats["commands_skipped"] += 1

                self.logger.info(f"✅ Synced {stats['commands_synced']} commands to {destination}")

            except Exception as e:
                error_msg = f"Failed to sync commands: {e}"
                self.logger.error(error_msg)
                stats["errors"].append(error_msg)

            return stats

        # Main sync logic
        self.logger.info(f"Syncing {source} → {destination}")

        # Load configs
        if source == "claude":
            src_config = load_json_safely(CLAUDE_CONFIG)
            dst_config = load_json_safely(QWEN_CONFIG)
            dst_config_path = QWEN_CONFIG
        else:
            src_config = load_json_safely(QWEN_CONFIG)
            dst_config = load_json_safely(CLAUDE_CONFIG)
            dst_config_path = CLAUDE_CONFIG

        stats = {
            "mcp_servers": 0,
            "mcp_servers_skipped": 0,
            "plugins_found": 0,
            "commands_synced": 0,
            "errors": [],
        }

        # Default sync types if not specified
        if sync_types is None:
            sync_types = ["mcp", "extensions", "commands"]

        # Sync MCP servers
        if "mcp" in sync_types or "all" in sync_types:
            try:
                if "mcpServers" in src_config:
                    src_mcp_count = len(src_config["mcpServers"])
                    dst_config["mcpServers"] = merge_mcp_servers(
                        src_config, dst_config, skip_servers
                    )
                    stats["mcp_servers"] = src_mcp_count
                    stats["mcp_servers_skipped"] = len(
                        [s for s in src_config["mcpServers"] if s in skip_servers]
                    )
                    save_json_atomically(dst_config_path, dst_config)
                    self.logger.info(
                        f"✅ Synced {stats['mcp_servers']} MCP servers to {destination} "
                        f"(skipped {stats['mcp_servers_skipped']}: {', '.join(skip_servers)})"
                    )
            except Exception as e:
                error_msg = f"Failed to sync MCP servers: {e}"
                self.logger.error(error_msg)
                stats["errors"].append(error_msg)

        # Sync extensions (tracking only - manual install required)
        if "extensions" in sync_types or "all" in sync_types:
            try:
                if source == "claude":
                    claude_settings = load_json_safely(CLAUDE_SETTINGS)
                    plugins_manifest = load_json_safely(CLAUDE_PLUGINS_FILE)

                    enabled_plugins = claude_settings.get("enabledPlugins", {})
                    stats["plugins_found"] = len(enabled_plugins)

                    plugin_names = []
                    for plugin_id in enabled_plugins.keys():
                        name = plugin_id.split("@")[0]
                        plugin_names.append(name)

                    self.logger.info(
                        f"Found {len(plugin_names)} Claude plugins to potentially sync"
                    )
                    # Note: Actual extension installation requires manual action
            except Exception as e:
                error_msg = f"Failed to sync extensions: {e}"
                self.logger.error(error_msg)
                stats["errors"].append(error_msg)

        # Sync commands
        if "commands" in sync_types or "all" in sync_types:
            cmd_stats = sync_commands_source_to_dest()
            stats["commands_synced"] = cmd_stats["commands_synced"]
            stats["errors"].extend(cmd_stats["errors"])

        return stats
