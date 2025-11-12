"""
Data models for the Communication Style Filter.

This module defines the core data structures used throughout the style filter system:
- StyleExample: Individual communication style examples
- FilterResult: Result of a style transformation operation
- FilterMetricsSummary: Aggregated metrics for filter usage
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class StyleExample:
    """
    A single communication style example.
    
    Style examples demonstrate how a persona writes emails or chat messages,
    and are used to guide GPT-4o transformations.
    
    Attributes:
        type: Type of communication ("email" or "chat")
        content: The example message content
    """

    type: Literal["email", "chat"]
    content: str

    def validate(self) -> bool:
        """
        Validate that the example meets minimum requirements.
        
        Returns:
            True if the example is valid, False otherwise
        """
        return len(self.content.strip()) >= 20

    def to_dict(self) -> dict[str, str]:
        """
        Convert to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation of the style example
        """
        return {"type": self.type, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleExample:
        """
        Create StyleExample from dictionary.
        
        Args:
            data: Dictionary with 'type' and 'content' keys
            
        Returns:
            StyleExample instance
        """
        return cls(type=data["type"], content=data["content"])

    @classmethod
    def from_json(cls, json_str: str) -> list[StyleExample]:
        """
        Parse a JSON string into a list of StyleExample objects.
        
        Args:
            json_str: JSON string containing array of style examples
            
        Returns:
            List of StyleExample instances
        """
        data = json.loads(json_str)
        return [cls.from_dict(item) for item in data]

    @staticmethod
    def to_json(examples: list[StyleExample]) -> str:
        """
        Serialize a list of StyleExample objects to JSON.
        
        Args:
            examples: List of StyleExample instances
            
        Returns:
            JSON string representation
        """
        return json.dumps([ex.to_dict() for ex in examples])


@dataclass
class FilterResult:
    """
    Result of a style filter transformation.
    
    Contains both the transformed message and metadata about the transformation
    operation including performance metrics and success status.
    
    Attributes:
        styled_message: The transformed message with applied style
        original_message: The original message before transformation
        tokens_used: Number of tokens consumed by the GPT-4o API call
        latency_ms: Time taken for the transformation in milliseconds
        success: Whether the transformation succeeded
        error: Error message if transformation failed, None otherwise
    """

    styled_message: str
    original_message: str
    tokens_used: int
    latency_ms: float
    success: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation of the filter result
        """
        return {
            "styled_message": self.styled_message,
            "original_message": self.original_message,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class FilterMetricsSummary:
    """
    Aggregated metrics for style filter usage.
    
    Provides summary statistics about filter transformations including
    counts, token usage, performance, and cost estimates.
    
    Attributes:
        total_transformations: Total number of transformation attempts
        successful_transformations: Number of successful transformations
        total_tokens: Total tokens consumed across all transformations
        average_latency_ms: Average transformation latency in milliseconds
        estimated_cost_usd: Estimated API cost in USD
        by_message_type: Breakdown of transformation counts by message type
    """

    total_transformations: int
    successful_transformations: int
    total_tokens: int
    average_latency_ms: float
    estimated_cost_usd: float
    by_message_type: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation of the metrics summary
        """
        return {
            "total_transformations": self.total_transformations,
            "successful_transformations": self.successful_transformations,
            "total_tokens": self.total_tokens,
            "average_latency_ms": self.average_latency_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "by_message_type": self.by_message_type,
        }

    @property
    def success_rate(self) -> float:
        """
        Calculate the success rate as a percentage.
        
        Returns:
            Success rate between 0.0 and 1.0
        """
        if self.total_transformations == 0:
            return 0.0
        return self.successful_transformations / self.total_transformations

    @property
    def failure_count(self) -> int:
        """
        Calculate the number of failed transformations.
        
        Returns:
            Number of failures
        """
        return self.total_transformations - self.successful_transformations
