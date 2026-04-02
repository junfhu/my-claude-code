"""
CtxInspectTool – Inspect the current conversation context.

Shows message history, token usage, and tool state.
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


class CtxInspectInput(BaseModel):
    section: str = Field(
        "all",
        description="What to inspect: 'messages', 'tools', 'state', 'tokens', or 'all'.",
    )


class CtxInspectTool(Tool):
    """Inspect the current conversation context."""

    name = "ctx_inspect"
    aliases = ["context_inspect", "inspect"]
    search_hint = "context inspect messages tokens state"

    def get_input_schema(self) -> dict[str, Any]:
        return CtxInspectInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Inspect the current conversation context."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        valid = {"messages", "tools", "state", "tokens", "all"}
        section = input.get("section", "all")
        if section not in valid:
            return ValidationResult(
                result=False, message=f"section must be one of: {', '.join(sorted(valid))}"
            )
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = CtxInspectInput.model_validate(args)
        parts: list[str] = []

        if parsed.section in ("all", "state"):
            parts.append(f"=== State ===\nCWD: {context.cwd}\nSession: {context.session_id}")
            parts.append(f"Tracked files: {len(context.read_file_timestamps)}")
            parts.append(f"Extra keys: {list(context.extra.keys())}")

        if parsed.section in ("all", "tools"):
            tool_names = [t.name for t in context.tools]
            parts.append(f"=== Tools ({len(tool_names)}) ===\n" + ", ".join(tool_names))

        return ToolResult(data="\n\n".join(parts) if parts else "No data.")

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "CtxInspect"
