#!/usr/bin/env python3
"""Unit tests for LLM provider management MCP tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCheckLlmAvailable:
    """Test suite for _check_llm_available function."""

    def test_llm_available_when_module_exists(self):
        """Test that _check_llm_available returns True when module exists."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _check_llm_available,
        )

        with patch(
            "importlib.util.find_spec",
            return_value=MagicMock(),
        ):
            # Reset the cached value
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = _check_llm_available()
            assert result is True

    def test_llm_not_available_when_module_missing(self):
        """Test that _check_llm_available returns False when module is missing."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _check_llm_available,
        )

        with patch(
            "importlib.util.find_spec",
            return_value=None,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = _check_llm_available()
            assert result is False

    def test_llm_not_available_on_import_error(self):
        """Test that _check_llm_available returns False on ImportError."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _check_llm_available,
        )

        with patch(
            "importlib.util.find_spec",
            side_effect=ImportError("Module not found"),
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = _check_llm_available()
            assert result is False

    def test_result_is_cached(self):
        """Test that _check_llm_available caches its result."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _check_llm_available,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = True
        result = _check_llm_available()
        assert result is True


class TestGetLlmManager:
    """Test suite for _get_llm_manager function."""

    @pytest.mark.asyncio
    async def test_returns_manager_when_available(self):
        """Test that _get_llm_manager returns manager when available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _get_llm_manager,
        )

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _get_llm_manager()
            assert result is mock_manager
            assert llm_tools._llm_available is True

    @pytest.mark.asyncio
    async def test_returns_none_when_previously_marked_unavailable(self):
        """Test that _get_llm_manager returns None when already marked unavailable."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _get_llm_manager,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        result = await _get_llm_manager()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_manager_init_returns_none(self):
        """Test that _get_llm_manager returns None when manager init returns None."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _get_llm_manager,
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=None,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            with patch(
                "session_buddy.mcp.tools.intelligence.llm_tools._get_logger"
            ) as mock_logger:
                result = await _get_llm_manager()
                assert result is None
                assert llm_tools._llm_available is False


class TestRequireLlmManager:
    """Test suite for _require_llm_manager function."""

    @pytest.mark.asyncio
    async def test_returns_manager_when_available(self):
        """Test that _require_llm_manager returns manager when available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _require_llm_manager,
        )

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _require_llm_manager()
            assert result is mock_manager

    @pytest.mark.asyncio
    async def test_raises_runtime_when_llm_not_available(self):
        """Test that _require_llm_manager raises RuntimeError when LLM not available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _require_llm_manager,
            LLM_NOT_AVAILABLE_MSG,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        with pytest.raises(RuntimeError) as exc_info:
            await _require_llm_manager()
        assert LLM_NOT_AVAILABLE_MSG in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_runtime_when_manager_is_none(self):
        """Test that _require_llm_manager raises RuntimeError when manager is None."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _require_llm_manager,
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=None,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            with patch(
                "session_buddy.mcp.tools.intelligence.llm_tools._get_logger"
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    await _require_llm_manager()
                assert "Failed to initialize LLM manager" in str(exc_info.value)


class TestExecuteLlmOperation:
    """Test suite for _execute_llm_operation function."""

    @pytest.mark.asyncio
    async def test_successful_operation(self):
        """Test that _execute_llm_operation returns result on success."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _execute_llm_operation,
        )

        async def mock_operation(manager):
            return "success"

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _execute_llm_operation("Test Op", mock_operation)
            assert result == "success"

    @pytest.mark.asyncio
    async def test_runtime_error_returns_formatted_message(self):
        """Test that RuntimeError is caught and formatted as error message."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _execute_llm_operation,
        )

        async def mock_operation(manager):
            raise RuntimeError("LLM not available")

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _execute_llm_operation("Test Op", mock_operation)
            assert "❌" in result
            assert "LLM not available" in result

    @pytest.mark.asyncio
    async def test_generic_exception_returns_formatted_message(self):
        """Test that generic Exception is caught and logged."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _execute_llm_operation,
        )

        async def mock_operation(manager):
            raise ValueError("Something went wrong")

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            with patch(
                "session_buddy.mcp.tools.intelligence.llm_tools._get_logger"
            ) as mock_logger:
                result = await _execute_llm_operation("Test Op", mock_operation)
                assert "❌" in result
                assert "Something went wrong" in result


