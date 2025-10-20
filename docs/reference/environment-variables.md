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

## Simulation Configuration

### VDOS_TICKS_PER_DAY
- **Default**: `480`
- **Description**: Number of ticks (minutes) in a simulated workday
- **Example**: `VDOS_TICKS_PER_DAY=480`
- **Notes**: 480 ticks = 8 hours; adjust for different workday lengths

### VDOS_TICK_INTERVAL_SECONDS
- **Default**: `1.0`
- **Description**: Seconds between auto-ticks when enabled
- **Example**: `VDOS_TICK_INTERVAL_SECONDS=0.5`
- **Notes**: Lower values run simulation faster but use more CPU

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

## Localization

### VDOS_LOCALE
- **Default**: `en`
- **Description**: Locale for generated content
- **Values**: `en` (English), `ko` (Korean)
- **Example**: `VDOS_LOCALE=ko`
- **Notes**: Affects planner prompts and generated text

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

## GUI Configuration

### VDOS_GUI_AUTOKILL_SECONDS
- **Default**: None (disabled)
- **Description**: Auto-shutdown GUI after N seconds (testing only)
- **Example**: `VDOS_GUI_AUTOKILL_SECONDS=300`
- **Notes**: Used for automated GUI testing; leave unset in normal use

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
