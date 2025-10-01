#!/usr/bin/env python3
"""
Quick Mobile Chat App Simulation
===============================

A streamlined version that creates realistic personas and runs a simulation.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
import requests

# Base URLs for the running servers
SIM_BASE_URL = "http://127.0.0.1:8015/api/v1"

# Output directory
OUTPUT_DIR = Path(__file__).parent / "simulation_output"
OUTPUT_DIR.mkdir(exist_ok=True)

def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def api_call(method, url, data=None):
    try:
        if method.upper() == "GET":
            response = requests.get(url)
        elif method.upper() == "POST":
            response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json() if response.content else {}
    except Exception as e:
        log(f"API Error: {e}")
        return {}

def save_json(data, filename):
    filepath = OUTPUT_DIR / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Saved: {filename}")

def create_mobile_team():
    """Create 4-person mobile development team."""
    log("🎭 Creating mobile development team...")

    team_specs = [
        {
            "prompt": "Experienced agile project manager for mobile app development with strong communication and leadership skills",
            "role_title": "Project Manager",
            "is_head": True
        },
        {
            "prompt": "Creative UI/UX designer specializing in mobile app interfaces and user experience design",
            "role_title": "UI/UX Designer",
            "is_head": False
        },
        {
            "prompt": "Senior full stack developer with React Native and Node.js expertise for mobile applications",
            "role_title": "Full Stack Developer",
            "is_head": False
        },
        {
            "prompt": "DevOps engineer experienced in mobile app deployment, CI/CD, and cloud infrastructure",
            "role_title": "DevOps Engineer",
            "is_head": False
        }
    ]

    created_personas = []

    for i, spec in enumerate(team_specs):
        log(f"   Creating {spec['role_title']}...")

        # Generate with GPT
        persona_response = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {
            "prompt": spec["prompt"]
        })

        if persona_response and "persona" in persona_response:
            persona = persona_response["persona"]

            # Enhance with project-specific details
            persona.update({
                "is_department_head": spec["is_head"],
                "email_address": f"{persona['name'].lower().replace(' ', '.')}.{i+1}@quickchat.dev",
                "chat_handle": f"@{persona['name'].lower().replace(' ', '_')}",
                "timezone": ["America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"][i],
                "work_hours": "09:00-18:00"
            })

            # Create persona in system
            created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
            if created:
                created_personas.append(created)
                log(f"   ✅ Created: {persona['name']} ({spec['role_title']})")

    save_json(created_personas, "mobile_team.json")
    return created_personas

def run_simulation(personas, weeks=4):
    """Run the mobile chat app simulation."""
    log(f"🚀 Starting {weeks}-week QuickChat mobile app simulation...")

    # Start simulation
    start_data = {
        "project_name": "QuickChat Mobile App",
        "project_summary": "Develop a barebone mobile chatting application with core messaging features, user authentication, real-time chat, and basic UI/UX. Target completion in 4 weeks with iterative development.",
        "duration_weeks": weeks,
        "include_person_ids": [p["id"] for p in personas],
        "random_seed": 42
    }

    start_response = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_data)
    if not start_response:
        log("❌ Failed to start simulation")
        return False

    log("✅ Simulation started")

    # Run simulation in weekly chunks
    ticks_per_week = 5 * 8 * 60  # 5 days * 8 hours * 60 minutes

    for week in range(weeks):
        log(f"📅 Running Week {week + 1}/{weeks}...")

        advance_data = {
            "ticks": ticks_per_week,
            "reason": f"Week {week + 1} development cycle"
        }

        advance_response = api_call("POST", f"{SIM_BASE_URL}/simulation/advance", advance_data)
        if advance_response:
            log(f"   ✅ Week {week + 1} completed")

            # Capture weekly snapshot
            sim_state = api_call("GET", f"{SIM_BASE_URL}/simulation")
            save_json(sim_state, f"week_{week + 1}_state.json")

        time.sleep(1)  # Brief pause

    return True

def generate_reports(personas):
    """Generate comprehensive final reports."""
    log("📊 Generating final reports...")

    # Get final project state
    final_state = api_call("GET", f"{SIM_BASE_URL}/simulation")

    # Get all events
    events = api_call("GET", f"{SIM_BASE_URL}/events")

    # Get token usage
    tokens = api_call("GET", f"{SIM_BASE_URL}/simulation/token-usage")

    # Get reports for each person
    all_reports = {}
    for persona in personas:
        daily_reports = api_call("GET", f"{SIM_BASE_URL}/people/{persona['id']}/daily-reports?limit=50")
        hourly_plans = api_call("GET", f"{SIM_BASE_URL}/people/{persona['id']}/plans?plan_type=hourly&limit=100")

        all_reports[persona['name']] = {
            "daily_reports": daily_reports,
            "hourly_plans": hourly_plans
        }

    # Compile final report
    final_report = {
        "simulation_completed": datetime.now().isoformat(),
        "project": "QuickChat Mobile App - 4 Week Development",
        "team": personas,
        "final_state": final_state,
        "events": events,
        "token_usage": tokens,
        "reports_by_person": all_reports,
        "summary": {
            "total_events": len(events) if events else 0,
            "total_team_members": len(personas),
            "simulation_duration": "4 weeks",
            "total_tokens": tokens.get("total", 0) if tokens else 0
        }
    }

    save_json(final_report, "final_simulation_report.json")

    # Generate readable summary
    summary = f"""# QuickChat Mobile App - 4-Week Development Simulation