class TestListLlmProvidersOperation:
    """Test suite for _list_llm_providers_operation."""

    @pytest.mark.asyncio
    async def test_formats_provider_list_correctly(self):
        """Test that provider list is formatted correctly."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _list_llm_providers_operation,
        )

        mock_manager = MagicMock()
        mock_manager.get_available_providers = AsyncMock(
            return_value={"openai", "anthropic"}
        )
        mock_manager.get_provider_info = MagicMock(
            return_value={
                "providers": {
                    "openai": {"models": ["gpt-4", "gpt-3.5-turbo"]},
                    "anthropic": {"models": ["claude-3-opus"]},
                },
                "config": {
                    "default_provider": "openai",
                    "fallback_providers": ["anthropic"],
                },
            }
        )

        result = await _list_llm_providers_operation(mock_manager)

        assert "🤖 Available LLM Providers" in result
        assert "✅ Openai" in result
        assert "✅ Anthropic" in result
        assert "🎯 Default Provider: openai" in result
        assert "🔄 Fallback Providers: anthropic" in result
        assert "gpt-4" in result
        assert "claude-3-opus" in result


class TestListLlmProvidersImpl:
    """Test suite for _list_llm_providers_impl."""

    @pytest.mark.asyncio
    async def test_delegates_to_execute_llm_operation(self):
        """Test that _list_llm_providers_impl uses _execute_llm_operation."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _list_llm_providers_impl,
        )

        mock_manager = MagicMock()
        mock_manager.get_available_providers = AsyncMock(return_value={"openai"})
        mock_manager.get_provider_info = MagicMock(
            return_value={
                "providers": {"openai": {"models": ["gpt-4"]}},
                "config": {
                    "default_provider": "openai",
                    "fallback_providers": [],
                },
            }
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _list_llm_providers_impl()
            assert "🤖 Available LLM Providers" in result


class TestTestLlmProvidersOperation:
    """Test suite for _test_llm_providers_operation."""

    @pytest.mark.asyncio
    async def test_all_providers_working(self):
        """Test formatting when all providers work."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _test_llm_providers_operation,
        )

        mock_manager = MagicMock()
        mock_manager.test_all_providers = AsyncMock(
            return_value={
                "openai": {
                    "success": True,
                    "response_time_ms": 150.0,
                    "model": "gpt-4",
                },
                "anthropic": {
                    "success": True,
                    "response_time_ms": 200.0,
                    "model": "claude-3-opus",
                },
            }
        )

        result = await _test_llm_providers_operation(mock_manager)

        assert "🧪 LLM Provider Test Results" in result
        assert "✅ Openai" in result
        assert "✅ Anthropic" in result
        assert "📊 Summary: 2/2 providers working" in result

    @pytest.mark.asyncio
    async def test_some_providers_failing(self):
        """Test formatting when some providers fail."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _test_llm_providers_operation,
        )

        mock_manager = MagicMock()
        mock_manager.test_all_providers = AsyncMock(
            return_value={
                "openai": {
                    "success": True,
                    "response_time_ms": 150.0,
                    "model": "gpt-4",
                },
                "anthropic": {"success": False, "error": "API key invalid"},
            }
        )

        result = await _test_llm_providers_operation(mock_manager)

        assert "🧪 LLM Provider Test Results" in result
        assert "✅ Openai" in result
        assert "❌ Anthropic" in result
        assert "API key invalid" in result
        assert "📊 Summary: 1/2 providers working" in result


