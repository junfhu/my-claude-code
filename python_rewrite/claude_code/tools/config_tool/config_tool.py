"""
ConfigTool – Get or set configuration values.

Reads / writes the session or project configuration.
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


class ConfigInput(BaseModel):
    action: str = Field("get", description="'get' or 'set'.")
    key: str = Field(..., description="Configuration key.")
    value: Optional[Any] = Field(None, description="Value to set (required for 'set').")


class ConfigTool(Tool):
    """Get or set configuration values."""

    name = "config"
    aliases = ["setting", "settings"]
    search_hint = "config configuration get set"

    def get_input_schema(self) -> dict[str, Any]:
        return ConfigInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Get or set configuration values."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        action = input.get("action", "get")
        if action not in ("get", "set"):
            return ValidationResult(result=False, message="action must be 'get' or 'set'.")
        if not input.get("key"):
            return ValidationResult(result=False, message="key is required.")
        if action == "set" and input.get("value") is None:
            return ValidationResult(result=False, message="value is required for 'set'.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        action = input.get("action", "get")
        if action == "get":
            return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ConfigInput.model_validate(args)
        config = context.extra.setdefault("config", {})

        if parsed.action == "get":
            value = config.get(parsed.key)
            if value is None:
                return ToolResult(data=f"Config key '{parsed.key}' is not set.")
            return ToolResult(data=f"{parsed.key} = {value!r}")

        config[parsed.key] = parsed.value
        return ToolResult(data=f"Config set: {parsed.key} = {parsed.value!r}")

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return input.get("action", "get") == "get"

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Config"
