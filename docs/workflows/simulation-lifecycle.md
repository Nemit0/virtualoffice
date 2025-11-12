# Simulation Lifecycle

This guide explains how a simulation run flows through the modular engine after the refactor.

Overview
- Facade: `SimulationEngine` wires and delegates to core modules.
- Lifecycle: `core/lifecycle.py` manages start/stop/reset, auto‑ticks, and auto‑pause.
- Planning: `core/planning_orchestrator.py` coordinates daily/hourly planning, summaries, and reports.
- Planner calls: `core/planner_service.py` handles strict/fallback and metrics.
- Persistence: `core/*_repository.py`, `core/*_store.py` manage all DB I/O.

Phases
1) Start
- Engine parses request, stores model hint + duration.
- Lifecycle seeds RNG, resets runtime/overrides, resolves active people.
- Projects initialized (single or multi) via Engine callback → `ProjectManager`.
- Mark running, set base datetime, sync runtimes, and schedule kickoff comms.

2) Advance (manual or auto)
- `TickManager` increments tick (auto or manual) and acquires lock.
- Engine computes current week and gathers active projects/persons.
- Planning Orchestrator runs per person:
  - Ensure daily plan (day boundary)
  - Generate hourly plan (with adjustments and recent email threads)
  - Persist plans to `PlanStore`
  - Parse and schedule explicit comms via `CommunicationHub`
- End of hour: generate hourly summaries (`ReportStore`).
- End of day: generate daily reports (`ReportStore`).

3) Auto‑pause
- Lifecycle computes status: no active or future projects → should pause.
- `TickManager` uses this to stop auto‑ticks and archive project chat rooms.

4) Stop
- Lifecycle stops auto‑ticks, generates end‑of‑run simulation report, and clears running state.

5) Reset / Full Reset
- Reset: clears simulation artifacts (plans, reports, events, runtime), preserves people.
- Full Reset: destructive cleanup of sim + email/chat tables.

Key Endpoints (served by `sim_manager/app.py`)
- State: `GET /api/v1/simulation`
- Start: `POST /api/v1/simulation/start`
- Advance: `POST /api/v1/simulation/advance {ticks, reason}`
- Auto‑ticks: `POST /api/v1/simulation/ticks/start`, `POST /api/v1/simulation/ticks/stop`
- Auto‑pause: `GET /api/v1/simulation/auto-pause/status`, `POST /api/v1/simulation/auto-pause/toggle {enabled}`
- Reset: `POST /api/v1/simulation/reset`, `POST /api/v1/simulation/full-reset`
- Metrics: `GET /api/v1/metrics/planner`

Data Flow
- Plans: `PlanStore → worker_plans`
- Hourly summaries: `ReportStore → hourly_summaries`
- Daily reports: `ReportStore → daily_reports`
- Simulation reports: `ReportStore → simulation_reports`
- Project plans: `ProjectManager → project_plans (+ project_assignments)`

Notes
- VirtualWorker is preferred when planner supports `generate_with_messages`; otherwise PlannerService is used directly.
- All planner calls are visible in metrics for troubleshooting and optimization.

---

## Mermaid Overview

```mermaid
flowchart TD
    A[Start Request\nPOST /simulation/start] --> B[Engine.start]\n
    subgraph Init[Initialization]
      B --> C[Seed RNG\nresolve active people]
      C --> D[Generate Project Plan\nPlannerService -> OpenAI]
      D --> E[Persist Plan\nproject_plans + assignments]
      E --> F[Mark Running\nset base datetime]
      F --> G[Sync Worker Runtimes\nbootstrap channels]
    end

    G --> H{Advance Tick\nmanual or auto}

    subgraph Tick[Per Tick]
      H --> I[Compute week/day/hour]
      I --> J[Ensure Daily Plan]
      J --> K[Generate Hourly Plan]
      K --> L[Persist Plans\nPlanStore]
      L --> M[Dispatch Comms\nCommunicationHub -> Email/Chat]
      M --> N[Summaries/Reports\nReportStore]
      N --> O{Auto‑pause?}
      O -- no --> H
    end

    O -- yes --> P[Stop Auto‑ticks]
    P --> Q[Paused]

    Q --> R[Stop]
    R --> S[Reset or Full Reset]
    S --> T[Idle]
```
