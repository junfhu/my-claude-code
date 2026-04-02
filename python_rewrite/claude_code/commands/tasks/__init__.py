"""
/tasks — View and manage background tasks.

Type: local_jsx (renders task listing).
"""

from __future__ import annotations

from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Task registry (in-process)
# ---------------------------------------------------------------------------

class _TaskRegistry:
    """
    Simple in-process registry for background tasks.

    The real implementation tracks sub-agent bash processes, long-running
    tool calls, etc.
    """

    def __init__(self) -> None:
        self._tasks: list[dict[str, Any]] = []
        self._next_id: int = 1

    def add(self, description: str, **meta: Any) -> int:
        tid = self._next_id
        self._next_id += 1
        self._tasks.append(
            {"id": tid, "description": description, "status": "running", **meta}
        )
        return tid

    def complete(self, task_id: int) -> None:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = "completed"
                return

    def cancel(self, task_id: int) -> None:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = "cancelled"
                return

    def list_active(self) -> list[dict[str, Any]]:
        return [t for t in self._tasks if t["status"] == "running"]

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._tasks)


# Module-level singleton
task_registry = _TaskRegistry()


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/tasks [list|cancel <id>]``.

    - No args / list:  Show all tasks.
    - cancel <id>:     Cancel a running task.
    """
    parts = args.strip().split() if args else []
    sub = parts[0].lower() if parts else "list"

    if sub in ("list", "ls", ""):
        tasks = task_registry.list_all()
        if not tasks:
            return TextResult(value="No background tasks.")

        lines = ["Background Tasks", "=" * 40, ""]
        for t in tasks:
            icon = {
                "running": "\u25b6",     # ▶
                "completed": "\u2713",   # ✓
                "cancelled": "\u2717",   # ✗
            }.get(t["status"], "?")
            lines.append(
                f"  [{icon}] #{t['id']}  {t['description']}  ({t['status']})"
            )
        return TextResult(value="\n".join(lines))

    if sub == "cancel":
        if len(parts) < 2:
            return TextResult(value="Usage: /tasks cancel <id>")
        try:
            task_id = int(parts[1])
        except ValueError:
            return TextResult(value=f"Invalid task ID: {parts[1]!r}")
        task_registry.cancel(task_id)
        return TextResult(value=f"Task #{task_id} cancelled.")

    return TextResult(value="Usage: /tasks [list|cancel <id>]")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="tasks",
    description="List and manage background tasks",
    aliases=["bashes"],
    call=_execute,
)
