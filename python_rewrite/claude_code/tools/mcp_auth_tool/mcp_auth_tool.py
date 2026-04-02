"""
McpAuthTool – Authenticate with an MCP server.
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


class McpAuthInput(BaseModel):
    server_name: str = Field(..., description="MCP server to authenticate with.")
    method: str = Field("oauth", description="Auth method: 'oauth', 'token', 'api_key'.")
    credentials: Optional[dict[str, str]] = Field(None, description="Credentials if needed.")


class McpAuthTool(Tool):
    """Authenticate with an MCP server."""

    name = "mcp_auth"
    aliases = ["mcp_authenticate"]
    search_hint = "mcp auth authenticate login"

    def get_input_schema(self) -> dict[str, Any]:
        return McpAuthInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Authenticate with an MCP server."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("server_name"):
            return ValidationResult(result=False, message="server_name is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = McpAuthInput.model_validate(args)
        return ToolResult(
            data={
                "type": "mcp_auth",
                "server_name": parsed.server_name,
                "method": parsed.method,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "McpAuth"
