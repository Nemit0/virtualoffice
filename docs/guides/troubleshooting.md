# VDOS Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Virtual Department Operations Simulator.

## Table of Contents

- [Diagnostic Tools](#diagnostic-tools)
- [Common Issues](#common-issues)
- [Service Issues](#service-issues)
- [Simulation Issues](#simulation-issues)
- [Performance Issues](#performance-issues)
- [Getting Help](#getting-help)

## Diagnostic Tools

### Simulation Diagnostic Script

**Location**: `.tmp/diagnose_stuck_simulation.py`

A comprehensive diagnostic tool for troubleshooting simulation advancement issues.

### Full Simulation Test

**Location**: `.tmp/full_simulation_test.py`

Comprehensive integration test that validates the entire VDOS workflow from service initialization through tick advancement and auto-tick functionality.

```bash
python .tmp/full_simulation_test.py
```

This script performs a complete workflow test:
- **Phase 1**: Initialize services and create simulation engine
- **Phase 2**: Verify personas exist (requires at least 2 personas)
- **Phase 3**: Start simulation with test project
- **Phase 4**: Test manual tick advancement (5 ticks)
- **Phase 5**: Analyze performance metrics
- **Phase 6**: Test auto-tick functionality

**Use this when**:
- Validating a fresh VDOS installation
- Testing performance after configuration changes
- Verifying tick advancement works correctly
- Benchmarking simulation speed

**Expected results**:
- Manual advance: <20 seconds per tick
- Auto-tick: Should advance multiple ticks in 30 seconds
- No errors or timeouts during advancement

### 1-Week Simulation Test

**Location**: `.tmp/test_1week_simulation.py`

Comprehensive long-running test that simulates a full work week (5 days) with continuous auto-tick monitoring.

```bash
python .tmp/test_1week_simulation.py
```

This script performs an extended simulation test:
- **Configuration**: 480 ticks/day × 5 days = 2400 total ticks
- **Monitoring**: Progress checks every 60 seconds with detailed metrics
- **Safety Limits**: 1-hour maximum test duration
- **Performance Tracking**: Tick rates, ETA calculations, rate variation analysis
- **Optimized Settings**: Parallel planning (4 workers), Korean validation disabled, auto-pause disabled

**What It Tests**:
- Long-running simulation stability
- Auto-tick reliability over extended periods
- Performance consistency across multiple days
- Memory and resource management
- Auto-tick thread lifecycle

**Metrics Collected**:
- Overall tick advancement rate (ticks/second)
- Time per tick (seconds)
- Progress percentage and ETA
- Rate variation (min/max/average)
- Day and tick-of-day tracking

**Use this when**:
- Validating simulation stability for production use
- Testing performance under realistic workloads
- Verifying auto-tick doesn't degrade over time
- Benchmarking full-week simulation duration
- Stress-testing the simulation engine

**Expected results**:
- Completion: 2400 ticks in ~10 hours (at ~15s/tick)
- Stable performance: Consistent tick rates throughout
- No auto-tick failures or crashes
- Memory usage remains stable
- All communications generated correctly

**Success Criteria**:
- ✓ Completes full 2400 ticks (or reaches time limit)
- ✓ Average time per tick <20 seconds
- ✓ Auto-tick remains enabled throughout
- ✓ No errors or exceptions in logs

### Auto-Tick Thread Status Script

**Location**: `.tmp/check_thread_status.py`

Quick diagnostic tool to verify if the auto-tick thread is actually running and alive.

```bash
python .tmp/check_thread_status.py
```

This script checks if the auto-tick thread is created and remains alive after starting auto-tick. Useful for diagnosing thread creation or lifecycle issues.

**What It Checks**:
- Active threads before starting auto-tick
- Active threads after starting auto-tick
- Identifies auto-tick thread by name
- Verifies thread is alive and daemon status
- Monitors thread for 5 seconds to ensure it stays alive

**Use this when**:
- Auto-tick doesn't start at all
- Suspecting thread creation failures
- Need to verify thread lifecycle

### Auto-Tick Database Monitoring Script

**Location**: `.tmp/test_auto_tick_with_logging.py`

Specialized diagnostic tool for troubleshooting auto-tick issues by monitoring database state directly.

```bash
python .tmp/test_auto_tick_with_logging.py
```

This script monitors the auto-tick state directly from the database and detects if auto-tick gets disabled during execution. Useful when auto-tick appears to stop working unexpectedly.

**What It Checks**:
- Initial simulation state (tick, running, auto_tick)
- Database state after starting auto-tick
- Continuous monitoring for 15 seconds
- Detects if auto_tick flag gets disabled in database
- Compares engine state vs database state

**Use this when**:
- Auto-tick starts but stops advancing after a few ticks
- Suspecting auto-tick thread is crashing silently
- Need to verify database state matches engine state

### OpenAI API Test Script

**Location**: `.tmp/test_openai_api.py`

Quick test to verify OpenAI API connectivity and authentication.

```bash
python .tmp/test_openai_api.py
```

This script checks if your OpenAI API key is configured correctly and can make successful API calls. Useful when simulations hang during planning phases.

#### Usage

```bash
# Ensure VDOS dashboard is running first
briefcase dev

# In another terminal, run the diagnostic
python .tmp/diagnose_stuck_simulation.py
```

#### What It Checks

1. **Simulation State**
   - Current tick number
   - Running status (is_running)
   - Auto-tick status (auto_tick)
   - Simulation time

2. **Manual Advance Test**
   - Tests if `POST /api/v1/simulation/advance` works
   - Verifies the advance() method is functional
   - Shows emails/chats sent during advancement

3. **Auto-Tick Monitoring**
   - Monitors tick advancement for 10 seconds
   - Detects if auto-tick thread is working
   - Calculates ticks per second

#### Sample Output

```
╔====================================================================╗
║               VDOS SIMULATION DIAGNOSTIC TOOL                      ║
╚====================================================================╝

======================================================================
SIMULATION STATE
======================================================================
Current Tick: 1
Is Running: True
Auto Tick: True
Sim Time: Day 0, 09:00

======================================================================
TESTING MANUAL ADVANCE
======================================================================
✓ SUCCESS: Manual advance worked!
  Ticks advanced: 1
  Current tick: 2
  Emails sent: 0
  Chats sent: 0

CONCLUSION: Auto-tick thread is the problem, not the advance logic

======================================================================
MONITORING AUTO-TICK FOR 10 SECONDS
======================================================================
Initial tick: 2
Waiting 10 seconds...
Final tick: 12
Ticks advanced: 10

✓ Auto-tick is working!
```

#### Interpreting Results

**If manual advance works but auto-tick doesn't**:
- Auto-tick thread has crashed
- Check server logs for "Automatic tick failed" messages
- Look for exceptions in the auto-tick thread
- Restart the simulation

**If manual advance fails**:
- Check the error message for specific issue
- Common causes:
  - Missing project plan
  - No active personas
  - AI API key not configured
  - Database corruption

## Common Issues

### Simulation Stuck at Tick 1

**Symptoms**:
- Simulation starts successfully
- Tick counter shows 1 but doesn't advance
- Auto-tick is enabled but not working

**Diagnosis**:
```bash
python .tmp/diagnose_stuck_simulation.py
```

**Common Causes**:

1. **Auto-Tick Thread Crashed**
   - **Check**: Server logs for "Automatic tick failed"
   - **Solution**: Restart simulation from dashboard

2. **Missing Project Plan**
   - **Check**: `GET http://127.0.0.1:8015/api/v1/simulation`
   - **Solution**: Stop and restart simulation with project details

3. **No Active Personas**
   - **Check**: Persona list in dashboard
   - **Solution**: Create at least one persona before starting

4. **Planning Failures**
   - **Check**: Token usage and planner metrics
   - **Solution**: Verify `OPENAI_API_KEY` is set correctly

**Resolution Steps**:

1. Run diagnostic tool to identify specific issue
2. Check server logs in `virtualoffice.log`
3. Verify simulation state via API
4. Restart simulation if needed
5. If issue persists, check database integrity

### Service Connection Errors

**Symptoms**:
- "Connection refused" errors during startup
- Services fail to communicate
- Engine initialization fails

**Common Causes**:

1. **Services Starting Out of Order**
   - Email/Chat services not ready when Simulation starts
   - Race condition during concurrent startup

2. **Port Already in Use**
   - Another process using ports 8000, 8001, or 8015
   - Previous instance not fully terminated

**Solutions**:

1. **Use GUI Application** (Recommended)
   ```bash
   briefcase dev
   ```
   GUI manages service lifecycle automatically

2. **Manual Service Startup** (Development)
   ```bash
   # Start in sequence with delays
   # Terminal 1: Email
   uvicorn virtualoffice.servers.email:app --host 127.0.0.1 --port 8000
   
   # Wait 2 seconds, then Terminal 2: Chat
   uvicorn virtualoffice.servers.chat:app --host 127.0.0.1 --port 8001
   
   # Wait 2 seconds, then Terminal 3: Simulation
   uvicorn virtualoffice.sim_manager:create_app --host 127.0.0.1 --port 8015
   ```

3. **Check for Port Conflicts**
   ```bash
   # Windows
   netstat -ano | findstr :8000
   netstat -ano | findstr :8001
   netstat -ano | findstr :8015
   
   # Kill process if needed
   taskkill /PID <process_id> /F
   ```

### Database Issues

**Symptoms**:
- "Database is locked" errors
- Simulation state not persisting
- Missing data after restart

**Recent Improvements** (October 2025):
- WAL mode enabled for better concurrent access
- 30-second connection and busy timeouts
- Improved lock handling for multi-service scenarios

**Solutions**:

1. **Database Locked** (Rare after October 2025 improvements)
   - WAL mode should prevent most lock issues
   - If still occurring, close all connections to database
   - Restart all services
   - Check for zombie processes

2. **Corrupted Database**
   ```bash
   # Backup current database
   copy src\virtualoffice\vdos.db src\virtualoffice\vdos.db.backup
   
   # Delete and restart (loses all data)
   del src\virtualoffice\vdos.db
   briefcase dev
   ```

3. **Check Database Integrity**
   ```bash
   python .tmp/check_tables.py
   python .tmp/check_sim_state.py
   ```

4. **Verify WAL Mode** (if issues persist)
   ```bash
   # Check if WAL mode is active
   sqlite3 src\virtualoffice\vdos.db "PRAGMA journal_mode;"
   # Should return: wal
   ```

## Service Issues

### Email Service Not Responding

**Check Service Status**:
```bash
curl http://127.0.0.1:8000/mailboxes
```

**Common Issues**:
- Service not started
- Port 8000 in use
- Database connection failed

**Solutions**:
- Restart email service from dashboard
- Check logs for specific errors
- Verify database path is correct

### Chat Service Not Responding

**Check Service Status**:
```bash
curl http://127.0.0.1:8001/rooms
```

**Common Issues**:
- Service not started
- Port 8001 in use
- Database connection failed

**Solutions**:
- Restart chat service from dashboard
- Check logs for specific errors
- Verify database path is correct

### Simulation Service Not Responding

**Check Service Status**:
```bash
curl http://127.0.0.1:8015/api/v1/simulation
```

**Common Issues**:
- Service not started
- Port 8015 in use
- Email/Chat services not available

**Solutions**:
- Restart simulation service from dashboard
- Ensure Email and Chat services are running first
- Check logs for connection errors

## Simulation Issues

### No Communications Generated

**Symptoms**:
- Simulation advances but no emails/chats sent
- Workers have plans but don't communicate

**Diagnosis**:
```bash
# Check if communications are being scheduled
python .tmp/check_tick_log.py

# Check worker exchange log
python .tmp/check_sim_state.py
```

**Common Causes**:
1. **Cooldown Period Active**
   - Workers recently communicated
   - Waiting for cooldown to expire (default: 10 ticks)

2. **Deduplication Preventing Sends**
   - Same message already sent this tick
   - Check deduplication logic

3. **No Collaborators Selected**
   - Worker has no one to communicate with
   - Check team roster

**Solutions**:
- Wait for cooldown period to expire
- Verify team has multiple personas
- Check worker plans include communication steps

### Planning Failures

**Symptoms**:
- "Unable to generate plan" errors
- Stub plans being used instead of AI plans
- High token usage but poor quality plans

**Diagnosis**:
```bash
# Check planner metrics
curl http://127.0.0.1:8015/api/v1/planner/metrics
```

**Common Causes**:
1. **API Key Issues**
   - `OPENAI_API_KEY` not set
   - API key invalid or expired
   - Rate limit exceeded

2. **Model Configuration**
   - Invalid model name
   - Model not available

3. **Prompt Issues**
   - Context too large
   - Invalid template

**Solutions**:
1. **Verify API Key**
   ```bash
   # Check .env file
   type .env | findstr OPENAI_API_KEY
   ```

2. **Check Model Configuration**
   ```bash
   # Verify model names
   type .env | findstr VDOS_PLANNER
   ```

3. **Enable Strict Mode** (for debugging)
   ```bash
   # In .env
   VDOS_PLANNER_STRICT=1
   ```
   This disables fallback to stub planner, showing actual errors

### Auto-Pause Not Working

**Symptoms**:
- Simulation continues after all projects complete
- Auto-pause enabled but not triggering

**Diagnosis**:
```bash
# Check auto-pause status
curl http://127.0.0.1:8015/api/v1/simulation/auto-pause/status
```

**Common Causes**:
1. **Auto-Pause Disabled**
   - `VDOS_AUTO_PAUSE_ON_PROJECT_END=false`
   - Disabled via API

2. **Future Projects Exist**
   - Projects scheduled to start later
   - Auto-pause waits for all projects

3. **Project Timeline Issues**
   - Incorrect start_week or duration_weeks
   - Projects never marked as complete

**Solutions**:
1. **Enable Auto-Pause**
   ```bash
   curl -X POST http://127.0.0.1:8015/api/v1/simulation/auto-pause/toggle \
     -H "Content-Type: application/json" \
     -d '{"enabled": true}'
   ```

2. **Check Project Timelines**
   ```bash
   # View active projects
   curl http://127.0.0.1:8015/api/v1/simulation
   ```

## Performance Issues

### Slow Tick Advancement

**Symptoms**:
- Ticks take longer than expected
- Simulation feels sluggish

**Diagnosis**:
```bash
# Check tick interval
curl http://127.0.0.1:8015/api/v1/simulation
# Look for tick_interval_seconds
```

**Common Causes**:
1. **High Tick Interval**
   - `VDOS_TICK_MS` set too high
   - Tick interval increased via API

2. **Slow Planning**
   - AI API calls taking too long
   - Network latency

3. **Database Contention**
   - Many workers planning simultaneously
   - Database locked

**Solutions**:
1. **Adjust Tick Interval**
   ```bash
   # Set to 0 for maximum speed (no delay)
   curl -X POST http://127.0.0.1:8015/api/v1/simulation/tick-interval \
     -H "Content-Type: application/json" \
     -d '{"interval_seconds": 0}'
   ```

2. **Enable Parallel Planning**
   ```bash
   # In .env
   VDOS_MAX_PLANNING_WORKERS=4
   ```

3. **Use Stub Planner** (for testing)
   ```bash
   # In .env
   VDOS_PLANNER_STRICT=0
   # Stub planner will be used on failures
   ```

### High Memory Usage

**Symptoms**:
- Memory usage grows over time
- Application becomes unresponsive

**Diagnosis**:
```bash
# Monitor memory usage
# Use Task Manager (Windows) or Activity Monitor (macOS)
```

**Common Causes**:
1. **Message Accumulation**
   - Worker inboxes not being drained
   - Communication history growing

2. **Plan Storage**
   - Many hourly plans stored
   - Large plan content

3. **Memory Leak**
   - Objects not being garbage collected

**Solutions**:
1. **Limit Simulation Duration**
   - Use shorter simulations for testing
   - Clear database between runs

2. **Reduce Planning Frequency**
   ```bash
   # In .env
   VDOS_MAX_HOURLY_PLANS_PER_MINUTE=5
   ```

3. **Restart Services Periodically**
   - For long-running simulations
   - Clear accumulated state

## Getting Help

### Log Files

**Primary Log**:
- Location: `virtualoffice.log`
- Contains: All service logs with timestamps
- Format: Structured JSON entries

**GUI Error Log**:
- Location: `logs/error_output.txt`
- Contains: GUI-specific errors
- Format: Plain text

**Viewing Logs**:
```bash
# View recent logs
tail -n 100 virtualoffice.log

# Search for errors
findstr /i "error" virtualoffice.log
findstr /i "exception" virtualoffice.log
findstr /i "failed" virtualoffice.log
```

### Database Inspection

**Check Tables**:
```bash
python .tmp/check_tables.py
```

**Check Simulation State**:
```bash
python .tmp/check_sim_state.py
```

**Check Tick Log**:
```bash
python .tmp/check_tick_log.py
```

### Integration Testing

**Full Workflow Test**:
```bash
python .tmp/full_simulation_test.py
```

Runs a complete end-to-end test of the simulation workflow including performance benchmarking.

### API Debugging

**Check Simulation State**:
```bash
curl http://127.0.0.1:8015/api/v1/simulation
```

**Check Personas**:
```bash
curl http://127.0.0.1:8015/api/v1/people
```

**Check Planner Metrics**:
```bash
curl http://127.0.0.1:8015/api/v1/planner/metrics
```

**Manual Tick Advance**:
```bash
curl -X POST http://127.0.0.1:8015/api/v1/simulation/advance \
  -H "Content-Type: application/json" \
  -d '{"ticks": 1, "reason": "debug test"}'
```

### Reporting Issues

When reporting issues, include:

1. **System Information**
   - Operating system and version
   - Python version
   - VDOS version

2. **Error Details**
   - Full error message
   - Stack trace if available
   - Steps to reproduce

3. **Diagnostic Output**
   - Output from diagnostic script
   - Relevant log entries
   - API responses

4. **Configuration**
   - Environment variables (redact API keys)
   - Simulation parameters
   - Number of personas

5. **Context**
   - What were you trying to do?
   - When did the issue start?
   - Does it happen consistently?

### Additional Resources

- **Architecture Documentation**: `docs/architecture.md`
- **API Documentation**: `docs/api/`
- **Agent Reports**: `agent_reports/` (implementation details)
- **Testing Guide**: `docs/workflows/testing.md`
- **GitHub Issues**: Report bugs and request features

## Quick Reference

### Restart Everything
```bash
# Stop all services
# Close GUI application

# Delete database (optional, loses all data)
del src\virtualoffice\vdos.db

# Start fresh
briefcase dev
```

### Reset Simulation
```bash
# Via API
curl -X POST http://127.0.0.1:8015/api/v1/simulation/stop

# Delete database
del src\virtualoffice\vdos.db

# Restart services
briefcase dev
```

### Check Service Health
```bash
# Email service
curl http://127.0.0.1:8000/mailboxes

# Chat service
curl http://127.0.0.1:8001/rooms

# Simulation service
curl http://127.0.0.1:8015/api/v1/simulation
```

### Common Environment Variables
```bash
# In .env file

# API Configuration
OPENAI_API_KEY=sk-...

# Service Ports
VDOS_EMAIL_PORT=8000
VDOS_CHAT_PORT=8001
VDOS_SIM_PORT=8015

# Simulation Configuration
VDOS_TICK_MS=50
VDOS_BUSINESS_DAYS=5
VDOS_LOCALE=en

# Performance Tuning
VDOS_MAX_PLANNING_WORKERS=4
VDOS_MAX_HOURLY_PLANS_PER_MINUTE=10
VDOS_CONTACT_COOLDOWN_TICKS=10

# Features
VDOS_AUTO_PAUSE_ON_PROJECT_END=true
VDOS_PLANNER_STRICT=0
```
