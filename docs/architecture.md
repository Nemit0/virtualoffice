# VDOS Architecture

## System Overview

VDOS is a three-tier architecture with FastAPI services, a Web Dashboard, and a shared SQLite database. The simulation engine has been refactored into modular components for improved maintainability and testability.

```
┌───────────────────────────────────────────────────────────────┐
│                        Web Dashboard                           │
│       (src/virtualoffice/sim_manager/index_new.html)           │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │   Server     │  │  Simulation  │  │     Persona       │   │
│  │  Management  │  │   Controls   │  │   Management      │   │
│  │              │  │              │  │                   │   │
│  │ Start/Stop   │  │ Start/Stop   │  │ Create/Edit       │   │
│  │ Services     │  │ Advance      │  │ View Reports      │   │
│  └──────────────┘  └──────────────┘  └───────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                           │
                           │ HTTP/REST
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    ┌────────┐        ┌────────┐       ┌────────────┐
    │ Email  │        │  Chat  │       │Simulation  │
    │ Server │        │ Server │       │  Manager   │
    │:8000   │        │ :8001  │       │   :8015    │
    └────┬───┘        └────┬───┘       └─────┬──────┘
         │                 │                  │
         │                 │           ┌──────▼──────────────────┐
         │                 │           │ SimulationEngine        │
         │                 │           │   (Facade/Orchestrator) │
         │                 │           └──────┬──────────────────┘
         │                 │                  │
         │                 │    ┌─────────────┼─────────────┐
         │                 │    │             │             │
         │                 │    ▼             ▼             ▼
         │                 │  ┌────────┐  ┌────────┐  ┌──────────┐
         │                 │  │ State  │  │  Tick  │  │  Event   │
         │                 │  │Manager │  │Manager │  │  System  │
         │                 │  └────────┘  └────────┘  └──────────┘
         │                 │    │             │             │
         │                 │    ▼             ▼             ▼
         │                 │  ┌────────┐  ┌────────┐  ┌──────────┐
         │                 │  │ Comms  │  │Worker  │  │ Project  │
         │                 │  │  Hub   │  │Runtime │  │ Manager  │
         │                 │  └────────┘  └────────┘  └──────────┘
         │                 │                  │
         │                 │           ┌──────▼──────────────────┐
         │                 │           │   VirtualWorker         │
         │                 │           │ (Autonomous Planning)   │
         │                 │           └──────┬──────────────────┘
         │                 │                  │
         │                 │           ┌──────▼──────────────────┐
         │                 │           │  Prompt Management      │
         │                 │           │  - PromptManager        │
         │                 │           │  - ContextBuilder       │
         │                 │           │  - MetricsCollector     │
         │                 │           └─────────────────────────┘
         │                 │                  │
         └─────────────────┴──────────────────┘
                           │
                      ┌────▼─────┐
                      │  SQLite  │
                      │ vdos.db  │
                      └──────────┘
```

### Refactored Architecture Benefits

**Modularity**: Engine acts as a thin facade; core responsibilities live in focused modules
**Testability**: Each module has comprehensive unit tests with >90% coverage
**Maintainability**: Clear separation of concerns and single responsibilities
**Extensibility**: Easy to add new features without modifying core engine
**Performance**: Parallel planning support for multi-worker scenarios
**Observability**: Metrics collection for prompt performance and optimization

## Component Architecture

### Refactored Core Modules

The simulation engine has been refactored from a monolithic 2360+ line class into focused, testable modules. Each module has a single responsibility and clean interfaces.

**Phase 4 Integration Status**: VirtualWorker integration is partially implemented. The engine has VirtualWorker infrastructure (lazy imports, PromptManager, ContextBuilder, workers dictionary, sync method) but planning delegation to workers is not yet complete. See Virtual Workers section below for detailed integration status.

#### SimulationState Module
**Location**: `src/virtualoffice/sim_manager/core/simulation_state.py`

**Responsibilities**:
- Database initialization and schema management
- Simulation state persistence (tick, running status, auto-tick)
- Configuration loading from environment
- Status override management
- Database migrations

**Key Classes**:
- `SimulationState` - Main state management class

**Key Methods**:
- `get_current_state()` - Get current simulation status
- `update_tick(tick, reason)` - Update current tick with reason
- `set_running(running)` - Set simulation running state
- `set_auto_tick(enabled)` - Enable/disable auto-tick
- `get_status_overrides()` - Get worker status overrides
- `set_status_override(worker_id, status, until_tick)` - Set temporary status
- `clear_status_override(worker_id)` - Clear status override
- `apply_migrations()` - Apply database schema migrations
- `reset()` - Reset simulation state

**Integration**:
- Used by all core modules for database access
- Thread-safe state updates
- Encapsulates all SQLite operations

#### TickManager Module
**Location**: `src/virtualoffice/sim_manager/core/tick_manager.py`

**Responsibilities**:
- Time progression and tick advancement
- Auto-tick loop management with threading
- Work hours calculation and caching
- Simulation datetime calculations
- Time formatting utilities

**Key Classes**:
- `TickManager` - Main time management class

**Key Methods**:
- `advance_ticks(count, reason)` - Advance simulation by N ticks
- `is_within_work_hours(person, tick)` - Check if tick is during work hours
- `parse_work_hours_to_ticks(work_hours)` - Convert work hours to tick range
- `format_sim_time(tick)` - Format tick as human-readable time
- `sim_datetime_for_tick(tick, base_dt)` - Convert tick to datetime
- `start_auto_tick(callback, interval_seconds)` - Start auto-tick thread
- `stop_auto_tick()` - Stop auto-tick thread
- `is_auto_tick_running()` - Check auto-tick status

**Integration**:
- Used by `SimulationEngine` for all time-related operations
- Manages auto-tick threading lifecycle
- Provides time formatting for communications

#### EventSystem Module
**Location**: `src/virtualoffice/sim_manager/core/event_system.py`

**Responsibilities**:
- Event storage and retrieval from database
- Random event generation (sick leave, client requests, blockers)
- Event-to-adjustment conversion for worker planning
- Project-specific event filtering
- Scheduled event processing at specific ticks

**Key Classes**:
- `EventSystem` - Main event management class

**Key Methods**:
- `inject_event(event)` - Store custom events in database
- `list_events(project_id, target_id)` - Query events with filtering
- `process_events_for_tick(tick, people)` - Generate and process events for current tick
- `convert_event_to_adjustments(event, person)` - Convert events to planning adjustments
- `generate_random_events(tick, people)` - Generate random events

**Random Event Types**:
- **Sick Leave**: 5% daily chance, triggers status override and team notifications
- **Client Feature Requests**: ~10% chance every 2 hours, generates coordination tasks
- **Blockers**: Dependency issues requiring team coordination (extensible)
- **Meetings**: Scheduled gatherings affecting availability (extensible)

