"""
ScheduleCronTool – Schedule a cron job / recurring task.
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


class ScheduleCronInput(BaseModel):
    schedule: str = Field(..., description="Cron expression, e.g. '0 * * * *'.")
    command: str = Field(..., description="Command or task to run.")
    description: Optional[str] = Field(None, description="Human-readable description.")


class ScheduleCronTool(Tool):
    """Schedule a recurring task."""

    name = "schedule_cron"
    aliases = ["cron"]
    search_hint = "schedule cron recurring job"

    def get_input_schema(self) -> dict[str, Any]:
        return ScheduleCronInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Schedule a recurring cron job."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("schedule"):
            return ValidationResult(result=False, message="schedule is required.")
        if not input.get("command"):
            return ValidationResult(result=False, message="command is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ScheduleCronInput.model_validate(args)
        return ToolResult(
            data={
                "type": "schedule_cron",
                "schedule": parsed.schedule,
                "command": parsed.command,
                "description": parsed.description,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ScheduleCron"
