"""
McpTool – Generic MCP (Model Context Protocol) tool wrapper.

Wraps any tool exposed by an MCP server so it can be called uniformly
through the Claude Code tool interface.
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
from claude_code.tools.utils import format_tool_error, truncate_output, MAX_OUTPUT_CHARS


class McpToolInput(BaseModel):
    server_name: str = Field(..., description="Name of the MCP server.")
    tool_name: str = Field(..., description="Name of the tool on the server.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Input arguments for the MCP tool."
    )


class McpTool(Tool):
    """Call a tool on an MCP server."""

    name = "mcp"
    aliases = ["mcp_call_tool"]
    search_hint = "mcp model context protocol server tool"

    def get_input_schema(self) -> dict[str, Any]:
        return McpToolInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Execute a tool on an MCP server. Interacts with external services "
            "like Linear, GitHub, Slack, databases, and more."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the mcp tool to call tools on MCP servers. "
            "Provide server_name, tool_name, and arguments."
        )

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        if not input.get("server_name"):
            return ValidationResult(result=False, message="server_name is required.")
        if not input.get("tool_name"):
            return ValidationResult(result=False, message="tool_name is required.")
        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ASK, updated_input=input
        )

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = McpToolInput.model_validate(args)

        # In a full implementation this dispatches to the MCP client runtime.
        # Return a structured request for the coordinator to handle.
        return ToolResult(
            data={
                "type": "mcp_call",
                "server_name": parsed.server_name,
                "tool_name": parsed.tool_name,
                "arguments": parsed.arguments,
            },
            mcp_meta={
                "server_name": parsed.server_name,
                "tool_name": parsed.tool_name,
            },
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        if input:
            return f"MCP:{input.get('tool_name', '?')}"
        return "MCP"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"MCP {input.get('server_name', '?')}/{input.get('tool_name', '?')}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Calling MCP tool..."
