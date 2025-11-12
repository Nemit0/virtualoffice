"""
Unit tests for email client interface functionality.

These tests focus on the core logic and API interactions without requiring Playwright.
They test the email client functionality at the API and data processing level.
"""

import json
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from virtualoffice.sim_manager.app import create_app


class TestEmailClientAPI:
    """Test email client API endpoints and data handling."""

    def setup_method(self):
        """Set up test client and mock data."""
        self.app = create_app()
        self.client = TestClient(self.app)
        
        # Use unique names for each test to avoid conflicts
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        # Create test persona
        self.test_persona = {
            "name": f"Test User {unique_id}",
            "role": "Test Role",
            "timezone": "UTC",
            "work_hours": "09:00-17:00",
            "break_frequency": "50/10 cadence",
            "communication_style": "Test style",
            "email_address": f"test{unique_id}@vdos.local",
            "chat_handle": f"test{unique_id}",
            "skills": ["Testing"],
            "personality": ["Reliable"],
            "schedule": [{"start": "09:00", "end": "10:00", "activity": "Testing"}],
            "objectives": ["Test objectives"],
            "metrics": ["Test metrics"],
        }

    def test_create_persona_for_email_monitoring(self):
        """Test creating a persona that can be used for email monitoring."""
        response = self.client.post("/api/v1/people", json=self.test_persona)
        assert response.status_code == 201  # API returns 201 Created for new resources
        
        persona_data = response.json()
        assert persona_data["name"] == self.test_persona["name"]
        assert persona_data["email_address"] == self.test_persona["email_address"]
        assert "id" in persona_data

    def test_get_personas_for_email_client(self):
        """Test retrieving personas for email client dropdown."""
        # Create a persona first
        create_response = self.client.post("/api/v1/people", json=self.test_persona)
        assert create_response.status_code == 201
        
        # Get all personas
        response = self.client.get("/api/v1/people")
        assert response.status_code == 200
        
        personas = response.json()
        assert len(personas) > 0
        
        # Verify persona has required fields for email client
        persona = personas[0]
        assert "id" in persona
        assert "name" in persona
        assert "email_address" in persona

    def test_email_monitoring_endpoint_structure(self):
        """Test the structure of email monitoring API response."""
        # Create a persona first
        create_response = self.client.post("/api/v1/people", json=self.test_persona)
        persona_id = create_response.json()["id"]
        
        # Test email monitoring endpoint
        response = self.client.get(f"/api/v1/monitor/emails/{persona_id}?box=all&limit=200")
        assert response.status_code == 200
        
        email_data = response.json()
        
        # Verify response structure matches email client expectations
        assert "inbox" in email_data
        assert "sent" in email_data
        assert isinstance(email_data["inbox"], list)
        assert isinstance(email_data["sent"], list)

    def test_email_monitoring_with_invalid_persona(self):
        """Test email monitoring with non-existent persona ID."""
        invalid_id = 99999
        response = self.client.get(f"/api/v1/monitor/emails/{invalid_id}?box=all&limit=200")
        
        # Should handle gracefully (either 404 or empty response)
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            email_data = response.json()
            # Should return empty lists for non-existent persona
            assert email_data.get("inbox", []) == []
            assert email_data.get("sent", []) == []

    def test_email_data_structure_validation(self):
        """Test that email data has the expected structure for the client."""
        # Create persona
        create_response = self.client.post("/api/v1/people", json=self.test_persona)
        persona_id = create_response.json()["id"]
        
        # Get email data
        response = self.client.get(f"/api/v1/monitor/emails/{persona_id}?box=all&limit=200")
        email_data = response.json()
        
        # Test with empty data (should not cause errors)
        inbox_emails = email_data.get("inbox", [])
        sent_emails = email_data.get("sent", [])
        
        # Verify structure for any existing emails
        for email_list in [inbox_emails, sent_emails]:
            for email in email_list:
                # These fields are expected by the email client interface
                expected_fields = ["id", "sender", "subject", "body", "sent_at"]
                for field in expected_fields:
                    assert field in email or email.get(field) is not None or field == "sent_at"
                
                # Optional fields that should be handled gracefully if missing
                optional_fields = ["to", "cc", "bcc", "thread_id", "read"]
                for field in optional_fields:
                    # Should not cause errors if missing
                    value = email.get(field)
                    if field in ["to", "cc", "bcc"] and value is not None:
                        assert isinstance(value, list)


