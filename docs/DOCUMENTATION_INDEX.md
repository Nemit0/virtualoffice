# VDOS Documentation Index

## Created Documentation Files

This documentation was generated on 2025-10-17 to provide a comprehensive guide to the Virtual Department Operations Simulator (VDOS) codebase.

**Last Updated**: 2025-10-28 - README.md AI section updated to reflect Prompt Management System

### Core Documentation

#### 1. Main README
**File**: `README.md` (project root)

**Contains**:
- Project overview and quick start guide
- Architecture diagram (text-based)
- Table of contents with links to all docs
- Installation instructions
- Quick examples for GUI and headless usage
- Core concepts explanation
- Development workflow guide
- **NEW (2025-10-28)**: Enhanced "Extending with AI" section with:
  - Prompt Management System overview
  - YAML-based template documentation
  - Template authoring example
  - AI features comprehensive list
  - Documentation cross-references

#### 2. Architecture Documentation
**File**: `docs/architecture.md`

**Contains**:
- System architecture overview with diagrams
- Component architecture for all 6 main modules:
  - Email Server (Port 8000)
  - Chat Server (Port 8001)
  - Simulation Manager (Port 8015)
  - Virtual Workers
  - PySide6 GUI
  - **Web Dashboard Interface** (Browser-based monitoring)
- Complete database schema documentation
- Data flow diagrams (Mermaid format)
- Communication patterns and protocols
- Configuration reference
- Threading model
- Error handling strategies
- Performance considerations
- Extensibility guide

#### 3. Environment Variables Reference
**File**: `docs/reference/environment-variables.md`

**Contains**:
- Complete list of all environment variables
- Service connection configuration
- Database settings
- Simulation configuration
- Planner configuration
- Localization settings
- OpenAI integration
- Example `.env` file
- Docker compose example
- Security best practices

## Documentation Structure Created

```
docs/
├── README.md                                  # Main entry point
├── DOCUMENTATION_INDEX.md                     # This file
├── architecture.md                            # System architecture
├── modules/                                   # Module documentation
│   ├── simulation_state.md                  # ✓ Created - SimulationState module documentation
│   ├── tick_manager.md                      # ✓ Created - TickManager module documentation
│   ├── event_system.md                      # ✓ Created - EventSystem module documentation
│   ├── communication_hub.md                 # ✓ Created - CommunicationHub module documentation
│   ├── worker_runtime.md                    # ✓ Created - WorkerRuntime module documentation
│   ├── project_manager.md                   # ✓ Created - ProjectManager module documentation
│   ├── prompt_system.md                     # ✓ Created - Prompt Management System documentation
│   ├── virtual_worker_context.md            # ✓ Created - VirtualWorker Context Classes documentation
│   ├── localization.md                      # ✓ Created - Localization system documentation
│   ├── planner.md                           # ✓ Created - Planner system documentation
│   ├── database.md                          # ✓ Created (2025-10-28) - Database connection management and concurrent access
│   ├── communication_style_filter.md        # ✓ Updated (2025-10-30) - Communication style filter system (Phase 2 Complete)
│   ├── communication_generator.md           # ✓ Created (2025-11-05) - GPT-powered fallback communication generation
│   ├── inbox_manager.md                     # ✓ Created (2025-11-05) - Inbox tracking and message classification
│   ├── participation_balancer.md            # ✓ Created (2025-11-05) - Message distribution balancing
│   ├── plan_parser.md                       # ✓ Created (2025-11-06) - AI-powered plan parsing and JSON scheduling
│   ├── planner.md                           # ✓ Created (2025-11-06) - GPT and Stub planners with protocol interface
│   ├── email-server.md                      # (To be created)
│   ├── chat-server.md                       # (To be created)
│   ├── sim-manager.md                       # (To be created)
│   ├── virtual-workers.md                   # (To be created)
│   ├── gui-app.md                           # (To be created)
│   └── utils.md                             # (To be created)
├── guides/                                    # User guides
│   ├── template_authoring.md                # ✓ Created - Template authoring guide (referenced in README)
│   ├── migration_guide.md                   # ✓ Created - Engine refactoring migration guide
│   ├── troubleshooting.md                   # ✓ Created (2025-10-28) - Comprehensive troubleshooting guide with diagnostic tools
│   ├── communication_diversity_examples.md  # ✓ Created (2025-11-05) - Usage examples for communication diversity features
│   └── communication_diversity_troubleshooting.md  # ✓ Created (2025-11-05) - Troubleshooting guide for communication diversity
├── GETTING_STARTED.md                        # ✓ Updated (2025-10-28) - Added Prompt Management System section
├── api/                                       # API documentation (directory created)
│   ├── style_filter_endpoints.md            # ✓ Created (2025-10-30) - Style filter API endpoints
│   ├── email-api.md                          # (To be created)
│   ├── chat-api.md                           # (To be created)
│   └── sim-manager-api.md                    # (To be created)
├── workflows/                                 # Workflow documentation (directory created)
│   ├── testing.md                           # ✓ Created - Comprehensive testing documentation
│   ├── simulation-lifecycle.md               # ✓ Created - Simulation flow across lifecycle + planning orchestrator
│   ├── worker-behavior.md                    # (To be created)
│   ├── token-tracking.md                     # (To be created)
│   └── multi-project.md                      # (To be created)
├── reference/                                 # Reference documentation
│   ├── environment-variables.md              # ✓ Created
│   ├── classes.md                            # (To be created)
│   ├── functions.md                          # (To be created)
│   └── data-models.md                        # (To be created)
└── scripts/                                   # Scripts documentation (directory created)
    └── simulation-scripts.md                 # (To be created)
```

