"""
System prompt construction.

Builds the system prompt from base instructions, memory files,
tool descriptions, and context-specific sections.
"""

from __future__ import annotations

import os
import platform
import time
from typing import Any, Optional

from ..memdir.memory import read_memory_files, filter_injected_memory_files
from ..memdir.memory_utils import memory_content_for_prompt


SYSTEM_PROMPT_BASE = """You are Claude Code, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.

IMPORTANT: Refuse to write code or explain code that could be used for malicious purposes, even if the user claims it is for educational purposes. When in doubt, err on the side of caution.

# Memory
If the conversation starts with a <memory> block, it contains relevant instructions from CLAUDE.md files. Follow those instructions.

# Tone and style
- Be concise and direct. Avoid unnecessary preamble or postamble.
- Use markdown formatting for code blocks and technical content.
- When making changes to files, briefly explain what you changed and why.

# Proactive safety
- Do not execute potentially destructive commands without user confirmation.
- When in doubt about file paths, verify before modifying.
- Prefer non-destructive operations (e.g., creating new files over overwriting).

# Tool usage
- Use tools to accomplish tasks. Prefer precise tools over shell commands.
- When running shell commands, consider the user's operating system.
- Always read files before editing them to understand context.
"""


def build_system_prompt(
    *,
    tools: Optional[list[dict[str, Any]]] = None,
    cwd: Optional[str] = None,
    model: Optional[str] = None,
    extra_context: Optional[dict[str, str]] = None,
    memory_content: Optional[str] = None,
    coordinator_context: Optional[str] = None,
) -> str:
    """Construct the full system prompt for a Claude Code session."""
    parts: list[str] = [SYSTEM_PROMPT_BASE]

    # Environment context
    work_dir = cwd or os.getcwd()
    parts.append(f"\n# Environment\n- Working directory: {work_dir}")
    parts.append(f"- Platform: {platform.system()} {platform.machine()}")
    parts.append(f"- Date: {time.strftime('%Y-%m-%d')}")
    if model:
        parts.append(f"- Model: {model}")

    # Memory (CLAUDE.md content)
    if memory_content is None:
        files = read_memory_files(cwd)
        filtered = filter_injected_memory_files(files)
        if filtered:
            memory_content = memory_content_for_prompt(filtered)

    if memory_content:
        parts.append(f"\n<memory>\n{memory_content}\n</memory>")

    # Coordinator context
    if coordinator_context:
        parts.append(f"\n# Coordinator Mode\n{coordinator_context}")

    # Extra context
    if extra_context:
        for key, value in extra_context.items():
            parts.append(f"\n# {key}\n{value}")

    # Tool descriptions
    if tools:
        tool_desc = "\n".join(
            f"- **{t['name']}**: {t.get('description', '')}" for t in tools
        )
        parts.append(f"\n# Available Tools\n{tool_desc}")

    return "\n".join(parts)
