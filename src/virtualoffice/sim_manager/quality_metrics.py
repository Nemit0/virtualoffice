"""
Quality Metrics Tracker for Communication Diversity.

This module tracks quality metrics for the communication diversity feature,
including template diversity, threading rate, participation balance, and
project context usage.
"""

from __future__ import annotations

import logging
from typing import Any
from collections import Counter

logger = logging.getLogger(__name__)


class QualityMetricsTracker:
    """
    Tracks quality metrics for communication diversity and realism.
    
    Metrics tracked:
    - template_diversity_score: Unique subjects / total messages
    - threading_rate: Messages with thread_id / total emails
    - participation_gini: Gini coefficient of message distribution
    - project_context_rate: Messages with project refs / total
    - json_vs_fallback_ratio: JSON comms / total comms
    
    Requirements: O-2
    """
    
    def __init__(self):
        """Initialize the quality metrics tracker."""
        self.total_emails = 0
        self.total_chats = 0
        self.unique_subjects = set()
        self.threaded_emails = 0
        self.project_context_messages = 0
        self.json_communications = 0
        self.fallback_communications = 0
        self.messages_per_persona: dict[int, int] = {}
        
        logger.info("QualityMetricsTracker initialized")
    
    def record_email(
        self,
        subject: str,
        thread_id: str | None = None,
        has_project_context: bool = False,
        source: str = "unknown",
        person_id: int | None = None
    ) -> None:
        """
        Record an email for quality metrics.
        
        Args:
            subject: Email subject line
            thread_id: Thread ID if part of a conversation
            has_project_context: Whether email mentions project
            source: Source of communication ('json' or 'fallback')
            person_id: ID of sender persona
        """
        self.total_emails += 1
        self.unique_subjects.add(subject)
        
        if thread_id:
            self.threaded_emails += 1
        
        if has_project_context:
            self.project_context_messages += 1
        
        if source == "json":
            self.json_communications += 1
        elif source == "fallback":
            self.fallback_communications += 1
        
        if person_id is not None:
            self.messages_per_persona[person_id] = self.messages_per_persona.get(person_id, 0) + 1
        
        logger.debug(
            f"[METRICS] Recorded email: subject='{subject[:50]}...', "
            f"threaded={thread_id is not None}, project_context={has_project_context}, "
            f"source={source}"
        )
    
    def record_chat(
        self,
        has_project_context: bool = False,
        source: str = "unknown",
        person_id: int | None = None
    ) -> None:
        """
        Record a chat message for quality metrics.
        
        Args:
            has_project_context: Whether chat mentions project
            source: Source of communication ('json' or 'fallback')
            person_id: ID of sender persona
        """
        self.total_chats += 1
        
        if has_project_context:
            self.project_context_messages += 1
        
        if source == "json":
            self.json_communications += 1
        elif source == "fallback":
            self.fallback_communications += 1
        
        if person_id is not None:
            self.messages_per_persona[person_id] = self.messages_per_persona.get(person_id, 0) + 1
        
        logger.debug(
            f"[METRICS] Recorded chat: project_context={has_project_context}, "
            f"source={source}"
        )
    
    def get_template_diversity_score(self) -> float:
        """
        Calculate template diversity score.
        
        Returns:
            Ratio of unique subjects to total emails (0.0 to 1.0)
            Returns 0.0 if no emails sent
        """
        if self.total_emails == 0:
            return 0.0
        return len(self.unique_subjects) / self.total_emails
    
    def get_threading_rate(self) -> float:
        """
        Calculate threading rate.
        
        Returns:
            Ratio of threaded emails to total emails (0.0 to 1.0)
            Returns 0.0 if no emails sent
        """
        if self.total_emails == 0:
            return 0.0
        return self.threaded_emails / self.total_emails
    
    def get_participation_gini(self) -> float:
        """
        Calculate Gini coefficient for message distribution.
        
        The Gini coefficient measures inequality in message distribution.
        0.0 = perfect equality (all personas send same amount)
        1.0 = perfect inequality (one persona sends everything)
        
        Returns:
            Gini coefficient (0.0 to 1.0)
            Returns 0.0 if fewer than 2 personas
        """
        if len(self.messages_per_persona) < 2:
            return 0.0
        
        # Get sorted message counts
        counts = sorted(self.messages_per_persona.values())
        n = len(counts)
        
        # Calculate Gini coefficient
        # Formula: G = (2 * sum(i * x_i)) / (n * sum(x_i)) - (n + 1) / n
        total = sum(counts)
        if total == 0:
            return 0.0
        
        weighted_sum = sum((i + 1) * count for i, count in enumerate(counts))
        gini = (2 * weighted_sum) / (n * total) - (n + 1) / n
        
        return max(0.0, min(1.0, gini))  # Clamp to [0, 1]
    
    def get_project_context_rate(self) -> float:
        """
        Calculate project context rate.
        
        Returns:
            Ratio of messages with project context to total messages (0.0 to 1.0)
            Returns 0.0 if no messages sent
        """
        total_messages = self.total_emails + self.total_chats
        if total_messages == 0:
            return 0.0
        return self.project_context_messages / total_messages
    
    def get_json_vs_fallback_ratio(self) -> float:
        """
        Calculate JSON vs fallback ratio.
        
        Returns:
            Ratio of JSON communications to total communications (0.0 to 1.0)
            Returns 0.0 if no communications sent
        """
        total_comms = self.json_communications + self.fallback_communications
        if total_comms == 0:
            return 0.0
        return self.json_communications / total_comms
    
    def get_all_metrics(self) -> dict[str, Any]:
        """
        Get all quality metrics as a dictionary.
        
        Returns:
            Dictionary with all metrics and their current values
        """
        total_messages = self.total_emails + self.total_chats
        
        metrics = {
            "template_diversity_score": {
                "value": self.get_template_diversity_score(),
                "target": 0.7,
                "description": "Unique subjects / total emails (higher is better)"
            },
            "threading_rate": {
                "value": self.get_threading_rate(),
                "target": 0.3,
                "description": "Emails with thread_id / total emails (target: 30%+)"
            },
            "participation_gini": {
                "value": self.get_participation_gini(),
                "target": 0.3,
                "description": "Gini coefficient of message distribution (lower is better, 0=equal)"
            },
            "project_context_rate": {
                "value": self.get_project_context_rate(),
                "target": 0.6,
                "description": "Messages with project references / total messages (target: 60%+)"
            },
            "json_vs_fallback_ratio": {
                "value": self.get_json_vs_fallback_ratio(),
                "target": 0.7,
                "description": "JSON communications / total communications (higher is better)"
            },
            "total_emails": self.total_emails,
            "total_chats": self.total_chats,
            "total_messages": total_messages,
            "unique_subjects": len(self.unique_subjects),
            "threaded_emails": self.threaded_emails,
            "project_context_messages": self.project_context_messages,
            "json_communications": self.json_communications,
            "fallback_communications": self.fallback_communications,
            "personas_tracked": len(self.messages_per_persona)
        }
        
        logger.debug(f"[METRICS] Generated metrics summary: {metrics}")
        
        return metrics
    
    def reset(self) -> None:
        """Reset all metrics to initial state."""
        self.total_emails = 0
        self.total_chats = 0
        self.unique_subjects = set()
        self.threaded_emails = 0
        self.project_context_messages = 0
        self.json_communications = 0
        self.fallback_communications = 0
        self.messages_per_persona = {}
        
        logger.info("[METRICS] Reset all quality metrics")
    
    def log_summary(self) -> None:
        """Log a summary of current metrics at INFO level."""
        metrics = self.get_all_metrics()
        
        logger.info(
            f"[METRICS] Quality Metrics Summary:\n"
            f"  Template Diversity: {metrics['template_diversity_score']['value']:.2%} "
            f"(target: {metrics['template_diversity_score']['target']:.0%})\n"
            f"  Threading Rate: {metrics['threading_rate']['value']:.2%} "
            f"(target: {metrics['threading_rate']['target']:.0%})\n"
            f"  Participation Gini: {metrics['participation_gini']['value']:.3f} "
            f"(target: <{metrics['participation_gini']['target']:.1f})\n"
            f"  Project Context: {metrics['project_context_rate']['value']:.2%} "
            f"(target: {metrics['project_context_rate']['target']:.0%})\n"
            f"  JSON vs Fallback: {metrics['json_vs_fallback_ratio']['value']:.2%} "
            f"(target: {metrics['json_vs_fallback_ratio']['target']:.0%})\n"
            f"  Total Messages: {metrics['total_messages']} "
            f"(emails: {metrics['total_emails']}, chats: {metrics['total_chats']})"
        )
