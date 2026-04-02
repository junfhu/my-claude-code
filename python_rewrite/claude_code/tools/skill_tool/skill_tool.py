"""
SkillTool – Invoke or discover custom skills.

Skills are project-specific scripts or workflows registered in
``.devin/skills/`` directories.
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
from claude_code.tools.utils import format_tool_error, resolve_path


class SkillInput(BaseModel):
    command: str = Field(
        "invoke", description="'invoke' to run a skill, 'list' to discover skills."
    )
    skill: Optional[str] = Field(None, description="Skill name (required for invoke).")
    path: Optional[str] = Field(None, description="Project path (required for list).")


class SkillTool(Tool):
    """Invoke or discover custom skills."""

    name = "skill"
    aliases: list[str] = []
    search_hint = "skill invoke discover custom"

    def get_input_schema(self) -> dict[str, Any]:
        return SkillInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Invoke or discover project-specific skills."

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use skill to invoke or list project-specific skills. "
            "'invoke' activates a skill by name; 'list' discovers skills."
        )

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        command = input.get("command", "invoke")
        if command not in ("invoke", "list"):
            return ValidationResult(result=False, message="command must be 'invoke' or 'list'.")
        if command == "invoke" and not input.get("skill"):
            return ValidationResult(result=False, message="skill name required for invoke.")
        if command == "list" and not input.get("path"):
            return ValidationResult(result=False, message="path required for list.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ASK, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = SkillInput.model_validate(args)

        if parsed.command == "list":
            search_dir = resolve_path(parsed.path or ".", context.cwd)
            skills_dir = search_dir / ".devin" / "skills"
            if not skills_dir.is_dir():
                return ToolResult(data="No skills directory found.")

            skills = [
                p.stem for p in skills_dir.iterdir()
                if p.is_file() and not p.name.startswith(".")
            ]
            if not skills:
                return ToolResult(data="No skills found.")
            return ToolResult(data="Available skills:\n" + "\n".join(f"  - {s}" for s in sorted(skills)))

        # invoke
        return ToolResult(
            data={
                "type": "skill_invoke",
                "skill": parsed.skill,
            }
        )

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Skill"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Running skill..."
