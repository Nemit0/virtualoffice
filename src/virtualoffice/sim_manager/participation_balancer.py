"""
Participation Balancer for Communication Diversity

This module implements participation balancing to ensure realistic distribution
of communication volume across personas. It prevents message dominance by
throttling high-volume senders and boosting low-volume senders.

Requirements:
- R-5.1: Track message counts per persona per day
- R-5.2: Throttle personas exceeding 2x team average (updated to 1.3x)
- R-5.3: Boost personas below 0.5x team average
- R-5.4: Ensure top 2 chatters account for ≤40% of messages
- R-9.1: Deterministic behavior with random seed
- R-11.4: Configuration support via enabled flag
- O-3: Log throttling/boosting decisions
- R-3.1: Configurable throttle threshold (default: 1.3x)
- R-3.2: Configurable throttle probability (default: 0.1)
"""

import logging
import os
import random
from dataclasses import dataclass, field
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParticipationStats:
    """Statistics for a persona's participation on a specific day.
    
    Attributes:
        person_id: Unique identifier for the persona
        day_index: Day number in the simulation (0-based)
        email_count: Number of emails sent by persona on this day
        chat_count: Number of chat messages sent by persona on this day
        total_count: Total messages sent (email + chat)
        probability_modifier: Multiplier for fallback generation probability (0.5 to 1.5)
    """
    person_id: int
    day_index: int
    email_count: int = 0
    chat_count: int = 0
    total_count: int = 0
    probability_modifier: float = 1.0


