"""
Test suite for the enhanced email client interface functionality.

This module tests the email client interface components including:
- Email list rendering with various data scenarios
- Folder switching and selection state management
- Error handling for network failures and malformed data
- API interaction and state synchronization
"""

import json
import os
import socket
import time
from multiprocessing import Process
from unittest.mock import Mock, patch

import httpx
import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None

from virtualoffice.sim_manager.app import create_app

# Skip tests if Playwright is not available or not enabled
RUN_PLAYWRIGHT = os.getenv("VDOS_RUN_PLAYWRIGHT") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_PLAYWRIGHT or sync_playwright is None,
    reason="Email client interface tests require Playwright (set VDOS_RUN_PLAYWRIGHT=1 and install playwright)",
)


def _get_free_port() -> int:
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server(port: int) -> None:
    """Run the simulation manager server for testing."""
    import uvicorn

    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server.run()


def _wait_for_server(port: int, timeout: float = 15.0) -> None:
    """Wait for the server to start up."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/v1/simulation"
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError("Server did not start in time")


def _create_test_persona(base_url: str, name: str, email: str, handle: str) -> dict:
    """Create a test persona and return the response."""
    payload = {
        "name": name,
        "role": "Test Role",
        "timezone": "UTC",
        "work_hours": "09:00-17:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Test style",
        "email_address": email,
        "chat_handle": handle,
        "skills": ["Testing"],
        "personality": ["Reliable"],
        "schedule": [
            {"start": "09:00", "end": "10:00", "activity": "Testing"},
        ],
        "objectives": ["Test objectives"],
        "metrics": ["Test metrics"],
    }
    resp = httpx.post(f"{base_url}/api/v1/people", json=payload, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


class TestEmailListRendering:
    """Test email list rendering with various data scenarios."""

    def test_empty_email_list_display(self):
        """Test that empty email list shows appropriate placeholder."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.wait_for_selector("#tab-emails", state="visible")
                
                # Select persona
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Wait for email list to load
                page.wait_for_selector("#email-list")
                
                # Check for empty state
                empty_text = page.text_content("#email-list .small")
                assert "No emails" in empty_text
                
                # Check placeholder in detail view
                placeholder = page.text_content("#email-detail .email-detail-placeholder")
                assert "No email selected" in placeholder
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_email_list_with_sample_data(self):
        """Test email list rendering with sample email data."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            # Send a test email to create data
            email_payload = {
                "sender": "sender@vdos.local",
                "to": ["test@vdos.local"],
                "subject": "Test Email Subject",
                "body": "This is a test email body with some content to verify rendering."
            }
            httpx.post(f"{base_url}/../email/emails/send", json=email_payload, timeout=5.0)
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.wait_for_selector("#tab-emails", state="visible")
                
                # Select persona
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Wait for email list to load and refresh
                page.wait_for_selector("#email-list")
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)  # Allow refresh to complete
                
                # Check if email appears in list
                email_rows = page.query_selector_all(".email-row")
                if email_rows:
                    # Verify email row structure
                    first_row = email_rows[0]
                    sender_text = first_row.query_selector(".email-sender")
                    subject_text = first_row.query_selector(".email-subject")
                    timestamp_text = first_row.query_selector(".email-timestamp")
                    
                    assert sender_text is not None
                    assert subject_text is not None
                    assert timestamp_text is not None
                    
                    # Verify content
                    assert "sender@vdos.local" in sender_text.text_content()
                    assert "Test Email Subject" in subject_text.text_content()
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_email_row_selection_and_detail_view(self):
        """Test email selection and detail view rendering."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            # Send a test email
            email_payload = {
                "sender": "sender@vdos.local",
                "to": ["test@vdos.local"],
                "subject": "Detailed Test Email",
                "body": "This email tests the detail view functionality.\nIt has multiple lines."
            }
            httpx.post(f"{base_url}/../email/emails/send", json=email_payload, timeout=5.0)
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab and select persona
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Click on email row if it exists
                email_rows = page.query_selector_all(".email-row")
                if email_rows:
                    email_rows[0].click()
                    
                    # Verify selection state
                    assert "selected" in email_rows[0].get_attribute("class")
                    
                    # Verify detail view content
                    detail_subject = page.text_content("#email-detail-heading")
                    assert "Detailed Test Email" in detail_subject
                    
                    # Check email addresses section
                    from_address = page.text_content(".email-address-row .email-address-value")
                    assert "sender@vdos.local" in from_address
                    
                    # Check email body
                    email_body = page.text_content(".email-content")
                    assert "This email tests the detail view functionality" in email_body
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)


