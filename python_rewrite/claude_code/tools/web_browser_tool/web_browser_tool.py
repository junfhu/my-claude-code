"""
WebBrowserTool – Browser automation for web interaction.

Opens URLs, takes screenshots, clicks elements, types text.
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


class WebBrowserInput(BaseModel):
    action: str = Field(
        ...,
        description="Action: 'navigate', 'screenshot', 'click', 'type', 'scroll', 'close'.",
    )
    url: Optional[str] = Field(None, description="URL to navigate to.")
    selector: Optional[str] = Field(None, description="CSS selector for click/type.")
    text: Optional[str] = Field(None, description="Text to type.")
    direction: Optional[str] = Field(None, description="Scroll direction: 'up' or 'down'.")


class WebBrowserTool(Tool):
    """Automate browser interactions."""

    name = "web_browser"
    aliases = ["browser"]
    search_hint = "browser web navigate click type screenshot"

    def get_input_schema(self) -> dict[str, Any]:
        return WebBrowserInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Automate browser interactions: navigate, click, type, screenshot."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        valid_actions = {"navigate", "screenshot", "click", "type", "scroll", "close"}
        action = input.get("action", "")
        if action not in valid_actions:
            return ValidationResult(
                result=False,
                message=f"action must be one of: {', '.join(sorted(valid_actions))}",
            )
        if action == "navigate" and not input.get("url"):
            return ValidationResult(result=False, message="url required for navigate.")
        if action == "click" and not input.get("selector"):
            return ValidationResult(result=False, message="selector required for click.")
        if action == "type" and not input.get("text"):
            return ValidationResult(result=False, message="text required for type.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = WebBrowserInput.model_validate(args)

        # In a full implementation, this would use Playwright or Puppeteer
        # to drive a headless browser.
        return ToolResult(
            data={
                "type": "browser_action",
                "action": parsed.action,
                "url": parsed.url,
                "selector": parsed.selector,
                "text": parsed.text,
                "direction": parsed.direction,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Browser"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"Browser: {input.get('action', '?')}..."
        return "Using browser..."