## Quick Navigation Guide

### For New Developers
Start here to understand the system:
1. `docs/README.md` - Overview and quick start
2. `docs/architecture.md` - How everything fits together
3. `docs/reference/environment-variables.md` - Configuration guide
4. `docs/guides/troubleshooting.md` - Troubleshooting common issues

### For API Integration
If you're integrating with VDOS services:
1. `docs/architecture.md` - Understand the service architecture
2. `docs/api/email-api.md` - Email server endpoints (to be created)
3. `docs/api/chat-api.md` - Chat server endpoints (to be created)
4. `docs/api/sim-manager-api.md` - Simulation control endpoints (to be created)

### For Running Simulations
If you want to run simulations:
1. `docs/README.md#quick-start` - Get started quickly
2. `docs/workflows/simulation-lifecycle.md` - How simulations work
3. `docs/workflows/worker-behavior.md` - How workers behave (to be created)
4. `docs/scripts/simulation-scripts.md` - Pre-built simulation scripts (to be created)

### For Extending VDOS
If you're adding features:
1. `docs/architecture.md#extensibility` - Extension patterns
2. `docs/reference/classes.md` - Class reference (to be created)
3. `docs/reference/data-models.md` - Data model reference (to be created)

## Key Information Covered

### Architecture Documentation Includes:
- Complete system architecture with diagrams
- All 5 core components explained in detail
- Database schema for all 20+ tables
- Data flow diagrams for simulation lifecycle
- Message routing and communication patterns
- Planning hierarchy (Project → Daily → Hourly → Reports)
- Threading model and concurrency
- Error handling and planner fallback
- Performance optimizations
- Extension points

### API Documentation Includes:
- Complete REST API reference for all services
- New export/import endpoints for personas and projects
- Request/response examples with realistic data
- Error handling and validation documentation
- Authentication and rate limiting information

### Configuration Documentation Includes:
- All 30+ environment variables documented
- Service connection settings
- Database configuration
- Simulation parameters
- Planner model configuration
- Locale settings (English/Korean support)
- Security best practices
- Docker deployment example

### Code Structure Documented:
- **Email Server**: FastAPI app, models, database tables
- **Chat Server**: FastAPI app, models, DM handling
- **Simulation Manager**: 2360-line engine, planner, gateways, schemas
- **Virtual Workers**: Persona system, markdown generation
- **GUI**: PySide6 app with server management and simulation controls

