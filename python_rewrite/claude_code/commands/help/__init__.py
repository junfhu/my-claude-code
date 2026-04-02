"""
/help — Show all available commands.

Type: local_jsx (renders a formatted table of commands).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ...command_registry import (
    Command,
    LocalJSXCommand,
    TextResult,
    get_command_name,
    is_command_enabled,
)

if TYPE_CHECKING:
    from ...command_registry import Command as CommandType


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Build and return a formatted help listing of all slash commands.

    Mirrors the React/Ink component from the TS source — here we produce
    plain-text output suitable for a terminal.
    """
    from ...command_registry import get_all_commands, meets_availability_requirement

    commands = get_all_commands()

    # Group commands by visibility
    visible_commands = [
        cmd
        for cmd in commands
        if (
            meets_availability_requirement(cmd)
            and is_command_enabled(cmd)
            and not cmd.hidden
        )
    ]

    # Sort alphabetically by user-facing name
    visible_commands.sort(key=lambda c: get_command_name(c))

    # Build output lines
    lines: list[str] = []
    lines.append("Available commands:\n")

    # Calculate column width for alignment
    max_name_len = max(
        (len(get_command_name(cmd)) for cmd in visible_commands),
        default=10,
    )

    for cmd in visible_commands:
        name = get_command_name(cmd)
        desc = cmd.description
        aliases_str = ""
        if cmd.aliases:
            aliases_str = f"  (aliases: {', '.join(cmd.aliases)})"
        hint = ""
        if cmd.argument_hint:
            hint = f" {cmd.argument_hint}"

        lines.append(f"  /{name:<{max_name_len}}{hint}  — {desc}{aliases_str}")

    lines.append("")
    lines.append(
        "Type /<command> to run a command.  "
        "Use Tab for autocomplete."
    )

    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="help",
    description="Show help and available commands",
    aliases=["?", "h"],
    call=_execute,
)
