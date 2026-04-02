"""
BriefTool – Send a brief message to the user.

Used for short status updates or acknowledgements.
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


class BriefInput(BaseModel):
    message: str = Field(..., description="The message to display to the user.")


class BriefTool(Tool):
    """Send a brief message or status update to the user."""

    name = "brief"
    aliases: list[str] = []
    search_hint = "brief message status user"

    def get_input_schema(self) -> dict[str, Any]:
        return BriefInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Send a brief message to the user."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("message", "").strip():
            return ValidationResult(result=False, message="message is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = BriefInput.model_validate(args)
        return ToolResult(data=parsed.message)

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Brief"
