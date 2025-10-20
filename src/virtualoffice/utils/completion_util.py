import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI

load_dotenv()

logger = logging.getLogger(__name__)

# Azure configuration
_AVAILABLE_AZURE_MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5-mini",
    "text-embedding-3-large",
    "text-embedding-3-small",
    "text-embedding-ada-002"
]

_AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
_AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
_AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

# OpenAI API keys
_API_KEY = os.getenv("OPENAI_API_KEY")
_API_KEY2 = os.getenv("OPENAI_API_KEY2")
_DEFAULT_TIMEOUT = float(os.getenv("VDOS_OPENAI_TIMEOUT", "120"))

# Model fallbacks
_MODEL_FALLBACKS = {
    "gpt-4.1-nano": "gpt-4o-mini",
    "gpt-3.5-turbo": "gpt-4o-mini",  # gpt-3.5-turbo not available in Azure
}

# Client cache
_client: Optional[OpenAI] = None
_azure_client: Optional[AzureOpenAI] = None

# Token tracking
_TOKEN_USAGE_FILE = Path(__file__).parent.parent.parent.parent / "token_usage.json"

# Free tier limits (daily reset)
# Mini/nano models: 10M tokens/day per API key
# Regular models (gpt-4o, gpt-5): 1M tokens/day per API key
_FREE_TIER_LIMITS = {
    "mini": 10_000_000,  # gpt-4o-mini, gpt-4.1-mini, gpt-5-mini, etc.
    "regular": 1_000_000,  # gpt-4o, gpt-4.1, gpt-5, etc.
}  # Will be set to True if we exceed limit


def _is_mini_model(model: str) -> bool:
    """Check if model is a mini/nano variant."""
    model_lower = model.lower()
    return "mini" in model_lower or "nano" in model_lower


def _load_token_usage() -> dict:
    """Load token usage from file, reset if new day."""
    if not _TOKEN_USAGE_FILE.exists():
        return {
            "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
            "daily_usage": {
                "openai_key1": {"mini": 0, "regular": 0},
                "openai_key2": {"mini": 0, "regular": 0},
                "azure": {"mini": 0, "regular": 0},
            },
            "lifetime_usage": {
                "openai_key1": {"mini": 0, "regular": 0},
                "openai_key2": {"mini": 0, "regular": 0},
                "azure": {"mini": 0, "regular": 0},
            },
        }

    with open(_TOKEN_USAGE_FILE, "r") as f:
        data = json.load(f)

    # Reset daily usage if new day
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("last_reset_date") != today:
        data["last_reset_date"] = today
        data["daily_usage"] = {
            "openai_key1": {"mini": 0, "regular": 0},
            "openai_key2": {"mini": 0, "regular": 0},
            "azure": {"mini": 0, "regular": 0},
        }

    return data


