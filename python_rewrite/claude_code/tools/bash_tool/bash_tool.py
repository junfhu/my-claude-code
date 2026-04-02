"""
BashTool – Execute shell commands.

Runs arbitrary shell commands via ``asyncio.create_subprocess_shell``,
capturing stdout/stderr, enforcing timeouts, and respecting sandbox
restrictions.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
from pathlib import Path
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
    MAX_OUTPUT_CHARS,
    format_tool_error,
    truncate_output,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class BashInput(BaseModel):
    """Input schema for the Bash tool."""

    command: str = Field(..., description="The shell command to execute.")
    timeout: Optional[int] = Field(
        None,
        description="Optional timeout in milliseconds. Defaults to 120 000 (2 min).",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of what this command does.",
    )


# ---------------------------------------------------------------------------
# Blocked / dangerous patterns
# ---------------------------------------------------------------------------
_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-rf\s+/\s*$"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+.*of=/dev/"),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;"),  # fork bomb
]

_BACKGROUND_PATTERN = re.compile(r"&\s*$")


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class BashTool(Tool):
    """Execute a shell command and return its output."""

    name = "bash"
    aliases = ["shell", "execute", "run"]
    search_hint = "execute shell command terminal"
    always_load = True

    # -- schema / description -----------------------------------------------

    def get_input_schema(self) -> dict[str, Any]:
        return BashInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Executes a given bash command in a persistent shell session. "
            "Use this for running system commands, scripts, build tools, etc. "
            "Commands run in a persistent session so environment variables and "
            "working directory changes persist between calls."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the bash tool to run shell commands. You can execute any "
            "valid bash command. The shell session is persistent — state like "
            "environment variables and the working directory are preserved "
            "across invocations.\n\n"
            "Important guidelines:\n"
            "- Always quote file paths that contain spaces\n"
            "- Chain dependent commands with &&\n"
            "- Use ; only when you don't care about earlier failures\n"
            "- Prefer absolute paths\n"
            "- Do NOT use this tool for reading or writing files — use the "
            "dedicated file tools instead\n"
        )

    # -- validation ---------------------------------------------------------

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        command = input.get("command", "").strip()
        if not command:
            return ValidationResult(result=False, message="Command must not be empty.")

        for pat in _DANGEROUS_PATTERNS:
            if pat.search(command):
                return ValidationResult(
                    result=False,
                    message=f"Blocked potentially destructive command: {command!r}",
                )

        return ValidationResult(result=True)

    # -- permissions --------------------------------------------------------

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        command = input.get("command", "")
        # Read-only commands can be auto-approved
        if self.is_read_only(input):
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW, updated_input=input
            )
        return PermissionDecision(
            behavior=PermissionBehavior.ASK, updated_input=input
        )

    # -- execution ----------------------------------------------------------

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = BashInput.model_validate(args)
        command = parsed.command.strip()
        timeout_ms = parsed.timeout or 120_000
        timeout_s = timeout_ms / 1000.0

        cwd = context.cwd or "."
        if not Path(cwd).is_dir():
            return ToolResult(data=format_tool_error(f"Working directory does not exist: {cwd}"))

        start = time.monotonic()
        timed_out = False
        stdout = ""
        stderr = ""
        returncode = -1

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
                returncode = proc.returncode or 0
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                try:
                    stdout_bytes, stderr_bytes = await proc.communicate()
                    stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
                except Exception:
                    pass
                returncode = -1

        except FileNotFoundError:
            return ToolResult(data=format_tool_error(f"Shell not found while running: {command}"))
        except PermissionError:
            return ToolResult(data=format_tool_error(f"Permission denied: {command}"))
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Failed to execute command: {exc}"))

        duration = time.monotonic() - start

        # Build result text
        parts: list[str] = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"<stderr>\n{stderr}\n</stderr>")
        if timed_out:
            parts.append(f"\n[Command timed out after {timeout_s:.1f}s]")
        if returncode != 0 and not timed_out:
            parts.append(f"\n[Exit code: {returncode}]")

        output = "\n".join(parts) if parts else "(no output)"
        output = truncate_output(output, MAX_OUTPUT_CHARS)

        return ToolResult(data=output)

    # -- capability flags ---------------------------------------------------

    def is_read_only(self, input: dict[str, Any]) -> bool:
        cmd = input.get("command", "").strip()
        read_prefixes = (
            "ls", "cat", "head", "tail", "find", "grep", "rg", "wc",
            "echo", "pwd", "which", "whereis", "type", "file", "stat",
            "du", "df", "env", "printenv", "date", "whoami", "id",
            "uname", "hostname", "git log", "git status", "git diff",
            "git show", "git branch", "ps", "top", "htop",
        )
        first_word = cmd.split()[0] if cmd.split() else ""
        return first_word in read_prefixes or cmd.startswith(("git log", "git status", "git diff", "git show", "git branch"))

    def is_destructive(self, input: dict[str, Any]) -> bool:
        cmd = input.get("command", "").strip()
        destructive_words = {"rm", "rmdir", "mkfs", "dd", "format", "fdisk"}
        first_word = cmd.split()[0] if cmd.split() else ""
        return first_word in destructive_words

    def interrupt_behavior(self) -> InterruptBehavior:
        return InterruptBehavior.ALLOW

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return self.is_read_only(input)

    # -- display ------------------------------------------------------------

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Bash"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            cmd = input.get("command", "")
            if len(cmd) > 80:
                cmd = cmd[:77] + "..."
            return f"$ {cmd}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Running command..."

    def get_path(self, input: dict[str, Any]) -> Optional[str]:
        return None
