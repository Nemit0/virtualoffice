"""
Metrics collection for prompt performance tracking.

Tracks prompt usage, token consumption, and performance metrics
to support A/B testing and optimization.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any
import json
from pathlib import Path


@dataclass
class PromptMetric:
    """
    Represents a single prompt usage metric.

    Attributes:
        timestamp: When the prompt was used
        template_name: Name of the template used
        variant: Variant name (e.g., "default", "verbose", "concise")
        model_used: LLM model identifier (e.g., "gpt-4o", "gpt-4o-mini")
        tokens_used: Number of tokens consumed
        duration_ms: Generation duration in milliseconds
        success: Whether generation succeeded
        error: Error message if generation failed
    """

    timestamp: datetime
    template_name: str
    variant: str
    model_used: str
    tokens_used: int
    duration_ms: float
    success: bool
    error: str | None = None


class PromptMetricsCollector:
    """
    Collects and aggregates prompt usage metrics.

    Tracks prompt performance for analysis and A/B testing,
    with support for exporting metrics to JSON.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize the metrics collector.

        Args:
            max_history: Maximum number of metrics to keep in memory
        """
        self.max_history = max_history
        self._metrics: list[PromptMetric] = []

    def record_usage(
        self,
        template_name: str,
        variant: str,
        model_used: str,
        tokens_used: int,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """
        Record a prompt usage event.

        Args:
            template_name: Name of template used
            variant: Variant name
            model_used: Model identifier
            tokens_used: Token count
            duration_ms: Generation duration in milliseconds
            success: Whether generation succeeded
            error: Optional error message
        """
        metric = PromptMetric(
            timestamp=datetime.now(),
            template_name=template_name,
            variant=variant,
            model_used=model_used,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )

        self._metrics.append(metric)

        # Trim history if needed
        if len(self._metrics) > self.max_history:
            self._metrics = self._metrics[-self.max_history :]

    def get_performance_stats(self, template_name: str) -> dict[str, Any]:
        """
        Get performance statistics for a template.

        Args:
            template_name: Name of template to analyze

        Returns:
            Dictionary with performance statistics including:
            - total_uses: Total number of uses
            - success_rate: Percentage of successful generations
            - avg_tokens: Average token consumption
            - avg_duration_ms: Average generation duration
            - total_tokens: Total tokens consumed
            - by_variant: Per-variant statistics
        """
        # Filter metrics for this template
        template_metrics = [m for m in self._metrics if m.template_name == template_name]

        if not template_metrics:
            return {
                "total_uses": 0,
                "success_rate": 0.0,
                "avg_tokens": 0,
                "avg_duration_ms": 0.0,
                "total_tokens": 0,
                "by_variant": {},
            }

        # Calculate overall stats
        total_uses = len(template_metrics)
        successful = [m for m in template_metrics if m.success]
        success_rate = (len(successful) / total_uses) * 100 if total_uses > 0 else 0.0

        total_tokens = sum(m.tokens_used for m in template_metrics)
        avg_tokens = total_tokens / total_uses if total_uses > 0 else 0

        total_duration = sum(m.duration_ms for m in template_metrics)
        avg_duration_ms = total_duration / total_uses if total_uses > 0 else 0.0

        # Calculate per-variant stats
        variants: dict[str, dict[str, Any]] = {}
        for metric in template_metrics:
            variant = metric.variant
            if variant not in variants:
                variants[variant] = {
                    "uses": 0,
                    "successes": 0,
                    "total_tokens": 0,
                    "total_duration_ms": 0.0,
                }

            variants[variant]["uses"] += 1
            if metric.success:
                variants[variant]["successes"] += 1
            variants[variant]["total_tokens"] += metric.tokens_used
            variants[variant]["total_duration_ms"] += metric.duration_ms

        # Calculate variant averages
        by_variant = {}
        for variant, stats in variants.items():
            uses = stats["uses"]
            by_variant[variant] = {
                "uses": uses,
                "success_rate": (stats["successes"] / uses * 100) if uses > 0 else 0.0,
                "avg_tokens": stats["total_tokens"] / uses if uses > 0 else 0,
                "avg_duration_ms": stats["total_duration_ms"] / uses if uses > 0 else 0.0,
            }

        return {
            "total_uses": total_uses,
            "success_rate": success_rate,
            "avg_tokens": avg_tokens,
            "avg_duration_ms": avg_duration_ms,
            "total_tokens": total_tokens,
            "by_variant": by_variant,
        }

    def get_best_variant(self, template_name: str) -> str:
        """
        Identify the best performing variant for a template.

        Uses a composite score based on success rate, token efficiency,
        and generation speed. Success rate is heavily weighted.

        Args:
            template_name: Name of template to analyze

        Returns:
            Name of best performing variant, or "default" if no data
        """
        stats = self.get_performance_stats(template_name)
        by_variant = stats.get("by_variant", {})

        if not by_variant:
            return "default"

        # Calculate composite score for each variant
        # Score = success_rate * 0.7 + (1 / avg_tokens) * 0.2 + (1 / avg_duration_ms) * 0.1
        # Success rate is heavily weighted (70%)
        best_variant = "default"
        best_score = -1.0

        for variant, variant_stats in by_variant.items():
            success_rate = variant_stats["success_rate"]
            avg_tokens = variant_stats["avg_tokens"]
            avg_duration = variant_stats["avg_duration_ms"]

            # Avoid division by zero
            if avg_tokens == 0 or avg_duration == 0:
                continue

            # Calculate composite score (higher is better)
            # Success rate is the dominant factor
            score = (
                (success_rate / 100) * 0.7  # 70% weight on success rate
                + (1000 / avg_tokens) * 0.2  # 20% weight on token efficiency
                + (1000 / avg_duration) * 0.1  # 10% weight on speed
            )

            if score > best_score:
                best_score = score
                best_variant = variant

        return best_variant

    def export_metrics(self, filepath: str) -> None:
        """
        Export metrics to a JSON file.

        Args:
            filepath: Path to output JSON file
        """
        # Convert metrics to serializable format
        metrics_data = []
        for metric in self._metrics:
            data = asdict(metric)
            # Convert datetime to ISO format string
            data["timestamp"] = metric.timestamp.isoformat()
            metrics_data.append(data)

        # Write to file
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, indent=2)

    def clear_metrics(self) -> None:
        """
        Clear all collected metrics.

        Useful for testing or resetting the collector.
        """
        self._metrics.clear()

    def get_all_metrics(self) -> list[PromptMetric]:
        """
        Get all collected metrics.

        Returns:
            List of all PromptMetric objects
        """
        return self._metrics.copy()

    def get_metrics_summary(self) -> dict[str, Any]:
        """
        Get a summary of all metrics across all templates.

        Returns:
            Dictionary with overall statistics
        """
        if not self._metrics:
            return {
                "total_prompts": 0,
                "total_tokens": 0,
                "avg_duration_ms": 0.0,
                "success_rate": 0.0,
                "templates": {},
            }

        total_prompts = len(self._metrics)
        total_tokens = sum(m.tokens_used for m in self._metrics)
        total_duration = sum(m.duration_ms for m in self._metrics)
        successful = sum(1 for m in self._metrics if m.success)

        # Get unique template names
        template_names = set(m.template_name for m in self._metrics)
        templates = {name: self.get_performance_stats(name) for name in template_names}

        return {
            "total_prompts": total_prompts,
            "total_tokens": total_tokens,
            "avg_duration_ms": total_duration / total_prompts if total_prompts > 0 else 0.0,
            "success_rate": (successful / total_prompts * 100) if total_prompts > 0 else 0.0,
            "templates": templates,
        }
