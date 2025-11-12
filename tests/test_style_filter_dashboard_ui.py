"""
Integration tests for dashboard UI style filter functionality.

Tests filter toggle updates configuration, persona dialog saves style examples,
metrics display updates, and regenerate functionality.
"""

import json
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from virtualoffice.sim_manager.app import app
from virtualoffice.sim_manager.style_filter.models import StyleExample


@pytest.fixture
def db_connection():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    
    # Create people table
    conn.execute("""
        CREATE TABLE people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            email TEXT NOT NULL,
            chat_handle TEXT NOT NULL,
            personality TEXT NOT NULL DEFAULT '[]',
            skills TEXT NOT NULL DEFAULT '[]',
            communication_style TEXT NOT NULL DEFAULT '',
            style_examples TEXT NOT NULL DEFAULT '[]',
            style_filter_enabled INTEGER NOT NULL DEFAULT 1
        )
    """)
    
    # Create style_filter_config table
    conn.execute("""
        CREATE TABLE style_filter_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert default config
    conn.execute("INSERT INTO style_filter_config (id, enabled) VALUES (1, 1)")
    
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
def client(db_connection):
    """Create a test client for the FastAPI app."""
    # Override the database connection in the app
    app.state.db_path = ":memory:"
    
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_style_examples():
    """Create sample style examples for testing."""
    return [
        {"type": "email", "content": "Professional email with formal tone and clear structure."},
        {"type": "email", "content": "Another email showing consistent communication style."},
        {"type": "email", "content": "Third email example demonstrating personality traits."},
        {"type": "chat", "content": "Quick chat message showing informal style."},
        {"type": "chat", "content": "Another chat with personality and brevity."},
    ]


class TestStyleFilterDashboardUI:
    """Integration test suite for dashboard UI style filter functionality."""

    def test_get_filter_config(self, client, db_connection):
        """Test getting filter configuration via API."""
        response = client.get("/api/v1/style-filter/config")
        
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert data["enabled"] is True

    def test_update_filter_config_enable(self, client, db_connection):
        """Test enabling filter via API."""
        response = client.put(
            "/api/v1/style-filter/config",
            json={"enabled": True}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        
        # Verify in database
        cursor = db_connection.execute("SELECT enabled FROM style_filter_config WHERE id = 1")
        row = cursor.fetchone()
        assert row[0] == 1

    def test_update_filter_config_disable(self, client, db_connection):
        """Test disabling filter via API."""
        response = client.put(
            "/api/v1/style-filter/config",
            json={"enabled": False}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        
        # Verify in database
        cursor = db_connection.execute("SELECT enabled FROM style_filter_config WHERE id = 1")
        row = cursor.fetchone()
        assert row[0] == 0

    def test_create_persona_with_style_examples(self, client, db_connection, sample_style_examples):
        """Test creating persona with style examples via API."""
        persona_data = {
            "name": "Test User",
            "role": "Software Engineer",
            "email": "test@example.com",
            "chat_handle": "testuser",
            "personality": ["analytical", "collaborative"],
            "skills": ["Python", "JavaScript"],
            "communication_style": "clear and concise",
            "style_examples": sample_style_examples,
            "style_filter_enabled": True
        }
        
        response = client.post("/api/v1/people", json=persona_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test User"
        assert "style_examples" in data
        assert len(data["style_examples"]) == 5

    def test_get_persona_with_style_examples(self, client, db_connection, sample_style_examples):
        """Test retrieving persona with style examples via API."""
        # Insert persona
        examples_json = json.dumps(sample_style_examples)
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, style_examples, style_filter_enabled) 
            VALUES (?, ?, ?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser", examples_json, 1)
        )
        db_connection.commit()
        
        # Get persona
        response = client.get("/api/v1/people/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test User"
        assert len(data["style_examples"]) == 5
        assert data["style_filter_enabled"] is True

    def test_update_persona_style_examples(self, client, db_connection, sample_style_examples):
        """Test updating persona style examples via API."""
        # Insert persona
        examples_json = json.dumps(sample_style_examples)
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, style_examples, style_filter_enabled) 
            VALUES (?, ?, ?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser", examples_json, 1)
        )
        db_connection.commit()
        
        # Update with new examples
        new_examples = [
            {"type": "email", "content": "Updated email example one."},
            {"type": "email", "content": "Updated email example two."},
            {"type": "email", "content": "Updated email example three."},
            {"type": "chat", "content": "Updated chat one."},
            {"type": "chat", "content": "Updated chat two."},
        ]
        
        response = client.put(
            "/api/v1/people/1",
            json={
                "name": "Test User",
                "role": "Engineer",
                "email": "test@example.com",
                "chat_handle": "testuser",
                "style_examples": new_examples
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["style_examples"][0]["content"] == "Updated email example one."

    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    def test_regenerate_style_examples(self, mock_generate_text, client, db_connection):
        """Test regenerating style examples via API."""
        # Insert persona
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, personality, communication_style, style_examples) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser", 
             '["analytical"]', "concise", "[]")
        )
        db_connection.commit()
        
        # Mock GPT-4o response
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "Regenerated email example one."},
                {"type": "email", "content": "Regenerated email example two."},
                {"type": "email", "content": "Regenerated email example three."},
                {"type": "chat", "content": "Regenerated chat one."},
                {"type": "chat", "content": "Regenerated chat two."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 150)
        
        # Regenerate examples
        response = client.post("/api/v1/people/1/regenerate-style-examples")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["style_examples"]) == 5
        assert data["style_examples"][0]["content"] == "Regenerated email example one."

    def test_get_filter_metrics_empty(self, client, db_connection):
        """Test getting filter metrics when no data exists."""
        response = client.get("/api/v1/style-filter/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_transformations"] == 0
        assert data["successful_transformations"] == 0
        assert data["total_tokens"] == 0

    def test_get_filter_metrics_with_data(self, client, db_connection):
        """Test getting filter metrics with recorded data."""
        # Insert test persona
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle) 
            VALUES (?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser")
        )
        
        # Insert metrics
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "email", 100, 200.0, 1)
        )
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "chat", 80, 150.0, 1)
        )
        db_connection.commit()
        
        # Get metrics
        response = client.get("/api/v1/style-filter/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_transformations"] == 2
        assert data["successful_transformations"] == 2
        assert data["total_tokens"] == 180
        assert data["by_message_type"]["email"] == 1
        assert data["by_message_type"]["chat"] == 1

    def test_get_persona_metrics(self, client, db_connection):
        """Test getting metrics for specific persona."""
        # Insert test persona
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle) 
            VALUES (?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser")
        )
        
        # Insert metrics
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "email", 100, 200.0, 1)
        )
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "email", 120, 250.0, 1)
        )
        db_connection.commit()
        
        # Get persona metrics
        response = client.get("/api/v1/style-filter/metrics/persona/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["persona_id"] == 1
        assert data["transformation_count"] == 2
        assert data["token_usage"] == 220

    def test_toggle_persona_filter(self, client, db_connection):
        """Test toggling filter for specific persona."""
        # Insert persona with filter enabled
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, style_filter_enabled) 
            VALUES (?, ?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser", 1)
        )
        db_connection.commit()
        
        # Disable filter for persona
        response = client.put(
            "/api/v1/people/1",
            json={
                "name": "Test User",
                "role": "Engineer",
                "email": "test@example.com",
                "chat_handle": "testuser",
                "style_filter_enabled": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["style_filter_enabled"] is False
        
        # Verify in database
        cursor = db_connection.execute(
            "SELECT style_filter_enabled FROM people WHERE id = 1"
        )
        row = cursor.fetchone()
        assert row[0] == 0

    def test_validate_style_examples_on_save(self, client, db_connection):
        """Test that style examples are validated when saving persona."""
        # Try to create persona with invalid examples (too short)
        persona_data = {
            "name": "Test User",
            "role": "Engineer",
            "email": "test@example.com",
            "chat_handle": "testuser",
            "style_examples": [
                {"type": "email", "content": "Short"},  # Too short
            ]
        }
        
        response = client.post("/api/v1/people", json=persona_data)
        
        # Should fail validation
        assert response.status_code == 400 or response.status_code == 422

    def test_empty_style_examples_allowed(self, client, db_connection):
        """Test that empty style examples are allowed (filter will be bypassed)."""
        persona_data = {
            "name": "Test User",
            "role": "Engineer",
            "email": "test@example.com",
            "chat_handle": "testuser",
            "style_examples": []
        }
        
        response = client.post("/api/v1/people", json=persona_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["style_examples"] == []

    def test_filter_config_persistence(self, client, db_connection):
        """Test that filter configuration persists across requests."""
        # Disable filter
        response1 = client.put(
            "/api/v1/style-filter/config",
            json={"enabled": False}
        )
        assert response1.status_code == 200
        
        # Get config again
        response2 = client.get("/api/v1/style-filter/config")
        assert response2.status_code == 200
        data = response2.json()
        assert data["enabled"] is False

    def test_metrics_display_cost_estimation(self, client, db_connection):
        """Test that metrics include cost estimation."""
        # Insert test persona
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle) 
            VALUES (?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser")
        )
        
        # Insert metrics with known token count
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "email", 100000, 200.0, 1)  # 100k tokens
        )
        db_connection.commit()
        
        # Get metrics
        response = client.get("/api/v1/style-filter/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "estimated_cost_usd" in data
        assert data["estimated_cost_usd"] > 0

    def test_list_personas_includes_filter_status(self, client, db_connection):
        """Test that listing personas includes filter enabled status."""
        # Insert personas with different filter states
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, style_filter_enabled) 
            VALUES (?, ?, ?, ?, ?)""",
            ("User One", "Engineer", "user1@example.com", "user1", 1)
        )
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, style_filter_enabled) 
            VALUES (?, ?, ?, ?, ?)""",
            ("User Two", "Manager", "user2@example.com", "user2", 0)
        )
        db_connection.commit()
        
        # List personas
        response = client.get("/api/v1/people")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["style_filter_enabled"] is True
        assert data[1]["style_filter_enabled"] is False

    @patch('virtualoffice.sim_manager.style_filter.example_generator.generate_text')
    def test_regenerate_preserves_other_attributes(self, mock_generate_text, client, db_connection):
        """Test that regenerating examples preserves other persona attributes."""
        # Insert persona with specific attributes
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle, personality, skills, communication_style, style_examples) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Test User", "Senior Engineer", "test@example.com", "testuser",
             '["analytical", "creative"]', '["Python", "Go"]', "technical and precise", "[]")
        )
        db_connection.commit()
        
        # Mock GPT-4o response
        mock_response = json.dumps({
            "examples": [
                {"type": "email", "content": "New email example one."},
                {"type": "email", "content": "New email example two."},
                {"type": "email", "content": "New email example three."},
                {"type": "chat", "content": "New chat one."},
                {"type": "chat", "content": "New chat two."},
            ]
        })
        mock_generate_text.return_value = (mock_response, 150)
        
        # Regenerate examples
        response = client.post("/api/v1/people/1/regenerate-style-examples")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify other attributes preserved
        assert data["name"] == "Test User"
        assert data["role"] == "Senior Engineer"
        assert data["email"] == "test@example.com"
        assert data["personality"] == ["analytical", "creative"]
        assert data["skills"] == ["Python", "Go"]
        assert data["communication_style"] == "technical and precise"
        
        # Verify examples were regenerated
        assert len(data["style_examples"]) == 5
        assert data["style_examples"][0]["content"] == "New email example one."

    def test_metrics_latency_tracking(self, client, db_connection):
        """Test that metrics track latency correctly."""
        # Insert test persona
        db_connection.execute(
            """INSERT INTO people 
            (name, role, email, chat_handle) 
            VALUES (?, ?, ?, ?)""",
            ("Test User", "Engineer", "test@example.com", "testuser")
        )
        
        # Insert metrics with various latencies
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "email", 100, 200.0, 1)
        )
        db_connection.execute(
            """INSERT INTO style_filter_metrics 
            (persona_id, message_type, tokens_used, latency_ms, success) 
            VALUES (?, ?, ?, ?, ?)""",
            (1, "email", 100, 300.0, 1)
        )
        db_connection.commit()
        
        # Get metrics
        response = client.get("/api/v1/style-filter/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "average_latency_ms" in data
        assert data["average_latency_ms"] == 250.0  # (200 + 300) / 2
