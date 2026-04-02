"""
ListPeersTool – List connected peer agents.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel

from claude_code.tool import (
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)


class ListPeersInput(BaseModel):
    pass


class ListPeersTool(Tool):
    """List connected peer agents."""

    name = "list_peers"
    aliases: list[str] = []
    search_hint = "peers list agents connected"

    def get_input_schema(self) -> dict[str, Any]:
        return ListPeersInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "List connected peer agents."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        peers = context.extra.get("peers", [])
        if not peers:
            return ToolResult(data="No connected peers.")
        lines = [f"  {p.get('id', '?')}: {p.get('name', 'unnamed')}" for p in peers]
        return ToolResult(data=f"Connected peers ({len(peers)}):\n" + "\n".join(lines))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ListPeers"
