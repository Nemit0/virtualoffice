"""
Communication Style Filter for message transformation.

This module implements the core style filter that transforms generated messages
using persona-specific style examples and GPT-4o. The filter operates as a
post-processing layer in the message generation pipeline.
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlite3 import Connection

from .models import FilterResult, StyleExample
from .metrics import FilterMetrics

try:
    from ...utils.completion_util import generate_text
except (ImportError, ModuleNotFoundError):  # pragma: no cover

    def generate_text(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError(
            "OpenAI client is not installed; "
            "install optional dependencies to enable style filtering."
        )


logger = logging.getLogger(__name__)


class CommunicationStyleFilter:
    """
    Transforms messages using persona-specific communication styles.
    
    The filter uses GPT-4o to rewrite generated messages in the style of
    a specific persona, based on example communications stored in the database.
    It supports both global and per-persona enable/disable controls.
    
    Attributes:
        db_connection: SQLite database connection
        locale: Language locale for prompts ("ko" or "en")
        enabled: Global filter enable flag
    """

    def __init__(
        self,
        db_connection: Connection,
        locale: str = "ko",
        enabled: bool = True,
        metrics: FilterMetrics | None = None,
    ):
        """
        Initialize the communication style filter.
        
        Args:
            db_connection: SQLite database connection for querying style examples
            locale: Language locale for prompts (default: "ko" for Korean)
            enabled: Global filter enable flag (default: True)
            metrics: Optional FilterMetrics instance for tracking (creates new if None)
        """
        self.db_connection = db_connection
        self.locale = locale
        self._global_enabled = enabled
        self._example_cache: dict[int, list[StyleExample]] = {}
        self._prompt_templates = self._build_prompt_templates()
        self.metrics = metrics or FilterMetrics(db_connection)

    def _build_prompt_templates(self) -> dict[str, str]:
        """
        Build locale-specific prompt templates for message transformation.
        
        Returns:
            Dictionary mapping locale codes to prompt templates
        """
        korean_prompt = """다음 주어진 사용자 입력을 예시 채팅/이메일 어투로 다시 작성하세요.

예시 커뮤니케이션 스타일:

{examples}

위 예시들의 어투와 스타일을 참고하여, 사용자가 제공한 메시지를 동일한 스타일로 다시 작성하세요.
재작성된 메시지만 출력하고, 다른 설명이나 주석은 포함하지 마세요."""

        english_prompt = """Rewrite the user's message in the style of the following example communications.

Example communication style:

{examples}

