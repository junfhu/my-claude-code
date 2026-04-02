"""
SendMessageTool – Send a message to a teammate / peer agent.
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


class SendMessageInput(BaseModel):
    recipient: str = Field(..., description="Recipient agent or teammate ID.")
    message: str = Field(..., description="The message content.")


class SendMessageTool(Tool):
    """Send a message to a teammate or peer agent."""

    name = "send_message"
    aliases = ["message"]
    search_hint = "send message teammate communication"

    def get_input_schema(self) -> dict[str, Any]:
        return SendMessageInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Send a message to a teammate or peer agent."

    async def get_prompt(self, **kwargs: Any) -> str:
        return "Use send_message to communicate with other agents or teammates."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("recipient", "").strip():
            return ValidationResult(result=False, message="recipient is required.")
        if not input.get("message", "").strip():
            return ValidationResult(result=False, message="message is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = SendMessageInput.model_validate(args)
        # Deliver through the coordinator's messaging system
        return ToolResult(
            data={
                "type": "send_message",
                "recipient": parsed.recipient,
                "message": parsed.message,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Message"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Sending message..."
