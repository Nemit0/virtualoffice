import os
import socket
import time
from multiprocessing import Process

import httpx
import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None

from virtualoffice.sim_manager.app import create_app

RUN_PLAYWRIGHT = os.getenv("VDOS_RUN_PLAYWRIGHT") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_PLAYWRIGHT or sync_playwright is None,
    reason="Playwright smoke test disabled (set VDOS_RUN_PLAYWRIGHT=1 and install playwright)",
)


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server(port: int) -> None:
    import uvicorn

    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server.run()


def _wait_for_server(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/v1/simulation"
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError("Server did not start in time")


def test_web_dashboard_start_stop():
    port = _get_free_port()
    proc = Process(target=_run_server, args=(port,), daemon=True)
    proc.start()
    try:
        _wait_for_server(port)
        base_url = f"http://127.0.0.1:{port}"

        # Seed personas
        hana_payload = {
            "name": "Hana Kim",
            "role": "Designer",
            "timezone": "Asia/Seoul",
            "work_hours": "09:00-17:00",
            "break_frequency": "50/10 cadence",
            "communication_style": "Warm async",
            "email_address": "hana.kim@vdos.local",
            "chat_handle": "hana",
            "skills": ["Figma", "UX"],
            "personality": ["Collaborative", "Calm"],
            "schedule": [
                {"start": "09:00", "end": "10:00", "activity": "Stand-up"},
                {"start": "10:00", "end": "12:00", "activity": "Design work"},
            ],
            "objectives": ["Ship mockups"],
            "metrics": ["Mockups approved"],
        }
        dev_payload = {
            "name": "Elliot Park",
            "role": "Full-Stack Developer",
            "timezone": "America/Los_Angeles",
            "work_hours": "08:00-16:00",
            "break_frequency": "45/15 cadence",
            "communication_style": "Concise async",
            "email_address": "elliot.park@vdos.local",
            "chat_handle": "elliot",
            "skills": ["React", "Python"],
            "personality": ["Pragmatic", "Supportive"],
            "schedule": [
                {"start": "08:00", "end": "09:00", "activity": "Code review"},
                {"start": "09:00", "end": "11:00", "activity": "Feature work"},
            ],
            "objectives": ["Deliver web experience"],
            "metrics": ["Tickets closed"],
        }
        for payload in (hana_payload, dev_payload):
            resp = httpx.post(f"{base_url}/api/v1/people", json=payload, timeout=5.0)
            resp.raise_for_status()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(base_url, wait_until="networkidle")
            page.wait_for_selector(".person-card", timeout=10000)

            page.fill("#project-name", "WebUI Test Project")
            page.fill("#project-summary", "Smoke test from Playwright")
            page.click("#start-btn")
            page.wait_for_selector("#state-status", timeout=20000)
            page.wait_for_function("() => document.getElementById('state-status').textContent.includes('running')", timeout=20000)
            page.wait_for_timeout(500)
            page.click("#stop-btn")
            page.wait_for_function("() => document.getElementById('state-status').textContent.includes('stopped')", timeout=20000)
            browser.close()
    finally:
        proc.terminate()
        proc.join(timeout=5)
