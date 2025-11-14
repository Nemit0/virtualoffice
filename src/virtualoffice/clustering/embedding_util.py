"""
OpenAI Embeddings API wrapper with caching and batch processing.

Reuses the API key management from completion_util.py but specialized for embeddings.
"""

import logging
from typing import Optional
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

# API Configuration (reuse from completion_util pattern)
_API_KEY = os.getenv("OPENAI_API_KEY")
_DEFAULT_TIMEOUT = float(os.getenv("VDOS_OPENAI_TIMEOUT", "120"))

# Client cache
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        if not _API_KEY:
            raise ValueError("OPENAI_API_KEY not set in environment")
        _client = OpenAI(api_key=_API_KEY, timeout=_DEFAULT_TIMEOUT)
    return _client


def generate_embedding(
    text: str, model: str = "text-embedding-3-small"
) -> tuple[list[float], int]:
    """
    Generate embedding vector for text using OpenAI API.

    Args:
        text: Text to embed
        model: Embedding model to use (default: text-embedding-3-small, 1536 dims)

    Returns:
        Tuple of (embedding_vector, tokens_used)

    Raises:
        ValueError: If text is empty
        openai.OpenAIError: If API call fails
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text")

    client = _get_client()

    try:
        response = client.embeddings.create(input=text, model=model, encoding_format="float")

        embedding = response.data[0].embedding
        tokens_used = response.usage.total_tokens

        logger.info(
            f"Generated embedding for text ({len(text)} chars) using {model}, "
            f"tokens: {tokens_used}, dim: {len(embedding)}"
        )

        return embedding, tokens_used

    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        raise


def generate_embeddings_batch(
    texts: list[str], model: str = "text-embedding-3-small", batch_size: int = 100
) -> tuple[list[list[float]], int]:
    """
    Generate embeddings for multiple texts in batches.

    OpenAI API allows up to 2048 inputs per request, but we use smaller batches
    for better error handling and progress tracking.

    Args:
        texts: List of texts to embed
        model: Embedding model to use
        batch_size: Number of texts per API call (max 2048)

    Returns:
        Tuple of (list of embedding vectors, total tokens used)

    Raises:
        ValueError: If texts list is empty
        openai.OpenAIError: If API call fails
    """
    if not texts:
        raise ValueError("Cannot generate embeddings for empty text list")

    client = _get_client()
    all_embeddings = []
    total_tokens = 0

    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(texts) + batch_size - 1) // batch_size

        try:
            response = client.embeddings.create(
                input=batch, model=model, encoding_format="float"
            )

            # Extract embeddings in order
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

            batch_tokens = response.usage.total_tokens
            total_tokens += batch_tokens

            logger.info(
                f"Generated embeddings batch {batch_num}/{total_batches}: "
                f"{len(batch)} texts, {batch_tokens} tokens"
            )

        except Exception as e:
            logger.error(f"Failed to generate embeddings for batch {batch_num}: {e}")
            raise

    logger.info(
        f"Completed batch embedding generation: {len(texts)} texts, "
        f"{total_tokens} total tokens, model: {model}"
    )

    return all_embeddings, total_tokens


def get_embedding_dimension(model: str = "text-embedding-3-small") -> int:
    """
    Get dimension of embedding vectors for a model.

    Args:
        model: Embedding model name

    Returns:
        Dimension of embedding vectors
    """
    dimensions = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    return dimensions.get(model, 1536)


def prepare_email_text_for_embedding(subject: str, body: str) -> str:
    """
    Prepare email text for embedding generation.

    Combines subject and body in a format that captures email semantics.

    Args:
        subject: Email subject line
        body: Email body text

    Returns:
        Formatted text for embedding
    """
    # Simple concatenation with separator
    # Future: Could add more sophisticated preprocessing
    # - Remove signatures
    # - Remove quoted text
    # - Normalize whitespace
    return f"Subject: {subject}\n\n{body}"


# Optional: Embedding cache for avoiding duplicate API calls
# This would be implemented with a SQLite or in-memory cache
# For MVP, we rely on the FAISS storage acting as our cache
