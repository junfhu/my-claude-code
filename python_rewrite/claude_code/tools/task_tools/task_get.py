"""TaskGetTool – Get details for a specific task."""

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


class TaskGetInput(BaseModel):
    task_id: str = Field(..., description="The task ID.")


class TaskGetTool(Tool):
    """Get details for a specific task."""

    name = "task_get"
    aliases: list[str] = []
    search_hint = "task get details"

    def get_input_schema(self) -> dict[str, Any]:
        return TaskGetInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Get details and current status of a specific task."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        if not input.get("task_id"):
            return ValidationResult(result=False, message="task_id is required.")
        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TaskGetInput.model_validate(args)
        tasks = context.extra.get("tasks", {})
        task = tasks.get(parsed.task_id)
        if not task:
            return ToolResult(data=format_tool_error(f"Task not found: {parsed.task_id}"))

        lines = [
            f"Task ID:    {task['id']}",
            f"Status:     {task['status']}",
            f"Background: {task['background']}",
            f"Prompt:     {task['prompt']}",
        ]
        if task.get("output"):
            lines.append(f"Output:     {task['output']}")

        return ToolResult(data="\n".join(lines))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TaskGet"
