"""
ListMcpResourcesTool – List resources available on MCP servers.
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


class ListMcpResourcesInput(BaseModel):
    server_name: Optional[str] = Field(
        None, description="MCP server name. Lists all if omitted."
    )


class ListMcpResourcesTool(Tool):
    """List resources available from MCP servers."""

    name = "list_mcp_resources"
    aliases = ["mcp_list_resources"]
    search_hint = "mcp resources list"

    def get_input_schema(self) -> dict[str, Any]:
        return ListMcpResourcesInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "List resources available from MCP servers."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ListMcpResourcesInput.model_validate(args)
        return ToolResult(
            data={"type": "list_mcp_resources", "server_name": parsed.server_name}
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ListMcpResources"