**Integration**:
- Used by `SimulationEngine` during tick advancement via `process_events_for_tick()`
- Used by `SimulationEngine` for event retrieval via `list_events()`
- Used by `SimulationEngine` for report generation (event summaries)
- Callbacks to engine for message queuing and status overrides
- Localization support via `get_current_locale_manager()`
- Deterministic random generation via optional seed
- Complete separation from direct database access in engine methods

#### CommunicationHub Module
**Location**: `src/virtualoffice/sim_manager/core/communication_hub.py`

**Responsibilities**:
- Parse hourly plans for scheduled communications
- Manage email and chat message scheduling
- Handle message deduplication and cooldown logic
- Support email threading (reply-to, thread_id)
- Route group chat vs DM messages
- Automatic CC suggestion for emails
- External stakeholder validation
- Recent email history tracking

**Key Classes**:
- `CommunicationHub` - Main communication management class

**Key Methods**:
- `schedule_from_hourly_plan(person, plan_text, current_tick, hours_per_day)` - Parse and schedule communications
- `dispatch_scheduled(person, current_tick, people_by_id)` - Dispatch scheduled messages
- `can_send(tick, channel, sender, recipient_key, subject, body)` - Check deduplication and cooldown
- `reset_tick_sends()` - Clear deduplication tracking for new tick
- `get_thread_id_for_reply(person_id, email_id)` - Look up email thread information
- `get_recent_emails_for_person(person_id, limit)` - Get recent email history
- `schedule_direct_comm(person_id, tick, channel, target, payload)` - Direct message scheduling

**Communication Formats Supported**:
- **Email**: `Email at HH:MM to PERSON: Subject | Body`
- **Email with CC**: `Email at HH:MM to PERSON cc PERSON2: Subject | Body`
- **Email with BCC**: `Email at HH:MM to PERSON bcc PERSON2: Subject | Body`
- **Reply to Email**: `Reply at HH:MM to [email-id]: Subject | Body`
- **Chat DM**: `Chat at HH:MM to PERSON: Message`
- **Group Chat**: `Chat at HH:MM to team: Message` (keywords: team, project, group, everyone)

**Features**:
- **Deduplication**: Prevents duplicate messages within same tick
- **Cooldown**: Enforces minimum ticks between messages to same recipient (default: 10)
- **Email Threading**: Maintains conversation threads with thread_id tracking
- **Recent Email History**: Tracks last 10 emails per person for context
- **Automatic CC Suggestion**: Suggests department head and relevant peers
- **Target Resolution**: Resolves names to email addresses or chat handles
- **External Stakeholder Support**: Validates against allowed external email addresses
- **Hallucination Prevention**: Rejects non-existent email addresses
- **Group Chat Routing**: Routes team messages to project chat rooms
- **DM Deduplication**: Prevents mirrored DMs between same participants

**Integration**:
- Used by `SimulationEngine` during tick advancement for communication dispatch
- Delegates to `EmailGateway` and `ChatGateway` for actual message delivery
- Uses `TickManager` for time calculations and datetime formatting
- Integrates with localization system for message templates
- Configurable via `VDOS_CONTACT_COOLDOWN_TICKS` environment variable
- Supports external stakeholders via `VDOS_EXTERNAL_STAKEHOLDERS` environment variable

#### WorkerRuntime Module
**Location**: `src/virtualoffice/sim_manager/core/worker_runtime.py`

**Responsibilities**:
- Maintain per-worker message inboxes
- Queue and drain messages for workers
- Persist runtime messages to database
- Load runtime state from database
- Synchronize worker runtimes with active people

**Key Classes**:
- `InboundMessage` - Dataclass for worker inbox messages
- `WorkerRuntime` - Runtime state for a single virtual worker
- `WorkerRuntimeManager` - Manages runtime state for all workers

**Key Methods**:
- `get_or_create(person)` - Get or create runtime for a person
- `sync_workers(people)` - Synchronize runtimes with active people
- `get_all_runtimes()` - Get all worker runtimes
- `clear_runtime(person_id)` - Clear specific worker runtime
- `WorkerRuntime.queue_message(message)` - Queue message for worker
- `WorkerRuntime.drain_messages()` - Drain and return all queued messages
- `WorkerRuntime.get_message_count()` - Get count of queued messages
- `WorkerRuntime.has_messages()` - Check if worker has messages

**Integration**:
- Used by `SimulationEngine` for worker message management
- Persists to `worker_runtime_messages` database table
- Uses `InboundMessage` dataclass for type safety
- Automatically loads persisted messages on runtime creation
- Thread-safe message queuing and draining

#### ProjectManager Module
**Location**: `src/virtualoffice/sim_manager/core/project_manager.py`

**Responsibilities**:
- Project plan storage and retrieval
- Active project queries with timeline awareness
- Project-person assignment management
- Multi-project scenario support
- Project chat room lifecycle management
- Project completion detection

**Key Classes**:
- `ProjectManager` - Main project management class

**Key Methods**:
- `store_project_plan(...)` - Store new project plan with assignments
- `get_project_plan(project_id)` - Retrieve project plan by ID or most recent
- `get_active_projects_for_person(person_id, week)` - Get ALL active projects for a person
- `get_active_project_for_person(person_id, week)` - Get first active project (backward compatibility)
- `get_active_projects_with_assignments(week)` - Get all active projects with their teams
- `create_project_chat_room(...)` - Create group chat room for project
- `get_active_project_chat_room(project_id)` - Get active chat room slug
- `archive_project_chat_room(project_id)` - Archive completed project's chat room
- `is_project_complete(project_id, current_week)` - Check if project is complete
- `clear_cache()` - Clear project plan cache

**Multi-Project Features**:
- **Overlapping Projects**: Person can work on multiple projects simultaneously
- **Sequential Projects**: Projects that run one after another
- **Mixed Assignments**: Both assigned and unassigned (everyone) projects
- **Timeline Awareness**: Queries respect project start_week and duration_weeks
- **Team Assignments**: Track which people work on which projects

**Project Chat Rooms**:
- Automatic room creation with naming convention: `project-{id}-{name-lowercase}`
- Room lifecycle management (active/archived states)
- Integration with ChatGateway for room creation
- Participant management based on project assignments

**Integration**:
- Used by `SimulationEngine` for project lifecycle management
- Persists to `project_plans`, `project_assignments`, `project_chat_rooms` tables
- Delegates to `ChatGateway` for room creation
- Supports multi-project simulations with overlapping timelines

#### Prompt Management System
**Location**: `src/virtualoffice/sim_manager/prompts/`

**Responsibilities**:
- LLM prompt template management with caching and validation
- Context aggregation from multiple data sources
- Performance metrics collection for A/B testing
- Multi-locale template support
- Variant management for prompt optimization

**Key Classes**:
- `PromptManager` - Template loading, caching, and prompt construction
- `PromptTemplate` - Dataclass representing loaded YAML templates
- `ContextBuilder` - Aggregates data for comprehensive context dictionaries
- `PromptMetricsCollector` - Tracks usage, tokens, and performance
- `PromptMetric` - Dataclass for individual metric records

