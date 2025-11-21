# VDOS Project TODO

**Last Updated:** 2025-10-27
**Current Focus:** Engine Refactoring - Phase 1 (Core Module Extraction)

---

## 🚀 ACTIVE: Engine Refactoring Project

**Goal:** Refactor monolithic engine into modular, maintainable architecture
**Timeline:** 10 weeks (5 phases)
**Reference:** See `agent_reports/20251027_151949_plan_and_design.md`

### Phase 1: Core Module Extraction (Weeks 1-2) - IN PROGRESS

**Goal:** Extract simulation_state.py, tick_manager.py, and event_system.py

#### Step 1.1: Create Module Structure ✅ COMPLETED
- [x] Create `src/virtualoffice/sim_manager/core/` directory
- [x] Create `core/__init__.py` with module exports
- [x] Set up testing infrastructure (`tests/core/`)
- [x] Create `tests/core/__init__.py`

#### Step 1.2: Extract SimulationState ✅ COMPLETED
- [x] Create `core/simulation_state.py`
- [x] Move database schema constants (SIM_SCHEMA)
- [x] Move `_ensure_state_row()` method
- [x] Move `_fetch_state()` method
- [x] Move `_apply_migrations()` method
- [x] Move status override methods
- [x] Add `SimulationState` class with clean interface
- [x] Create `tests/core/test_simulation_state.py`
- [x] Write comprehensive tests (state, migrations, overrides)
- [x] Update `engine.py` to use `SimulationState`
- [x] Run full test suite and verify passing (16/16 core tests passing)
- [ ] Commit changes: "refactor: extract SimulationState module"

#### Step 1.3: Extract TickManager - IN PROGRESS
- [x] Create `core/tick_manager.py`
- [x] Move `_format_sim_time()` method
- [x] Move `_sim_datetime_for_tick()` method
- [x] Move `_parse_work_hours_to_ticks()` method
- [x] Move `_is_within_work_hours()` method
- [x] Move `_update_work_windows()` method
- [x] Move auto-tick threading logic
- [x] Add `TickManager` class with clean interface
- [x] Create `tests/core/test_tick_manager.py`
- [x] Write comprehensive tests (time parsing, work hours, auto-tick)
- [x] Update `engine.py` to use `TickManager` (mostly complete)
- [ ] Run full test suite and verify passing
- [ ] Commit changes: "refactor: extract TickManager module"

#### Step 1.4: Extract EventSystem
- [ ] Create `core/event_system.py`
- [ ] Move `inject_event()` method
- [ ] Move event processing logic
- [ ] Move random event generation
- [ ] Move event-to-adjustment conversion
- [ ] Add `EventSystem` class with clean interface
- [ ] Create `tests/core/test_event_system.py`
- [ ] Write comprehensive tests (injection, processing, random events)
- [ ] Update `engine.py` to use `EventSystem`
- [ ] Run full test suite and verify passing
- [ ] Commit changes: "refactor: extract EventSystem module"

**Phase 1 Deliverables:**
- [ ] 3 new core modules with tests
- [ ] Engine.py reduced by ~500 lines
- [ ] All existing tests passing
- [ ] Code coverage maintained at >90%

---

### Phase 2: Communication and Worker Modules (Weeks 3-4) - TODO

**Goal:** Extract communication_hub.py, worker_runtime.py, project_manager.py

#### Step 2.1: Extract CommunicationHub
- [ ] Create `core/communication_hub.py`
- [ ] Move `_schedule_from_hourly_plan()` method
- [ ] Move `_dispatch_scheduled()` method
- [ ] Move `_can_send()` method
- [ ] Move `_reset_tick_sends()` method
- [ ] Move email threading logic
- [ ] Move deduplication/cooldown logic
- [ ] Add `CommunicationHub` class with clean interface
- [ ] Create `tests/core/test_communication_hub.py`
- [ ] Write comprehensive tests (parsing, dispatch, dedup, threading)
- [ ] Update `engine.py` to use `CommunicationHub`
- [ ] Run full test suite and verify passing
- [ ] Commit changes: "refactor: extract CommunicationHub module"

