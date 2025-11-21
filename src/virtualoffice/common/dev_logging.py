"""Development session logging for `briefcase dev`.

This module mirrors stdout/stderr to a timestamped log file under `logs/` while
keeping console output unchanged. Logging is enabled by default and can be
disabled via `VDOS_DEV_LOGGING_ENABLED=false`.
"""
from __future__ import annotations

import atexit
import io
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional, TextIO


_SENSITIVE_KEYS = [
    "OPENAI_API_KEY",
    "OPENAI_API_KEY2",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
]

_CONFIG_KEYS = [
    "VDOS_CHAT_HOST",
    "VDOS_CHAT_PORT",
    "VDOS_EMAIL_HOST",
    "VDOS_EMAIL_PORT",
    "VDOS_SIM_HOST",
    "VDOS_SIM_PORT",
    "VDOS_DB_PATH",
    "VDOS_USE_OPENROUTER",
    "VDOS_CLUSTER_HOST",
    "VDOS_CLUSTER_PORT",
]

_dev_state: dict[str, object] = {}


def _is_enabled(env: Mapping[str, str]) -> bool:
    raw = env.get("VDOS_DEV_LOGGING_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes"}


def _resolve_logs_dir(env: Mapping[str, str]) -> Path:
    """Resolve the directory to write logs into."""
    if "VDOS_LOG_DIR" in env and env["VDOS_LOG_DIR"]:
        return Path(env["VDOS_LOG_DIR"]).expanduser().resolve()
    try:
        # Repo root: .../src/virtualoffice/common/dev_logging.py -> parents[3] == repo root
        return Path(__file__).resolve().parents[3] / "logs"
    except Exception:
        # Fallback to current working directory if resolution fails
        return Path.cwd() / "logs"


def _warn(original_stdout: TextIO, message: str) -> None:
    try:
        original_stdout.write(f"[VDOS-DEV-LOG] {message}\n")
        original_stdout.flush()
    except Exception:
        # If even the console write fails, there is nothing else to do.
        pass


def _format_header(
    session_label: str,
    start_time: datetime,
    cwd: Path,
    env: Mapping[str, str],
) -> str:
    lines = [
        f"===== VDOS {session_label} session =====",
        f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"CWD:   {cwd}",
        "Env:",
    ]

    for key in _CONFIG_KEYS:
        if key in env:
            lines.append(f"  {key}: {env.get(key, '')}")

    for key in _SENSITIVE_KEYS:
        if key in env:
            marker = "[set]" if env.get(key) else "[unset]"
            lines.append(f"  {key}: {marker}")

    lines.append("=" * 40)
    return "\n".join(lines) + "\n"


class TeeStream(io.TextIOBase):
    """Mirror writes to both the original stream and a log file."""

    def __init__(self, original: TextIO, log_file: TextIO) -> None:
        self._original = original
        self._log_file = log_file
        self._log_disabled = False
        self._warned = False

    @property
    def encoding(self) -> Optional[str]:
        return getattr(self._original, "encoding", None)

    @property
    def errors(self) -> Optional[str]:
        return getattr(self._original, "errors", None)

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            s = str(s)

        try:
            written = self._original.write(s)
        except Exception:
            written = 0
        try:
            if not self._log_disabled:
                self._log_file.write(s)
        except Exception as exc:  # pragma: no cover - warning path observed indirectly
            if not self._warned:
                self._warned = True
                self._log_disabled = True
                try:
                    self._original.write(
                        f"\n[VDOS-DEV-LOG] Logging to file disabled: {exc}\n"
                    )
                except Exception:
                    pass
        return written

    def flush(self) -> None:
        try:
            self._original.flush()
        finally:
            if not self._log_disabled:
                try:
                    self._log_file.flush()
                except Exception:
                    # Disable further log writes but keep console alive.
                    self._log_disabled = True

    def isatty(self) -> bool:
        return getattr(self._original, "isatty", lambda: False)()


def _close_log_file() -> None:
    tee_out = _dev_state.get("tee_stdout")
    tee_err = _dev_state.get("tee_stderr")
    log_file = _dev_state.get("log_file")
    original_out = _dev_state.get("original_stdout")
    original_err = _dev_state.get("original_stderr")

    if log_file and hasattr(log_file, "flush"):
        try:
            log_file.flush()
        except Exception:
            pass
    if log_file and hasattr(log_file, "close"):
        try:
            log_file.close()
        except Exception:
            pass

    if tee_out and sys.stdout is tee_out and original_out:
        sys.stdout = original_out  # type: ignore[assignment]
    if tee_err and sys.stderr is tee_err and original_err:
        sys.stderr = original_err  # type: ignore[assignment]

    _dev_state.clear()


def init_dev_logging(
    session_label: str = "briefcase dev",
    env: Optional[Mapping[str, str]] = None,
) -> None:
    """Initialize per-session logging for `briefcase dev`.

    Creates a timestamped log file under `logs/`, writes a session header, and
    replaces sys.stdout with a tee that mirrors output to both console and file.
    """
    env = env or os.environ

    if isinstance(sys.stdout, TeeStream) or isinstance(sys.stderr, TeeStream):
        return

    original_stdout: TextIO = sys.stdout
    original_stderr: TextIO = sys.stderr

    if not _is_enabled(env):
        return

    start_time = datetime.now()
    logs_dir = _resolve_logs_dir(env)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _warn(original_stdout, f"Could not create logs directory at {logs_dir}: {exc}")
        return

    log_filename = f"{start_time.strftime('%Y%m%d_%H%M%S')}_briefcase_dev.log"
    log_path = logs_dir / log_filename

    try:
        log_file = log_path.open("a", encoding="utf-8")
    except Exception as exc:
        _warn(original_stdout, f"Could not open log file {log_path}: {exc}")
        return

    header = _format_header(session_label, start_time, Path.cwd(), env)
    try:
        log_file.write(header)
        log_file.flush()
    except Exception as exc:
        _warn(original_stdout, f"Could not write header to log file {log_path}: {exc}")
        try:
            log_file.close()
        except Exception:
            pass
        return

    tee_stdout = TeeStream(original_stdout, log_file)
    tee_stderr = TeeStream(original_stderr, log_file)
    sys.stdout = tee_stdout  # type: ignore[assignment]
    sys.stderr = tee_stderr  # type: ignore[assignment]

    _dev_state.update(
        {
            "tee_stdout": tee_stdout,
            "tee_stderr": tee_stderr,
            "log_file": log_file,
            "log_path": log_path,
            "original_stdout": original_stdout,
            "original_stderr": original_stderr,
        }
    )

    atexit.register(_close_log_file)
