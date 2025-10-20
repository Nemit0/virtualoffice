#!/usr/bin/env python3
"""
Quick Mobile Chat App Simulation (enhanced)
==========================================

Runs a full multi-week simulation against the running VDOS services, with:
- GPT-backed persona generation (model hint configurable)
- Fast manual tick advancement (only GPT calls are the bottleneck)
- Collection of ALL emails and DMs between team members and sim-manager
- Artifacts saved under `simulation_output/`
"""

import itertools
import threading
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
import uvicorn
import sys

# Ensure local src/ is on path for `virtualoffice` package
_SRC_DIR = Path(__file__).parent / "src"
if _SRC_DIR.exists():
    sys.path.insert(0, str(_SRC_DIR))

from virtualoffice.servers.email import app as email_app
from virtualoffice.servers.chat import app as chat_app
from virtualoffice.sim_manager import create_app as create_sim_app

# Base URLs for the running servers (override via env if needed)
SIM_BASE_URL = os.getenv("VDOS_SIM_BASE_URL", "http://127.0.0.1:8015/api/v1")
EMAIL_BASE_URL = os.getenv("VDOS_EMAIL_BASE_URL", "http://127.0.0.1:8000")
CHAT_BASE_URL = os.getenv("VDOS_CHAT_BASE_URL", "http://127.0.0.1:8001")

# Simulation manager identity defaults (mirror sim_manager defaults)
SIM_MANAGER_EMAIL = os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local")
SIM_MANAGER_HANDLE = os.getenv("VDOS_SIM_HANDLE", "sim-manager")

# Planner model hint (quality vs speed)
MODEL_HINT = os.getenv("VDOS_SIM_MODEL_HINT", "gpt-4.1-nano")

# Output directory
OUTPUT_DIR = Path(__file__).parent / "simulation_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def api_call(method: str, url: str, data: Dict | None = None) -> Dict:
    try:
        if method.upper() == "GET":
            response = requests.get(url)
        elif method.upper() == "POST":
            response = requests.post(url, json=data)
        elif method.upper() == "PUT":
            response = requests.put(url, json=data)
        else:
            raise ValueError(f"Unsupported method: {method}")
        response.raise_for_status()
        return response.json() if response.content else {}
    except Exception as e:
        log(f"API Error: {e} ({method} {url})")
        return {}


def save_json(data: Any, filename: str) -> None:
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Saved: {filename}")


def _norm_handle(handle: str) -> str:
    # Match chat server normalization: strip + lower (keep '@' if present)
    return (handle or "").strip().lower()


def _dm_slug(a: str, b: str) -> str:
    handles = sorted([_norm_handle(a), _norm_handle(b)])
    return f"dm:{handles[0]}:{handles[1]}"


def _parse_host_port(base_url: str) -> tuple[str, int]:
    # very small parser (expects http://host:port)
    try:
        without_scheme = base_url.split("://", 1)[1]
        host, port_s = without_scheme.split("/", 1)[0].split(":", 1)
        return host, int(port_s)
    except Exception:
        return "127.0.0.1", 0


class _ServerHandle:
    def __init__(self, name: str, server: uvicorn.Server, thread: threading.Thread, host: str, port: int) -> None:
        self.name = name
        self.server = server
        self.thread = thread
        self.host = host
        self.port = port


def _start_uvicorn_server(name: str, fastapi_app, host: str, port: int) -> _ServerHandle:
    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server.install_signal_handlers = False
    thread = threading.Thread(target=server.run, name=f"{name}-uvicorn", daemon=True)
    thread.start()
    # Wait briefly for startup
    import time as _t
    deadline = _t.time() + 8
    while not getattr(server, "started", False) and thread.is_alive() and _t.time() < deadline:
        _t.sleep(0.05)
    if not getattr(server, "started", False):
        raise RuntimeError(f"{name} server failed to start on {host}:{port}")
    return _ServerHandle(name, server, thread, host, port)


def _stop_uvicorn_server(handle: _ServerHandle, timeout: float = 5.0) -> None:
    if handle.thread.is_alive():
        handle.server.should_exit = True
        handle.thread.join(timeout)


