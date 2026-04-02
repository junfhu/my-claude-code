"""
ExitWorktreeTool – Leave a git worktree.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel

from claude_code.tool import (
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)


class ExitWorktreeInput(BaseModel):
    cleanup: bool = True


class ExitWorktreeTool(Tool):
    """Exit the current git worktree."""

    name = "exit_worktree"
    aliases: list[str] = []
    search_hint = "worktree git exit leave"

    def get_input_schema(self) -> dict[str, Any]:
        return ExitWorktreeInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Exit the current git worktree."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ExitWorktreeInput.model_validate(args)
        return ToolResult(
            data={"type": "exit_worktree", "cleanup": parsed.cleanup}
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ExitWorktree"