## File Locations Reference

### Source Code
- Email Server: `src/virtualoffice/servers/email/`
- Chat Server: `src/virtualoffice/servers/chat/`
- Simulation Manager: `src/virtualoffice/sim_manager/`
- Virtual Workers: `src/virtualoffice/virtualWorkers/`
- Web Dashboard: `src/virtualoffice/sim_manager/index_new.html`
- Common Utilities: `src/virtualoffice/common/`
- Utils: `src/virtualoffice/utils/`

### Database
- Default location: `src/virtualoffice/vdos.db`
- Configurable via: `VDOS_DB_PATH`

### Tests
- Test suite: `tests/`
- Email server tests: `tests/test_email_server.py`
- Chat server tests: `tests/test_chat_server.py`
- Simulation tests: `tests/test_sim_manager.py`
- Worker tests: `tests/test_virtual_worker.py`
- Enhanced worker tests: `tests/test_virtual_worker_enhanced.py`
- Integration tests: `tests/integration/`
  - Long simulation tests: `tests/integration/test_long_simulation.py`
  - Multi-project tests: `tests/integration/test_multi_project.py`
- Performance tests: `tests/performance/`
  - Tick advancement: `tests/performance/test_tick_advancement.py`
  - Parallel planning: `tests/performance/test_parallel_planning.py`
  - Memory usage: `tests/performance/test_memory_usage.py`
  - Template loading: `tests/performance/test_template_loading.py`

## Additional Documentation to Create

While the core architecture and configuration documentation is complete, the following additional documentation files should be created to provide complete coverage:

### Module Documentation (`docs/modules/`)
Each module needs detailed documentation including:
- Purpose and responsibilities
- Key classes and their methods
- Configuration options
- Example usage
- Integration points

**Completed Module Documentation:**
- ✅ **simulation_state.md**: Complete documentation for the SimulationState module including database operations, state persistence, configuration management, and schema migrations
- ✅ **tick_manager.md**: Complete documentation for the TickManager module including tick advancement, work hours calculation, time formatting, and auto-tick threading
- ✅ **event_system.md**: Complete documentation for the EventSystem module including event injection, random event generation, event-to-adjustment conversion, localization support, and integration with SimulationEngine
- ✅ **communication_hub.md**: Complete documentation for the CommunicationHub module including communication scheduling, parsing, dispatch, deduplication, cooldown logic, email threading, and group chat routing
- ✅ **worker_runtime.md**: Complete documentation for the WorkerRuntime module including message inbox management, runtime state persistence, worker synchronization, and integration with SimulationEngine
- ✅ **project_manager.md**: Complete documentation for the ProjectManager module including project plan storage/retrieval, active project queries, multi-project coordination, project chat room lifecycle, and project completion detection
- ✅ **prompt_system.md**: Complete documentation for the Prompt Management System including PromptManager, ContextBuilder, PromptMetricsCollector, YAML template format, A/B testing, localization support, and integration with SimulationEngine
- ✅ **virtual_worker_context.md**: Complete documentation for VirtualWorker Context Classes including PlanningContext, DailyPlanningContext, EventContext, ReportContext, EventResponse, integration patterns, and localization support
- ✅ **localization.md**: Comprehensive documentation for the localization system including LocalizationManager class, supported locales, integration examples, Korean persona integration testing, and extension guidelines
- ✅ **planner.md**: Complete documentation for the planner system including GPTPlanner, StubPlanner, persona integration, localization support, and planning workflows
- ✅ **communication_style_filter.md**: Complete documentation for the communication style filter system including StyleExampleGenerator, CommunicationStyleFilter, FilterMetrics, database schema, integration points, and implementation roadmap (Phase 2 Complete - Core Implementation)
- ✅ **communication_generator.md**: Complete documentation for GPT-powered fallback communication generation including context building, Korean/English prompts, role-specific terminology, integration with planner and style filter (Nov 5, 2025) - **Integrated into engine**
- ✅ **inbox_manager.md**: Complete documentation for inbox tracking system including message classification, reply prioritization, multilingual support, and integration with communication generator (Nov 5, 2025) - **Integrated into engine**
- ✅ **participation_balancer.md**: Complete documentation for participation balancing system including throttling/boosting logic, deterministic behavior, and integration with fallback generation (Nov 5, 2025) - **Integrated into engine**

