"""
Task lifecycle management.

Creates, tracks, and kills tasks of all types.
"""

from __future__ import annotations

import logging
from typing import Optional

from .task import TaskHandle, TaskStatus, TaskType, generate_task_id

logger = logging.getLogger(__name__)


class TaskManager:
    """Central registry for all running and completed tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskHandle] = {}

    def create_task(
        self,
        task_type: TaskType,
        *,
        label: str = "",
        task_id: Optional[str] = None,
    ) -> TaskHandle:
        """Create and register a new task."""
        tid = task_id or generate_task_id()
        handle = TaskHandle(task_id=tid, task_type=task_type, label=label)
        self._tasks[tid] = handle
        logger.debug("Created task %s (%s)", tid, task_type.value)
        return handle

    def get_task_by_id(self, task_id: str) -> Optional[TaskHandle]:
        return self._tasks.get(task_id)

    def get_tasks(
        self,
        *,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
    ) -> list[TaskHandle]:
        """List tasks with optional filtering."""
        result = list(self._tasks.values())
        if status is not None:
            result = [t for t in result if t.status == status]
        if task_type is not None:
            result = [t for t in result if t.task_type == task_type]
        return result

    def get_running_tasks(self) -> list[TaskHandle]:
        return [t for t in self._tasks.values() if t.is_running]

    def get_background_tasks(self) -> list[TaskHandle]:
        from .task import is_background_task
        return [t for t in self._tasks.values() if is_background_task(t)]

    def kill_task(self, task_id: str) -> bool:
        """Kill a running task. Returns True if found and killed."""
        handle = self._tasks.get(task_id)
        if handle is None:
            return False
        if not handle.is_running:
            return False
        handle.kill()
        handle.mark_cancelled()
        logger.info("Killed task %s", task_id)
        return True

    def kill_all(self) -> int:
        """Kill all running tasks. Returns count killed."""
        count = 0
        for handle in self._tasks.values():
            if handle.is_running:
                handle.kill()
                handle.mark_cancelled()
                count += 1
        return count

    def remove_completed(self, *, keep_last: int = 50) -> int:
        """Prune completed tasks from the registry, keeping the most recent."""
        completed = sorted(
            [t for t in self._tasks.values() if t.is_done],
            key=lambda t: t.completed_at or 0,
        )
        to_remove = completed[:-keep_last] if len(completed) > keep_last else []
        for t in to_remove:
            del self._tasks[t.task_id]
        return len(to_remove)

    def clear(self) -> None:
        self._tasks.clear()
