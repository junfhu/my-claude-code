"""
Task type definitions.

Mirrors src/tasks/types.ts — defines task types, statuses, and handles.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class TaskType(str, Enum):
    """Concrete task types."""
    LOCAL_SHELL = "local_shell"
    LOCAL_AGENT = "local_agent"
    REMOTE_AGENT = "remote_agent"
    LOCAL_WORKFLOW = "local_workflow"
    MONITOR_MCP = "monitor_mcp"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    DREAM = "dream"


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BACKGROUNDED = "backgrounded"


def generate_task_id() -> str:
    """Generate a unique task identifier."""
    return f"task_{uuid.uuid4().hex[:12]}"


@dataclass
class TaskContext:
    """Runtime context for task execution."""
    cwd: str
    session_id: str
    env: dict[str, str] = field(default_factory=dict)
    timeout_ms: Optional[int] = None


@dataclass
class TaskHandle:
    """Handle to a running task, providing control and status access."""
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    label: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    is_backgrounded: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None
    output: Optional[str] = None
    _kill_fn: Optional[Callable[[], None]] = field(default=None, repr=False)

    @property
    def is_running(self) -> bool:
        return self.status in (TaskStatus.RUNNING, TaskStatus.BACKGROUNDED)

    @property
    def is_done(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    @property
    def pill_label(self) -> str:
        """Short label for UI display."""
        if self.label:
            return self.label
        return f"{self.task_type.value}:{self.task_id[-6:]}"

    def kill(self) -> None:
        if self._kill_fn:
            self._kill_fn()

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self, output: Optional[str] = None, exit_code: int = 0) -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.time()
        self.output = output
        self.exit_code = exit_code

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.completed_at = time.time()
        self.error = error

    def mark_cancelled(self) -> None:
        self.status = TaskStatus.CANCELLED
        self.completed_at = time.time()

    def background(self) -> None:
        self.is_backgrounded = True
        if self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.BACKGROUNDED


def is_background_task(handle: TaskHandle) -> bool:
    """Check if a task should appear in the background tasks indicator."""
    if handle.status not in (TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.BACKGROUNDED):
        return False
    if not handle.is_backgrounded:
        return False
    return True