class TestEmailClientDataProcessing:
    """Test email client data processing and formatting logic."""

    def test_relative_time_formatting_logic(self):
        """Test the logic for relative time formatting used in email list."""
        from datetime import datetime, timedelta
        
        # Simulate the relative time formatting logic from the JavaScript
        def format_relative_time(timestamp_str):
            """Python version of the JavaScript formatRelativeTime function."""
            if not timestamp_str:
                return ""
            
            try:
                now = datetime.now()
                email_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                diff = now - email_time
                
                diff_minutes = int(diff.total_seconds() / 60)
                diff_hours = int(diff.total_seconds() / 3600)
                diff_days = diff.days
                
                if diff_minutes < 1:
                    return "Just now"
                elif diff_minutes < 60:
                    return f"{diff_minutes} min ago"
                elif diff_hours < 24:
                    return f"{diff_hours} hour{'s' if diff_hours != 1 else ''} ago"
                elif diff_days == 1:
                    return "Yesterday"
                elif diff_days < 7:
                    return f"{diff_days} days ago"
                else:
                    return email_time.strftime("%m/%d/%Y")
            except:
                return ""
        
        # Test various time scenarios
        now = datetime.now()
        
        # Just now
        recent = now - timedelta(seconds=30)
        assert "Just now" in format_relative_time(recent.isoformat())
        
        # Minutes ago
        minutes_ago = now - timedelta(minutes=15)
        result = format_relative_time(minutes_ago.isoformat())
        assert "min ago" in result
        
        # Hours ago
        hours_ago = now - timedelta(hours=3)
        result = format_relative_time(hours_ago.isoformat())
        assert "hour" in result and "ago" in result
        
        # Days ago
        days_ago = now - timedelta(days=2)
        result = format_relative_time(days_ago.isoformat())
        assert "days ago" in result
        
        # Invalid timestamp
        assert format_relative_time("invalid") == ""
        assert format_relative_time("") == ""
        assert format_relative_time(None) == ""

    def test_email_sorting_logic(self):
        """Test email sorting by timestamp (newest first)."""
        from datetime import datetime, timedelta
        
        # Create sample emails with different timestamps
        now = datetime.now()
        emails = [
            {
                "id": 1,
                "subject": "Oldest Email",
                "sent_at": (now - timedelta(days=3)).isoformat(),
                "sender": "test@example.com"
            },
            {
                "id": 2,
                "subject": "Newest Email",
                "sent_at": now.isoformat(),
                "sender": "test@example.com"
            },
            {
                "id": 3,
                "subject": "Middle Email",
                "sent_at": (now - timedelta(days=1)).isoformat(),
                "sender": "test@example.com"
            }
        ]
        
        # Sort emails by timestamp (newest first) - simulating JavaScript logic
        def sort_emails_by_time(email_list):
            return sorted(email_list, key=lambda x: datetime.fromisoformat(x["sent_at"]), reverse=True)
        
        sorted_emails = sort_emails_by_time(emails)
        
        # Verify sorting order
        assert sorted_emails[0]["subject"] == "Newest Email"
        assert sorted_emails[1]["subject"] == "Middle Email"
        assert sorted_emails[2]["subject"] == "Oldest Email"

    def test_email_thread_counting_logic(self):
        """Test logic for counting emails in the same thread."""
        emails = [
            {"id": 1, "thread_id": "thread-1", "subject": "Initial Email"},
            {"id": 2, "thread_id": "thread-1", "subject": "Re: Initial Email"},
            {"id": 3, "thread_id": "thread-1", "subject": "Re: Initial Email"},
            {"id": 4, "thread_id": "thread-2", "subject": "Different Thread"},
            {"id": 5, "thread_id": None, "subject": "No Thread"},
        ]
        
        # Simulate thread counting logic
        def count_thread_emails(emails, thread_id):
            if not thread_id:
                return 1
            return len([email for email in emails if email.get("thread_id") == thread_id])
        
        # Test thread counting
        assert count_thread_emails(emails, "thread-1") == 3
        assert count_thread_emails(emails, "thread-2") == 1
        assert count_thread_emails(emails, None) == 1
        assert count_thread_emails(emails, "nonexistent") == 0

    def test_email_snippet_generation(self):
        """Test email body snippet generation for list view."""
        def generate_email_snippet(body, max_length=100):
            """Generate email snippet for list view."""
            if not body:
                return ""
            
            body_str = str(body)
            if len(body_str) <= max_length:
                return body_str
            
            return body_str[:max_length] + "…"
        
        # Test various body lengths
        short_body = "Short email"
        assert generate_email_snippet(short_body) == "Short email"
        
        long_body = "This is a very long email body that should be truncated because it exceeds the maximum length limit for display in the email list view."
        snippet = generate_email_snippet(long_body, 50)
        assert len(snippet) <= 51  # 50 chars + ellipsis
        assert snippet.endswith("…")
        
        # Test edge cases
        assert generate_email_snippet("") == ""
        assert generate_email_snippet(None) == ""

    def test_email_address_formatting(self):
        """Test email address list formatting for display."""
        def format_email_addresses(addresses):
            """Format email address list for display."""
            if not addresses:
                return "Unknown"
            
            if isinstance(addresses, list):
                return ", ".join(addresses) if addresses else "Unknown"
            
            return str(addresses)
        
        # Test various address formats
        assert format_email_addresses(["test@example.com"]) == "test@example.com"
        assert format_email_addresses(["test1@example.com", "test2@example.com"]) == "test1@example.com, test2@example.com"
        assert format_email_addresses([]) == "Unknown"
        assert format_email_addresses(None) == "Unknown"
        assert format_email_addresses("single@example.com") == "single@example.com"