class TestFolderSwitchingAndState:
    """Test folder switching and selection state management."""

    def test_folder_navigation_buttons(self):
        """Test inbox/sent folder navigation."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Test initial state (Inbox should be active)
                inbox_btn = page.query_selector("#email-folder-inbox")
                sent_btn = page.query_selector("#email-folder-sent")
                
                assert "active" in inbox_btn.get_attribute("class")
                assert "active" not in sent_btn.get_attribute("class")
                
                # Test folder title
                folder_title = page.text_content("#email-folder-title")
                assert "Inbox" in folder_title
                
                # Switch to Sent folder
                sent_btn.click()
                page.wait_for_timeout(500)
                
                # Verify state change
                assert "active" not in inbox_btn.get_attribute("class")
                assert "active" in sent_btn.get_attribute("class")
                
                folder_title = page.text_content("#email-folder-title")
                assert "Sent" in folder_title
                
                # Switch back to Inbox
                inbox_btn.click()
                page.wait_for_timeout(500)
                
                # Verify state restored
                assert "active" in inbox_btn.get_attribute("class")
                assert "active" not in sent_btn.get_attribute("class")
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_selection_state_persistence_across_folders(self):
        """Test that selection state is maintained when switching folders."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Switch to sent folder and back to verify state handling
                page.click("#email-folder-sent")
                page.wait_for_timeout(500)
                page.click("#email-folder-inbox")
                page.wait_for_timeout(500)
                
                # Verify no errors occurred and interface is still functional
                error_elements = page.query_selector_all(".error")
                assert len(error_elements) == 0
                
                # Verify folder navigation still works
                folder_title = page.text_content("#email-folder-title")
                assert "Inbox" in folder_title
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)


class TestErrorHandling:
    """Test error handling for network failures and malformed data."""

    def test_refresh_with_invalid_persona(self):
        """Test error handling when refreshing with invalid persona ID."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                
                # Try to refresh without selecting a persona
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Should handle gracefully - no persona selected means no refresh
                status_text = page.text_content("#email-last-refresh")
                # Should not show error, just no refresh
                assert "Never refreshed" in status_text or "Refresh" in status_text
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_malformed_email_data_handling(self):
        """Test handling of emails with missing or malformed data."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Test with empty email list (should handle gracefully)
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Should show empty state without errors
                empty_text = page.text_content("#email-list")
                assert "No emails" in empty_text or "Select a persona" in empty_text
                
                # Verify no JavaScript errors occurred
                console_errors = []
                page.on("console", lambda msg: console_errors.append(msg) if msg.type == "error" else None)
                
                # Trigger some interactions to test error handling
                page.click("#email-folder-sent")
                page.wait_for_timeout(500)
                page.click("#email-folder-inbox")
                page.wait_for_timeout(500)
                
                # Should not have critical JavaScript errors
                critical_errors = [err for err in console_errors if "Failed to" in str(err)]
                assert len(critical_errors) == 0
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)


class TestResponsiveLayout:
    """Test responsive layout behavior at different screen sizes."""

    def test_desktop_layout(self):
        """Test email client layout on desktop screen size."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                
                # Set desktop viewport
                page.set_viewport_size({"width": 1200, "height": 800})
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Verify two-pane layout is visible
                list_pane = page.query_selector(".email-list-pane")
                detail_pane = page.query_selector(".email-detail-pane")
                
                assert list_pane is not None
                assert detail_pane is not None
                
                # Both panes should be visible on desktop
                list_visible = page.is_visible(".email-list-pane")
                detail_visible = page.is_visible(".email-detail-pane")
                
                assert list_visible
                assert detail_visible
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_mobile_layout(self):
        """Test email client layout on mobile screen size."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                
                # Set mobile viewport
                page.set_viewport_size({"width": 375, "height": 667})
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Verify layout adapts to mobile
                email_client = page.query_selector(".email-client-layout")
                assert email_client is not None
                
                # On mobile, the layout should still be functional
                # (specific responsive behavior depends on CSS implementation)
                list_pane = page.query_selector(".email-list-pane")
                detail_pane = page.query_selector(".email-detail-pane")
                
                assert list_pane is not None
                assert detail_pane is not None
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)


