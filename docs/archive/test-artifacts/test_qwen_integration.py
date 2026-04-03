#!/usr/bin/env python3
"""Test script to verify Qwen provider integration in session-buddy."""

import asyncio
import os


async def test_qwen_provider_registration() -> bool:
    """Test that Qwen provider is properly registered."""
    from session_buddy.llm_providers import LLMManager

    print("Testing Qwen provider registration...")

    # Initialize LLM manager
    mgr = LLMManager()

    # Get available providers
    providers = await mgr.get_available_providers()
    print(f"Available providers: {providers}")

    # Check if qwen is in the list when QWEN_API_KEY is set
    if os.getenv("QWEN_API_KEY"):
        if "qwen" in providers:
            print("✅ Qwen provider is registered when QWEN_API_KEY is set")
            return True
        else:
            print("❌ Qwen provider NOT registered even though QWEN_API_KEY is set")
            return False
    else:
        print("⚠️  QWEN_API_KEY not set - skipping provider availability check")
        print("   To test full integration, set QWEN_API_KEY and run again")
        return True


async def test_qwen_config_loading() -> bool:
    """Test that Qwen config loads correctly."""
    from session_buddy.llm_providers import LLMManager

    print("\nTesting Qwen config loading...")

    mgr = LLMManager()

    # Check if qwen config exists
    if "qwen" in mgr.config.get("providers", {}):
        qwen_config = mgr.config["providers"]["qwen"]
        print(f"Qwen config: {qwen_config}")

        # Check expected fields
        expected_fields = ["api_key", "base_url", "default_model"]
        for field in expected_fields:
            if field in qwen_config:
                print(f"  ✅ {field}: {qwen_config[field]}")
            else:
                print(f"  ❌ Missing field: {field}")
                return False

        return True
    else:
        print("❌ Qwen config not found in manager config")
        return False


async def test_qwen_masked_api_key() -> bool:
    """Test that Qwen API key masking works."""
    from session_buddy.llm_providers import get_masked_api_key

    print("\nTesting Qwen API key masking...")

    # Set a fake API key for testing
    os.environ["QWEN_API_KEY"] = "sk-test-qwen-key-12345678"

    try:
        masked = get_masked_api_key("qwen")
        print(f"Masked Qwen API key: {masked}")

        # Check that key is masked (contains ... or *** and is not the full key)
        if ("..." in masked or "***" in masked) and masked != "sk-test-qwen-key-12345678":
            print("✅ Qwen API key masking works")
            return True
        else:
            print("❌ Qwen API key masking failed")
            return False
    finally:
        # Clean up
        os.environ.pop("QWEN_API_KEY", None)


async def test_qwen_settings_field() -> bool:
    """Test that qwen_api_key field exists in settings."""
    from session_buddy.settings import get_settings

    print("\nTesting Qwen settings field...")

    settings = get_settings()

    if hasattr(settings, "qwen_api_key"):
        print("✅ qwen_api_key field exists in settings")
        return True
    else:
        print("❌ qwen_api_key field NOT found in settings")
        return False


async def main() -> None:
    """Run all Qwen integration tests."""
    print("=" * 60)
    print("Session-Buddy Qwen Integration Tests")
    print("=" * 60)

    results = []

    # Run tests
    results.append(await test_qwen_settings_field())
    results.append(await test_qwen_config_loading())
    results.append(await test_qwen_masked_api_key())
    results.append(await test_qwen_provider_registration())

    # Summary
    print("\n" + "=" * 60)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    print("=" * 60)

    if all(results):
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
