"""
Core simulation modules.

This package contains the core components of the VDOS simulation engine,
extracted from the monolithic engine.py for better modularity and maintainability.

Modules:
    simulation_state: State persistence and database management
    tick_manager: Tick advancement and timing operations
    event_system: Event injection and processing
    communication_hub: Email and chat coordination
    worker_runtime: Worker runtime state management
    project_manager: Project and team management
"""

__version__ = "1.0.0"

# Import core modules
from .simulation_state import SimulationState, SimulationStatus, SIM_SCHEMA
from .tick_manager import TickManager
from .event_system import EventSystem, InboundMessage
from .communication_hub import CommunicationHub
from .worker_runtime import WorkerRuntimeManager, WorkerRuntime
from .project_manager import ProjectManager

# Module exports
__all__ = [
    "SimulationState",
    "SimulationStatus",
    "SIM_SCHEMA",
    "TickManager",
    "EventSystem",
    "InboundMessage",
    "CommunicationHub",
    "WorkerRuntimeManager",
    "WorkerRuntime",
    "ProjectManager",
]
