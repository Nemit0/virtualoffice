#!/usr/bin/env python3
"""
Flush all VDOS local state (DB + artifacts).

This script removes the shared SQLite database and clears common
artifact directories so you can start from a completely clean slate.

What it does:
- Resolves DB path via virtualoffice.common.db (honors VDOS_DB_PATH)
- Deletes the DB file if present
- Clears simulation_output/ and logs/ folders (optional flags)

Usage:
  python flush_all_files.py            # delete DB only
  python flush_all_files.py --all      # DB + simulation_output + logs
  python flush_all_files.py --outputs  # only simulation_output
  python flush_all_files.py --logs     # only logs

Note: Stop any running Email/Chat/Sim servers first.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Ensure local src/ is on path so we can import virtualoffice
ROOT = Path(__file__).parent
SRC_DIR = ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

try:
    from virtualoffice.common import db as vdos_db
except Exception as exc:
    raise SystemExit(f"Unable to import virtualoffice.common.db: {exc}")

OUT_DIR = ROOT / "simulation_output"
LOG_DIR = ROOT / "logs"


def rm(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink(missing_ok=True)  # type: ignore[arg-type]
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except Exception as exc:
        print(f"WARN: Failed to remove {path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Flush VDOS local state")
    parser.add_argument("--all", action="store_true", help="Delete DB + outputs + logs")
    parser.add_argument("--outputs", action="store_true", help="Delete simulation_output only")
    parser.add_argument("--logs", action="store_true", help="Delete logs only")
    args = parser.parse_args()

    if not (args.all or args.outputs or args.logs):
        # default: DB only
        db_path = Path(getattr(vdos_db, "DB_PATH"))
        print(f"Deleting DB: {db_path}")
        rm(db_path)
        return

    if args.all or args.outputs:
        print(f"Deleting outputs: {OUT_DIR}")
        rm(OUT_DIR)
    if args.all or args.logs:
        print(f"Deleting logs: {LOG_DIR}")
        rm(LOG_DIR)
    if args.all:
        db_path = Path(getattr(vdos_db, "DB_PATH"))
        print(f"Deleting DB: {db_path}")
        rm(db_path)


if __name__ == "__main__":
    main()
