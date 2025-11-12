# Communication Diversity & Conversational Realism — Troubleshooting Guide

**Date:** 2025-11-05  
**Related Spec:** `.kiro/specs/communication-diversity/`  
**Related Modules:** `communication_generator.md`, `inbox_manager.md`, `participation_balancer.md`

---

## Table of Contents

1. [Common Issues and Solutions](#common-issues-and-solutions)
2. [Rollback Procedures](#rollback-procedures)
3. [Debugging Tips](#debugging-tips)
4. [FAQ](#faq)
5. [Performance Issues](#performance-issues)
6. [Quality Issues](#quality-issues)
7. [Getting Help](#getting-help)

---

## Common Issues and Solutions

### Issue 1: GPT Fallback Not Generating Communications

**Symptoms:**
- Messages still look like templates (repetitive subjects)
- No diverse communications appearing
- Quality metrics show low diversity scores

**Possible Causes & Solutions:**

**Cause 1: Feature disabled**
```bash
# Check your .env file
cat .env | grep VDOS_GPT_FALLBACK_ENABLED

# Solution: Enable the feature
VDOS_GPT_FALLBACK_ENABLED=true
```

**Cause 2: Missing OpenAI API key**
```bash
# Check if API key is set
echo $OPENAI_API_KEY

# Solution: Set your API key
export OPENAI_API_KEY=sk-...
# Or add to .env file
echo "OPENAI_API_KEY=sk-..." >> .env
```

**Cause 3: Hourly plans include JSON communications**
- GPT fallback only triggers when JSON communications are absent
- Check hourly plans in database or logs
- Solution: This is expected behavior - JSON communications take priority

**Cause 4: Participation balancing throttling**
- High-volume senders may be throttled
- Check logs for "throttling" messages
- Solution: Adjust `VDOS_PARTICIPATION_BALANCE_ENABLED` or `VDOS_FALLBACK_PROBABILITY`

**Verification:**
```bash
# Check logs for GPT fallback calls
grep "GPT fallback" logs/virtualoffice.log

# Check quality metrics
curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics
```

---

### Issue 2: API Rate Limits or Errors

**Symptoms:**
- Error messages about rate limits
- 429 HTTP errors in logs
- Communications failing to generate

**Solutions:**

**Solution 1: Reduce fallback probability**
```bash
# Lower the probability to reduce API calls
VDOS_FALLBACK_PROBABILITY=0.4  # Down from 0.6
```

**Solution 2: Add retry logic (already implemented)**
- The system automatically retries failed API calls
- Check logs for retry attempts

**Solution 3: Switch to different API key**
```bash
# Use secondary OpenAI key if available
OPENAI_API_KEY=$OPENAI_API_KEY2
```

**Solution 4: Temporarily disable GPT fallback**
```bash
# Disable during rate limit period
VDOS_GPT_FALLBACK_ENABLED=false

# Re-enable after rate limit resets
VDOS_GPT_FALLBACK_ENABLED=true
```

**Verification:**
```bash
# Check API error rate
grep "API error" logs/virtualoffice.log | wc -l

# Monitor rate limit headers
curl -I https://api.openai.com/v1/models
```

---

### Issue 3: Threading Not Working

**Symptoms:**
- Threading rate remains low (<10%)
- No "RE:" subjects appearing
- Quality metrics show poor threading

**Possible Causes & Solutions:**

**Cause 1: Threading rate set too low**
```bash
# Check current setting
cat .env | grep VDOS_THREADING_RATE

# Solution: Increase threading rate
VDOS_THREADING_RATE=0.4  # Up from 0.3
```

**Cause 2: Inbox not tracking messages**
```bash
# Check inbox_messages table
sqlite3 src/virtualoffice/vdos.db "SELECT COUNT(*) FROM inbox_messages;"

# If empty, check if messages are being delivered
sqlite3 src/virtualoffice/vdos.db "SELECT COUNT(*) FROM emails;"
```

**Cause 3: Personas not receiving messages**
- Check if personas are actually receiving emails
- Verify email routing in logs

**Solution: Enable debug logging**
```bash
# Add to .env
VDOS_LOG_LEVEL=DEBUG

# Check inbox tracking logs
grep "add_to_inbox" logs/virtualoffice.log
```

**Verification:**
```bash
# Check threading rate
curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics | jq '.threading_rate'

# Check inbox messages
sqlite3 src/virtualoffice/vdos.db "SELECT person_id, COUNT(*) FROM inbox_messages GROUP BY person_id;"
```

---

### Issue 4: Participation Still Imbalanced

**Symptoms:**
- Top 2 senders still dominate (>50% of messages)
- Some personas send very few messages
- Participation Gini coefficient high (>0.4)

**Possible Causes & Solutions:**

**Cause 1: Balancing disabled**
```bash
# Check setting
cat .env | grep VDOS_PARTICIPATION_BALANCE_ENABLED

# Solution: Enable balancing
VDOS_PARTICIPATION_BALANCE_ENABLED=true
```

**Cause 2: Balancing not aggressive enough**
```bash
# Solution: Lower base probability
VDOS_FALLBACK_PROBABILITY=0.5  # Down from 0.6

# This makes throttling more effective
```

**Cause 3: JSON communications bypassing balancing**
- JSON communications from hourly plans are never throttled
- If most communications are JSON, balancing has limited effect
- Solution: This is expected behavior

**Verification:**
```bash
# Check participation stats
sqlite3 src/virtualoffice/vdos.db "
SELECT person_id, SUM(total_count) as total 
FROM participation_stats 
GROUP BY person_id 
ORDER BY total DESC;
"

# Check Gini coefficient
curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics | jq '.participation_gini'
```

---

### Issue 5: Poor Message Quality

**Symptoms:**
- Messages don't make sense
- Wrong role language (developer using design terms)
- Missing project context
- Generic or vague content

**Possible Causes & Solutions:**

**Cause 1: Using wrong model**
```bash
# Check current model
cat .env | grep VDOS_FALLBACK_MODEL

# Solution: Upgrade to GPT-4o for better quality
VDOS_FALLBACK_MODEL=gpt-4o  # Instead of gpt-4o-mini
```

**Cause 2: Insufficient context in hourly plans**
- GPT extracts context from hourly plans
- If plans are vague, messages will be vague
- Solution: Improve hourly plan quality (adjust planner prompts)

**Cause 3: Wrong locale**
```bash
# Check locale setting
cat .env | grep VDOS_LOCALE

# Solution: Set correct locale
VDOS_LOCALE=ko  # For Korean
VDOS_LOCALE=en  # For English
```

**Verification:**
```bash
# Sample recent messages
sqlite3 src/virtualoffice/vdos.db "
SELECT subject, body FROM emails 
ORDER BY created_at DESC LIMIT 5;
"

# Run quality validation
python .tmp/test_quality_validation_gpt.py
```

---

### Issue 6: High Costs

**Symptoms:**
- OpenAI bill higher than expected
- Too many API calls
- Budget concerns

**Solutions:**

**Solution 1: Use GPT-4o-mini**
```bash
# Switch to cheaper model (10x cost reduction)
VDOS_FALLBACK_MODEL=gpt-4o-mini
```

**Solution 2: Reduce fallback probability**
```bash
# Generate fewer fallback communications
VDOS_FALLBACK_PROBABILITY=0.4  # Down from 0.6
```

**Solution 3: Increase JSON communication rate**
- Improve planner prompts to include more JSON communications
- JSON communications bypass GPT fallback (no cost)

**Solution 4: Disable for development**
```bash
# Disable during development/testing
VDOS_GPT_FALLBACK_ENABLED=false

# Re-enable for production runs
VDOS_GPT_FALLBACK_ENABLED=true
```

**Cost Monitoring:**
```bash
# Track API calls
grep "GPT fallback" logs/virtualoffice.log | wc -l

# Estimate cost (GPT-4o-mini)
# calls × $0.00024 = total cost
```

---

## Rollback Procedures

### Rollback 1: Disable All Communication Diversity Features

Complete rollback to template-based generation:

```bash
# 1. Update .env file
VDOS_GPT_FALLBACK_ENABLED=false
VDOS_THREADING_RATE=0.0
VDOS_PARTICIPATION_BALANCE_ENABLED=false

# 2. Restart simulation services
# If using briefcase dev:
# Stop and restart the application

# If using manual services:
pkill -f "uvicorn virtualoffice.sim_manager"
uvicorn virtualoffice.sim_manager:create_app --host 127.0.0.1 --port 8015 --reload

# 3. Verify rollback
curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics
# Should show json_vs_fallback_ratio = 1.0 (all JSON or templates)
```

**Expected behavior after rollback:**
- No GPT API calls for fallback communications
- Simple template-based messages
- No threading or participation balancing
- Lower quality but faster and cheaper

---

### Rollback 2: Partial Rollback (Keep Some Features)

Keep threading but disable GPT fallback:

```bash
# Keep threading and balancing, disable GPT
VDOS_GPT_FALLBACK_ENABLED=false
VDOS_THREADING_RATE=0.3
VDOS_PARTICIPATION_BALANCE_ENABLED=true

# Restart services
```

**Use case:** Want threading benefits without API costs

---

### Rollback 3: Database Rollback

If database tables cause issues:

```bash
# 1. Backup current database
cp src/virtualoffice/vdos.db src/virtualoffice/vdos.db.backup

# 2. Drop optional tables (if needed)
sqlite3 src/virtualoffice/vdos.db "
DROP TABLE IF EXISTS inbox_messages;
DROP TABLE IF EXISTS participation_stats;
DROP TABLE IF EXISTS communication_generation_log;
"

# 3. Restart services
# Tables will be recreated automatically if features are enabled
```

**Warning:** This will lose inbox and participation history

---

### Rollback 4: Code Rollback

If code changes cause issues:

```bash
# 1. Check git status
git status

# 2. Revert specific files
git checkout HEAD -- src/virtualoffice/sim_manager/communication_generator.py
git checkout HEAD -- src/virtualoffice/sim_manager/inbox_manager.py
git checkout HEAD -- src/virtualoffice/sim_manager/participation_balancer.py

# 3. Or revert entire commit
git log --oneline  # Find commit hash
git revert <commit-hash>

# 4. Restart services
```

---

## Debugging Tips

### Tip 1: Enable Debug Logging

Get detailed information about communication generation:

```bash
# Add to .env
VDOS_LOG_LEVEL=DEBUG

# Restart services

# Watch logs in real-time
tail -f logs/virtualoffice.log | grep -E "(GPT fallback|inbox|participation)"
```

**What to look for:**
- "GPT fallback call" - Confirms GPT is being invoked
- "add_to_inbox" - Confirms inbox tracking
- "throttling" or "boosting" - Confirms participation balancing
- "thread_id" - Confirms threading

---

### Tip 2: Inspect Database State

Check database tables directly:

```bash
# Open database
sqlite3 src/virtualoffice/vdos.db

# Check inbox messages
SELECT person_id, COUNT(*) as inbox_count, 
       SUM(needs_reply) as needs_reply_count
FROM inbox_messages 
GROUP BY person_id;

# Check participation stats
SELECT person_id, day_index, total_count, probability_modifier
FROM participation_stats
ORDER BY day_index, total_count DESC;

# Check communication generation log
SELECT generation_type, COUNT(*) as count, 
       AVG(token_count) as avg_tokens,
       AVG(latency_ms) as avg_latency
FROM communication_generation_log
GROUP BY generation_type;

# Exit
.quit
```

---

### Tip 3: Test Individual Components

Test components in isolation:

```python
# Test CommunicationGenerator
from virtualoffice.sim_manager.communication_generator import CommunicationGenerator
from virtualoffice.sim_manager.planner import GPTPlanner

planner = GPTPlanner(locale='ko')
generator = CommunicationGenerator(planner=planner, locale='ko', random_seed=42)

# Test with mock context
context = {
    'person': mock_person,
    'hourly_plan': "API 엔드포인트 구현 중...",
    'project': {'name': 'MobileApp'},
    'inbox': [],
    'collaborators': []
}

comms = generator.generate_fallback_communications(context)
print(comms)
```

```python
# Test InboxManager
from virtualoffice.sim_manager.inbox_manager import InboxManager, InboxMessage

manager = InboxManager()

# Add test message
msg = InboxMessage(
    message_id=1,
    sender_id=2,
    sender_name="Test Sender",
    subject="Test Subject",
    body="Test body",
    thread_id=None,
    received_tick=100,
    needs_reply=True,
    message_type="question"
)

manager.add_message(person_id=1, message=msg)
inbox = manager.get_inbox(person_id=1)
print(f"Inbox size: {len(inbox)}")
```

```python
# Test ParticipationBalancer
from virtualoffice.sim_manager.participation_balancer import ParticipationBalancer
import random

balancer = ParticipationBalancer(enabled=True)

# Simulate high volume sender
for _ in range(20):
    balancer.record_message(person_id=1, day_index=0, channel='email')

# Check if throttled
rng = random.Random(42)
should_send = balancer.should_generate_fallback(
    person_id=1, 
    day_index=0, 
    team_size=10,
    random=rng
)
print(f"Should send: {should_send}")  # Should be False or low probability
```

---

### Tip 4: Compare Before/After

Run simulations with features on/off to compare:

```bash
# Run with features disabled
VDOS_GPT_FALLBACK_ENABLED=false python scripts/test_multiteam_2week.py
mv simulation_output/latest simulation_output/without_diversity

# Run with features enabled
VDOS_GPT_FALLBACK_ENABLED=true python scripts/test_multiteam_2week.py
mv simulation_output/latest simulation_output/with_diversity

# Compare results
diff -r simulation_output/without_diversity simulation_output/with_diversity
```

---

### Tip 5: Monitor API Calls

Track OpenAI API usage:

```bash
# Count API calls in logs
grep "GPT fallback call" logs/virtualoffice.log | wc -l

# Check token usage
grep "token_count" logs/virtualoffice.log | \
  awk '{sum+=$NF} END {print "Total tokens:", sum}'

# Estimate cost
# tokens × $0.00015 per 1K input tokens (GPT-4o-mini)
# tokens × $0.0006 per 1K output tokens (GPT-4o-mini)
```

---

## FAQ

### Q1: Why are my messages still repetitive?

**A:** Check these in order:
1. Is `VDOS_GPT_FALLBACK_ENABLED=true`?
2. Is `OPENAI_API_KEY` set correctly?
3. Are hourly plans including JSON communications? (JSON bypasses GPT fallback)
4. Check logs for "GPT fallback call" messages
5. Verify quality metrics show `json_vs_fallback_ratio < 1.0`

---

### Q2: How do I know if GPT fallback is working?

**A:** Multiple ways to verify:
1. Check logs: `grep "GPT fallback" logs/virtualoffice.log`
2. Check quality metrics: `curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics`
3. Check database: `SELECT COUNT(*) FROM communication_generation_log WHERE generation_type='gpt_fallback';`
4. Inspect messages: Look for diverse subjects and role-appropriate language

---

### Q3: Can I use this without OpenAI API?

**A:** No, GPT fallback requires OpenAI API access. However, you can:
- Disable GPT fallback: `VDOS_GPT_FALLBACK_ENABLED=false`
- Use JSON communications in hourly plans (no API calls needed)
- Use template-based generation (legacy behavior)

---

### Q4: How much does this cost?

**A:** Costs depend on simulation size and model:

**GPT-4o-mini (recommended):**
- ~$0.00024 per fallback communication
- 5-day, 5-persona simulation: ~$0.06
- 20-day, 10-persona simulation: ~$0.48

**GPT-4o (higher quality):**
- ~$0.0024 per fallback communication (10x more)
- 5-day, 5-persona simulation: ~$0.60
- 20-day, 10-persona simulation: ~$4.80

See [Usage Examples](./communication_diversity_examples.md#cost-and-performance-examples) for detailed calculations.

---

### Q5: Why is threading rate still low?

**A:** Common reasons:
1. `VDOS_THREADING_RATE` set too low (increase to 0.4-0.5)
2. Not enough emails being sent (increase `VDOS_FALLBACK_PROBABILITY`)
3. Personas not receiving emails (check email routing)
4. Inbox not tracking messages (check `inbox_messages` table)

---

### Q6: Can I customize the prompts?

**A:** Yes! Prompts are in `src/virtualoffice/sim_manager/communication_generator.py`:
- Edit `_build_korean_prompt()` for Korean prompts
- Edit `_build_english_prompt()` for English prompts (if implemented)
- Restart services after changes

---

### Q7: How do I disable just threading?

**A:**
```bash
VDOS_THREADING_RATE=0.0
```

This keeps GPT fallback and participation balancing but disables email threading.

---

### Q8: What if I get JSON parsing errors?

**A:** The system handles this gracefully:
1. Logs warning: "Failed to parse GPT response"
2. Falls back to empty communications list
3. Simulation continues normally

To debug:
```bash
# Check for parsing errors
grep "Failed to parse" logs/virtualoffice.log

# Enable debug logging to see raw responses
VDOS_LOG_LEVEL=DEBUG
```

---

### Q9: Can I use this with Azure OpenAI?

**A:** Currently, the system uses OpenAI API directly. Azure OpenAI support would require:
1. Modifying `communication_generator.py` to support Azure endpoints
2. Adding Azure-specific configuration
3. Testing with Azure API

This is not currently implemented but could be added as an enhancement.

---

### Q10: How do I reset everything?

**A:** Complete reset:
```bash
# 1. Stop all services
pkill -f "uvicorn virtualoffice"

# 2. Backup and delete database
mv src/virtualoffice/vdos.db src/virtualoffice/vdos.db.backup
rm src/virtualoffice/vdos.db

# 3. Reset configuration
cp .env.template .env
# Edit .env with your settings

# 4. Restart services
briefcase dev
```

---

## Performance Issues

### Issue: Simulation Running Slowly

**Symptoms:**
- Tick advancement takes >100ms
- Simulation feels sluggish
- High CPU usage

**Solutions:**

1. **Use GPT-4o-mini instead of GPT-4o**
   ```bash
   VDOS_FALLBACK_MODEL=gpt-4o-mini
   ```

2. **Reduce fallback probability**
   ```bash
   VDOS_FALLBACK_PROBABILITY=0.4
   ```

3. **Increase tick speed**
   ```bash
   VDOS_TICK_MS=25  # Faster wall-clock time
   ```

4. **Profile the simulation**
   ```python
   import cProfile
   cProfile.run('engine.advance(100, "test")', 'profile.stats')
   
   import pstats
   p = pstats.Stats('profile.stats')
   p.sort_stats('cumulative').print_stats(20)
   ```

---

### Issue: High Memory Usage

**Symptoms:**
- Memory usage growing over time
- System running out of RAM
- Slow performance after long runs

**Solutions:**

1. **Limit inbox size** (already implemented - 20 messages max)

2. **Clear old participation stats**
   ```sql
   DELETE FROM participation_stats WHERE day_index < (SELECT MAX(day_index) - 7 FROM participation_stats);
   ```

3. **Disable optional persistence**
   ```bash
   VDOS_INBOX_PERSIST=false
   VDOS_PARTICIPATION_PERSIST=false
   ```

4. **Monitor memory**
   ```python
   import psutil
   import os
   
   process = psutil.Process(os.getpid())
   print(f"Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB")
   ```

---

## Quality Issues

### Issue: Messages Don't Sound Natural

**Solutions:**

1. **Upgrade to GPT-4o**
   ```bash
   VDOS_FALLBACK_MODEL=gpt-4o
   ```

2. **Enable style filter**
   ```bash
   VDOS_STYLE_FILTER_ENABLED=true
   ```

3. **Improve hourly plan quality**
   - Adjust planner prompts
   - Include more specific work details
   - Add project context

4. **Check locale setting**
   ```bash
   VDOS_LOCALE=ko  # For Korean
   ```

---

### Issue: Wrong Role Language

**Symptoms:**
- Developers using design terms
- Designers using technical terms
- Generic language across all roles

**Solutions:**

1. **Verify persona roles are set correctly**
   ```sql
   SELECT id, name, role FROM people;
   ```

2. **Check role vocabulary in code**
   - Edit `communication_generator.py`
   - Verify role-specific terms are correct

3. **Improve context extraction**
   - Ensure hourly plans include role-specific work
   - Add more role-specific keywords

---

## Getting Help

### Support Resources

1. **Documentation:**
   - [Communication Generator Module](../modules/communication_generator.md)
   - [Inbox Manager Module](../modules/inbox_manager.md)
   - [Participation Balancer Module](../modules/participation_balancer.md)
   - [Usage Examples](./communication_diversity_examples.md)

2. **Logs:**
   - `logs/virtualoffice.log` - Main application log
   - `logs/error_output.txt` - Error output

3. **Database:**
   - `src/virtualoffice/vdos.db` - SQLite database
   - Use `sqlite3` to inspect tables

4. **Code:**
   - `src/virtualoffice/sim_manager/communication_generator.py`
   - `src/virtualoffice/sim_manager/inbox_manager.py`
   - `src/virtualoffice/sim_manager/participation_balancer.py`

### Reporting Issues

When reporting issues, include:

1. **Configuration:**
   ```bash
   cat .env | grep VDOS_
   ```

2. **Logs:**
   ```bash
   tail -100 logs/virtualoffice.log
   ```

3. **Quality Metrics:**
   ```bash
   curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics
   ```

4. **Database Stats:**
   ```sql
   SELECT 
     (SELECT COUNT(*) FROM emails) as email_count,
     (SELECT COUNT(*) FROM inbox_messages) as inbox_count,
     (SELECT COUNT(*) FROM participation_stats) as participation_count,
     (SELECT COUNT(*) FROM communication_generation_log) as generation_log_count;
   ```

5. **System Info:**
   ```bash
   python --version
   pip list | grep -E "(openai|httpx|fastapi)"
   ```

---

## Summary

This troubleshooting guide covers:
- ✅ Common issues and solutions
- ✅ Rollback procedures for safe recovery
- ✅ Debugging tips for investigation
- ✅ FAQ for quick answers
- ✅ Performance optimization
- ✅ Quality improvement
- ✅ Support resources

**Quick Troubleshooting Checklist:**
1. ✅ Is `VDOS_GPT_FALLBACK_ENABLED=true`?
2. ✅ Is `OPENAI_API_KEY` set?
3. ✅ Check logs for errors
4. ✅ Verify quality metrics
5. ✅ Inspect database tables
6. ✅ Test individual components
7. ✅ Compare with/without features

**Emergency Rollback:**
```bash
VDOS_GPT_FALLBACK_ENABLED=false
VDOS_THREADING_RATE=0.0
VDOS_PARTICIPATION_BALANCE_ENABLED=false
# Restart services
```

For additional help, refer to the module documentation and usage examples.
