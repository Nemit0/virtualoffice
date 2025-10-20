# VDOS Documentation Index

## Created Documentation Files

This documentation was generated on 2025-10-17 to provide a comprehensive guide to the Virtual Department Operations Simulator (VDOS) codebase.

### Core Documentation

#### 1. Main README
**File**: `docs/README.md`

**Contains**:
- Project overview and quick start guide
- Architecture diagram (text-based)
- Table of contents with links to all docs
- Installation instructions
- Quick examples for GUI and headless usage
- Core concepts explanation
- Development workflow guide

#### 2. Architecture Documentation
**File**: `docs/architecture.md`

**Contains**:
- System architecture overview with diagrams
- Component architecture for all 5 main modules:
  - Email Server (Port 8000)
  - Chat Server (Port 8001)
  - Simulation Manager (Port 8015)
  - Virtual Workers
  - PySide6 GUI
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
├── modules/                                   # Module documentation (directory created)
│   ├── email-server.md                       # (To be created)
│   ├── chat-server.md                        # (To be created)
│   ├── sim-manager.md                        # (To be created)
│   ├── virtual-workers.md                    # (To be created)
│   ├── gui-app.md                            # (To be created)
│   └── utils.md                              # (To be created)
├── api/                                       # API documentation (directory created)
│   ├── email-api.md                          # (To be created)
│   ├── chat-api.md                           # (To be created)
│   └── sim-manager-api.md                    # (To be created)
├── workflows/                                 # Workflow documentation (directory created)
│   ├── simulation-lifecycle.md               # (To be created)
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

### For API Integration
If you're integrating with VDOS services:
1. `docs/architecture.md` - Understand the service architecture
2. `docs/api/email-api.md` - Email server endpoints (to be created)
3. `docs/api/chat-api.md` - Chat server endpoints (to be created)
4. `docs/api/sim-manager-api.md` - Simulation control endpoints (to be created)

### For Running Simulations
If you want to run simulations:
1. `docs/README.md#quick-start` - Get started quickly
2. `docs/workflows/simulation-lifecycle.md` - How simulations work (to be created)
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
- GUI Application: `src/virtualoffice/app.py`
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

## Additional Documentation to Create

While the core architecture and configuration documentation is complete, the following additional documentation files should be created to provide complete coverage:

### Module Documentation (`docs/modules/`)
Each module needs detailed documentation including:
- Purpose and responsibilities
- Key classes and their methods
- Configuration options
- Example usage
- Integration points

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

## Summary

The documentation infrastructure is now in place with:
- ✅ Main README with overview and quick start
- ✅ Complete architecture documentation
- ✅ Full environment variables reference
- ✅ Directory structure for all planned docs
- ⏳ Module-specific documentation (to be created)
- ⏳ API reference (to be created)
- ⏳ Workflow guides (to be created)
- ⏳ Class/function reference (to be created)
- ⏳ Scripts documentation (to be created)

The foundational documentation provides a solid understanding of the system architecture, configuration, and how components interact. Additional documentation can be created incrementally as needed.
