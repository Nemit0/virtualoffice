"""
Unit tests for StyleExampleGenerator.

Tests example generation with various persona types, validation logic,
locale-specific generation, and error handling with mocked GPT-4o responses.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from virtualoffice.sim_manager.style_filter.example_generator import StyleExampleGenerator
from virtualoffice.sim_manager.style_filter.models import StyleExample


# Mock WorkerPersona for testing
class MockWorkerPersona:
    def __init__(self, name, role, personality, communication_style):
        self.name = name
        self.role = role
        self.personality = personality
        self.communication_style = communication_style


class TestStyleExampleGenerator:
    """Test suite for StyleExampleGenerator."""

    def test_initialization_korean_locale(self):
        """Test generator initialization with Korean locale."""
        generator = StyleExampleGenerator(locale="ko")
        assert generator.locale == "ko"
        assert "ko" in generator._prompt_templates
        assert "당신은 가상 직원의" in generator._prompt_templates["ko"]

    def test_initialization_english_locale(self):
        """Test generator initialization with English locale."""
        generator = StyleExampleGenerator(locale="en")
        assert generator.locale == "en"
        assert "en" in generator._prompt_templates
        assert "You are an expert" in generator._prompt_templates["en"]

    def test_get_prompt_template_korean(self):
        """Test prompt template retrieval for Korean locale."""
        generator = StyleExampleGenerator(locale="ko")
        template = generator._get_prompt_template()
        assert "당신은 가상 직원의" in template
        assert "{name}" in template
        assert "{role}" in template

    def test_get_prompt_template_english(self):
        """Test prompt template retrieval for English locale."""
        generator = StyleExampleGenerator(locale="en")
        template = generator._get_prompt_template()
        assert "You are an expert" in template
        assert "{name}" in template
        assert "{role}" in template

    def test_get_prompt_template_fallback(self):
        """Test prompt template fallback for unknown locale."""
        generator = StyleExampleGenerator(locale="fr")
        template = generator._get_prompt_template()
        # Should fallback to English
        assert "You are an expert" in template

    def test_validate_examples_valid(self):
        """Test validation with valid examples."""
        generator = StyleExampleGenerator()
        examples = [
            StyleExample(type="email", content="This is a valid email example with enough characters."),
            StyleExample(type="email", content="Another valid email example for testing purposes."),
            StyleExample(type="email", content="Third email example with sufficient length."),
            StyleExample(type="chat", content="Valid chat message example."),
            StyleExample(type="chat", content="Another chat example here."),
        ]
        assert generator.validate_examples(examples) is True

    def test_validate_examples_empty_list(self):
        """Test validation with empty example list."""
        generator = StyleExampleGenerator()
        assert generator.validate_examples([]) is False

    def test_validate_examples_too_short(self):
        """Test validation with examples that are too short."""
        generator = StyleExampleGenerator()
        examples = [
            StyleExample(type="email", content="Too short"),  # Less than 20 chars
            StyleExample(type="chat", content="Valid chat message example."),
        ]
        assert generator.validate_examples(examples) is False

    def test_validate_examples_no_email(self):
        """Test validation with no email examples."""
        generator = StyleExampleGenerator()
        examples = [
            StyleExample(type="chat", content="Valid chat message example one."),
            StyleExample(type="chat", content="Valid chat message example two."),
        ]
        assert generator.validate_examples(examples) is False

    def test_validate_examples_no_chat(self):
        """Test validation with no chat examples."""
        generator = StyleExampleGenerator()
        examples = [
            StyleExample(type="email", content="Valid email example one with enough characters."),
            StyleExample(type="email", content="Valid email example two with enough characters."),
        ]
        assert generator.validate_examples(examples) is False

    def test_validate_examples_korean_locale(self):
        """Test validation with Korean locale and Korean content."""
        generator = StyleExampleGenerator(locale="ko")
        examples = [
            StyleExample(type="email", content="안녕하세요, 이것은 한국어 이메일 예시입니다."),
            StyleExample(type="email", content="프로젝트 진행 상황을 공유드립니다. 감사합니다."),
            StyleExample(type="email", content="회의 일정을 확인해 주시기 바랍니다."),
            StyleExample(type="chat", content="네, 확인했습니다! 감사합니다. 좋습니다."),
            StyleExample(type="chat", content="오늘 오후에 회의 가능하신가요? 알려주세요."),
        ]
        assert generator.validate_examples(examples) is True

    def test_validate_examples_korean_locale_no_korean_chars(self):
        """Test validation warns when Korean locale but no Korean characters."""
        generator = StyleExampleGenerator(locale="ko")
        examples = [
            StyleExample(type="email", content="This is an English email example."),
            StyleExample(type="chat", content="English chat message."),
        ]
        # Should still pass validation but log a warning
        assert generator.validate_examples(examples) is True

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_success(self, mock_generate_text):
        """Test successful example generation with mocked GPT-4o response."""
        # Mock GPT-4o response
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Professional email example with formal tone and structure."},
                {"type": "email", "content": "Another email showing consistent communication style."},
                {"type": "email", "content": "Third email example demonstrating personality traits."},
                {"type": "chat", "content": "Quick chat message showing informal style."},
                {"type": "chat", "content": "Another chat with personality."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 150)

        generator = StyleExampleGenerator(locale="en")
        persona = MockWorkerPersona(
            name="John Doe",
            role="Software Engineer",
            personality=["analytical", "detail-oriented"],
            communication_style="concise and technical"
        )

        examples = await generator.generate_examples(persona)

        assert len(examples) == 5
        assert sum(1 for ex in examples if ex.type == "email") == 3
        assert sum(1 for ex in examples if ex.type == "chat") == 2
        assert all(ex.validate() for ex in examples)
        mock_generate_text.assert_called_once()

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_korean_persona(self, mock_generate_text):
        """Test example generation for Korean persona."""
        # Mock Korean GPT-4o response
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "안녕하세요, 프로젝트 진행 상황을 공유드립니다."},
                {"type": "email", "content": "회의 일정을 확인해 주시기 바랍니다. 감사합니다."},
                {"type": "email", "content": "보고서를 첨부 파일로 보내드립니다. 확인 부탁드립니다."},
                {"type": "chat", "content": "네, 확인했습니다! 감사합니다. 좋습니다."},
                {"type": "chat", "content": "오늘 오후 3시에 가능하신가요? 알려주세요."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 180)

        generator = StyleExampleGenerator(locale="ko")
        persona = MockWorkerPersona(
            name="김철수",
            role="프로젝트 매니저",
            personality=["책임감 있는", "협력적인"],
            communication_style="공손하고 명확한"
        )

        examples = await generator.generate_examples(persona)

        assert len(examples) == 5
        assert all(ex.validate() for ex in examples)
        # Verify Korean characters present
        assert any('\uac00' <= char <= '\ud7a3' for ex in examples for char in ex.content)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_with_markdown_code_blocks(self, mock_generate_text):
        """Test example generation handles markdown code blocks in response."""
        # Mock response with markdown code blocks
        mock_response = """```json
{
  "examples": [
    {"type": "email", "content": "Email example one with sufficient length."},
    {"type": "email", "content": "Email example two with sufficient length."},
    {"type": "email", "content": "Email example three with sufficient length."},
    {"type": "chat", "content": "Chat example one here."},
    {"type": "chat", "content": "Chat example two here."}
  ]
}
```"""
        mock_generate_text.return_value = (mock_response, 160)

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        examples = await generator.generate_examples(persona)

        assert len(examples) == 5
        assert all(ex.validate() for ex in examples)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_invalid_json(self, mock_generate_text):
        """Test example generation handles invalid JSON response."""
        # Mock invalid JSON response
        mock_generate_text.return_value = ("This is not valid JSON", 50)

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        with pytest.raises(RuntimeError, match="Failed to parse style examples"):
            await generator.generate_examples(persona, max_retries=1)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_missing_examples_key(self, mock_generate_text):
        """Test example generation handles response missing 'examples' key."""
        # Mock response without examples key
        mock_response = json.dumps({"data": []})
        mock_generate_text.return_value = (mock_response, 50)

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        with pytest.raises(ValueError, match="failed validation"):
            await generator.generate_examples(persona, max_retries=1)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_validation_failure(self, mock_generate_text):
        """Test example generation handles validation failures."""
        # Mock response with invalid examples (too short)
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Short"},  # Too short
                {"type": "chat", "content": "Also short"},  # Too short
            ]
        })
        mock_generate_text.return_value = (mock_response, 50)

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        with pytest.raises(ValueError, match="failed validation"):
            await generator.generate_examples(persona, max_retries=1)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_api_failure(self, mock_generate_text):
        """Test example generation handles API failures."""
        # Mock API failure
        mock_generate_text.side_effect = RuntimeError("API connection failed")

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        with pytest.raises(RuntimeError, match="Style example generation failed"):
            await generator.generate_examples(persona, max_retries=2)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_retry_logic(self, mock_generate_text):
        """Test example generation retry logic on transient failures."""
        # First call fails, second succeeds
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Valid email example with enough characters."},
                {"type": "email", "content": "Another valid email example here."},
                {"type": "email", "content": "Third email example for testing."},
                {"type": "chat", "content": "Valid chat message here."},
                {"type": "chat", "content": "Another chat message here."},
            ]
        })
        
        # Use a list to track calls and return appropriate values
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Temporary failure")
            return (mock_response, 150)
        
        mock_generate_text.side_effect = side_effect

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        examples = await generator.generate_examples(persona, max_retries=3)

        assert len(examples) == 5
        assert mock_generate_text.call_count == 2

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_different_persona_types(self, mock_generate_text):
        """Test example generation with various persona types."""
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Manager email with leadership tone and clear direction."},
                {"type": "email", "content": "Strategic email discussing project goals."},
                {"type": "email", "content": "Team coordination email with action items."},
                {"type": "chat", "content": "Quick check-in message."},
                {"type": "chat", "content": "Team encouragement message."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 170)

        generator = StyleExampleGenerator(locale="en")
        
        # Test with manager persona
        manager = MockWorkerPersona(
            name="Jane Manager",
            role="Engineering Manager",
            personality=["strategic", "supportive"],
            communication_style="clear and motivating"
        )

        examples = await generator.generate_examples(manager)
        assert len(examples) == 5
        assert all(ex.validate() for ex in examples)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_generate_examples_custom_count(self, mock_generate_text):
        """Test example generation with custom count parameter."""
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Email example one with sufficient length."},
                {"type": "email", "content": "Email example two with sufficient length."},
                {"type": "chat", "content": "Chat example one here."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 120)

        generator = StyleExampleGenerator()
        persona = MockWorkerPersona(
            name="Test User",
            role="Tester",
            personality=["thorough"],
            communication_style="clear"
        )

        # Note: count parameter is passed but actual count depends on GPT response
        examples = await generator.generate_examples(persona, count=3)
        assert len(examples) == 3
