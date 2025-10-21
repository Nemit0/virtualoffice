#!/usr/bin/env python3
"""
1주 다중 프로젝트 시뮬레이션 (한국어) - 토큰 최적화 테스트
=====================================

1주 기간 동안 3개의 겹치는 프로젝트를 시뮬레이션:
- 프로젝트 A: 1-3일 (모바일 앱 MVP)
- 프로젝트 B: 2-4일 (웹 대시보드)
- 프로젝트 C: 3-5일 (API 통합)

목적: 토큰 길이 에러 (163K) 수정 검증
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

MODEL_HINT = os.getenv("VDOS_SIM_MODEL_HINT", "gpt-4o-mini")
TICK_INTERVAL_SECONDS = float(os.getenv("VDOS_TICK_INTERVAL_SECONDS", "0.0001"))

ROOT_OUTPUT = Path(__file__).parent / "simulation_output"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = ROOT_OUTPUT / f"test_1week_ko_{TIMESTAMP}"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


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
    # First, try to stop any running simulation
    api_call("POST", f"{SIM_BASE_URL}/simulation/stop", {})
    # Try hard reset endpoint
    r = api_call("POST", f"{SIM_BASE_URL}/admin/hard-reset", {})
    if not r:
        api_call("POST", f"{SIM_BASE_URL}/simulation/full-reset", {})
    # Give the database a moment to finish any cleanup
    time.sleep(1)
    st = api_call("GET", f"{SIM_BASE_URL}/simulation", {})
    ppl = api_call("GET", f"{SIM_BASE_URL}/people", {})
    tick = st.get("current_tick", None) if isinstance(st, dict) else None
    log(f"   상태: tick={tick}, 인원수={len(ppl) if isinstance(ppl, list) else '?'}")


def create_team() -> List[Dict[str, Any]]:
    log("🎭 팀 생성 (PM, 디자이너, 개발자, 데보옵스)…")
    specs = [
        {"prompt": "Agile/Scrum 기반 다중 프로젝트 관리 PM, 이해관계자 커뮤니케이션 능숙, 한국어", "is_head": True, "tz": "Asia/Seoul", "handle": "pm"},
        {"prompt": "모바일/웹 UI/UX 디자이너, 디자인 시스템/협업 능숙, 한국어", "is_head": False, "tz": "Asia/Seoul", "handle": "designer"},
        {"prompt": "React Native/React/Node 풀스택 개발자, API 통합 경험, 한국어", "is_head": False, "tz": "Asia/Seoul", "handle": "dev"},
        {"prompt": "클라우드 인프라/CI/CD/모니터링 데보옵스 엔지니어, 한국어", "is_head": False, "tz": "Asia/Seoul", "handle": "devops"},
    ]
    people: List[Dict[str, Any]] = []
    existing_names = set()
    for i, s in enumerate(specs):
        created = None
        for attempt in range(5):  # Retry up to 5 times for duplicate names
            log(f"   → POST /personas/generate ({s['handle']}) [attempt {attempt+1}]")
            gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {"prompt": s["prompt"], "model_hint": MODEL_HINT}, timeout=120)
            if not gen or "persona" not in gen:
                continue
            persona = gen["persona"]
            # Defensive normalization
            if isinstance(persona.get("schedule"), list):
                persona.pop("schedule", None)
            persona.setdefault("break_frequency", "50/10 cadence")
            persona.setdefault("communication_style", "Async")
            persona.update({
                "is_department_head": bool(s["is_head"]),
                "email_address": f"{s['handle']}.1@multiproject.dev",
                "chat_handle": s["handle"],
                "timezone": s["tz"],
                "work_hours": "09:00-18:00",
            })
            log(f"   → POST /people ({persona['email_address']})")
            created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
            # Check if created successfully (must have 'id' field)
            if created and 'id' in created:
                people.append(created)
                existing_names.add(created['name'])
                log(f"   ✅ {created['name']} ({created['role']})")
                break
            else:
                log(f"   ⚠️ Duplicate name detected, retrying...")
        if not created or 'id' not in created:
            log(f"   ❌ Failed to create persona for {s['handle']} after 5 attempts")
    save_json(people, "team_personas.json")
    return people


def run_1week_sim(people: List[Dict[str, Any]]) -> tuple[bool, Dict[str, Any]]:
    log("🚀 1주 다중 프로젝트 시뮬레이션 시작 (5일, 3개 프로젝트)…")

    test_metrics = {
        "token_errors": [],
        "daily_report_failures": [],
        "email_thread_issues": [],
        "api_errors": [],
        "start_time": datetime.now().isoformat(),
    }

    # Define 3 overlapping projects (scaled down to 1 week)
    projects = [
        {
            "project_name": "모바일 앱 MVP",
            "project_summary": "핵심 메시징, 인증, 실시간 채팅 기능을 갖춘 모바일 채팅 앱 MVP 개발",
            "start_week": 1,
            "duration_weeks": 1,
            "assigned_person_ids": [p["id"] for p in people],  # All team members
        },
        {
            "project_name": "웹 대시보드",
            "project_summary": "관리자용 웹 대시보드 - 사용자 관리, 통계, 모니터링 기능",
            "start_week": 1,
            "duration_weeks": 1,
            "assigned_person_ids": None,  # All team members (default)
        },
        {
            "project_name": "API 통합",
            "project_summary": "외부 서비스 API 통합 - 결제, 알림, 분석 시스템",
            "start_week": 1,
            "duration_weeks": 1,
            "assigned_person_ids": None,  # All team members (default)
        },
    ]

    start_request = {
        "project_name": "통합 플랫폼 개발",  # Overall project name
        "project_summary": "모바일 앱, 웹 대시보드, API 통합을 포함한 통합 플랫폼 개발",
        "duration_weeks": 1,  # 1 week
        "total_duration_weeks": 1,
        "projects": projects,
        "include_person_ids": [p["id"] for p in people],
        "random_seed": 42,
        "model_hint": MODEL_HINT,
    }

    # Synchronous initialization with built-in retry logic (3 attempts with exponential backoff)
    log("   → POST /simulation/start (with 3 retry attempts)…")
    ok = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_request, timeout=300)
    if not ok:
        log("❌ 시뮬레이션 시작 실패 (3회 재시도 후)")
        test_metrics["api_errors"].append({
            "operation": "start",
            "error": "Failed after 3 retries",
            "timestamp": datetime.now().isoformat(),
        })
        return False, test_metrics
    log("✅ 초기화 완료")

    # 1 week * 5 days * 8 hours * 60 minutes = 2400 ticks
    ticks_total = 1 * 5 * 8 * 60
    log(f"   Total ticks to simulate: {ticks_total}")

    # Kickoff
    api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": 1, "reason": "kickoff"}, timeout=300)
    remaining = ticks_total - 1
    progressed = 1
    step = 60
    day_ticks = 480  # 8 hours * 60 minutes

    while remaining > 0:
        chunk = step if remaining >= step else remaining
        current_day = (progressed // day_ticks) + 1
        log(f"   → Advancing {chunk} ticks; progressed={progressed}/{ticks_total} (Day {current_day})")

        ok = False
        attempt = 0
        while attempt < 3 and not ok:
            attempt += 1
            res = api_call(
                "POST",
                f"{SIM_BASE_URL}/simulation/advance",
                {"ticks": chunk, "reason": "auto"},
                timeout=600,
            )
            if res:
                ok = True
                # Check for token errors in response
                if isinstance(res, dict):
                    if "error" in res and "token" in str(res["error"]).lower():
                        test_metrics["token_errors"].append({
                            "tick": progressed,
                            "error": res["error"],
                            "timestamp": datetime.now().isoformat(),
                        })
                        log(f"   ⚠️ TOKEN ERROR at tick {progressed}: {res['error']}")
                break
            else:
                log(f"   ! advance 실패 (시도 {attempt}/3)")
                time.sleep(5)

        if not ok:
            err = {
                "at_progress": progressed,
                "attempted_ticks": chunk,
                "error": "advance timeout/failure",
                "timestamp": datetime.now().isoformat(),
            }
            test_metrics["api_errors"].append(err)
            save_json(test_metrics, "test_metrics.json")
            step = max(30, step // 2)
            continue

        remaining -= chunk
        progressed += chunk

        # Check for daily report generation at end of each day
        if progressed % day_ticks == 0:
            day = progressed // day_ticks
            log(f"   📊 Checking Day {day} report generation...")
            st = api_call("GET", f"{SIM_BASE_URL}/simulation")
            if st and "daily_reports" in st:
                reports = st.get("daily_reports", [])
                log(f"      Daily reports generated: {len(reports)}")

        time.sleep(0.02)

    test_metrics["end_time"] = datetime.now().isoformat()
    test_metrics["total_ticks"] = progressed
    save_json(test_metrics, "test_metrics.json")

    return True, test_metrics


def collect_logs(people: List[Dict[str, Any]]) -> Dict[str, Any]:
    log("📥 이메일/채팅 로그 수집…")
    addrs = [p.get("email_address") for p in people if p.get("email_address")]
    sim_email = os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local")
    if sim_email not in addrs:
        addrs.append(sim_email)

    emails: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
    total_emails = 0
    threaded_emails = 0

    for addr in addrs:
        recs = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
        emails["mailboxes"][addr] = recs
        total_emails += len(recs)
        threaded_emails += sum(1 for e in recs if e.get("thread_id"))

    save_json(emails, "email_communications.json")
    log(f"   Total emails: {total_emails}, Threaded: {threaded_emails}")

    # Collect chat logs
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
    total_messages = 0

    for slug in sorted(rooms):
        recs = api_call("GET", f"{CHAT_BASE_URL}/rooms/{slug}/messages")
        if isinstance(recs, list) and recs:
            chats["rooms"][slug] = recs
            total_messages += len(recs)

    save_json(chats, "chat_communications.json")
    log(f"   Total chat messages: {total_messages}")

    return {
        "total_emails": total_emails,
        "threaded_emails": threaded_emails,
        "total_chat_messages": total_messages,
    }


def generate_report(team: List[Dict[str, Any]], test_metrics: Dict[str, Any], comm_stats: Dict[str, Any]) -> str:
    report_lines = [
        "=" * 60,
        "SIMULATION EXECUTION REPORT - 1 WEEK KOREAN MULTI-PROJECT TEST",
        "=" * 60,
        "",
        f"Status: {'SUCCESS' if not test_metrics['token_errors'] and not test_metrics['api_errors'] else 'FAILED'}",
        f"Start Time: {test_metrics.get('start_time', 'N/A')}",
        f"End Time: {test_metrics.get('end_time', 'N/A')}",
        f"Ticks Completed: {test_metrics.get('total_ticks', 0)} / 2400",
        f"Workers Active: {len(team)}",
        "",
        "COMMUNICATION STATS:",
        f"- Emails Sent: {comm_stats.get('total_emails', 0)}",
        f"- Threaded Emails: {comm_stats.get('threaded_emails', 0)}",
        f"- Chat Messages: {comm_stats.get('total_chat_messages', 0)}",
        "",
        "TOKEN OPTIMIZATION TEST RESULTS:",
        f"- Token Length Errors: {len(test_metrics.get('token_errors', []))}",
        f"- Daily Report Failures: {len(test_metrics.get('daily_report_failures', []))}",
        f"- API Errors: {len(test_metrics.get('api_errors', []))}",
        "",
    ]

    if test_metrics.get("token_errors"):
        report_lines.append("TOKEN ERRORS DETECTED:")
        for err in test_metrics["token_errors"]:
            report_lines.append(f"  - Tick {err['tick']}: {err['error']}")
        report_lines.append("")

    if test_metrics.get("api_errors"):
        report_lines.append("API ERRORS:")
        for err in test_metrics["api_errors"]:
            report_lines.append(f"  - {err['operation']}: {err['error']}")
        report_lines.append("")

    report_lines.extend([
        "ARTIFACTS:",
        f"- Output Directory: {OUTPUT_DIR}",
        f"- Test Metrics: {OUTPUT_DIR / 'test_metrics.json'}",
        f"- Team Personas: {OUTPUT_DIR / 'team_personas.json'}",
        f"- Email Logs: {OUTPUT_DIR / 'email_communications.json'}",
        f"- Chat Logs: {OUTPUT_DIR / 'chat_communications.json'}",
        f"- Final State: {OUTPUT_DIR / 'final_state.json'}",
        "",
        "NEXT STEPS:",
        "- Review test_metrics.json for detailed token error analysis",
        "- Verify daily reports used hourly summaries (not minute_schedule)",
        "- Check email threading consistency",
        "- Ready for evaluation by simulation-evaluation agent",
        "",
        "=" * 60,
    ])

    return "\n".join(report_lines)


def main() -> int:
    log("한국어 1주 다중 프로젝트 시뮬레이션 시작 (토큰 최적화 테스트)…")
    handles: list[_Srv] = []
    team: List[Dict[str, Any]] = []
    test_metrics: Dict[str, Any] = {}
    comm_stats: Dict[str, Any] = {}

    try:
        handles = _maybe_start_services(force=True)
        _full_reset()
        team = create_team()
        if len(team) < 4:
            log("❌ 팀 생성 실패")
            return 1

        success, test_metrics = run_1week_sim(team)
        if not success:
            log("❌ 시뮬레이션 실패")
            return 1

        comm_stats = collect_logs(team)

        # Final state/reports
        st = api_call("GET", f"{SIM_BASE_URL}/simulation")
        save_json(st, "final_state.json")

        # Generate and save report
        report = generate_report(team, test_metrics, comm_stats)
        report_path = OUTPUT_DIR / "EXECUTION_REPORT.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        print("\n" + report)
        log(f"✅ 완료. 출력: {OUTPUT_DIR}")

        # Return error code if token errors detected
        if test_metrics.get("token_errors"):
            log("⚠️ TOKEN ERRORS DETECTED - Test FAILED")
            return 1

        return 0
    finally:
        _stop_services(handles)


if __name__ == "__main__":
    sys.exit(main())
