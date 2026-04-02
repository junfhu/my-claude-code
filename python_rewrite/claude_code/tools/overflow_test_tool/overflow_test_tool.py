"""
OverflowTestTool – Testing tool for context overflow scenarios.

Used internally to test how the system handles very large outputs.
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


class OverflowTestInput(BaseModel):
    size: int = Field(
        10_000, description="Number of characters to generate."
    )
    pattern: str = Field("x", description="Character pattern to repeat.")


class OverflowTestTool(Tool):
    """Generate a large output to test overflow handling."""

    name = "overflow_test"
    aliases: list[str] = []
    search_hint = "overflow test large output"

    def get_input_schema(self) -> dict[str, Any]:
        return OverflowTestInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Generate a large output to test context overflow handling."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        size = input.get("size", 0)
        if not isinstance(size, int) or size <= 0:
            return ValidationResult(result=False, message="size must be a positive integer.")
        if size > 10_000_000:
            return ValidationResult(result=False, message="Maximum size is 10,000,000 characters.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = OverflowTestInput.model_validate(args)
        output = (parsed.pattern * ((parsed.size // len(parsed.pattern)) + 1))[:parsed.size]
        return ToolResult(data=output)

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "OverflowTest"
