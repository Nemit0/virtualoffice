#!/usr/bin/env python3
"""
Email Threading Test Script
============================

Tests the new email threading feature with reply syntax.

Expected behavior:
1. PM sends an initial email to Dev
2. Dev replies using "Reply at HH:MM to [email-id]" syntax
3. Reply should have the same thread_id as the original email
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
import uvicorn

SRC_DIR = Path(__file__).parent.parent / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from virtualoffice.servers.email import app as email_app
from virtualoffice.servers.chat import app as chat_app
from virtualoffice.sim_manager import create_app as create_sim_app
from virtualoffice.sim_manager.gateways import HttpEmailGateway, HttpChatGateway
from virtualoffice.sim_manager.engine import SimulationEngine

SIM_BASE_URL = os.getenv("VDOS_SIM_BASE_URL", "http://127.0.0.1:8015/api/v1")
EMAIL_BASE_URL = os.getenv("VDOS_EMAIL_BASE_URL", "http://127.0.0.1:8000")
CHAT_BASE_URL = os.getenv("VDOS_CHAT_BASE_URL", "http://127.0.0.1:8001")

MODEL_HINT = os.getenv("VDOS_SIM_MODEL_HINT", "gpt-4o-mini")
TICK_INTERVAL_SECONDS = float(os.getenv("VDOS_TICK_INTERVAL_SECONDS", "0.0001"))

ROOT_OUTPUT = Path(__file__).parent.parent / "simulation_output"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = ROOT_OUTPUT / f"test_threading_{TIMESTAMP}"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def api_call(method: str, url: str, data: Dict | None = None, *, timeout: float | None = 240.0) -> Dict:
    try:
        kwargs = {"timeout": timeout} if timeout is not None else {}
        if method == "GET":
            r = requests.get(url, **kwargs)
        elif method == "POST":
            r = requests.post(url, json=data, **kwargs)
        elif method == "PUT":
            r = requests.put(url, json=data, **kwargs)
        else:
            raise ValueError("Unsupported method")
        r.raise_for_status()
        return r.json() if r.content else {}
    except Exception as e:
        log(f"API Error: {e} ({method} {url})")
        return {}


def save_json(data: Any, filename: str) -> None:
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Saved: {OUTPUT_DIR.name}/{filename}")


class _Srv:
    def __init__(self, name: str, server: uvicorn.Server, thread: threading.Thread, host: str, port: int) -> None:
        self.name = name
        self.server = server
        self.thread = thread
        self.host = host
        self.port = port


def _parse_host_port(base_url: str) -> tuple[str, int]:
    try:
        without = base_url.split("://", 1)[1]
        host, port_s = without.split("/", 1)[0].split(":", 1)
        return host, int(port_s)
    except Exception:
        return "127.0.0.1", 0


def _start_server(name: str, app, host: str, port: int) -> _Srv:
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server.install_signal_handlers = False
    t = threading.Thread(target=server.run, name=f"{name}-uvicorn", daemon=True)
    t.start()
    deadline = time.time() + 8
    while not getattr(server, "started", False) and t.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not getattr(server, "started", False):
        raise RuntimeError(f"{name} failed to start on {host}:{port}")
    return _Srv(name, server, t, host, port)


def _free_port() -> int:
    import socket as _s
    with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server_ready(url: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def _maybe_start_services(force: bool = False) -> list[_Srv]:
    handles: list[_Srv] = []
    global EMAIL_BASE_URL, CHAT_BASE_URL, SIM_BASE_URL
    if force:
        eport, cport, sport = _free_port(), _free_port(), _free_port()
        EMAIL_BASE_URL = f"http://127.0.0.1:{eport}"
        CHAT_BASE_URL = f"http://127.0.0.1:{cport}"
        SIM_BASE_URL = f"http://127.0.0.1:{sport}/api/v1"
    # Email
    eh, ep = _parse_host_port(EMAIL_BASE_URL)
    if force or not _server_ready(f"{EMAIL_BASE_URL}/docs", timeout=1.5):
        log(f"Starting email server: {eh or '127.0.0.1'}:{ep or 8000}...")
        handles.append(_start_server("email", email_app, eh or "127.0.0.1", ep or 8000))
    # Chat
    ch, cp = _parse_host_port(CHAT_BASE_URL)
    if force or not _server_ready(f"{CHAT_BASE_URL}/docs", timeout=1.5):
        log(f"Starting chat server: {ch or '127.0.0.1'}:{cp or 8001}...")
        handles.append(_start_server("chat", chat_app, ch or "127.0.0.1", cp or 8001))
    # Sim
    sh, sp = _parse_host_port(SIM_BASE_URL)
    if force or not _server_ready(f"{SIM_BASE_URL.replace('/api/v1','')}/docs", timeout=1.5):
        log(f"Starting simulation manager: {sh or '127.0.0.1'}:{sp or 8015}...")
        email_gateway = HttpEmailGateway(base_url=EMAIL_BASE_URL)
        chat_gateway = HttpChatGateway(base_url=CHAT_BASE_URL)
        os.environ["VDOS_LOCALE"] = "en"
        engine = SimulationEngine(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            tick_interval_seconds=TICK_INTERVAL_SECONDS,
            hours_per_day=480,
        )
        sim = create_sim_app(engine)
        handles.append(_start_server("sim", sim, sh or "127.0.0.1", sp or 8015))
    return handles


def _stop_services(handles: list[_Srv]) -> None:
    for h in handles:
        try:
            if h.thread.is_alive():
                h.server.should_exit = True
                h.thread.join(5)
        except Exception:
            pass


def _full_reset() -> None:
    log("🧹 Full reset...")
    api_call("POST", f"{SIM_BASE_URL}/simulation/stop", {})
    r = api_call("POST", f"{SIM_BASE_URL}/admin/hard-reset", {})
    if not r:
        api_call("POST", f"{SIM_BASE_URL}/simulation/full-reset", {})
    st = api_call("GET", f"{SIM_BASE_URL}/simulation", {})
    ppl = api_call("GET", f"{SIM_BASE_URL}/people", {})
    tick = st.get("current_tick", None) if isinstance(st, dict) else None
    log(f"   State: tick={tick}, people count={len(ppl) if isinstance(ppl, list) else '?'}")


def create_team() -> List[Dict[str, Any]]:
    log("🎭 Creating team (PM, Dev)...")
    specs = [
        {"prompt": "English-speaking Project Manager, Agile/Scrum expert", "is_head": True, "tz": "America/New_York", "handle": "pm"},
        {"prompt": "English-speaking Full-stack Developer, React/Node expert", "is_head": False, "tz": "America/New_York", "handle": "dev"},
    ]
    people: List[Dict[str, Any]] = []
    for i, s in enumerate(specs):
        log(f"   → POST /personas/generate ({s['handle']})")
        gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {"prompt": s["prompt"], "model_hint": MODEL_HINT}, timeout=120)
        if not gen or "persona" not in gen:
            continue
        persona = gen["persona"]
        if isinstance(persona.get("schedule"), list):
            persona.pop("schedule", None)
        persona.setdefault("break_frequency", "50/10 cadence")
        persona.setdefault("communication_style", "Async")
        persona.update({
            "is_department_head": bool(s["is_head"]),
            "email_address": f"{s['handle']}.1@threading.test",
            "chat_handle": s["handle"],
            "timezone": s["tz"],
            "work_hours": "09:00-18:00",
        })
        log(f"   → POST /people ({persona['email_address']})")
        created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
        if created:
            people.append(created)
            log(f"   ✅ {created['name']} ({created['role']})")
    save_json(people, "team_personas.json")
    return people


def run_threading_test(people: List[Dict[str, Any]]) -> bool:
    log("🚀 Starting threading test (1 day)...")

    start_request = {
        "project_name": "Threading Test Project",
        "project_summary": "Test project to verify email threading with reply syntax",
        "duration_weeks": 1,
        "total_duration_weeks": 1,
        "projects": [],
        "include_person_ids": [p["id"] for p in people],
        "random_seed": 42,
        "model_hint": MODEL_HINT,
    }

    log("   → POST /simulation/start...")
    ok = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_request, timeout=300)
    if not ok:
        log("❌ Simulation start failed")
        return False
    log("✅ Initialization complete")

    # Run for 1 day (8 hours * 60 minutes)
    ticks_total = 1 * 8 * 60

    # Kickoff
    api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": 1, "reason": "kickoff"}, timeout=300)
    remaining = ticks_total - 1
    progressed = 1
    step = 60

    while remaining > 0:
        chunk = step if remaining >= step else remaining
        log(f"   → Advancing {chunk} ticks; progressed={progressed}/{ticks_total}")
        res = api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": chunk, "reason": "auto"}, timeout=600)
        if not res:
            log(f"   ! Advance failed at tick {progressed}")
            break
        remaining -= chunk
        progressed += chunk
        time.sleep(0.02)

    return True


def analyze_threading(people: List[Dict[str, Any]]) -> None:
    log("📊 Analyzing threading results...")

    # Collect all emails
    addrs = [p.get("email_address") for p in people if p.get("email_address")]
    all_emails = []

    for addr in addrs:
        recs = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
        all_emails.extend(recs)

    # Group by thread_id
    threads = {}
    no_thread = []

    for email in all_emails:
        thread_id = email.get("thread_id")
        if thread_id:
            if thread_id not in threads:
                threads[thread_id] = []
            threads[thread_id].append(email)
        else:
            no_thread.append(email)

    log(f"\n📧 Email Threading Analysis:")
    log(f"   Total emails: {len(all_emails)}")
    log(f"   Emails with thread_id: {len(all_emails) - len(no_thread)}")
    log(f"   Emails without thread_id: {len(no_thread)}")
    log(f"   Unique threads: {len(threads)}")

    if threads:
        log(f"\n🧵 Thread Details:")
        for thread_id, emails in threads.items():
            log(f"   Thread {thread_id}:")
            log(f"      Emails in thread: {len(emails)}")
            for i, email in enumerate(sorted(emails, key=lambda e: e.get('sent_at', '')), 1):
                log(f"      [{i}] From: {email.get('sender')} To: {email.get('to')} Subject: {email.get('subject', 'No subject')[:50]}")

    # Save analysis
    analysis = {
        "total_emails": len(all_emails),
        "emails_with_threads": len(all_emails) - len(no_thread),
        "emails_without_threads": len(no_thread),
        "unique_threads": len(threads),
        "threads": {tid: [{"from": e.get("sender"), "to": e.get("to"), "subject": e.get("subject"), "sent_at": e.get("sent_at")} for e in emails] for tid, emails in threads.items()}
    }
    save_json(analysis, "threading_analysis.json")


def collect_logs(people: List[Dict[str, Any]]) -> None:
    log("📥 Collecting email/chat logs...")
    addrs = [p.get("email_address") for p in people if p.get("email_address")]

    emails: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
    for addr in addrs:
        recs = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
        emails["mailboxes"][addr] = recs
    save_json(emails, "email_communications.json")


def main() -> int:
    log("Email Threading Test Starting...")
    handles: list[_Srv] = []
    team: List[Dict[str, Any]] = []
    try:
        handles = _maybe_start_services(force=True)
        _full_reset()
        team = create_team()
        if len(team) < 2:
            log("❌ Team creation failed")
            return 1
        if not run_threading_test(team):
            log("❌ Simulation failed")
            return 1
        collect_logs(team)
        analyze_threading(team)

        # Final state
        st = api_call("GET", f"{SIM_BASE_URL}/simulation")
        save_json(st, "final_state.json")
        log(f"✅ Complete. Output: {OUTPUT_DIR}")
        return 0
    finally:
        _stop_services(handles)


if __name__ == "__main__":
    sys.exit(main())