#### Step 2.2: Extract WorkerRuntime
- [ ] Create `core/worker_runtime.py`
- [ ] Move `_InboundMessage` class
- [ ] Move `_WorkerRuntime` class
- [ ] Create `WorkerRuntimeManager` class
- [ ] Move `_sync_worker_runtimes()` method
- [ ] Move `_get_worker_runtime()` method
- [ ] Add comprehensive interface
- [ ] Create `tests/core/test_worker_runtime.py`
- [ ] Write comprehensive tests (queuing, draining, syncing)
- [ ] Update `engine.py` to use `WorkerRuntimeManager`
- [ ] Run full test suite and verify passing
- [ ] Commit changes: "refactor: extract WorkerRuntime module"

#### Step 2.3: Extract ProjectManager
- [ ] Create `core/project_manager.py`
- [ ] Move `get_project_plan()` method
- [ ] Move `get_active_projects_with_assignments()` method
- [ ] Move `_get_active_project_for_person()` method
- [ ] Move `_get_all_active_projects_for_person()` method
- [ ] Move `_store_project_plan()` method
- [ ] Move chat room management methods
- [ ] Add `ProjectManager` class with clean interface
- [ ] Create `tests/core/test_project_manager.py`
- [ ] Write comprehensive tests (projects, assignments, chat rooms)
- [ ] Update `engine.py` to use `ProjectManager`
- [ ] Run full test suite and verify passing
- [ ] Commit changes: "refactor: extract ProjectManager module"

**Phase 2 Deliverables:**
- [ ] 3 more core modules with tests
- [ ] Engine.py reduced by ~800 more lines (now ~1000 lines total)
- [ ] All communication logic centralized
- [ ] Worker runtime logic isolated

---

### Phase 3: Prompt Management System (Weeks 5-6) - TODO

**Goal:** Create centralized prompt template system

#### Step 3.1: Create Prompt Infrastructure
- [ ] Create `src/virtualoffice/sim_manager/prompts/` directory
- [ ] Create `prompts/__init__.py`
- [ ] Create `prompts/prompt_manager.py` with `PromptManager` class
- [ ] Create `prompts/context_builder.py` with `ContextBuilder` class
- [ ] Create `prompts/metrics_collector.py` with `PromptMetricsCollector`
- [ ] Create `prompts/templates/` directory structure
- [ ] Add YAML parsing utilities
- [ ] Create `tests/prompts/` directory
- [ ] Create `tests/prompts/test_prompt_manager.py`
- [ ] Create `tests/prompts/test_context_builder.py`
- [ ] Write comprehensive tests
- [ ] Commit changes: "feat: add prompt management infrastructure"

#### Step 3.2: Convert Existing Prompts to Templates
- [ ] Create `templates/planning/` directory
- [ ] Create `templates/planning/hourly_en.yaml`
- [ ] Create `templates/planning/hourly_ko.yaml`
- [ ] Create `templates/planning/daily_en.yaml`
- [ ] Create `templates/planning/daily_ko.yaml`
- [ ] Create `templates/reporting/` directory
- [ ] Create `templates/reporting/daily_report_en.yaml`
- [ ] Create `templates/reporting/daily_report_ko.yaml`
- [ ] Test template loading and caching
- [ ] Verify templates produce identical output to hard-coded prompts
- [ ] Commit changes: "feat: convert prompts to YAML templates"

#### Step 3.3: Integrate with Planner
- [ ] Add `generate_with_messages()` method to `Planner` protocol
- [ ] Update `GPTPlanner` to accept pre-built messages
- [ ] Update `generate_hourly_plan()` to use templates
- [ ] Update `generate_daily_plan()` to use templates
- [ ] Update `generate_daily_report()` to use templates
- [ ] Add metrics collection to all prompt usage
- [ ] Test all planning methods with templates
- [ ] Verify Korean and English locales work
- [ ] Run full test suite and verify passing
- [ ] Commit changes: "refactor: integrate prompt templates with planner"

#### Step 3.4: Create Template Validation
- [ ] Add template schema validation
- [ ] Add context variable validation
- [ ] Add prompt output validation
- [ ] Create template testing utilities
- [ ] Document template format in README
- [ ] Add validation tests
- [ ] Commit changes: "feat: add template validation system"

**Phase 3 Deliverables:**
- [ ] Full prompt management system
- [ ] All existing prompts as YAML templates
- [ ] Template validation and testing
- [ ] Metrics collection framework
- [ ] Planner.py reduced by ~300 lines

