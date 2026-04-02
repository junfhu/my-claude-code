"""
Skill loading from filesystem.

Loads skills from ``~/.claude/skills/``, project ``.claude/skills/``,
managed directories, and parses SKILL.md frontmatter.

Mirrors src/skills/loadSkillsDir.ts.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from .types import Skill, SkillFrontmatter, SkillLoadedFrom, SkillSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL
)


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Returns ``(frontmatter_dict, remaining_content)``.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    yaml_str = match.group(1)
    body = content[match.end():]
    try:
        fm = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _extract_description(content: str, label: str = "Skill") -> str:
    """Extract a description from the first paragraph of markdown content."""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:200]
    return f"{label} (no description)"


def _parse_skill_frontmatter(fm: dict[str, Any], name: str) -> SkillFrontmatter:
    """Parse raw frontmatter dict into a SkillFrontmatter."""
    allowed_tools_raw = fm.get("allowed-tools", [])
    if isinstance(allowed_tools_raw, str):
        allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]
    elif isinstance(allowed_tools_raw, list):
        allowed_tools = [str(t) for t in allowed_tools_raw]
    else:
        allowed_tools = []

    arg_names_raw = fm.get("arguments", [])
    if isinstance(arg_names_raw, str):
        arg_names = [a.strip() for a in arg_names_raw.split(",") if a.strip()]
    elif isinstance(arg_names_raw, list):
        arg_names = [str(a) for a in arg_names_raw]
    else:
        arg_names = []

    paths_raw = fm.get("paths")
    paths: Optional[list[str]] = None
    if paths_raw:
        if isinstance(paths_raw, str):
            paths = [p.strip() for p in paths_raw.split(",") if p.strip()]
        elif isinstance(paths_raw, list):
            paths = [str(p) for p in paths_raw]
        # Remove match-all patterns
        if paths and all(p in ("**", "**/*") for p in paths):
            paths = None

    user_invocable = fm.get("user-invocable", True)
    if isinstance(user_invocable, str):
        user_invocable = user_invocable.lower() in ("true", "1", "yes")

    disable_model = fm.get("disable-model-invocation", False)
    if isinstance(disable_model, str):
        disable_model = disable_model.lower() in ("true", "1", "yes")

    return SkillFrontmatter(
        name=fm.get("name"),
        description=fm.get("description") if isinstance(fm.get("description"), str) else None,
        when_to_use=fm.get("when_to_use"),
        allowed_tools=allowed_tools,
        argument_hint=fm.get("argument-hint"),
        argument_names=arg_names,
        version=fm.get("version"),
        model=fm.get("model"),
        disable_model_invocation=disable_model,
        user_invocable=bool(user_invocable),
        paths=paths,
        context="fork" if fm.get("context") == "fork" else None,
        agent=fm.get("agent"),
        effort=str(fm.get("effort")) if fm.get("effort") is not None else None,
        shell=fm.get("shell"),
        hooks=fm.get("hooks"),
    )


# ---------------------------------------------------------------------------
# Directory loading
# ---------------------------------------------------------------------------

def get_skills_path(source: SkillSource) -> str:
    """Return the skills directory for a given source."""
    if source == SkillSource.POLICY_SETTINGS:
        managed = os.environ.get(
            "CLAUDE_MANAGED_CONFIG_DIR",
            "/etc/claude" if os.name != "nt" else r"C:\ProgramData\Claude",
        )
        return os.path.join(managed, ".claude", "skills")
    if source == SkillSource.USER_SETTINGS:
        config_dir = os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.join(os.path.expanduser("~"), ".claude"),
        )
        return os.path.join(config_dir, "skills")
    if source == SkillSource.PROJECT_SETTINGS:
        return os.path.join(".claude", "skills")
    return ""


def _load_skill_from_dir(
    skill_dir: str,
    source: SkillSource,
    loaded_from: SkillLoadedFrom = SkillLoadedFrom.SKILLS,
) -> Optional[Skill]:
    """Load a single skill from a directory containing SKILL.md."""
    skill_file = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_file):
        return None

    try:
        with open(skill_file, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Failed to read %s: %s", skill_file, exc)
        return None

    fm_dict, body = parse_frontmatter(raw_content)
    skill_name = os.path.basename(skill_dir)
    frontmatter = _parse_skill_frontmatter(fm_dict, skill_name)

    description = frontmatter.description or _extract_description(body)

    return Skill(
        name=skill_name,
        description=description,
        content=body,
        loaded_from=loaded_from,
        source=source,
        base_dir=skill_dir,
        frontmatter=frontmatter,
        file_path=skill_file,
        display_name=frontmatter.name,
        is_hidden=not frontmatter.user_invocable,
        content_length=len(body),
    )


def load_skills_from_dir(
    base_path: str,
    source: SkillSource,
    loaded_from: SkillLoadedFrom = SkillLoadedFrom.SKILLS,
) -> list[Skill]:
    """Load all skills from a ``skills/`` directory.

    Each subdirectory containing a ``SKILL.md`` is loaded as a skill.
    """
    if not os.path.isdir(base_path):
        return []

    skills: list[Skill] = []
    try:
        for entry in os.scandir(base_path):
            if entry.is_dir() or entry.is_symlink():
                skill = _load_skill_from_dir(entry.path, source, loaded_from)
                if skill:
                    skills.append(skill)
    except OSError as exc:
        logger.debug("Failed to scan %s: %s", base_path, exc)

    return skills


def load_all_skills(cwd: Optional[str] = None) -> list[Skill]:
    """Load skills from all sources with deduplication.

    Sources (in priority order):
    1. Managed/enterprise skills
    2. User skills (``~/.claude/skills/``)
    3. Project skills (``.claude/skills/``)
    """
    all_skills: list[Skill] = []
    seen_names: set[str] = set()

    # Managed skills
    managed_path = get_skills_path(SkillSource.POLICY_SETTINGS)
    for skill in load_skills_from_dir(managed_path, SkillSource.POLICY_SETTINGS, SkillLoadedFrom.MANAGED):
        if skill.name not in seen_names:
            all_skills.append(skill)
            seen_names.add(skill.name)

    # User skills
    user_path = get_skills_path(SkillSource.USER_SETTINGS)
    for skill in load_skills_from_dir(user_path, SkillSource.USER_SETTINGS):
        if skill.name not in seen_names:
            all_skills.append(skill)
            seen_names.add(skill.name)

    # Project skills (relative to cwd)
    if cwd:
        project_path = os.path.join(cwd, get_skills_path(SkillSource.PROJECT_SETTINGS))
    else:
        project_path = get_skills_path(SkillSource.PROJECT_SETTINGS)
    for skill in load_skills_from_dir(project_path, SkillSource.PROJECT_SETTINGS):
        if skill.name not in seen_names:
            all_skills.append(skill)
            seen_names.add(skill.name)

    # Walk parent directories for .claude/skills/
    if cwd:
        current = os.path.abspath(cwd)
        home = os.path.expanduser("~")
        while current != os.path.dirname(current):
            if current == home:
                break
            parent = os.path.dirname(current)
            parent_skills = os.path.join(parent, ".claude", "skills")
            if os.path.isdir(parent_skills) and parent_skills != project_path:
                for skill in load_skills_from_dir(parent_skills, SkillSource.PROJECT_SETTINGS):
                    if skill.name not in seen_names:
                        all_skills.append(skill)
                        seen_names.add(skill.name)
            current = parent

    return all_skills


def get_skill_by_name(name: str, cwd: Optional[str] = None) -> Optional[Skill]:
    """Find a skill by name across all sources."""
    for skill in load_all_skills(cwd):
        if skill.name == name:
            return skill
    return None
