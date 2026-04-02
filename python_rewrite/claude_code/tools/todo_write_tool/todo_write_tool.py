"""
TodoWriteTool – Create and manage a structured task list.

Provides a way to track progress on complex multi-step tasks.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from claude_code.tool import (
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)
from claude_code.tools.utils import format_tool_error


class TodoItem(BaseModel):
    id: str = Field(..., description="Unique identifier for the todo item.")
    content: str = Field(..., description="Task description.")
    status: str = Field(
        "pending", description="One of: pending, in_progress, completed."
    )


class TodoWriteInput(BaseModel):
    todos: list[TodoItem] = Field(..., description="The updated list of todo items.")


class TodoWriteTool(Tool):
    """Create and manage a structured task list."""

    name = "todo_write"
    aliases = ["todo", "task_list"]
    search_hint = "todo task list progress tracking"
    always_load = True

    def get_input_schema(self) -> dict[str, Any]:
        return TodoWriteInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Create and manage a structured task list for the current coding session. "
            "Helps track progress on complex multi-step tasks."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use todo_write to track progress on multi-step tasks. "
            "Each item has an id, content (description), and status "
            "(pending, in_progress, completed). Only have one item "
            "in_progress at a time."
        )

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        todos = input.get("todos", [])
        if not isinstance(todos, list):
            return ValidationResult(result=False, message="todos must be a list.")

        valid_statuses = {"pending", "in_progress", "completed"}
        for item in todos:
            status = item.get("status", "")
            if status not in valid_statuses:
                return ValidationResult(
                    result=False,
                    message=f"Invalid status '{status}'. Must be: {', '.join(valid_statuses)}",
                )

        # Check only one in_progress
        in_progress = [t for t in todos if t.get("status") == "in_progress"]
        if len(in_progress) > 1:
            return ValidationResult(
                result=False,
                message="Only one todo item should be in_progress at a time.",
            )

        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW, updated_input=input
        )

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TodoWriteInput.model_validate(args)

        # Store in context
        context.extra["todos"] = [t.model_dump() for t in parsed.todos]

        # Format summary
        total = len(parsed.todos)
        completed = sum(1 for t in parsed.todos if t.status == "completed")
        in_progress = sum(1 for t in parsed.todos if t.status == "in_progress")
        pending = total - completed - in_progress

        lines: list[str] = ["Todos have been modified successfully."]
        lines.append(f"\nCurrent todo list:")
        for t in parsed.todos:
            status_icon = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
            icon = status_icon.get(t.status, "[ ]")
            lines.append(f"  {icon} {t.content} [{t.status}]")

        lines.append(f"\nSummary: {completed}/{total} completed, {in_progress} in progress, {pending} pending")

        return ToolResult(data="\n".join(lines))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return False

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Todo"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Updating tasks..."