**Key Methods (PromptManager)**:
- `load_template(name, version)` - Load template from disk or cache
- `build_prompt(template_name, context, variant)` - Build prompt with context substitution
- `validate_context(template, context)` - Validate required variables present
- `list_templates(category)` - List available templates
- `reload_templates()` - Clear cache for development

**Key Methods (ContextBuilder)**:
- `build_planning_context(...)` - Build context for hourly planning prompts
- `build_event_context(...)` - Build context for event reaction prompts
- `build_reporting_context(...)` - Build context for daily report generation

**Key Methods (PromptMetricsCollector)**:
- `record_usage(...)` - Record prompt usage event with metrics
- `get_performance_stats(template_name)` - Get statistics for a template
- `get_best_variant(template_name)` - Identify best performing variant
- `export_metrics(filepath)` - Export metrics to JSON
- `get_metrics_summary()` - Get summary across all templates

**Template Features**:
- **YAML Format**: Structured templates with system/user prompts
- **Variable Substitution**: Context variables injected into templates
- **Sections**: Reusable template sections with their own variables
- **Variants**: Multiple versions for A/B testing
- **Validation Rules**: Expected output format requirements
- **Metadata**: Author, version, description tracking

**A/B Testing**:
- Automatic variant selection based on composite scoring
- Success rate weighted at 70% (most important)
- Token efficiency weighted at 20% (cost optimization)
- Generation speed weighted at 10% (user experience)

**Localization Support**:
- Locale-specific templates (e.g., `hourly_planning_en.yaml`, `hourly_planning_ko.yaml`)
- Context builder formats data based on locale
- Team rosters, email lists, project descriptions localized

**Integration**:
- Used by `SimulationEngine` for all LLM-powered planning and reporting
- Replaces inline prompt construction with template-based approach
- Provides metrics for optimization and cost tracking
- Supports future prompt optimization and refinement

#### CommunicationHub Module
**Location**: `src/virtualoffice/sim_manager/core/communication_hub.py`

**Key Classes**:
- `CommunicationHub` - Main communication management class

**Key Methods**:
- `schedule_from_hourly_plan(person, plan_text, current_tick, hours_per_day)` - Parse and schedule communications
- `dispatch_scheduled(person, current_tick, people_by_id, ...)` - Dispatch scheduled messages
- `can_send(tick, channel, sender, recipient_key, subject, body)` - Check deduplication and cooldown
- `reset_tick_sends()` - Clear deduplication tracking for new tick
- `get_thread_id_for_reply(person_id, email_id)` - Look up email thread information
- `get_recent_emails_for_person(person_id, limit)` - Get recent email history
- `schedule_direct_comm(person_id, tick, channel, target, payload)` - Direct message scheduling

**Communication Formats Supported**:
- **Email**: `Email at HH:MM to PERSON: Subject | Body`
- **Email with CC**: `Email at HH:MM to PERSON cc PERSON2: Subject | Body`
- **Email with BCC**: `Email at HH:MM to PERSON bcc PERSON2: Subject | Body`
- **Reply to Email**: `Reply at HH:MM to [email-id]: Subject | Body`
- **Chat DM**: `Chat at HH:MM to PERSON: Message`
- **Group Chat**: `Chat at HH:MM to team: Message` (keywords: team, project, group, everyone)

**Features**:
- **Deduplication**: Prevents duplicate messages within same tick
- **Cooldown**: Enforces minimum ticks between messages to same recipient (default: 10)
- **Email Threading**: Maintains conversation threads with thread_id tracking
- **Recent Email History**: Tracks last 10 emails per person for context
- **Automatic CC Suggestion**: Suggests department head and relevant peers
- **Target Resolution**: Resolves names to email addresses or chat handles
- **External Stakeholder Support**: Validates against allowed external email addresses
- **Hallucination Prevention**: Rejects non-existent email addresses
- **Group Chat Routing**: Routes team messages to project chat rooms
- **DM Deduplication**: Prevents mirrored DMs between same participants

**Integration**:
- Used by `SimulationEngine` during tick advancement for communication dispatch
- Delegates to `EmailGateway` and `ChatGateway` for actual message delivery
- Uses `TickManager` for time calculations and datetime formatting
- Integrates with localization system for message templates
- Configurable via `VDOS_CONTACT_COOLDOWN_TICKS` environment variable
- Supports external stakeholders via `VDOS_EXTERNAL_STAKEHOLDERS` environment variable

### 1. Email Server (Port 8000)
**Location**: `src/virtualoffice/servers/email/`

**Responsibilities**:
- Email storage and retrieval
- Mailbox management
- Draft management
- Thread tracking

**Key Files**:
- `app.py` - FastAPI application with endpoints
- `models.py` - Pydantic models (EmailSend, EmailMessage, Mailbox, DraftCreate)

**Database Tables**:
- `mailboxes` - Email addresses and display names
- `emails` - Email messages
- `email_recipients` - To/CC/BCC recipients
- `drafts` - Draft emails

### 2. Chat Server (Port 8001)
**Location**: `src/virtualoffice/servers/chat/`

**Responsibilities**:
- Chat room management
- Direct message (DM) handling
- User management
- Message storage and retrieval

**Key Files**:
- `app.py` - FastAPI application
- `models.py` - Pydantic models (RoomCreate, MessagePost, DMPost)

**Database Tables**:
- `chat_users` - Chat handles and display names
- `chat_rooms` - Chat rooms and DM channels
- `chat_members` - Room membership
- `chat_messages` - Messages within rooms

### 3. Simulation Manager (Port 8015)
**Location**: `src/virtualoffice/sim_manager/`

**Responsibilities**:
- Simulation orchestration
- Tick advancement
- Worker planning lifecycle
- Event injection
- Report generation
- Multi-project support

**Key Files**:
- `app.py` - FastAPI application (515 lines)
- `engine.py` - Core simulation engine (2360+ lines, refactored)
- `planner.py` - GPT and Stub planners (546 lines)
- `gateways.py` - HTTP clients for email/chat (110 lines)
- `schemas.py` - Pydantic models (217 lines)

**Core Modules** (`src/virtualoffice/sim_manager/core/`):
- `simulation_state.py` - State management and database operations
- `tick_manager.py` - Time progression and auto-tick functionality
- `event_system.py` - Event injection, processing, and random generation (NEW)

**Auto-Pause Methods**:
- `set_auto_pause(enabled: bool)` - Toggle auto-pause setting at runtime with comprehensive status return
- `get_auto_pause_status()` - Get detailed auto-pause status including project counts and reasoning

**Auto-Pause API Endpoints**:
- `GET /api/v1/simulation/auto-pause/status` - Get comprehensive auto-pause status with project information
- `POST /api/v1/simulation/auto-pause/toggle` - Toggle auto-pause setting and return updated status
- `GET /api/v1/simulation/auto-pause-status` - Legacy endpoint (deprecated)

