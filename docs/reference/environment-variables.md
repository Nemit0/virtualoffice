# Environment Variables Reference

## Overview

VDOS uses environment variables for configuration. Variables can be set in:
1. `.env` file (local development only, not committed)
2. Operating system environment
3. Docker/deployment configuration

## Service Connection

### VDOS_EMAIL_HOST
- **Default**: `127.0.0.1`
- **Description**: Hostname or IP address of the email server
- **Example**: `VDOS_EMAIL_HOST=localhost`

### VDOS_EMAIL_PORT
- **Default**: `8000`
- **Description**: Port number for the email server
- **Example**: `VDOS_EMAIL_PORT=8000`

### VDOS_EMAIL_BASE_URL
- **Default**: `http://{VDOS_EMAIL_HOST}:{VDOS_EMAIL_PORT}`
- **Description**: Full base URL for email server (overrides host/port)
- **Example**: `VDOS_EMAIL_BASE_URL=http://email-server:8000`

### VDOS_CHAT_HOST
- **Default**: `127.0.0.1`
- **Description**: Hostname or IP address of the chat server
- **Example**: `VDOS_CHAT_HOST=localhost`

### VDOS_CHAT_PORT
- **Default**: `8001`
- **Description**: Port number for the chat server
- **Example**: `VDOS_CHAT_PORT=8001`

### VDOS_CHAT_BASE_URL
- **Default**: `http://{VDOS_CHAT_HOST}:{VDOS_CHAT_PORT}`
- **Description**: Full base URL for chat server (overrides host/port)
- **Example**: `VDOS_CHAT_BASE_URL=http://chat-server:8001`

### VDOS_SIM_HOST
- **Default**: `127.0.0.1`
- **Description**: Hostname or IP address of the simulation manager
- **Example**: `VDOS_SIM_HOST=localhost`

### VDOS_SIM_PORT
- **Default**: `8015`
- **Description**: Port number for the simulation manager
- **Example**: `VDOS_SIM_PORT=8015`

### VDOS_SIM_BASE_URL
- **Default**: `http://{VDOS_SIM_HOST}:{VDOS_SIM_PORT}`
- **Description**: Full base URL for simulation manager
- **Example**: `VDOS_SIM_BASE_URL=http://sim-manager:8015`

## Database

### VDOS_DB_PATH
- **Default**: `src/virtualoffice/vdos.db`
- **Description**: Path to SQLite database file
- **Example**: `VDOS_DB_PATH=/data/vdos.db`
- **Notes**: All services must point to the same database file

## Time Model & Scheduling

### VDOS_TICK_INTERVAL_SECONDS
- **Default**: `1.0`
- **Description**: Seconds between auto-ticks when enabled.
- **Example**: `VDOS_TICK_INTERVAL_SECONDS=0.5`
- **Notes**: Lower values run the simulation faster but use more CPU.

### VDOS_HOURS_PER_DAY
- **Default**: `8`
- **Description**: Length of a simulated workday in hours.
- **Example**: `VDOS_HOURS_PER_DAY=6`
- **Notes**: Replaces the older `VDOS_TICKS_PER_DAY` knob. If `VDOS_TICKS_PER_DAY` is still set, it is converted to hours by dividing by 60 for backward compatibility.

### VDOS_TICKS_PER_DAY (legacy)
- **Default**: `480`
- **Description**: Legacy setting for ticks per day (1 tick = 1 minute).
- **Notes**: Prefer `VDOS_HOURS_PER_DAY`. Still supported for compatibility.

## Simulation Configuration

### VDOS_CONTACT_COOLDOWN_TICKS
- **Default**: `10`
- **Description**: Minimum ticks between contacts to same person
- **Example**: `VDOS_CONTACT_COOLDOWN_TICKS=20`
- **Notes**: Prevents message spam; 0 disables cooldown

### VDOS_MAX_HOURLY_PLANS_PER_MINUTE
- **Default**: `10`
- **Description**: Maximum hourly plans per person per minute
- **Example**: `VDOS_MAX_HOURLY_PLANS_PER_MINUTE=5`
- **Notes**: Rate limit to prevent planning loops

