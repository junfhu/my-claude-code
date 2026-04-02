"""
/skills — List and manage available skills.

Type: local_jsx (renders skill listing).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Skill discovery
# ---------------------------------------------------------------------------

_SKILL_DIRS = [
    Path.home() / ".claude" / "skills",
]


def _project_skill_dirs() -> list[Path]:
    cwd = Path(os.getcwd())
    return [
        cwd / ".claude" / "skills",
    ]


def _discover_skills() -> list[dict[str, str]]:
    """
    Scan skill directories for SKILL.md files and return metadata.
    """
    skills: list[dict[str, str]] = []
    all_dirs = _SKILL_DIRS + _project_skill_dirs()

    for skill_dir in all_dirs:
        if not skill_dir.is_dir():
            continue
        for entry in sorted(skill_dir.iterdir()):
            skill_md = entry / "SKILL.md" if entry.is_dir() else None
            if skill_md and skill_md.exists():
                content = skill_md.read_text(encoding="utf-8")
                # Parse YAML frontmatter (simple extraction)
                name = entry.name
                description = ""
                lines = content.splitlines()
                in_frontmatter = False
                for line in lines:
                    if line.strip() == "---":
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter:
                        if line.startswith("name:"):
                            name = line.split(":", 1)[1].strip()
                        elif line.startswith("description:"):
                            description = line.split(":", 1)[1].strip()
                    elif not in_frontmatter and not description:
                        # Use first non-empty line as description fallback
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            description = stripped[:80]

                skills.append({
                    "name": name,
                    "description": description or "(no description)",
                    "path": str(entry),
                    "source": str(skill_dir),
                })

    return skills


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """List all available skills."""
    skills = _discover_skills()

    if not skills:
        return TextResult(
            value="No skills found.\n"
            "Add skills to .claude/skills/<name>/SKILL.md"
        )

    lines = ["Available Skills", "=" * 40, ""]
    max_name = max(len(s["name"]) for s in skills)

    for s in skills:
        lines.append(f"  /{s['name']:<{max_name}}  — {s['description']}")
        lines.append(f"    {'':>{max_name}}    {s['path']}")

    lines.append("")
    lines.append(f"Total: {len(skills)} skill(s)")
    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="skills",
    description="List available skills",
    call=_execute,
)