---

### Phase 4: VirtualWorker Enhancement (Weeks 7-8) - TODO

**Goal:** Move planning logic from engine to workers

#### Step 4.1: Create Enhanced Worker Classes
- [ ] Create `virtualWorkers/context_classes.py` (PlanningContext, etc.)
- [ ] Create `virtualWorkers/virtual_worker.py`
- [ ] Create `virtualWorkers/planner_mixin.py`
- [ ] Add comprehensive docstrings and type hints
- [ ] Create `tests/test_virtual_worker.py`
- [ ] Write comprehensive tests
- [ ] Commit changes: "feat: create enhanced VirtualWorker classes"

#### Step 4.2: Implement Worker-Driven Planning
- [ ] Implement `VirtualWorker.__init__()` with dependencies
- [ ] Implement `VirtualWorker.as_prompt()` using PromptManager
- [ ] Implement `VirtualWorker.plan_next_hour()`
- [ ] Implement `VirtualWorker.plan_daily()`
- [ ] Implement `VirtualWorker.generate_daily_report()`
- [ ] Update engine to create VirtualWorker instances
- [ ] Update engine to delegate planning to workers
- [ ] Test planning produces identical results
- [ ] Commit changes: "feat: implement worker-driven planning"

#### Step 4.3: Implement Event Reactions
- [ ] Design event reaction system
- [ ] Implement `VirtualWorker.react_to_event()`
- [ ] Create event reaction templates
- [ ] Update `EventSystem` to use worker reactions
- [ ] Test event reactions with various event types
- [ ] Commit changes: "feat: implement worker event reactions"

#### Step 4.4: Migrate All Planning to Workers
- [ ] Remove `_generate_hourly_plan()` from engine
- [ ] Remove `_generate_daily_plan()` from engine
- [ ] Update all planning calls to use workers
- [ ] Test all planning scenarios (single/multi-project)
- [ ] Verify Korean localization works
- [ ] Performance test parallel planning
- [ ] Run full test suite
- [ ] Commit changes: "refactor: complete migration to worker-driven planning"

**Phase 4 Deliverables:**
- [ ] Full VirtualWorker implementation
- [ ] All planning moved to workers
- [ ] Event reaction system
- [ ] Engine.py reduced to ~450 lines total
- [ ] All tests passing

---

### Phase 5: Integration and Testing (Weeks 9-10) - TODO

**Goal:** Full integration testing, documentation, cleanup

#### Step 5.1: Integration Testing
- [ ] Create `tests/integration/` directory
- [ ] Create multi-project integration tests
- [ ] Create long-running simulation tests (1 week, 4 weeks)
- [ ] Test all locales (English, Korean)
- [ ] Test parallel planning
- [ ] Performance benchmarking
- [ ] Load testing (10+ workers)
- [ ] Memory leak testing
- [ ] Commit changes: "test: add comprehensive integration tests"

#### Step 5.2: Documentation
- [ ] Update `docs/architecture.md` with new module structure
- [ ] Create module API documentation
- [ ] Create template authoring guide
- [ ] Create migration guide for existing users
- [ ] Update `README.md` with new architecture
- [ ] Create developer guide
- [ ] Update `DOCUMENTATION_INDEX.md`
- [ ] Commit changes: "docs: update all documentation for refactored architecture"

#### Step 5.3: Cleanup and Polish
- [ ] Remove deprecated code from engine
- [ ] Clean up all imports
- [ ] Add type hints to all public APIs
- [ ] Run linters (flake8, mypy)
- [ ] Run formatters (black)
- [ ] Update all docstrings
- [ ] Create CHANGELOG.md entry
- [ ] Commit changes: "chore: cleanup and polish refactored code"

#### Step 5.4: Final Validation
- [ ] Run 1-week English simulation
- [ ] Run 1-week Korean simulation
- [ ] Run 4-week multi-project simulation
- [ ] Validate persona integration works
- [ ] Validate all locales work correctly
- [ ] Performance comparison with old system
- [ ] Memory usage analysis
- [ ] Create demo scripts in `scripts/`
- [ ] Final commit: "feat: complete engine refactoring project"

**Phase 5 Deliverables:**
- [ ] Complete test suite
- [ ] Full documentation
- [ ] Clean codebase
- [ ] Performance benchmarks
- [ ] Migration guide