class ParticipationBalancer:
    """Manages participation balancing to ensure realistic message distribution.
    
    This class tracks message counts per persona per day and applies throttling
    or boosting to prevent message dominance and ensure balanced participation.
    
    Throttling: Reduces probability for personas sending >2x team average
    Boosting: Increases probability for personas sending <0.5x team average
    
    Attributes:
        enabled: Whether participation balancing is active
        stats: Dictionary mapping (person_id, day_index) to ParticipationStats
        persist_to_db: Whether to persist stats to database
    """
    
    def __init__(self, enabled: bool = True, persist_to_db: bool = False):
        """Initialize the ParticipationBalancer.
        
        Args:
            enabled: Whether to apply participation balancing logic.
                    If False, all personas always generate fallback messages.
            persist_to_db: If True, persist participation stats to database (optional)
        """
        self.enabled = enabled
        self.persist_to_db = persist_to_db
        self.stats: Dict[Tuple[int, int], ParticipationStats] = {}
        
        logger.info(
            f"ParticipationBalancer initialized (enabled={enabled}, "
            f"persist_to_db={persist_to_db})"
        )

    def _get_stats(self, person_id: int, day_index: int) -> ParticipationStats:
        """Get or create stats for a persona on a specific day.
        
        Args:
            person_id: Unique identifier for the persona
            day_index: Day number in the simulation (0-based)
            
        Returns:
            ParticipationStats object for the persona-day combination
        """
        key = (person_id, day_index)
        if key not in self.stats:
            self.stats[key] = ParticipationStats(
                person_id=person_id,
                day_index=day_index
            )
        return self.stats[key]
    
    def record_message(
        self,
        person_id: int,
        day_index: int,
        channel: str
    ) -> None:
        """Record that a persona sent a message.
        
        Updates the message counts for the persona on the specified day.
        Increments email_count or chat_count based on channel, and updates
        total_count.
        
        Args:
            person_id: Unique identifier for the persona
            day_index: Day number in the simulation (0-based)
            channel: Communication channel ('email' or 'chat')
            
        Example:
            >>> balancer = ParticipationBalancer()
            >>> balancer.record_message(1, 0, 'email')
            >>> balancer.record_message(1, 0, 'chat')
            >>> stats = balancer._get_stats(1, 0)
            >>> stats.email_count
            1
            >>> stats.chat_count
            1
            >>> stats.total_count
            2
        """
        stats = self._get_stats(person_id, day_index)
        
        if channel == 'email':
            stats.email_count += 1
        elif channel == 'chat':
            stats.chat_count += 1
        else:
            logger.warning(
                f"Unknown channel '{channel}' for person_id={person_id}, "
                f"day_index={day_index}"
            )
        
        stats.total_count = stats.email_count + stats.chat_count
        
        logger.debug(
            f"Recorded {channel} message for person_id={person_id}, "
            f"day_index={day_index}: "
            f"email={stats.email_count}, chat={stats.chat_count}, "
            f"total={stats.total_count}"
        )
        
        # Optionally persist to database
        if self.persist_to_db:
            self._persist_stats(stats)

    def _get_team_average(self, day_index: int, team_size: int) -> float:
        """Calculate team average message count for a specific day.
        
        Args:
            day_index: Day number in the simulation (0-based)
            team_size: Total number of personas in the team
            
        Returns:
            Average message count per persona for the day.
            Returns 0 if team_size is 0 or no messages recorded.
            
        Example:
            >>> balancer = ParticipationBalancer()
            >>> balancer.record_message(1, 0, 'email')
            >>> balancer.record_message(2, 0, 'email')
            >>> balancer.record_message(2, 0, 'chat')
            >>> balancer._get_team_average(0, 2)
            1.5
        """
        if team_size == 0:
            return 0.0
        
        total = sum(
            stats.total_count
            for (pid, day), stats in self.stats.items()
            if day == day_index
        )
        
        return total / team_size
    
    def get_send_probability(
        self,
        person_id: int,
        day_index: int,
        team_size: int
    ) -> float:
        """Get probability modifier for sending fallback message.
        
        Calculates a probability modifier based on the persona's message count
        relative to the team average:
        - >1.3x average (configurable): 0.1 (throttle - 90% reduction)
        - <0.5x average: 0.9 (boost - 50% increase from base 0.6)
        - Otherwise: 0.6 (normal baseline)
        
        If balancing is disabled, always returns 1.0.
        
        Thresholds are configurable via environment variables:
        - VDOS_PARTICIPATION_THROTTLE_RATIO (default: 1.3)
        - VDOS_PARTICIPATION_THROTTLE_PROBABILITY (default: 0.1)
        
        Args:
            person_id: Unique identifier for the persona
            day_index: Day number in the simulation (0-based)
            team_size: Total number of personas in the team
            
        Returns:
            Probability modifier (0.1, 0.6, or 0.9, or 1.0 if disabled)
            
        Requirements:
            - R-3.1: Throttle threshold configurable (default: 1.3x)
            - R-3.2: Throttle probability configurable (default: 0.1)
            - R-5.3: Boost if <0.5x average
            - R-11.4: Return 1.0 if disabled
            
        Example:
            >>> balancer = ParticipationBalancer(enabled=True)
            >>> # High volume sender (15 messages, team avg = 10)
            >>> for _ in range(15):
            ...     balancer.record_message(1, 0, 'email')
            >>> balancer.get_send_probability(1, 0, 10)
            0.1
            >>> # Low volume sender (1 message, team avg = 10)
            >>> balancer.record_message(2, 0, 'email')
            >>> balancer.get_send_probability(2, 0, 10)
            0.9
        """
        if not self.enabled:
            return 1.0
        
        stats = self._get_stats(person_id, day_index)
        team_avg = self._get_team_average(day_index, team_size)
        
        # If no messages yet, use normal probability
        if team_avg == 0:
            return 0.6
        
        # Get configurable thresholds from environment
        throttle_ratio = float(os.getenv("VDOS_PARTICIPATION_THROTTLE_RATIO", "1.3"))
        throttle_prob = float(os.getenv("VDOS_PARTICIPATION_THROTTLE_PROBABILITY", "0.1"))
        
        # Calculate ratio of persona's count to team average
        ratio = stats.total_count / team_avg
        
        # Apply throttling/boosting logic
        if ratio > throttle_ratio:
            # High volume - throttle
            probability = throttle_prob
            logger.info(
                f"[PARTICIPATION] Throttling person_id={person_id} on day_index={day_index}: "
                f"count={stats.total_count}, team_avg={team_avg:.1f}, "
                f"ratio={ratio:.2f}, threshold={throttle_ratio}, probability={probability}"
            )
        elif ratio < 0.5:
            # Low volume - boost
            probability = 0.9
            logger.info(
                f"[PARTICIPATION] Boosting person_id={person_id} on day_index={day_index}: "
                f"count={stats.total_count}, team_avg={team_avg:.1f}, "
                f"ratio={ratio:.2f}, probability={probability}"
            )
        else:
            # Normal volume
            probability = 0.6
        
        # Update stats with probability modifier
        stats.probability_modifier = probability
        
        return probability
    
    def should_generate_fallback(
        self,
        person_id: int,
        day_index: int,
        team_size: int,
        random_gen: random.Random
    ) -> bool:
        """Determine if a fallback message should be generated for a persona.
        
        Uses the probability modifier from get_send_probability() and a
        provided random generator to make a deterministic decision.
        
        Args:
            person_id: Unique identifier for the persona
            day_index: Day number in the simulation (0-based)
            team_size: Total number of personas in the team
            random_gen: Random number generator for deterministic behavior
            
        Returns:
            True if fallback message should be generated, False otherwise
            
        Requirements:
            - R-9.1: Deterministic with provided random generator
            - R-5.2, R-5.3: Apply throttling/boosting logic
            
        Example:
            >>> import random
            >>> balancer = ParticipationBalancer(enabled=True)
            >>> rng = random.Random(42)
            >>> # With seed 42, this should be deterministic
            >>> result = balancer.should_generate_fallback(1, 0, 10, rng)
            >>> isinstance(result, bool)
            True
        """
        probability = self.get_send_probability(person_id, day_index, team_size)
        decision = random_gen.random() < probability
        
        if not decision and self.enabled:
            logger.info(
                f"[PARTICIPATION] Prevented fallback generation for "
                f"person_id={person_id}, day_index={day_index} "
                f"(probability={probability:.2f})"
            )
        
        return decision

    def get_stats_summary(self, day_index: int) -> Dict[str, any]:
        """Get summary statistics for all personas on a specific day.
        
        Useful for monitoring and debugging participation balance.
        
        Args:
            day_index: Day number in the simulation (0-based)
            
        Returns:
            Dictionary with summary statistics including:
            - total_messages: Total messages sent by all personas
            - persona_counts: List of (person_id, count) tuples sorted by count
            - top_2_percentage: Percentage of messages from top 2 senders
            - gini_coefficient: Gini coefficient of message distribution
            
        Example:
            >>> balancer = ParticipationBalancer()
            >>> balancer.record_message(1, 0, 'email')
            >>> balancer.record_message(2, 0, 'email')
            >>> summary = balancer.get_stats_summary(0)
            >>> summary['total_messages']
            2
        """
        # Get all stats for this day
        day_stats = [
            (stats.person_id, stats.total_count)
            for (pid, day), stats in self.stats.items()
            if day == day_index
        ]
        
        if not day_stats:
            return {
                'total_messages': 0,
                'persona_counts': [],
                'top_2_percentage': 0.0,
                'gini_coefficient': 0.0
            }
        
        # Sort by count descending
        day_stats.sort(key=lambda x: x[1], reverse=True)
        
        total_messages = sum(count for _, count in day_stats)
        
        # Calculate top 2 percentage
        top_2_count = sum(count for _, count in day_stats[:2])
        top_2_percentage = (top_2_count / total_messages * 100) if total_messages > 0 else 0.0
        
        # Calculate Gini coefficient (measure of inequality)
        gini = self._calculate_gini([count for _, count in day_stats])
        
        return {
            'total_messages': total_messages,
            'persona_counts': day_stats,
            'top_2_percentage': top_2_percentage,
            'gini_coefficient': gini
        }
    
    def _calculate_gini(self, counts: list[int]) -> float:
        """Calculate Gini coefficient for message distribution.
        
        Gini coefficient measures inequality in distribution:
        - 0.0: Perfect equality (everyone sends same amount)
        - 1.0: Perfect inequality (one person sends everything)
        
        Args:
            counts: List of message counts per persona
            
        Returns:
            Gini coefficient (0.0 to 1.0)
        """
        if not counts or sum(counts) == 0:
            return 0.0
        
        # Sort counts
        sorted_counts = sorted(counts)
        n = len(sorted_counts)
        
        # Calculate Gini coefficient
        cumsum = 0
        for i, count in enumerate(sorted_counts):
            cumsum += (i + 1) * count
        
        total = sum(sorted_counts)
        gini = (2 * cumsum) / (n * total) - (n + 1) / n
        
        return gini
    
    def log_daily_summary(self, day_index: int) -> None:
        """Log summary of participation balance for a day.
        
        Logs at INFO level with key metrics for monitoring.
        
        Args:
            day_index: Day number in the simulation (0-based)
            
        Requirements:
            - O-3: Log throttling/boosting decisions
        """
        summary = self.get_stats_summary(day_index)
        
        if summary['total_messages'] == 0:
            logger.info(
                f"Participation summary for day {day_index}: No messages"
            )
            return
        
        logger.info(
            f"Participation summary for day {day_index}: "
            f"total={summary['total_messages']}, "
            f"top_2={summary['top_2_percentage']:.1f}%, "
            f"gini={summary['gini_coefficient']:.3f}, "
            f"enabled={self.enabled}"
        )
        
        # Log top senders
        top_5 = summary['persona_counts'][:5]
        logger.info(
            f"Top senders on day {day_index}: " +
            ", ".join(f"person_{pid}={count}" for pid, count in top_5)
        )

    def _persist_stats(self, stats: ParticipationStats) -> None:
        """
        Persist participation stats to the database.
        
        Uses INSERT OR REPLACE to update existing records or create new ones.
        
        Args:
            stats: ParticipationStats object to persist
            
        Requirements: R-12.1
        """
        try:
            from virtualoffice.common.db import get_connection
            from datetime import datetime
            
            with get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO participation_stats (
                        person_id, day_index, email_count, chat_count, 
                        total_count, probability_modifier, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    stats.person_id,
                    stats.day_index,
                    stats.email_count,
                    stats.chat_count,
                    stats.total_count,
                    stats.probability_modifier,
                    datetime.utcnow().isoformat()
                ))
        except Exception as e:
            logger.warning(f"Failed to persist participation stats: {e}")
