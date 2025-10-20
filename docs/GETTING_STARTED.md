# Getting Started with VDOS

This guide will help you get the Virtual Department Operations Simulator up and running quickly.

## Prerequisites

- Python 3.11 or higher
- Git (for cloning the repository)
- OpenAI API key for AI-powered features (optional for functionality, but package is required)

## Installation

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd virtualoffice

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure AI Features

VDOS now includes OpenAI integration as a core dependency. Set up your API key:

```bash
# Create .env file
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

**Note**: While the OpenAI package is installed, AI features will gracefully degrade to stub implementations if no API key is provided.

## Quick Start Options

### Option 1: GUI Application (Recommended for Beginners)

The GUI provides the easiest way to get started:

```bash
# Start the PySide6 GUI
briefcase dev

# Or run directly
python -m virtualoffice
```

**What you'll see:**
- Server management panel (start/stop individual services)
- Simulation controls (start/stop/advance)
- Persona creation and management
- Real-time logs and reports
- Token usage monitoring

**First steps in the GUI:**
1. Click "Start" for each service (Email, Chat, Simulation)
2. Click "Seed Sample Worker" to create a test persona
3. Fill in project details (name, summary, duration)
4. Click "Start Simulation"
5. Use "Advance" to manually step through time
6. Watch the logs and reports update in real-time

### Option 2: Run a Complete Simulation Script

For a hands-off experience:

```bash
# Run a comprehensive 4-week simulation
python mobile_chat_simulation.py

# Or run a quick test
python quick_simulation.py
```

These scripts will:
- Start all required services
- Create sample personas
- Run a complete simulation
- Generate reports and artifacts
- Save results to `simulation_output/`

### Option 3: Manual Service Management

For developers who want full control:

```bash
# Terminal 1: Email Server
uvicorn virtualoffice.servers.email:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Chat Server  
uvicorn virtualoffice.servers.chat:app --host 127.0.0.1 --port 8001 --reload

# Terminal 3: Simulation Manager
uvicorn virtualoffice.sim_manager:create_app --host 127.0.0.1 --port 8015 --reload
```

Then use the API directly or run simulation scripts.

## Your First Simulation

### Step 1: Create Personas

You can create personas in several ways:

**Via GUI:**
1. Click "Create Person" in the dashboard
2. Fill in the form manually or use "Generate with GPT-4o"
3. Click OK to create

**Via API:**
```bash
curl -X POST http://127.0.0.1:8015/api/v1/people \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "role": "Senior Developer",
    "timezone": "Asia/Seoul", 
    "work_hours": "09:00-18:00",
    "break_frequency": "50/10 cadence",
    "communication_style": "Direct, async",
    "email_address": "alice@vdos.local",
    "chat_handle": "alice",
    "skills": ["Python", "FastAPI", "React"],
    "personality": ["Analytical", "Collaborative", "Detail-oriented"]
  }'
```

### Step 2: Start a Simulation

**Via GUI:**
1. Enter project name: "Dashboard MVP"
2. Enter project summary: "Build a metrics dashboard for team productivity"
3. Set duration: 2 weeks
4. Select participants (check/uncheck personas)
5. Click "Start Simulation"

**Via API:**
```bash
curl -X POST http://127.0.0.1:8015/api/v1/simulation/start \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Dashboard MVP",
    "project_summary": "Build a metrics dashboard for team productivity",
    "duration_weeks": 2
  }'
```

### Step 3: Advance Time

**Via GUI:**
- Set ticks (480 = 1 workday)
- Enter reason: "manual test"
- Click "Advance"

**Via API:**
```bash
curl -X POST http://127.0.0.1:8015/api/v1/simulation/advance \
  -H "Content-Type: application/json" \
  -d '{"ticks": 480, "reason": "manual test"}'
```

### Step 4: View Results

**Via GUI:**
- Check the "Daily Reports", "Simulation Reports", and "Token Usage" tabs
- View real-time logs in the bottom panel
- Monitor current tasks and hourly plans

**Via API:**
```bash
# Get simulation state
curl http://127.0.0.1:8015/api/v1/simulation

# Get daily reports for a person
curl http://127.0.0.1:8015/api/v1/people/1/daily-reports

# Get token usage
curl http://127.0.0.1:8015/api/v1/simulation/token-usage
```

## Understanding the Output

### Simulation Artifacts

When you run simulations, you'll find generated content in:

- `simulation_output/` - Timestamped simulation runs with JSON data
- `agent_reports/` - AI-generated analysis reports  
- `virtualoffice.log` - Application logs
- `token_usage.json` - Token consumption tracking

### Key Metrics

- **Ticks**: Simulation time units (1 tick = 1 minute)
- **Emails sent**: Number of email messages generated
- **Chat messages**: Number of chat messages sent
- **Token usage**: OpenAI API tokens consumed (if AI features enabled)
- **Current tick**: Current simulation time position

### Typical Simulation Flow

1. **Project Planning**: Department head creates project roadmap
2. **Daily Planning**: Each worker plans their day
3. **Hourly Execution**: Workers execute plans, send messages, respond to events
4. **Message Processing**: Workers read inbox, acknowledge messages, replan
5. **Daily Reports**: End-of-day summaries and next-day planning
6. **Event Injection**: Random events (client changes, blockers, absences)

## Common Issues and Solutions

### Services Won't Start
- Check if ports 8000, 8001, 8015 are available
- Ensure virtual environment is activated
- Check `virtualoffice.log` for error details

### AI Features Not Working
- Verify `OPENAI_API_KEY` is set in `.env` file
- Check API key has sufficient credits
- AI features gracefully degrade to stub implementations

### Simulation Seems Stuck
- Check if simulation is actually running (`GET /api/v1/simulation`)
- Verify personas exist and are included in simulation
- Look for errors in logs or GUI status messages

### No Messages Generated
- Ensure multiple personas exist
- Check that simulation has advanced enough ticks
- Verify project summary provides clear work context

## Next Steps

Once you have a basic simulation running:

1. **Explore the GUI**: Try different persona configurations and project types
2. **Read the Architecture**: Understand how the components work together
3. **Customize Personas**: Create personas that match your use case
4. **Analyze Output**: Use the generated data for your downstream applications
5. **Extend the System**: Add new event types or planning strategies

## Getting Help

- Check the logs: `virtualoffice.log` contains detailed execution information
- Review the API documentation for endpoint details
- Look at the test files for usage examples
- Examine the simulation scripts for complete workflows

The VDOS system is designed to be both powerful and approachable. Start with the GUI to understand the concepts, then move to programmatic control as your needs grow.