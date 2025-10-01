import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client: Optional[OpenAI] = None
_API_KEY = os.getenv("OPENAI_API_KEY")
_DEFAULT_TIMEOUT = float(os.getenv("VDOS_OPENAI_TIMEOUT", "10"))


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not _API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set the key or enable the stub planner (set VDOS_PLANNER=stub)."
            )
        _client = OpenAI(api_key=_API_KEY, timeout=_DEFAULT_TIMEOUT)
    return _client


def generate_text(prompt: list[dict], model: str = "gpt-3.5-turbo") -> tuple[str, int | None]:
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=prompt,
            timeout=_DEFAULT_TIMEOUT,
        )
    except Exception as exc:  # pragma: no cover - network/credential failure
        raise RuntimeError(f"OpenAI completion failed: {exc}") from exc
    message = response.choices[0].message.content
    tokens = getattr(getattr(response, "usage", None), "total_tokens", None)
    return message, tokens


if __name__ == "__main__":
    client = _get_client()
    print(client.models.list())
    print(
        client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Hello!"},
            ],
            timeout=_DEFAULT_TIMEOUT,
        )
    )
    print("Done")
