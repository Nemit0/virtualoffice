#!/usr/bin/env python3
"""
Comprehensive 4-Week Mobile Chat App Simulation
==============================================

This script simulates a realistic 4-person virtual office working on developing
a mobile chatting application over 4 weeks, with GPT-generated personas, daily/weekly
reports, email/chat logs, and comprehensive project documentation.

Team Structure:
- Project Manager (Department Head)
- UI/UX Designer
- Full Stack Developer
- DevOps Engineer

Project: "QuickChat" - A barebone mobile chatting application
Duration: 4 weeks
Output: Complete simulation logs, reports, and project documentation
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import requests

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Base URLs for the running servers
EMAIL_BASE_URL = "http://127.0.0.1:8000"
CHAT_BASE_URL = "http://127.0.0.1:8001"
SIM_BASE_URL = "http://127.0.0.1:8015/api/v1"

# Output directory for all simulation results
OUTPUT_DIR = Path(__file__).parent / "simulation_output"

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

    def api_call(self, method: str, url: str, data: Dict = None) -> Dict:
        """Make API call with error handling."""
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
            self.log(f"API Error ({method} {url}): {e}")
            return {}

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
            **self.project_data,
            "include_person_ids": person_ids,
            "random_seed": 42,  # For reproducible events
            "model_hint": "gpt-4o-mini"
        }

        response = self.api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_data)
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

        # Run simulation in chunks to allow for realistic development flow
        ticks_per_day = 8 * 60  # 8 hours * 60 minutes
        ticks_per_week = 5 * ticks_per_day  # 5 working days

        for week in range(total_weeks):
            self.log(f"📅 Week {week + 1}/{total_weeks}")

            for day in range(5):  # 5 working days
                day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][day]
                self.log(f"   Day {day + 1}/5 ({day_name})")

                # Run a full day of simulation
                advance_data = {
                    "ticks": ticks_per_day,
                    "reason": f"Week {week + 1} - {day_name} workday"
                }

                response = self.api_call("POST", f"{SIM_BASE_URL}/simulation/advance", advance_data)
                if response:
                    self.log(f"      ✅ Completed {day_name} ({ticks_per_day} ticks)")

                # Add brief pause to allow system to process
                time.sleep(2)

                # Capture daily state
                self.capture_daily_snapshot(week + 1, day + 1, day_name)

            # Capture weekly summary
            self.capture_weekly_snapshot(week + 1)
            self.log(f"✅ Week {week + 1} completed")

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
        ]

        # Save readable summary
        summary_path = self.output_dir / "PROJECT_SUMMARY.md"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(summary_lines))

        self.log("📋 Generated human-readable project summary: PROJECT_SUMMARY.md")

    def export_communication_logs(self):
        """Export email and chat logs from the communication servers."""
        self.log("📧 Exporting communication logs...")

        try:
            # Export email logs
            email_response = requests.get(f"{EMAIL_BASE_URL}/mailboxes")
            if email_response.status_code == 200:
                emails = email_response.json()
                self.save_json(emails, "email_communications.json")

            # Export chat logs
            chat_response = requests.get(f"{CHAT_BASE_URL}/rooms")
            if chat_response.status_code == 200:
                chats = chat_response.json()
                self.save_json(chats, "chat_communications.json")

        except Exception as e:
            self.log(f"Warning: Could not export communication logs: {e}")

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
    """Main execution function."""
    print("🏢 Mobile Chat App Development - Virtual Office Simulation")
    print("=" * 60)

    simulation = MobileChatSimulation()

    try:
        # Run the complete simulation
        success = asyncio.run(simulation.run_complete_simulation())

        if success:
            print(f"\n✅ Simulation completed! Check '{simulation.output_dir}' for all reports and logs.")
            return 0
        else:
            print(f"\n❌ Simulation failed. Check logs for details.")
            return 1

    except KeyboardInterrupt:
        print(f"\n⏹️  Simulation interrupted by user.")
        return 1
    except Exception as e:
        print(f"\n💥 Simulation failed with error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())