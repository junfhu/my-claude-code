"""TeamDeleteTool – Delete a team."""

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
from claude_code.tools.utils import format_tool_error


class TeamDeleteInput(BaseModel):
    team_id: str = Field(..., description="The team ID to delete.")


class TeamDeleteTool(Tool):
    """Delete a team."""

    name = "team_delete"
    aliases: list[str] = []
    search_hint = "team delete remove"

    def get_input_schema(self) -> dict[str, Any]:
        return TeamDeleteInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Delete a team."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("team_id"):
            return ValidationResult(result=False, message="team_id is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TeamDeleteInput.model_validate(args)
        teams = context.extra.get("teams", {})
        if parsed.team_id not in teams:
            return ToolResult(data=format_tool_error(f"Team not found: {parsed.team_id}"))
        del teams[parsed.team_id]
        return ToolResult(data=f"Team {parsed.team_id} deleted.")

    def is_destructive(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TeamDelete"
