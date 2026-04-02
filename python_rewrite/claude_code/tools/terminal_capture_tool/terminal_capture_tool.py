"""
TerminalCaptureTool – Capture terminal screen content.
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


class TerminalCaptureInput(BaseModel):
    shell_id: Optional[str] = Field(None, description="Shell session ID to capture.")


class TerminalCaptureTool(Tool):
    """Capture the current terminal screen content."""

    name = "terminal_capture"
    aliases: list[str] = []
    search_hint = "terminal capture screen"

    def get_input_schema(self) -> dict[str, Any]:
        return TerminalCaptureInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Capture the current terminal screen content."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TerminalCaptureInput.model_validate(args)
        # In a full implementation, this reads the terminal emulator buffer
        return ToolResult(
            data={"type": "terminal_capture", "shell_id": parsed.shell_id}
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TerminalCapture"
