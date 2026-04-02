"""TaskStopTool – Stop a running task."""

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


class TaskStopInput(BaseModel):
    task_id: str = Field(..., description="The task ID to stop.")


class TaskStopTool(Tool):
    """Stop a running task."""

    name = "task_stop"
    aliases: list[str] = []
    search_hint = "task stop cancel kill"

    def get_input_schema(self) -> dict[str, Any]:
        return TaskStopInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Stop a running task."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        if not input.get("task_id"):
            return ValidationResult(result=False, message="task_id is required.")
        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TaskStopInput.model_validate(args)
        tasks = context.extra.get("tasks", {})
        task = tasks.get(parsed.task_id)
        if not task:
            return ToolResult(data=format_tool_error(f"Task not found: {parsed.task_id}"))

        task["status"] = "stopped"
        return ToolResult(data=f"Task {parsed.task_id} stopped.")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TaskStop"
