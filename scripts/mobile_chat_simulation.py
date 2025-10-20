#!/usr/bin/env python3
"""
Comprehensive 4-Week Mobile Chat App Simulation (updated)
========================================================

Runs a realistic 4-person team simulation for a mobile chat app with:
- GPT-backed persona generation (model_hint configurable)
- Fast local servers (minute-level ticks; tiny wall-clock intervals)
- Auto-tick loop with polling (avoids per-tick HTTP calls)
- Collection of ALL emails and DMs, plus daily/weekly/final reports

Outputs under `simulation_output/mobile_4week/`.
"""

import asyncio
import itertools
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import socket
import requests
import uvicorn

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from virtualoffice.servers.email import app as email_app
from virtualoffice.servers.chat import app as chat_app
from virtualoffice.sim_manager import create_app as create_sim_app
from virtualoffice.sim_manager.gateways import HttpEmailGateway, HttpChatGateway
from virtualoffice.sim_manager.engine import SimulationEngine

# Base URLs are overridden when we force-start local servers
EMAIL_BASE_URL = os.getenv("VDOS_EMAIL_BASE_URL", "http://127.0.0.1:8000")
CHAT_BASE_URL = os.getenv("VDOS_CHAT_BASE_URL", "http://127.0.0.1:8001")
SIM_BASE_URL = os.getenv("VDOS_SIM_BASE_URL", "http://127.0.0.1:8015/api/v1")

# Output directory
ROOT_OUTPUT = Path(__file__).parent / "simulation_output"
OUTPUT_DIR = ROOT_OUTPUT / "mobile_4week"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

