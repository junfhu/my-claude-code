"""
VerifyPlanTool – Verify that a plan was executed correctly.
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


class VerifyPlanInput(BaseModel):
    plan_id: Optional[str] = Field(None, description="ID of the plan to verify.")
    checks: list[str] = Field(default_factory=list, description="Specific checks to run.")


class VerifyPlanTool(Tool):
    """Verify that a plan was executed correctly."""

    name = "verify_plan_execution"
    aliases = ["verify_plan"]
    search_hint = "verify plan execution check"

    def get_input_schema(self) -> dict[str, Any]:
        return VerifyPlanInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Verify that a plan was executed correctly."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = VerifyPlanInput.model_validate(args)
        return ToolResult(
            data={"type": "verify_plan", "plan_id": parsed.plan_id, "checks": parsed.checks}
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "VerifyPlan"
