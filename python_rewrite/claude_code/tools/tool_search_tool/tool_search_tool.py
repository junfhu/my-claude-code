"""
ToolSearchTool – Search available tools by name or capability.
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


class ToolSearchInput(BaseModel):
    query: str = Field(..., description="Search query for finding tools.")


class ToolSearchTool(Tool):
    """Search available tools by name, alias, or capability description."""

    name = "tool_search"
    aliases = ["find_tool"]
    search_hint = "tool search find discover"

    def get_input_schema(self) -> dict[str, Any]:
        return ToolSearchInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Search available tools by name or capability."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("query", "").strip():
            return ValidationResult(result=False, message="query is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ToolSearchInput.model_validate(args)
        query = parsed.query.lower()

        matches: list[str] = []
        for tool in context.tools:
            searchable = f"{tool.name} {' '.join(tool.aliases or [])} {tool.search_hint}".lower()
            if query in searchable:
                aliases = f" (aliases: {', '.join(tool.aliases)})" if tool.aliases else ""
                matches.append(f"  {tool.name}{aliases}")

        if not matches:
            return ToolResult(data=f"No tools matching '{parsed.query}'.")

        return ToolResult(
            data=f"Tools matching '{parsed.query}':\n" + "\n".join(matches)
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ToolSearch"
