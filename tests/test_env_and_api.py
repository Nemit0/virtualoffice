#!/usr/bin/env python3
"""
Test all environment variables and API connections.

This test verifies:
1. All required environment variables are set
2. OpenAI API keys work (both key1 and key2)
3. Azure OpenAI connection works
4. Token tracking system works
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class TestEnvironmentVariables:
    """Test that all required environment variables are set."""

    def test_openai_api_key_exists(self):
        """Test OPENAI_API_KEY is set."""
        api_key = os.getenv("OPENAI_API_KEY")
        assert api_key is not None, "OPENAI_API_KEY not set in .env"
        assert len(api_key) > 0, "OPENAI_API_KEY is empty"
        assert api_key.startswith("sk-"), "OPENAI_API_KEY should start with 'sk-'"

    def test_openai_api_key2_exists(self):
        """Test OPENAI_API_KEY2 is set."""
        api_key = os.getenv("OPENAI_API_KEY2")
        assert api_key is not None, "OPENAI_API_KEY2 not set in .env"
        assert len(api_key) > 0, "OPENAI_API_KEY2 is empty"
        assert api_key.startswith("sk-"), "OPENAI_API_KEY2 should start with 'sk-'"

    def test_azure_endpoint_exists(self):
        """Test AZURE_OPENAI_ENDPOINT is set."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        assert endpoint is not None, "AZURE_OPENAI_ENDPOINT not set in .env"
        assert len(endpoint) > 0, "AZURE_OPENAI_ENDPOINT is empty"
        assert endpoint.startswith("https://"), "AZURE_OPENAI_ENDPOINT should start with 'https://'"
        assert "azure.com" in endpoint, "AZURE_OPENAI_ENDPOINT should contain 'azure.com'"

    def test_azure_api_key_exists(self):
        """Test AZURE_OPENAI_API_KEY is set."""
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        assert api_key is not None, "AZURE_OPENAI_API_KEY not set in .env"
        assert len(api_key) > 0, "AZURE_OPENAI_API_KEY is empty"

    def test_azure_api_version_exists(self):
        """Test AZURE_OPENAI_API_VERSION is set or has default."""
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        assert api_version is not None
        assert len(api_version) > 0


class TestOpenAIConnections:
    """Test OpenAI API connections work."""

    def test_openai_key1_connection(self):
        """Test connection with OPENAI_API_KEY (key1)."""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        assert api_key is not None, "OPENAI_API_KEY not set"

        client = OpenAI(api_key=api_key, timeout=30)

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Say 'test1' and nothing else."}],
                max_tokens=10,
            )
            result = response.choices[0].message.content
            tokens = response.usage.total_tokens

            assert result is not None, "No response from OpenAI API (key1)"
            assert tokens > 0, "No token usage reported (key1)"
            print(f"\n✅ OPENAI_API_KEY works - Response: {result}, Tokens: {tokens}")

        except Exception as e:
            pytest.fail(f"OPENAI_API_KEY connection failed: {e}")

    def test_openai_key2_connection(self):
        """Test connection with OPENAI_API_KEY2 (key2)."""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY2")
        assert api_key is not None, "OPENAI_API_KEY2 not set"

        client = OpenAI(api_key=api_key, timeout=30)

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Say 'test2' and nothing else."}],
                max_tokens=10,
            )
            result = response.choices[0].message.content
            tokens = response.usage.total_tokens

            assert result is not None, "No response from OpenAI API (key2)"
            assert tokens > 0, "No token usage reported (key2)"
            print(f"\n✅ OPENAI_API_KEY2 works - Response: {result}, Tokens: {tokens}")

        except Exception as e:
            pytest.fail(f"OPENAI_API_KEY2 connection failed: {e}")

    def test_azure_openai_connection(self):
        """Test connection with Azure OpenAI."""
        from openai import AzureOpenAI

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        assert endpoint is not None, "AZURE_OPENAI_ENDPOINT not set"
        assert api_key is not None, "AZURE_OPENAI_API_KEY not set"

        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=30,
        )

        try:
            # Test with gpt-4o-mini (should be available in Azure)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Say 'azure test' and nothing else."}],
                max_tokens=10,
            )
            result = response.choices[0].message.content
            tokens = response.usage.total_tokens

            assert result is not None, "No response from Azure OpenAI"
            assert tokens > 0, "No token usage reported (Azure)"
            print(f"\n✅ Azure OpenAI works - Response: {result}, Tokens: {tokens}")

        except Exception as e:
            pytest.fail(f"Azure OpenAI connection failed: {e}")


