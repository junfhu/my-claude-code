"""
Skill execution engine.

Runs a loaded skill by substituting arguments, executing inline shell
commands, and returning the final prompt content.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any, Optional

from .types import Skill

logger = logging.getLogger(__name__)

# Matches ${ARG_NAME} placeholders
_ARG_RE = re.compile(r"\$\{(\w+)\}")

# Matches inline shell commands: !`command` or ```! command ```
_INLINE_SHELL_RE = re.compile(r"!`([^`]+)`")
_FENCED_SHELL_RE = re.compile(r"```!\s*\n(.*?)\n```", re.DOTALL)


def substitute_arguments(
    content: str,
    args: str,
    *,
    strip_unused: bool = True,
    arg_names: Optional[list[str]] = None,
) -> str:
    """Replace ``${ARG}`` placeholders in *content* with values from *args*.

    If *arg_names* is provided, positional arguments from *args* are mapped
    to those names. Otherwise, ``${ARGUMENTS}`` is replaced with the full string.
    """
    if arg_names:
        parts = args.split(None, len(arg_names) - 1)
        for i, name in enumerate(arg_names):
            value = parts[i] if i < len(parts) else ""
            content = content.replace(f"${{{name}}}", value)
    else:
        content = content.replace("${ARGUMENTS}", args)

    # Replace ${CLAUDE_SKILL_DIR} and ${CLAUDE_SESSION_ID}
    content = content.replace(
        "${CLAUDE_SESSION_ID}",
        os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown"),
    )

    if strip_unused:
        content = _ARG_RE.sub("", content)

    return content


def _execute_shell_command(cmd: str, cwd: Optional[str] = None) -> str:
    """Execute a shell command and return its stdout."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        if result.returncode != 0:
            logger.warning("Shell command failed: %s (exit %d)", cmd, result.returncode)
            return f"[Command failed with exit code {result.returncode}]\n{result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "[Command timed out after 30s]"
    except Exception as exc:
        return f"[Command error: {exc}]"


def execute_shell_commands_in_content(
    content: str,
    cwd: Optional[str] = None,
) -> str:
    """Execute inline shell commands (``!`cmd```) and fenced shell blocks
    (``````! cmd ``````) in skill content, replacing them with their output.
    """
    # Fenced blocks first (they may contain backticks)
    def _replace_fenced(m: re.Match[str]) -> str:
        return _execute_shell_command(m.group(1).strip(), cwd)

    content = _FENCED_SHELL_RE.sub(_replace_fenced, content)

    # Inline commands
    def _replace_inline(m: re.Match[str]) -> str:
        return _execute_shell_command(m.group(1).strip(), cwd)

    content = _INLINE_SHELL_RE.sub(_replace_inline, content)
    return content


def run_skill(
    skill: Skill,
    args: str = "",
    *,
    execute_shell: bool = True,
) -> list[dict[str, str]]:
    """Execute a skill and return its content as message blocks.

    Steps:
    1. Substitute arguments into the skill content
    2. Replace ``${CLAUDE_SKILL_DIR}`` with the skill's base directory
    3. Execute inline shell commands (unless the skill is from MCP)
    4. Return the final content as a list of ``{type: "text", text: ...}``

    Returns:
        List of content blocks suitable for injection into the conversation.
    """
    content = skill.content

    # Prepend base directory context
    if skill.base_dir:
        content = f"Base directory for this skill: {skill.base_dir}\n\n{content}"

    # Substitute arguments
    content = substitute_arguments(
        content,
        args,
        arg_names=skill.frontmatter.argument_names or None,
    )

    # Replace ${CLAUDE_SKILL_DIR}
    if skill.base_dir:
        skill_dir = skill.base_dir
        if os.name == "nt":
            skill_dir = skill_dir.replace("\\", "/")
        content = content.replace("${CLAUDE_SKILL_DIR}", skill_dir)

    # Execute shell commands (not for MCP skills — they are remote/untrusted)
    if execute_shell and skill.loaded_from.value != "mcp":
        content = execute_shell_commands_in_content(content, cwd=skill.base_dir)

    return [{"type": "text", "text": content}]