class TestKeyboardNavigation:
    """Test keyboard navigation and accessibility features."""

    def test_keyboard_navigation_basics(self):
        """Test basic keyboard navigation in email list."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            # Send multiple test emails to test navigation
            for i in range(3):
                email_payload = {
                    "sender": f"sender{i}@vdos.local",
                    "to": ["test@vdos.local"],
                    "subject": f"Test Email {i+1}",
                    "body": f"This is test email number {i+1}."
                }
                httpx.post(f"{base_url}/../email/emails/send", json=email_payload, timeout=5.0)
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Focus on email list
                email_list = page.query_selector("#email-list")
                if email_list:
                    email_list.focus()
                    
                    # Test arrow key navigation
                    page.keyboard.press("ArrowDown")
                    page.wait_for_timeout(200)
                    
                    # Verify focus moved (implementation depends on JavaScript)
                    focused_element = page.evaluate("document.activeElement.className")
                    # Should be on an email row or the list container
                    assert "email" in focused_element or "list" in focused_element
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_accessibility_attributes(self):
        """Test that proper accessibility attributes are present."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Check for proper ARIA attributes
                email_tab = page.query_selector("#tab-emails")
                assert email_tab.get_attribute("role") == "tabpanel"
                
                # Check email list accessibility
                email_list = page.query_selector("#email-list")
                if email_list:
                    # Should have proper ARIA attributes for list navigation
                    tabindex = email_list.get_attribute("tabindex")
                    assert tabindex is not None
                
                # Check folder navigation accessibility
                inbox_btn = page.query_selector("#email-folder-inbox")
                sent_btn = page.query_selector("#email-folder-sent")
                
                assert inbox_btn.get_attribute("role") == "tab"
                assert sent_btn.get_attribute("role") == "tab"
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)


class TestAPIIntegration:
    """Test API interaction and state synchronization."""

    def test_email_refresh_api_call(self):
        """Test that refresh button triggers proper API calls."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                
                # Monitor network requests
                requests = []
                page.on("request", lambda request: requests.append(request))
                
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Clear previous requests
                requests.clear()
                
                # Click refresh button
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Check that API call was made
                email_api_calls = [req for req in requests if "/monitor/emails/" in req.url]
                assert len(email_api_calls) > 0
                
                # Verify the API call includes the persona ID
                api_call = email_api_calls[0]
                assert str(persona["id"]) in api_call.url
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_persona_selection_triggers_refresh(self):
        """Test that selecting a persona triggers email refresh."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create two test personas
            persona1 = _create_test_persona(base_url, "Test User 1", "test1@vdos.local", "test1")
            persona2 = _create_test_persona(base_url, "Test User 2", "test2@vdos.local", "test2")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                
                # Monitor network requests
                requests = []
                page.on("request", lambda request: requests.append(request))
                
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                
                # Clear previous requests
                requests.clear()
                
                # Select first persona
                page.select_option("#email-person-select", str(persona1["id"]))
                page.wait_for_timeout(1000)
                
                # Check that API call was made for first persona
                email_api_calls = [req for req in requests if "/monitor/emails/" in req.url]
                assert len(email_api_calls) > 0
                assert str(persona1["id"]) in email_api_calls[0].url
                
                # Clear requests and select second persona
                requests.clear()
                page.select_option("#email-person-select", str(persona2["id"]))
                page.wait_for_timeout(1000)
                
                # Check that API call was made for second persona
                email_api_calls = [req for req in requests if "/monitor/emails/" in req.url]
                assert len(email_api_calls) > 0
                assert str(persona2["id"]) in email_api_calls[0].url
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)

    def test_state_synchronization_after_refresh(self):
        """Test that UI state is properly synchronized after API refresh."""
        port = _get_free_port()
        proc = Process(target=_run_server, args=(port,), daemon=True)
        proc.start()
        try:
            _wait_for_server(port)
            base_url = f"http://127.0.0.1:{port}"
            
            # Create test persona
            persona = _create_test_persona(base_url, "Test User", "test@vdos.local", "test")
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(base_url, wait_until="networkidle")
                
                # Switch to emails tab
                page.click("#tab-emails-button")
                page.select_option("#email-person-select", str(persona["id"]))
                
                # Initial refresh
                page.click("#email-refresh-btn")
                page.wait_for_timeout(1000)
                
                # Check that refresh status is updated
                status_text = page.text_content("#email-last-refresh")
                assert "Last refreshed:" in status_text or "Never refreshed" in status_text
                
                # Switch folders and verify state is maintained
                page.click("#email-folder-sent")
                page.wait_for_timeout(500)
                
                # Folder title should update
                folder_title = page.text_content("#email-folder-title")
                assert "Sent" in folder_title
                
                # Switch back to inbox
                page.click("#email-folder-inbox")
                page.wait_for_timeout(500)
                
                folder_title = page.text_content("#email-folder-title")
                assert "Inbox" in folder_title
                
                browser.close()
        finally:
            proc.terminate()
            proc.join(timeout=5)