"""
ReadMcpResourceTool – Read a resource from an MCP server.
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


class ReadMcpResourceInput(BaseModel):
    server_name: str = Field(..., description="MCP server name.")
    resource_uri: str = Field(..., description="Resource URI to read.")


class ReadMcpResourceTool(Tool):
    """Read a resource from an MCP server."""

    name = "read_mcp_resource"
    aliases = ["mcp_read_resource"]
    search_hint = "mcp resource read"

    def get_input_schema(self) -> dict[str, Any]:
        return ReadMcpResourceInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Read a resource from an MCP server."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("server_name"):
            return ValidationResult(result=False, message="server_name is required.")
        if not input.get("resource_uri"):
            return ValidationResult(result=False, message="resource_uri is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ReadMcpResourceInput.model_validate(args)
        return ToolResult(
            data={
                "type": "read_mcp_resource",
                "server_name": parsed.server_name,
                "resource_uri": parsed.resource_uri,
            }
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ReadMcpResource"
