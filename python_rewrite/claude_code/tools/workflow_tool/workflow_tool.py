"""
WorkflowTool – Execute predefined workflows.

Workflows are sequences of tool invocations defined declaratively.
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
from claude_code.tools.utils import format_tool_error


class WorkflowInput(BaseModel):
    workflow_name: str = Field(..., description="Name of the workflow to execute.")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parameters for the workflow."
    )


class WorkflowTool(Tool):
    """Execute a predefined workflow."""

    name = "workflow"
    aliases: list[str] = []
    search_hint = "workflow sequence automation"

    def get_input_schema(self) -> dict[str, Any]:
        return WorkflowInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Execute a predefined workflow (sequence of tool invocations)."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("workflow_name", "").strip():
            return ValidationResult(result=False, message="workflow_name is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = WorkflowInput.model_validate(args)
        return ToolResult(
            data={
                "type": "workflow_execute",
                "workflow_name": parsed.workflow_name,
                "parameters": parsed.parameters,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Workflow"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Running workflow..."
