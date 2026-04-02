"""
EnterWorktreeTool – Enter a git worktree for isolated work.
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


class EnterWorktreeInput(BaseModel):
    branch: str = Field(..., description="Branch name for the worktree.")
    path: Optional[str] = Field(None, description="Path for the worktree directory.")


class EnterWorktreeTool(Tool):
    """Enter a git worktree for isolated work on a branch."""

    name = "enter_worktree"
    aliases: list[str] = []
    search_hint = "worktree git branch enter"

    def get_input_schema(self) -> dict[str, Any]:
        return EnterWorktreeInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Enter a git worktree for isolated work on a branch."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("branch", "").strip():
            return ValidationResult(result=False, message="branch is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = EnterWorktreeInput.model_validate(args)
        return ToolResult(
            data={"type": "enter_worktree", "branch": parsed.branch, "path": parsed.path}
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "EnterWorktree"