def create_mobile_team() -> List[Dict[str, Any]]:
    """Create a 4-person mobile development team using the persona generator."""
    log("🎭 Creating mobile development team...")

    team_specs = [
        {
            "prompt": "Experienced agile project manager for mobile app development with strong communication and leadership skills",
            "role_title": "Project Manager",
            "is_head": True,
        },
        {
            "prompt": "Creative UI/UX designer specializing in mobile app interfaces and user experience design",
            "role_title": "UI/UX Designer",
            "is_head": False,
        },
        {
            "prompt": "Senior full stack developer with React Native and Node.js expertise for mobile applications",
            "role_title": "Full Stack Developer",
            "is_head": False,
        },
        {
            "prompt": "DevOps engineer experienced in mobile app deployment, CI/CD, and cloud infrastructure",
            "role_title": "DevOps Engineer",
            "is_head": False,
        },
    ]

    created_personas: List[Dict[str, Any]] = []

    for i, spec in enumerate(team_specs):
        log(f"   Creating {spec['role_title']}...")

        # Generate with GPT (model_hint for higher realism)
        persona_response = api_call(
            "POST",
            f"{SIM_BASE_URL}/personas/generate",
            {"prompt": spec["prompt"], "model_hint": MODEL_HINT},
        )

        if persona_response and "persona" in persona_response:
            persona = persona_response["persona"]

            # Enhance with project-specific details
            persona.update(
                {
                    "is_department_head": spec["is_head"],
                    "email_address": f"{persona['name'].lower().replace(' ', '.')}.{i+1}@quickchat.dev",
                    # Keep '@' prefix; server accepts it
                    "chat_handle": f"@{persona['name'].lower().replace(' ', '_')}",
                    "timezone": [
                        "America/New_York",
                        "America/Los_Angeles",
                        "Europe/London",
                        "Asia/Tokyo",
                    ][i],
                    "work_hours": "09:00-18:00",
                }
            )

            # Create persona in system
            created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
            if created:
                created_personas.append(created)
                log(f"   ✅ Created: {persona['name']} ({spec['role_title']})")

    save_json(created_personas, "mobile_team.json")
    return created_personas


def run_simulation(personas: List[Dict[str, Any]], weeks: int = 4) -> bool:
    """Run the mobile chat app simulation with fast manual advancement."""
    log(f"🚀 Starting {weeks}-week QuickChat mobile app simulation...")

    # Start simulation (include model_hint for more human-like plans)
    start_data = {
        "project_name": "QuickChat Mobile App",
        "project_summary": (
            "Develop a barebone mobile chatting application with core messaging features, "
            "user authentication, real-time chat, and basic UI/UX. Target completion in 4 weeks "
            "with iterative development."
        ),
        "duration_weeks": weeks,
        "include_person_ids": [p["id"] for p in personas],
        "random_seed": 42,
        "model_hint": MODEL_HINT,
    }

    start_response = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_data)
    if not start_response:
        log("❌ Failed to start simulation")
        return False

    log("✅ Simulation started")

    # Manual advancement is CPU-bound and fast; only GPT calls add latency.
    ticks_per_week = 5 * 8 * 60  # 5 days * 8 hours * 60 minutes

    for week in range(weeks):
        log(f"📅 Running Week {week + 1}/{weeks}...")
        remaining = ticks_per_week
        while remaining > 0:
            chunk = 480 if remaining >= 480 else remaining
            advance_data = {"ticks": chunk, "reason": f"Week {week + 1} development cycle"}
            advance_response = api_call("POST", f"{SIM_BASE_URL}/simulation/advance", advance_data)
            if not advance_response:
                break
            remaining -= chunk
            # tiny pause for logs
            time.sleep(0.05)
        sim_state = api_call("GET", f"{SIM_BASE_URL}/simulation")
        save_json(sim_state, f"week_{week + 1}_state.json")

    return True


