"""
ReplTool – Execute code in a REPL session.

Runs code in a persistent interpreter (Python, Node, etc.).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from claude_code.tool import (
    InterruptBehavior,
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)
from claude_code.tools.utils import (
    format_tool_error,
    run_subprocess,
    truncate_output,
    MAX_OUTPUT_CHARS,
)


class ReplInput(BaseModel):
    code: str = Field(..., description="The code to execute.")
    language: str = Field(
        "python", description="Language / runtime: python, node, etc."
    )


class ReplTool(Tool):
    """Execute code in a REPL and return the output."""

    name = "repl"
    aliases = ["eval", "execute_code"]
    search_hint = "repl eval execute code python node"

    def get_input_schema(self) -> dict[str, Any]:
        return ReplInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Execute code in a REPL session and return the output."

    async def get_prompt(self, **kwargs: Any) -> str:
        return "Use the repl tool to run code snippets and see their output."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        if not input.get("code", "").strip():
            return ValidationResult(result=False, message="code is required.")
        lang = input.get("language", "python")
        if lang not in ("python", "node", "ruby", "bash"):
            return ValidationResult(
                result=False,
                message=f"Unsupported language: {lang}. Use python, node, ruby, or bash.",
            )
        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ASK, updated_input=input
        )

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ReplInput.model_validate(args)

        interpreters = {
            "python": ["python3", "-c"],
            "node": ["node", "-e"],
            "ruby": ["ruby", "-e"],
            "bash": ["bash", "-c"],
        }

        cmd_prefix = interpreters.get(parsed.language, ["python3", "-c"])
        cmd = cmd_prefix + [parsed.code]

        result = await run_subprocess(cmd, cwd=context.cwd, timeout=30.0)

        parts: list[str] = []
        if result["stdout"]:
            parts.append(result["stdout"])
        if result["stderr"]:
            parts.append(f"<stderr>\n{result['stderr']}\n</stderr>")
        if result["timed_out"]:
            parts.append("[Execution timed out after 30s]")
        if result["returncode"] != 0 and not result["timed_out"]:
            parts.append(f"[Exit code: {result['returncode']}]")

        output = "\n".join(parts) if parts else "(no output)"
        return ToolResult(data=truncate_output(output, MAX_OUTPUT_CHARS))

    def interrupt_behavior(self) -> InterruptBehavior:
        return InterruptBehavior.ALLOW

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "REPL"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Executing code..."
