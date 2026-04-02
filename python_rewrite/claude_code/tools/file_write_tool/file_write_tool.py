"""
FileWriteTool – Create or overwrite files.

Enforces read-before-write semantics and staleness detection via mtime.
"""

from __future__ import annotations

import os
from pathlib import Path
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
from claude_code.tools.utils import (
    check_file_staleness,
    file_mtime,
    format_tool_error,
    is_device_path,
    resolve_path,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class FileWriteInput(BaseModel):
    """Input schema for the FileWrite tool."""

    file_path: str = Field(
        ..., description="The absolute path to the file to write."
    )
    content: str = Field(
        ..., description="The content to write to the file."
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class FileWriteTool(Tool):
    """Write content to a file, creating it if necessary.

    Enforces that existing files must have been read first (to prevent
    accidental data loss), and detects staleness via mtime comparison.
    """

    name = "write"
    aliases = ["file_write"]
    search_hint = "write create file"
    always_load = True

    # -- schema / description -----------------------------------------------

    def get_input_schema(self) -> dict[str, Any]:
        return FileWriteInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Write content to a file, overwriting it if it exists. "
            "The file_path must be an absolute path. "
            "If the file already exists you MUST read it first."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the write tool to create or overwrite files. Rules:\n"
            "- If the file already exists, you MUST use the read tool first.\n"
            "- ALWAYS prefer editing existing files with the edit tool.\n"
            "- NEVER write new files unless explicitly required.\n"
            "- Only use emojis if the user explicitly requests it.\n"
        )

    # -- validation ---------------------------------------------------------

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        file_path = input.get("file_path", "")
        if not file_path:
            return ValidationResult(result=False, message="file_path is required.")

        if is_device_path(file_path):
            return ValidationResult(
                result=False,
                message=f"Cannot write to device path: {file_path}",
            )

        resolved = resolve_path(file_path, context.cwd)

        # Read-before-write check: if file exists it must have been read
        if resolved.exists():
            recorded = context.read_file_timestamps.get(str(resolved))
            if recorded is None:
                return ValidationResult(
                    result=False,
                    message=(
                        f"You must read {resolved} before overwriting it. "
                        "Use the read tool first."
                    ),
                )

            # Staleness check
            if check_file_staleness(resolved, recorded):
                return ValidationResult(
                    result=False,
                    message=(
                        f"File {resolved} has been modified since you last read it. "
                        "Please re-read it before writing."
                    ),
                )

        return ValidationResult(result=True)

    # -- permissions --------------------------------------------------------

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
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
        parsed = FileWriteInput.model_validate(args)
        resolved = resolve_path(parsed.file_path, context.cwd)

        try:
            # Ensure parent directory exists
            resolved.parent.mkdir(parents=True, exist_ok=True)

            existed = resolved.exists()
            old_size = resolved.stat().st_size if existed else 0

            resolved.write_text(parsed.content, encoding="utf-8")
            new_size = resolved.stat().st_size

            # Update tracked mtime
            context.read_file_timestamps[str(resolved)] = file_mtime(resolved)

            if existed:
                msg = f"Wrote {new_size} bytes to {resolved} (was {old_size} bytes)"
            else:
                msg = f"Created {resolved} ({new_size} bytes)"

            return ToolResult(data=msg)

        except PermissionError:
            return ToolResult(
                data=format_tool_error(f"Permission denied: {resolved}")
            )
        except OSError as exc:
            return ToolResult(
                data=format_tool_error(f"Failed to write file: {exc}")
            )

    # -- capability flags ---------------------------------------------------

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return False

    def is_destructive(self, input: dict[str, Any]) -> bool:
        # Overwriting an existing file is destructive
        resolved = resolve_path(input.get("file_path", ""), ".")
        return resolved.exists()

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return False

    # -- display ------------------------------------------------------------

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Write"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"Write {input.get('file_path', '?')}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Writing file..."

    def get_path(self, input: dict[str, Any]) -> Optional[str]:
        return input.get("file_path")
