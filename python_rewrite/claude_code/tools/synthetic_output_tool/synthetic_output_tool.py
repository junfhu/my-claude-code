"""
SyntheticOutputTool – Generate synthetic tool output for testing.

Useful for testing the tool result pipeline without side effects.
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


class SyntheticOutputInput(BaseModel):
    output: str = Field("synthetic output", description="The synthetic output to return.")
    output_type: str = Field("text", description="Type: 'text', 'json', 'error'.")
    delay_ms: int = Field(0, description="Simulated delay in milliseconds.")


class SyntheticOutputTool(Tool):
    """Generate synthetic tool output for testing purposes."""

    name = "synthetic_output"
    aliases: list[str] = []
    search_hint = "synthetic output test mock"

    def get_input_schema(self) -> dict[str, Any]:
        return SyntheticOutputInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Generate synthetic tool output for testing."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        import asyncio
        import json

        parsed = SyntheticOutputInput.model_validate(args)

        if parsed.delay_ms > 0:
            await asyncio.sleep(parsed.delay_ms / 1000.0)

        if parsed.output_type == "error":
            return ToolResult(data=f"[ERROR] {parsed.output}")
        if parsed.output_type == "json":
            try:
                data = json.loads(parsed.output)
                return ToolResult(data=data)
            except json.JSONDecodeError:
                return ToolResult(data={"raw": parsed.output})

        return ToolResult(data=parsed.output)

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "SyntheticOutput"
