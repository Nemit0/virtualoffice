#!/usr/bin/env python3
"""
Mobile Chat App Simulation Test
===============================

Pytest version of the mobile chat app simulation that creates realistic personas
and runs a 4-week development simulation.
"""

import json
import os
import time
import pytest
from datetime import datetime
from pathlib import Path
import requests

# Base URLs for the running servers
SIM_BASE_URL = "http://127.0.0.1:8015/api/v1"

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "simulation_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def log(message):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def api_call(method, url, data=None):
    """Make API call with error handling."""
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        return response.json() if response.content else {}
    except Exception as e:
        log(f"API Error: {e}")
        return {}


def save_json(data, filename):
    """Save data to JSON file."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Saved: {filename}")


class TestMobileChatSimulation:
    """Test class for mobile chat app simulation."""

    @pytest.fixture(scope="class")
    def mobile_team(self):
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
        assert len(created_personas) == 4, "Should create exactly 4 personas"
        return created_personas

    def test_team_creation(self, mobile_team):
        """Test that the mobile development team is created successfully."""
        assert len(mobile_team) == 4

        # Check that we have the right roles
        roles = [persona.get("role", "") for persona in mobile_team]
        assert any("Project Manager" in role or "Manager" in role for role in roles)
        assert any("Designer" in role or "UI" in role or "UX" in role for role in roles)
        assert any("Developer" in role or "Dev" in role for role in roles)
        assert any("DevOps" in role or "Ops" in role for role in roles)

        # Check that exactly one is department head
        heads = [p for p in mobile_team if p.get("is_department_head")]
        assert len(heads) == 1

        log("✅ Team creation test passed")

    def test_simulation_setup_and_run(self, mobile_team):
        """Test running the 4-week mobile chat app simulation."""
        log("🚀 Starting 4-week QuickChat mobile app simulation...")
        weeks = 4

        # Start simulation
        start_data = {
            "project_name": "QuickChat Mobile App",
            "project_summary": "Develop a barebone mobile chatting application with core messaging features, user authentication, real-time chat, and basic UI/UX. Target completion in 4 weeks with iterative development.",
            "duration_weeks": weeks,
            "include_person_ids": [p["id"] for p in mobile_team],
            "random_seed": 42
        }

        start_response = api_call("POST", f"{SIM_BASE_URL}/simulation/start", start_data)
        assert start_response, "Simulation should start successfully"
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
            assert advance_response, f"Week {week + 1} should advance successfully"
            log(f"   ✅ Week {week + 1} completed")

            # Capture weekly snapshot
            sim_state = api_call("GET", f"{SIM_BASE_URL}/simulation")
            save_json(sim_state, f"week_{week + 1}_state.json")

            time.sleep(1)  # Brief pause

        log("✅ Simulation run test passed")

    def test_report_generation(self, mobile_team):
        """Test generating comprehensive final reports."""
        log("📊 Generating final reports...")

        # Get final project state
        final_state = api_call("GET", f"{SIM_BASE_URL}/simulation")
        assert final_state, "Should retrieve final simulation state"

        # Get all events
        events = api_call("GET", f"{SIM_BASE_URL}/events")
        assert isinstance(events, list), "Events should be a list"

        # Get token usage
        tokens = api_call("GET", f"{SIM_BASE_URL}/simulation/token-usage")

        # Get reports for each person
        all_reports = {}
        for persona in mobile_team:
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
            "team": mobile_team,
            "final_state": final_state,
            "events": events,
            "token_usage": tokens,
            "reports_by_person": all_reports,
            "summary": {
                "total_events": len(events) if events else 0,
                "total_team_members": len(mobile_team),
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
- **Team Size**: {len(mobile_team)} members
- **Completed**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Team Members
"""

        for persona in mobile_team:
            role_marker = " (Team Lead)" if persona.get("is_department_head") else ""
            summary += f"- **{persona['name']}** - {persona['role']}{role_marker}\\n"
            summary += f"  - Email: {persona['email_address']}\\n"
            summary += f"  - Timezone: {persona['timezone']}\\n\\n"

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

        # Assertions for test validation
        assert final_report["summary"]["total_events"] >= 0
        assert final_report["summary"]["total_team_members"] == 4
        assert len(all_reports) == 4

        log("✅ Report generation test passed")

    def test_output_files_exist(self):
        """Test that all expected output files were created."""
        expected_files = [
            "mobile_team.json",
            "final_simulation_report.json",
            "PROJECT_SUMMARY.md"
        ]

        for filename in expected_files:
            file_path = OUTPUT_DIR / filename
            assert file_path.exists(), f"Output file {filename} should exist"
            assert file_path.stat().st_size > 0, f"Output file {filename} should not be empty"

        # Check for weekly state files
        for week in range(1, 5):
            week_file = OUTPUT_DIR / f"week_{week}_state.json"
            assert week_file.exists(), f"Week {week} state file should exist"

        log("✅ Output files validation test passed")

    def test_simulation_metrics(self):
        """Test simulation produced meaningful metrics."""
        report_path = OUTPUT_DIR / "final_simulation_report.json"
        assert report_path.exists(), "Final report should exist"

        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)

        # Validate key metrics
        assert report["summary"]["total_team_members"] == 4
        assert report["summary"]["simulation_duration"] == "4 weeks"
        assert isinstance(report["events"], list)
        assert len(report["team"]) == 4

        # Check that all team members have reports
        assert len(report["reports_by_person"]) == 4

        log("✅ Simulation metrics validation test passed")


if __name__ == "__main__":
    # Allow running as standalone script for debugging
    pytest.main([__file__, "-v", "--tb=short"])