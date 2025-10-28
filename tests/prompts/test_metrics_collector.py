"""
Tests for PromptMetricsCollector class.

Tests metrics recording, aggregation, and performance tracking.
"""

import pytest
from datetime import datetime
import tempfile
import json
from pathlib import Path

from virtualoffice.sim_manager.prompts import (
    PromptMetricsCollector,
    PromptMetric,
)


@pytest.fixture
def metrics_collector():
    """Create a fresh metrics collector."""
    return PromptMetricsCollector(max_history=100)


class TestMetricsCollectorInitialization:
    """Test PromptMetricsCollector initialization."""
    
    def test_init_default(self):
        """Test initialization with default parameters."""
        collector = PromptMetricsCollector()
        assert collector.max_history == 1000
        assert len(collector._metrics) == 0
    
    def test_init_custom_max_history(self):
        """Test initialization with custom max history."""
        collector = PromptMetricsCollector(max_history=50)
        assert collector.max_history == 50


class TestMetricsRecording:
    """Test recording metrics."""
    
    def test_record_usage_success(self, metrics_collector):
        """Test recording a successful prompt usage."""
        metrics_collector.record_usage(
            template_name="hourly_planning",
            variant="default",
            model_used="gpt-4o",
            tokens_used=500,
            duration_ms=1200.5,
            success=True,
        )
        
        metrics = metrics_collector.get_all_metrics()
        assert len(metrics) == 1
        
        metric = metrics[0]
        assert metric.template_name == "hourly_planning"
        assert metric.variant == "default"
        assert metric.model_used == "gpt-4o"
        assert metric.tokens_used == 500
        assert metric.duration_ms == 1200.5
        assert metric.success is True
        assert metric.error is None
    
    def test_record_usage_failure(self, metrics_collector):
        """Test recording a failed prompt usage."""
        metrics_collector.record_usage(
            template_name="hourly_planning",
            variant="default",
            model_used="gpt-4o",
            tokens_used=0,
            duration_ms=100.0,
            success=False,
            error="API timeout",
        )
        
        metrics = metrics_collector.get_all_metrics()
        assert len(metrics) == 1
        
        metric = metrics[0]
        assert metric.success is False
        assert metric.error == "API timeout"
    
    def test_record_multiple_usages(self, metrics_collector):
        """Test recording multiple usages."""
        for i in range(5):
            metrics_collector.record_usage(
                template_name=f"template_{i}",
                variant="default",
                model_used="gpt-4o",
                tokens_used=100 * i,
                duration_ms=500.0,
                success=True,
            )
        
        metrics = metrics_collector.get_all_metrics()
        assert len(metrics) == 5
    
    def test_max_history_limit(self):
        """Test that metrics are trimmed when exceeding max history."""
        collector = PromptMetricsCollector(max_history=3)
        
        for i in range(5):
            collector.record_usage(
                template_name=f"template_{i}",
                variant="default",
                model_used="gpt-4o",
                tokens_used=100,
                duration_ms=500.0,
                success=True,
            )
        
        metrics = collector.get_all_metrics()
        assert len(metrics) == 3
        # Should keep the most recent 3
        assert metrics[0].template_name == "template_2"
        assert metrics[1].template_name == "template_3"
        assert metrics[2].template_name == "template_4"


