"""
Unit tests for FilterMetrics.

Tests metric recording and aggregation, session and persona-specific metrics,
and cost estimation calculations.
"""

import pytest
import sqlite3
from datetime import datetime, timezone

from virtualoffice.sim_manager.style_filter.metrics import FilterMetrics
from virtualoffice.sim_manager.style_filter.models import FilterMetricsSummary


@pytest.fixture
def db_connection():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    
    # Create people table (required for foreign key)
    conn.execute("""
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    
    # Insert test personas
    conn.execute("INSERT INTO people (id, name) VALUES (1, 'Test User 1')")
    conn.execute("INSERT INTO people (id, name) VALUES (2, 'Test User 2')")
    conn.commit()
    
    yield conn
    conn.close()


class TestFilterMetrics:
    """Test suite for FilterMetrics."""

    def test_initialization(self, db_connection):
        """Test metrics tracker initialization."""
        metrics = FilterMetrics(db_connection)
        assert metrics.db_connection == db_connection
        assert metrics.batch_size == 10
        assert len(metrics._pending_records) == 0

    def test_initialization_custom_batch_size(self, db_connection):
        """Test metrics tracker initialization with custom batch size."""
        metrics = FilterMetrics(db_connection, batch_size=5)
        assert metrics.batch_size == 5

    def test_ensure_table_exists(self, db_connection):
        """Test that metrics table is created on initialization."""
        metrics = FilterMetrics(db_connection)
        
        # Verify table exists
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='style_filter_metrics'"
        )
        assert cursor.fetchone() is not None
        
        # Verify indexes exist
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_filter_metrics_persona'"
        )
        assert cursor.fetchone() is not None

    @pytest.mark.asyncio
    async def test_record_transformation(self, db_connection):
        """Test recording a single transformation."""
        metrics = FilterMetrics(db_connection, batch_size=10)
        
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=250.5,
            success=True
        )
        
        assert len(metrics._pending_records) == 1
        record = metrics._pending_records[0]
        assert record[0] == 1  # persona_id
        assert record[1] == "email"  # message_type
        assert record[2] == 100  # tokens_used
        assert record[3] == 250.5  # latency_ms
        assert record[4] == 1  # success (True as 1)

    @pytest.mark.asyncio
    async def test_record_transformation_failure(self, db_connection):
        """Test recording a failed transformation."""
        metrics = FilterMetrics(db_connection, batch_size=10)
        
        await metrics.record_transformation(
            persona_id=1,
            message_type="chat",
            tokens_used=0,
            latency_ms=150.0,
            success=False
        )
        
        assert len(metrics._pending_records) == 1
        record = metrics._pending_records[0]
        assert record[4] == 0  # success (False as 0)

    @pytest.mark.asyncio
    async def test_batch_flush_on_size(self, db_connection):
        """Test that batch is flushed when size is reached."""
        metrics = FilterMetrics(db_connection, batch_size=3)
        
        # Record 3 transformations (should trigger flush)
        for i in range(3):
            await metrics.record_transformation(
                persona_id=1,
                message_type="email",
                tokens_used=100,
                latency_ms=200.0,
                success=True
            )
        
        # Pending records should be cleared after flush
        assert len(metrics._pending_records) == 0
        
        # Verify records in database
        cursor = db_connection.execute("SELECT COUNT(*) FROM style_filter_metrics")
        count = cursor.fetchone()[0]
        assert count == 3

    @pytest.mark.asyncio
    async def test_manual_flush(self, db_connection):
        """Test manual flushing of pending records."""
        metrics = FilterMetrics(db_connection, batch_size=10)
        
        # Record 2 transformations (below batch size)
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=2,
            message_type="chat",
            tokens_used=80,
            latency_ms=180.0,
            success=True
        )
        
        assert len(metrics._pending_records) == 2
        
        # Manual flush
        await metrics._flush_batch()
        
        assert len(metrics._pending_records) == 0
        
        # Verify records in database
        cursor = db_connection.execute("SELECT COUNT(*) FROM style_filter_metrics")
        count = cursor.fetchone()[0]
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_session_metrics_empty(self, db_connection):
        """Test getting session metrics when no data exists."""
        metrics = FilterMetrics(db_connection)
        summary = await metrics.get_session_metrics()
        
        assert isinstance(summary, FilterMetricsSummary)
        assert summary.total_transformations == 0
        assert summary.successful_transformations == 0
        assert summary.total_tokens == 0
        assert summary.average_latency_ms == 0.0
        assert summary.estimated_cost_usd == 0.0
        assert summary.by_message_type == {}

    @pytest.mark.asyncio
    async def test_get_session_metrics_with_data(self, db_connection):
        """Test getting session metrics with recorded data."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record multiple transformations
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=120,
            latency_ms=250.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=2,
            message_type="chat",
            tokens_used=80,
            latency_ms=150.0,
            success=True
        )
        
        summary = await metrics.get_session_metrics()
        
        assert summary.total_transformations == 3
        assert summary.successful_transformations == 3
        assert summary.total_tokens == 300
        assert summary.average_latency_ms == 200.0  # (200 + 250 + 150) / 3
        assert summary.by_message_type == {"email": 2, "chat": 1}

    @pytest.mark.asyncio
    async def test_get_session_metrics_with_failures(self, db_connection):
        """Test session metrics calculation with failed transformations."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record successful and failed transformations
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=0,
            latency_ms=50.0,
            success=False
        )
        await metrics.record_transformation(
            persona_id=2,
            message_type="chat",
            tokens_used=80,
            latency_ms=180.0,
            success=True
        )
        
        summary = await metrics.get_session_metrics()
        
        assert summary.total_transformations == 3
        assert summary.successful_transformations == 2
        assert summary.total_tokens == 180  # Only successful transformations
        assert summary.failure_count == 1

    @pytest.mark.asyncio
    async def test_cost_estimation(self, db_connection):
        """Test API cost estimation calculation."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record transformation with 1 million tokens
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=1_000_000,
            latency_ms=200.0,
            success=True
        )
        
        summary = await metrics.get_session_metrics()
        
        # Cost should be approximately $6.25 per 1M tokens
        assert summary.estimated_cost_usd == pytest.approx(6.25, rel=0.01)

    @pytest.mark.asyncio
    async def test_cost_estimation_small_amounts(self, db_connection):
        """Test cost estimation with small token amounts."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record transformation with 100 tokens
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        
        summary = await metrics.get_session_metrics()
        
        # Cost should be very small
        expected_cost = (100 / 1_000_000) * 6.25
        assert summary.estimated_cost_usd == pytest.approx(expected_cost, rel=0.01)

    @pytest.mark.asyncio
    async def test_get_persona_metrics_empty(self, db_connection):
        """Test getting persona metrics when no data exists."""
        metrics = FilterMetrics(db_connection)
        persona_metrics = await metrics.get_persona_metrics(1)
        
        assert persona_metrics["persona_id"] == 1
        assert persona_metrics["transformation_count"] == 0
        assert persona_metrics["successful_count"] == 0
        assert persona_metrics["token_usage"] == 0
        assert persona_metrics["average_latency_ms"] == 0.0
        assert persona_metrics["estimated_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_get_persona_metrics_with_data(self, db_connection):
        """Test getting persona-specific metrics."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record transformations for persona 1
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="chat",
            tokens_used=80,
            latency_ms=150.0,
            success=True
        )
        
        # Record transformation for persona 2 (should not be included)
        await metrics.record_transformation(
            persona_id=2,
            message_type="email",
            tokens_used=120,
            latency_ms=250.0,
            success=True
        )
        
        persona_metrics = await metrics.get_persona_metrics(1)
        
        assert persona_metrics["persona_id"] == 1
        assert persona_metrics["transformation_count"] == 2
        assert persona_metrics["successful_count"] == 2
        assert persona_metrics["token_usage"] == 180
        assert persona_metrics["average_latency_ms"] == 175.0  # (200 + 150) / 2

    @pytest.mark.asyncio
    async def test_get_persona_metrics_with_failures(self, db_connection):
        """Test persona metrics with failed transformations."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record successful and failed transformations
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=0,
            latency_ms=50.0,
            success=False
        )
        
        persona_metrics = await metrics.get_persona_metrics(1)
        
        assert persona_metrics["transformation_count"] == 2
        assert persona_metrics["successful_count"] == 1
        assert persona_metrics["token_usage"] == 100

    @pytest.mark.asyncio
    async def test_message_type_breakdown(self, db_connection):
        """Test breakdown of transformations by message type."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record various message types
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=110,
            latency_ms=210.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="chat",
            tokens_used=80,
            latency_ms=150.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=2,
            message_type="chat",
            tokens_used=85,
            latency_ms=160.0,
            success=True
        )
        
        summary = await metrics.get_session_metrics()
        
        assert summary.by_message_type["email"] == 2
        assert summary.by_message_type["chat"] == 2

    @pytest.mark.asyncio
    async def test_close_flushes_pending(self, db_connection):
        """Test that close() flushes pending records."""
        metrics = FilterMetrics(db_connection, batch_size=10)
        
        # Record transformations below batch size
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=1,
            message_type="chat",
            tokens_used=80,
            latency_ms=150.0,
            success=True
        )
        
        assert len(metrics._pending_records) == 2
        
        # Close should flush
        await metrics.close()
        
        assert len(metrics._pending_records) == 0
        
        # Verify records in database
        cursor = db_connection.execute("SELECT COUNT(*) FROM style_filter_metrics")
        count = cursor.fetchone()[0]
        assert count == 2

    @pytest.mark.asyncio
    async def test_success_rate_calculation(self, db_connection):
        """Test success rate calculation in metrics summary."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record 3 successful and 1 failed
        for _ in range(3):
            await metrics.record_transformation(
                persona_id=1,
                message_type="email",
                tokens_used=100,
                latency_ms=200.0,
                success=True
            )
        
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=0,
            latency_ms=50.0,
            success=False
        )
        
        summary = await metrics.get_session_metrics()
        
        assert summary.success_rate == 0.75  # 3/4

    @pytest.mark.asyncio
    async def test_multiple_personas_aggregation(self, db_connection):
        """Test that session metrics aggregate across all personas."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        # Record for multiple personas
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        await metrics.record_transformation(
            persona_id=2,
            message_type="email",
            tokens_used=120,
            latency_ms=250.0,
            success=True
        )
        
        summary = await metrics.get_session_metrics()
        
        assert summary.total_transformations == 2
        assert summary.total_tokens == 220

    @pytest.mark.asyncio
    async def test_timestamp_recording(self, db_connection):
        """Test that timestamps are recorded correctly."""
        metrics = FilterMetrics(db_connection, batch_size=1)
        
        before = datetime.now(timezone.utc)
        
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        
        after = datetime.now(timezone.utc)
        
        # Verify timestamp in database
        cursor = db_connection.execute(
            "SELECT created_at FROM style_filter_metrics WHERE persona_id = 1"
        )
        timestamp_str = cursor.fetchone()[0]
        timestamp = datetime.fromisoformat(timestamp_str)
        
        assert before <= timestamp <= after

    @pytest.mark.asyncio
    async def test_batch_write_efficiency(self, db_connection):
        """Test that batching reduces database write operations."""
        metrics = FilterMetrics(db_connection, batch_size=5)
        
        # Record 4 transformations (below batch size)
        for i in range(4):
            await metrics.record_transformation(
                persona_id=1,
                message_type="email",
                tokens_used=100,
                latency_ms=200.0,
                success=True
            )
        
        # Should still be pending
        cursor = db_connection.execute("SELECT COUNT(*) FROM style_filter_metrics")
        count = cursor.fetchone()[0]
        assert count == 0
        
        # 5th record should trigger flush
        await metrics.record_transformation(
            persona_id=1,
            message_type="email",
            tokens_used=100,
            latency_ms=200.0,
            success=True
        )
        
        cursor = db_connection.execute("SELECT COUNT(*) FROM style_filter_metrics")
        count = cursor.fetchone()[0]
        assert count == 5
