"""
Multi-agent orchestration — coordinator mode.

When coordinator mode is active, the main agent acts as a coordinator that
decomposes complex tasks into subtasks, routes them to worker agents,
and aggregates results.

Mirrors src/coordinator/coordinatorMode.ts.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Callable, Optional

from .types import (
    AgentInfo,
    AgentRole,
    AgentStatus,
    CoordinatorState,
    CoordinatorTask,
)

logger = logging.getLogger(__name__)

# Tools available to worker agents
ASYNC_AGENT_ALLOWED_TOOLS = frozenset({
    "Bash",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Glob",
    "Grep",
    "LS",
    "WebFetch",
    "NotebookRead",
    "NotebookEdit",
    "TodoWrite",
    "WebSearch",
})

# Internal tools not exposed to users
INTERNAL_WORKER_TOOLS = frozenset({
    "TeamCreate",
    "TeamDelete",
    "SendMessage",
    "SyntheticOutput",
})


def is_coordinator_mode() -> bool:
    """Check if coordinator mode is enabled."""
    return os.environ.get("CLAUDE_CODE_COORDINATOR_MODE", "").lower() in ("1", "true", "yes")


def match_session_mode(session_mode: Optional[str]) -> Optional[str]:
    """Sync current mode with a resumed session's mode.

    Returns a warning message if the mode was switched, or ``None``.
    """
    if session_mode is None:
        return None

    current = is_coordinator_mode()
    session_is_coordinator = session_mode == "coordinator"

    if current == session_is_coordinator:
        return None

    if session_is_coordinator:
        os.environ["CLAUDE_CODE_COORDINATOR_MODE"] = "1"
        return "Entered coordinator mode to match resumed session."
    else:
        os.environ.pop("CLAUDE_CODE_COORDINATOR_MODE", None)
        return "Exited coordinator mode to match resumed session."


def get_coordinator_user_context(
    mcp_clients: list[dict[str, str]],
    scratchpad_dir: Optional[str] = None,
) -> dict[str, str]:
    """Build coordinator-mode context for the system prompt."""
    if not is_coordinator_mode():
        return {}

    is_simple = os.environ.get("CLAUDE_CODE_SIMPLE", "").lower() in ("1", "true")
    if is_simple:
        worker_tools = ", ".join(sorted(["Bash", "Read", "Edit"]))
    else:
        worker_tools = ", ".join(
            sorted(ASYNC_AGENT_ALLOWED_TOOLS - INTERNAL_WORKER_TOOLS)
        )

    content = f"Workers spawned via the Agent tool have access to these tools: {worker_tools}"

    if mcp_clients:
        names = ", ".join(c.get("name", "unknown") for c in mcp_clients)
        content += f"\n\nMCP servers available: {names}"

    if scratchpad_dir:
        content += (
            f"\n\nScratchpad directory for inter-agent communication: {scratchpad_dir}\n"
            "Workers can read/write files in this directory to share context."
        )

    return {"coordinator_context": content}


class CoordinatorMode:
    """Manages multi-agent orchestration.

    The coordinator:
    1. Receives a complex task from the user
    2. Decomposes it into subtasks
    3. Spawns worker agents for each subtask
    4. Routes messages between agents
    5. Aggregates results
    """

    def __init__(self) -> None:
        self._state = CoordinatorState()
        self._on_agent_complete: Optional[Callable[[str, str], None]] = None

    @property
    def state(self) -> CoordinatorState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state.is_active

    def activate(self) -> None:
        """Enable coordinator mode."""
        self._state.is_active = True
        os.environ["CLAUDE_CODE_COORDINATOR_MODE"] = "1"
        logger.info("Coordinator mode activated")

    def deactivate(self) -> None:
        """Disable coordinator mode."""
        self._state.is_active = False
        os.environ.pop("CLAUDE_CODE_COORDINATOR_MODE", None)
        logger.info("Coordinator mode deactivated")

    # -- Agent management ----------------------------------------------------

    def register_agent(
        self,
        agent_id: Optional[str] = None,
        role: AgentRole = AgentRole.WORKER,
        tools: Optional[list[str]] = None,
    ) -> AgentInfo:
        """Register a new agent."""
        aid = agent_id or str(uuid.uuid4())[:8]
        agent = AgentInfo(
            agent_id=aid,
            role=role,
            tools=tools or list(ASYNC_AGENT_ALLOWED_TOOLS - INTERNAL_WORKER_TOOLS),
        )
        self._state.agents[aid] = agent
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        return self._state.agents.get(agent_id)

    def remove_agent(self, agent_id: str) -> bool:
        return self._state.agents.pop(agent_id, None) is not None

    def list_agents(self, *, role: Optional[AgentRole] = None) -> list[AgentInfo]:
        agents = list(self._state.agents.values())
        if role:
            agents = [a for a in agents if a.role == role]
        return agents

    # -- Task management -----------------------------------------------------

    def create_task(
        self,
        description: str,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> CoordinatorTask:
        """Create a new task for assignment to a worker."""
        task = CoordinatorTask(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            context=context or {},
        )
        self._state.pending_tasks.append(task)
        return task

    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a pending task to an agent."""
        for task in self._state.pending_tasks:
            if task.task_id == task_id:
                agent = self._state.agents.get(agent_id)
                if agent is None:
                    return False
                task.assigned_to = agent_id
                task.status = AgentStatus.RUNNING
                agent.status = AgentStatus.RUNNING
                agent.task_description = task.description
                return True
        return False

    def complete_task(self, task_id: str, result: str) -> bool:
        """Mark a task as completed."""
        for i, task in enumerate(self._state.pending_tasks):
            if task.task_id == task_id:
                task.status = AgentStatus.DONE
                task.result = result
                self._state.pending_tasks.pop(i)
                self._state.completed_tasks.append(task)

                if task.assigned_to:
                    agent = self._state.agents.get(task.assigned_to)
                    if agent:
                        agent.status = AgentStatus.DONE
                        agent.result = result
                        if self._on_agent_complete:
                            self._on_agent_complete(task.assigned_to, result)
                return True
        return False

    def fail_task(self, task_id: str, error: str) -> bool:
        """Mark a task as failed."""
        for i, task in enumerate(self._state.pending_tasks):
            if task.task_id == task_id:
                task.status = AgentStatus.FAILED
                self._state.pending_tasks.pop(i)
                self._state.completed_tasks.append(task)

                if task.assigned_to:
                    agent = self._state.agents.get(task.assigned_to)
                    if agent:
                        agent.status = AgentStatus.FAILED
                        agent.error = error
                return True
        return False

    # -- Result aggregation --------------------------------------------------

    def get_results(self) -> list[dict[str, Any]]:
        """Collect results from all completed tasks."""
        return [
            {
                "task_id": t.task_id,
                "description": t.description,
                "status": t.status.value,
                "result": t.result,
                "assigned_to": t.assigned_to,
            }
            for t in self._state.completed_tasks
        ]

    def on_agent_complete(self, callback: Callable[[str, str], None]) -> None:
        self._on_agent_complete = callback

    # -- Routing helpers -----------------------------------------------------

    def get_idle_worker(self) -> Optional[AgentInfo]:
        """Find an idle worker agent for task assignment."""
        for agent in self._state.agents.values():
            if agent.role == AgentRole.WORKER and agent.status == AgentStatus.IDLE:
                return agent
        return None

    def get_worker_tools_description(self) -> str:
        """Human-readable list of tools available to workers."""
        tools = sorted(ASYNC_AGENT_ALLOWED_TOOLS - INTERNAL_WORKER_TOOLS)
        return ", ".join(tools)
