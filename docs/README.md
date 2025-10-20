# Virtual Department Operations Simulator (VDOS) Documentation

> A headless-first sandbox that generates realistic departmental communications (email + chat) and agent behavior so downstream systems (dashboards, analytics, AI assistants) can iterate without exposing production data.

## Table of Contents

### Getting Started
- [Getting Started Guide](GETTING_STARTED.md) - Complete setup and first simulation
- [Architecture Overview](architecture.md) - System architecture, components, and data flow
- [Quick Start](#quick-start) - Get up and running in 5 minutes
- [Environment Variables](reference/environment-variables.md) - Configuration reference

### Core Modules
- [Email Server](modules/email-server.md) - Email communication service
- [Chat Server](modules/chat-server.md) - Chat and DM service
- [Simulation Manager](modules/sim-manager.md) - Orchestration engine
- [Virtual Workers](modules/virtual-workers.md) - AI persona system
- [GUI Application](modules/gui-app.md) - PySide6 desktop interface
- [Utilities](modules/utils.md) - Common utilities and helpers

### API Reference
- [Email API](api/email-api.md) - REST endpoints for email operations
- [Chat API](api/chat-api.md) - REST endpoints for chat operations
- [Simulation Manager API](api/sim-manager-api.md) - REST endpoints for simulation control

### Workflows
- [Simulation Lifecycle](workflows/simulation-lifecycle.md) - How simulations run from start to finish
- [Worker Behavior](workflows/worker-behavior.md) - How virtual workers plan and act
- [Token Tracking](workflows/token-tracking.md) - Token usage tracking system
- [Multi-Project Mode](workflows/multi-project.md) - Running concurrent projects

### Developer Reference
- [Classes Reference](reference/classes.md) - All classes with methods and properties
- [Functions Reference](reference/functions.md) - Standalone functions
- [Data Models](reference/data-models.md) - Pydantic models and schemas
- [Simulation Scripts](scripts/simulation-scripts.md) - Documentation of runner scripts

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/virtualoffice.git
cd virtualoffice

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables (required for AI features)
# Create .env file with your OPENAI_API_KEY
echo "OPENAI_API_KEY=your-key-here" > .env
```

### Running the GUI

```bash
# Start the GUI application (recommended)
briefcase dev

# Or run directly
python -m virtualoffice

# Or run the app module directly
python -m virtualoffice.app
```

### Running Headless

```python
# Example: Quick simulation script
# First start the services manually or use the provided scripts

# Run a complete simulation
python mobile_chat_simulation.py

# Or run a quick test simulation
python quick_simulation.py

# For programmatic control:
import httpx

# Connect to running simulation manager
client = httpx.Client(base_url="http://127.0.0.1:8015")

# Create a persona
persona_data = {
    "name": "Alice Johnson",
    "role": "Senior Developer",
    "timezone": "Asia/Seoul",
    "work_hours": "09:00-18:00",
    "break_frequency": "50/10 cadence",
    "communication_style": "Direct, async",
    "email_address": "alice@vdos.local",
    "chat_handle": "alice",
    "skills": ["Python", "FastAPI"],
    "personality": ["Analytical", "Collaborative"]
}
response = client.post("/api/v1/people", json=persona_data)
print(f"Created person: {response.json()}")

# Start simulation
sim_request = {
    "project_name": "Dashboard MVP",
    "project_summary": "Build a metrics dashboard for team productivity",
    "duration_weeks": 2
}
response = client.post("/api/v1/simulation/start", json=sim_request)
print(f"Simulation started: {response.json()}")

# Advance simulation
advance_request = {"ticks": 480, "reason": "manual advance"}
response = client.post("/api/v1/simulation/advance", json=advance_request)
result = response.json()
print(f"Advanced to tick {result['current_tick']}: {result['emails_sent']} emails, {result['chat_messages_sent']} chats")
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     PySide6 GUI Application                   │
│                  (src/virtualoffice/app.py)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Server Mgmt  │  │  Sim Control │  │ Persona Mgmt │      │
│  │ Start/Stop   │  │ Start/Stop   │  │ Create/Edit  │      │
│  │ Services     │  │ Advance      │  │ View Reports │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                           │ HTTP Requests
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ Email   │      │  Chat   │      │   Sim   │
    │ Server  │      │ Server  │      │ Manager │
    │ :8000   │      │ :8001   │      │ :8015   │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                │                 │
         │                │          ┌──────▼──────┐
         │                │          │ Sim Engine  │
         │                │          │  - Planner  │
         │                │          │  - Workers  │
         │                │          │  - Events   │
         │                │          │  - Gateways │
         └────────────────┴──────────┤             │
                          │          └──────┬──────┘
                    ┌─────▼─────┐           │
                    │  SQLite   │◄──────────┘
                    │ (vdos.db) │
                    └───────────┘
```

### Key Components

1. **Email Server (Port 8000)**: Handles email operations, mailboxes, drafts
2. **Chat Server (Port 8001)**: Manages chat rooms, DMs, and user presence
3. **Simulation Manager (Port 8015)**: Orchestrates the simulation, manages ticks, workers, and planning
4. **PySide6 GUI**: Desktop interface for developers to control and monitor simulations
5. **SQLite Database**: Single shared database for all services

## Core Concepts

### Ticks
A "tick" represents one minute of simulated time. By default:
- 1 tick = 1 minute
- 480 ticks = 1 workday (8 hours)
- Workers plan and communicate based on ticks

### Personas
Virtual workers with:
- Skills and personality traits
- Work hours and schedules
- Communication styles
- Email addresses and chat handles

### Projects
Simulation scenarios with:
- Name and summary
- Duration (weeks)
- Team assignments
- Multi-project concurrent support

### Planning Hierarchy
1. **Project Plan**: Department head creates overall roadmap
2. **Daily Plans**: Workers plan each day based on project
3. **Hourly Plans**: Workers adjust plans based on incoming messages
4. **Daily Reports**: End-of-day summaries with progress and blockers

## Development

### Running Tests

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_sim_manager.py

# Run with coverage
python -m pytest --cov=virtualoffice
```

### Project Structure

```
virtualoffice/
├── src/virtualoffice/
│   ├── __main__.py              # CLI entry point
│   ├── app.py                   # PySide6 GUI application (1197 lines)
│   ├── servers/
│   │   ├── email/               # Email server module
│   │   │   ├── app.py          # FastAPI email endpoints
│   │   │   └── models.py       # Email data models
│   │   └── chat/                # Chat server module
│   │       ├── app.py          # FastAPI chat endpoints
│   │       └── models.py       # Chat data models
│   ├── sim_manager/             # Simulation orchestration
│   │   ├── app.py              # FastAPI simulation API
│   │   ├── engine.py           # Core simulation engine (2360+ lines)
│   │   ├── planner.py          # GPT/Stub planning logic
│   │   ├── gateways.py         # HTTP clients for email/chat
│   │   ├── schemas.py          # Pydantic request/response models
│   │   ├── index.html          # Web dashboard (optional)
│   │   └── static/             # Static web assets
│   ├── virtualWorkers/          # Persona system
│   │   └── worker.py           # Worker persona and markdown builder
│   ├── common/                  # Shared utilities
│   │   └── db.py               # SQLite database helpers
│   ├── utils/                   # Utility functions
│   │   ├── completion_util.py  # OpenAI API wrapper
│   │   └── pdf_to_md.py        # PDF processing utility
│   ├── resources/               # Static resources
│   └── vdos.db                 # SQLite database file
├── tests/                       # Comprehensive test suite
│   ├── conftest.py             # Test configuration and fixtures
│   ├── test_*.py               # Individual test modules
│   └── virtualoffice.py        # Test utilities
├── docs/                        # Documentation
├── simulation_output/           # Generated simulation artifacts
├── agent_reports/              # AI-generated analysis reports
├── scripts/                    # Utility scripts
├── mobile_chat_simulation.py   # Main simulation runner
├── quick_simulation.py         # Quick test simulation
├── pyproject.toml              # Briefcase configuration
└── requirements.txt            # Python dependencies
```

## Contributing

See [CLAUDE.md](../CLAUDE.md) for detailed guidelines on:
- Code organization
- Testing requirements
- Commit message format
- Development workflow

## License

See [LICENSE](../LICENSE) for details.
