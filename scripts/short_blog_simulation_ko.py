#!/usr/bin/env python3
"""
짧은 5일 블로그 시뮬레이션 (2명, 한국어)
=======================================

로컬 VDOS 서비스를 띄우고(또는 재사용), 두 명(디자이너/풀스택 개발자) 팀을 생성한 뒤
5영업일 시뮬레이션을 진행합니다. 생성된 모든 이메일/DM 및 리포트를 다음 경로에 저장합니다:

  simulation_output/blog_5day_ko/

영어판 short_blog_simulation.py와 동일한 흐름이되, 모든 프롬프트/출력은 한국어를 기본으로 합니다.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import socket

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
from virtualoffice.sim_manager.planner import GPTPlanner


SIM_BASE_URL = os.getenv("VDOS_SIM_BASE_URL", "http://127.0.0.1:8015/api/v1")
EMAIL_BASE_URL = os.getenv("VDOS_EMAIL_BASE_URL", "http://127.0.0.1:8000")
CHAT_BASE_URL = os.getenv("VDOS_CHAT_BASE_URL", "http://127.0.0.1:8001")
SIM_MANAGER_EMAIL = os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local")
SIM_MANAGER_HANDLE = os.getenv("VDOS_SIM_HANDLE", "sim-manager")

MODEL_HINT = os.getenv("VDOS_SIM_MODEL_HINT", "gpt-4o-mini")
TICK_INTERVAL_SECONDS = 0.0002

ROOT_OUTPUT = Path(__file__).parent / "simulation_output"
OUTPUT_DIR = ROOT_OUTPUT / "blog_5day_ko"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}")


DEFAULT_TIMEOUT = 60.0


def api_call(method: str, url: str, data: Dict | None = None, *, timeout: float | None = DEFAULT_TIMEOUT) -> Dict:
    try:
        kwargs = {"timeout": timeout} if timeout is not None else {}
        if method == "GET":
            r = requests.get(url, **kwargs)
        elif method == "POST":
            r = requests.post(url, json=data, **kwargs)
        elif method == "PUT":
            r = requests.put(url, json=data, **kwargs)
        else:
            raise ValueError(f"Unsupported method: {method}")
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


def _norm_handle(h: str) -> str:
    return (h or "").strip().lower()


def _dm_slug(a: str, b: str) -> str:
    aa, bb = sorted([_norm_handle(a), _norm_handle(b)])
    return f"dm:{aa}:{bb}"


def _parse_host_port(base_url: str) -> tuple[str, int]:
    try:
        without_scheme = base_url.split("://", 1)[1]
        host, port_s = without_scheme.split("/", 1)[0].split(":", 1)
        return host, int(port_s)
    except Exception:
        return "127.0.0.1", 0


def _server_ready(url: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


class _Srv:
    def __init__(self, name: str, server: uvicorn.Server, thread: threading.Thread, host: str, port: int) -> None:
        self.name = name
        self.server = server
        self.thread = thread
        self.host = host
        self.port = port


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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class KoreanGPTPlanner(GPTPlanner):
    def _invoke(self, messages: list[dict[str, str]], model: str):  # type: ignore[override]
        prefixed = [{"role": "system", "content": "모든 응답은 자연스러운 한국어로 작성하세요."}] + list(messages)
        return super()._invoke(prefixed, model)


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
    # Sim Manager
    sh, sp = _parse_host_port(SIM_BASE_URL)
    if force or not _server_ready(f"{SIM_BASE_URL.replace('/api/v1','')}/docs", timeout=1.5):
        log(f"시뮬레이션 매니저 시작: {sh or '127.0.0.1'}:{sp or 8015}…")
        email_gateway = HttpEmailGateway(base_url=EMAIL_BASE_URL)
        chat_gateway = HttpChatGateway(base_url=CHAT_BASE_URL)
        os.environ["VDOS_LOCALE"] = "ko"
        engine = SimulationEngine(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            sim_manager_email=SIM_MANAGER_EMAIL,
            sim_manager_handle=SIM_MANAGER_HANDLE,
            planner=KoreanGPTPlanner(),
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
    log("🧹 전체 초기화 중…")
    api_call("POST", f"{SIM_BASE_URL}/simulation/stop", {})
    resp = api_call("POST", f"{SIM_BASE_URL}/admin/hard-reset", {})
    if not resp:
        api_call("POST", f"{SIM_BASE_URL}/simulation/full-reset", {})
    state = api_call("GET", f"{SIM_BASE_URL}/simulation", {})
    people = api_call("GET", f"{SIM_BASE_URL}/people", {})
    tick = state.get("current_tick", None) if isinstance(state, dict) else None
    log(f"   초기화 상태: tick={tick}, 인원수={len(people) if isinstance(people, list) else '?'}")


def create_team() -> List[Dict[str, Any]]:
    log("🎭 팀 생성 (디자이너, 풀스택 개발자)…")
    specs = [
        {
            "name_hint": "디자이너",
            "prompt": "마케팅/블로그 사이트에 능숙한 UI/UX 디자이너. Figma, 디자인 시스템, 비동기 협업 선호. 한국어로 작성",
            "email": "designer.1@blogsim.dev",
            "handle": "designer",
            "timezone": "Asia/Seoul",
        },
        {
            "name_hint": "풀스택 개발자",
            "prompt": "FastAPI + React 기반의 빠른 프로토타이핑에 능한 풀스택 개발자. 명확한 핸드오프 선호. 한국어로 작성",
            "email": "dev.1@blogsim.dev",
            "handle": "dev",
            "timezone": "Asia/Seoul",
        },
    ]

    people: List[Dict[str, Any]] = []
    for spec in specs:
        log(f"   → POST /personas/generate ({spec['handle']})")
        gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {"prompt": spec["prompt"], "model_hint": MODEL_HINT})
        if not gen or "persona" not in gen:
            continue
        persona = gen["persona"]
        persona.update(
            {
                "is_department_head": False,
                "email_address": spec["email"],
                "chat_handle": spec["handle"],
                "timezone": spec["timezone"],
                "work_hours": "09:00-17:00",
            }
        )
        log(f"   → POST /people ({persona['email_address']})")
        created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
        if created:
            people.append(created)
            log(f"   ✅ {created['name']} ({created['role']})")
    save_json(people, "mobile_team.json")
    return people


def run_sim(people: List[Dict[str, Any]]) -> bool:
    log("🚀 5일 블로그 프로젝트 시뮬레이션 시작…")
    start = {
        "project_name": "클라이언트 블로그 구축",
        "project_summary": "홈/포스트 페이지를 갖춘 단순 블로그 제작. 기본 스타일링과 연락처 링크 포함.",
        "duration_weeks": 1,
        "include_person_ids": [p["id"] for p in people],
        "random_seed": 7,
        "model_hint": MODEL_HINT,
    }
    log("   → POST /simulation/start")
    ok = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start, timeout=240)
    if not ok:
        log("❌ 시뮬레이션 시작 실패")
        return False

    ticks_total = 5 * 8 * 60
    log("   → POST /simulation/advance (ticks=1) [시작]")
    api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": 1, "reason": "kickoff"}, timeout=240)
    log("   → POST /simulation/ticks/start (자동 진행)")
    started = api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/start", {}, timeout=30)
    if not started:
        log("   ! 자동 진행 시작 실패 — 조기 종료")
        state = api_call("GET", f"{SIM_BASE_URL}/simulation")
        save_json(state, "week_1_state.json")
        return False

    deadline = time.time() + 120 * 60
    try:
        while time.time() < deadline:
            state = api_call("GET", f"{SIM_BASE_URL}/simulation", timeout=10) or {}
            cur = int(state.get("current_tick", 0))
            log(f"      tick={cur}/ {ticks_total} sim_time={state.get('sim_time')}")
            if cur >= ticks_total:
                break
            time.sleep(5)
    except KeyboardInterrupt:
        log("   ⚠️ 사용자가 중단 — 산출물 저장 진행…")
    finally:
        api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/stop", {}, timeout=10)

    log("   → GET /simulation")
    state = api_call("GET", f"{SIM_BASE_URL}/simulation")
    save_json(state, "week_1_state.json")
    return True


def collect_emails(people: List[Dict[str, Any]]) -> None:
    log("📥 이메일 수집…")
    addrs = [p.get("email_address") for p in people if p.get("email_address")]
    if SIM_MANAGER_EMAIL not in addrs:
        addrs.append(SIM_MANAGER_EMAIL)
    out: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
    for addr in addrs:
        records = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
        out["mailboxes"][addr] = records
    save_json(out, "all_emails.json")


def collect_chats(people: List[Dict[str, Any]]) -> None:
    log("💬 채팅 수집…")
    handles = [_norm_handle(p.get("chat_handle", "")) for p in people if p.get("chat_handle")]
    if _norm_handle(SIM_MANAGER_HANDLE) not in handles:
        handles.append(_norm_handle(SIM_MANAGER_HANDLE))
    slugs = {_dm_slug(a, b) for a, b in itertools.combinations(handles, 2)}
    out: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "rooms": {}}
    for slug in sorted(slugs):
        records = api_call("GET", f"{CHAT_BASE_URL}/rooms/{slug}/messages")
        if isinstance(records, list) and records:
            out["rooms"][slug] = records
    save_json(out, "all_chats.json")


def generate_reports(people: List[Dict[str, Any]]) -> None:
    log("📊 리포트 생성…")
    final_state = api_call("GET", f"{SIM_BASE_URL}/simulation")
    events = api_call("GET", f"{SIM_BASE_URL}/events")
    tokens = api_call("GET", f"{SIM_BASE_URL}/simulation/token-usage")

    per_person: Dict[str, Any] = {}
    for p in people:
        pid = p["id"]
        daily = api_call("GET", f"{SIM_BASE_URL}/people/{pid}/daily-reports?limit=20")
        hourly = api_call("GET", f"{SIM_BASE_URL}/people/{pid}/plans?plan_type=hourly&limit=50")
        per_person[p["name"]] = {"daily_reports": daily, "hourly_plans": hourly}

    out = {
        "simulation_completed": datetime.now().isoformat(),
        "project": "클라이언트 블로그 구축 (5일)",
        "team": people,
        "final_state": final_state,
        "events": events,
        "token_usage": tokens,
        "reports_by_person": per_person,
        "summary": {
            "total_events": len(events) if isinstance(events, list) else 0,
            "total_team_members": len(people),
            "simulation_duration": f"{final_state.get('current_tick', 0)} ticks",
            "total_tokens": (tokens or {}).get("total_tokens", 0),
        },
    }
    save_json(out, "final_simulation_report.json")


def main() -> None:
    log("한국어 5일 블로그 시뮬레이션 시작…")
    handles: list[_Srv] = []
    team: List[Dict[str, Any]] = []
    try:
        handles = _maybe_start_services(force=True)
        _full_reset()
        team = create_team()
        if len(team) < 2:
            log("❌ 팀 구성 실패")
            return
        try:
            run_ok = run_sim(team)
        except KeyboardInterrupt:
            log("⚠️ 사용자가 중단 — 산출물 저장…")
            run_ok = True
        if not run_ok:
            log("❌ 시뮬레이션 실패")
            return
        collect_emails(team)
        collect_chats(team)
        generate_reports(team)
        # 보조 로그 복사 (사용자 관찰용)
        # 출력은 기존 short_blog_simulation.py와 동일 구조로 저장됨
        log("✅ 한국어 시뮬레이션 완료")
        log(f"📁 Output: {OUTPUT_DIR}")
    finally:
        _stop_services(handles)


if __name__ == "__main__":
    main()
