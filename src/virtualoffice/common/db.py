import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_ENV_VAR = "VDOS_DB_PATH"


def _resolve_db_path() -> Path:
    raw_path = os.getenv(DB_ENV_VAR)
    if raw_path:
        path = Path(raw_path).expanduser().resolve()
    else:
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