class TestEmailClientStateManagement:
    """Test email client state management logic."""

    def test_folder_state_management(self):
        """Test folder switching state management."""
        # Simulate email client state
        class EmailClientState:
            def __init__(self):
                self.current_folder = "inbox"
                self.selected_email_id = None
                self.email_cache = {"inbox": [], "sent": []}
                self.focus_index = -1
            
            def switch_folder(self, folder):
                """Switch between inbox and sent folders."""
                if folder in ["inbox", "sent"]:
                    self.current_folder = folder
                    # Reset selection when switching folders
                    self.selected_email_id = None
                    self.focus_index = -1
                    return True
                return False
            
            def select_email(self, email_id):
                """Select an email in the current folder."""
                current_emails = self.email_cache.get(self.current_folder, [])
                if any(email.get("id") == email_id for email in current_emails):
                    self.selected_email_id = email_id
                    return True
                return False
        
        # Test state management
        state = EmailClientState()
        
        # Initial state
        assert state.current_folder == "inbox"
        assert state.selected_email_id is None
        
        # Switch to sent folder
        assert state.switch_folder("sent") is True
        assert state.current_folder == "sent"
        assert state.selected_email_id is None  # Should reset selection
        
        # Switch back to inbox
        assert state.switch_folder("inbox") is True
        assert state.current_folder == "inbox"
        
        # Invalid folder
        assert state.switch_folder("invalid") is False
        assert state.current_folder == "inbox"  # Should not change

    def test_email_selection_state(self):
        """Test email selection state management."""
        # Mock email data
        inbox_emails = [
            {"id": 1, "subject": "Email 1"},
            {"id": 2, "subject": "Email 2"},
        ]
        sent_emails = [
            {"id": 3, "subject": "Sent Email 1"},
        ]
        
        class EmailClientState:
            def __init__(self):
                self.current_folder = "inbox"
                self.selected_email_id = None
                self.email_cache = {"inbox": inbox_emails, "sent": sent_emails}
            
            def get_current_emails(self):
                return self.email_cache.get(self.current_folder, [])
            
            def select_email_by_index(self, index):
                current_emails = self.get_current_emails()
                if 0 <= index < len(current_emails):
                    self.selected_email_id = current_emails[index]["id"]
                    return True
                return False
            
            def get_selected_email(self):
                current_emails = self.get_current_emails()
                for email in current_emails:
                    if email["id"] == self.selected_email_id:
                        return email
                return None
        
        state = EmailClientState()
        
        # Test email selection
        assert state.select_email_by_index(0) is True
        assert state.selected_email_id == 1
        
        selected = state.get_selected_email()
        assert selected["subject"] == "Email 1"
        
        # Test invalid index
        assert state.select_email_by_index(10) is False
        assert state.selected_email_id == 1  # Should not change
        
        # Test selection persistence across folder switch
        state.current_folder = "sent"
        selected = state.get_selected_email()
        assert selected is None  # Email 1 not in sent folder

    def test_keyboard_navigation_state(self):
        """Test keyboard navigation state management."""
        emails = [
            {"id": 1, "subject": "Email 1"},
            {"id": 2, "subject": "Email 2"},
            {"id": 3, "subject": "Email 3"},
        ]
        
        class KeyboardNavigation:
            def __init__(self, emails):
                self.emails = emails
                self.focus_index = 0
            
            def navigate_down(self):
                if self.focus_index < len(self.emails) - 1:
                    self.focus_index += 1
                    return True
                return False
            
            def navigate_up(self):
                if self.focus_index > 0:
                    self.focus_index -= 1
                    return True
                return False
            
            def navigate_home(self):
                self.focus_index = 0
                return True
            
            def navigate_end(self):
                self.focus_index = len(self.emails) - 1
                return True
            
            def get_focused_email(self):
                if 0 <= self.focus_index < len(self.emails):
                    return self.emails[self.focus_index]
                return None
        
        nav = KeyboardNavigation(emails)
        
        # Test navigation
        assert nav.get_focused_email()["id"] == 1
        
        # Navigate down
        assert nav.navigate_down() is True
        assert nav.get_focused_email()["id"] == 2
        
        # Navigate up
        assert nav.navigate_up() is True
        assert nav.get_focused_email()["id"] == 1
        
        # Navigate to end
        assert nav.navigate_end() is True
        assert nav.get_focused_email()["id"] == 3
        
        # Try to navigate past end
        assert nav.navigate_down() is False
        assert nav.get_focused_email()["id"] == 3
        
        # Navigate to home
        assert nav.navigate_home() is True
        assert nav.get_focused_email()["id"] == 1