def collect_all_emails(personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch all emails for team and sim-manager mailboxes and save to JSON."""
    log("📥 Collecting all emails from mailboxes...")
    addresses = [p.get("email_address") for p in personas if p.get("email_address")]
    if SIM_MANAGER_EMAIL not in addresses:
        addresses.append(SIM_MANAGER_EMAIL)

    out: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
    for addr in addresses:
        url = f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails"
        records = api_call("GET", url) or []
        out["mailboxes"][addr] = records
    save_json(out, "all_emails.json")
    return out


def collect_all_chats(personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch all DM histories between team members and with sim-manager and save to JSON."""
    log("💬 Collecting all DM chat histories...")
    handles = [_norm_handle(p.get("chat_handle", "")) for p in personas if p.get("chat_handle")]
    if _norm_handle(SIM_MANAGER_HANDLE) not in handles:
        handles.append(_norm_handle(SIM_MANAGER_HANDLE))

    # Build unique DM slugs for all unordered pairs
    slugs = {_dm_slug(a, b) for a, b in itertools.combinations(handles, 2)}

    out: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "rooms": {}}
    for slug in sorted(slugs):
        url = f"{CHAT_BASE_URL}/rooms/{slug}/messages"
        records = api_call("GET", url)
        # Only record rooms that exist (non-empty dict/list expected)
        if isinstance(records, list) and records:
            out["rooms"][slug] = records
    save_json(out, "all_chats.json")
    return out


def generate_reports(personas: List[Dict[str, Any]]) -> None:
    """Generate comprehensive final reports (state, events, token usage, per-person)."""
    log("📊 Generating final reports...")

    final_state = api_call("GET", f"{SIM_BASE_URL}/simulation")
    events = api_call("GET", f"{SIM_BASE_URL}/events")
    tokens = api_call("GET", f"{SIM_BASE_URL}/simulation/token-usage")

    all_reports: Dict[str, Any] = {}
    for persona in personas:
        pid = persona["id"]
        daily_reports = api_call("GET", f"{SIM_BASE_URL}/people/{pid}/daily-reports?limit=200")
        hourly_plans = api_call(
            "GET", f"{SIM_BASE_URL}/people/{pid}/plans?plan_type=hourly&limit=200"
        )
        all_reports[persona["name"]] = {"daily_reports": daily_reports, "hourly_plans": hourly_plans}

    final_report = {
        "simulation_completed": datetime.now().isoformat(),
        "project": "QuickChat Mobile App - 4 Week Development",
        "team": personas,
        "final_state": final_state,
        "events": events,
        "token_usage": tokens,
        "reports_by_person": all_reports,
        "summary": {
            "total_events": len(events) if isinstance(events, list) else 0,
            "total_team_members": len(personas),
            "simulation_duration": f"{final_state.get('current_tick', 0)} ticks",
            "total_tokens": (tokens or {}).get("total_tokens", 0),
        },
    }

    save_json(final_report, "final_simulation_report.json")


def main() -> None:
    log("Starting Enhanced Quick Simulation...")
    # Optionally speed auto ticks if ever used
    os.environ.setdefault("VDOS_TICK_INTERVAL_SECONDS", "0.02")
    # Start local servers in-process
    handles: list[_ServerHandle] = []
    try:
        log("Starting Email server...")
        e_host, e_port = _parse_host_port(EMAIL_BASE_URL)
        if not e_port:
            e_host, e_port = "127.0.0.1", 8000
        handles.append(_start_uvicorn_server("email", email_app, e_host, e_port))
        log("Starting Chat server...")
        c_host, c_port = _parse_host_port(CHAT_BASE_URL)
        if not c_port:
            c_host, c_port = "127.0.0.1", 8001
        handles.append(_start_uvicorn_server("chat", chat_app, c_host, c_port))
        log("Starting Simulation Manager...")
        sim_app = create_sim_app()
        # Use default 8015; allow override through VDOS_SIM_BASE_URL if set
        sim_base = os.getenv("VDOS_SIM_BASE_URL", "http://127.0.0.1:8015/api/v1")
        s_host, s_port = _parse_host_port(sim_base)
        if not s_port:
            s_host, s_port = "127.0.0.1", 8015
        handles.append(_start_uvicorn_server("sim", sim_app, s_host, s_port))

        personas = create_mobile_team()
        if not personas:
            log("No personas created; aborting.")
            return
        if not run_simulation(personas, weeks=4):
            log("Simulation failed to start; aborting.")
            return
        # Collect comms artifacts before generating final report
        collect_all_emails(personas)
        collect_all_chats(personas)
        generate_reports(personas)
        log("✅ Enhanced Quick Simulation complete.")
    finally:
        # Tear down servers
        for h in handles:
            try:
                _stop_uvicorn_server(h)
            except Exception:
                pass


if __name__ == "__main__":
    main()
