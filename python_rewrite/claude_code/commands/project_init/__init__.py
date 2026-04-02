"""
/project_init — Project-level initialization (alias / extended init).

Type: prompt (expands to content sent to the model).

Like ``/init`` but focused on project-specific setup: creating
``.claude/`` directories, settings files, and project-scoped rules.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...command_registry import PromptCommand, TextResult


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROJECT_INIT_PROMPT = """\
Initialize the Claude Code project configuration for this repository.

1. Create the `.claude/` directory structure if it doesn't exist:
   - `.claude/settings.json` — project-level settings
   - `.claude/skills/` — project skill definitions
   - `.claude/rules/` — scoped rule files

2. Scan for existing configuration:
   - Check for CLAUDE.md at the project root
   - Check for `.cursor/rules/`, `.cursorrules`, `.github/copilot-instructions.md`
   - Check for `.mcp.json` or `.claude/mcp.json`

3. Suggest initial configuration based on the project type:
   - Detect language/framework from manifest files
   - Propose appropriate permission rules
   - Suggest hooks for formatting/linting if tools are detected

4. Show a summary of what was created and next steps.
"""


async def _get_prompt_for_command(
    args: str = "", context: Any = None
) -> list[dict[str, str]]:
    return [{"type": "text", "text": _PROJECT_INIT_PROMPT}]


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = PromptCommand(
    name="project-init",
    description="Initialize project-level Claude Code configuration",
    progress_message="setting up project configuration",
    content_length=0,
    get_prompt_content=_get_prompt_for_command,
)
