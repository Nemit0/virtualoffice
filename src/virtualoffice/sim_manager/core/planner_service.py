from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..planner import PlanResult, Planner, PlanningError, StubPlanner
from .metrics import MetricsRecorder


class PlannerService:
    """Wraps planner calls with fallback + metrics recording.

    This service centralizes error handling, optional strict mode, and
    emits uniform metrics entries for UI/monitoring.
    """

    def __init__(
        self,
        *,
        planner: Planner,
        stub_planner: Planner | None = None,
        strict: bool = False,
        metrics: MetricsRecorder | None = None,
        max_metrics: int = 200,
    ) -> None:
        self._planner = planner
        self._stub = stub_planner or StubPlanner()
        self._strict = bool(strict)
        self._metrics = metrics or MetricsRecorder(maxlen=max_metrics)

    @property
    def metrics(self) -> MetricsRecorder:
        return self._metrics

    def get_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._metrics.list(limit)

    def call(self, method_name: str, **kwargs) -> PlanResult:
        planner = self._planner
        method = getattr(planner, method_name)
        planner_name = planner.__class__.__name__
        fallback_name = self._stub.__class__.__name__
        context = self._summarize_context(kwargs)
        start = time.perf_counter()
        try:
            result = method(**kwargs)
        except PlanningError as exc:
            duration = time.perf_counter() - start
            if isinstance(planner, StubPlanner):
                # If the planner itself is a stub and failed, surface immediately
                self._metrics.append(
                    self._entry(
                        method_name,
                        planner_name,
                        planner_name,
                        duration,
                        model=getattr(exc, "model_used", "unknown"),
                        fallback=False,
                        error=str(exc),
                        context=context,
                    )
                )
                raise
            if self._strict:
                self._metrics.append(
                    self._entry(
                        method_name,
                        planner_name,
                        planner_name,
                        duration,
                        model="unknown",
                        fallback=False,
                        error=str(exc),
                        context=context,
                    )
                )
                raise RuntimeError(f"Planning failed ({method_name}): {exc}") from exc
            # Fallback to stub
            fallback_method = getattr(self._stub, method_name)
            fb_start = time.perf_counter()
            fb_result = fallback_method(**kwargs)
            fb_duration = time.perf_counter() - fb_start
            self._metrics.append(
                self._entry(
                    method_name,
                    planner_name,
                    fallback_name,
                    duration,
                    model=getattr(fb_result, "model_used", "vdos-stub"),
                    fallback=True,
                    fallback_duration=fb_duration,
                    error=str(exc),
                    context=context,
                )
            )
            return fb_result
        else:
            duration = time.perf_counter() - start
            self._metrics.append(
                self._entry(
                    method_name,
                    planner_name,
                    planner_name,
                    duration,
                    model=getattr(result, "model_used", "unknown"),
                    fallback=False,
                    context=context,
                )
            )
            return result

    # --- helpers ---
    def _summarize_context(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        worker = kwargs.get("worker")
        if worker is not None:
            summary["worker"] = getattr(worker, "name", worker)
        department_head = kwargs.get("department_head")
        if department_head is not None:
            summary["department_head"] = getattr(department_head, "name", department_head)
        project_name = kwargs.get("project_name")
        if project_name:
            summary["project_name"] = project_name
        day_index = kwargs.get("day_index")
        if day_index is not None:
            summary["day_index"] = day_index
        tick = kwargs.get("tick")
        if tick is not None:
            summary["tick"] = tick
        model_hint = kwargs.get("model_hint")
        if model_hint:
            summary["model_hint"] = model_hint
        return summary

    def _entry(
        self,
        method: str,
        planner: str,
        result_planner: str,
        duration: float,
        *,
        model: str,
        fallback: bool,
        context: dict[str, Any],
        fallback_duration: float | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "planner": planner,
            "result_planner": result_planner,
            "model": model,
            "duration_ms": round(duration * 1000, 2),
            "fallback_duration_ms": round(fallback_duration * 1000, 2) if fallback_duration is not None else None,
            "fallback": fallback,
            "error": error,
            "context": context,
        }

