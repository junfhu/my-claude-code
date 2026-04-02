"""
SnipTool – Store and retrieve code snippets.

Manages a snippet cache for the session.
"""

from __future__ import annotations

import uuid
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


class SnipInput(BaseModel):
    action: str = Field("save", description="'save', 'get', or 'list'.")
    snippet_id: Optional[str] = Field(None, description="Snippet ID (for 'get').")
    content: Optional[str] = Field(None, description="Content to save.")
    language: Optional[str] = Field(None, description="Language hint.")
    description: Optional[str] = Field(None, description="Short description.")


class SnipTool(Tool):
    """Save, retrieve, and list code snippets."""

    name = "snip"
    aliases = ["snippet"]
    search_hint = "snip snippet code save retrieve"

    def get_input_schema(self) -> dict[str, Any]:
        return SnipInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Save, retrieve, and list code snippets."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        action = input.get("action", "save")
        if action not in ("save", "get", "list"):
            return ValidationResult(result=False, message="action must be save, get, or list.")
        if action == "save" and not input.get("content"):
            return ValidationResult(result=False, message="content is required for save.")
        if action == "get" and not input.get("snippet_id"):
            return ValidationResult(result=False, message="snippet_id is required for get.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = SnipInput.model_validate(args)
        snippets = context.extra.setdefault("snippets", {})

        if parsed.action == "list":
            if not snippets:
                return ToolResult(data="No snippets saved.")
            lines = [f"  {sid}: {s.get('description', '(no description)')}" for sid, s in snippets.items()]
            return ToolResult(data="Saved snippets:\n" + "\n".join(lines))

        if parsed.action == "get":
            snip = snippets.get(parsed.snippet_id)
            if not snip:
                return ToolResult(data=format_tool_error(f"Snippet not found: {parsed.snippet_id}"))
            return ToolResult(data=truncate_output(snip["content"], MAX_OUTPUT_CHARS))

        # save
        sid = str(uuid.uuid4())[:8]
        snippets[sid] = {
            "content": parsed.content,
            "language": parsed.language,
            "description": parsed.description or "",
        }
        return ToolResult(data=f"Snippet saved: {sid}")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Snip"