**New Module Documentation to review (refactor additions):**
- ➕ **people_repository.md**: People CRUD + schedules, row↔model mapping
- ➕ **plan_store.md**: Worker plan storage and queries
- ➕ **report_store.md**: Daily/hourly/simulation report persistence and queries
- ➕ **metrics.md**: Thread-safe bounded metrics recorder for planner usage
- ➕ **planner_service.md**: Planner invocation service with strict/fallback and metrics
- ➕ **planning_orchestrator.md**: Orchestrates daily/hourly planning and reports
- ➕ **worker_registry.md**: VirtualWorker creation/sync with lazy imports
- ➕ **lifecycle.md**: Start/stop/reset/auto-ticks and auto-pause logic

**Completed Workflow Documentation:**
- ✅ **testing.md**: Comprehensive testing documentation including test suite organization, Korean persona integration tests, performance testing, integration tests, UI automation tests with Playwright, and debugging guidelines

**Completed Guide Documentation:**
- ✅ **template_authoring.md**: Complete guide for creating and managing YAML prompt templates including format specification, examples, validation, and best practices
- ✅ **migration_guide.md**: Comprehensive migration guide for the engine refactoring including breaking changes, migration steps, and troubleshooting
- ✅ **communication_diversity_examples.md**: Comprehensive usage examples for communication diversity features including GPT fallback generation, participation balancing, quality metrics monitoring, and cost/performance examples (Nov 5, 2025)
- ✅ **communication_diversity_troubleshooting.md**: Complete troubleshooting guide for communication diversity features including common issues, rollback procedures, debugging tips, FAQ, and support resources (Nov 5, 2025)

### API Documentation (`docs/api/`)
Complete REST API reference for each service:
- All endpoints with methods
- Request/response schemas
- Example requests with curl/httpx
- Error codes and responses
- Authentication (if applicable)

### Workflow Documentation (`docs/workflows/`)
Step-by-step guides for key workflows:
- **simulation-lifecycle.md**: Complete simulation flow from start to finish
- **worker-behavior.md**: How workers plan, communicate, and respond
- **token-tracking.md**: Token usage tracking and optimization
- **multi-project.md**: Running concurrent multi-project simulations

### Reference Documentation (`docs/reference/`)
- **classes.md**: All classes with signatures and descriptions
- **functions.md**: All standalone functions
- **data-models.md**: All Pydantic models with field descriptions

### Scripts Documentation (`docs/scripts/`)
Documentation for simulation runner scripts found in the root directory:
- `mobile_chat_simulation.py`
- `quick_simulation.py`
- `short_blog_simulation.py`
- Multi-project simulation scripts

## How to Use This Documentation

### Reading on GitHub
All documentation is written in GitHub-flavored Markdown and will render nicely on GitHub. Simply browse to the `docs/` directory in the repository.

### Local Viewing
You can also view the documentation locally:
1. Navigate to `docs/README.md` in any Markdown viewer
2. Follow the table of contents links
3. Use relative links between documents

### Contributing to Documentation
When adding new features to VDOS:
1. Update relevant module documentation in `docs/modules/`
2. Update API documentation if endpoints change
3. Add workflow documentation for new processes
4. Update environment variables if configuration changes
5. Keep the main `docs/README.md` table of contents current

## Documentation Standards

All documentation follows these standards:
- Clear, concise writing
- Code examples with syntax highlighting
- Mermaid diagrams for complex flows
- Tables for structured data
- Absolute file paths for references
- Cross-references using relative markdown links
- No emojis (professional tone)
- Proper markdown formatting (headers, lists, code blocks)

## Phase 4: VirtualWorker Enhancement Integration Status

**Current Status**: Task 4.7 In Progress (50% Complete)