Using the tone and style from the examples above, rewrite the user's message in the same style.
Output only the rewritten message without any additional commentary or notes."""

        return {
            "ko": korean_prompt,
            "en": english_prompt,
        }

    def is_enabled(self) -> bool:
        """
        Check if the filter is globally enabled.
        
        Returns:
            True if filter is enabled, False otherwise
        """
        return self._global_enabled

    def _is_persona_enabled(self, persona_id: int) -> bool:
        """
        Check if the filter is enabled for a specific persona.
        
        Args:
            persona_id: ID of the persona to check
            
        Returns:
            True if filter is enabled for this persona, False otherwise
        """
        try:
            cursor = self.db_connection.execute(
                "SELECT style_filter_enabled FROM people WHERE id = ?",
                (persona_id,)
            )
            row = cursor.fetchone()
            if row is None:
                logger.warning(f"Persona {persona_id} not found in database")
                return False
            return bool(row[0])
        except sqlite3.Error as e:
            logger.error(f"Database error checking persona filter status: {e}")
            return False

    async def get_style_examples(self, persona_id: int) -> list[StyleExample]:
        """
        Fetch style examples for a persona from the database.
        
        Queries the people table for style_examples by persona_id, parses the
        JSON, and creates StyleExample objects. Results are cached in memory
        for performance.
        
        Args:
            persona_id: ID of the persona
            
        Returns:
            List of StyleExample objects
            
        Raises:
            ValueError: If persona not found or examples are invalid
        """
        # Check cache first
        if persona_id in self._example_cache:
            logger.debug(f"Using cached style examples for persona {persona_id}")
            return self._example_cache[persona_id]

        try:
            cursor = self.db_connection.execute(
                "SELECT style_examples FROM people WHERE id = ?",
                (persona_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                raise ValueError(f"Persona {persona_id} not found in database")
            
            examples_json = row[0]
            
            # Parse JSON and create StyleExample objects
            if not examples_json or examples_json == "[]":
                logger.warning(f"No style examples found for persona {persona_id}")
                return []
            
            examples_data = json.loads(examples_json)
            examples = [
                StyleExample(type=ex["type"], content=ex["content"])
                for ex in examples_data
            ]
            
            # Validate examples
            if not examples:
                logger.warning(f"Empty style examples for persona {persona_id}")
                return []
            
            # Cache the examples
            self._example_cache[persona_id] = examples
            logger.debug(
                f"Loaded and cached {len(examples)} style examples for persona {persona_id}"
            )
            
            return examples
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse style examples JSON for persona {persona_id}: {e}")
            raise ValueError(f"Invalid style examples JSON for persona {persona_id}") from e
        except sqlite3.Error as e:
            logger.error(f"Database error fetching style examples: {e}")
            raise ValueError(f"Database error fetching style examples") from e

    def _build_filter_prompt(
        self,
        examples: list[StyleExample],
        message_type: str,
    ) -> str:
        """
        Build system prompt with randomly sampled style examples.
        
        Randomly samples 3 examples from the provided list to introduce
        variability and reduce token usage while maintaining style consistency.
        
        Args:
            examples: List of available style examples
            message_type: Type of message ("email" or "chat")
            
        Returns:
            System prompt string with formatted examples
        """
        # Randomly sample 3 examples from available examples
        sample_size = min(3, len(examples))
        sampled_examples = random.sample(examples, sample_size)
        
        # Format examples with line breaks
        formatted_examples = "\n\n".join(
            f"{ex.content}" for ex in sampled_examples
        )
        
        # Get prompt template for locale
        template = self._prompt_templates.get(self.locale, self._prompt_templates["en"])
        
        # Build final prompt
        prompt = template.format(examples=formatted_examples)
        
        logger.debug(
            f"Built filter prompt with {sample_size} sampled examples "
            f"(from {len(examples)} available) for {message_type}"
        )
        
        return prompt

    async def apply_filter(
        self,
        message: str,
        persona_id: int,
        message_type: Literal["email", "chat"],
    ) -> FilterResult:
        """
        Apply style filter to a message.
        
        Checks if filter is enabled (global and per-persona), fetches style
        examples, builds filter prompt with random sampling, calls GPT-4o API,
        and extracts the styled message from the response.
        
        Falls back to original message on any failure.
        
        Args:
            message: Original generated message content
            persona_id: ID of the persona sending the message
            message_type: Type of message ("email" or "chat")
            
        Returns:
            FilterResult with styled_message, tokens_used, latency_ms, success status
        """
        start_time = time.time()
        
        # Check if filter is enabled globally
        if not self.is_enabled():
            logger.debug("Style filter is globally disabled")
            return FilterResult(
                styled_message=message,
                original_message=message,
                tokens_used=0,
                latency_ms=0.0,
                success=True,
                error="Filter disabled globally",
            )
        
        # Check if filter is enabled for this persona
        if not self._is_persona_enabled(persona_id):
            logger.debug(f"Style filter is disabled for persona {persona_id}")
            return FilterResult(
                styled_message=message,
                original_message=message,
                tokens_used=0,
                latency_ms=0.0,
                success=True,
                error="Filter disabled for persona",
            )
        
        try:
            # Fetch style examples for persona
            examples = await self.get_style_examples(persona_id)
            
            if not examples:
                logger.warning(
                    f"No style examples available for persona {persona_id}, "
                    "using original message"
                )
                return FilterResult(
                    styled_message=message,
                    original_message=message,
                    tokens_used=0,
                    latency_ms=(time.time() - start_time) * 1000,
                    success=True,
                    error="No style examples available",
                )
            
            # Build filter prompt with random sampling
            system_prompt = self._build_filter_prompt(examples, message_type)
            
            # Prepare messages for GPT-4o
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            
            logger.info(
                f"Applying style filter for persona {persona_id} ({message_type})"
            )
            
            # Call GPT-4o API
            try:
                styled_message, tokens = generate_text(messages, model="gpt-4o")
                
                # Extract styled message (remove any markdown or commentary)
                styled_message = styled_message.strip()
                
                # Remove markdown code blocks if present
                if styled_message.startswith("```"):
                    lines = styled_message.split("\n")
                    styled_message = "\n".join(lines[1:-1]).strip()
                
                latency_ms = (time.time() - start_time) * 1000
                
                logger.info(
                    f"Style filter applied successfully: {tokens} tokens, "
                    f"{latency_ms:.1f}ms"
                )
                
                # Record metrics
                await self.metrics.record_transformation(
                    persona_id=persona_id,
                    message_type=message_type,
                    tokens_used=tokens or 0,
                    latency_ms=latency_ms,
                    success=True,
                )
                
                return FilterResult(
                    styled_message=styled_message,
                    original_message=message,
                    tokens_used=tokens or 0,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                )
                
            except RuntimeError as e:
                # API call failed
                error_msg = f"GPT-4o API call failed: {e}"
                logger.error(error_msg)
                
                latency_ms = (time.time() - start_time) * 1000
                
                # Record failure metrics
                await self.metrics.record_transformation(
                    persona_id=persona_id,
                    message_type=message_type,
                    tokens_used=0,
                    latency_ms=latency_ms,
                    success=False,
                )
                
                return FilterResult(
                    styled_message=message,  # Fallback to original
                    original_message=message,
                    tokens_used=0,
                    latency_ms=latency_ms,
                    success=False,
                    error=error_msg,
                )
                
        except Exception as e:
            # Unexpected error - log and fallback
            error_msg = f"Unexpected error in style filter: {e}"
            logger.error(
                error_msg,
                extra={
                    "persona_id": persona_id,
                    "message_type": message_type,
                },
                exc_info=True,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Record failure metrics
            await self.metrics.record_transformation(
                persona_id=persona_id,
                message_type=message_type,
                tokens_used=0,
                latency_ms=latency_ms,
                success=False,
            )
            
            return FilterResult(
                styled_message=message,  # Fallback to original
                original_message=message,
                tokens_used=0,
                latency_ms=latency_ms,
                success=False,
                error=error_msg,
            )
