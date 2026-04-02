"""
LspTool – Language Server Protocol operations.

Provides IDE-like features: go-to-definition, references, hover, diagnostics.
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


class LspInput(BaseModel):
    action: str = Field(
        ...,
        description=(
            "LSP action: 'definition', 'references', 'hover', "
            "'diagnostics', 'symbols', 'completion'."
        ),
    )
    file_path: str = Field(..., description="Path to the source file.")
    line: Optional[int] = Field(None, description="1-based line number.")
    column: Optional[int] = Field(None, description="1-based column number.")
    query: Optional[str] = Field(None, description="Symbol name to query.")


class LspTool(Tool):
    """Perform LSP (Language Server Protocol) operations."""

    name = "lsp"
    aliases = ["language_server"]
    search_hint = "lsp definition references hover diagnostics"

    def get_input_schema(self) -> dict[str, Any]:
        return LspInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Perform LSP operations: go-to-definition, find references, "
            "hover info, diagnostics, symbols, and completions."
        )

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        valid_actions = {"definition", "references", "hover", "diagnostics", "symbols", "completion"}
        action = input.get("action", "")
        if action not in valid_actions:
            return ValidationResult(
                result=False,
                message=f"action must be one of: {', '.join(sorted(valid_actions))}",
            )
        if not input.get("file_path"):
            return ValidationResult(result=False, message="file_path is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = LspInput.model_validate(args)

        # In a full implementation, this would connect to a running language server
        # via JSON-RPC and perform the requested action.
        return ToolResult(
            data={
                "type": "lsp_request",
                "action": parsed.action,
                "file_path": parsed.file_path,
                "line": parsed.line,
                "column": parsed.column,
                "query": parsed.query,
            }
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "LSP"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Querying language server..."
