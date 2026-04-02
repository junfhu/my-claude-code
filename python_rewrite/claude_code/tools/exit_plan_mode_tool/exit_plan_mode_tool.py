"""
ExitPlanModeTool – Leave planning mode and resume execution.
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


class ExitPlanModeInput(BaseModel):
    pass


class ExitPlanModeTool(Tool):
    """Exit planning mode."""

    name = "exit_plan_mode"
    aliases: list[str] = []
    search_hint = "plan mode exit leave"

    def get_input_schema(self) -> dict[str, Any]:
        return ExitPlanModeInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Exit planning mode and resume execution."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        context.extra["plan_mode"] = False
        return ToolResult(data="Exited planning mode.")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ExitPlanMode"