**Database Tables**:
- `people` - Virtual worker personas
- `schedule_blocks` - Worker schedules
- `simulation_state` - Current tick and running status
- `project_plans` - Project roadmaps
- `project_assignments` - Person-to-project mappings
- `worker_plans` - Daily and hourly plans
- `daily_reports` - End-of-day summaries
- `simulation_reports` - End-of-simulation summaries
- `events` - Injected simulation events
- `tick_log` - Tick advancement history
- `worker_runtime_messages` - Inbox queue
- `worker_exchange_log` - Communication history
- `worker_status_overrides` - Sick leave, etc.

### 4. Virtual Workers (Enhanced)
**Location**: `src/virtualoffice/virtualWorkers/`

**Responsibilities**:
- Autonomous worker planning and decision-making
- Persona markdown generation and management
- Worker identity and behavior definition
- Context-aware planning and reporting
- Event reaction and response generation
- Integration with prompt management system

**Key Classes**:
- `WorkerPersona` - Dataclass for persona attributes
- `VirtualWorker` - Enhanced autonomous worker with planning capabilities
- `ScheduleBlock` - Time block for daily schedule
- `PlannerMixin` - Mixin providing planning methods

**Context Classes** (`context_classes.py`):
- `PlanningContext` - Hourly planning context with project, team, and communication data
- `DailyPlanningContext` - Daily planning context with timeline and team information
- `EventContext` - Event reaction context with event details and team coordination
- `ReportContext` - Daily report context with activity logs and schedules
- `EventResponse` - Structured event response with adjustments and actions

**VirtualWorker Methods**:
- `__init__(persona, prompt_manager, context_builder, planner)` - Initialize with dependencies
- `to_person_read()` - Convert to PersonRead for API compatibility
- `as_prompt(context)` - Generate prompt using PromptManager
- `plan_next_hour(context)` - Generate hourly plan autonomously
- `plan_daily(context)` - Generate daily plan autonomously
- `react_to_event(event, context)` - React to simulation events
- `generate_daily_report(context)` - Generate end-of-day report

**Key Features**:
- **Autonomous Planning**: Workers own their planning logic, not the engine
- **Type-Safe Contexts**: Structured dataclasses for all worker operations
- **Multi-Project Support**: Context includes all active projects for coordination
- **Localization**: All contexts support locale-specific processing
- **Model Hints**: Optional model override for each operation
- **Event Reactions**: Structured responses to simulation events
- **Prompt Management Integration**: Uses PromptManager for template-based prompts
- **Context Building**: Uses ContextBuilder for comprehensive context aggregation
- **Parallel Planning Ready**: Designed for concurrent execution

**Integration Status** (Phase 4.7 - Partial):
- ✅ VirtualWorker lazy imports (module-level comment clarifies strategy)
- ✅ PromptManager and ContextBuilder initialized in engine
- ✅ `self.workers` dictionary added to store VirtualWorker instances
- ✅ `_sync_virtual_workers()` method implemented with planner capability check
- ✅ Worker creation logic in `_sync_virtual_workers()` (creates VirtualWorker from PersonRead)
- ⚠️ Partial: `_to_persona_from_person_read()` helper method referenced but not yet implemented
- ⏳ Pending: Planning delegation to VirtualWorker instances
- ⏳ Pending: Update person creation to instantiate VirtualWorker
- ⏳ Pending: Delegate hourly/daily planning to workers
- ⏳ Pending: Remove old planning logic from engine

**Integration**:
- Used by `SimulationEngine` for all worker-driven operations (in progress)
- Receives dependencies via constructor injection
- Delegates prompt construction to `PromptManager`
- Delegates context building to `ContextBuilder`
- Delegates LLM calls to `Planner`
- Supports parallel planning via ThreadPoolExecutor

### 5. Localization System
**Location**: `src/virtualoffice/common/localization.py`

**Responsibilities**:
- Centralized management of all localizable strings and templates
- Korean localization support for workplace simulations
- Consistent language enforcement across AI-generated content
- Template management with variable substitution

**Key Classes**:
- `LocalizationManager` - Main localization management class
- Global convenience functions: `get_text()`, `get_korean_text()`, `get_current_locale_manager()`

**Supported Locales**:
- English (`en`) - Default locale
- Korean (`ko`) - Enhanced Korean workplace simulation support

**Key Features**:
- **Hardcoded String Management**: Centralizes all hardcoded text for consistent localization
- **Korean Language Enforcement**: Strict Korean-only content generation when `VDOS_LOCALE=ko`
- **Template System**: Localized templates with variable substitution support
- **Fallback Handling**: Graceful fallback to English if Korean strings are missing
- **Integration Ready**: Designed to integrate with existing planner and engine systems

### 6. PySide6 GUI
**Location**: `src/virtualoffice/app.py` (1197 lines)

**Responsibilities**:
- Start/stop FastAPI services individually
- Start/stop simulations with project configuration
- Manual tick advancement and automatic ticking
- Create and manage personas (with optional GPT-4o assistance)
- View real-time reports, logs, and token usage
- Monitor simulation state and worker status
- Participant selection for simulations
- **Chat monitoring and visualization**: Real-time chat interface with conversation management
- **Email monitoring and management**: Comprehensive email client with search and filtering

**Key Classes**:
- `virtualOffice` - Main window (QMainWindow) with server lifecycle management
- `SimulationDashboard` - Main dashboard widget with comprehensive controls
- `PersonDialog` - Persona creation/editing dialog with AI generation
- `RequestWorker` - Background HTTP request worker (QRunnable)
- `ServerHandle` - Server lifecycle wrapper with threading
- `WorkerSignals` - Qt signals for async communication

### 7. Web Dashboard Interface
**Location**: `src/virtualoffice/sim_manager/` (HTML/CSS/JS)

**Responsibilities**:
- Browser-based simulation monitoring and control
- Real-time chat and email visualization
- Responsive design for desktop and mobile access
- Professional messaging interface similar to Slack/Discord

**Key Files**:
- `index_new.html` - Main dashboard HTML structure with tabbed interface
- `static/css/styles.css` - Comprehensive styling with responsive design
- `static/js/dashboard.js` - JavaScript functionality for real-time updates

**Chat Client Interface Features**:
- **Two-pane layout**: Conversation sidebar and message thread view
- **Conversation management**: Rooms and Direct Messages with search and filtering
- **Message threading**: Grouped message bubbles with sender identification and timestamps
- **Real-time updates**: 3-second auto-refresh with enhanced manual refresh controls
- **Persona selection**: Dropdown to switch between different persona viewpoints
- **Responsive design**: Mobile-friendly layout with collapsible sidebar
- **Accessibility**: ARIA labels, keyboard navigation, screen reader support
- **Search functionality**: Global conversation search with highlighting
- **Enhanced refresh controls**: Loading states, error handling, and retry mechanisms
- **Keyboard shortcuts**: R (refresh conversations), M (refresh messages)
- **New message indicators**: Visual indicators when new messages arrive
- **State persistence**: Maintains conversation selection across refreshes
- **Performance optimization**: Caching and virtual scrolling for large conversations

