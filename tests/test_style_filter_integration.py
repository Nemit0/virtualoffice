"""
Integration tests for end-to-end message flow with style filter.

Tests creating personas with style examples, generating and sending messages
through simulation, verifying filter application, and checking metrics recording.
"""

import json
import pytest
import sqlite3
from unittest.mock import patch, AsyncMock

from virtualoffice.sim_manager.style_filter.example_generator import StyleExampleGenerator
from virtualoffice.sim_manager.style_filter.filter import CommunicationStyleFilter
from virtualoffice.sim_manager.style_filter.metrics import FilterMetrics
from virtualoffice.sim_manager.style_filter.models import StyleExample
from virtualoffice.sim_manager.gateways import HttpEmailGateway, HttpChatGateway


# Mock WorkerPersona for testing
class MockWorkerPersona:
    def __init__(self, name, role, personality, communication_style):
        self.name = name
        self.role = role
        self.personality = personality
        self.communication_style = communication_style


@pytest.fixture
def db_connection():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    
    # Create people table
    conn.execute("""
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
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


class TestStyleFilterIntegration:
    """Integration test suite for style filter end-to-end flow."""

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    async def test_create_persona_with_generated_examples(self, mock_generate_text, db_connection):
        """Test creating a persona with AI-generated style examples."""
        # Mock GPT-4o response for example generation
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Professional email example with formal tone."},
                {"type": "email", "content": "Another email showing consistent style."},
                {"type": "email", "content": "Third email demonstrating personality."},
                {"type": "chat", "content": "Quick chat message here."},
                {"type": "chat", "content": "Another chat with brevity."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 150)
        
        # Create persona
        persona = MockWorkerPersona(
            name="John Doe",
            role="Software Engineer",
            personality=["analytical", "detail-oriented"],
            communication_style="concise and technical"
        )
        
        # Generate style examples
        generator = StyleExampleGenerator(locale="en")
        examples = await generator.generate_examples(persona)
        
        # Store persona in database
        examples_json = json.dumps([ex.to_dict() for ex in examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, persona.name, persona.role, examples_json, 1)
        )
        db_connection.commit()
        
        # Verify persona was created with examples
        cursor = db_connection.execute("SELECT style_examples FROM people WHERE id = 1")
        stored_examples_json = cursor.fetchone()[0]
        stored_examples = json.loads(stored_examples_json)
        
        assert len(stored_examples) == 5
        assert all(ex["content"] for ex in stored_examples)

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_send_email_with_filter(self, mock_generate_text, db_connection, sample_style_examples):
        """Test sending email through gateway with style filter applied."""
        # Setup persona with style examples
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "Test User", "Engineer", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o response for filter
        mock_generate_text.return_value = ("Styled email message with personality", 85)
        
        # Create filter and gateway
        style_filter = CommunicationStyleFilter(db_connection, locale="en")
        
        # Apply filter to message
        original_message = "This is a plain email message."
        result = await style_filter.apply_filter(
            message=original_message,
            persona_id=1,
            message_type="email"
        )
        
        # Verify filter was applied
        assert result.success is True
        assert result.styled_message != original_message
        assert result.styled_message == "Styled email message with personality"
        assert result.tokens_used == 85

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_send_chat_with_filter(self, mock_generate_text, db_connection, sample_style_examples):
        """Test sending chat message through gateway with style filter applied."""
        # Setup persona with style examples
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "Test User", "Engineer", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o response for filter
        mock_generate_text.return_value = ("Styled chat message!", 65)
        
        # Create filter
        style_filter = CommunicationStyleFilter(db_connection, locale="en")
        
        # Apply filter to message
        original_message = "This is a plain chat message."
        result = await style_filter.apply_filter(
            message=original_message,
            persona_id=1,
            message_type="chat"
        )
        
        # Verify filter was applied
        assert result.success is True
        assert result.styled_message != original_message
        assert result.styled_message == "Styled chat message!"
        assert result.tokens_used == 65

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_metrics_recorded_on_transformation(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that metrics are recorded when filter transforms messages."""
        # Setup persona
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "Test User", "Engineer", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o response
        mock_generate_text.return_value = ("Styled message", 80)
        
        # Create filter with metrics
        metrics = FilterMetrics(db_connection, batch_size=1)
        style_filter = CommunicationStyleFilter(db_connection, metrics=metrics)
        
        # Apply filter
        await style_filter.apply_filter(
            message="Original message",
            persona_id=1,
            message_type="email"
        )
        
        # Verify metrics were recorded
        cursor = db_connection.execute(
            "SELECT COUNT(*) FROM style_filter_metrics WHERE persona_id = 1"
        )
        count = cursor.fetchone()[0]
        assert count == 1
        
        # Verify metric details
        cursor = db_connection.execute(
            "SELECT message_type, tokens_used, success FROM style_filter_metrics WHERE persona_id = 1"
        )
        row = cursor.fetchone()
        assert row[0] == "email"
        assert row[1] == 80
        assert row[2] == 1  # success

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_multiple_messages_different_personas(self, mock_generate_text, db_connection, sample_style_examples):
        """Test filtering messages from multiple personas."""
        # Setup two personas
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "User One", "Engineer", examples_json, 1)
        )
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (2, "User Two", "Manager", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o responses
        mock_generate_text.side_effect = [
            ("Styled message from persona 1", 85),
            ("Styled message from persona 2", 90),
        ]
        
        # Create filter
        style_filter = CommunicationStyleFilter(db_connection)
        
        # Apply filter for both personas
        result1 = await style_filter.apply_filter(
            message="Message from persona 1",
            persona_id=1,
            message_type="email"
        )
        result2 = await style_filter.apply_filter(
            message="Message from persona 2",
            persona_id=2,
            message_type="email"
        )
        
        # Verify both were filtered
        assert result1.success is True
        assert result2.success is True
        assert result1.styled_message == "Styled message from persona 1"
        assert result2.styled_message == "Styled message from persona 2"

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_filter_disabled_for_persona(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that filter is bypassed when disabled for specific persona."""
        # Setup persona with filter disabled
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "Test User", "Engineer", examples_json, 0)  # Filter disabled
        )
        db_connection.commit()
        
        # Create filter
        style_filter = CommunicationStyleFilter(db_connection)
        
        # Apply filter
        original_message = "Original message"
        result = await style_filter.apply_filter(
            message=original_message,
            persona_id=1,
            message_type="email"
        )
        
        # Verify filter was bypassed
        assert result.success is True
        assert result.styled_message == original_message
        assert result.tokens_used == 0
        assert "disabled for persona" in result.error

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_filter_fallback_on_api_failure(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that filter falls back to original message on API failure."""
        # Setup persona
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "Test User", "Engineer", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock API failure
        mock_generate_text.side_effect = RuntimeError("API connection failed")
        
        # Create filter with metrics
        metrics = FilterMetrics(db_connection, batch_size=1)
        style_filter = CommunicationStyleFilter(db_connection, metrics=metrics)
        
        # Apply filter
        original_message = "Original message"
        result = await style_filter.apply_filter(
            message=original_message,
            persona_id=1,
            message_type="email"
        )
        
        # Verify fallback to original
        assert result.success is False
        assert result.styled_message == original_message
        assert result.tokens_used == 0
        assert "API connection failed" in result.error
        
        # Verify failure was recorded in metrics
        cursor = db_connection.execute(
            "SELECT success FROM style_filter_metrics WHERE persona_id = 1"
        )
        row = cursor.fetchone()
        assert row[0] == 0  # failure

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_session_metrics_aggregation(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that session metrics aggregate across multiple transformations."""
        # Setup persona
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "Test User", "Engineer", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o responses
        mock_generate_text.side_effect = [
            ("Styled email 1", 85),
            ("Styled email 2", 90),
            ("Styled chat 1", 65),
        ]
        
        # Create filter with metrics
        metrics = FilterMetrics(db_connection, batch_size=1)
        style_filter = CommunicationStyleFilter(db_connection, metrics=metrics)
        
        # Apply filter multiple times
        await style_filter.apply_filter("Message 1", persona_id=1, message_type="email")
        await style_filter.apply_filter("Message 2", persona_id=1, message_type="email")
        await style_filter.apply_filter("Message 3", persona_id=1, message_type="chat")
        
        # Get session metrics
        summary = await metrics.get_session_metrics()
        
        # Verify aggregation
        assert summary.total_transformations == 3
        assert summary.successful_transformations == 3
        assert summary.total_tokens == 240  # 85 + 90 + 65
        assert summary.by_message_type == {"email": 2, "chat": 1}

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_persona_specific_metrics(self, mock_generate_text, db_connection, sample_style_examples):
        """Test that persona-specific metrics are tracked correctly."""
        # Setup two personas
        examples_json = json.dumps([ex.to_dict() for ex in sample_style_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "User One", "Engineer", examples_json, 1)
        )
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (2, "User Two", "Manager", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock GPT-4o responses
        mock_generate_text.side_effect = [
            ("Styled from persona 1", 85),
            ("Styled from persona 1 again", 90),
            ("Styled from persona 2", 75),
        ]
        
        # Create filter with metrics
        metrics = FilterMetrics(db_connection, batch_size=1)
        style_filter = CommunicationStyleFilter(db_connection, metrics=metrics)
        
        # Apply filter for both personas
        await style_filter.apply_filter("Message 1", persona_id=1, message_type="email")
        await style_filter.apply_filter("Message 2", persona_id=1, message_type="email")
        await style_filter.apply_filter("Message 3", persona_id=2, message_type="email")
        
        # Get persona-specific metrics
        persona1_metrics = await metrics.get_persona_metrics(1)
        persona2_metrics = await metrics.get_persona_metrics(2)
        
        # Verify persona 1 metrics
        assert persona1_metrics["transformation_count"] == 2
        assert persona1_metrics["token_usage"] == 175  # 85 + 90
        
        # Verify persona 2 metrics
        assert persona2_metrics["transformation_count"] == 1
        assert persona2_metrics["token_usage"] == 75

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_full_workflow_persona_creation_to_message(
        self, mock_filter_generate, mock_example_generate, db_connection
    ):
        """Test complete workflow from persona creation to filtered message."""
        # Step 1: Generate style examples for new persona
        mock_example_generate.return_value = (json.dumps({
            "examples": [
                {"type": "email", "content": "Professional email with formal tone and structure."},
                {"type": "email", "content": "Another email showing consistent style."},
                {"type": "email", "content": "Third email example demonstrating traits."},
                {"type": "chat", "content": "Quick chat message here."},
                {"type": "chat", "content": "Another chat message here."},
            ]
        }), 150)
        
        persona = MockWorkerPersona(
            name="Alice Engineer",
            role="Senior Software Engineer",
            personality=["analytical", "collaborative"],
            communication_style="clear and concise"
        )
        
        generator = StyleExampleGenerator(locale="en")
        examples = await generator.generate_examples(persona)
        
        # Step 2: Store persona in database
        examples_json = json.dumps([ex.to_dict() for ex in examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, persona.name, persona.role, examples_json, 1)
        )
        db_connection.commit()
        
        # Step 3: Generate and filter a message
        mock_filter_generate.return_value = ("Styled message with Alice's personality", 88)
        
        metrics = FilterMetrics(db_connection, batch_size=1)
        style_filter = CommunicationStyleFilter(db_connection, metrics=metrics)
        
        result = await style_filter.apply_filter(
            message="Generic message content",
            persona_id=1,
            message_type="email"
        )
        
        # Step 4: Verify complete workflow
        assert result.success is True
        assert result.styled_message == "Styled message with Alice's personality"
        assert result.tokens_used == 88
        
        # Verify metrics were recorded
        summary = await metrics.get_session_metrics()
        assert summary.total_transformations == 1
        assert summary.successful_transformations == 1
        assert summary.total_tokens == 88

    @pytest.mark.asyncio
    @patch('virtualoffice.sim_manager.style_filter.filter.generate_text')
    async def test_korean_persona_workflow(self, mock_generate_text, db_connection):
        """Test workflow with Korean persona and locale."""
        # Setup Korean persona with Korean examples
        korean_examples = [
            StyleExample(type="email", content="안녕하세요, 프로젝트 진행 상황을 공유드립니다."),
            StyleExample(type="email", content="회의 일정을 확인해 주시기 바랍니다."),
            StyleExample(type="email", content="보고서를 첨부 파일로 보내드립니다."),
            StyleExample(type="chat", content="네, 확인했습니다!"),
            StyleExample(type="chat", content="오늘 오후 3시에 가능하신가요?"),
        ]
        
        examples_json = json.dumps([ex.to_dict() for ex in korean_examples])
        db_connection.execute(
            "INSERT INTO people (id, name, role, style_examples, style_filter_enabled) VALUES (?, ?, ?, ?, ?)",
            (1, "김철수", "프로젝트 매니저", examples_json, 1)
        )
        db_connection.commit()
        
        # Mock Korean GPT-4o response
        mock_generate_text.return_value = ("안녕하세요, 작업이 완료되었습니다.", 75)
        
        # Create filter with Korean locale
        style_filter = CommunicationStyleFilter(db_connection, locale="ko")
        
        # Apply filter
        result = await style_filter.apply_filter(
            message="작업 완료",
            persona_id=1,
            message_type="chat"
        )
        
        # Verify Korean filtering
        assert result.success is True
        assert result.styled_message == "안녕하세요, 작업이 완료되었습니다."
        # Verify Korean characters present
        assert any('\uac00' <= char <= '\ud7a3' for char in result.styled_message)