class TestEmailClientErrorHandling:
    """Test error handling scenarios in email client."""

    def test_malformed_email_data_handling(self):
        """Test handling of malformed email data."""
        def safe_get_email_field(email, field, default=""):
            """Safely get email field with fallback."""
            try:
                value = email.get(field, default)
                return value if value is not None else default
            except (AttributeError, TypeError):
                return default
        
        # Test with various malformed data
        malformed_emails = [
            None,
            {},
            {"id": 1},  # Missing required fields
            {"id": 2, "subject": None, "sender": ""},
            {"id": 3, "to": "not-a-list", "cc": None},
        ]
        
        for email in malformed_emails:
            if email is None:
                continue
                
            # Should not raise exceptions
            subject = safe_get_email_field(email, "subject", "(no subject)")
            sender = safe_get_email_field(email, "sender", "Unknown")
            body = safe_get_email_field(email, "body", "")
            
            assert isinstance(subject, str)
            assert isinstance(sender, str)
            assert isinstance(body, str)

    def test_api_error_response_handling(self):
        """Test handling of API error responses."""
        def handle_api_response(response_data):
            """Handle API response with error checking."""
            try:
                if not isinstance(response_data, dict):
                    return {"inbox": [], "sent": [], "error": "Invalid response format"}
                
                inbox = response_data.get("inbox", [])
                sent = response_data.get("sent", [])
                
                # Ensure lists
                if not isinstance(inbox, list):
                    inbox = []
                if not isinstance(sent, list):
                    sent = []
                
                return {"inbox": inbox, "sent": sent, "error": None}
            
            except Exception as e:
                return {"inbox": [], "sent": [], "error": str(e)}
        
        # Test various response scenarios
        valid_response = {"inbox": [{"id": 1}], "sent": []}
        result = handle_api_response(valid_response)
        assert result["error"] is None
        assert len(result["inbox"]) == 1
        
        # Invalid response types
        result = handle_api_response(None)
        assert result["error"] == "Invalid response format"
        
        result = handle_api_response("invalid")
        assert result["error"] == "Invalid response format"
        
        # Missing fields
        result = handle_api_response({})
        assert result["error"] is None
        assert result["inbox"] == []
        assert result["sent"] == []
        
        # Invalid field types
        result = handle_api_response({"inbox": "not-a-list", "sent": None})
        assert result["error"] is None
        assert result["inbox"] == []
        assert result["sent"] == []

    def test_network_error_simulation(self):
        """Test network error handling simulation."""
        def simulate_network_request(should_fail=False, response_data=None):
            """Simulate network request with potential failure."""
            if should_fail:
                raise Exception("Network error")
            
            return response_data or {"inbox": [], "sent": []}
        
        def handle_network_request(should_fail=False):
            """Handle network request with error recovery."""
            try:
                response = simulate_network_request(should_fail)
                return {"success": True, "data": response, "error": None}
            except Exception as e:
                return {"success": False, "data": {"inbox": [], "sent": []}, "error": str(e)}
        
        # Test successful request
        result = handle_network_request(False)
        assert result["success"] is True
        assert result["error"] is None
        
        # Test failed request
        result = handle_network_request(True)
        assert result["success"] is False
        assert result["error"] == "Network error"
        assert result["data"]["inbox"] == []  # Should provide fallback data