**Email Client Interface Features**:
- **Inbox/Sent management**: Separate views for received and sent emails
- **Email threading**: Grouped conversations with subject-based threading
- **Search and filtering**: Real-time search with highlighting and result navigation
- **Responsive layout**: Optimized for various screen sizes
- **Performance optimization**: Caching and virtual scrolling for large email lists
- **Keyboard navigation**: Full keyboard support for accessibility

**Key Features**:
- Real-time log viewing with auto-refresh
- Token usage tracking and display
- Multi-tab report viewing (daily, simulation, hourly plans, events)
- Participant inclusion/exclusion controls
- Department head selection
- Random seed configuration for reproducible simulations
- **Chat Client Interface**: Professional messaging interface with conversation sidebar and message threading
- **Email Client Interface**: Comprehensive email management with inbox/sent folders and search capabilities

## Data Flow

### Refactored Simulation Lifecycle

```mermaid
sequenceDiagram
    participant GUI
    participant SimManager
    participant Engine
    participant StateManager
    participant TickManager
    participant EventSystem
    participant CommsHub
    participant ProjectManager
    participant VirtualWorker
    participant PromptManager
    participant Planner
    participant EmailGW
    participant ChatGW

    GUI->>SimManager: POST /api/v1/simulation/start
    SimManager->>Engine: start(request)
    Engine->>ProjectManager: store_project_plan()
    Engine->>PromptManager: build_prompt("project_planning")
    Engine->>Planner: generate_with_messages()
    Planner-->>Engine: PlanResult
    loop For each worker
        Engine->>VirtualWorker: plan_daily(context)
        VirtualWorker->>PromptManager: build_prompt("daily_planning")
        VirtualWorker->>Planner: generate_with_messages()
        Planner-->>VirtualWorker: PlanResult
        VirtualWorker-->>Engine: PlanResult
        Engine->>VirtualWorker: plan_next_hour(context)
        VirtualWorker->>PromptManager: build_prompt("hourly_planning")
        VirtualWorker->>Planner: generate_with_messages()
        Planner-->>VirtualWorker: PlanResult
        VirtualWorker-->>Engine: PlanResult
    end
    Engine->>StateManager: set_running(true)
    Engine-->>SimManager: SimulationState
    SimManager-->>GUI: Response

    GUI->>SimManager: POST /api/v1/simulation/advance
    SimManager->>Engine: advance(ticks, reason)
    loop For each tick
        Engine->>TickManager: advance_ticks(1, reason)
        Engine->>EventSystem: process_events_for_tick(tick, people)
        EventSystem-->>Engine: event_adjustments
        loop For each worker (parallel)
            Engine->>VirtualWorker: plan_next_hour(context)
            VirtualWorker->>PromptManager: build_prompt("hourly_planning")
            VirtualWorker->>Planner: generate_with_messages()
            Planner-->>VirtualWorker: PlanResult
            VirtualWorker-->>Engine: PlanResult
            Engine->>CommsHub: schedule_from_hourly_plan()
        end
        Engine->>CommsHub: dispatch_scheduled(tick)
        CommsHub->>EmailGW: send_email()
        CommsHub->>ChatGW: send_dm()
    end
    Engine-->>SimManager: AdvanceResult
    SimManager-->>GUI: Response
```

### Module Interaction Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SimulationEngine                          │
│                   (Orchestrator Only)                        │
└───┬───────┬───────┬───────┬───────┬───────┬────────────────┘
    │       │       │       │       │       │
    ▼       ▼       ▼       ▼       ▼       ▼
┌────────┐ ┌────┐ ┌─────┐ ┌─────┐ ┌──────┐ ┌────────┐
│ State  │ │Tick│ │Event│ │Comms│ │Worker│ │Project │
│Manager │ │Mgr │ │Sys  │ │ Hub │ │Runtime│ │Manager │
└────┬───┘ └──┬─┘ └──┬──┘ └──┬──┘ └───┬──┘ └───┬────┘
     │        │      │       │        │        │
     │        │      │       │        │        │
     └────────┴──────┴───────┴────────┴────────┘
                      │
                 ┌────▼─────┐
                 │  SQLite  │
                 │ Database │
                 └──────────┘

┌─────────────────────────────────────────────────────────────┐
│                    VirtualWorker                             │
│                 (Autonomous Agent)                           │
└───┬───────────────┬─────────────────────────────────────────┘
    │               │
    ▼               ▼
┌────────────┐  ┌──────────┐
│  Prompt    │  │ Context  │
│  Manager   │  │ Builder  │
└─────┬──────┘  └────┬─────┘
      │              │
      └──────┬───────┘
             │
        ┌────▼────┐
        │ Planner │
        │ (LLM)   │
        └─────────┘
```

### Message Routing

1. **Outbound**: Engine → Gateway → Server → Database
2. **Inbound**: Database → Server → Gateway → Engine → Worker Inbox
3. **Processing**: Worker drains inbox → Planner generates response → Engine sends replies

### Planning Hierarchy

```
Project Plan (once per simulation)
    ↓
Daily Plan (once per worker per day)
    ↓
Hourly Plan (each tick when messages arrive or reason changes)
    ↓
Daily Report (end of each day)
    ↓
