import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_ENV_VAR = "VDOS_DB_PATH"


def _resolve_db_path() -> Path:
    """Resolve the SQLite DB path with a strong preference for the repo path.

    Resolution order:
    1) If VDOS_DB_PATH is set, use it.
    2) Prefer the repository path <repo>/src/virtualoffice/vdos.db by scanning
       from the current working directory upwards for a "src/virtualoffice" dir.
    3) Fallback to module-adjacent path (legacy behavior).
    """
    raw_path = os.getenv(DB_ENV_VAR)
    if raw_path:
        path = Path(raw_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # Try to find a repository root that contains src/virtualoffice
    try:
        cwd = Path.cwd().resolve()
        for base in [cwd, *cwd.parents]:
            repo_dir = base / "src" / "virtualoffice"
            if repo_dir.exists():
                path = (repo_dir / "vdos.db").resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                return path
    except Exception:
        pass

    # Fallback: next to the installed module files
    path = (Path(__file__).resolve().parent.parent / "vdos.db").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


DB_PATH = _resolve_db_path()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
        timeout=30.0  # Increase timeout for concurrent access
    )
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    # Set busy timeout for better lock handling
    conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds in milliseconds
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute_script(sql: str) -> None:
    with get_connection() as conn:
        conn.executescript(sql)
