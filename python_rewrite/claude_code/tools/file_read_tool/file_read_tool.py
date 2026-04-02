"""
FileReadTool – Read files from the filesystem.

Supports plain text (with line numbers), images (base64-encoded),
Jupyter notebooks, and basic binary detection.
"""

from __future__ import annotations

import base64
import mimetypes
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
    MAX_OUTPUT_CHARS,
    format_tool_error,
    is_binary_file,
    is_device_path,
    is_image_file,
    read_file_with_line_numbers,
    read_image_as_base64,
    read_notebook,
    resolve_path,
    truncate_output,
    file_mtime,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class FileReadInput(BaseModel):
    """Input schema for the FileRead tool."""

    file_path: str = Field(
        ..., description="The absolute path to the file to read."
    )
    offset: Optional[int] = Field(
        None,
        description="Optional 1-based line number to start reading from.",
    )
    limit: Optional[int] = Field(
        None,
        description="Optional maximum number of lines to read.",
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class FileReadTool(Tool):
    """Read a file from the local filesystem.

    Returns line-numbered text for source files, base64 data for images,
    cell contents for Jupyter notebooks, and rejects device paths.
    """

    name = "read"
    aliases = ["file_read", "cat"]
    search_hint = "read file contents text image notebook"
    always_load = True

    # -- schema / description -----------------------------------------------

    def get_input_schema(self) -> dict[str, Any]:
        return FileReadInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Reads a file from the local filesystem. The file_path must be "
            "an absolute path. By default reads the whole file; you can "
            "optionally specify offset (1-based line) and limit."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the read tool to read files from the filesystem. "
            "The file_path parameter must be an absolute path. "
            "By default it reads up to 20 000 characters from the beginning. "
            "You can optionally specify a line offset and limit for long files. "
            "Lines longer than 2 000 characters are truncated."
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
                message=f"Cannot read device path: {file_path}",
            )

        resolved = resolve_path(file_path, context.cwd)
        if not resolved.exists():
            return ValidationResult(
                result=False,
                message=f"File not found: {resolved}",
            )
        if resolved.is_dir():
            return ValidationResult(
                result=False,
                message=f"Path is a directory, not a file: {resolved}. Use bash + ls to list directories.",
            )

        return ValidationResult(result=True)

    # -- permissions --------------------------------------------------------

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        # Reading is always allowed
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW, updated_input=input
        )

    # -- execution ----------------------------------------------------------

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = FileReadInput.model_validate(args)
        resolved = resolve_path(parsed.file_path, context.cwd)

        # Record read timestamp for staleness detection
        mtime = file_mtime(resolved)
        context.read_file_timestamps[str(resolved)] = mtime

        # -- Image files ----------------------------------------------------
        if is_image_file(str(resolved)):
            try:
                b64_data, media_type = read_image_as_base64(resolved)
                return ToolResult(
                    data={
                        "type": "image",
                        "media_type": media_type,
                        "data": b64_data,
                        "path": str(resolved),
                    }
                )
            except Exception as exc:
                return ToolResult(data=format_tool_error(f"Failed to read image: {exc}"))

        # -- Binary files ---------------------------------------------------
        if is_binary_file(str(resolved)):
            size = resolved.stat().st_size
            return ToolResult(
                data=f"Binary file ({size} bytes): {resolved}\n"
                f"Use an appropriate tool to process this file type."
            )

        # -- Jupyter notebooks ----------------------------------------------
        if resolved.suffix == ".ipynb":
            try:
                cells = read_notebook(resolved)
                parts: list[str] = []
                for i, cell in enumerate(cells):
                    ctype = cell.get("cell_type", "unknown")
                    source = "".join(cell.get("source", []))
                    parts.append(f"--- Cell {i} [{ctype}] ---\n{source}")
                output = "\n\n".join(parts)
                return ToolResult(data=truncate_output(output, MAX_OUTPUT_CHARS))
            except Exception as exc:
                return ToolResult(data=format_tool_error(f"Failed to read notebook: {exc}"))

        # -- Plain text -----------------------------------------------------
        try:
            text, total_lines = read_file_with_line_numbers(
                resolved,
                offset=parsed.offset or 0,
                limit=parsed.limit,
            )
        except UnicodeDecodeError:
            # Fall back to binary detection
            size = resolved.stat().st_size
            return ToolResult(
                data=f"Binary file ({size} bytes): {resolved}\n"
                f"Could not decode as UTF-8."
            )
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Failed to read file: {exc}"))

        # Meta header
        header_parts: list[str] = [str(resolved)]
        if parsed.offset and parsed.offset > 1:
            header_parts.append(f"lines {parsed.offset}-{(parsed.offset or 1) + (parsed.limit or total_lines) - 1}")
        header_parts.append(f"({total_lines} lines total)")
        header = " | ".join(header_parts)

        output = f"{header}\n{text}"
        return ToolResult(data=truncate_output(output, MAX_OUTPUT_CHARS))

    # -- capability flags ---------------------------------------------------

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    def interrupt_behavior(self):
        from claude_code.tool import InterruptBehavior
        return InterruptBehavior.ALLOW

    # -- display ------------------------------------------------------------

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Read"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"Read {input.get('file_path', '?')}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Reading file..."

    def get_path(self, input: dict[str, Any]) -> Optional[str]:
        return input.get("file_path")

    def is_search_or_read_command(self, input: dict[str, Any]) -> Optional[dict[str, Any]]:
        return {"type": "read", "path": input.get("file_path")}