Simulation Report (end of simulation)
```

## Database Schema

### Core Tables

#### people
Stores virtual worker personas.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| name | TEXT | Worker name |
| role | TEXT | Job title |
| timezone | TEXT | IANA timezone |
| work_hours | TEXT | e.g., "09:00-18:00" |
| break_frequency | TEXT | e.g., "50/10 cadence" |
| communication_style | TEXT | Communication preferences |
| email_address | TEXT | Email address |
| chat_handle | TEXT | Chat username |
| is_department_head | INTEGER | 0 or 1 |
| skills | TEXT | JSON array |
| personality | TEXT | JSON array |
| objectives | TEXT | JSON array |
| metrics | TEXT | JSON array |
| persona_markdown | TEXT | Full persona spec |
| planning_guidelines | TEXT | JSON array |
| event_playbook | TEXT | JSON object |
| statuses | TEXT | JSON array |
| created_at | TEXT | Timestamp |

#### simulation_state
Single-row table tracking simulation state.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Always 1 |
| current_tick | INTEGER | Current simulation tick |
| is_running | INTEGER | 0 or 1 |
| auto_tick | INTEGER | 0 or 1 |

#### project_plans
Multi-project support with timeline awareness.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| project_name | TEXT | Project name |
| project_summary | TEXT | Project summary |
| plan | TEXT | Generated project plan |
| generated_by | INTEGER | FK to people.id |
| duration_weeks | INTEGER | Project duration in weeks |
| start_week | INTEGER | Week project starts (1-indexed, default: 1) |
| model_used | TEXT | LLM model name |
| tokens_used | INTEGER | Token count |
| created_at | TEXT | Timestamp |

**Timeline Logic**:
- Project active during weeks: `start_week` to `start_week + duration_weeks - 1`
- Example: `start_week=1, duration_weeks=3` → active weeks 1, 2, 3

#### project_assignments
Person-to-project assignments for multi-project scenarios.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| project_id | INTEGER | FK to project_plans.id |
| person_id | INTEGER | FK to people.id |
| UNIQUE(project_id, person_id) | | Prevents duplicate assignments |

**Assignment Logic**:
- If project has assignments: only assigned people work on it
- If project has NO assignments: everyone works on it (company-wide project)

#### project_chat_rooms
Project group chat room lifecycle management.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| project_id | INTEGER | FK to project_plans.id |
| room_slug | TEXT | Chat room slug (e.g., "project-1-dashboard-mvp") |
| room_name | TEXT | Display name (e.g., "Dashboard MVP Team") |
| is_active | INTEGER | 1 if active, 0 if archived |
| created_at | TEXT | Room creation timestamp |
| archived_at | TEXT | Room archival timestamp (NULL if active) |

**Room Naming Convention**:
- Slug: `project-{id}-{name-lowercase-with-dashes}`
- Name: `{project_name} Team`

#### worker_plans
Daily and hourly plans.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| person_id | INTEGER | FK to people.id |
| tick | INTEGER | Tick or day index |
| plan_type | TEXT | 'daily' or 'hourly' |
| content | TEXT | Plan text |
| model_used | TEXT | LLM model name |
| tokens_used | INTEGER | Token count |
| context | TEXT | Additional context |
| created_at | TEXT | Timestamp |

### Communication Tables

#### emails (Email Server)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| sender | TEXT | From address |
| subject | TEXT | Subject line |
| body | TEXT | Email body |
| thread_id | TEXT | Thread identifier |
| sent_at | TEXT | Timestamp |

#### chat_messages (Chat Server)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| room_id | INTEGER | FK to chat_rooms.id |
| sender | TEXT | Chat handle |
| body | TEXT | Message content |
| sent_at | TEXT | Timestamp |

## Communication Patterns

### Deduplication
Engine tracks sent messages to prevent duplicates:
- `_sent_dedup`: Set of (tick, channel, sender, recipients, subject, body)
- `_last_contact`: Dict of (channel, sender, recipient) → last tick
- `_contact_cooldown_ticks`: Minimum ticks between contacts (default 10)

### Scheduled Communications
Hourly plans can include scheduled communications:

**Format**:
```
Email at 10:30 to dev cc pm, designer: Subject | Body text
Chat at 14:00 with designer: Message text
```

**Processing**:
1. Planner generates hourly plan with scheduled comms
2. Engine parses scheduled comm lines
3. Engine dispatches at specified ticks
4. Fallback sends occur if no scheduled comms exist

### Acknowledgements
When a worker receives a message:
1. Message added to inbox
2. On next planning cycle, inbox drained
3. Worker sends chat acknowledgement to sender
4. Acknowledgement queued in sender's inbox

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VDOS_EMAIL_HOST` | 127.0.0.1 | Email server host |
| `VDOS_EMAIL_PORT` | 8000 | Email server port |
| `VDOS_CHAT_HOST` | 127.0.0.1 | Chat server host |
| `VDOS_CHAT_PORT` | 8001 | Chat server port |
| `VDOS_SIM_HOST` | 127.0.0.1 | Simulation server host |
| `VDOS_SIM_PORT` | 8015 | Simulation server port |
| `VDOS_SIM_BASE_URL` | http://127.0.0.1:8015 | Full simulation base URL |
| `VDOS_DB_PATH` | src/virtualoffice/vdos.db | Database path |
| `VDOS_DB_URL` | sqlite:///./vdos.db | Database connection URL |
| `VDOS_TICK_MS` | 50 | Wall-clock milliseconds per tick |
| `VDOS_BUSINESS_DAYS` | 5 | Default simulation duration |
| `VDOS_WORKDAY_START` | 09:00 | Business hours start |
| `VDOS_WORKDAY_END` | 18:00 | Business hours end |
| `VDOS_DEFAULT_BREAK_PATTERN` | 25/5,90/lunch/60 | Work/break rhythm |
| `VDOS_LOCALE_TZ` | Asia/Seoul | Timezone for simulation |
| `VDOS_SIM_EMAIL` | simulator@vdos.local | Simulation manager email |
| `VDOS_SIM_HANDLE` | sim-manager | Simulation manager chat handle |
| `VDOS_GUI_AUTOKILL_SECONDS` | - | Auto-shutdown for testing (optional) |
| `VDOS_PLANNER_STRICT` | 0 | Disable stub fallback |
| `VDOS_LOCALE` | en | Locale (en or ko) - Enhanced Korean support with localization system |
| `VDOS_CONTACT_COOLDOWN_TICKS` | 10 | Min ticks between contacts |
| `VDOS_MAX_HOURLY_PLANS_PER_MINUTE` | 10 | Planning rate limit |
| `VDOS_AUTO_PAUSE_ON_PROJECT_END` | true | Auto-pause when all projects complete |
| `OPENAI_API_KEY` | - | OpenAI API key (optional) |

### Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VDOS_PLANNER_PROJECT_MODEL` | gpt-4.1-nano | Project plan model |
| `VDOS_PLANNER_DAILY_MODEL` | (same as project) | Daily plan model |
| `VDOS_PLANNER_HOURLY_MODEL` | (same as daily) | Hourly plan model |
| `VDOS_PLANNER_DAILY_REPORT_MODEL` | (same as daily) | Daily report model |
| `VDOS_PLANNER_SIM_REPORT_MODEL` | (same as project) | Sim report model |

### Localization Support

VDOS provides enhanced localization support for Korean workplace simulations:

#### Korean Language Configuration
- **Environment Variable**: `VDOS_LOCALE=ko`
- **Supported Languages**: English (`en`) and Korean (`ko`)
- **Scope**: All AI-generated content including plans, messages, and reports

#### Korean Language Enforcement (October 2025 Enhancement)
When `VDOS_LOCALE=ko` is set, the system applies enhanced Korean language instructions across all AI-generated content:

**Planner Functions:**
```python
# Enhanced Korean system message (applied to all planner functions)
"모든 응답을 자연스러운 한국어로만 작성하세요. 영어 단어나 표현을 절대 사용하지 마세요. 
한국 직장에서 실제로 사용하는 자연스럽고 간결한 말투로 작성하세요. 
예: '개발 환경 설정' (O), 'development environment setup' (X)"
```

**Persona Generation:**
```python
# Korean persona generation system message
"한국 직장 시뮬레이션을 위한 JSON 페르소나를 생성합니다. 
모든 텍스트 필드는 자연스러운 한국어로만 작성하세요. 영어 단어나 표현을 절대 사용하지 마세요. 
실제 한국 직장인처럼 현실적으로 작성하세요. AI나 시뮬레이션에 대한 언급은 하지 마세요."
```

#### Localization Features
- **Natural Korean Communication**: Workplace-appropriate Korean language patterns
- **Mixed Language Prevention**: Strict enforcement against English/Korean mixing
- **Context-Aware Examples**: Specific examples of correct Korean terminology
- **Consistent Application**: Applied across all AI-powered functions:
  - **Planner Functions**: Project planning, daily planning, hourly planning, daily reports, simulation reports, communication drafting
  - **Persona Generation**: AI-assisted persona creation with Korean workplace context
  - **Fallback Handling**: Korean-localized stub personas when AI is unavailable