class TestCompletionUtil:
    """Test the completion_util module works correctly."""

    def test_generate_text_function(self):
        """Test generate_text function with automatic provider selection."""
        from virtualoffice.utils.completion_util import generate_text

        try:
            result, tokens = generate_text(
                [{"role": "user", "content": "Say 'hello' and nothing else."}],
                model="gpt-4o-mini"
            )

            assert result is not None, "generate_text returned None"
            assert tokens is not None, "No token count returned"
            assert tokens > 0, "Token count is zero"
            print(f"\n✅ generate_text works - Response: {result}, Tokens: {tokens}")

        except Exception as e:
            pytest.fail(f"generate_text failed: {e}")

    def test_token_tracking_file_exists(self):
        """Test that token_usage.json is created/updated."""
        from virtualoffice.utils.completion_util import generate_text

        # Make a call to ensure token tracking happens
        generate_text(
            [{"role": "user", "content": "test"}],
            model="gpt-4o-mini"
        )

        # Check if token_usage.json exists
        token_file = Path(__file__).parent.parent / "token_usage.json"
        assert token_file.exists(), "token_usage.json was not created"

        # Check if it has valid JSON
        import json
        with open(token_file, "r") as f:
            data = json.load(f)

        assert "daily_usage" in data, "token_usage.json missing 'daily_usage'"
        assert "lifetime_usage" in data, "token_usage.json missing 'lifetime_usage'"
        assert "last_reset_date" in data, "token_usage.json missing 'last_reset_date'"

        print(f"\n✅ Token tracking file exists and is valid")
        print(f"   Daily usage: {data['daily_usage']}")

    def test_model_fallbacks(self):
        """Test that model fallbacks work (gpt-3.5-turbo -> gpt-4o-mini)."""
        from virtualoffice.utils.completion_util import generate_text

        try:
            # Request gpt-3.5-turbo, should fallback to gpt-4o-mini for Azure compatibility
            result, tokens = generate_text(
                [{"role": "user", "content": "Say 'fallback test' and nothing else."}],
                model="gpt-3.5-turbo"
            )

            assert result is not None, "Model fallback failed"
            assert tokens > 0, "No tokens tracked for fallback model"
            print(f"\n✅ Model fallback works - Response: {result}, Tokens: {tokens}")

        except Exception as e:
            pytest.fail(f"Model fallback test failed: {e}")


class TestProviderSelection:
    """Test automatic provider selection logic."""

    def test_provider_selection_respects_free_tier(self):
        """Test that provider selection chooses based on free tier limits."""
        from virtualoffice.utils.completion_util import _choose_provider, _load_token_usage

        # Test with mini model
        provider, use_azure = _choose_provider("gpt-4o-mini")

        # Should choose openai_key1 or openai_key2 if under limit
        data = _load_token_usage()
        if data["daily_usage"]["openai_key1"]["mini"] < 10_000_000:
            assert provider == "openai_key1", "Should prefer openai_key1 for mini models under limit"
            assert use_azure == False, "Should not use Azure when free tier available"
        elif data["daily_usage"]["openai_key2"]["mini"] < 10_000_000:
            assert provider == "openai_key2", "Should use openai_key2 when key1 exhausted"
            assert use_azure == False, "Should not use Azure when free tier available"
        else:
            assert provider == "azure", "Should fallback to Azure when both keys exhausted"
            assert use_azure == True, "Should use Azure as fallback"

        print(f"\n✅ Provider selection logic works - Chose: {provider}, Azure: {use_azure}")

    def test_is_mini_model_detection(self):
        """Test mini/nano model detection."""
        from virtualoffice.utils.completion_util import _is_mini_model

        # Mini models
        assert _is_mini_model("gpt-4o-mini") == True
        assert _is_mini_model("gpt-4.1-mini") == True
        assert _is_mini_model("gpt-5-mini") == True
        assert _is_mini_model("gpt-4.1-nano") == True

        # Regular models
        assert _is_mini_model("gpt-4o") == False
        assert _is_mini_model("gpt-4.1") == False
        assert _is_mini_model("gpt-5") == False
        assert _is_mini_model("gpt-4") == False

        print("\n✅ Mini/nano model detection works")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
