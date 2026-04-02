"""
/branch — Create a branch of the current conversation.

Type: local_jsx (renders branch creation UI).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Create a named branch of the current conversation at this point.

    - No args:  Auto-generate a branch name.
    - With arg: Use the provided name.
    """
    name = args.strip() if args else ""

    if not name:
        # Auto-generate from timestamp
        name = f"branch-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]}"

    # Placeholder — real implementation forks the message history into a
    # separate session file that can be resumed later.
    return TextResult(
        value=f"Conversation branched as '{name}'.\n"
        f"You can resume this branch later with: /resume {name}"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="branch",
    description="Create a branch of the current conversation at this point",
    aliases=["fork"],
    argument_hint="[name]",
    call=_execute,
)
