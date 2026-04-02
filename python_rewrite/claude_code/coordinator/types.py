"""
Coordinator type definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentRole(str, Enum):
    """Role of an agent in the coordinator."""
    COORDINATOR = "coordinator"
    WORKER = "worker"


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentInfo:
    """Metadata about a worker agent."""
    agent_id: str
    role: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    task_description: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CoordinatorTask:
    """A unit of work to be assigned to a worker."""
    task_id: str
    description: str
    assigned_to: Optional[str] = None
    status: AgentStatus = AgentStatus.IDLE
    result: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinatorState:
    """Overall state of the coordinator."""
    is_active: bool = False
    agents: dict[str, AgentInfo] = field(default_factory=dict)
    pending_tasks: list[CoordinatorTask] = field(default_factory=list)
    completed_tasks: list[CoordinatorTask] = field(default_factory=list)
