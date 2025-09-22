# Repository Guidelines

## Project Structure & Module Organization
VirtualOffice is a Briefcase-generated PySide6 app. Core UI code lives in `src/virtualoffice/app.py`, and auxiliary modules are grouped by role: `servers/` hosts background services such as `email_server.py`; `virtualWorkers/` holds simulated agent logic; `utils/` contains shared helpers like `completion_util.py` for OpenAI access. Assets bundled with the app belong under `src/virtualoffice/resources/`. Tests reside in `tests/`, mirroring package names.

## Build, Test, and Development Commands
- `python -m venv .venv && .venv\Scripts\activate` sets up the expected virtual environment.
- `python -m pip install -r requirements.txt` syncs runtime and tooling deps.
- `python -m briefcase dev` launches the desktop app in development mode.
- `briefcase build windows` packages a distributable build; swap the platform token as needed.
- `pytest` runs the unit suite in `tests/`.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation. Keep modules and functions in `snake_case`, Qt widget subclasses in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Organize imports as stdlib, third-party, then local. When touching server code, prefer FastAPI path functions that return dictionaries. Log meaningful events with the configured root logger rather than `print`.

## Testing Guidelines
Add or update `tests/test_*.py` files alongside new modules. Use pytest's fixture pattern for setup, and assert against concrete payloads (for example, serialized email records) instead of broad truthiness. Target at least one regression test per bug fix and cover new API endpoints or UI flows before submitting.

## Commit & Pull Request Guidelines
The repository has no formal history yet; adopt Conventional Commit prefixes (`feat:`, `fix:`, `chore:`) and keep messages under 72 characters in the subject. Open pull requests with a concise summary, testing notes (`pytest`, `briefcase dev`, etc.), and link to any tracking issue. Include screenshots or log excerpts when UI or server behavior changes.

## Security & Configuration Tips
Store secrets such as `OPENAI_API_KEY` in `.env` and never commit overrides. Confirm `.env` is loaded before running `completion_util.py`. Rotate generated SQLite files under `src/virtualoffice/servers/database/` when sharing artifacts, and scrub sample data that may contain user identifiers.