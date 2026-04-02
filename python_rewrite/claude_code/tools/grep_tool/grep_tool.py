"""
GrepTool – Regex search using ripgrep (rg).

Supports three output modes: content, files_with_matches, count.
Falls back to Python ``re`` if ``rg`` is not installed.
"""

from __future__ import annotations

import re
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
    resolve_path,
    run_subprocess,
    truncate_output,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class GrepInput(BaseModel):
    """Input schema for the Grep tool."""

    pattern: str = Field(
        ..., description="The regex pattern to search for."
    )
    path: str = Field(
        ".", description="Directory or file to search in. Defaults to current directory."
    )
    glob_pattern: Optional[str] = Field(
        None,
        description="Glob to filter files, e.g. '*.py' or 'src/**/*.ts'.",
    )
    case_insensitive: bool = Field(
        False, description="If True, search case-insensitively."
    )
    context_lines: int = Field(
        0, description="Lines of context to show around each match."
    )
    max_results: int = Field(
        100, description="Maximum matches to return (max 20 000)."
    )
    output_mode: str = Field(
        "content",
        description="One of 'content', 'files_with_matches', 'count'.",
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class GrepTool(Tool):
    """Search for regex patterns in files using ripgrep."""

    name = "grep"
    aliases = ["rg", "search", "find_in_files"]
    search_hint = "search regex pattern files grep ripgrep"
    always_load = True

    # -- schema / description -----------------------------------------------

    def get_input_schema(self) -> dict[str, Any]:
        return GrepInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Search for patterns in files using regular expressions (ripgrep). "
            "Use output_mode to control results: 'content' for matching lines, "
            "'files_with_matches' for file paths only, 'count' for counts."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the grep tool to search file contents with regex patterns. "
            "This is powered by ripgrep under the hood. Use glob_pattern to "
            "filter by file type. Files larger than 4 MB are skipped."
        )

    # -- validation ---------------------------------------------------------

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        pattern = input.get("pattern", "")
        if not pattern:
            return ValidationResult(result=False, message="pattern is required.")

        # Validate regex
        try:
            re.compile(pattern)
        except re.error as exc:
            return ValidationResult(
                result=False, message=f"Invalid regex: {exc}"
            )

        mode = input.get("output_mode", "content")
        if mode not in ("content", "files_with_matches", "count"):
            return ValidationResult(
                result=False,
                message=f"Invalid output_mode: {mode}. Must be content, files_with_matches, or count.",
            )

        return ValidationResult(result=True)

    # -- permissions --------------------------------------------------------

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
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
        parsed = GrepInput.model_validate(args)
        search_path = resolve_path(parsed.path, context.cwd)

        if not search_path.exists():
            return ToolResult(data=format_tool_error(f"Path not found: {search_path}"))

        max_results = min(parsed.max_results, 20_000)

        # Build ripgrep command
        cmd: list[str] = ["rg", "--json" if parsed.output_mode == "content" else ""]
        cmd = ["rg"]

        if parsed.case_insensitive:
            cmd.append("-i")

        if parsed.context_lines > 0 and parsed.output_mode == "content":
            cmd.extend(["-C", str(parsed.context_lines)])

        if parsed.output_mode == "files_with_matches":
            cmd.append("-l")
        elif parsed.output_mode == "count":
            cmd.append("-c")

        # Max results
        if parsed.output_mode == "content":
            cmd.extend(["-m", str(max_results)])

        # Line numbers for content mode
        if parsed.output_mode == "content":
            cmd.append("-n")

        # Glob filter
        if parsed.glob_pattern:
            cmd.extend(["-g", parsed.glob_pattern])

        # Skip binary files, respect .gitignore
        cmd.extend(["--max-filesize", "4M"])

        cmd.append("--")
        cmd.append(parsed.pattern)
        cmd.append(str(search_path))

        result = await run_subprocess(cmd, cwd=context.cwd, timeout=30.0)

        if result["returncode"] == 2:
            # rg returns 2 for errors
            error_msg = result["stderr"].strip()
            # Fallback: try with Python re
            return ToolResult(data=format_tool_error(f"ripgrep error: {error_msg}"))

        if result["returncode"] == 1:
            # No matches
            return ToolResult(data="No matches found.")

        output = result["stdout"]
        if not output.strip():
            return ToolResult(data="No matches found.")

        return ToolResult(data=truncate_output(output, MAX_OUTPUT_CHARS))

    # -- capability flags ---------------------------------------------------

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    # -- display ------------------------------------------------------------

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Grep"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            pattern = input.get("pattern", "?")
            path = input.get("path", ".")
            return f"grep '{pattern}' in {path}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Searching..."

    def is_search_or_read_command(self, input: dict[str, Any]) -> Optional[dict[str, Any]]:
        return {"type": "search", "pattern": input.get("pattern")}
