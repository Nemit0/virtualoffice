"""
Filter Metrics Tracker for Communication Style Filter.

This module tracks filter usage, performance, and costs. It records transformation
metrics to the database and provides aggregated statistics for monitoring and
optimization.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlite3 import Connection

from .models import FilterMetricsSummary

logger = logging.getLogger(__name__)


class FilterMetrics:
    """
    Tracks and aggregates style filter usage metrics.
    
    Records transformation events to the database and provides methods for
    querying session-wide and per-persona statistics. Includes cost estimation
    based on token usage.
    
    Attributes:
        db_connection: SQLite database connection
        batch_size: Number of transformations to batch before writing (default: 10)
    """

    # GPT-4o pricing (as of 2024)
    # Input: $2.50 per 1M tokens, Output: $10.00 per 1M tokens
    # Assuming roughly 50/50 split for style transformations
    TOKEN_COST_PER_1M = 6.25  # Average of input and output costs

    def __init__(self, db_connection: Connection, batch_size: int = 10):
        """
        Initialize the filter metrics tracker.
        
        Args:
            db_connection: SQLite database connection
            batch_size: Number of transformations to batch before writing (default: 10)
        """
        self.db_connection = db_connection
        self.batch_size = batch_size
        self._pending_records: list[tuple] = []
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """
        Ensure the style_filter_metrics table exists in the database.
        
        Creates the table if it doesn't exist, with indexes for efficient querying.
        """
        try:
            self.db_connection.execute("""
                CREATE TABLE IF NOT EXISTS style_filter_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    persona_id INTEGER NOT NULL,
                    message_type TEXT NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    success INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(persona_id) REFERENCES people(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for efficient querying
            self.db_connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_filter_metrics_persona 
                ON style_filter_metrics(persona_id)
            """)
            
            self.db_connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_filter_metrics_created 
                ON style_filter_metrics(created_at)
            """)
            
            self.db_connection.commit()
            logger.debug("Ensured style_filter_metrics table exists")
            
        except sqlite3.Error as e:
            logger.error(f"Failed to create style_filter_metrics table: {e}")
            raise

    async def record_transformation(
        self,
        persona_id: int,
        message_type: str,
        tokens_used: int,
        latency_ms: float,
        success: bool,
    ) -> None:
        """
        Record a filter transformation event.
        
        Adds the transformation to a batch queue and writes to database when
        batch size is reached. This improves performance by reducing database
        write operations.
        
        Args:
            persona_id: ID of the persona
            message_type: Type of message ("email" or "chat")
            tokens_used: Number of tokens consumed by the transformation
            latency_ms: Time taken for the transformation in milliseconds
            success: Whether the transformation succeeded
        """
        # Add to pending records
        timestamp = datetime.now(timezone.utc).isoformat()
        self._pending_records.append((
            persona_id,
            message_type,
            tokens_used,
            latency_ms,
            1 if success else 0,
            timestamp,
        ))
        
        logger.debug(
            f"Recorded transformation: persona={persona_id}, type={message_type}, "
            f"tokens={tokens_used}, latency={latency_ms:.1f}ms, success={success}"
        )
        
        # Write batch if size reached
        if len(self._pending_records) >= self.batch_size:
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """
        Write pending transformation records to the database.
        
        Flushes all pending records in a single transaction for efficiency.
        """
        if not self._pending_records:
            return
        
        try:
            self.db_connection.executemany(
                """
                INSERT INTO style_filter_metrics 
                (persona_id, message_type, tokens_used, latency_ms, success, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                self._pending_records,
            )
            self.db_connection.commit()
            
            logger.debug(f"Flushed {len(self._pending_records)} transformation records to database")
            self._pending_records.clear()
            
        except sqlite3.Error as e:
            logger.error(f"Failed to write transformation records: {e}")
            # Don't raise - we don't want to break the simulation
            # Just log the error and clear the batch
            self._pending_records.clear()

    async def get_session_metrics(self) -> FilterMetricsSummary:
        """
        Get aggregated metrics for the current simulation session.
        
        Calculates totals, averages, and breakdowns by message type for all
        transformations in the current session. Estimates API cost based on
        token usage.
        
        Returns:
            FilterMetricsSummary with aggregated statistics
        """
        # Flush any pending records first
        await self._flush_batch()
        
        try:
            # Get overall statistics
            cursor = self.db_connection.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(tokens_used) as total_tokens,
                    AVG(latency_ms) as avg_latency
                FROM style_filter_metrics
            """)
            
            row = cursor.fetchone()
            
            if row is None or row[0] == 0:
                # No metrics yet
                return FilterMetricsSummary(
                    total_transformations=0,
                    successful_transformations=0,
                    total_tokens=0,
                    average_latency_ms=0.0,
                    estimated_cost_usd=0.0,
                    by_message_type={},
                )
            
            total = row[0]
            successful = row[1] or 0
            total_tokens = row[2] or 0
            avg_latency = row[3] or 0.0
            
            # Get breakdown by message type
            cursor = self.db_connection.execute("""
                SELECT message_type, COUNT(*) as count
                FROM style_filter_metrics
                GROUP BY message_type
            """)
            
            by_message_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Calculate estimated cost
            estimated_cost_usd = (total_tokens / 1_000_000) * self.TOKEN_COST_PER_1M
            
            logger.debug(
                f"Session metrics: {total} transformations, {successful} successful, "
                f"{total_tokens} tokens, ${estimated_cost_usd:.4f} estimated cost"
            )
            
            return FilterMetricsSummary(
                total_transformations=total,
                successful_transformations=successful,
                total_tokens=total_tokens,
                average_latency_ms=avg_latency,
                estimated_cost_usd=estimated_cost_usd,
                by_message_type=by_message_type,
            )
            
        except sqlite3.Error as e:
            logger.error(f"Failed to get session metrics: {e}")
            # Return empty metrics on error
            return FilterMetricsSummary(
                total_transformations=0,
                successful_transformations=0,
                total_tokens=0,
                average_latency_ms=0.0,
                estimated_cost_usd=0.0,
                by_message_type={},
            )

    async def get_persona_metrics(self, persona_id: int) -> dict[str, Any]:
        """
        Get filter metrics for a specific persona.
        
        Returns transformation count, token usage, and average latency for
        the specified persona.
        
        Args:
            persona_id: ID of the persona
            
        Returns:
            Dictionary with persona-specific metrics
        """
        # Flush any pending records first
        await self._flush_batch()
        
        try:
            cursor = self.db_connection.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(tokens_used) as total_tokens,
                    AVG(latency_ms) as avg_latency
                FROM style_filter_metrics
                WHERE persona_id = ?
                """,
                (persona_id,),
            )
            
            row = cursor.fetchone()
            
            if row is None or row[0] == 0:
                # No metrics for this persona
                return {
                    "persona_id": persona_id,
                    "transformation_count": 0,
                    "successful_count": 0,
                    "token_usage": 0,
                    "average_latency_ms": 0.0,
                    "estimated_cost_usd": 0.0,
                }
            
            total = row[0]
            successful = row[1] or 0
            total_tokens = row[2] or 0
            avg_latency = row[3] or 0.0
            
            # Calculate estimated cost
            estimated_cost_usd = (total_tokens / 1_000_000) * self.TOKEN_COST_PER_1M
            
            logger.debug(
                f"Persona {persona_id} metrics: {total} transformations, "
                f"{total_tokens} tokens, ${estimated_cost_usd:.4f} estimated cost"
            )
            
            return {
                "persona_id": persona_id,
                "transformation_count": total,
                "successful_count": successful,
                "token_usage": total_tokens,
                "average_latency_ms": avg_latency,
                "estimated_cost_usd": estimated_cost_usd,
            }
            
        except sqlite3.Error as e:
            logger.error(f"Failed to get persona metrics: {e}")
            # Return empty metrics on error
            return {
                "persona_id": persona_id,
                "transformation_count": 0,
                "successful_count": 0,
                "token_usage": 0,
                "average_latency_ms": 0.0,
                "estimated_cost_usd": 0.0,
            }

    async def close(self) -> None:
        """
        Flush any pending records before closing.
        
        Should be called when shutting down the simulation to ensure all
        metrics are persisted.
        """
        await self._flush_batch()
        logger.debug("FilterMetrics closed, all pending records flushed")