### VDOS_AUTO_PAUSE_ON_PROJECT_END
- **Default**: `false`
- **Description**: Automatically pause auto-tick when all projects complete
- **Example**: `VDOS_AUTO_PAUSE_ON_PROJECT_END=true`
- **Values**: `true` (enable auto-pause), `false` (disabled)
- **Notes**: Prevents simulations from running indefinitely after all work is done. Checks for both active and future projects before pausing.

### VDOS_COMM_STAGGER_MAX_MINUTES
- **Default**: `7`
- **Description**: Maximum number of minutes to stagger communications within a tick window.
- **Notes**: Used to avoid bursts of messages all landing at the exact same simulated minute.

### VDOS_AVOID_ROUND_MINUTES
- **Default**: `true`
- **Description**: When enabled, avoids scheduling communications exactly on round times (e.g. `09:00`, `10:00`).
- **Notes**: Helps produce more natural-looking timelines.

## Simulation Identity

### VDOS_SIM_EMAIL
- **Default**: `simulator@vdos.local`
- **Description**: Email address for simulation manager messages
- **Example**: `VDOS_SIM_EMAIL=admin@company.local`

### VDOS_SIM_HANDLE
- **Default**: `sim-manager`
- **Description**: Chat handle for simulation manager
- **Example**: `VDOS_SIM_HANDLE=admin`

## Planner Configuration

### VDOS_PLANNER_STRICT
- **Default**: `0`
- **Description**: If `1`, disable fallback to stub planner on GPT failure
- **Example**: `VDOS_PLANNER_STRICT=1`
- **Values**: `0` (fallback enabled), `1` (strict mode, fail on error)

### VDOS_PLANNER_PROJECT_MODEL
- **Default**: `gpt-4.1-nano`
- **Description**: Model for generating project plans
- **Example**: `VDOS_PLANNER_PROJECT_MODEL=gpt-4o`

### VDOS_PLANNER_DAILY_MODEL
- **Default**: Same as `VDOS_PLANNER_PROJECT_MODEL`
- **Description**: Model for generating daily plans
- **Example**: `VDOS_PLANNER_DAILY_MODEL=gpt-4o-mini`

### VDOS_PLANNER_HOURLY_MODEL
- **Default**: Same as `VDOS_PLANNER_DAILY_MODEL`
- **Description**: Model for generating hourly plans
- **Example**: `VDOS_PLANNER_HOURLY_MODEL=gpt-4.1-nano`

### VDOS_PLANNER_DAILY_REPORT_MODEL
- **Default**: Same as `VDOS_PLANNER_DAILY_MODEL`
- **Description**: Model for generating daily reports
- **Example**: `VDOS_PLANNER_DAILY_REPORT_MODEL=gpt-4o-mini`

### VDOS_PLANNER_SIM_REPORT_MODEL
- **Default**: Same as `VDOS_PLANNER_PROJECT_MODEL`
- **Description**: Model for generating simulation reports
- **Example**: `VDOS_PLANNER_SIM_REPORT_MODEL=gpt-4o`

### VDOS_PLAN_PARSER_MODEL
- **Default**: `gpt-4o-mini`
- **Description**: Model used by the JSON `PlanParser` when parsing hourly plans with embedded communications.
- **Notes**: Only used when `VDOS_ENABLE_PLAN_PARSER` is enabled.

## Localization

### VDOS_LOCALE
- **Default**: `en`
- **Description**: Locale for generated content with enhanced Korean support
- **Values**: `en` (English), `ko` (Korean)
- **Example**: `VDOS_LOCALE=ko`
- **Notes**: 
  - Affects all AI-generated content (plans, messages, reports, personas)
  - Korean mode enforces natural workplace Korean language
  - Prevents English/Korean mixing with strict language instructions
  - Includes context-aware examples for proper Korean terminology
  - Applied across all planner functions and persona generation for consistency
  - Korean personas automatically use `Asia/Seoul` timezone and Korean workplace defaults
  - Fallback stub personas also localized to Korean when AI unavailable

### VDOS_EXTERNAL_STAKEHOLDERS
- **Default**: *(unset)*
- **Description**: Comma-separated list of external stakeholder email addresses.
- **Notes**: Used by the simulation engine and communication hub to route messages to non-simulated recipients.

## OpenAI Integration

