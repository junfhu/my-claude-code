"""TaskCreateTool – Create a new managed task."""

from __future__ import annotations

import uuid
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


class TaskCreateInput(BaseModel):
    prompt: str = Field(..., description="Instructions for the task.")
    background: bool = Field(False, description="Run in background.")


class TaskCreateTool(Tool):
    """Create a new managed task."""

    name = "task_create"
    aliases: list[str] = []
    search_hint = "task create new"

    def get_input_schema(self) -> dict[str, Any]:
        return TaskCreateInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Create a new managed task."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        if not input.get("prompt", "").strip():
            return ValidationResult(result=False, message="prompt is required.")
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
        parsed = TaskCreateInput.model_validate(args)
        task_id = str(uuid.uuid4())[:8]

        tasks = context.extra.setdefault("tasks", {})
        tasks[task_id] = {
            "id": task_id,
            "prompt": parsed.prompt,
            "status": "pending",
            "background": parsed.background,
            "output": None,
        }

        return ToolResult(
            data=f"Task created: {task_id}\nPrompt: {parsed.prompt}\nBackground: {parsed.background}"
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TaskCreate"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Creating task..."