---

## Success Metrics

**Code Quality:**
- [ ] Engine.py reduced from 2360+ lines to <500 lines (80% reduction)
- [ ] Test coverage maintained at >90%
- [ ] All existing tests passing
- [ ] Passes mypy strict mode

**Performance:**
- [ ] No regression in simulation speed
- [ ] Parallel planning improves multi-worker scenarios by 2-4x
- [ ] Memory usage similar or better

**Functionality:**
- [ ] All existing features work identically
- [ ] Korean and English locales work
- [ ] Multi-project support works
- [ ] Template system functional
- [ ] A/B testing framework works

---

## Future Enhancements (Post-Refactoring)

### High Priority
- [ ] Plugin system for worker behaviors
- [ ] Snapshot and replay system
- [ ] Worker learning/adaptation
- [ ] Configuration management system
- [ ] Comprehensive observability/metrics

### Medium Priority
- [ ] Prompt versioning and rollback
- [ ] Hot reload for templates
- [ ] CLI tools for common tasks
- [ ] Interactive exploration tools
- [ ] Performance optimizations (caching, async I/O)

### Low Priority
- [ ] Property-based testing with hypothesis
- [ ] Fuzzing for robustness
- [ ] Extended simulation testing (12+ weeks)
- [ ] Advanced A/B testing analytics

---

## Completed Tasks

### 2025-10-27 (Engine Refactoring - Phase 1 Implementation)
- ✅ **Step 1.1: Module Structure Setup**
  - Created `src/virtualoffice/sim_manager/core/` directory
  - Created `core/__init__.py` with module exports
  - Set up testing infrastructure (`tests/core/`)
- ✅ **Step 1.2: SimulationState Module** (408 lines)
  - Extracted database schema (SIM_SCHEMA)
  - Extracted state management methods
  - Extracted status override system
  - Created 16 comprehensive unit tests (all passing)
  - Updated engine.py to use StateManager
  - Reduced engine.py by ~220 lines
- ✅ **Step 1.3: TickManager Module** (442 lines) - MOSTLY COMPLETE
  - Extracted time conversion methods (_format_sim_time, _sim_datetime_for_tick)
  - Extracted work hours parsing (_parse_work_hours_to_ticks, _is_within_work_hours)
  - Extracted auto-tick threading logic (_run_auto_tick_loop)
  - Created 41 comprehensive unit tests (all passing)
  - Updated engine.py to use TickManager (95% complete)
  - Reduced engine.py by ~190 lines
- ✅ **Total Progress**:
  - Created 2 core modules (850 lines)
  - Created 57 unit tests (all passing)
  - Reduced engine.py by ~410 lines (from 2360 to ~1950 lines)

### 2025-10-27 (Engine Refactoring Planning)
- ✅ Analyzed current engine.py architecture (2360+ lines)
- ✅ Created comprehensive refactoring plan (20251027_170000_Engine_Refactoring_plan.md)
- ✅ Created detailed plan and design document (20251027_151949_plan_and_design.md)
- ✅ Rewrote todo.md with phased implementation plan

### 2025-10-20 (Email Threading & Token Optimization)
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
- ✅ Token optimization bug fix (Daily Report Context Length)
  - Fixed 163K token limit issue in 8-week simulations
  - Removed minute_schedule from daily report prompt
  - Completed hierarchical summarization chain: Tick → Hour → Day → Simulation
- ✅ Project organization cleanup
  - Created `agent_reports/` directory
  - Created `scripts/` directory
  - Added timestamp prefixes to all reports
  - Updated `CLAUDE.md` with task tracking guidelines
- ✅ 8-week multi-project simulation
  - 100% clean email validation (0 hallucinations)
  - Korean language support
  - Multi-project context switching

---

## Notes

- **Current Focus:** Phase 1 - Core Module Extraction
- **Timeline:** 10-week refactoring project (started 2025-10-27)
- **Reference:** `agent_reports/20251027_151949_plan_and_design.md`
- All agent reports saved to `agent_reports/` with timestamp prefix
- All simulation scripts in `scripts/` directory
- Use OpenAI key 1 for all simulations (per company policy)
- Korean locale requires Korean names in personas
- Commit after each major step with descriptive messages
- Run full test suite before each commit
- Maintain >90% code coverage throughout refactoring
