"""
SendUserFileTool – Send a file to the user.
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
from claude_code.tools.utils import format_tool_error, resolve_path


class SendUserFileInput(BaseModel):
    file_path: str = Field(..., description="Path to the file to send.")
    description: Optional[str] = Field(None, description="Description of the file.")


class SendUserFileTool(Tool):
    """Send a file to the user for download."""

    name = "send_user_file"
    aliases: list[str] = []
    search_hint = "send file user download"

    def get_input_schema(self) -> dict[str, Any]:
        return SendUserFileInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Send a file to the user for download."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("file_path"):
            return ValidationResult(result=False, message="file_path is required.")
        resolved = resolve_path(input["file_path"], context.cwd)
        if not resolved.exists():
            return ValidationResult(result=False, message=f"File not found: {resolved}")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = SendUserFileInput.model_validate(args)
        resolved = resolve_path(parsed.file_path, context.cwd)
        return ToolResult(
            data={"type": "send_user_file", "file_path": str(resolved), "description": parsed.description}
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "SendFile"
