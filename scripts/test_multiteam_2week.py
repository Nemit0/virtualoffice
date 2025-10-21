#!/usr/bin/env python3
"""
Multi-Team 2-Week Test Simulation
==================================

Tests the multi-team organizational structure:
- 1 Department with 1 Department Head
- 2 Teams (Team A and Team B)
- Each team has 1 Team Head (PM) + 2 Developers
- Each team works on 1 project for 2 weeks
- All report to Department Head

Total: 7 people (1 dept head + 2 team heads + 4 devs)
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
OUTPUT_DIR = ROOT_OUTPUT / f"multiteam_2week_{TIMESTAMP}"
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
        os.environ["VDOS_LOCALE"] = "ko"
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
    log(f"   State: tick={tick}, people count={len(ppl) if isinstance(ppl, list) else '?'}  ")


def create_multiteam_organization() -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Creates organizational structure:
    - 1 Department Head
    - Team A: 1 PM + 2 Devs
    - Team B: 1 PM + 2 Devs

    Returns (people, teams_dict) where teams_dict has team_a and team_b person IDs
    """
    log("🎭 Creating multi-team organization...")

    specs = [
        # Department Head
        {
            "prompt": "엔지니어링 부문장, 여러 제품 팀을 총괄하며 전략적 방향 제시, 한국어",
            "explicit_name": "김지원 부문장",
            "is_head": True,
            "team": None,
            "handle": "director",
            "role_hint": "Engineering Director"
        },
        # Team A
        {
            "prompt": "제품 관리자(PM), 팀A 모바일 앱 개발 리드, 애자일/스크럼 경험, 한국어",
            "explicit_name": "박준호 PM",
            "is_head": False,
            "team": "팀A",
            "handle": "pm_a",
            "role_hint": "Product Manager"
        },
        {
            "prompt": "시니어 풀스택 개발자, 팀A 모바일 전문, React Native/Node.js 능숙, 한국어",
            "explicit_name": "이민석",
            "is_head": False,
            "team": "팀A",
            "handle": "dev_a1",
            "role_hint": "Senior Developer"
        },
        {
            "prompt": "프론트엔드 개발자, 팀A UI/UX 담당, React/디자인 시스템 경험, 한국어",
            "explicit_name": "최수진",
            "is_head": False,
            "team": "팀A",
            "handle": "dev_a2",
            "role_hint": "Frontend Developer"
        },
        # Team B
        {
            "prompt": "제품 관리자(PM), 팀B 분석 대시보드 리드, 데이터 제품 경험, 한국어",
            "explicit_name": "정은지 PM",
            "is_head": False,
            "team": "팀B",
            "handle": "pm_b",
            "role_hint": "Product Manager"
        },
        {
            "prompt": "백엔드 개발자, 팀B 데이터 인프라 전문, Python/SQL/클라우드 능숙, 한국어",
            "explicit_name": "강민우",
            "is_head": False,
            "team": "팀B",
            "handle": "dev_b1",
            "role_hint": "Backend Developer"
        },
        {
            "prompt": "데이터 엔지니어, 팀B 분석 전문, ETL/데이터 파이프라인/BigQuery 경험, 한국어",
            "explicit_name": "윤서영",
            "is_head": False,
            "team": "팀B",
            "handle": "dev_b2",
            "role_hint": "Data Engineer"
        },
    ]

    people: List[Dict[str, Any]] = []
    teams = {"team_a": [], "team_b": []}

    for i, s in enumerate(specs):
        log(f"   → POST /personas/generate ({s['handle']})...")
        gen_request = {"prompt": s["prompt"], "model_hint": MODEL_HINT}
        if "explicit_name" in s:
            gen_request["explicit_name"] = s["explicit_name"]
        gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", gen_request, timeout=120)
        if not gen or "persona" not in gen:
            log(f"   ⚠️  Failed to generate {s['handle']}")
            continue

        persona = gen["persona"]
        if isinstance(persona.get("schedule"), list):
            persona.pop("schedule", None)

        persona.setdefault("break_frequency", "50/10 cadence")
        persona.setdefault("communication_style", "Async")
        persona.update({
            "is_department_head": bool(s["is_head"]),
            "team_name": s["team"],
            "email_address": f"{s['handle']}.1@multiteam.test",
            "chat_handle": s["handle"],
            "timezone": "Asia/Seoul",
            "work_hours": "09:00-18:00",
        })

        log(f"   → POST /people ({persona['email_address']})...")
        created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
        if created:
            people.append(created)
            log(f"   ✅ {created['name']} ({created['role']}) - {s['team'] or 'Department Head'}")

            # Track team membership
            if s["team"] == "Team A":
                teams["team_a"].append(created["id"])
            elif s["team"] == "Team B":
                teams["team_b"].append(created["id"])

    save_json(people, "organization_personas.json")
    save_json(teams, "team_assignments.json")
    log(f"   ✅ Created {len(people)} people: 1 director + {len(teams['team_a'])} Team A + {len(teams['team_b'])} Team B")

    return people, teams