- **Locale-Specific Defaults**: Korean personas use `Asia/Seoul` timezone, `09:00-18:00` work hours, and Korean workplace terminology

#### Korean Simulation Scripts
Several Korean-specific simulation scripts demonstrate localized behavior:
- `mobile_chat_simulation_ko.py` - 4-week Korean mobile app simulation
- `short_blog_simulation_ko.py` - 5-day Korean blog simulation with `KoreanGPTPlanner`
- `multi_project_simulation_ko.py` - Multi-project Korean simulation
- `test_*_ko.py` scripts - Various Korean test scenarios

#### Localization Infrastructure
The localization system provides centralized management of all localizable content:

**LocalizationManager Class**:
```python
from virtualoffice.common.localization import LocalizationManager, get_current_locale_manager

# Initialize with specific locale
manager = LocalizationManager("ko")

# Get localized text
header = manager.get_text("scheduled_communications")  # Returns "예정된 커뮤니케이션"

# Get current locale manager (uses VDOS_LOCALE env var)
current_manager = get_current_locale_manager()
```

**Supported Localization Keys**:
- **Planner strings**: `scheduled_communications`, `live_collaboration_adjustments`
- **Status vocabulary**: `status_working`, `status_away`, `status_off_duty`, etc.
- **Client feature requests**: `client_feature_requests` (array of localized feature descriptions)
- **Communication templates**: `email_subject_update`, `chat_greeting`, etc.
- **Project terminology**: `project_milestone`, `project_deadline`, `project_task`, etc.

**Integration Points**:
- **Planner Integration**: Replace hardcoded "Scheduled Communications" with localized headers
- **Engine Integration**: Replace hardcoded "Adjustments from live collaboration" text
- **Client Feature Requests**: Localized Korean feature request templates
- **Future Extensions**: Ready for integration with persona generation and other AI components

## Threading Model

### GUI Application
- Main thread: Qt event loop
- Background threads: HTTP requests via `RequestWorker` (QRunnable)
- Thread pool: `QThreadPool.globalInstance()`

### Simulation Engine
- Main thread: FastAPI event loop
- Auto-tick thread: Optional background thread for automatic advancement
- Auto-pause: Intelligent stopping when all projects complete (configurable)
- Lock: `_advance_lock` prevents concurrent tick advancement

## Error Handling

### Planner Fallback
When `GPTPlanner` fails:
1. Log error and duration
2. If `VDOS_PLANNER_STRICT=1`, raise RuntimeError
3. Otherwise, fall back to `StubPlanner`
4. Record fallback in `_planner_metrics`

### Service Startup
- GUI attempts server startup with 5-second timeout
- If startup fails, error displayed in dashboard
- Services can be restarted independently

### API Errors
- 400 Bad Request: Invalid input
- 404 Not Found: Resource missing
- 422 Unprocessable Entity: Validation error
- 500 Internal Server Error: Server failure

## Performance Considerations

### Rate Limiting
- Hourly planning: Max 10 plans per person per minute
- Contact cooldown: 10 ticks between same sender/recipient pairs

### Auto-Pause on Project Completion
When `VDOS_AUTO_PAUSE_ON_PROJECT_END=true` (default), the simulation automatically pauses auto-tick when:
- No projects are currently active in the current simulation week
- No projects are scheduled to start in future weeks

This prevents simulations from running indefinitely after all work is completed, providing intelligent lifecycle management. The auto-pause setting can be toggled at runtime via the `set_auto_pause()` method, which overrides the environment variable for the current session.

**Enhanced Implementation Features:**
- **Session-level configuration**: Runtime toggle overrides environment variable for current session
- **Comprehensive status reporting**: Detailed project status, counts, and pause reasoning
- **Enhanced project lifecycle calculations**: Accurate week calculation with edge case handling
- **Multi-project scenario handling**: Supports overlapping, sequential, and gap scenarios
- **Comprehensive logging**: Detailed auto-pause events with project information
- **Error handling**: Graceful fallback with detailed error messages and safe defaults
- **API endpoints**: REST endpoints for status checking and runtime configuration
- **Frontend integration**: JavaScript functions for UI interaction and real-time updates
- **Backward compatibility**: Legacy endpoint maintained, environment variable still respected

**Project Lifecycle Calculations:**
- **Current week**: `max(1, ((current_tick - 1) // hours_per_day // 5) + 1)`
- **Project end week**: `start_week + duration_weeks - 1`
- **Active projects**: Projects where `start_week <= current_week <= end_week`
- **Future projects**: Projects where `start_week > current_week`
- **Auto-pause trigger**: `active_projects == 0 AND future_projects == 0`

**Logging and Debugging:**
- Comprehensive auto-pause trigger logging with project details
- Frontend console logging for debugging UI interactions
- State change detection and logging for active/future project counts
- Error logging with fallback to prevent simulation halt

**Testing and Validation:**
- **Integration Testing**: Complete end-to-end workflow validation in `tests/test_auto_pause_integration.py`
- **Multi-Project Scenarios**: Comprehensive testing of overlapping, sequential, and gap project timelines
- **API Endpoint Testing**: Full validation of request/response handling and error cases
- **State Persistence**: Testing of session-level configuration changes and persistence
- **Error Handling**: Edge case testing and graceful degradation validation
- **Future Project Detection**: Testing that future projects prevent premature auto-pause
- **Auto-Tick Integration**: Validation that auto-pause correctly stops auto-tick when triggered

### Caching
- Project plan cached in `_project_plan_cache`
- Worker runtimes cached in `_worker_runtime`
- Status overrides cached in `_status_overrides`

### Database
- Single SQLite file for all services
- Indices on frequently queried columns
- Foreign key constraints for referential integrity

## Extensibility

### Adding New Planning Methods
1. Add method to `Planner` protocol in `planner.py`
2. Implement in both `GPTPlanner` and `StubPlanner`
3. Call via `engine._call_planner()`

**Direct Prompt Generation**:
The `Planner` protocol supports direct prompt generation via `generate_with_messages()`:
```python
# Build messages externally (e.g., using PromptManager)
messages = [
    {"role": "system", "content": "You are a helpful assistant..."},
    {"role": "user", "content": "Generate a plan for..."}
]

# Generate using pre-built messages
result = planner.generate_with_messages(
    messages=messages,
    model_hint="gpt-4o"
)
```
This allows integration with external prompt management systems and advanced prompt engineering workflows.

### Adding New Events
1. Create event payload in `EventCreate` schema
2. Inject via `engine.inject_event()`
3. Process in `engine._maybe_generate_events()`

### Adding New Reports
1. Add database table for report type
2. Add Pydantic schema in `schemas.py`
3. Add API endpoint in `app.py`
4. Implement generation in `engine.py`


