"""
SubscribePrTool – Subscribe to pull request events.
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


class SubscribePrInput(BaseModel):
    repo: str = Field(..., description="Repository in owner/name format.")
    pr_number: int = Field(..., description="Pull request number.")
    events: list[str] = Field(
        default_factory=lambda: ["comment", "review", "merge"],
        description="Events to subscribe to.",
    )


class SubscribePrTool(Tool):
    """Subscribe to pull request events."""

    name = "subscribe_pr"
    aliases: list[str] = []
    search_hint = "subscribe pr pull request events"

    def get_input_schema(self) -> dict[str, Any]:
        return SubscribePrInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Subscribe to pull request events."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("repo"):
            return ValidationResult(result=False, message="repo is required.")
        if not input.get("pr_number"):
            return ValidationResult(result=False, message="pr_number is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = SubscribePrInput.model_validate(args)
        return ToolResult(
            data={
                "type": "subscribe_pr",
                "repo": parsed.repo,
                "pr_number": parsed.pr_number,
                "events": parsed.events,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "SubscribePR"