def run_multiteam_simulation(people: List[Dict[str, Any]], teams: Dict[str, Any]) -> bool:
    """
    Runs 2-week simulation with 2 projects:
    - Team A: Mobile App MVP (2 weeks)
    - Team B: Analytics Dashboard (2 weeks)
    """
    log("🚀 Starting 2-week multi-team simulation...")

    start_request = {
        "project_name": "Multi-Team Engineering Department",
        "project_summary": "Department with two product teams working on separate projects",
        "duration_weeks": 2,
        "total_duration_weeks": 2,
        "projects": [
            {
                "project_name": "Mobile App MVP",
                "project_summary": "Build cross-platform mobile app with user authentication and core features",
                "start_week": 1,
                "duration_weeks": 2,
                "assigned_person_ids": teams["team_a"]
            },
            {
                "project_name": "Analytics Dashboard",
                "project_summary": "Create real-time analytics dashboard with data visualization and reporting",
                "start_week": 1,
                "duration_weeks": 2,
                "assigned_person_ids": teams["team_b"]
            }
        ],
        "include_person_ids": [p["id"] for p in people],
        "random_seed": 42,
        "model_hint": MODEL_HINT,
    }

    log("   → POST /simulation/start...")
    ok = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_request, timeout=600)
    if not ok:
        log("❌ Simulation start failed")
        return False
    log("✅ Initialization complete")

    # Run for 2 weeks (2 * 5 days * 8 hours * 60 minutes)
    ticks_total = 2 * 5 * 8 * 60

    # Kickoff
    log("   → Kickoff tick...")
    api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": 1, "reason": "kickoff"}, timeout=600)
    remaining = ticks_total - 1
    progressed = 1
    step = 30  # Advance in 30-minute chunks (reduced from 60 for better responsiveness)

    while remaining > 0:
        chunk = step if remaining >= step else remaining
        log(f"   → Advancing {chunk} ticks; progressed={progressed}/{ticks_total} ({100*progressed//ticks_total}%)")
        res = api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": chunk, "reason": "auto"}, timeout=1200)
        if not res:
            log(f"   ! Advance failed at tick {progressed}")
            break
        remaining -= chunk
        progressed += chunk
        time.sleep(0.02)

    log(f"✅ Simulation complete: {progressed} ticks")
    return True


def collect_logs(people: List[Dict[str, Any]]) -> None:
    log("📥 Collecting simulation artifacts...")

    # Email communications
    addrs = [p.get("email_address") for p in people if p.get("email_address")]
    emails: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
    for addr in addrs:
        recs = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
        emails["mailboxes"][addr] = recs
    save_json(emails, "email_communications.json")
    log(f"   ✅ Collected {sum(len(v) for v in emails['mailboxes'].values())} emails")

    # Chat messages
    chats = api_call("GET", f"{CHAT_BASE_URL}/messages") or []
    save_json({"collected_at": datetime.now().isoformat(), "messages": chats}, "chat_messages.json")
    log(f"   ✅ Collected {len(chats)} chat messages")

    # Simulation state
    st = api_call("GET", f"{SIM_BASE_URL}/simulation")
    save_json(st, "final_state.json")

    # Project plans
    plans = api_call("GET", f"{SIM_BASE_URL}/project-plans") or []
    save_json(plans, "project_plans.json")
    log(f"   ✅ Collected {len(plans)} project plans")


def main() -> int:
    log("=" * 60)
    log("Multi-Team 2-Week Test Simulation")
    log("=" * 60)
    handles: list[_Srv] = []
    people: List[Dict[str, Any]] = []
    teams: Dict[str, Any] = {}

    try:
        handles = _maybe_start_services(force=True)
        _full_reset()
        people, teams = create_multiteam_organization()

        if len(people) < 7:
            log(f"❌ Organization creation incomplete: only {len(people)} people created")
            return 1

        if not run_multiteam_simulation(people, teams):
            log("❌ Simulation failed")
            return 1

        collect_logs(people)

        log("=" * 60)
        log(f"✅ Simulation Complete!")
        log(f"   Output: {OUTPUT_DIR}")
        log("=" * 60)
        return 0

    except Exception as e:
        log(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        _stop_services(handles)


if __name__ == "__main__":
    sys.exit(main())
