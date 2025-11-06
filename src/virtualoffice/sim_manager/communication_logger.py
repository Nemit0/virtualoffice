"""
Communication Generation Logger

This module provides logging functionality for communication generation events,
enabling observability and quality metrics tracking.

Requirements: O-2, O-6
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class CommunicationLogger:
    """
    Logs communication generation events to database for observability.
    
    Tracks:
    - Generation type (json, gpt_fallback, template)
    - Success/failure status
    - Token usage and latency
    - Context size
    
    Requirements: O-2, O-6
    """
    
    def __init__(self, persist_to_db: bool = False):
        """
        Initialize the communication logger.
        
        Args:
            persist_to_db: If True, persist logs to database (optional)
        """
        self.persist_to_db = persist_to_db
        logger.info(f"CommunicationLogger initialized (persist_to_db={persist_to_db})")
    
    def log_generation(
        self,
        person_id: int,
        tick: int,
        generation_type: str,
        channel: str,
        success: bool = True,
        error_message: Optional[str] = None,
        token_count: Optional[int] = None,
        latency_ms: Optional[int] = None,
        context_size: Optional[int] = None
    ) -> None:
        """
        Log a communication generation event.
        
        Args:
            person_id: ID of the persona generating communication
            tick: Current simulation tick
            generation_type: Type of generation ('json', 'gpt_fallback', 'template')
            channel: Communication channel ('email' or 'chat')
            success: Whether generation succeeded
            error_message: Error message if generation failed
            token_count: Number of tokens used (for GPT calls)
            latency_ms: Generation latency in milliseconds
            context_size: Size of context provided (characters)
            
        Requirements: O-2, O-6
        """
        # Log to application logger
        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"Communication generation: person_id={person_id}, tick={tick}, "
            f"type={generation_type}, channel={channel}, success={success}, "
            f"tokens={token_count}, latency_ms={latency_ms}"
        )
        
        # Optionally persist to database
        if self.persist_to_db:
            self._persist_log(
                person_id=person_id,
                tick=tick,
                generation_type=generation_type,
                channel=channel,
                success=success,
                error_message=error_message,
                token_count=token_count,
                latency_ms=latency_ms,
                context_size=context_size
            )
    
    def _persist_log(
        self,
        person_id: int,
        tick: int,
        generation_type: str,
        channel: str,
        success: bool,
        error_message: Optional[str],
        token_count: Optional[int],
        latency_ms: Optional[int],
        context_size: Optional[int]
    ) -> None:
        """
        Persist communication generation log to database.
        
        Args:
            person_id: ID of the persona
            tick: Current simulation tick
            generation_type: Type of generation
            channel: Communication channel
            success: Whether generation succeeded
            error_message: Error message if failed
            token_count: Number of tokens used
            latency_ms: Generation latency
            context_size: Context size in characters
            
        Requirements: R-12.1
        """
        try:
            from virtualoffice.common.db import get_connection
            
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO communication_generation_log (
                        person_id, tick, generation_type, channel, success,
                        error_message, token_count, latency_ms, context_size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    person_id,
                    tick,
                    generation_type,
                    channel,
                    1 if success else 0,
                    error_message,
                    token_count,
                    latency_ms,
                    context_size
                ))
        except Exception as e:
            logger.warning(f"Failed to persist communication generation log: {e}")
    
    def get_generation_stats(self, tick_start: int, tick_end: int) -> dict:
        """
        Get generation statistics for a tick range.
        
        Args:
            tick_start: Start tick (inclusive)
            tick_end: End tick (inclusive)
            
        Returns:
            Dictionary with statistics:
            - total_generations: Total generation attempts
            - json_count: Number of JSON generations
            - gpt_fallback_count: Number of GPT fallback generations
            - template_count: Number of template generations
            - success_rate: Percentage of successful generations
            - avg_latency_ms: Average latency in milliseconds
            - total_tokens: Total tokens used
            
        Requirements: O-2
        """
        if not self.persist_to_db:
            logger.warning("Cannot get stats - database persistence is disabled")
            return {}
        
        try:
            from virtualoffice.common.db import get_connection
            
            with get_connection() as conn:
                # Get counts by type
                result = conn.execute("""
                    SELECT 
                        generation_type,
                        COUNT(*) as count,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                        AVG(latency_ms) as avg_latency,
                        SUM(token_count) as total_tokens
                    FROM communication_generation_log
                    WHERE tick BETWEEN ? AND ?
                    GROUP BY generation_type
                """, (tick_start, tick_end)).fetchall()
                
                stats = {
                    'total_generations': 0,
                    'json_count': 0,
                    'gpt_fallback_count': 0,
                    'template_count': 0,
                    'success_rate': 0.0,
                    'avg_latency_ms': 0.0,
                    'total_tokens': 0
                }
                
                total_success = 0
                total_latency = 0
                latency_count = 0
                
                for row in result:
                    gen_type = row['generation_type']
                    count = row['count']
                    success_count = row['success_count']
                    avg_latency = row['avg_latency']
                    total_tokens = row['total_tokens'] or 0
                    
                    stats['total_generations'] += count
                    total_success += success_count
                    
                    if avg_latency:
                        total_latency += avg_latency * count
                        latency_count += count
                    
                    stats['total_tokens'] += total_tokens
                    
                    if gen_type == 'json':
                        stats['json_count'] = count
                    elif gen_type == 'gpt_fallback':
                        stats['gpt_fallback_count'] = count
                    elif gen_type == 'template':
                        stats['template_count'] = count
                
                if stats['total_generations'] > 0:
                    stats['success_rate'] = (total_success / stats['total_generations']) * 100
                
                if latency_count > 0:
                    stats['avg_latency_ms'] = total_latency / latency_count
                
                return stats
                
        except Exception as e:
            logger.warning(f"Failed to get generation stats: {e}")
            return {}