class TestPerformanceStats:
    """Test performance statistics calculation."""
    
    def test_get_performance_stats_empty(self, metrics_collector):
        """Test getting stats when no metrics exist."""
        stats = metrics_collector.get_performance_stats("nonexistent")
        
        assert stats["total_uses"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_tokens"] == 0
        assert stats["avg_duration_ms"] == 0.0
        assert stats["total_tokens"] == 0
        assert stats["by_variant"] == {}
    
    def test_get_performance_stats_single_template(self, metrics_collector):
        """Test getting stats for a single template."""
        # Record 3 successful uses
        for i in range(3):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="default",
                model_used="gpt-4o",
                tokens_used=500,
                duration_ms=1000.0,
                success=True,
            )
        
        stats = metrics_collector.get_performance_stats("hourly_planning")
        
        assert stats["total_uses"] == 3
        assert stats["success_rate"] == 100.0
        assert stats["avg_tokens"] == 500
        assert stats["avg_duration_ms"] == 1000.0
        assert stats["total_tokens"] == 1500
    
    def test_get_performance_stats_with_failures(self, metrics_collector):
        """Test stats calculation with some failures."""
        # 3 successes, 1 failure
        for i in range(3):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="default",
                model_used="gpt-4o",
                tokens_used=500,
                duration_ms=1000.0,
                success=True,
            )
        
        metrics_collector.record_usage(
            template_name="hourly_planning",
            variant="default",
            model_used="gpt-4o",
            tokens_used=0,
            duration_ms=100.0,
            success=False,
            error="Timeout",
        )
        
        stats = metrics_collector.get_performance_stats("hourly_planning")
        
        assert stats["total_uses"] == 4
        assert stats["success_rate"] == 75.0  # 3 out of 4
        assert stats["total_tokens"] == 1500  # Only successful ones counted
    
    def test_get_performance_stats_multiple_variants(self, metrics_collector):
        """Test stats with multiple variants."""
        # Default variant: 2 uses
        for i in range(2):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="default",
                model_used="gpt-4o",
                tokens_used=500,
                duration_ms=1000.0,
                success=True,
            )
        
        # Verbose variant: 3 uses
        for i in range(3):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="verbose",
                model_used="gpt-4o",
                tokens_used=800,
                duration_ms=1500.0,
                success=True,
            )
        
        stats = metrics_collector.get_performance_stats("hourly_planning")
        
        assert stats["total_uses"] == 5
        assert "default" in stats["by_variant"]
        assert "verbose" in stats["by_variant"]
        
        default_stats = stats["by_variant"]["default"]
        assert default_stats["uses"] == 2
        assert default_stats["avg_tokens"] == 500
        
        verbose_stats = stats["by_variant"]["verbose"]
        assert verbose_stats["uses"] == 3
        assert verbose_stats["avg_tokens"] == 800


class TestBestVariantSelection:
    """Test best variant selection."""
    
    def test_get_best_variant_no_data(self, metrics_collector):
        """Test getting best variant when no data exists."""
        best = metrics_collector.get_best_variant("nonexistent")
        assert best == "default"
    
    def test_get_best_variant_single_variant(self, metrics_collector):
        """Test with only one variant."""
        metrics_collector.record_usage(
            template_name="hourly_planning",
            variant="default",
            model_used="gpt-4o",
            tokens_used=500,
            duration_ms=1000.0,
            success=True,
        )
        
        best = metrics_collector.get_best_variant("hourly_planning")
        assert best == "default"
    
    def test_get_best_variant_multiple_variants(self, metrics_collector):
        """Test selecting best variant from multiple options."""
        # Default variant: good success rate, moderate tokens
        for i in range(5):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="default",
                model_used="gpt-4o",
                tokens_used=500,
                duration_ms=1000.0,
                success=True,
            )
        
        # Verbose variant: good success rate, high tokens (worse)
        for i in range(5):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="verbose",
                model_used="gpt-4o",
                tokens_used=1000,
                duration_ms=1500.0,
                success=True,
            )
        
        # Concise variant: good success rate, low tokens (better)
        for i in range(5):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="concise",
                model_used="gpt-4o",
                tokens_used=300,
                duration_ms=800.0,
                success=True,
            )
        
        best = metrics_collector.get_best_variant("hourly_planning")
        # Concise should win due to lower tokens and faster speed
        assert best == "concise"
    
    def test_get_best_variant_considers_success_rate(self, metrics_collector):
        """Test that success rate is considered in variant selection."""
        # Variant A: 100% success, moderate tokens
        for i in range(5):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="variant_a",
                model_used="gpt-4o",
                tokens_used=500,
                duration_ms=1000.0,
                success=True,
            )
        
        # Variant B: 20% success, low tokens (should lose due to very low success rate)
        for i in range(5):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="variant_b",
                model_used="gpt-4o",
                tokens_used=300,
                duration_ms=800.0,
                success=(i == 0),  # Only 20% success rate
            )
        
        best = metrics_collector.get_best_variant("hourly_planning")
        # Variant A should win due to much higher success rate
        assert best == "variant_a"


