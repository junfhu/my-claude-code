"""
EnterPlanModeTool – Switch the agent into planning mode.

In plan mode the agent thinks through a task before executing.
"""

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


class EnterPlanModeInput(BaseModel):
    pass


class EnterPlanModeTool(Tool):
    """Enter planning mode."""

    name = "enter_plan_mode"
    aliases: list[str] = []
    search_hint = "plan mode enter"

    def get_input_schema(self) -> dict[str, Any]:
        return EnterPlanModeInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Enter planning mode — think through a task before executing."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        context.extra["plan_mode"] = True
        return ToolResult(data="Entered planning mode.")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "EnterPlanMode"
