"""
/init — Initialize project (create CLAUDE.md and optionally skills/hooks).

Type: prompt (expands to content sent to the model).

Scans the codebase and creates a minimal CLAUDE.md with build/test/lint
commands, architecture notes, and coding conventions.
"""

from __future__ import annotations

import os
from typing import Any

from ...command_registry import PromptCommand


# ---------------------------------------------------------------------------
# Feature-flag helper
# ---------------------------------------------------------------------------

def _is_init_disabled() -> bool:
    return os.environ.get("DISABLE_INIT_COMMAND", "").lower() in (
        "1", "true", "yes",
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_INIT_PROMPT = """\
Set up a minimal CLAUDE.md for this repo. CLAUDE.md is loaded into every \
Claude Code session, so it must be concise — only include what Claude would \
get wrong without it.

## Phase 1: Explore the codebase

Read key files to understand the project: manifest files (package.json, \
Cargo.toml, pyproject.toml, go.mod, pom.xml, etc.), README, Makefile/build \
configs, CI config, existing CLAUDE.md.

Detect:
- Build, test, and lint commands (especially non-standard ones)
- Languages, frameworks, and package manager
- Project structure (monorepo with workspaces, multi-module, or single project)
- Code style rules that differ from language defaults
- Non-obvious gotchas, required env vars, or workflow quirks

## Phase 2: Fill in the gaps

Ask the user about anything you couldn't figure out from code alone — \
non-obvious commands, gotchas, branch/PR conventions, required env setup, \
testing quirks.

## Phase 3: Write CLAUDE.md

Write a minimal CLAUDE.md at the project root. Every line must pass this \
test: "Would removing this cause Claude to make mistakes?" If no, cut it.

Include:
- Build/test/lint commands Claude can't guess
- Code style rules that DIFFER from language defaults
- Testing instructions and quirks
- Repo etiquette (branch naming, PR conventions, commit style)
- Required env vars or setup steps
- Non-obvious gotchas or architectural decisions

Exclude:
- File-by-file structure or component lists
- Standard language conventions Claude already knows
- Generic advice ("write clean code", "handle errors")
- Commands obvious from manifest files (e.g., standard "npm test")

Prefix the file with:

```
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working \
with code in this repository.
```

If CLAUDE.md already exists: read it, propose specific changes as diffs, \
and explain why each change improves it. Do not silently overwrite.
"""


async def _get_prompt_for_command(
    args: str = "", context: Any = None
) -> list[dict[str, str]]:
    return [{"type": "text", "text": _INIT_PROMPT}]


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = PromptCommand(
    name="init",
    description="Initialize project with CLAUDE.md",
    progress_message="initializing project",
    content_length=0,
    is_enabled=lambda: not _is_init_disabled(),
    get_prompt_content=_get_prompt_for_command,
)
