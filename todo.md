# VDOS Project TODO

## Current Tasks

### Email Threading Implementation ✅
- [x] Add reply syntax support to planner prompt
- [x] Add reply parsing to scheduled comms parser
- [x] Add email tracking per person (inbox/sent)
- [x] Implement thread_id lookup and assignment
- [x] Test threading implementation
- [x] Fix test script field name bug (from → sender)

**Status**: Complete. Email threading with reply syntax is fully implemented and tested.

---

## Future Enhancements

### High Priority
- [ ] Email threading validation - verify threads work correctly in multi-project simulations
- [ ] GPT call logging - track API costs and performance in simulation outputs
- [ ] External stakeholders testing - test with mock client email addresses

### Medium Priority
- [ ] Email threading UI - enhance conversation view in existing dashboard
- [ ] Group chat channels - add project-specific channels (currently only DMs)
- [ ] Content length variation - reduce template patterns in planner outputs

### Low Priority
- [ ] Documentation - update user guide with threading feature
- [ ] Performance optimization - profile long-running simulations
- [ ] Extended simulation testing - 12-week stability test

---

## Completed

### 2025-10-20 (Session 1)
- ✅ Email threading implementation (Method 3: Explicit Reply Syntax)
  - Thread ID generation and assignment
  - Recent emails context for planner
  - Reply syntax parsing and handling
  - Test script with threading analysis
- ✅ Token usage optimization (Hierarchical Summarization)
  - Created `hourly_summaries` table in database
  - Implemented hourly summary generation (2-3 bullet points per hour)
  - Updated daily reports to use hourly summaries instead of all tick logs (~95% token reduction)
  - Updated simulation reports to use sampled data (~98% token reduction)
  - Auto-generate summaries at end of each hour
  - Prevents context length errors in long simulations

### 2025-10-20 (Session 2 - Continued)
- ✅ Token optimization bug fix (Daily Report Context Length)
  - **Issue Found**: 8-week simulation still hit 163K token limit (exceeding 128K)
  - **Root Cause**: `minute_schedule` (32 entries/day) still included in daily report prompt
  - **Fix**: Removed minute_schedule from `generate_daily_report()` in planner.py
  - **Result**: Daily reports now only use hourly summaries (expected <10K tokens vs 163K)
  - Completes the full hierarchical summarization chain: Tick → Hour → Day → Simulation
- ✅ Project organization cleanup
  - Created `agent_reports/` directory
  - Created `scripts/` directory
  - Added timestamp prefixes to all reports
  - Created `todo.md` for persistent task tracking
  - Updated `CLAUDE.md` with task tracking guidelines
- ✅ Simulation output timestamping
  - Added datetime to all simulation output directories
- ✅ 8-week multi-project simulation
  - 100% clean email validation (0 hallucinations)
  - Korean language support
  - Multi-project context switching

---

## Notes

- All agent reports should be saved to `agent_reports/` with timestamp prefix
- All simulation scripts should be in `scripts/` directory
- Use OpenAI key 1 for all simulations (per company policy)
- Korean locale requires Korean names in personas