### Completed Tasks (4.1-4.6)
- ✅ **Context Classes**: Complete implementation with comprehensive documentation
- ✅ **Planner Mixin**: All planning methods implemented and tested
- ✅ **VirtualWorker Class**: Full autonomous worker implementation
- ✅ **Event Reaction System**: Templates and structured responses
- ✅ **Comprehensive Testing**: 13 tests with 100% pass rate
- ✅ **Documentation**: Complete module and integration documentation

### Task 4.7: Engine Integration (In Progress)
**Status**: Partial implementation, 50% complete

**Completed Steps**:
- ✅ VirtualWorker imports added to `engine.py`
- ✅ PromptManager and ContextBuilder initialized in engine constructor
- ✅ `self.workers` dictionary added to store VirtualWorker instances
- ✅ `_sync_virtual_workers()` method added for worker synchronization
- ✅ Parallel planning infrastructure (ThreadPoolExecutor) in place

**Incomplete Steps**:
- ⚠️ Worker creation logic partially implemented (missing `_to_persona_from_person_read()` helper)
- ⏳ Person creation not yet updated to instantiate VirtualWorker
- ⏳ Planning delegation not yet implemented
- ⏳ Old planning logic not yet removed from engine

**Next Actions**:
1. Implement `_to_persona_from_person_read()` helper method
2. Update `create_person()` to instantiate VirtualWorker
3. Delegate hourly planning to `VirtualWorker.plan_next_hour()`
4. Delegate daily planning to `VirtualWorker.plan_daily()`
5. Delegate reporting to `VirtualWorker.generate_daily_report()`
6. Remove old planning logic from engine
7. Test integration with existing simulations

### Task 4.8: Parallel Planning (Pending)
**Status**: Infrastructure ready, implementation pending

**Ready Components**:
- ✅ ThreadPoolExecutor configured in engine
- ✅ `_max_planning_workers` configuration
- ✅ VirtualWorker designed for concurrent execution

**Pending Implementation**:
- ⏳ `_execute_planning_parallel()` method
- ⏳ Update tick advancement to use parallel planning
- ⏳ Performance metrics collection
- ⏳ Benchmark parallel vs sequential

### Documentation Status
- ✅ **Integration Guide**: `agent_reports/20251028_PHASE4_INTEGRATION_GUIDE.md`
- ✅ **Implementation Report**: `agent_reports/20251028_PHASE4_VIRTUALWORKER_ENHANCEMENT.md`
- ✅ **Complete Summary**: `agent_reports/20251028_PHASE4_COMPLETE_SUMMARY.md`
- ✅ **Context Documentation**: `docs/modules/virtual_worker_context.md`
- ✅ **Architecture Updated**: Integration status documented in `docs/architecture.md`

### References
- **Integration Guide**: See `agent_reports/20251028_PHASE4_INTEGRATION_GUIDE.md` for step-by-step instructions
- **VirtualWorker Tests**: `tests/test_virtual_worker_enhanced.py` (13 tests, all passing)
- **Context Classes**: `src/virtualoffice/virtualWorkers/context_classes.py`
- **VirtualWorker**: `src/virtualoffice/virtualWorkers/virtual_worker.py`
- **Engine**: `src/virtualoffice/sim_manager/engine.py` (integration in progress)

## Summary

The documentation infrastructure is now in place with:
- ✅ Main README with overview and quick start
- ✅ Complete architecture documentation (updated with Phase 4 status)
- ✅ Full environment variables reference
- ✅ Directory structure for all planned docs
- ✅ Phase 4 VirtualWorker documentation complete
- ✅ Integration status tracking
- ⏳ Module-specific documentation (to be created)
- ⏳ API reference (to be created)
- ⏳ Workflow guides (to be created)
- ⏳ Class/function reference (to be created)
- ⏳ Scripts documentation (to be created)

The foundational documentation provides a solid understanding of the system architecture, configuration, and how components interact. Phase 4 VirtualWorker enhancement is partially integrated with comprehensive documentation available. Additional documentation can be created incrementally as needed.