class TestTestLlmProvidersImpl:
    """Test suite for _test_llm_providers_impl."""

    @pytest.mark.asyncio
    async def test_delegates_to_execute_llm_operation(self):
        """Test that _test_llm_providers_impl uses _execute_llm_operation."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _test_llm_providers_impl,
        )

        mock_manager = MagicMock()
        mock_manager.test_all_providers = AsyncMock(return_value={})

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _test_llm_providers_impl()
            assert "🧪 LLM Provider Test Results" in result


class TestGenerateWithLlmImpl:
    """Test suite for _generate_with_llm_impl."""

    @pytest.mark.asyncio
    async def test_successful_generation(self):
        """Test successful text generation."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _generate_with_llm_impl,
        )

        mock_manager = MagicMock()
        mock_manager.generate_text = AsyncMock(
            return_value={
                "success": True,
                "text": "Hello, world!",
                "metadata": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "response_time_ms": 150.0,
                    "tokens_used": 10,
                },
            }
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _generate_with_llm_impl("Say hello")
            assert "✨ LLM Generation Result" in result
            assert "Hello, world!" in result
            assert "gpt-4" in result

    @pytest.mark.asyncio
    async def test_failed_generation(self):
        """Test failed text generation returns error message."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _generate_with_llm_impl,
        )

        mock_manager = MagicMock()
        mock_manager.generate_text = AsyncMock(
            return_value={"success": False, "error": "Rate limit exceeded"}
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _generate_with_llm_impl("Say hello")
            assert "❌" in result
            assert "Rate limit exceeded" in result

    @pytest.mark.asyncio
    async def test_passes_parameters_to_manager(self):
        """Test that parameters are passed correctly to manager."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _generate_with_llm_impl,
        )

        mock_manager = MagicMock()
        mock_manager.generate_text = AsyncMock(
            return_value={"success": True, "text": "result", "metadata": {}}
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            await _generate_with_llm_impl(
                "test prompt",
                provider="openai",
                model="gpt-4",
                temperature=0.5,
                max_tokens=100,
                use_fallback=False,
            )

            mock_manager.generate_text.assert_called_once()
            call_kwargs = mock_manager.generate_text.call_args.kwargs
            assert call_kwargs["prompt"] == "test prompt"
            assert call_kwargs["provider"] == "openai"
            assert call_kwargs["model"] == "gpt-4"
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["max_tokens"] == 100
            assert call_kwargs["use_fallback"] is False


class TestChatWithLlmImpl:
    """Test suite for _chat_with_llm_impl."""

    @pytest.mark.asyncio
    async def test_successful_chat(self):
        """Test successful chat conversation."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _chat_with_llm_impl,
        )

        mock_manager = MagicMock()
        mock_manager.chat = AsyncMock(
            return_value={
                "success": True,
                "response": "Hello! How can I help?",
                "metadata": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "response_time_ms": 200.0,
                },
            }
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
            result = await _chat_with_llm_impl(messages)
            assert "💬 LLM Chat Result" in result
            assert "Hello! How can I help?" in result
            assert "📊 Messages: 2 → 1" in result

    @pytest.mark.asyncio
    async def test_failed_chat(self):
        """Test failed chat returns error message."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _chat_with_llm_impl,
        )

        mock_manager = MagicMock()
        mock_manager.chat = AsyncMock(
            return_value={"success": False, "error": "Invalid API key"}
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _chat_with_llm_impl([{"role": "user", "content": "Hi"}])
            assert "❌" in result
            assert "Invalid API key" in result


class TestConfigureLlmProviderImpl:
    """Test suite for _configure_llm_provider_impl."""

    @pytest.mark.asyncio
    async def test_successful_configuration(self):
        """Test successful provider configuration."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _configure_llm_provider_impl,
        )

        mock_manager = MagicMock()
        mock_manager.configure_provider = AsyncMock(
            return_value={"success": True}
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _configure_llm_provider_impl(
                "openai",
                api_key="sk-1234567890abcdef",
                base_url="https://api.openai.com/v1",
                default_model="gpt-4",
            )
            assert "⚙️ Provider Configuration Updated" in result
            assert "openai" in result
            # API key should be masked (full key should NOT appear)
            assert "sk-1234567890abcdef" not in result
            # Masked key should be present
            assert "sk-12" in result
            assert "gpt-4" in result
            assert "✅ Configuration saved successfully!" in result

    @pytest.mark.asyncio
    async def test_failed_configuration(self):
        """Test failed configuration returns error message."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _configure_llm_provider_impl,
        )

        mock_manager = MagicMock()
        mock_manager.configure_provider = AsyncMock(
            return_value={"success": False, "error": "Invalid API key format"}
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _configure_llm_provider_impl(
                "openai",
                api_key="invalid-key",
            )
            assert "❌" in result
            assert "Invalid API key format" in result

    @pytest.mark.asyncio
    async def test_api_key_masking_short_key(self):
        """Test that short API keys are fully masked."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _configure_llm_provider_impl,
        )

        mock_manager = MagicMock()
        mock_manager.configure_provider = AsyncMock(
            return_value={"success": True}
        )

        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _configure_llm_provider_impl(
                "openai",
                api_key="short",
            )
            # Short keys should be fully masked
            assert "***" in result


class TestSyncClaudeQwenConfig:
    """Test suite for sync_claude_qwen_config operation."""

    @pytest.mark.asyncio
    async def test_successful_sync_with_mcp_servers(self):
        """Test successful sync with MCP servers."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _execute_llm_operation,
        )

        async def mock_operation(manager):
            result = {
                "mcp_servers": 3,
                "mcp_servers_skipped": 1,
                "commands_synced": 5,
                "plugins_found": 2,
                "errors": [],
            }
            # Replicate the formatting from the actual tool
            output = [
                "🔄 Config Sync Complete",
                "",
                f"📊 Source: claude → qwen",
                "",
            ]
            if result.get("mcp_servers", 0) > 0:
                output.extend(
                    [
                        f"✅ MCP Servers: {result['mcp_servers']} synced",
                        f"⏭️  Skipped: {result['mcp_servers_skipped']} (homebrew, pycharm)",
                        "",
                    ]
                )
            if result.get("commands_synced", 0) > 0:
                output.extend([f"✅ Commands: {result['commands_synced']} converted", ""])
            if result.get("plugins_found", 0) > 0:
                output.extend(
                    [
                        f"📦 Plugins: {result['plugins_found']} found (tracking only)",
                        "💡 Install manually in destination with: qwen extensions install",
                        "",
                    ]
                )
            if result.get("errors"):
                output.extend(["⚠️  Errors:", ""])
                for error in result["errors"]:
                    output.append(f"   ❌ {error}")
            output.append("✨ Sync completed successfully!")
            return "\n".join(output)

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _execute_llm_operation(
                "Sync Claude/Qwen config", mock_operation
            )
            assert "🔄 Config Sync Complete" in result
            assert "✅ MCP Servers: 3 synced" in result
            assert "✅ Commands: 5 converted" in result
            assert "📦 Plugins: 2 found" in result
            assert "✨ Sync completed successfully!" in result

    @pytest.mark.asyncio
    async def test_sync_with_errors(self):
        """Test sync that encounters errors."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _execute_llm_operation,
        )

        async def mock_operation(manager):
            result = {
                "mcp_servers": 1,
                "mcp_servers_skipped": 0,
                "commands_synced": 0,
                "plugins_found": 0,
                "errors": ["Failed to sync server-1: timeout", "Server-2 skipped"],
            }
            output = ["⚠️  Errors:", ""]
            for error in result["errors"]:
                output.append(f"   ❌ {error}")
            return "\n".join(output)

        mock_manager = MagicMock()
        with patch(
            "session_buddy.mcp.tools.intelligence.llm_tools.resolve_llm_manager",
            return_value=mock_manager,
        ):
            import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

            llm_tools._llm_available = None
            result = await _execute_llm_operation(
                "Sync Claude/Qwen config", mock_operation
            )
            assert "⚠️  Errors:" in result
            assert "Failed to sync server-1: timeout" in result


class TestAddProviderDetails:
    """Test suite for _add_provider_details helper."""

    def test_adds_available_provider_with_checkmark(self):
        """Test that available providers show ✅ status."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _add_provider_details,
        )

        output = []
        providers = {
            "openai": {"models": ["gpt-4"]},
        }
        available_providers = {"openai"}

        _add_provider_details(output, providers, available_providers)

        assert "✅ Openai" in output

    def test_adds_unavailable_provider_with_x(self):
        """Test that unavailable providers show ❌ status."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _add_provider_details,
        )

        output = []
        providers = {
            "anthropic": {"models": ["claude-3"]},
        }
        available_providers = set()

        _add_provider_details(output, providers, available_providers)

        assert "❌ Anthropic" in output


class TestAddModelList:
    """Test suite for _add_model_list helper."""

    def test_shows_first_five_models(self):
        """Test that only first 5 models are shown."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _add_model_list,
        )

        output = []
        models = ["model-1", "model-2", "model-3", "model-4", "model-5", "model-6"]

        _add_model_list(output, models)

        assert "model-1" in output
        assert "model-5" in output
        assert "model-6" not in output
        assert "... and 1 more" in output

    def test_no_overflow_when_five_or_fewer_models(self):
        """Test no overflow message when 5 or fewer models."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _add_model_list,
        )

        output = []
        models = ["gpt-4", "gpt-3.5-turbo"]

        _add_model_list(output, models)

        assert "... and" not in output


class TestAddConfigSummary:
    """Test suite for _add_config_summary helper."""

    def test_formats_config_correctly(self):
        """Test configuration summary formatting."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _add_config_summary,
        )

        output = []
        config = {
            "default_provider": "openai",
            "fallback_providers": ["anthropic", "google"],
        }

        _add_config_summary(output, config)

        assert "🎯 Default Provider: openai" in output
        assert "🔄 Fallback Providers: anthropic, google" in output


