# Agent Guide: Spec-Driven Execution (Project-Agnostic)

This guide defines how an agent should intake requests, produce specs, and execute work via a gated, three-phase flow:

1) Requirements → 2) Design → 3) Tasks & Execution

It enforces approvals at each gate, traceability across phases, and alignment with repository conventions.


## 0) Spec Location Strategy

- Drafts directory: `.tmp/specs/<slug>/`
- Create three files in order inside each `<slug>` folder:
  - `requirements.md`
  - `design.md`
  - `tasks.md`
- Optional promotion: If your repository uses a canonical specs directory (e.g., `specs/`), copy finalized specs from `.tmp/specs/<slug>/` to that location after approvals.

Scaffold helper (if available):
- `python scripts/spec_init.py --slug <slug> --title "<Title>" [--force] [--dry-run]`
- Writes: `.tmp/specs/<slug>/{requirements.md,design.md,tasks.md}`


## 1) Intake & Scoping

- Confirm scope, constraints, stakeholders, and success criteria.
- Propose a kebab-case `<slug>` from the request title.
- Create the folder `.tmp/specs/<slug>/` (or scaffold via helper).
- Summarize the request back to the user and ask to proceed to Requirements.


## 2) Phase A — Requirements (Gate 1)

Purpose: Capture testable, implementation-agnostic requirements.

- Author `.tmp/specs/<slug>/requirements.md`.
- Use SHALL/WHEN language for objective acceptance criteria.
- Number requirements; maintain traceability to later phases.

Template:
```
# Requirements Document: <Title>

## Introduction
Brief description of the problem, motivation, and desired outcome.

## Glossary (optional)
- <Term>: <Definition>

## Requirements

### Requirement 1: <Concise Title>
**User Story:** As a <role>, I want <capability>, so that <value>.

#### Acceptance Criteria
1. WHEN <situation>, THE system SHALL <observable behavior>
2. ...

### Requirement 2: <Concise Title>
...

## Non-Goals / Out of Scope (optional)
- ...

## Constraints & Assumptions (optional)
- ...

## Risks & Mitigations (optional)
- ...

## Approvals
- Requester/Owner: [ ] Approved — name/date
- Tech Lead (if applicable): [ ] Approved — name/date
```

Gate 1 approval:
- Present a short summary and the file path.
- Request explicit approval or revisions before moving on.


## 3) Phase B — Design (Gate 2)

Purpose: Describe how requirements will be met (architecture, data shapes, interfaces, tradeoffs).

- Author `.tmp/specs/<slug>/design.md`.
- Reference requirement numbers (e.g., “Satisfies Req 3.2, 3.5”).
- Provide enough detail for another engineer to implement without guesswork.

Recommended sections:
```
# Design Document: <Title>

## Overview
Goals, non-goals, key choices, tradeoffs.

## Architecture
- High-level diagram (ASCII ok)
- Component responsibilities and collaboration

## Directory Structure
```text
src/
  └── <new or modified structure>
```

## Component Design & Interfaces
- Responsibility, method signatures, payload shapes
- Data models (Pydantic/dataclasses), errors, edge cases
- Concurrency/performance considerations

## API & Contracts (if any)
- Endpoints, schemas, status codes

## Data & Persistence
- Tables, indices, migrations, retention

## Localization/Accessibility (if relevant)

## Telemetry & Metrics (if relevant)

## Security & Compliance (if relevant)

## Testing Strategy
- Unit, integration, E2E; validation of acceptance criteria

## Rollout & Migration Plan
- Flags, incremental rollout, rollback procedure

## Open Questions
- ...

## Approvals
- Architecture/Lead: [ ] Approved — name/date
```

Gate 2 approval:
- Present a concise design summary + file path.
- Request approval or edits before moving to Tasks.


## 4) Phase C — Tasks & Execution

Purpose: Break down implementation into ordered, verifiable tasks mapped to requirements.

