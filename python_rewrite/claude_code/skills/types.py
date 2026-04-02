"""
Skill type definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional


class SkillLoadedFrom(str, Enum):
    """Where a skill was loaded from."""
    COMMANDS_DEPRECATED = "commands_DEPRECATED"
    SKILLS = "skills"
    PLUGIN = "plugin"
    MANAGED = "managed"
    BUNDLED = "bundled"
    MCP = "mcp"


class SkillSource(str, Enum):
    """Config source that provided the skill."""
    POLICY_SETTINGS = "policySettings"
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"


@dataclass
class SkillFrontmatter:
    """Parsed frontmatter from a SKILL.md file."""
    name: Optional[str] = None
    description: Optional[str] = None
    when_to_use: Optional[str] = None
    allowed_tools: list[str] = field(default_factory=list)
    argument_hint: Optional[str] = None
    argument_names: list[str] = field(default_factory=list)
    version: Optional[str] = None
    model: Optional[str] = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    paths: Optional[list[str]] = None
    context: Optional[str] = None  # "fork" or None (inline)
    agent: Optional[str] = None
    effort: Optional[str] = None
    shell: Optional[dict[str, Any]] = None
    hooks: Optional[dict[str, Any]] = None


@dataclass
class Skill:
    """A loaded skill ready for invocation."""
    name: str
    description: str
    content: str
    loaded_from: SkillLoadedFrom
    source: Optional[SkillSource] = None
    base_dir: Optional[str] = None
    frontmatter: SkillFrontmatter = field(default_factory=SkillFrontmatter)
    file_path: Optional[str] = None
    display_name: Optional[str] = None
    is_hidden: bool = False
    content_length: int = 0

    def user_facing_name(self) -> str:
        return self.display_name or self.name

    @property
    def is_user_invocable(self) -> bool:
        return self.frontmatter.user_invocable and not self.is_hidden
