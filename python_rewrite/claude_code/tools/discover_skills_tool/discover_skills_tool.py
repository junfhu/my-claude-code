"""
DiscoverSkillsTool – Discover available skills in a project.
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
from claude_code.tools.utils import resolve_path


class DiscoverSkillsInput(BaseModel):
    path: str = Field(..., description="Project root path to scan for skills.")


class DiscoverSkillsTool(Tool):
    """Discover skills registered in a project."""

    name = "discover_skills"
    aliases: list[str] = []
    search_hint = "discover skills list available"

    def get_input_schema(self) -> dict[str, Any]:
        return DiscoverSkillsInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Discover skills available in a project directory."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        if not input.get("path", "").strip():
            return ValidationResult(result=False, message="path is required.")
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = DiscoverSkillsInput.model_validate(args)
        search_dir = resolve_path(parsed.path, context.cwd)
        skills_dir = search_dir / ".devin" / "skills"

        if not skills_dir.is_dir():
            return ToolResult(data=f"No skills directory found at {skills_dir}")

        skills = sorted(
            p.stem for p in skills_dir.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )

        if not skills:
            return ToolResult(data="Skills directory exists but is empty.")

        return ToolResult(
            data=f"Found {len(skills)} skill(s):\n" + "\n".join(f"  - {s}" for s in skills)
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "DiscoverSkills"