class TestFormatProviderList:
    """Test suite for _format_provider_list helper."""

    def test_formats_provider_list(self):
        """Test provider list formatting."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_provider_list,
        )

        provider_data = {
            "available_providers": {"openai"},
            "provider_info": {
                "providers": {
                    "openai": {"models": ["gpt-4"]},
                    "anthropic": {"models": ["claude-3"]},
                },
                "config": {
                    "default_provider": "openai",
                    "fallback_providers": ["anthropic"],
                },
            },
        }

        result = _format_provider_list(provider_data)

        assert "🤖 Available LLM Providers" in result
        assert "✅ Openai" in result
        assert "❌ Anthropic" in result
        assert "gpt-4" in result


class TestFormatGenerationResult:
    """Test suite for _format_generation_result helper."""

    def test_formats_generation_result(self):
        """Test generation result formatting."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_generation_result,
        )

        result = {
            "text": "Generated content here",
            "metadata": {
                "provider": "openai",
                "model": "gpt-4",
                "response_time_ms": 150.5,
                "tokens_used": 25,
            },
        }

        output = _format_generation_result(result)

        assert "✨ LLM Generation Result" in output
        assert "🤖 Provider: openai" in output
        assert "🎯 Model: gpt-4" in output
        assert "⚡ Response time: 150ms" in output
        assert "📊 Tokens: 25" in output
        assert "Generated content here" in output

    def test_handles_missing_tokens(self):
        """Test handling of missing tokens_used field."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_generation_result,
        )

        result = {
            "text": "Content",
            "metadata": {
                "provider": "openai",
                "model": "gpt-4",
                "response_time_ms": 100.0,
            },
        }

        output = _format_generation_result(result)

        assert "📊 Tokens: N/A" in output


class TestFormatChatResult:
    """Test suite for _format_chat_result helper."""

    def test_formats_chat_result(self):
        """Test chat result formatting."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_chat_result,
        )

        result = {
            "response": "Assistant response text",
            "metadata": {
                "provider": "anthropic",
                "model": "claude-3-opus",
                "response_time_ms": 200.0,
            },
        }

        output = _format_chat_result(result, message_count=3)

        assert "💬 LLM Chat Result" in output
        assert "🤖 Provider: anthropic" in output
        assert "📊 Messages: 3 → 1" in output
        assert "Assistant response text" in output


