"""TaskListTool – List all managed tasks."""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel

from claude_code.tool import (
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)


class TaskListInput(BaseModel):
    pass


class TaskListTool(Tool):
    """List all managed tasks and their status."""

    name = "task_list"
    aliases: list[str] = []
    search_hint = "task list all"

    def get_input_schema(self) -> dict[str, Any]:
        return TaskListInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "List all managed tasks and their status."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
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
        tasks = context.extra.get("tasks", {})
        if not tasks:
            return ToolResult(data="No tasks found.")

        lines: list[str] = ["ID       | Status     | Prompt"]
        lines.append("-" * 60)
        for tid, task in tasks.items():
            prompt = task["prompt"][:40]
            lines.append(f"{tid:<8} | {task['status']:<10} | {prompt}")

        return ToolResult(data="\n".join(lines))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TaskList"
