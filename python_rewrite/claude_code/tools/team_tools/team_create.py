"""TeamCreateTool – Create a new team."""

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


class TeamCreateInput(BaseModel):
    name: str = Field(..., description="Team name.")
    description: str = Field("", description="Team description.")


class TeamCreateTool(Tool):
    """Create a new team for collaborative work."""

    name = "team_create"
    aliases: list[str] = []
    search_hint = "team create new"

    def get_input_schema(self) -> dict[str, Any]:
        return TeamCreateInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Create a new team."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("name", "").strip():
            return ValidationResult(result=False, message="name is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TeamCreateInput.model_validate(args)
        team_id = str(uuid.uuid4())[:8]
        teams = context.extra.setdefault("teams", {})
        teams[team_id] = {"id": team_id, "name": parsed.name, "description": parsed.description}
        return ToolResult(data=f"Team created: {team_id} ({parsed.name})")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "TeamCreate"