### OPENAI_API_KEY
- **Default**: None (required for GPT planning)
- **Description**: OpenAI API key for GPT models
- **Example**: `OPENAI_API_KEY=sk-...`
- **Security**: Store in `.env` (local) or secure secret store (production)
- **Notes**: Without this, only stub planner is available

### OPENAI_MODEL
- **Default**: `gpt-4.1-nano`
- **Description**: Default model for persona generation
- **Example**: `OPENAI_MODEL=gpt-4o-mini`

### OPENAI_API_KEY2
- **Default**: None
- **Description**: Secondary OpenAI API key used when rotating across free tier limits.
- **Notes**: The completion utility can automatically switch between `OPENAI_API_KEY` and `OPENAI_API_KEY2` based on `VDOS_API_PROVIDER` and token usage.

### VDOS_API_PROVIDER
- **Default**: `auto`
- **Description**: Controls which provider/key is used for GPT calls.
- **Values**:
  - `auto` – automatically choose based on free tier usage
  - `openai_key1` – force `OPENAI_API_KEY`
  - `openai_key2` – force `OPENAI_API_KEY2`
  - `azure` – force Azure OpenAI

### VDOS_OPENAI_TIMEOUT
- **Default**: `120`
- **Description**: Timeout (seconds) for OpenAI/Azure OpenAI requests.

### VDOS_OPENAI_TEMPERATURE
- **Default**: *(OpenAI default)*
- **Description**: Optional override for LLM temperature (0.0–2.0). If unset, the API default is used.

### FIX_ALL_GPT_MODEL
- **Default**: `false`
- **Description**: When `true`, forces all GPT calls through a single `FIXED_MODEL` value (for experiments/diagnostics).

### FIXED_MODEL
- **Default**: `gpt-4o`
- **Description**: Model name used when `FIX_ALL_GPT_MODEL=true`.

### AZURE_OPENAI_API_KEY
- **Default**: None
- **Description**: API key for Azure OpenAI.

### AZURE_OPENAI_ENDPOINT
- **Default**: None
- **Description**: Endpoint URL for Azure OpenAI (e.g. `https://your-resource.openai.azure.com/`).

### AZURE_OPENAI_API_VERSION
- **Default**: `2025-04-01-preview`
- **Description**: API version used for Azure OpenAI calls.

### VDOS_FALLBACK_MODEL
- **Default**: `gpt-4o-mini`
- **Description**: Model used for GPT-powered fallback communications when enabled.

### VDOS_STYLE_FILTER_ENABLED
- **Default**: `true`
- **Description**: Enable/disable the communication style filter (persona-specific writing style transforms).

## GUI Configuration

### VDOS_GUI_AUTOKILL_SECONDS
- **Default**: None (disabled)
- **Description**: Auto-shutdown GUI after N seconds (testing only)
- **Example**: `VDOS_GUI_AUTOKILL_SECONDS=300`
- **Notes**: Used for automated GUI testing; leave unset in normal use

## Communication Volume Configuration

### VDOS_ENABLE_AUTO_FALLBACK
- **Default**: `false`
- **Description**: Enable/disable automatic fallback communication generation (legacy feature)
- **Example**: `VDOS_ENABLE_AUTO_FALLBACK=false`
- **Values**: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
- **Notes**: Disabled by default in v2.0 to reduce excessive email volume. Set to `true` to restore legacy behavior.

### VDOS_ENABLE_INBOX_REPLIES
- **Default**: `true`
- **Description**: Enable inbox-driven reply generation for realistic threading
- **Example**: `VDOS_ENABLE_INBOX_REPLIES=true`
- **Values**: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
- **Notes**: When enabled, personas reply to unreplied messages in their inbox. Maintains threading and realistic communication patterns.

### VDOS_INBOX_REPLY_PROBABILITY
- **Default**: `0.80`
- **Description**: Probability (0.0-1.0) of replying to inbox messages
- **Example**: `VDOS_INBOX_REPLY_PROBABILITY=0.80`
- **Range**: 0.0 to 1.0
- **Notes**: 
  - 0.80 = 80% of unreplied messages get replies
  - Higher values create more conversational threads
  - Deterministic with random seed for reproducible simulations
  - Updated from 0.65 to 0.80 on Nov 6, 2025 for more active communication patterns

