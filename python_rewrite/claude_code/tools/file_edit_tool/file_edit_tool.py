"""
FileEditTool – Perform exact string replacement edits.

Supports old_string/new_string replacement, optional replace_all,
quote normalisation, and mtime-based staleness detection.
"""

from __future__ import annotations

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
    normalize_quotes,
    resolve_path,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class FileEditInput(BaseModel):
    """Input schema for the FileEdit tool."""

    file_path: str = Field(
        ..., description="The absolute path to the file to modify."
    )
    old_string: str = Field(
        ..., description="The exact text to find and replace."
    )
    new_string: str = Field(
        ..., description="The replacement text (must differ from old_string)."
    )
    replace_all: bool = Field(
        False,
        description="If True, replace every occurrence rather than just the first.",
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class FileEditTool(Tool):
    """Perform exact string replacements in files.

    The tool finds *old_string* in the file and replaces it with *new_string*.
    The replacement must be unambiguous (unique match) unless *replace_all*
    is set.  Staleness is checked via mtime.
    """

    name = "edit"
    aliases = ["file_edit", "sed"]
    search_hint = "edit modify replace string file"
    always_load = True

    # -- schema / description -----------------------------------------------

    def get_input_schema(self) -> dict[str, Any]:
        return FileEditInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Performs exact string replacements in files. "
            "You must read the file first. The old_string must be unique "
            "unless replace_all is True."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use the edit tool for surgical text replacements in existing files.\n"
            "Rules:\n"
            "- You MUST read the file first before editing.\n"
            "- Preserve the exact indentation from the file.\n"
            "- old_string must be unique in the file (or use replace_all).\n"
            "- old_string and new_string must be different.\n"
            "- ALWAYS prefer editing over writing whole files.\n"
        )

    # -- validation ---------------------------------------------------------

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        file_path = input.get("file_path", "")
        old_string = input.get("old_string", "")
        new_string = input.get("new_string", "")

        if not file_path:
            return ValidationResult(result=False, message="file_path is required.")

        if is_device_path(file_path):
            return ValidationResult(
                result=False, message=f"Cannot edit device path: {file_path}"
            )

        if old_string == new_string:
            return ValidationResult(
                result=False,
                message="old_string and new_string must be different.",
            )

        if not old_string:
            return ValidationResult(
                result=False, message="old_string must not be empty."
            )

        resolved = resolve_path(file_path, context.cwd)

        if not resolved.exists():
            return ValidationResult(
                result=False, message=f"File not found: {resolved}"
            )
        if not resolved.is_file():
            return ValidationResult(
                result=False, message=f"Not a file: {resolved}"
            )

        # Must have been read first
        recorded = context.read_file_timestamps.get(str(resolved))
        if recorded is None:
            return ValidationResult(
                result=False,
                message=f"You must read {resolved} before editing it.",
            )

        # Staleness check
        if check_file_staleness(resolved, recorded):
            return ValidationResult(
                result=False,
                message=(
                    f"File {resolved} has been modified since you last read it. "
                    "Please re-read before editing."
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
        parsed = FileEditInput.model_validate(args)
        resolved = resolve_path(parsed.file_path, context.cwd)

        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Cannot read file: {exc}"))

        old = parsed.old_string
        new = parsed.new_string
        replace_all = parsed.replace_all

        # Try exact match first
        count = content.count(old)

        # If no exact match, try normalised quotes
        if count == 0:
            normalised_content = normalize_quotes(content)
            normalised_old = normalize_quotes(old)
            if normalised_content.count(normalised_old) > 0:
                # Use the normalised version
                old = normalised_old
                content = normalised_content
                count = content.count(old)

        if count == 0:
            return ToolResult(
                data=format_tool_error(
                    f"old_string not found in {resolved}. "
                    "Make sure it matches the file content exactly, "
                    "including whitespace and indentation."
                )
            )

        if count > 1 and not replace_all:
            return ToolResult(
                data=format_tool_error(
                    f"old_string appears {count} times in {resolved}. "
                    "Provide more context to make it unique, or set replace_all=True."
                )
            )

        # Perform replacement
        if replace_all:
            new_content = content.replace(old, new)
            replacements = count
        else:
            new_content = content.replace(old, new, 1)
            replacements = 1

        try:
            resolved.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Failed to write: {exc}"))

        # Update recorded mtime
        context.read_file_timestamps[str(resolved)] = file_mtime(resolved)

        # Build a snippet around the replacement for context
        snippet = _get_replacement_snippet(new_content, new)
        msg = f"Replaced {replacements} occurrence(s) in {resolved}"
        if snippet:
            msg += f"\n\nSnippet:\n{snippet}"

        return ToolResult(data=msg)

    # -- capability flags ---------------------------------------------------

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return False

    def is_destructive(self, input: dict[str, Any]) -> bool:
        return False  # edits are generally reversible

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return False

    # -- display ------------------------------------------------------------

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Edit"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"Edit {input.get('file_path', '?')}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Editing file..."

    def get_path(self, input: dict[str, Any]) -> Optional[str]:
        return input.get("file_path")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_replacement_snippet(
    content: str, new_string: str, context_lines: int = 3
) -> str:
    """Return a few lines of context around the first occurrence of *new_string*."""
    idx = content.find(new_string)
    if idx == -1:
        return ""

    before = content[:idx]
    after = content[idx + len(new_string):]

    before_lines = before.split("\n")[-context_lines:]
    after_lines = after.split("\n")[:context_lines]

    snippet_lines = before_lines + [new_string.split("\n")[0] + " ..."] + after_lines
    return "\n".join(snippet_lines)
