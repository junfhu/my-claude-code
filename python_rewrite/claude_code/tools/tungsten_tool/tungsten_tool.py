"""
TungstenTool – Tungsten integration for advanced code analysis.

Provides deep code analysis capabilities powered by the Tungsten engine.
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
from claude_code.tools.utils import format_tool_error


class TungstenInput(BaseModel):
    action: str = Field(
        ..., description="Analysis action: 'analyze', 'index', 'query', 'status'."
    )
    target: Optional[str] = Field(None, description="File or directory to analyze.")
    query: Optional[str] = Field(None, description="Query string for search.")
    options: dict[str, Any] = Field(default_factory=dict, description="Additional options.")


class TungstenTool(Tool):
    """Deep code analysis via Tungsten engine."""

    name = "tungsten"
    aliases: list[str] = []
    search_hint = "tungsten analyze code deep analysis"

    def get_input_schema(self) -> dict[str, Any]:
        return TungstenInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Deep code analysis powered by the Tungsten engine."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        valid_actions = {"analyze", "index", "query", "status"}
        action = input.get("action", "")
        if action not in valid_actions:
            return ValidationResult(
                result=False,
                message=f"action must be one of: {', '.join(sorted(valid_actions))}",
            )
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = TungstenInput.model_validate(args)
        return ToolResult(
            data={
                "type": "tungsten",
                "action": parsed.action,
                "target": parsed.target,
                "query": parsed.query,
                "options": parsed.options,
            }
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return input.get("action") in ("query", "status")

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Tungsten"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Analyzing code..."
