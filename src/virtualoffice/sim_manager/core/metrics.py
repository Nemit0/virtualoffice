from __future__ import annotations

import threading
from collections import deque
from typing import Any


class MetricsRecorder:
    """Thread-safe, bounded metrics recorder.

    Stores dict entries and returns the last N items on demand.
    """

    def __init__(self, *, maxlen: int = 200) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._entries.append(entry)

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            data = list(self._entries)
        if not limit or limit <= 0:
            return data
        return data[-limit:]

