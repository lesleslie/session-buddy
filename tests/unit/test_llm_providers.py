"""Tests for llm_providers module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from session_buddy.llm import LLMMessage
from session_buddy.llm_providers import LLMManager


@pytest.fixture
def llm_manager():
    """Create an LLMManager instance for testing."""
    with patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai, \
         patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini, \
         patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama:

        # Mock the provider instances
        mock_openai_instance = AsyncMock()
        mock_openai_instance.is_available.return_value = True
        mock_openai.return_value = mock_openai_instance

        mock_gemini_instance = AsyncMock()
        mock_gemini_instance.is_available.return_value = True
        mock_gemini.return_value = mock_gemini_instance

        mock_ollama_instance = AsyncMock()
        mock_ollama_instance.is_available.return_value = True
        mock_ollama.return_value = mock_ollama_instance

        manager = LLMManager()
        yield manager


@pytest.mark.asyncio
async def test_llm_manager_initialization():
    """Test LLMManager initialization."""
    with patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai, \
         patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini, \
         patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama:

        # Mock the provider instances
        mock_openai_instance = AsyncMock()
        mock_openai_instance.is_available.return_value = True
        mock_openai.return_value = mock_openai_instance

        mock_gemini_instance = AsyncMock()
        mock_gemini_instance.is_available.return_value = True
        mock_gemini.return_value = mock_gemini_instance

        mock_ollama_instance = AsyncMock()
        mock_ollama_instance.is_available.return_value = True
        mock_ollama.return_value = mock_ollama_instance

        manager = LLMManager()

        assert manager.config["default_provider"] == "openai"
        assert "openai" in manager.providers
        assert "gemini" in manager.providers
        assert "ollama" in manager.providers


@pytest.mark.asyncio
async def test_get_available_providers():
    """Test getting available providers."""
    with patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai, \
         patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini, \
         patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama:

        # Mock the provider instances
        mock_openai_instance = AsyncMock()
        mock_openai_instance.is_available.return_value = True
        mock_openai.return_value = mock_openai_instance

        mock_gemini_instance = AsyncMock()
        mock_gemini_instance.is_available.return_value = False  # Not available
        mock_gemini.return_value = mock_gemini_instance

        mock_ollama_instance = AsyncMock()
        mock_ollama_instance.is_available.return_value = True
        mock_ollama.return_value = mock_ollama_instance

        manager = LLMManager()

        available = await manager.get_available_providers()
        assert "openai" in available
        assert "gemini" not in available  # Should not be available
        assert "ollama" in available
        assert len(available) == 2


@pytest.mark.asyncio
async def test_is_valid_provider():
    """Test checking if a provider is valid."""
    with patch("session_buddy.llm_providers.OpenAIProvider") as mock_openai, \
         patch("session_buddy.llm_providers.GeminiProvider") as mock_gemini, \
         patch("session_buddy.llm_providers.OllamaProvider") as mock_ollama:

        # Mock the provider instances
        mock_openai_instance = AsyncMock()
        mock_openai_instance.is_available.return_value = True
        mock_openai.return_value = mock_openai_instance

        mock_gemini_instance = AsyncMock()
        mock_gemini_instance.is_available.return_value = True
        mock_gemini.return_value = mock_gemini_instance

        mock_ollama_instance = AsyncMock()
        mock_ollama_instance.is_available.return_value = True
        mock_ollama.return_value = mock_ollama_instance

        manager = LLMManager()

        assert manager._is_valid_provider("openai") is True
        assert manager._is_valid_provider("nonexistent") is False
