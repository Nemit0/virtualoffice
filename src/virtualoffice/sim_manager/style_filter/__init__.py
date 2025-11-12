"""
Communication Style Filter Module.

This module provides AI-powered message transformation to apply persona-specific
communication styles to generated emails and chat messages.
"""

from .example_generator import StyleExampleGenerator
from .filter import CommunicationStyleFilter
from .metrics import FilterMetrics
from .models import FilterMetricsSummary, FilterResult, StyleExample

__all__ = [
    "CommunicationStyleFilter",
    "FilterMetrics",
    "FilterMetricsSummary",
    "FilterResult",
    "StyleExample",
    "StyleExampleGenerator",
]
