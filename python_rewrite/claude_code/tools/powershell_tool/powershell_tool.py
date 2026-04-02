"""
PowerShellTool – Execute PowerShell commands.

Similar to BashTool but targets PowerShell on Windows/cross-platform.
"""

from __future__ import annotations

import asyncio
import os
import time
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
from claude_code.tools.utils import format_tool_error, truncate_output, MAX_OUTPUT_CHARS


class PowerShellInput(BaseModel):
    command: str = Field(..., description="The PowerShell command to execute.")
    timeout: Optional[int] = Field(None, description="Timeout in milliseconds.")


class PowerShellTool(Tool):
    """Execute PowerShell commands."""

    name = "powershell"
    aliases = ["pwsh", "ps1"]
    search_hint = "powershell windows command"

    def get_input_schema(self) -> dict[str, Any]:
        return PowerShellInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Execute PowerShell commands."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("command", "").strip():
            return ValidationResult(result=False, message="command is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = PowerShellInput.model_validate(args)
        timeout_s = (parsed.timeout or 120_000) / 1000.0

        # Try pwsh first (cross-platform), then powershell (Windows)
        for shell in ("pwsh", "powershell"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    shell, "-Command", parsed.command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=context.cwd,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

                parts: list[str] = []
                if stdout:
                    parts.append(stdout)
                if stderr:
                    parts.append(f"<stderr>\n{stderr}\n</stderr>")
                if proc.returncode != 0:
                    parts.append(f"[Exit code: {proc.returncode}]")

                return ToolResult(
                    data=truncate_output("\n".join(parts) if parts else "(no output)", MAX_OUTPUT_CHARS)
                )
            except FileNotFoundError:
                continue
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(data=format_tool_error(f"Command timed out after {timeout_s}s"))

        return ToolResult(data=format_tool_error("PowerShell not found. Install pwsh or powershell."))

    def interrupt_behavior(self) -> InterruptBehavior:
        return InterruptBehavior.ALLOW

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "PowerShell"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Running PowerShell..."
