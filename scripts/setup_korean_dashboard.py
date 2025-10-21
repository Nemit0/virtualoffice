#!/usr/bin/env python3
"""
한국어 VDOS 대시보드 설정 스크립트
===================================

VDOS 대시보드를 한국어 프로젝트용으로 초기화합니다:
1. 모든 데이터베이스 초기화 (전체 리셋)
2. 한국어 페르소나 생성
3. 한국어 프로젝트 설정

사용법:
    python scripts/setup_korean_dashboard.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

# API 엔드포인트 설정
SIM_BASE_URL = "http://127.0.0.1:8015/api/v1"

def log(msg: str) -> None:
    """로그 메시지 출력"""
    print(f"[한국어 설정] {msg}")


def api_call(method: str, url: str, data: dict | None = None, *, timeout: float = 120.0) -> dict | None:
    """API 호출 헬퍼"""
    try:
        if method == "GET":
            r = requests.get(url, timeout=timeout)
        elif method == "POST":
            r = requests.post(url, json=data, timeout=timeout)
        elif method == "PUT":
            r = requests.put(url, json=data, timeout=timeout)
        elif method == "DELETE":
            r = requests.delete(url, timeout=timeout)
        else:
            raise ValueError(f"지원하지 않는 메서드: {method}")

        r.raise_for_status()
        return r.json() if r.content else {}
    except requests.exceptions.RequestException as e:
        log(f"❌ API 오류: {e} ({method} {url})")
        return None


def full_reset() -> bool:
    """전체 데이터베이스 리셋"""
    log("🔄 전체 데이터베이스 리셋 중...")

    # 시뮬레이션 중지
    api_call("POST", f"{SIM_BASE_URL}/simulation/stop")
    api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/stop")
    time.sleep(1)

    # 전체 리셋 실행
    result = api_call("POST", f"{SIM_BASE_URL}/admin/hard-reset")
    if not result:
        log("❌ 데이터베이스 리셋 실패")
        return False

    log("✅ 데이터베이스 리셋 완료")
    time.sleep(2)
    return True


def create_korean_personas() -> list[dict[str, Any]]:
    """한국어 페르소나 생성"""
    log("👥 한국어 페르소나 생성 중...")

    # 한국어 페르소나 스펙
    persona_specs = [
        {
            "prompt": "Agile/Scrum 기반 프로덕트 매니저, 이해관계자 커뮤니케이션 능숙, 한국어",
            "is_head": True,
            "handle": "pm",
            "team_name": "Team A"
        },
        {
            "prompt": "시니어 풀스택 개발자, React/Node.js 전문, 한국어",
            "is_head": False,
            "handle": "dev1",
            "team_name": "Team A"
        },
        {
            "prompt": "프론트엔드 개발자, UI/UX 구현 전문, 한국어",
            "is_head": False,
            "handle": "frontend",
            "team_name": "Team A"
        },
        {
            "prompt": "백엔드 개발자, API/데이터베이스 설계 전문, 한국어",
            "is_head": False,
            "handle": "backend",
            "team_name": "Team B"
        },
        {
            "prompt": "데이터 엔지니어, 데이터 파이프라인/분석 전문, 한국어",
            "is_head": False,
            "handle": "data",
            "team_name": "Team B"
        },
        {
            "prompt": "데보옵스 엔지니어, CI/CD/클라우드 인프라 전문, 한국어",
            "is_head": False,
            "handle": "devops",
            "team_name": "Team B"
        },
    ]

    people: list[dict[str, Any]] = []

    for spec in persona_specs:
        log(f"   → 페르소나 생성 중: {spec['handle']}")

        # GPT로 페르소나 생성
        gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {
            "prompt": spec["prompt"],
            "model_hint": "gpt-4o-mini"
        })

        if not gen or "persona" not in gen:
            log(f"   ⚠️  {spec['handle']} 생성 실패 - 건너뜀")
            continue

        persona = gen["persona"]

        # 스케줄 제거 (시간 형식 문제 방지)
        if isinstance(persona.get("schedule"), list):
            persona.pop("schedule", None)

        # 필수 필드 설정
        persona.update({
            "break_frequency": "50/10 cadence",
            "communication_style": "Async",
            "is_department_head": spec["is_head"],
            "email_address": f"{spec['handle']}@company.kr",
            "chat_handle": spec["handle"],
            "timezone": "Asia/Seoul",
            "work_hours": "09:00-18:00",
            "team_name": spec["team_name"]
        })

        # 페르소나 생성
        created = api_call("POST", f"{SIM_BASE_URL}/people", persona)

        if created:
            people.append(created)
            log(f"   ✅ {created['name']} ({created['role']}) - {spec['team_name']}")
        else:
            log(f"   ❌ {spec['handle']} 생성 실패")

    log(f"✅ {len(people)}명의 페르소나 생성 완료")
    return people


def verify_setup() -> None:
    """설정 확인"""
    log("🔍 설정 확인 중...")

    # 페르소나 목록 확인
    people = api_call("GET", f"{SIM_BASE_URL}/people")
    if people:
        log(f"   페르소나: {len(people)}명")
        for p in people:
            log(f"      - {p['name']} ({p['role']}) - Team: {p.get('team_name', 'None')}")
    else:
        log("   ⚠️  페르소나 없음")

    # 시뮬레이션 상태 확인
    state = api_call("GET", f"{SIM_BASE_URL}/simulation")
    if state:
        log(f"   시뮬레이션 상태: {'실행 중' if state.get('is_running') else '중지됨'}")
        log(f"   현재 틱: {state.get('current_tick', 0)}")

    log("✅ 설정 확인 완료")


def print_summary(people: list[dict[str, Any]]) -> None:
    """설정 요약 출력"""
    print("\n" + "=" * 60)
    print("한국어 VDOS 대시보드 설정 완료!")
    print("=" * 60)
    print(f"\n✅ 생성된 페르소나: {len(people)}명")

    team_a = [p for p in people if p.get('team_name') == 'Team A']
    team_b = [p for p in people if p.get('team_name') == 'Team B']

    print(f"\n📋 Team A ({len(team_a)}명):")
    for p in team_a:
        log(f"   - {p['name']} ({p['role']})")

    print(f"\n📋 Team B ({len(team_b)}명):")
    for p in team_b:
        log(f"   - {p['name']} ({p['role']})")

    print("\n" + "=" * 60)
    print("다음 단계:")
    print("1. 대시보드에서 프로젝트 추가 (Add Project)")
    print("2. 각 팀에 프로젝트 할당")
    print("3. Start Simulation 버튼으로 시뮬레이션 시작")
    print("=" * 60 + "\n")


def main() -> int:
    """메인 함수"""
    log("=" * 60)
    log("한국어 VDOS 대시보드 설정 시작")
    log("=" * 60)

    # 서버 연결 확인
    try:
        state = api_call("GET", f"{SIM_BASE_URL}/simulation")
        if state is None:
            log("❌ VDOS 서버에 연결할 수 없습니다.")
            log("   briefcase dev 명령으로 서버를 먼저 시작하세요.")
            return 1
    except Exception as e:
        log(f"❌ 서버 연결 오류: {e}")
        return 1

    # 1. 전체 리셋
    if not full_reset():
        log("❌ 리셋 실패")
        return 1

    # 2. 한국어 페르소나 생성
    people = create_korean_personas()

    if len(people) < 4:
        log("❌ 최소 4명의 페르소나가 필요합니다")
        return 1

    # 3. 설정 확인
    verify_setup()

    # 4. 요약 출력
    print_summary(people)

    log("✅ 한국어 대시보드 설정 완료!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