## Testing Infrastructure

VDOS includes a comprehensive testing infrastructure organized into multiple layers to ensure reliability, correctness, and performance across all components.

### Test Suite Organization

```
tests/
├── conftest.py                          # Shared fixtures and configuration
├── test_*.py                            # Unit tests for individual components
├── integration/                         # Integration tests (Phase 5)
│   ├── __init__.py                     # Integration test package
│   ├── test_long_simulation.py         # Extended simulation tests
│   └── test_multi_project.py           # Multi-project scenario tests
└── performance/                         # Performance benchmarks (Phase 5)
    ├── test_tick_advancement.py        # Tick advancement performance
    ├── test_parallel_planning.py       # Parallel planning benchmarks
    ├── test_memory_usage.py            # Memory profiling
    └── test_template_loading.py        # Template caching performance
```

### Unit Tests

**Location**: `tests/test_*.py`

**Coverage**:
- Email server endpoints (`test_email_server.py`)
- Chat server endpoints (`test_chat_server.py`)
- Simulation manager (`test_sim_manager.py`)
- Virtual workers (`test_virtual_worker.py`, `test_virtual_worker_enhanced.py`)
- Auto-pause functionality (`test_auto_pause_unit.py`, `test_auto_pause_integration.py`)
- Core modules (SimulationState, TickManager, EventSystem, etc.)

**Characteristics**:
- Fast execution (< 1 second per test)
- Isolated from external dependencies
- Use mocks and stubs for external services
- ASGI TestClient for FastAPI endpoint testing
- Comprehensive coverage (>90% target)

### Integration Tests

**Location**: `tests/integration/`

**Purpose**: Validate that refactored modules work together correctly and produce valid simulation output.

#### test_long_simulation.py

Tests extended simulation scenarios:

**Test Cases**:
- `test_one_week_english_simulation()` - 1-week simulation in English locale
- `test_one_week_korean_simulation()` - 1-week simulation in Korean locale
- `test_four_week_multi_project_simulation()` - 4-week multi-project scenario
- `test_simulation_output_validation()` - Output structure validation

**Validation**:
- Simulation completes without errors
- All workers generate plans and reports
- Communications are generated
- Locale-specific content is correct
- Output structure is valid

#### test_multi_project.py

Tests multi-project coordination:

**Test Cases**:
- `test_two_project_scenario_with_five_workers()` - 2 projects with 5 workers
- `test_project_completion_and_auto_pause()` - Auto-pause on completion
- `test_refactored_modules_integration()` - Module integration validation

**Validation**:
- Multiple projects run concurrently
- Workers coordinate across projects
- Auto-pause triggers correctly
- All refactored modules integrate properly
- Event injection works across projects

**Key Features**:
- Uses temporary databases for isolation
- Stub planners for deterministic output
- Test gateways for service communication
- Comprehensive state validation

### Performance Tests

**Location**: `tests/performance/`

**Purpose**: Benchmark performance and identify bottlenecks in the refactored engine.

#### test_tick_advancement.py

**Benchmarks**:
- Single tick advancement speed
- Batch tick advancement (10, 100, 1000 ticks)
- Tick advancement with multiple workers
- Comparison with baseline performance

**Metrics**:
- Ticks per second
- Average tick duration
- Memory usage per tick
- Regression detection

**Target**: No performance regression from original engine

#### test_parallel_planning.py

**Benchmarks**:
- Sequential vs parallel planning
- Speedup with 2, 4, 8 workers
- Thread pool efficiency
- Overhead measurement

**Metrics**:
- Planning duration per worker
- Total planning time
- Speedup factor
- Thread utilization

**Target**: 2-4x speedup with parallel planning

#### test_memory_usage.py

**Profiling**:
- Memory usage during long simulations
- Memory growth over time
- Peak memory consumption
- Memory leaks detection

**Metrics**:
- Memory per tick
- Memory per worker
- Memory per message
- Garbage collection frequency

**Target**: Similar or better memory usage than original engine

#### test_template_loading.py

**Benchmarks**:
- Template loading time
- Template caching effectiveness
- Cache hit rate
- Memory overhead of caching

**Metrics**:
- Load time per template
- Cache hit percentage
- Memory per cached template
- Reload time after cache clear

**Target**: Fast template loading with effective caching

### Test Execution

#### Run All Tests
```bash
pytest tests/
```

#### Run Specific Test Suites
```bash
# Unit tests only
pytest tests/test_*.py

# Integration tests only
pytest tests/integration/

# Performance tests only
pytest tests/performance/

# Specific test file
pytest tests/integration/test_long_simulation.py -v
```

#### Run with Coverage
```bash
pytest tests/ --cov=src/virtualoffice --cov-report=html
```

#### Run with Markers
```bash
# Run only fast tests
pytest tests/ -m "not slow"

# Run only integration tests
pytest tests/integration/
```

### Test Fixtures and Utilities

**conftest.py**:
- Shared fixtures for database setup
- Test client factories
- Mock service gateways
- Temporary directory management
- Environment variable configuration

**Common Patterns**:
- `@pytest.fixture` for reusable test components
- `TestClient` for FastAPI endpoint testing
- `monkeypatch` for environment variable mocking
- `tmp_path` for temporary file operations
- Context managers for database reloading

### Continuous Integration

**Test Requirements**:
- All tests must pass before merge
- Code coverage must be >90%
- No performance regressions
- Integration tests validate end-to-end workflows
- Performance tests benchmark critical paths

**CI Pipeline**:
1. Run unit tests (fast feedback)
2. Run integration tests (validate workflows)
3. Run performance tests (detect regressions)
4. Generate coverage report
5. Validate documentation

### Testing Best Practices

**Unit Tests**:
- Test one thing at a time
- Use descriptive test names
- Arrange-Act-Assert pattern
- Mock external dependencies
- Fast execution (<1s per test)

**Integration Tests**:
- Test realistic scenarios
- Use temporary databases
- Validate complete workflows
- Check output structure
- Test error handling

**Performance Tests**:
- Establish baselines
- Measure consistently
- Detect regressions
- Profile bottlenecks
- Document targets

### Test Coverage Goals

**Phase 5 Targets**:
- Overall coverage: >90%
- Core modules: >95%
- Integration tests: All critical workflows
- Performance tests: All critical paths
- Regression tests: All bug fixes

**Current Status**:
- Unit tests: ✅ Comprehensive coverage
- Integration tests: ✅ Phase 5 complete
- Performance tests: ⏳ Phase 5 in progress
- Auto-pause tests: ✅ Complete
- VirtualWorker tests: ✅ Complete

## Related Documentation

- **Testing Workflow**: `docs/workflows/testing.md` - Comprehensive testing guide
- **Module Documentation**: `docs/modules/` - Individual module documentation
- **Integration Guide**: `agent_reports/20251028_PHASE4_INTEGRATION_GUIDE.md` - Phase 4 integration
- **Phase 5 Tasks**: `.kiro/specs/engine-refactoring/tasks.md` - Refactoring task list
