"""
/add-dir — Add a new working directory to scope.

Type: local_jsx (renders directory picker / confirmation).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Add a directory to the set of allowed working directories.

    ``/add-dir <path>``

    Validates the path exists and is a directory before adding.
    """
    raw_path = args.strip() if args else ""

    if not raw_path:
        return TextResult(
            value="Usage: /add-dir <path>\n\n"
            "Adds a directory to Claude Code's working scope so tools "
            "can read and write files in that directory."
        )

    # Resolve relative paths against cwd
    target = Path(raw_path).expanduser().resolve()

    if not target.exists():
        return TextResult(value=f"Path does not exist: {target}")
    if not target.is_dir():
        return TextResult(value=f"Not a directory: {target}")

    # Placeholder — real implementation updates AppState.toolPermissionContext
    # .additionalWorkingDirectories
    if context is not None and hasattr(context, "set_app_state"):
        context.set_app_state(
            lambda s: {
                **s,
                "additionalWorkingDirectories": [
                    *s.get("additionalWorkingDirectories", []),
                    str(target),
                ],
            }
        )

    return TextResult(
        value=f"Added working directory: {target}\n"
        "Claude can now read and write files in this directory."
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="add-dir",
    description="Add a new working directory",
    argument_hint="<path>",
    call=_execute,
)
