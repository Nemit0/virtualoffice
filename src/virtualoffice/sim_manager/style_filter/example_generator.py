"""
Style Example Generator for Communication Style Filter.

This module generates realistic communication style examples during persona creation
using GPT-4o. Examples demonstrate how a persona writes emails and chat messages,
and are used to guide style transformations.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..virtualWorkers.worker import WorkerPersona

from .models import StyleExample

try:
    from ...utils.completion_util import generate_text
except (ImportError, ModuleNotFoundError):  # pragma: no cover

    def generate_text(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError(
            "OpenAI client is not installed; "
            "install optional dependencies to enable style example generation."
        )


logger = logging.getLogger(__name__)


class StyleExampleGenerator:
    """
    Generates communication style examples for personas using GPT-4o.
    
    The generator creates realistic email and chat examples that demonstrate
    a persona's unique writing style based on their role, personality, and
    communication preferences.
    
    Attributes:
        locale: Language locale for example generation ("ko" or "en")
    """

    def __init__(self, locale: str = "ko"):
        """
        Initialize the style example generator.
        
        Args:
            locale: Language locale for prompts and examples (default: "ko" for Korean)
        """
        self.locale = locale
        self._prompt_templates = self._build_prompt_templates()

    def _build_prompt_templates(self) -> dict[str, str]:
        """
        Build locale-specific prompt templates for example generation.
        
        Returns:
            Dictionary mapping locale codes to prompt templates
        """
        korean_prompt = """당신은 가상 직원의 커뮤니케이션 스타일을 정의하는 예시를 생성하는 전문가입니다.

다음 직원의 특성을 바탕으로 5개의 커뮤니케이션 예시를 생성하세요:
- 이름: {name}
- 역할: {role}
- 성격: {personality}
- 커뮤니케이션 스타일: {communication_style}

요구사항:
1. 이메일 5개, 채팅 메시지 5개를 생성하세요 (총 10개)
2. 각 예시는 실제 업무 상황을 반영해야 합니다
3. 공식적인 것과 비공식적인 것을 섞어주세요
4. 각 예시는 최소 50자 이상이어야 합니다
5. 해당 직원의 성격과 스타일이 명확히 드러나야 하고 특징적인 말투를 이용해야 합니다

JSON 형식으로 응답하세요:
{{
  "examples": [
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}}
  ]
}}"""

        english_prompt = """You are an expert at generating communication style examples for virtual employees.

Generate 5 communication examples based on the following employee characteristics:
- Name: {name}
- Role: {role}
- Personality: {personality}
- Communication Style: {communication_style}

Requirements:
1. Generate 5 email examples and 5 chat message examples (10 total)
2. Each example should reflect realistic work situations
3. Mix formal and informal communications appropriately
4. Each example must be at least 50 characters long
5. The employee's personality and style should be clearly evident

