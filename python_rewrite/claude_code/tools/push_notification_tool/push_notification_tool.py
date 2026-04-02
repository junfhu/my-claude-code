"""
PushNotificationTool – Send a push notification to the user.
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


class PushNotificationInput(BaseModel):
    title: str = Field(..., description="Notification title.")
    body: str = Field(..., description="Notification body.")
    urgency: str = Field("normal", description="'low', 'normal', or 'high'.")


class PushNotificationTool(Tool):
    """Send a push notification to the user."""

    name = "push_notification"
    aliases = ["notify"]
    search_hint = "push notification alert"

    def get_input_schema(self) -> dict[str, Any]:
        return PushNotificationInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Send a push notification to the user."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("title"):
            return ValidationResult(result=False, message="title is required.")
        if not input.get("body"):
            return ValidationResult(result=False, message="body is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = PushNotificationInput.model_validate(args)
        return ToolResult(
            data={"type": "push_notification", "title": parsed.title, "body": parsed.body, "urgency": parsed.urgency}
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Notify"
