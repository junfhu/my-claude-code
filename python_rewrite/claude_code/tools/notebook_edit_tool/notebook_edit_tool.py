"""
NotebookEditTool – Edit cells in Jupyter notebooks (.ipynb).

Supports replace, insert, and delete operations on notebook cells.
"""

from __future__ import annotations

import json
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
    format_tool_error,
    resolve_path,
    write_notebook_cell,
)


class NotebookEditInput(BaseModel):
    notebook_path: str = Field(..., description="Absolute path to the .ipynb file.")
    cell_number: int = Field(..., description="0-based index of the cell to edit.")
    new_source: str = Field(..., description="New source content for the cell.")
    cell_type: Optional[str] = Field(
        None, description="Cell type: 'code' or 'markdown'. Keeps current type if omitted."
    )
    edit_mode: str = Field(
        "replace", description="One of 'replace', 'insert', 'delete'."
    )


class NotebookEditTool(Tool):
    """Edit a cell in a Jupyter notebook file."""

    name = "notebook_edit"
    aliases = ["nb_edit"]
    search_hint = "notebook jupyter cell edit insert delete"

    def get_input_schema(self) -> dict[str, Any]:
        return NotebookEditInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Edit a cell in a Jupyter notebook — replace, insert, or delete."

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use notebook_edit to modify Jupyter notebooks. Specify cell_number "
            "(0-based) and edit_mode ('replace', 'insert', or 'delete')."
        )

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        nb_path = input.get("notebook_path", "")
        if not nb_path:
            return ValidationResult(result=False, message="notebook_path is required.")
        if not nb_path.endswith(".ipynb"):
            return ValidationResult(result=False, message="File must be a .ipynb notebook.")

        mode = input.get("edit_mode", "replace")
        if mode not in ("replace", "insert", "delete"):
            return ValidationResult(
                result=False, message=f"Invalid edit_mode: {mode}"
            )

        resolved = resolve_path(nb_path, context.cwd)
        if not resolved.exists():
            return ValidationResult(result=False, message=f"File not found: {resolved}")

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
        parsed = NotebookEditInput.model_validate(args)
        resolved = resolve_path(parsed.notebook_path, context.cwd)

        try:
            result = write_notebook_cell(
                resolved,
                parsed.cell_number,
                parsed.new_source,
                cell_type=parsed.cell_type,
                edit_mode=parsed.edit_mode,
            )
        except json.JSONDecodeError:
            return ToolResult(data=format_tool_error("Invalid notebook JSON."))
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Notebook edit failed: {exc}"))

        total = result["total"]
        return ToolResult(
            data=f"Notebook updated: {parsed.edit_mode} cell {parsed.cell_number} "
            f"({total} cells total)"
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return False

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "NotebookEdit"

    def get_path(self, input: dict[str, Any]) -> Optional[str]:
        return input.get("notebook_path")

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Editing notebook..."
