"""
GlobTool – Fast file name/path pattern matching using glob.

Supports brace expansion, recursive patterns, and result truncation.
"""

from __future__ import annotations

import fnmatch
import os
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
    truncate_output,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class GlobInput(BaseModel):
    """Input schema for the Glob tool."""

    pattern: str = Field(
        ...,
        description=(
            "The glob pattern to match files against, e.g. '**/*.py' or 'src/**/*.{ts,tsx}'."
        ),
    )
    path: Optional[str] = Field(
        None,
        description="Directory to search in. Defaults to the current working directory.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _expand_braces(pattern: str) -> list[str]:
    """Expand simple brace expressions like ``*.{ts,tsx}`` into multiple patterns."""
    match = re.search(r"\{([^}]+)\}", pattern)
    if not match:
        return [pattern]

    prefix = pattern[: match.start()]
    suffix = pattern[match.end():]
    alternatives = match.group(1).split(",")

    expanded: list[str] = []
    for alt in alternatives:
        expanded.extend(_expand_braces(prefix + alt.strip() + suffix))
    return expanded


def _glob_search(base: Path, pattern: str, max_results: int = 10_000) -> list[str]:
    """Search *base* for files matching *pattern*, with brace expansion."""
    patterns = _expand_braces(pattern)
    results: list[str] = []
    seen: set[str] = set()

    for pat in patterns:
        for match in base.glob(pat):
            s = str(match)
            if s not in seen:
                seen.add(s)
                results.append(s)
                if len(results) >= max_results:
                    return results
    return results


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class GlobTool(Tool):
    """Find files by name / path pattern using glob matching."""

    name = "find_file_by_name"
    aliases = ["glob", "find_file"]
    search_hint = "find file name path glob pattern"
    always_load = True

    # -- schema / description -----------------------------------------------

    def get_input_schema(self) -> dict[str, Any]:
        return GlobInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Fast file name/path pattern matching using glob patterns. "
            "Supports brace expansion (e.g. **/*.{ts,tsx}). "
            "Matches against file paths, not file contents."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the find_file_by_name tool to search for files by name or path pattern.\n"
            "Examples:\n"
            "  '*.py'            — Python files in current dir only\n"
            "  '**/*.js'         — JS files recursively\n"
            "  'src/**/*.ts'     — TS files under src/\n"
            "  'test_*.py'       — test files in current dir\n"
            "  '**/*.{ts,tsx}'   — TS + TSX files recursively\n"
            "Do NOT use this for searching file contents — use grep instead."
        )

    # -- validation ---------------------------------------------------------

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        pattern = input.get("pattern", "")
        if not pattern:
            return ValidationResult(result=False, message="pattern is required.")
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
        parsed = GlobInput.model_validate(args)
        search_dir = resolve_path(parsed.path or ".", context.cwd)

        if not search_dir.is_dir():
            return ToolResult(data=format_tool_error(f"Not a directory: {search_dir}"))

        try:
            results = _glob_search(search_dir, parsed.pattern)
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Glob error: {exc}"))

        if not results:
            return ToolResult(data="No files matched the pattern.")

        # Sort and format
        results.sort()
        total = len(results)
        output = "\n".join(results)

        if total > 1000:
            output = "\n".join(results[:1000])
            output += f"\n\n... and {total - 1000} more files (truncated)"

        return ToolResult(data=truncate_output(output, MAX_OUTPUT_CHARS))

    # -- capability flags ---------------------------------------------------

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    # -- display ------------------------------------------------------------

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Glob"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"find '{input.get('pattern', '?')}'"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Searching for files..."

    def is_search_or_read_command(self, input: dict[str, Any]) -> Optional[dict[str, Any]]:
        return {"type": "glob", "pattern": input.get("pattern")}
