"""
/commit — Git commit with AI-generated message.

Type: prompt (expands to content sent to the model).

Gathers the current git status / diff and asks the model to craft a commit
message, stage relevant files, and create the commit.
"""

from __future__ import annotations

import subprocess
from typing import Any

from ...command_registry import PromptCommand


# ---------------------------------------------------------------------------
# Allowed tools for sandboxed execution
# ---------------------------------------------------------------------------

ALLOWED_TOOLS = [
    "Bash(git add:*)",
    "Bash(git status:*)",
    "Bash(git commit:*)",
]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _get_prompt_content() -> str:
    """Build the system/user prompt for the commit command."""
    return """## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`

## Git Safety Protocol

- NEVER update the git config
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly requests it
- CRITICAL: ALWAYS create NEW commits. NEVER use git commit --amend, unless the user explicitly requests it
- Do not commit files that likely contain secrets (.env, credentials.json, etc). Warn the user if they specifically request to commit those files
- If there are no changes to commit (i.e., no untracked files and no modifications), do not create an empty commit
- Never use git commands with the -i flag (like git rebase -i or git add -i) since they require interactive input which is not supported

## Your task

Based on the above changes, create a single git commit:

1. Analyze all staged changes and draft a commit message:
   - Look at the recent commits above to follow this repository's commit message style
   - Summarize the nature of the changes (new feature, enhancement, bug fix, refactoring, test, docs, etc.)
   - Ensure the message accurately reflects the changes and their purpose (i.e. "add" means a wholly new feature, "update" means an enhancement to an existing feature, "fix" means a bug fix, etc.)
   - Draft a concise (1-2 sentences) commit message that focuses on the "why" rather than the "what"

2. Stage relevant files and create the commit using HEREDOC syntax:
```
git commit -m "$(cat <<'EOF'
Commit message here.
EOF
)"
```

You have the capability to call multiple tools in a single response. Stage and create the commit using a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls."""


async def _get_prompt_for_command(
    args: str = "", context: Any = None
) -> list[dict[str, str]]:
    """Return content blocks to send to the model."""
    prompt = _get_prompt_content()

    # In the full implementation, shell commands prefixed with !` ` are
    # expanded via ``execute_shell_commands_in_prompt()``.  Placeholder
    # returns the raw prompt; the REPL layer handles expansion.
    return [{"type": "text", "text": prompt}]


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = PromptCommand(
    name="commit",
    description="Create a git commit",
    progress_message="creating commit",
    content_length=0,  # Dynamic content
    allowed_tools=ALLOWED_TOOLS,
    get_prompt_content=_get_prompt_for_command,
)