Respond in JSON format:
{{
  "examples": [
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "email", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}},
    {{"type": "chat", "content": "..."}}
  ]
}}"""

        return {
            "ko": korean_prompt,
            "en": english_prompt,
        }

    def _get_prompt_template(self) -> str:
        """
        Get the prompt template for the current locale.
        
        Returns:
            Prompt template string
        """
        return self._prompt_templates.get(self.locale, self._prompt_templates["en"])

    async def generate_examples(
        self,
        persona: WorkerPersona,
        count: int = 10,
        max_retries: int = 3,
    ) -> list[StyleExample]:
        """
        Generate style examples based on persona attributes.
        
        Uses GPT-4o to create realistic communication examples that demonstrate
        the persona's unique writing style. The examples are based on the persona's
        role, personality traits, and communication style preferences.
        
        Implements retry logic for transient API failures and comprehensive
        error handling with clear error messages.
        
        Args:
            persona: WorkerPersona with role, personality, communication_style
            count: Number of examples to generate (default: 5)
            max_retries: Maximum number of retry attempts for API failures (default: 3)
            
        Returns:
            List of StyleExample objects with type (email/chat) and content
            
        Raises:
            RuntimeError: If GPT-4o API call fails after retries or response is invalid
            ValueError: If generated examples fail validation
        """
        # Build the prompt from persona attributes
        personality_str = ", ".join(persona.personality) if persona.personality else "전문적"
        
        prompt_template = self._get_prompt_template()
        prompt_text = prompt_template.format(
            name=persona.name,
            role=persona.role,
            personality=personality_str,
            communication_style=persona.communication_style,
        )
        
        # Prepare messages for GPT-4o
        messages = [
            {"role": "system", "content": "You are a helpful assistant that generates realistic workplace communication examples."},
            {"role": "user", "content": prompt_text},
        ]
        
        logger.info(
            f"Generating {count} style examples for persona: {persona.name} ({persona.role})"
        )
        
        # Retry loop for API calls
        last_error = None
        for attempt in range(max_retries):
            try:
                # Call GPT-4o API
                response_text, tokens = generate_text(messages, model="gpt-4o")
                logger.info(
                    f"Generated examples using {tokens} tokens (attempt {attempt + 1}/{max_retries})"
                )
                
                # Parse JSON response
                try:
                    # Extract JSON from response (handle markdown code blocks)
                    response_text = response_text.strip()
                    if response_text.startswith("```json"):
                        response_text = response_text[7:]
                    if response_text.startswith("```"):
                        response_text = response_text[3:]
                    if response_text.endswith("```"):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()
                    
                    data = json.loads(response_text)
                    examples_data = data.get("examples", [])
                    
                    if not examples_data:
                        raise ValueError("No examples found in response")
                    
                    # Create StyleExample objects
                    examples = [
                        StyleExample(type=ex["type"], content=ex["content"])
                        for ex in examples_data
                    ]
                    
                    # Validate examples
                    if not self.validate_examples(examples):
                        raise ValueError(
                            f"Generated examples failed validation. "
                            f"Expected mix of email and chat with minimum 20 characters each."
                        )
                    
                    logger.info(
                        f"Successfully generated and validated {len(examples)} style examples"
                    )
                    return examples
                    
                except (json.JSONDecodeError, KeyError) as e:
                    error_msg = f"Failed to parse GPT-4o response: {e}"
                    logger.error(error_msg)
                    logger.debug(f"Response text: {response_text}")
                    
                    # If this is the last attempt, raise the error
                    if attempt == max_retries - 1:
                        raise RuntimeError(
                            f"Failed to parse style examples after {max_retries} attempts. "
                            f"Last error: {error_msg}"
                        ) from e
                    
                    # Otherwise, retry
                    logger.info(f"Retrying example generation (attempt {attempt + 2}/{max_retries})")
                    last_error = e
                    continue
                    
                except ValueError as e:
                    error_msg = f"Validation failed: {e}"
                    logger.error(error_msg)
                    
                    # If this is the last attempt, raise the error
                    if attempt == max_retries - 1:
                        raise ValueError(
                            f"Generated examples failed validation after {max_retries} attempts. "
                            f"Last error: {error_msg}"
                        ) from e
                    
                    # Otherwise, retry
                    logger.info(f"Retrying example generation (attempt {attempt + 2}/{max_retries})")
                    last_error = e
                    continue
                    
            except RuntimeError as e:
                # API call failed
                error_msg = f"GPT-4o API call failed: {e}"
                logger.error(error_msg)
                
                # If this is the last attempt, raise the error
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Style example generation failed after {max_retries} attempts. "
                        f"Please check your API key and network connection. "
                        f"Last error: {error_msg}"
                    ) from e
                
                # Otherwise, retry with exponential backoff
                import time
                backoff_seconds = 2 ** attempt
                logger.info(
                    f"Retrying in {backoff_seconds}s (attempt {attempt + 2}/{max_retries})"
                )
                time.sleep(backoff_seconds)
                last_error = e
                continue
        
        # Should never reach here, but just in case
        raise RuntimeError(
            f"Style example generation failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def validate_examples(self, examples: list[StyleExample]) -> bool:
        """
        Validate that examples meet minimum quality requirements.
        
        Checks:
        - Minimum length (20 characters per example)
        - Mix of email and chat examples
        - Examples are in correct locale (basic check)
        
        Args:
            examples: List of StyleExample objects to validate
            
        Returns:
            True if all examples are valid, False otherwise
        """
        if not examples:
            logger.warning("No examples to validate")
            return False
        
        # Check minimum length for each example
        for i, example in enumerate(examples):
            if not example.validate():
                logger.warning(
                    f"Example {i} failed validation: "
                    f"content length {len(example.content)} < 20 characters"
                )
                return False
        
        # Check for mix of email and chat examples
        email_count = sum(1 for ex in examples if ex.type == "email")
        chat_count = sum(1 for ex in examples if ex.type == "chat")
        
        if email_count == 0:
            logger.warning("No email examples found")
            return False
        
        if chat_count == 0:
            logger.warning("No chat examples found")
            return False
        
        # Basic locale check - verify examples contain appropriate characters
        if self.locale == "ko":
            # Check if at least some examples contain Korean characters
            has_korean = any(
                any('\uac00' <= char <= '\ud7a3' for char in ex.content)
                for ex in examples
            )
            if not has_korean:
                logger.warning(
                    "Korean locale specified but no Korean characters found in examples"
                )
                # Don't fail validation, just warn - English might be acceptable
        
        logger.info(
            f"Validation passed: {len(examples)} examples "
            f"({email_count} email, {chat_count} chat)"
        )
        return True
