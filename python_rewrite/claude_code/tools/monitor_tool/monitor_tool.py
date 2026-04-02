"""
MonitorTool – System resource monitoring.

Reports CPU, memory, disk, and process information.
"""

from __future__ import annotations

import os
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
from claude_code.tools.utils import run_subprocess, truncate_output, MAX_OUTPUT_CHARS


class MonitorInput(BaseModel):
    metric: str = Field(
        "all", description="What to monitor: 'cpu', 'memory', 'disk', 'processes', or 'all'."
    )


class MonitorTool(Tool):
    """Monitor system resources."""

    name = "monitor"
    aliases = ["sysinfo", "system"]
    search_hint = "monitor system cpu memory disk"

    def get_input_schema(self) -> dict[str, Any]:
        return MonitorInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Monitor system resources: CPU, memory, disk, processes."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        valid = {"cpu", "memory", "disk", "processes", "all"}
        metric = input.get("metric", "all")
        if metric not in valid:
            return ValidationResult(result=False, message=f"metric must be one of: {', '.join(sorted(valid))}")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = MonitorInput.model_validate(args)
        parts: list[str] = []

        if parsed.metric in ("all", "cpu"):
            result = await run_subprocess(["uptime"], cwd=context.cwd, timeout=5.0)
            parts.append(f"=== CPU / Load ===\n{result['stdout'].strip()}")

        if parsed.metric in ("all", "memory"):
            result = await run_subprocess(["free", "-h"], cwd=context.cwd, timeout=5.0)
            if result["returncode"] == 0:
                parts.append(f"=== Memory ===\n{result['stdout'].strip()}")

        if parsed.metric in ("all", "disk"):
            result = await run_subprocess(["df", "-h", "/"], cwd=context.cwd, timeout=5.0)
            parts.append(f"=== Disk ===\n{result['stdout'].strip()}")

        if parsed.metric in ("all", "processes"):
            result = await run_subprocess(
                ["ps", "aux", "--sort=-pcpu"], cwd=context.cwd, timeout=5.0
            )
            lines = result["stdout"].strip().split("\n")[:11]
            parts.append(f"=== Top Processes ===\n" + "\n".join(lines))

        output = "\n\n".join(parts) if parts else "No data available."
        return ToolResult(data=truncate_output(output, MAX_OUTPUT_CHARS))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Monitor"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Checking system resources..."
