#!/usr/bin/env python3
"""
1주 간단 다중 프로젝트 테스트 (한국어)
====================================

2개의 겹치는 프로젝트로 1주 테스트:
- 프로젝트 A: 1주 전체 (모바일 앱)
- 프로젝트 B: 1주 전체 (웹 대시보드)

목적: 동시 다중 프로젝트 작업이 제대로 작동하는지 빠르게 확인
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

SRC_DIR = Path(__file__).parent / "src"
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

MODEL_HINT = os.getenv("VDOS_SIM_MODEL_HINT", "gpt-4.1-mini")
TICK_INTERVAL_SECONDS = float(os.getenv("VDOS_TICK_INTERVAL_SECONDS", "0.00001"))

ROOT_OUTPUT = Path(__file__).parent / "simulation_output"
# Add datetime stamp to output directory
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = ROOT_OUTPUT / f"quick_multiproject_1week_ko_{TIMESTAMP}"
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
        log(f"이메일 서버 시작: {eh or '127.0.0.1'}:{ep or 8000}…")
        handles.append(_start_server("email", email_app, eh or "127.0.0.1", ep or 8000))
    # Chat
    ch, cp = _parse_host_port(CHAT_BASE_URL)
    if force or not _server_ready(f"{CHAT_BASE_URL}/docs", timeout=1.5):
        log(f"채팅 서버 시작: {ch or '127.0.0.1'}:{cp or 8001}…")
        handles.append(_start_server("chat", chat_app, ch or "127.0.0.1", cp or 8001))
    # Sim
    sh, sp = _parse_host_port(SIM_BASE_URL)
    if force or not _server_ready(f"{SIM_BASE_URL.replace('/api/v1','')}/docs", timeout=1.5):
        log(f"시뮬레이션 매니저 시작: {sh or '127.0.0.1'}:{sp or 8015}…")
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
    log("🧹 전체 초기화…")
    api_call("POST", f"{SIM_BASE_URL}/simulation/stop", {})
    r = api_call("POST", f"{SIM_BASE_URL}/admin/hard-reset", {})
    if not r:
        api_call("POST", f"{SIM_BASE_URL}/simulation/full-reset", {})
    st = api_call("GET", f"{SIM_BASE_URL}/simulation", {})
    ppl = api_call("GET", f"{SIM_BASE_URL}/people", {})
    tick = st.get("current_tick", None) if isinstance(st, dict) else None
    log(f"   상태: tick={tick}, 인원수={len(ppl) if isinstance(ppl, list) else '?'}")


def create_team_simple() -> List[Dict[str, Any]]:
    """Create team with minimal GPT calls - only 2 people"""
    log("🎭 간단 팀 생성 (PM, 개발자만)…")
    specs = [
        {"prompt": "Agile PM managing multiple projects, Korean speaker", "is_head": True, "tz": "Asia/Seoul", "handle": "pm"},
        {"prompt": "Full-stack developer, React/Node/API expert, Korean speaker", "is_head": False, "tz": "Asia/Seoul", "handle": "dev"},
    ]
    people: List[Dict[str, Any]] = []
    for s in specs:
        log(f"   → POST /personas/generate ({s['handle']})")
        gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {"prompt": s["prompt"], "model_hint": MODEL_HINT}, timeout=120)
        if not gen or "persona" not in gen:
            log(f"   ⚠️  Failed to generate {s['handle']}")
            continue
        persona = gen["persona"]
        if isinstance(persona.get("schedule"), list):
            persona.pop("schedule", None)
        persona.setdefault("break_frequency", "2 hours")
        persona.setdefault("communication_style", "Direct and collaborative")
        persona.update({
            "is_department_head": bool(s["is_head"]),
            "email_address": f"{s['handle']}.1@quicktest.dev",
            "chat_handle": s["handle"],
            "timezone": s["tz"],
            "work_hours": "09:00-18:00",
        })
        log(f"   → POST /people ({persona['email_address']})")
        created = api_call("POST", f"{SIM_BASE_URL}/people", persona, timeout=60)
        if created:
            people.append(created)
            log(f"   ✅ {created['name']} ({created['role']})")
        else:
            log(f"   ❌ Failed to create person")
    save_json(people, "team_personas.json")
    return people


def run_multiproject_test(people: List[Dict[str, Any]]) -> tuple[bool, Dict[str, Any]]:
    log("🚀 다중 프로젝트 1주 테스트 시작…")
    start_time = time.time()
    start_datetime = datetime.now().isoformat()

    # 2 overlapping projects for 1 week
    projects = [
        {
            "project_name": "모바일 채팅 앱",
            "project_summary": "실시간 메시징 및 인증 기능을 갖춘 모바일 앱",
            "start_week": 1,
            "duration_weeks": 1,
            "assigned_person_ids": None,
        },
        {
            "project_name": "웹 관리 대시보드",
            "project_summary": "사용자 관리 및 통계 확인용 웹 대시보드",
            "start_week": 1,
            "duration_weeks": 1,
            "assigned_person_ids": None,
        },
    ]

    start_request = {
        "project_name": "통합 플랫폼 (1주 테스트)",
        "project_summary": "모바일 앱과 웹 대시보드 동시 개발",
        "duration_weeks": 1,
        "total_duration_weeks": 1,
        "projects": projects,
        "include_person_ids": [p["id"] for p in people],
        "random_seed": 42,
        "model_hint": MODEL_HINT,
    }

    log("   → POST /simulation/start (with retry)…")
    ok = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_request, timeout=300)
    if not ok:
        log("❌ 시뮬레이션 시작 실패")
        return False, {}
    log("✅ 초기화 완료")

    # 1 week * 5 days * 8 hours * 60 minutes
    ticks_total = 1 * 5 * 8 * 60

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
            log(f"   ! 진행 실패: tick {progressed}")
            break
        remaining -= chunk
        progressed += chunk
        time.sleep(0.01)

    log(f"✅ 시뮬레이션 완료: {progressed}/{ticks_total} ticks")

    # Calculate duration
    end_time = time.time()
    end_datetime = datetime.now().isoformat()
    duration_seconds = end_time - start_time
    duration_hours = duration_seconds / 3600

    duration_info = {
        "start_time": start_datetime,
        "end_time": end_datetime,
        "duration_seconds": duration_seconds,
        "duration_hours": duration_hours,
        "duration_formatted": f"{int(duration_hours)}h {int((duration_seconds % 3600) / 60)}m {int(duration_seconds % 60)}s"
    }

    return True, duration_info


def collect_logs(people: List[Dict[str, Any]]) -> None:
    log("📥 이메일/채팅 로그 수집…")
    addrs = [p.get("email_address") for p in people if p.get("email_address")]
    sim_email = os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local")
    if sim_email not in addrs:
        addrs.append(sim_email)

    emails: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
    for addr in addrs:
        recs = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
        emails["mailboxes"][addr] = recs
    save_json(emails, "email_communications.json")

    import itertools
    handles = [(_ or "").strip().lower() for _ in [p.get("chat_handle") for p in people]]
    sim_handle = os.getenv("VDOS_SIM_HANDLE", "sim-manager").lower()
    if sim_handle not in handles:
        handles.append(sim_handle)

    def _dm_slug(a: str, b: str) -> str:
        aa, bb = sorted([a.lower(), b.lower()])
        return f"dm:{aa}:{bb}"

    rooms = {_dm_slug(a, b) for a, b in itertools.combinations(handles, 2)}
    chats: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "rooms": {}}
    for slug in sorted(rooms):
        recs = api_call("GET", f"{CHAT_BASE_URL}/rooms/{slug}/messages")
        if isinstance(recs, list) and recs:
            chats["rooms"][slug] = recs
    save_json(chats, "chat_communications.json")


def main() -> int:
    log("한국어 간단 다중 프로젝트 1주 테스트 시작…")
    handles: list[_Srv] = []
    team: List[Dict[str, Any]] = []
    try:
        handles = _maybe_start_services(force=True)
        _full_reset()
        team = create_team_simple()
        if len(team) < 2:
            log("❌ 팀 생성 실패 (최소 2명 필요)")
            return 1
        success, duration_info = run_multiproject_test(team)
        if not success:
            log("❌ 시뮬레이션 실패")
            return 1
        collect_logs(team)
        st = api_call("GET", f"{SIM_BASE_URL}/simulation")
        if st and duration_info:
            st["simulation_duration"] = duration_info
        save_json(st, "final_state.json")
        if duration_info:
            log(f"⏱️  시뮬레이션 소요시간: {duration_info['duration_formatted']}")
        log(f"✅ 완료. 출력: {OUTPUT_DIR}")
        return 0
    finally:
        _stop_services(handles)


if __name__ == "__main__":
    sys.exit(main())