class MobileChatSimulation:
    """Orchestrates the complete mobile chat app development simulation."""

    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(exist_ok=True)
        self.personas = []
        self.project_data = {
            "name": "QuickChat Mobile App",
            "summary": "Develop a barebone mobile chatting application with core messaging features, user authentication, real-time chat, and basic UI/UX. Target completion in 4 weeks with iterative development approach.",
            "duration_weeks": 4
        }

    def log(self, message: str):
        """Log message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    def save_json(self, data: Any, filename: str):
        """Save data as JSON to output directory."""
        filepath = self.output_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.log(f"Saved: {filename}")

    def api_call(self, method: str, url: str, data: Dict = None, *, timeout: float | None = 120.0) -> Dict:
        """Make API call with error handling."""
        try:
            kwargs = {"timeout": timeout} if timeout is not None else {}
            if method.upper() == "GET":
                response = requests.get(url, **kwargs)
            elif method.upper() == "POST":
                response = requests.post(url, json=data, **kwargs)
            elif method.upper() == "PUT":
                response = requests.put(url, json=data, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json() if response.content else {}
        except Exception as e:
            self.log(f"API Error ({method} {url}): {e}")
            return {}

    # -------- Local server bootstrap (email/chat/sim) --------
    class _Srv:
        def __init__(self, name: str, server: uvicorn.Server, thread: threading.Thread, host: str, port: int) -> None:
            self.name = name
            self.server = server
            self.thread = thread
            self.host = host
            self.port = port

    def _norm_handle(self, h: str) -> str:
        return (h or "").strip().lower()

    def _dm_slug(self, a: str, b: str) -> str:
        aa, bb = sorted([self._norm_handle(a), self._norm_handle(b)])
        return f"dm:{aa}:{bb}"

    def _parse_host_port(self, base_url: str) -> tuple[str, int]:
        try:
            without_scheme = base_url.split("://", 1)[1]
            host, port_s = without_scheme.split("/", 1)[0].split(":", 1)
            return host, int(port_s)
        except Exception:
            return "127.0.0.1", 0

    def _start_server(self, name: str, app, host: str, port: int) -> _Srv:
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
        return self._Srv(name, server, t, host, port)

    def _free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _server_ready(self, url: str, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                requests.get(url, timeout=0.5)
                return True
            except Exception:
                time.sleep(0.1)
        return False

    def _maybe_start_services(self, force: bool = False) -> list[_Srv]:
        handles: list[MobileChatSimulation._Srv] = []
        global EMAIL_BASE_URL, CHAT_BASE_URL, SIM_BASE_URL
        if force:
            eport, cport, sport = self._free_port(), self._free_port(), self._free_port()
            EMAIL_BASE_URL = f"http://127.0.0.1:{eport}"
            CHAT_BASE_URL = f"http://127.0.0.1:{cport}"
            SIM_BASE_URL = f"http://127.0.0.1:{sport}/api/v1"
        # Email
        eh, ep = self._parse_host_port(EMAIL_BASE_URL)
        if force or not self._server_ready(f"{EMAIL_BASE_URL}/docs", timeout=1.5):
            self.log(f"Starting Email server on {eh or '127.0.0.1'}:{ep or 8000}…")
            handles.append(self._start_server("email", email_app, eh or "127.0.0.1", ep or 8000))
        # Chat
        ch, cp = self._parse_host_port(CHAT_BASE_URL)
        if force or not self._server_ready(f"{CHAT_BASE_URL}/docs", timeout=1.5):
            self.log(f"Starting Chat server on {ch or '127.0.0.1'}:{cp or 8001}…")
            handles.append(self._start_server("chat", chat_app, ch or "127.0.0.1", cp or 8001))
        # Simulation Manager with fast tick + minute-level day
        sh, sp = self._parse_host_port(SIM_BASE_URL)
        if force or not self._server_ready(f"{SIM_BASE_URL.replace('/api/v1','')}/docs", timeout=1.5):
            self.log(f"Starting Simulation Manager on {sh or '127.0.0.1'}:{sp or 8015}…")
            email_gateway = HttpEmailGateway(base_url=EMAIL_BASE_URL)
            chat_gateway = HttpChatGateway(base_url=CHAT_BASE_URL)
            engine = SimulationEngine(
                email_gateway=email_gateway,
                chat_gateway=chat_gateway,
                sim_manager_email=os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local"),
                sim_manager_handle=os.getenv("VDOS_SIM_HANDLE", "sim-manager"),
                tick_interval_seconds=float(os.getenv("VDOS_TICK_INTERVAL_SECONDS", "0.0002")),
                hours_per_day=480,
            )
            sim = create_sim_app(engine)
            handles.append(self._start_server("sim", sim, sh or "127.0.0.1", sp or 8015))
        return handles

    def _stop_services(self, handles: list[_Srv]) -> None:
        for h in handles:
            try:
                if h.thread.is_alive():
                    h.server.should_exit = True
                    h.thread.join(5)
            except Exception:
                pass

    def _full_reset(self) -> None:
        self.log("🧹 Resetting simulation state (hard-reset)…")
        self.api_call("POST", f"{SIM_BASE_URL}/simulation/stop", {})
        resp = self.api_call("POST", f"{SIM_BASE_URL}/admin/hard-reset", {})
        if not resp:
            self.api_call("POST", f"{SIM_BASE_URL}/simulation/full-reset", {})
        state = self.api_call("GET", f"{SIM_BASE_URL}/simulation", {})
        people = self.api_call("GET", f"{SIM_BASE_URL}/people", {})
        tick = state.get("current_tick", None) if isinstance(state, dict) else None
        self.log(f"   State after reset: tick={tick}, people={len(people) if isinstance(people, list) else '?'}")

    def create_personas(self):
        """Create 4 realistic personas for the mobile chat app project."""
        self.log("🎭 Creating 4 realistic personas for mobile chat app development...")

        # Define the team with realistic prompts
        team_prompts = [
            {
                "prompt": "Experienced project manager for mobile app development with Agile/Scrum expertise, stakeholder communication skills, and technical background in mobile platforms",
                "is_department_head": True,
                "base_info": {
                    "timezone": "America/New_York",
                    "work_hours": "09:00-18:00",
                    "communication_style": "Direct and organized",
                    "email_domain": "@quickchat.dev"
                }
            },
            {
                "prompt": "Creative UI/UX designer specializing in mobile app interfaces, user experience optimization, and modern design systems with strong collaboration skills",
                "is_department_head": False,
                "base_info": {
                    "timezone": "America/Los_Angeles",
                    "work_hours": "10:00-19:00",
                    "communication_style": "Visual and collaborative",
                    "email_domain": "@quickchat.dev"
                }
            },
            {
                "prompt": "Senior full stack developer experienced in React Native, Node.js, real-time messaging systems, and mobile app architecture",
                "is_department_head": False,
                "base_info": {
                    "timezone": "Europe/London",
                    "work_hours": "08:00-17:00",
                    "communication_style": "Technical and precise",
                    "email_domain": "@quickchat.dev"
                }
            },
            {
                "prompt": "DevOps engineer skilled in mobile app deployment, CI/CD pipelines, cloud infrastructure, and monitoring systems for mobile applications",
                "is_department_head": False,
                "base_info": {
                    "timezone": "Asia/Tokyo",
                    "work_hours": "09:00-18:00",
                    "communication_style": "Systematic and proactive",
                    "email_domain": "@quickchat.dev"
                }
            }
        ]

        created_personas = []

        for i, team_member in enumerate(team_prompts):
            self.log(f"   Generating persona {i+1}/4 with GPT...")

            # Generate persona with GPT
            persona_response = self.api_call("POST", f"{SIM_BASE_URL}/personas/generate", {
                "prompt": team_member["prompt"]
            })

            if persona_response and "persona" in persona_response:
                persona = persona_response["persona"]
                # Drop schedules that may use non HH:MM formats (optional on server side)
                if isinstance(persona.get("schedule"), list):
                    persona.pop("schedule", None)
                # Default required text fields if missing
                persona.setdefault("break_frequency", "50/10 cadence")
                persona.setdefault("communication_style", "Async")

                # Enhance with our specific project details
                persona.update({
                    "timezone": team_member["base_info"]["timezone"],
                    "work_hours": team_member["base_info"]["work_hours"],
                    "communication_style": team_member["base_info"]["communication_style"],
                    "is_department_head": team_member["is_department_head"],
                    "email_address": f"{persona['name'].lower().replace(' ', '.')}{team_member['base_info']['email_domain']}",
                    "chat_handle": f"@{persona['name'].lower().replace(' ', '_')}"
                })

                # Add mobile app specific objectives and metrics
                if team_member["is_department_head"]:  # PM
                    persona.update({
                        "objectives": [
                            "Deliver QuickChat MVP within 4 weeks",
                            "Ensure cross-team coordination and blockers resolution",
                            "Maintain project scope and timeline adherence",
                            "Facilitate daily standups and sprint planning"
                        ],
                        "metrics": [
                            "Sprint velocity and burn-down tracking",
                            "Stakeholder satisfaction score",
                            "Team blockers resolution time"
                        ]
                    })
                elif "designer" in persona.get("role", "").lower():  # Designer
                    persona.update({
                        "objectives": [
                            "Create intuitive mobile UI/UX for chat interface",
                            "Develop consistent design system and components",
                            "Ensure accessibility and usability standards",
                            "Collaborate with developers on implementation"
                        ],
                        "metrics": [
                            "Design review feedback score",
                            "UI component reusability rate",
                            "User testing satisfaction"
                        ]
                    })
                elif "developer" in persona.get("role", "").lower():  # Developer
                    persona.update({
                        "objectives": [
                            "Implement core messaging functionality",
                            "Build real-time chat features with WebSocket",
                            "Ensure code quality and testing coverage",
                            "Optimize app performance and responsiveness"
                        ],
                        "metrics": [
                            "Code coverage percentage",
                            "API response time benchmarks",
                            "Feature completion velocity"
                        ]
                    })
                else:  # DevOps
                    persona.update({
                        "objectives": [
                            "Set up CI/CD pipeline for mobile app deployment",
                            "Configure cloud infrastructure and monitoring",
                            "Ensure security and performance optimization",
                            "Automate testing and deployment processes"
                        ],
                        "metrics": [
                            "Deployment success rate",
                            "Infrastructure uptime percentage",
                            "Build and deployment time optimization"
                        ]
                    })

                # Create the persona in the system
                created_persona = self.api_call("POST", f"{SIM_BASE_URL}/people", persona)
                if created_persona:
                    created_personas.append(created_persona)
                    self.log(f"   ✅ Created: {persona['name']} ({persona['role']})")

        self.personas = created_personas
        self.save_json(self.personas, "team_personas.json")
        return len(created_personas) == 4

    def start_project_simulation(self):
        """Start the 4-week mobile chat app project simulation."""
        self.log("🚀 Starting QuickChat mobile app project simulation...")

        # Get persona IDs for the simulation
        person_ids = [p["id"] for p in self.personas]

        # Start simulation with our project
        start_data = {
            "project_name": self.project_data.get("name", "QuickChat Mobile App"),
            "project_summary": self.project_data.get("summary", "Mobile chat MVP"),
            "duration_weeks": int(self.project_data.get("duration_weeks", 4)),
            "include_person_ids": person_ids,
            "random_seed": 42,  # For reproducible events
            "model_hint": os.getenv("VDOS_SIM_MODEL_HINT", "gpt-4.1-nano"),
        }

        response = self.api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_data, timeout=240)
        if response:
            self.log("✅ Project simulation started successfully")
            return True
        return False

    def run_simulation_ticks(self, total_weeks: int = 4):
        """Run the simulation for the specified number of weeks with realistic pacing."""
        self.log(f"⏰ Running {total_weeks}-week simulation with realistic pacing...")

        # Calculate total ticks (4 weeks * 5 days * 8 hours * 60 minutes)
        total_ticks = total_weeks * 5 * 8 * 60
        self.log(f"   Total simulation time: {total_ticks} ticks ({total_weeks} weeks)")

        # Auto-tick for speed: start + poll
        ticks_per_day = 8 * 60
        ticks_per_week = 5 * ticks_per_day
        self.log("   → POST /simulation/advance (ticks=1) [kickoff]")
        self.api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": 1, "reason": "kickoff"}, timeout=240)
        self.log("   → POST /simulation/ticks/start (auto)")
        started = self.api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/start", {}, timeout=30)
        if not started:
            self.log("   ! Failed to start auto-ticks; aborting run")
            return
        deadline = time.time() + 90 * 60  # 90 minutes safety cap
        for week in range(total_weeks):
            self.log(f"📅 Week {week + 1}/{total_weeks}")
            for day in range(5):
                day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][day]
                target_tick = (week * ticks_per_week) + ((day + 1) * ticks_per_day)
                while time.time() < deadline:
                    st = self.api_call("GET", f"{SIM_BASE_URL}/simulation", timeout=10) or {}
                    cur = int(st.get("current_tick", 0))
                    self.log(f"      tick={cur}/{(week+1)*ticks_per_week} sim_time={st.get('sim_time')}")
                    if cur >= target_tick:
                        break
                    time.sleep(5)
                # Snapshot end of day
                self.capture_daily_snapshot(week + 1, day + 1, day_name)
            # Weekly snapshot
            self.capture_weekly_snapshot(week + 1)
        self.api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/stop", {}, timeout=10)

    def capture_daily_snapshot(self, week: int, day: int, day_name: str):
        """Capture daily simulation state and reports."""
        # Get current simulation state
        sim_state = self.api_call("GET", f"{SIM_BASE_URL}/simulation")

        # Get daily reports for each person
        daily_reports = {}
        for persona in self.personas:
            reports = self.api_call("GET", f"{SIM_BASE_URL}/people/{persona['id']}/daily-reports?limit=1")
            if reports:
                daily_reports[persona['name']] = reports[0] if reports else None

        # Save daily snapshot
        daily_data = {
            "week": week,
            "day": day,
            "day_name": day_name,
            "simulation_state": sim_state,
            "daily_reports": daily_reports,
            "timestamp": datetime.now().isoformat()
        }

        filename = f"daily_snapshot_week{week}_day{day}_{day_name.lower()}.json"
        self.save_json(daily_data, filename)

    def capture_weekly_snapshot(self, week: int):
        """Capture weekly summary and reports."""
        # Get recent events
        events = self.api_call("GET", f"{SIM_BASE_URL}/events")

        # Get token usage
        token_usage = self.api_call("GET", f"{SIM_BASE_URL}/simulation/token-usage")

        # Get planner metrics
        metrics = self.api_call("GET", f"{SIM_BASE_URL}/metrics/planner?limit=100")

        weekly_data = {
            "week": week,
            "events": events[-50:] if events else [],  # Last 50 events
            "token_usage": token_usage,
            "planner_metrics": metrics[-20:] if metrics else [],  # Last 20 metrics
            "timestamp": datetime.now().isoformat()
        }

        filename = f"weekly_summary_week{week}.json"
        self.save_json(weekly_data, filename)

    def generate_final_reports(self):
        """Generate comprehensive final project reports."""
        self.log("📊 Generating comprehensive final project reports...")

        # Get project plan
        project_plan = self.api_call("GET", f"{SIM_BASE_URL}/simulation/project-plan")

        # Get all simulation reports
        sim_reports = self.api_call("GET", f"{SIM_BASE_URL}/simulation/reports")

        # Get final simulation state
        final_state = self.api_call("GET", f"{SIM_BASE_URL}/simulation")

        # Get all events
        all_events = self.api_call("GET", f"{SIM_BASE_URL}/events")

        # Get final token usage
        final_tokens = self.api_call("GET", f"{SIM_BASE_URL}/simulation/token-usage")

        # Get all daily reports for each person
        all_daily_reports = {}
        all_hourly_plans = {}

        for persona in self.personas:
            # Get all daily reports
            daily_reports = self.api_call("GET", f"{SIM_BASE_URL}/people/{persona['id']}/daily-reports?limit=100")
            all_daily_reports[persona['name']] = daily_reports

            # Get all hourly plans
            hourly_plans = self.api_call("GET", f"{SIM_BASE_URL}/people/{persona['id']}/plans?plan_type=hourly&limit=200")
            all_hourly_plans[persona['name']] = hourly_plans

        # Compile final report
        final_report = {
            "project_info": self.project_data,
            "team": self.personas,
            "project_plan": project_plan,
            "simulation_reports": sim_reports,
            "final_simulation_state": final_state,
            "all_events": all_events,
            "token_usage_summary": final_tokens,
            "daily_reports_by_person": all_daily_reports,
            "hourly_plans_by_person": all_hourly_plans,
            "simulation_completed": datetime.now().isoformat(),
            "total_duration": "4 weeks",
            "summary": {
                "total_events": len(all_events) if all_events else 0,
                "total_daily_reports": sum(len(reports) for reports in all_daily_reports.values()),
                "total_hourly_plans": sum(len(plans) for plans in all_hourly_plans.values()),
                "total_tokens_used": final_tokens.get("total", 0) if final_tokens else 0
            }
        }

        self.save_json(final_report, "final_project_report.json")

        # Generate human-readable summary
        self.generate_readable_summary(final_report)

    def generate_readable_summary(self, final_report: Dict):
        """Generate a human-readable project summary."""
        summary_lines = [
            "# QuickChat Mobile App - 4-Week Development Simulation Report",
            "=" * 60,
            "",
            f"**Project:** {self.project_data['name']}",
            f"**Duration:** {self.project_data['duration_weeks']} weeks",
            f"**Completed:** {final_report['simulation_completed']}",
            "",
            "## Team Members",
            "-" * 20
        ]

        for persona in self.personas:
            role_marker = " (Team Lead)" if persona.get("is_department_head") else ""
            summary_lines.extend([
                f"- **{persona['name']}** - {persona['role']}{role_marker}",
                f"  - Timezone: {persona['timezone']}",
                f"  - Email: {persona['email_address']}",
                f"  - Work Hours: {persona['work_hours']}",
                ""
            ])

        summary_lines.extend([
            "## Project Statistics",
            "-" * 20,
            f"- **Total Events Generated:** {final_report['summary']['total_events']}",
            f"- **Daily Reports Created:** {final_report['summary']['total_daily_reports']}",
            f"- **Hourly Plans Generated:** {final_report['summary']['total_hourly_plans']}",
            f"- **Total AI Tokens Used:** {final_report['summary']['total_tokens_used']:,}",
            "",
            "## Project Timeline",
            "-" * 20,
            "The simulation covered a complete 4-week development cycle with:",
            "- Daily standup meetings and planning sessions",
            "- Regular design reviews and implementation discussions",
            "- DevOps setup and deployment planning",
            "- Random project events and realistic team interactions",
            "",
            "## Outputs Generated",
            "-" * 20,
            "1. **Team Personas** - Detailed AI-generated team member profiles",
            "2. **Daily Snapshots** - Complete daily simulation states and reports",
            "3. **Weekly Summaries** - Weekly progress and metrics tracking",
            "4. **Communication Logs** - All team emails and chat interactions",
            "5. **Final Project Report** - Comprehensive simulation analysis",
            "",
            "This simulation demonstrates the VDOS system's capability to model realistic",
            "software development workflows with AI-driven team interactions, proper",
            "project management, and comprehensive reporting and analytics.",
            "",
            f"Generated by VDOS (Virtual Department Operations Simulator) on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ])

        # Save readable summary
        summary_path = self.output_dir / "PROJECT_SUMMARY.md"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(summary_lines))

        self.log("📋 Generated human-readable project summary: PROJECT_SUMMARY.md")

    def export_communication_logs(self):
        """Export email and chat logs from the communication servers."""
        self.log("📧 Exporting communication logs...")
        # Emails by mailbox
        addrs = [p.get("email_address") for p in self.personas if p.get("email_address")]
        sim_email = os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local")
        if sim_email not in addrs:
            addrs.append(sim_email)
        emails_out: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "mailboxes": {}}
        for addr in addrs:
            recs = self.api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails") or []
            emails_out["mailboxes"][addr] = recs
        self.save_json(emails_out, "email_communications.json")
        # Chats by DM slug
        handles = [(p.get("chat_handle") or "").strip().lower() for p in self.personas if p.get("chat_handle")]
        sim_handle = os.getenv("VDOS_SIM_HANDLE", "sim-manager").lower()
        if sim_handle not in handles:
            handles.append(sim_handle)
        rooms = {self._dm_slug(a, b) for a, b in itertools.combinations(handles, 2)}
        chats_out: Dict[str, Any] = {"collected_at": datetime.now().isoformat(), "rooms": {}}
        for slug in sorted(rooms):
            recs = self.api_call("GET", f"{CHAT_BASE_URL}/rooms/{slug}/messages")
            if isinstance(recs, list) and recs:
                chats_out["rooms"][slug] = recs
        self.save_json(chats_out, "chat_communications.json")

    async def run_complete_simulation(self):
        """Run the complete mobile chat app development simulation."""
        start_time = datetime.now()
        self.log("🎬 Starting Complete Mobile Chat App Development Simulation")
        self.log("=" * 70)

        # Step 1: Create personas
        if not self.create_personas():
            self.log("❌ Failed to create personas. Aborting simulation.")
            return False

        self.log(f"✅ Created {len(self.personas)} team members")

        # Step 2: Start project
        if not self.start_project_simulation():
            self.log("❌ Failed to start project simulation. Aborting.")
            return False

        # Step 3: Run simulation
        self.run_simulation_ticks(4)  # 4 weeks

        # Step 4: Generate reports
        self.generate_final_reports()

        # Step 5: Export communication logs
        self.export_communication_logs()

        # Final summary
        end_time = datetime.now()
        duration = end_time - start_time

        self.log("=" * 70)
        self.log("🎉 SIMULATION COMPLETED SUCCESSFULLY!")
        self.log(f"⏱️  Total Execution Time: {duration}")
        self.log(f"📁 All outputs saved to: {self.output_dir.absolute()}")
        self.log(f"👥 Team Size: {len(self.personas)} members")
        self.log(f"📅 Project Duration: 4 weeks (simulated)")
        self.log("📊 Reports Generated:")

        # List all generated files
        output_files = list(self.output_dir.glob("*"))
        for file in sorted(output_files):
            self.log(f"   - {file.name}")

        return True

def main():
    print("🏢 Mobile Chat App Development - Virtual Office Simulation")
    print("=" * 60)
    simulation = MobileChatSimulation()
    handles: list[MobileChatSimulation._Srv] = []
    try:
        # Force-start local services with fast tick config
        handles = simulation._maybe_start_services(force=True)
        simulation._full_reset()
        # Create personas
        if not simulation.create_personas():
            simulation.log("❌ Failed to create personas. Aborting simulation.")
            return 1
        # Start + run
        if not simulation.start_project_simulation():
            simulation.log("❌ Failed to start project simulation. Aborting.")
            return 1
        # Allow weeks override via env for quicker local runs
        weeks = int(os.getenv("MOBILE_SIM_WEEKS", str(simulation.project_data.get("duration_weeks", 4))))
        simulation.run_simulation_ticks(weeks)
        # Reports + logs
        simulation.generate_final_reports()
        simulation.export_communication_logs()
        simulation.log(f"✅ Simulation complete. Output: {OUTPUT_DIR}")
        return 0
    except KeyboardInterrupt:
        simulation.log("⏹️  Simulation interrupted by user — saving what we have…")
        try:
            simulation.export_communication_logs()
        except Exception:
            pass
        return 1
    except Exception as e:
        simulation.log(f"💥 Simulation failed with error: {e}")
        return 1
    finally:
        simulation._stop_services(handles)

if __name__ == "__main__":
    sys.exit(main())