- Author `.tmp/specs/<slug>/tasks.md`.
- Use phases if helpful (e.g., extraction, integration, testing, docs).
- Each task includes mapping to requirement ids and a Definition of Done.

Template:
```
# Implementation Plan: <Title>

## Overview
High-level plan and current status.

### Progress Summary
- 🔄 Phase 1: <summary>

## Task List

- [ ] N.M <Task Title>
  - What: <one-liner>
  - Why: Satisfies Req <ids>
  - Steps:
    - Do A
    - Do B
  - Definition of Done:
    - Tests created/updated and passing
    - Docs updated (which files)
    - Performance/UX validated (if applicable)
  - Files/Modules:
    - `src/...`
  - Risks/Mitigations:
    - ...
```

Execution rules:
- Execute tasks in order unless dependencies change.
- After each task, check it off in `tasks.md` and add a 1–2 line result note.
- Keep PRs/commits focused per task; follow your repository’s commit conventions.


## 5) Interaction Protocol (Gated Flow)

- Start → Gather request → Confirm `<slug>` → Draft Requirements.
- Gate 1: Wait for explicit approval of `requirements.md`.
- Gate 2: Wait for explicit approval of `design.md`.
- Execute tasks from `tasks.md` step-by-step; report progress after each task.
- If scope changes, return to the appropriate phase, revise, and note changes at the top of the doc.


## 6) Quality Bar & Traceability

- Acceptance criteria must be observable and testable.
- Use clear, assertive phrasing: “WHEN …, THE system SHALL …”.
- Maintain traceability:
  - Requirements are numbered.
  - Design cites requirement numbers.
  - Tasks cite requirement numbers and design sections.
- Document edge cases and error handling; prefer typed interfaces.


## 7) Repository Conventions

- Defer to your repository’s AGENTS.md/CLAUDE.md for project-specific rules (testing, commits, security, API usage).
- Use a temp workspace (e.g., `.tmp/`) for drafts and artifacts; avoid cluttering the project root.
- Promote finalized specs from `.tmp/specs/<slug>/` to the canonical specs directory (if defined) after approvals.


## 8) Practical Workflow (Step-by-Step)

1) Intake
- Confirm scope, constraints, success criteria.
- Propose slug and path: `.tmp/specs/<slug>/`.
- Scaffold (if helper available): `python scripts/spec_init.py --slug <slug> --title "<Title>"`

2) Draft Requirements
- Write `requirements.md` from the template.
- Share a short summary and request approval.

3) Draft Design
- Write `design.md` referencing requirement numbers.
- Include architecture, interfaces, directory structure, testing strategy.
- Share summary and request approval.

4) Plan Tasks
- Write `tasks.md` with checklists and DoD per task.
- Confirm order, dependencies, and risks.

5) Execute
- Implement tasks sequentially.
- After each task: update `tasks.md`, add a result note, run tests.
- Keep changes focused; commit per task.

6) Validate & Close Out
- Re-run tests; ensure acceptance criteria are met.
- Update relevant documentation.
- Summarize outcomes and remaining risks.


## 9) Minimal Prompts for Approvals & Execution

- Requirements approval:
  - “I drafted requirements at `.tmp/specs/<slug>/requirements.md`. Approve to proceed to Design? Any edits?”

- Design approval:
  - “I drafted the design at `.tmp/specs/<slug>/design.md`. Approve to proceed to Tasks? Any edits?”

- Execution step:
  - “Tasks are in `.tmp/specs/<slug>/tasks.md`. Proceed to execute Task N.M now?”

- Scope change:
  - “New info affects scope. I will revise the [Requirements/Design], note changes, and re-seek approval.”


## 10) Validation Checklist (Before Done)

- All acceptance criteria demonstrably met.
- All tests passing; no regressions in existing suites.
- Docs updated where relevant.
- Temporary artifacts cleaned or intentionally preserved.
- Specs and tasks reflect actual outcomes (checked items, result notes).


---

This guide is project-agnostic. Always defer to repository-specific rules in AGENTS.md/CLAUDE.md when present.

