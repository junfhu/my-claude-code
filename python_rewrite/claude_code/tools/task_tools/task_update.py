"""TaskUpdateTool – Update a task's status or prompt."""

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


class TaskUpdateInput(BaseModel):
    task_id: str = Field(..., description="The task ID.")
    status: Optional[str] = Field(None, description="New status.")
    prompt: Optional[str] = Field(None, description="Updated prompt.")


class TaskUpdateTool(Tool):
    """Update a task's status or prompt."""

    name = "task_update"
    aliases: list[str] = []
    search_hint = "task update modify"

    def get_input_schema(self) -> dict[str, Any]:
        return TaskUpdateInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Update a task's status or prompt."

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
        parsed = TaskUpdateInput.model_validate(args)
        tasks = context.extra.get("tasks", {})
        task = tasks.get(parsed.task_id)
        if not task:
            return ToolResult(data=format_tool_error(f"Task not found: {parsed.task_id}"))

        if parsed.status:
            task["status"] = parsed.status
        if parsed.prompt:
            task["prompt"] = parsed.prompt

        return ToolResult(data=f"Task {parsed.task_id} updated.")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TaskUpdate"
