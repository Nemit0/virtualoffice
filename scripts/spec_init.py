#!/usr/bin/env python3
"""
Spec Scaffold Helper

Creates a spec skeleton under `.tmp/specs/<slug>/` with:
  - requirements.md
  - design.md
  - tasks.md

Usage:
  python scripts/spec_init.py --slug chat-client-interface --title "Chat Client Interface"

Options:
  --slug <slug>      Required. Kebab-case identifier for the initiative.
  --title <title>    Optional. Human-friendly title. Defaults to slug.
  --force            Overwrite existing files if they exist.
  --dry-run          Show what would be created without writing files.

Notes:
  - Files are created only under `.tmp/specs` to keep drafts out of versioned specs.
  - After approvals, you may promote the folder to `.kiro/specs/<slug>/`.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TMP_SPECS = ROOT / ".tmp" / "specs"


REQ_TMPL = """# Requirements Document: {title}

> Status: Draft — generated {ts}

## Introduction
Summarize the problem, motivation, and desired outcome for “{title}”.

## Glossary (optional)
- <Term>: <Definition>

## Requirements

### Requirement 1: <Concise Title>
**User Story:** As a <role>, I want <capability>, so that <value>.

#### Acceptance Criteria
1. WHEN <situation>, THE system SHALL <observable behavior>
2. ...

### Requirement 2: <Concise Title>
**User Story:** ...

#### Acceptance Criteria
1. ...

## Non-Goals / Out of Scope (optional)
- ...

## Constraints & Assumptions (optional)
- ...

## Risks & Mitigations (optional)
- ...

## Approvals
- Product/Requester: [ ] Approved — name/date
- Tech Lead (if applicable): [ ] Approved — name/date
"""


DESIGN_TMPL = """# Design Document: {title}

> Status: Draft — generated {ts}
> References: `.tmp/specs/{slug}/requirements.md`

## Overview
Goals, non-goals, key choices, and tradeoffs.

## Architecture
- High-level diagram (ASCII ok)
- Component responsibilities and collaboration

## Directory Structure
```text
src/virtualoffice/
  └── <new or modified structure>
```

## Component Design & Interfaces
For each component/module:
- Responsibility
- Interfaces (method signatures, payload shapes)
- Data models (Pydantic/dataclasses)
- Error handling & edge cases
- Concurrency/performance considerations

## API & Contracts (if any)
- Endpoints, schemas, status codes

## Data & Persistence
- Tables, indices, migrations, retention

## i18n/Locale & Accessibility (if relevant)

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
"""


TASKS_TMPL = """# Implementation Plan: {title}

## Overview
High-level plan and current status.

### Progress Summary
- 🔄 Phase 1: Drafting requirements/design

## Task List

- [ ] 1.0 Confirm scope and stakeholders
  - Why: Aligns success criteria and constraints (Reqs TBD)
  - DoD: Stakeholders confirmed; constraints documented in requirements

- [ ] 1.1 Draft requirements document
  - Why: Establish testable acceptance criteria
  - DoD: `.tmp/specs/{slug}/requirements.md` approved (Gate 1)

- [ ] 2.0 Draft design document
  - Why: Define architecture and interfaces mapped to requirements
  - DoD: `.tmp/specs/{slug}/design.md` approved (Gate 2)

- [ ] 3.0 Break down implementation tasks
  - Why: Plan executable steps with traceability to requirements
  - DoD: Tasks enumerated with DoD; owners assigned if applicable

- [ ] 4.x Implement features per tasks
  - Why: Deliver against approved design
  - DoD: Tests pass; acceptance criteria satisfied

- [ ] 5.0 Validate, document, and close out
  - Why: Ensure quality and maintainability
  - DoD: Tests green; docs updated; outcomes summarized
"""


def write_file(path: Path, content: str, force: bool, dry_run: bool) -> bool:
    if path.exists() and not force:
        return False
    if dry_run:
        print(f"DRY-RUN would write: {path}")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold spec files under .tmp/specs/<slug>/")
    parser.add_argument("--slug", required=True, help="kebab-case identifier, e.g., chat-client-interface")
    parser.add_argument("--title", default=None, help="Human-friendly title; defaults to slug")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing files")
    args = parser.parse_args(argv)

    slug = args.slug.strip()
    if not slug:
        print("Error: --slug is required", file=sys.stderr)
        return 2

    title = args.title.strip() if args.title else slug.replace("-", " ").title()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    dest = TMP_SPECS / slug
    paths = {
        "requirements": dest / "requirements.md",
        "design": dest / "design.md",
        "tasks": dest / "tasks.md",
    }

    created = []
    skipped = []

    # Prepare contents
    req_content = REQ_TMPL.format(title=title, ts=ts)
    design_content = DESIGN_TMPL.format(title=title, ts=ts, slug=slug)
    tasks_content = TASKS_TMPL.format(title=title, slug=slug)

    for key, path in paths.items():
        content = {"requirements": req_content, "design": design_content, "tasks": tasks_content}[key]
        if path.exists() and not args.force:
            skipped.append(str(path))
            continue
        if write_file(path, content, force=args.force, dry_run=args.dry_run):
            created.append(str(path))

    print("Spec scaffold summary:")
    print(f"  Slug: {slug}")
    print(f"  Folder: {dest}")
    if created:
        print("  Created:")
        for p in created:
            print(f"    - {p}")
    if skipped:
        print("  Skipped (exists):")
        for p in skipped:
            print(f"    - {p}")

    if not created and not skipped:
        print("  No actions performed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