class TestMetricsExport:
    """Test metrics export functionality."""
    
    def test_export_metrics_to_json(self, metrics_collector):
        """Test exporting metrics to JSON file."""
        # Record some metrics
        metrics_collector.record_usage(
            template_name="hourly_planning",
            variant="default",
            model_used="gpt-4o",
            tokens_used=500,
            duration_ms=1000.0,
            success=True,
        )
        
        # Export to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            metrics_collector.export_metrics(temp_path)
            
            # Read and verify
            with open(temp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            assert len(data) == 1
            assert data[0]["template_name"] == "hourly_planning"
            assert data[0]["variant"] == "default"
            assert data[0]["tokens_used"] == 500
            assert "timestamp" in data[0]
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_export_metrics_creates_directory(self, metrics_collector):
        """Test that export creates parent directories if needed."""
        metrics_collector.record_usage(
            template_name="test",
            variant="default",
            model_used="gpt-4o",
            tokens_used=100,
            duration_ms=500.0,
            success=True,
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "subdir" / "metrics.json"
            metrics_collector.export_metrics(str(export_path))
            
            assert export_path.exists()


class TestMetricsManagement:
    """Test metrics management operations."""
    
    def test_clear_metrics(self, metrics_collector):
        """Test clearing all metrics."""
        # Record some metrics
        for i in range(5):
            metrics_collector.record_usage(
                template_name="test",
                variant="default",
                model_used="gpt-4o",
                tokens_used=100,
                duration_ms=500.0,
                success=True,
            )
        
        assert len(metrics_collector.get_all_metrics()) == 5
        
        metrics_collector.clear_metrics()
        
        assert len(metrics_collector.get_all_metrics()) == 0
    
    def test_get_all_metrics_returns_copy(self, metrics_collector):
        """Test that get_all_metrics returns a copy, not the original list."""
        metrics_collector.record_usage(
            template_name="test",
            variant="default",
            model_used="gpt-4o",
            tokens_used=100,
            duration_ms=500.0,
            success=True,
        )
        
        metrics1 = metrics_collector.get_all_metrics()
        metrics2 = metrics_collector.get_all_metrics()
        
        # Should be different list objects
        assert metrics1 is not metrics2
        # But contain the same data
        assert len(metrics1) == len(metrics2)


class TestMetricsSummary:
    """Test overall metrics summary."""
    
    def test_get_metrics_summary_empty(self, metrics_collector):
        """Test summary when no metrics exist."""
        summary = metrics_collector.get_metrics_summary()
        
        assert summary["total_prompts"] == 0
        assert summary["total_tokens"] == 0
        assert summary["avg_duration_ms"] == 0.0
        assert summary["success_rate"] == 0.0
        assert summary["templates"] == {}
    
    def test_get_metrics_summary_with_data(self, metrics_collector):
        """Test summary with multiple templates."""
        # Template 1
        for i in range(3):
            metrics_collector.record_usage(
                template_name="hourly_planning",
                variant="default",
                model_used="gpt-4o",
                tokens_used=500,
                duration_ms=1000.0,
                success=True,
            )
        
        # Template 2
        for i in range(2):
            metrics_collector.record_usage(
                template_name="daily_report",
                variant="default",
                model_used="gpt-4o",
                tokens_used=300,
                duration_ms=800.0,
                success=True,
            )
        
        summary = metrics_collector.get_metrics_summary()
        
        assert summary["total_prompts"] == 5
        assert summary["total_tokens"] == 2100  # (3 * 500) + (2 * 300)
        assert summary["success_rate"] == 100.0
        assert "hourly_planning" in summary["templates"]
        assert "daily_report" in summary["templates"]
    
    def test_get_metrics_summary_calculates_averages(self, metrics_collector):
        """Test that summary calculates correct averages."""
        metrics_collector.record_usage(
            template_name="test",
            variant="default",
            model_used="gpt-4o",
            tokens_used=500,
            duration_ms=1000.0,
            success=True,
        )
        
        metrics_collector.record_usage(
            template_name="test",
            variant="default",
            model_used="gpt-4o",
            tokens_used=300,
            duration_ms=600.0,
            success=True,
        )
        
        summary = metrics_collector.get_metrics_summary()
        
        assert summary["total_prompts"] == 2
        assert summary["total_tokens"] == 800
        assert summary["avg_duration_ms"] == 800.0  # (1000 + 600) / 2
