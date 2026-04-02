"""
SleepTool – Pause execution for a specified duration.
"""

from __future__ import annotations

import asyncio
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


class SleepInput(BaseModel):
    seconds: float = Field(..., description="Number of seconds to sleep.", gt=0, le=300)


class SleepTool(Tool):
    """Pause execution for a given number of seconds."""

    name = "sleep"
    aliases = ["wait", "pause"]
    search_hint = "sleep wait pause delay"

    def get_input_schema(self) -> dict[str, Any]:
        return SleepInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Pause execution for a specified number of seconds (max 300)."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        seconds = input.get("seconds", 0)
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            return ValidationResult(result=False, message="seconds must be a positive number.")
        if seconds > 300:
            return ValidationResult(result=False, message="Maximum sleep is 300 seconds.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = SleepInput.model_validate(args)
        await asyncio.sleep(parsed.seconds)
        return ToolResult(data=f"Slept for {parsed.seconds} seconds.")

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Sleep"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Sleeping..."