### VDOS_MAX_EMAILS_PER_DAY
- **Default**: `50`
- **Description**: Hard limit on emails per persona per day (safety net)
- **Example**: `VDOS_MAX_EMAILS_PER_DAY=50`
- **Notes**: Prevents runaway email generation bugs. WARNING logs when limits reached.

### VDOS_MAX_CHATS_PER_DAY
- **Default**: `100`
- **Description**: Hard limit on chats per persona per day (safety net)
- **Example**: `VDOS_MAX_CHATS_PER_DAY=100`
- **Notes**: Prevents runaway chat generation bugs. WARNING logs when limits reached.

### VDOS_THREADING_RATE
- **Default**: `0.3`
- **Description**: Target rate (0.0–1.0) for generating threaded email replies.
- **Notes**: Higher values produce more reply chains; validated and clamped to safe ranges.

### VDOS_FALLBACK_PROBABILITY
- **Default**: `0.6`
- **Description**: Base probability (0.0–1.0) of generating fallback communications when enabled.
- **Notes**: Only used when `VDOS_ENABLE_AUTO_FALLBACK=true`.

### VDOS_PARTICIPATION_BALANCE_ENABLED
- **Default**: `true`
- **Description**: Enable participation balancing to prevent a few personas from dominating communications.

### VDOS_PARTICIPATION_THROTTLE_RATIO
- **Default**: `1.3`
- **Description**: Threshold ratio for throttling high-volume senders.

### VDOS_PARTICIPATION_THROTTLE_PROBABILITY
- **Default**: `0.1`
- **Description**: Probability of suppressing communications from over-active senders when balancing is enabled.

## Example .env File

```bash
# Service connections
VDOS_EMAIL_HOST=127.0.0.1
VDOS_EMAIL_PORT=8000
VDOS_CHAT_HOST=127.0.0.1
VDOS_CHAT_PORT=8001
VDOS_SIM_HOST=127.0.0.1
VDOS_SIM_PORT=8015

# Database
VDOS_DB_PATH=src/virtualoffice/vdos.db

# Simulation settings
VDOS_TICKS_PER_DAY=480
VDOS_TICK_INTERVAL_SECONDS=1.0

# Communication volume control (v2.0)
VDOS_ENABLE_AUTO_FALLBACK=false
VDOS_ENABLE_INBOX_REPLIES=true
VDOS_INBOX_REPLY_PROBABILITY=0.80
VDOS_MAX_EMAILS_PER_DAY=50
VDOS_MAX_CHATS_PER_DAY=100

# OpenAI (required for GPT planning)
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-nano

# Planner models
VDOS_PLANNER_PROJECT_MODEL=gpt-4.1-nano
VDOS_PLANNER_DAILY_MODEL=gpt-4.1-nano
VDOS_PLANNER_HOURLY_MODEL=gpt-4.1-nano

# Locale
VDOS_LOCALE=en

# Planner behavior
VDOS_PLANNER_STRICT=0

# Auto-pause
VDOS_AUTO_PAUSE_ON_PROJECT_END=false
```

## Docker Example

```yaml
version: '3.8'
services:
  email-server:
    image: vdos-email:latest
    environment:
      - VDOS_DB_PATH=/data/vdos.db
    ports:
      - "8000:8000"
    volumes:
      - vdos-data:/data

  chat-server:
    image: vdos-chat:latest
    environment:
      - VDOS_DB_PATH=/data/vdos.db
    ports:
      - "8001:8001"
    volumes:
      - vdos-data:/data

  sim-manager:
    image: vdos-sim:latest
    environment:
      - VDOS_DB_PATH=/data/vdos.db
      - VDOS_EMAIL_BASE_URL=http://email-server:8000
      - VDOS_CHAT_BASE_URL=http://chat-server:8001
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - VDOS_PLANNER_PROJECT_MODEL=gpt-4.1-nano
    ports:
      - "8015:8015"
    volumes:
      - vdos-data:/data

volumes:
  vdos-data:
```

## Security Best Practices

1. **Never commit `.env` files** - Add to `.gitignore`
2. **Use secret management** - In production, use secure secret stores
3. **Rotate API keys** - Regularly rotate OpenAI API keys
4. **Limit permissions** - Use read-only API keys where possible
5. **Audit logs** - Monitor API usage and database access