def _save_token_usage(data: dict) -> None:
    """Save token usage to file."""
    with open(_TOKEN_USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _record_tokens(tokens: int, provider: str, model: str) -> None:
    """Record token usage per provider and model type."""
    if tokens is None or tokens <= 0:
        return

    data = _load_token_usage()
    model_type = "mini" if _is_mini_model(model) else "regular"

    # Ensure provider exists in data structure
    if provider not in data["daily_usage"]:
        data["daily_usage"][provider] = {"mini": 0, "regular": 0}
    if provider not in data["lifetime_usage"]:
        data["lifetime_usage"][provider] = {"mini": 0, "regular": 0}

    data["daily_usage"][provider][model_type] += tokens
    data["lifetime_usage"][provider][model_type] += tokens

    _save_token_usage(data)


def _choose_provider(model: str) -> tuple[str, bool]:
    """
    Choose which provider to use based on free tier limits.

    Returns: (provider_name, use_azure)
    provider_name: "openai_key1", "openai_key2", or "azure"
    use_azure: True if should use Azure, False if OpenAI API
    """
    data = _load_token_usage()
    model_type = "mini" if _is_mini_model(model) else "regular"
    limit = _FREE_TIER_LIMITS[model_type]

    # Priority: OPENAI_API_KEY only (Azure disabled per company policy)

    # Check OPENAI_API_KEY (key1)
    if _API_KEY and data["daily_usage"]["openai_key1"][model_type] < limit:
        return ("openai_key1", False)

    # If limit exceeded, still use key1 (will charge - company provided credits)
    if _API_KEY:
        print(f"⚠️  Free tier limit exceeded for {model_type} models. Using OPENAI_API_KEY (company credits).")
        return ("openai_key1", False)

    raise RuntimeError("No API keys configured")


def _get_openai_client(api_key: str) -> OpenAI:
    """Get OpenAI API client."""
    return OpenAI(api_key=api_key, timeout=_DEFAULT_TIMEOUT, max_retries=2)


def _get_azure_client() -> AzureOpenAI:
    """Get Azure OpenAI client."""
    global _azure_client
    if _azure_client is None:
        if not _AZURE_ENDPOINT or not _AZURE_API_KEY:
            raise RuntimeError("Azure OpenAI not configured (missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY)")
        _azure_client = AzureOpenAI(
            azure_endpoint=_AZURE_ENDPOINT,
            api_key=_AZURE_API_KEY,
            api_version=_AZURE_API_VERSION,
            timeout=_DEFAULT_TIMEOUT,
            max_retries=2,
        )
    return _azure_client


def generate_text(prompt: list[dict], model: str = "gpt-4o-mini") -> tuple[str, int | None]:
    """
    Generate text using OpenAI API with automatic provider selection.

    Priority: OPENAI_API_KEY (free tier) -> OPENAI_API_KEY2 (free tier) -> Azure
    """
    # Choose provider based on free tier limits
    provider, use_azure = _choose_provider(model)

    # Apply fallback if model not available
    actual_model = model
    if model in _MODEL_FALLBACKS:
        actual_model = _MODEL_FALLBACKS[model]

    # For Azure, ensure model is in available list
    if use_azure and actual_model not in _AVAILABLE_AZURE_MODELS:
        # Try fallback
        if actual_model in _MODEL_FALLBACKS:
            actual_model = _MODEL_FALLBACKS[actual_model]
        # If still not available, use default
        if actual_model not in _AVAILABLE_AZURE_MODELS:
            actual_model = "gpt-4o-mini"

    start_time = time.time()

    try:
        if use_azure:
            # Azure OpenAI
            client = _get_azure_client()
            response = client.chat.completions.create(
                model=actual_model,  # Use deployment name directly
                messages=prompt,
                timeout=_DEFAULT_TIMEOUT,
            )
        else:
            # OpenAI API (key1 or key2)
            api_key = _API_KEY if provider == "openai_key1" else _API_KEY2
            client = _get_openai_client(api_key)
            response = client.chat.completions.create(
                model=actual_model,
                messages=prompt,
                timeout=_DEFAULT_TIMEOUT,
            )

        # Log slow API calls
        duration = time.time() - start_time
        if duration > 10:
            logger.warning(f"Slow GPT API call: {duration:.1f}s for {actual_model} ({provider})")

    except Exception as exc:
        # Try fallback model
        fb = _MODEL_FALLBACKS.get(model)
        if fb and fb != actual_model:
            try:
                if use_azure:
                    if fb in _AVAILABLE_AZURE_MODELS:
                        response = _get_azure_client().chat.completions.create(
                            model=fb,
                            messages=prompt,
                            timeout=_DEFAULT_TIMEOUT,
                        )
                    else:
                        raise exc
                else:
                    api_key = _API_KEY if provider == "openai_key1" else _API_KEY2
                    response = _get_openai_client(api_key).chat.completions.create(
                        model=fb,
                        messages=prompt,
                        timeout=_DEFAULT_TIMEOUT,
                    )
                actual_model = fb
            except Exception:
                raise RuntimeError(f"OpenAI completion failed: {exc}") from exc
        else:
            raise RuntimeError(f"OpenAI completion failed: {exc}") from exc

    message = response.choices[0].message.content
    tokens = getattr(getattr(response, "usage", None), "total_tokens", None)

    # Record token usage
    if tokens:
        _record_tokens(tokens, provider, actual_model)

    return message, tokens


if __name__ == "__main__":
    # Test the API with a simple call
    result, tokens = generate_text(
        [{"role": "user", "content": "Say hello!"}],
        model="gpt-4o-mini"
    )
    print(f"Response: {result}")
    print(f"Tokens used: {tokens}")
    print("Done")