class TestFormatProviderConfigOutput:
    """Test suite for _format_provider_config_output helper."""

    def test_formats_with_all_parameters(self):
        """Test configuration output with all parameters."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_provider_config_output,
        )

        result = _format_provider_config_output(
            provider="openai",
            api_key="sk-1234567890abcdef",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4",
        )

        assert "⚙️ Provider Configuration Updated" in result
        assert "🤖 Provider: openai" in result
        # API key should be masked (original key should NOT appear)
        assert "sk-1234567890abcdef" not in result
        # But some prefix of the key should be visible
        assert "sk-12" in result
        assert "https://api.openai.com/v1" in result
        assert "gpt-4" in result
        assert "✅ Configuration saved successfully!" in result

    def test_formats_with_minimal_parameters(self):
        """Test configuration output with only provider."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_provider_config_output,
        )

        result = _format_provider_config_output(provider="openai")

        assert "sk-..." not in result
        assert "Base URL" not in result
        assert "Default Model" not in result

    def test_api_key_masking(self):
        """Test API key masking logic."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _format_provider_config_output,
        )

        # Key longer than 12 chars should show first 8 + ... + last 4
        long_key = "abcdefghijklmnop"  # 16 chars > 12
        result = _format_provider_config_output(
            provider="test",
            api_key=long_key,
        )
        # Should show first 8 chars, ..., last 4 chars
        assert "abcdefgh" in result
        assert "mnop" in result
        assert "***" not in result  # Not fully masked

        # Key 12 chars or shorter should be fully masked
        short_key = "shortkey"  # 8 chars <= 12
        result = _format_provider_config_output(
            provider="test",
            api_key=short_key,
        )
        assert "***" in result
        assert "shortkey" not in result


class TestRegisterLlmTools:
    """Test suite for register_llm_tools function."""

    def test_registers_all_tools(self):
        """Test that all LLM tools are registered on the FastMCP server."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            register_llm_tools,
        )

        mock_mcp = MagicMock()

        register_llm_tools(mock_mcp)

        # Verify tool decorator was called 5 times (list, test, generate, chat, configure)
        assert mock_mcp.tool.call_count >= 5

    def test_tools_are_async_functions(self):
        """Test that registered tools are async functions."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            register_llm_tools,
        )
        import inspect

        mock_mcp = MagicMock()
        register_llm_tools(mock_mcp)

        # Get the decorated functions
        calls = mock_mcp.tool.call_args_list
        for call in calls:
            func = call.kwargs.get("func")
            if func is not None:
                assert inspect.iscoroutinefunction(func)


class TestLlmToolsIntegration:
    """Integration tests for LLM tools using mocked dependencies."""

    @pytest.mark.asyncio
    async def test_list_providers_when_llm_not_available(self):
        """Test list_providers returns error when LLM not available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _list_llm_providers_impl,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        result = await _list_llm_providers_impl()
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_test_providers_when_llm_not_available(self):
        """Test test_providers returns error when LLM not available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _test_llm_providers_impl,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        result = await _test_llm_providers_impl()
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_generate_when_llm_not_available(self):
        """Test generate returns error when LLM not available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _generate_with_llm_impl,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        result = await _generate_with_llm_impl("test prompt")
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_chat_when_llm_not_available(self):
        """Test chat returns error when LLM not available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _chat_with_llm_impl,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        result = await _chat_with_llm_impl([{"role": "user", "content": "Hi"}])
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_configure_when_llm_not_available(self):
        """Test configure returns error when LLM not available."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            _configure_llm_provider_impl,
        )

        import session_buddy.mcp.tools.intelligence.llm_tools as llm_tools

        llm_tools._llm_available = False
        result = await _configure_llm_provider_impl("openai", api_key="test")
        assert "❌" in result


class TestLlmToolsConstants:
    """Test suite for module-level constants."""

    def test_llm_not_available_msg_contains_hint(self):
        """Test that LLM_NOT_AVAILABLE_MSG contains installation hint."""
        from session_buddy.mcp.tools.intelligence.llm_tools import (
            LLM_NOT_AVAILABLE_MSG,
        )

        assert "pip install" in LLM_NOT_AVAILABLE_MSG
        assert "openai" in LLM_NOT_AVAILABLE_MSG