## Project Overview
- **Project**: QuickChat Mobile Chatting Application
- **Duration**: 4 weeks
- **Team Size**: {len(personas)} members
- **Completed**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Team Members
"""

    for persona in personas:
        role_marker = " (Team Lead)" if persona.get("is_department_head") else ""
        summary += f"- **{persona['name']}** - {persona['role']}{role_marker}\n"
        summary += f"  - Email: {persona['email_address']}\n"
        summary += f"  - Timezone: {persona['timezone']}\n\n"

    summary += f"""## Simulation Results
- **Total Events Generated**: {final_report['summary']['total_events']}
- **Total AI Tokens Used**: {final_report['summary']['total_tokens']:,}
- **Simulation Status**: {'✅ Completed Successfully' if final_state else '❌ Issues Occurred'}

## Outputs Generated
1. **Team Personas** (`mobile_team.json`) - AI-generated team member profiles
2. **Weekly States** (`week_N_state.json`) - Weekly simulation snapshots
3. **Final Report** (`final_simulation_report.json`) - Complete simulation data
4. **Project Summary** (`PROJECT_SUMMARY.md`) - This human-readable summary

This simulation demonstrates the VDOS system's capability to model realistic
software development workflows with AI-driven team interactions and comprehensive reporting.

Generated by VDOS (Virtual Department Operations Simulator)
"""

    summary_path = OUTPUT_DIR / "PROJECT_SUMMARY.md"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary)

    log("📋 Generated PROJECT_SUMMARY.md")

    return final_report

def main():
    """Main execution."""
    start_time = datetime.now()

    print("🏢 QuickChat Mobile App - Virtual Office Simulation")
    print("=" * 55)

    try:
        # Step 1: Create team
        personas = create_mobile_team()
        if len(personas) != 4:
            log("❌ Failed to create complete team")
            return 1

        # Step 2: Run simulation
        if not run_simulation(personas, weeks=4):
            log("❌ Simulation failed")
            return 1

        # Step 3: Generate reports
        final_report = generate_reports(personas)

        # Success summary
        duration = datetime.now() - start_time
        print("\n" + "=" * 55)
        print("🎉 SIMULATION COMPLETED SUCCESSFULLY!")
        print(f"⏱️  Duration: {duration}")
        print(f"📁 Output Directory: {OUTPUT_DIR.absolute()}")
        print(f"👥 Team: {len(personas)} members")
        print(f"📊 Events: {final_report['summary']['total_events']}")
        print(f"🤖 Tokens: {final_report['summary']['total_tokens']:,}")

        # List output files
        print("\n📄 Generated Files:")
        for file in sorted(OUTPUT_DIR.glob("*")):
            print(f"   - {file.name}")

        return 0

    except Exception as e:
        log(f"💥 Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())