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

# Optional: Enable Korean localization
echo "VDOS_LOCALE=ko" >> .env

# Optional: Disable auto-pause when projects complete (enabled by default)
echo "VDOS_AUTO_PAUSE_ON_PROJECT_END=false" >> .env
```

**Note**: While the OpenAI package is installed, AI features will gracefully degrade to stub implementations if no API key is provided.

**Localization**: Set `VDOS_LOCALE=ko` for enhanced Korean workplace simulations with:
- Natural Korean communication patterns and strict language enforcement
- Korean-localized persona generation with workplace-appropriate terminology
- Korean timezone (`Asia/Seoul`) and work hours (`09:00-18:00`) defaults
- Centralized localization system managing all hardcoded strings and templates
- Consistent Korean experience across all AI-generated content

**Auto-Pause**: Auto-pause is enabled by default (`VDOS_AUTO_PAUSE_ON_PROJECT_END=true`) to automatically stop auto-tick when all projects complete, preventing simulations from running indefinitely after work is done. Set to `false` to disable this behavior.

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
- **Web Dashboard Access**: Navigate to `http://127.0.0.1:8015` for browser-based interface

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

Then use the API directly, run simulation scripts, or access the web dashboard at `http://127.0.0.1:8015`.

### Option 4: Web Dashboard Interface

Access the browser-based interface for monitoring and visualization:

```bash
# Start services (any method above)
# Then navigate to: http://127.0.0.1:8015

# The web dashboard provides:
# - Real-time chat monitoring with conversation sidebar
# - Email client interface with inbox/sent management  
# - Responsive design for desktop and mobile
# - Professional messaging interface similar to Slack/Discord
```

**Web Dashboard Features:**
- **Chat Tab**: View conversations from any persona's perspective with real-time updates
- **Email Tab**: Browse inbox and sent emails with search and threading
- **Controls Tab**: Full simulation management (same as GUI)
- **Responsive Design**: Works on desktop, tablet, and mobile devices

## Your First Simulation

### Step 1: Create Personas

You can create personas in several ways:

**Via GUI:**
1. Click "Create Person" in the dashboard
2. Fill in the form manually or use "Generate with GPT-4o"
   - For Korean simulations: Set `VDOS_LOCALE=ko` to generate Korean workplace personas
   - Korean personas automatically use appropriate timezone, work hours, and terminology
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

## Advanced Features

### Prompt Management System

VDOS includes a centralized prompt management system for AI-powered features:

**Key Features:**
- **YAML-based templates**: All LLM prompts defined in versioned YAML templates
- **Template categories**: Planning (hourly, daily), reporting, events, communication
- **Localization support**: Separate templates for English (`_en.yaml`) and Korean (`_ko.yaml`)
- **A/B testing**: Support for prompt variants with performance metrics
- **Context-aware prompts**: Automatic context building with persona, team, project info
- **Metrics collection**: Track token usage, duration, and success rates per template

**Template Location**: `src/virtualoffice/sim_manager/prompts/templates/`

**Creating Custom Templates:**

See `docs/guides/template_authoring.md` for a complete guide on creating custom prompt templates.

Example template structure:
```yaml
name: "hourly_planning_en"
version: "1.0"
locale: "en"
category: "planning"

system_prompt: |
  You act as an operations coach who reshapes hourly schedules.

user_prompt_template: |
  Worker: {worker_name} ({worker_role}) at tick {tick}.
  {persona_section}
  {team_roster_section}
  
  Plan the next few hours with realistic tasks.

sections:
  persona_section:
    template: "=== YOUR PERSONA ===\n{persona_markdown}"
    required_variables: ["persona_markdown"]

validation_rules:
  - "Must include scheduled communications section"
```

**Documentation:**
- `docs/modules/prompt_system.md` - Complete prompt system reference
- `docs/guides/template_authoring.md` - Template creation guide
- `docs/modules/virtual_worker_context.md` - Context classes documentation

## Next Steps

Once you have a basic simulation running:

1. **Explore the GUI**: Try different persona configurations and project types
2. **Read the Architecture**: Understand how the components work together (`docs/architecture.md`)
3. **Customize Personas**: Create personas that match your use case
4. **Customize Prompts**: Create custom prompt templates for specialized scenarios
5. **Analyze Output**: Use the generated data for your downstream applications
6. **Extend the System**: Add new event types or planning strategies

## Getting Help

- Check the logs: `virtualoffice.log` contains detailed execution information
- Review the API documentation for endpoint details
- Look at the test files for usage examples
- Examine the simulation scripts for complete workflows

The VDOS system is designed to be both powerful and approachable. Start with the GUI to understand the concepts, then move to programmatic control as your needs grow.## Te
sting and Validation

VDOS includes comprehensive testing to ensure reliability and correctness:

### Running Tests

```bash
# Run the complete test suite
pytest tests/

# Run specific auto-pause integration tests
pytest tests/test_auto_pause_integration.py -v

# Run with coverage reporting
pytest tests/ --cov=src/virtualoffice
```

### Auto-Pause Testing

The auto-pause functionality includes extensive integration tests that validate:

- **Complete workflow**: End-to-end auto-pause triggering when projects complete
- **Multi-project scenarios**: Overlapping, sequential, and gap project timelines
- **API endpoints**: Request/response handling and error cases
- **State persistence**: Session-level configuration changes
- **Future project detection**: Prevention of premature auto-pause

### Test Coverage

Key test files provide comprehensive coverage:
- `tests/test_auto_pause_integration.py` - Integration tests for auto-pause workflow
- `tests/test_auto_pause_unit.py` - Unit tests for individual components
- `tests/test_sim_manager.py` - Simulation engine tests
- `tests/test_email_server.py` - Email service tests
- `tests/test_chat_server.py` - Chat service tests

## Next Steps

- Explore the [API Reference](api/API_REFERENCE.md) for detailed endpoint documentation
- Review [Architecture](architecture.md) for system design details
- Check out simulation scripts in the `scripts/` directory for advanced examples
- Run the test suite to validate your installation

## Troubleshooting

### Common Issues

1. **Services won't start**: Check that ports 8000, 8001, and 8015 are available
2. **AI features not working**: Verify your OpenAI API key is set correctly
3. **Database errors**: Ensure the SQLite database file has proper permissions
4. **Test failures**: Run `pytest tests/ -v` to see detailed error information

### Getting Help

- Check the logs in `virtualoffice.log` for detailed error information
- Review the comprehensive test suite for usage examples
- Examine the `agent_reports/` directory for implementation details