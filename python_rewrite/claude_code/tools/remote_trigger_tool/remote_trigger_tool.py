"""
RemoteTriggerTool – Trigger a remote action or webhook.
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


class RemoteTriggerInput(BaseModel):
    trigger_url: str = Field(..., description="URL or identifier of the remote trigger.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Payload to send.")


class RemoteTriggerTool(Tool):
    """Trigger a remote action or webhook."""

    name = "remote_trigger"
    aliases = ["webhook"]
    search_hint = "remote trigger webhook action"

    def get_input_schema(self) -> dict[str, Any]:
        return RemoteTriggerInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Trigger a remote action or webhook."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("trigger_url"):
            return ValidationResult(result=False, message="trigger_url is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = RemoteTriggerInput.model_validate(args)
        return ToolResult(
            data={"type": "remote_trigger", "trigger_url": parsed.trigger_url, "payload": parsed.payload}
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "RemoteTrigger"
