"""
Unit tests for CommunicationStyleFilter.

Tests filter application with valid examples, random sampling, fallback behavior
on API failure, and enable/disable toggle functionality.
"""

import json
import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

from virtualoffice.sim_manager.style_filter.filter import CommunicationStyleFilter
from virtualoffice.sim_manager.style_filter.models import StyleExample, FilterResult
from virtualoffice.sim_manager.style_filter.metrics import FilterMetrics


@pytest.fixture
def db_connection():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    
    # Create people table
    conn.execute("""
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            style_examples TEXT NOT NULL DEFAULT '[]',
            style_filter_enabled INTEGER NOT NULL DEFAULT 1
        )
    """)
    
    # Create style_filter_metrics table
    conn.execute("""
        CREATE TABLE style_filter_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id INTEGER NOT NULL,
            message_type TEXT NOT NULL,
            tokens_used INTEGER NOT NULL,
            latency_ms REAL NOT NULL,
            success INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(persona_id) REFERENCES people(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sample_style_examples():
    """Create sample style examples for testing."""
    return [
        StyleExample(type="email", content="Professional email with formal tone and clear structure."),
        StyleExample(type="email", content="Another email showing consistent communication style."),
        StyleExample(type="email", content="Third email example demonstrating personality traits."),
        StyleExample(type="chat", content="Quick chat message showing informal style."),
        StyleExample(type="chat", content="Another chat with personality and brevity."),
    ]


class TestCommunicationStyleFilter:
    """Test suite for CommunicationStyleFilter."""

    def test_initialization(self, db_connection):
        """Test filter initialization with default parameters."""
        filter_obj = CommunicationStyleFilter(db_connection)
        assert filter_obj.db_connection == db_connection
        assert filter_obj.locale == "ko"
        assert filter_obj.is_enabled() is True
        assert isinstance(filter_obj.metrics, FilterMetrics)

    def test_initialization_custom_locale(self, db_connection):
        """Test filter initialization with custom locale."""
        filter_obj = CommunicationStyleFilter(db_connection, locale="en")
        assert filter_obj.locale == "en"

    def test_initialization_disabled(self, db_connection):
        """Test filter initialization with disabled state."""
        filter_obj = CommunicationStyleFilter(db_connection, enabled=False)
        assert filter_obj.is_enabled() is False

    def test_is_enabled(self, db_connection):
        """Test global enable/disable check."""
        filter_obj = CommunicationStyleFilter(db_connection, enabled=True)
        assert filter_obj.is_enabled() is True
        
        filter_obj._global_enabled = False
        assert filter_obj.is_enabled() is False

    def test_is_persona_enabled(self, db_connection):
        """Test per-persona enable/disable check."""
        # Insert test persona
        db_connection.execute(
            "INSERT INTO people (id, name, style_filter_enabled) VALUES (?, ?, ?)",
            (1, "Test User", 1)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        assert filter_obj._is_persona_enabled(1) is True

    def test_is_persona_disabled(self, db_connection):
        """Test per-persona disabled state."""
        # Insert test persona with filter disabled
        db_connection.execute(
            "INSERT INTO people (id, name, style_filter_enabled) VALUES (?, ?, ?)",
            (1, "Test User", 0)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        assert filter_obj._is_persona_enabled(1) is False

    def test_is_persona_enabled_not_found(self, db_connection):
        """Test per-persona check with non-existent persona."""
        filter_obj = CommunicationStyleFilter(db_connection)
        assert filter_obj._is_persona_enabled(999) is False

    @pytest.mark.asyncio
    async def test_get_style_examples(self, db_connection, sample_style_examples):
        """Test fetching style examples from database."""
        # Insert test persona with style examples
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples) VALUES (?, ?, ?)",
            (1, "Test User", examples_json)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        examples = await filter_obj.get_style_examples(1)
        
        assert len(examples) == 5
        assert all(isinstance(ex, StyleExample) for ex in examples)
        assert examples[0].content == sample_style_examples[0].content

    @pytest.mark.asyncio
    async def test_get_style_examples_caching(self, db_connection, sample_style_examples):
        """Test that style examples are cached after first fetch."""
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples) VALUES (?, ?, ?)",
            (1, "Test User", examples_json)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        
        # First fetch
        examples1 = await filter_obj.get_style_examples(1)
        # Second fetch should use cache
        examples2 = await filter_obj.get_style_examples(1)
        
        assert examples1 == examples2
        assert 1 in filter_obj._example_cache

    @pytest.mark.asyncio
    async def test_get_style_examples_empty(self, db_connection):
        """Test fetching style examples when none exist."""
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples) VALUES (?, ?, ?)",
            (1, "Test User", "[]")
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        examples = await filter_obj.get_style_examples(1)
        
        assert examples == []

    @pytest.mark.asyncio
    async def test_get_style_examples_not_found(self, db_connection):
        """Test fetching style examples for non-existent persona."""
        filter_obj = CommunicationStyleFilter(db_connection)
        
        with pytest.raises(ValueError, match="not found"):
            await filter_obj.get_style_examples(999)

    @pytest.mark.asyncio
    async def test_get_style_examples_invalid_json(self, db_connection):
        """Test fetching style examples with invalid JSON."""
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples) VALUES (?, ?, ?)",
            (1, "Test User", "invalid json")
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        
        with pytest.raises(ValueError, match="Invalid style examples JSON"):
            await filter_obj.get_style_examples(1)

    def test_build_filter_prompt_korean(self, db_connection, sample_style_examples):
        """Test building filter prompt with Korean locale."""
        filter_obj = CommunicationStyleFilter(db_connection, locale="ko")
        prompt = filter_obj._build_filter_prompt(sample_style_examples, "email")
        
        assert "다음 주어진 사용자 입력을" in prompt
        assert "예시 커뮤니케이션 스타일:" in prompt
        # Should contain sampled examples
        assert any(ex.content in prompt for ex in sample_style_examples)

    def test_build_filter_prompt_english(self, db_connection, sample_style_examples):
        """Test building filter prompt with English locale."""
        filter_obj = CommunicationStyleFilter(db_connection, locale="en")
        prompt = filter_obj._build_filter_prompt(sample_style_examples, "email")
        
        assert "Rewrite the user's message" in prompt
        assert "Example communication style:" in prompt
        # Should contain sampled examples
        assert any(ex.content in prompt for ex in sample_style_examples)

    def test_build_filter_prompt_random_sampling(self, db_connection, sample_style_examples):
        """Test that filter prompt randomly samples 3 from 5 examples."""
        filter_obj = CommunicationStyleFilter(db_connection)
        
        # Generate multiple prompts and verify sampling
        prompts = [
            filter_obj._build_filter_prompt(sample_style_examples, "email")
            for _ in range(10)
        ]
        
        # Each prompt should contain exactly 3 examples
        for prompt in prompts:
            example_count = sum(1 for ex in sample_style_examples if ex.content in prompt)
            assert example_count == 3

    def test_build_filter_prompt_fewer_than_3_examples(self, db_connection):
        """Test building filter prompt with fewer than 3 examples."""
        examples = [
            StyleExample(type="email", content="Only one example available here."),
        ]
        
        filter_obj = CommunicationStyleFilter(db_connection)
        prompt = filter_obj._build_filter_prompt(examples, "email")
        
        # Should include the single example
        assert examples[0].content in prompt

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_apply_filter_success(self, mock_generate_text, db_connection, sample_style_examples):
        """Test successful filter application."""
        # Setup database
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o response
        mock_generate_text.return_value = ("Styled message with personality", 80)
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        assert result.success is True
        assert result.styled_message == "Styled message with personality"
        assert result.original_message == "Original message"
        assert result.tokens_used == 80
        assert result.latency_ms >= 0  # Changed from > 0 to >= 0 since it can be very fast
        assert result.error is None

    @pytest.mark.asyncio
    async def test_apply_filter_globally_disabled(self, db_connection):
        """Test filter application when globally disabled."""
        filter_obj = CommunicationStyleFilter(db_connection, enabled=False)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        assert result.success is True
        assert result.styled_message == "Original message"
        assert result.tokens_used == 0
        assert result.error == "Filter disabled globally"

    @pytest.mark.asyncio
    async def test_apply_filter_persona_disabled(self, db_connection):
        """Test filter application when disabled for specific persona."""
        # Insert persona with filter disabled
        db_connection.execute(
            "INSERT INTO people (id, name, style_filter_enabled) VALUES (?, ?, ?)",
            (1, "Test User", 0)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        assert result.success is True
        assert result.styled_message == "Original message"
        assert result.tokens_used == 0
        assert result.error == "Filter disabled for persona"

    @pytest.mark.asyncio
    async def test_apply_filter_no_examples(self, db_connection):
        """Test filter application when no style examples available."""
        # Insert persona with no examples
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", "[]", 1)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        assert result.success is True
        assert result.styled_message == "Original message"
        assert result.tokens_used == 0
        assert result.error == "No style examples available"

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_apply_filter_api_failure(self, mock_generate_text, db_connection, sample_style_examples):
        """Test filter fallback behavior on API failure."""
        # Setup database
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock API failure
        mock_generate_text.side_effect = RuntimeError("API connection failed")
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        # Should fallback to original message
        assert result.success is False
        assert result.styled_message == "Original message"
        assert result.tokens_used == 0
        assert "API connection failed" in result.error

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_apply_filter_removes_markdown(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that filter removes markdown code blocks from response."""
        # Setup database
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock response with markdown
        mock_generate_text.return_value = ("```\nStyled message\n```", 80)
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        assert result.success is True
        assert result.styled_message == "Styled message"
        assert "```" not in result.styled_message

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_apply_filter_email_type(self, mock_generate_text, db_connection, sample_style_examples):
        """Test filter application for email message type."""
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", examples_json, 1)
        )
        db_connection.commit()
        
        mock_generate_text.return_value = ("Styled email message", 90)
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original email",
            persona_id=1,
            message_type="email"
        )
        
        assert result.success is True
        assert result.styled_message == "Styled email message"

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_apply_filter_chat_type(self, mock_generate_text, db_connection, sample_style_examples):
        """Test filter application for chat message type."""
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", examples_json, 1)
        )
        db_connection.commit()
        
        mock_generate_text.return_value = ("Styled chat message", 70)
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original chat",
            persona_id=1,
            message_type="chat"
        )
        
        assert result.success is True
        assert result.styled_message == "Styled chat message"

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_apply_filter_metrics_recorded(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that filter records metrics on transformation."""
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", examples_json, 1)
        )
        db_connection.commit()
        
        mock_generate_text.return_value = ("Styled message", 85)
        
        filter_obj = CommunicationStyleFilter(db_connection)
        await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        # Flush metrics to database
        await filter_obj.metrics._flush_batch()
        
        # Verify metrics were recorded
        cursor = db_connection.execute(
            "SELECT COUNT(*) FROM style_filter_metrics WHERE persona_id = ?",
            (1,)
        )
        count = cursor.fetchone()[0]
        assert count == 1

    @pytest.mark.asyncio
    async def test_apply_filter_unexpected_error(self, db_connection):
        """Test filter handles unexpected errors gracefully."""
        # Insert persona but cause an error by corrupting data
        db_connection.execute(
            "INSERT INTO people (id, name, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?)",
            (1, "Test User", "invalid", 1)
        )
        db_connection.commit()
        
        filter_obj = CommunicationStyleFilter(db_connection)
        result = await filter_obj.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        # Should fallback to original message
        assert result.success is False
        assert result.styled_message == "Original message"
        assert result.error is not None
