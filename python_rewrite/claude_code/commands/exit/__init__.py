"""
/exit — Exit the REPL.

Type: local_jsx (immediate — no queuing).
"""

from __future__ import annotations

import sys
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Exit the Claude Code REPL.

    In the full implementation this triggers a graceful shutdown through the
    TUI framework.  Here we raise ``SystemExit`` so the outer REPL loop can
    catch it.
    """
    # Notify context of pending exit so cleanup hooks run
    if context is not None and hasattr(context, "request_exit"):
        context.request_exit()

    return TextResult(value="Goodbye!")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="exit",
    description="Exit the REPL",
    aliases=["quit"],
    immediate=True,
    call=_execute,
)
